"""Consolidación del Coaching MORE hacia el KPI Coaching del Score Integral.

Opción disponible (decisión del cliente): cuando decida dejar su Excel y usar VISTA,
vuelca los promedios MORE de un (ciclo, país) hacia:
  • Opción 1 — DW.FACT_Coaching  (componente "Coaching" del Score).
  • Opción 2 — DW.FACT_ResultadoIndicador para el indicador EVAL_COACHING
    (mismo patrón que la consolidación de Exámenes → EVAL_CONOCIMIENTOS).

Ambas son idempotentes (delete-then-insert de SOLO las filas marcadas como MORE, sin
tocar la carga legado por Excel) y disparan el recálculo del ciclo (solo ciclo ABIERTO).
El promedio MORE (1..4) se lleva a 0..100 con `avg/4*100`.
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.coaching_more_models import CoachingSesion
from app.models.hechos import Coaching, ResultadoIndicador
from app.models.dimensiones import RepresentanteMedico, Indicador
from app.services import recalculo_service, puntaje_service
from app.services.coaching_more_service import META_HOJAS_POR_RM

_TAG = "Coaching MORE (consolidado)"


def _promedios_por_rm(db: Session, ciclo_id: int, pais_codigo: str | None) -> dict:
    """{rm_id: (avg_1a4, n_hojas)} de hojas VIGENTES (excluye las enmendadas)."""
    q = db.query(CoachingSesion).filter(CoachingSesion.ciclo_id == ciclo_id)
    if pais_codigo:
        q = q.filter(CoachingSesion.pais_codigo == pais_codigo)
    hojas = q.all()
    enmendadas = {h.corrige_a_id for h in hojas if h.corrige_a_id}
    vigentes = [h for h in hojas if h.id not in enmendadas]
    agg: dict[int, list] = {}
    gd_gerente: dict[int, int | None] = {}
    for h in vigentes:
        agg.setdefault(h.rm_id, []).append(float(h.evaluacion_promedio))
        gd_gerente.setdefault(h.rm_id, h.gd_gerente_id)
    return {rm: (sum(v) / len(v), len(v), gd_gerente.get(rm)) for rm, v in agg.items()}


# ── Opción 1 — FACT_Coaching ──────────────────────────────────────────────────

def consolidar_fact_coaching(db: Session, ciclo_id: int, pais_codigo: str) -> dict:
    recalculo_service.validar_ciclo_abierto(db, ciclo_id)  # CicloCerradoError si está cerrado
    proms = _promedios_por_rm(db, ciclo_id, pais_codigo)

    # Idempotente: borra solo lo consolidado antes por MORE (respeta la carga por Excel).
    db.query(Coaching).filter(
        Coaching.ciclo_id == ciclo_id, Coaching.observaciones == _TAG).delete(synchronize_session=False)

    insertadas, omitidos = 0, []
    for rm_id, (avg, n, gd_ger) in proms.items():
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
        if not rm:
            continue
        gerente_id = rm.gerente_id or gd_ger
        if not gerente_id:
            omitidos.append(rm_id)
            continue
        calidad = Decimal(str(round(avg / 4 * 100, 2)))            # 1..4 → 0..100
        programado = META_HOJAS_POR_RM
        cumpl = Decimal(str(min(100.0, n / programado * 100) if programado else 0))
        puntaje = puntaje_service.calcular_puntaje_coaching(cumpl, calidad, Decimal("0.7"), Decimal("0.3"))
        db.add(Coaching(
            pais_codigo=rm.pais_codigo, gerente_id=gerente_id, rm_id=rm_id, ciclo_id=ciclo_id,
            tipo="CAMPO", coaching_programado=programado, coaching_ejecutado=n,
            cumplimiento_pct=cumpl, calificacion_calidad=calidad,
            peso_cantidad=Decimal("0.7"), peso_calidad=Decimal("0.3"),
            resultado_coaching=puntaje, puntaje=puntaje, observaciones=_TAG))
        insertadas += 1
    db.commit()
    logger.info(f"Coaching MORE → FACT_Coaching: ciclo={ciclo_id} país={pais_codigo} "
                f"{insertadas} RMs (omitidos sin gerente: {len(omitidos)})")
    recalculo = recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
    return {"destino": "FACT_Coaching", "rms_consolidados": insertadas,
            "omitidos_sin_gerente": omitidos, "recalculo": recalculo}


# ── Opción 2 — EVAL_COACHING (FACT_ResultadoIndicador) ────────────────────────

def consolidar_indicador(db: Session, ciclo_id: int, pais_codigo: str) -> dict:
    recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    ind = db.query(Indicador).filter(
        Indicador.codigo == "EVAL_COACHING", Indicador.pais_codigo == pais_codigo).first()
    if not ind:
        raise ValueError(f"No existe el indicador EVAL_COACHING para el país {pais_codigo}. "
                         f"Créalo en Configuración → Indicadores antes de consolidar.")
    proms = _promedios_por_rm(db, ciclo_id, pais_codigo)

    db.query(ResultadoIndicador).filter(
        ResultadoIndicador.indicador_id == ind.id,
        ResultadoIndicador.ciclo_id == ciclo_id).delete(synchronize_session=False)

    insertadas = 0
    for rm_id, (avg, _n, _g) in proms.items():
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
        if not rm:
            continue
        valor = Decimal(str(round(avg / 4 * 100, 2)))    # 1..4 → 0..100
        db.add(ResultadoIndicador(
            pais_codigo=rm.pais_codigo, linea_id=rm.linea_id, gerente_id=rm.gerente_id,
            rm_id=rm_id, indicador_id=ind.id, ciclo_id=ciclo_id,
            resultado_real=valor, activo=True))
        insertadas += 1
    db.commit()
    logger.info(f"Coaching MORE → EVAL_COACHING: ciclo={ciclo_id} país={pais_codigo} {insertadas} RMs")
    # El recálculo completa resultado_porcentaje/puntos y regenera Score+Ranking.
    recalculo = recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
    return {"destino": "EVAL_COACHING", "indicador_id": ind.id,
            "rms_consolidados": insertadas, "recalculo": recalculo}
