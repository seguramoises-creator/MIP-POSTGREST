"""
SCGCPR — Motor de Score Integral del RM (Ranking Regional / Histórico Anual)
FIX C-02: Los pesos se leen desde DIM_Indicador.peso_iup en BD,
          NO desde constantes hardcodeadas.
FIX W-08: Consistencia de RMs nuevos usa 0 como base neutral en lugar
          de 50, para evitar ventaja artificial sobre RMs con historial.

REDISEÑO (jul-2026, auditoría pre-lanzamiento): el diseño original de 5
componentes (Productividad + Comercial + Coaching + Capacitación +
Consistencia, cada uno ponderado por DIM_Indicador.peso_iup) asumía que
Comercial/Coaching/Capacitación se cargaban por separado en FACT_Ventas/
FACT_EVOIR/FACT_Coaching/FACT_Capacitacion. En la práctica esas 4 tablas están
prácticamente vacías (la carga real entra por el Excel unificado KPI_RM, un
solo FACT_ResultadoIndicador con los 8 KPIs reales) — confirmado con conteos
reales (scripts/diagnostics/verificar_tablas_legacy_comercial.py: 9/0/2/0
filas para RD). Eso hacía que 3 de los 5 componentes dieran 0 siempre, y el
score real terminara en 18-28 en vez de una escala 0-100 con sentido.

Fórmula nueva (validada contra datos reales antes de aplicarse, ver
scripts/diagnostics/probar_formula_propuesta.py):
    score = kpi_score × (1 − peso_consistencia) + consistencia × peso_consistencia
donde:
  - kpi_score es EXACTAMENTE la misma fórmula que ya usa el Ranking Mensual real
    (motor_calculo_service.generar_ranking): suma de puntos_obtenidos de los 8
    KPIs reales (Gestión + Resultados juntos, sin separar en categorías),
    ponderados por Indicador.ponderacion_pct ("Peso (pts)", la configuración que
    de verdad se mantiene en Administración → Indicadores).
  - consistencia sigue el mismo cálculo de siempre (promedio del score
    consolidado de hasta los 3 ciclos previos).
El nombre "IUP" se conserva como métrica interna, aunque la salida consolidada
se persiste como FACT_ScoreIntegralRM.score_total.
"""
from decimal import Decimal
from sqlalchemy.orm import Session
from sqlalchemy import func
from loguru import logger

from app.models.hechos import ResultadoIndicador, ScoreIntegralRM
from app.models.dimensiones import Indicador, Ciclo

# Peso de Consistencia por defecto — usado si DIM_Indicador no tiene un módulo
# "CONSISTENCIA" configurado (nunca lo tiene en la práctica: no es un KPI real,
# así que este default es efectivamente el valor vigente siempre).
_PESOS_DEFECTO = {
    "CONSISTENCIA": Decimal("0.15"),
}


def _obtener_pesos(db: Session) -> dict:
    """
    Lee los pesos configurados desde DIM_Indicador.peso_iup agrupados por
    módulo, normalizados a que sumen 1.0. `calcular_iup` solo usa la clave
    CONSISTENCIA de este resultado — la ponderación real de los KPIs viene de
    Indicador.ponderacion_pct (ver `_get_puntaje_kpis`), no de peso_iup.
    """
    rows = (
        db.query(
            Indicador.modulo,
            func.sum(Indicador.peso_iup).label("peso_total"),
        )
        .filter(Indicador.activo == True, Indicador.peso_iup > 0)  # noqa: E712
        .group_by(Indicador.modulo)
        .all()
    )

    if not rows:
        logger.debug("SCORE: sin pesos en DIM_Indicador — usando pesos por defecto")
        return _PESOS_DEFECTO.copy()

    pesos = {r.modulo: Decimal(str(r.peso_total)) for r in rows}

    # Normalizar para que sumen 1.0 (por si la configuración no está balanceada)
    total = sum(pesos.values()) or Decimal("1")
    pesos_norm = {k: v / total for k, v in pesos.items()}

    # Garantizar clave CONSISTENCIA (no es un módulo de indicadores)
    if "CONSISTENCIA" not in pesos_norm:
        pesos_norm["CONSISTENCIA"] = _PESOS_DEFECTO["CONSISTENCIA"]
        # Re-normalizar dejando espacio para consistencia
        resto = Decimal("1") - pesos_norm["CONSISTENCIA"]
        otros = {k: v for k, v in pesos_norm.items() if k != "CONSISTENCIA"}
        total_otros = sum(otros.values()) or Decimal("1")
        for k in otros:
            pesos_norm[k] = (otros[k] / total_otros) * resto

    logger.debug(f"SCORE pesos leídos de BD: {pesos_norm}")
    return pesos_norm


