"""Calendario de Coaching (§7).

Consume el cuadrante LSII vigente (FACT_EvaluacionReceptividad) — NO lo recalcula —
y sugiere una frecuencia de acompañamiento por RM, repartida en el ciclo. El GD
edita y publica. Es planeación; la ejecución del coaching vive en Coaching MORE.
"""
from datetime import datetime, timezone
from math import ceil

from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.models.formacion import CalendarioCoachingSugerido, ParametroFrecuenciaLSII
from app.models.hechos import EvaluacionReceptividad
from app.services import visita_costo_service
from app.services.recalculo_service import validar_ciclo_abierto

CUADRANTES: tuple[str, ...] = ("D1", "D2", "D3", "D4")

#: Arranque del §7.2 (ilustrativo, punto abierto 4): a menor desarrollo, más
#: acompañamiento. Editable por país en ParametroFrecuenciaLSII.
FRECUENCIA_DEFECTO: dict[str, int] = {"D1": 4, "D2": 3, "D3": 2, "D4": 1}

SEMANAS_DEFECTO = 8  # biciclo típico si el ciclo no trae fechas


def semanas_ciclo(ciclo) -> int:
    """Semanas que abarca el ciclo, por sus fechas; fallback al biciclo típico."""
    ini = getattr(ciclo, "fecha_inicio", None)
    fin = getattr(ciclo, "fecha_fin", None)
    if ini and fin and fin >= ini:
        return max(1, ceil(((fin - ini).days + 1) / 7))
    return SEMANAS_DEFECTO


def distribuir_semanas(n: int, semanas: int) -> list[int]:
    """Reparte n visitas espaciadas entre 1..semanas.

    La i-ésima cae en round((i+0.5)*semanas/n), acotada a [1, semanas]. Para
    n=4, semanas=8 da [1,3,5,7]; para n=1 da la mitad del ciclo."""
    if n <= 0 or semanas <= 0:
        return []
    return [min(semanas, max(1, round((i + 0.5) * semanas / n))) for i in range(n)]


def frecuencias(db: Session, pais_codigo: str) -> dict[str, int]:
    """Los valores de arranque, con las sobrescrituras del país."""
    valores = dict(FRECUENCIA_DEFECTO)
    for p in (db.query(ParametroFrecuenciaLSII)
              .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo).all()):
        if p.cuadrante in valores:
            valores[p.cuadrante] = int(p.visitas_por_ciclo)
    return valores


def cuadrante_vigente(db: Session, rm_id: int, ciclo_id: int) -> str | None:
    """Cuadrante D1-D4 de la última evaluación LSII activa del RM en el ciclo.

    Solo lee: el cálculo del cuadrante es del módulo LSII, no de aquí."""
    e = (db.query(EvaluacionReceptividad)
         .filter(EvaluacionReceptividad.rm_id == rm_id,
                 EvaluacionReceptividad.ciclo_id == ciclo_id,
                 EvaluacionReceptividad.activo.is_(True))
         .order_by(EvaluacionReceptividad.id.desc())
         .first())
    return e.nivel_lsii if e else None


def ciclo_anterior_id(db: Session, ciclo) -> int | None:
    """El ciclo inmediatamente anterior del mismo país (por anio, numero)."""
    prev = (db.query(Ciclo)
            .filter(Ciclo.pais_codigo == ciclo.pais_codigo,
                    (Ciclo.anio < ciclo.anio) |
                    ((Ciclo.anio == ciclo.anio) & (Ciclo.numero < ciclo.numero)))
            .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
            .first())
    return prev.id if prev else None


def orden_por_roi(db: Session, rm_ids: list[int], ciclo_anterior_id: int | None) -> list[int]:
    """Ordena los RM por ROI ASCENDENTE del ciclo anterior (menor ROI = más
    atención = primero). RM sin ROI previo o sin ciclo anterior → al final,
    conservando el orden de entrada (estable)."""
    roi_map: dict[int, float] = {}
    if ciclo_anterior_id is not None:
        rk = visita_costo_service.roi_ranking(db, ciclo_anterior_id)
        roi_map = {it["vm_id"]: it["valor"] for it in rk.get("items", [])}
    orden_entrada = {rm: i for i, rm in enumerate(rm_ids)}
    return sorted(rm_ids, key=lambda rm: (roi_map.get(rm, float("inf")), orden_entrada[rm]))


def fijar_frecuencia(db: Session, pais_codigo: str, cuadrante: str, visitas: int,
                     descripcion: str | None = None) -> ParametroFrecuenciaLSII:
    if cuadrante not in CUADRANTES:
        raise ValueError(f"Cuadrante inválido: {cuadrante}. Válidos: {', '.join(CUADRANTES)}.")
    if visitas < 0:
        raise ValueError("visitas_por_ciclo no puede ser negativo.")
    p = (db.query(ParametroFrecuenciaLSII)
         .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo,
                 ParametroFrecuenciaLSII.cuadrante == cuadrante).first())
    if p is None:
        p = ParametroFrecuenciaLSII(pais_codigo=pais_codigo, cuadrante=cuadrante,
                                    visitas_por_ciclo=visitas, descripcion=descripcion)
        db.add(p)
    else:
        p.visitas_por_ciclo = visitas
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p


DIAS: list[str] = ["lunes", "martes", "miercoles", "jueves", "viernes"]


def generar(db: Session, gd_id: int, ciclo_id: int, persistir: bool = True) -> dict:
    """Sugiere el calendario del GD para el ciclo. persistir=False = previa.

    Persistir hace delete-then-insert SELECTIVO: borra solo las celdas sugeridas
    (no publicadas ni editadas a mano) y reinserta; conserva el trabajo del GD."""
    ciclo = validar_ciclo_abierto(db, ciclo_id)   # levanta CicloCerradoError si está cerrado
    semanas = semanas_ciclo(ciclo)
    frec = frecuencias(db, ciclo.pais_codigo)
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.gerente_id == gd_id).all())
    nombre = {rm.id: rm.nombre for rm in rms}

    con_cuadrante: list[tuple[int, str]] = []
    sin_evaluar: list[dict] = []
    for rm in rms:
        q = cuadrante_vigente(db, rm.id, ciclo_id)
        if q is None:
            sin_evaluar.append({"rm_id": rm.id, "rm_nombre": rm.nombre})
        else:
            con_cuadrante.append((rm.id, q))

    orden = orden_por_roi(db, [rm_id for rm_id, _ in con_cuadrante],
                          ciclo_anterior_id(db, ciclo))
    quad = dict(con_cuadrante)

    celdas: list[dict] = []
    for idx, rm_id in enumerate(orden):
        q = quad[rm_id]
        dia = DIAS[idx % len(DIAS)]          # reparte los RM entre los días
        for semana in distribuir_semanas(frec.get(q, 0), semanas):
            celdas.append({"rm_id": rm_id, "rm_nombre": nombre[rm_id],
                           "semana": semana, "dia_semana": dia, "cuadrante": q})

    if persistir:
        # Borra solo lo sugerido (no publicado ni editado); conserva el trabajo del GD.
        (db.query(CalendarioCoachingSugerido)
         .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                 CalendarioCoachingSugerido.ciclo_id == ciclo_id,
                 CalendarioCoachingSugerido.publicado.is_(False),
                 CalendarioCoachingSugerido.editado_manualmente.is_(False))
         .delete(synchronize_session=False))
        db.flush()
        # RMs con celdas preservadas (publicadas/editadas): NO se re-agendan, o se
        # duplicarían con la nueva sugerencia.
        preservados = {rm_id for (rm_id,) in
                       db.query(CalendarioCoachingSugerido.rm_id)
                       .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                               CalendarioCoachingSugerido.ciclo_id == ciclo_id)
                       .distinct().all()}
        insertadas = [c for c in celdas if c["rm_id"] not in preservados]
        for c in insertadas:
            db.add(CalendarioCoachingSugerido(
                gd_id=gd_id, ciclo_id=ciclo_id, rm_id=c["rm_id"], semana=c["semana"],
                dia_semana=c["dia_semana"], cuadrante_al_generar=c["cuadrante"]))
        db.commit()
    else:
        insertadas = celdas

    return {"semanas": semanas, "celdas": insertadas, "sin_evaluar": sin_evaluar}


def listar(db: Session, gd_id: int, ciclo_id: int) -> list[CalendarioCoachingSugerido]:
    return (db.query(CalendarioCoachingSugerido)
            .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                    CalendarioCoachingSugerido.ciclo_id == ciclo_id)
            .order_by(CalendarioCoachingSugerido.rm_id, CalendarioCoachingSugerido.semana)
            .all())


def mover_celda(db: Session, celda_id: int, semana: int,
                dia_semana: str) -> CalendarioCoachingSugerido:
    c = db.get(CalendarioCoachingSugerido, celda_id)
    if c is None:
        raise ValueError("Celda no encontrada")
    validar_ciclo_abierto(db, c.ciclo_id)
    if dia_semana not in DIAS:
        raise ValueError(f"Día inválido: {dia_semana}. Válidos: {', '.join(DIAS)}.")
    c.semana = semana
    c.dia_semana = dia_semana
    c.editado_manualmente = True
    db.commit()
    db.refresh(c)
    return c


def publicar(db: Session, gd_id: int, ciclo_id: int) -> int:
    validar_ciclo_abierto(db, ciclo_id)
    ahora = datetime.now(timezone.utc)
    filas = (db.query(CalendarioCoachingSugerido)
             .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                     CalendarioCoachingSugerido.ciclo_id == ciclo_id).all())
    for c in filas:
        c.publicado = True
        c.publicado_en = ahora
    db.commit()
    return len(filas)