def calcular_iup(
    db: Session,
    rm_id: int,
    pais_codigo: str,
    ciclo_id: int,
) -> dict:
    """
    Calcula el score integral (antes "IUP") para un RM en un ciclo dado —
    usado por el Ranking Regional/Histórico Anual (ver ranking_service).
    """
    logger.debug(f"Calculando score integral — rm_id={rm_id}, ciclo_id={ciclo_id}")

    pesos = _obtener_pesos(db)
    peso_consistencia = pesos.get("CONSISTENCIA", _PESOS_DEFECTO["CONSISTENCIA"])

    kpis = _get_puntaje_kpis(db, rm_id, pais_codigo, ciclo_id)
    cons = _get_puntaje_consistencia(db, rm_id, pais_codigo, ciclo_id)

    score = kpis * (Decimal("1") - peso_consistencia) + cons * peso_consistencia
    score = max(Decimal("0"), min(score, Decimal("100")))

    return {
        "rm_id":            rm_id,
        "pais_codigo":      pais_codigo,
        "ciclo_id":         ciclo_id,
        "iup_kpis":         round(kpis, 4),
        "iup_consistencia": round(cons, 4),
        "iup_total":        round(score, 4),
        "score_total":      round(score, 4),
        "pesos_aplicados":  {
            "KPIS": float(Decimal("1") - peso_consistencia),
            "CONSISTENCIA": float(peso_consistencia),
        },
    }


def _get_puntaje_kpis(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    """
    Score de los KPIs reales del ciclo (los 8 de Administración → Indicadores,
    Gestión + Resultados juntos) — misma fórmula que el Ranking Mensual real
    (motor_calculo_service.generar_ranking):
        SUM(puntos_obtenidos) × 100 / SUM(ponderacion_pct)
    Fuente: FACT_ResultadoIndicador.puntos_obtenidos + Indicador.ponderacion_pct.
    """
    puntos, pond = (
        db.query(
            func.sum(ResultadoIndicador.puntos_obtenidos),
            func.sum(Indicador.ponderacion_pct),
        )
        .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
        .filter(
            ResultadoIndicador.rm_id == rm_id,
            ResultadoIndicador.pais_codigo == pais_codigo,
            ResultadoIndicador.ciclo_id == ciclo_id,
            ResultadoIndicador.activo == True,  # noqa: E712
            ResultadoIndicador.puntos_obtenidos.isnot(None),
        )
        .first()
    ) or (None, None)

    if not puntos or not pond:
        return Decimal("0")
    return Decimal(str(puntos)) * Decimal("100") / Decimal(str(pond))


def _get_puntaje_consistencia(db: Session, rm_id: int, pais_codigo: str, ciclo_id: int) -> Decimal:
    """
    CLAUDE.md §7 "IUP consistencia completo": componente de consistencia
    calculado como el promedio del score consolidado
    (FACT_ScoreIntegralRM.score_total) de los últimos 3 ciclos PREVIOS del
    RM — ordenados cronológicamente (DIM_Ciclo.anio/numero descendente),
    excluyendo el ciclo que se está calculando.

    Reglas:
      - Si tiene 3 o más ciclos con historial -> promedio de los 3 más recientes.
      - Si tiene 1-2 ciclos -> promedio de los disponibles.
      - Si no tiene historial (RM nuevo) -> 0 (base neutral, FIX W-08:
        evita ventaja artificial de un RM nuevo frente a uno con trayectoria).

    Nota: se lee de FACT_ScoreIntegralRM (no de FACT_RankingRM) porque es la
    tabla que persiste el score consolidado por RM/ciclo de forma
    independiente del tipo de ranking — la fuente correcta de "historial".
    """
    rows = (
        db.query(ScoreIntegralRM.score_total)
        .join(Ciclo, Ciclo.id == ScoreIntegralRM.ciclo_id)
        .filter(
            ScoreIntegralRM.rm_id    == rm_id,
            ScoreIntegralRM.pais_codigo  == pais_codigo,
            ScoreIntegralRM.ciclo_id != ciclo_id,
        )
        .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
        .limit(3)
        .all()
    )

    if not rows:
        logger.debug(f"CONSISTENCIA: RM {rm_id} sin historial previo — usando base neutral 0")
        return Decimal("0")

    valores = [Decimal(str(r[0] or 0)) for r in rows]
    promedio = sum(valores) / Decimal(len(valores))
    logger.debug(
        f"CONSISTENCIA: RM {rm_id} — {len(valores)} ciclo(s) previos, "
        f"promedio={promedio}"
    )
    return promedio
