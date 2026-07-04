"""SCGCPR — Consolidación de exámenes → EVAL_CONOCIMIENTOS por (ciclo, país).

Gate del módulo: la nota EVAL_CONOCIMIENTOS de los RM entra al KPI SOLO cuando
Capacitación ejecuta esta consolidación. La entrega individual ya no alimenta la FACT.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen, AsignacionExamen, IntentoExamen, ConsolidacionCiclo
from app.models.dimensiones import RepresentanteMedico
from app.services import examen_kpi_service, recalculo_service

INDICADOR_EXAMEN = "EVAL_CONOCIMIENTOS"


def _examenes_marcados(db: Session, ciclo_id: int):
    return db.query(Examen).filter(
        Examen.indicador_codigo == INDICADOR_EXAMEN, Examen.ciclo_id == ciclo_id).all()


def rms_del_ciclo(db: Session, ciclo_id: int, pais_codigo: str) -> list[RepresentanteMedico]:
    """RM del país con al menos un intento finalizado con score en algún examen
    marcado EVAL_CONOCIMIENTOS del ciclo."""
    examenes = _examenes_marcados(db, ciclo_id)
    if not examenes:
        return []
    ex_ids = [e.id for e in examenes]
    rm_ids = {
        r.evaluado_rm_id
        for r in db.query(IntentoExamen)
        .join(AsignacionExamen, AsignacionExamen.id == IntentoExamen.asignacion_id)
        .filter(
            AsignacionExamen.examen_id.in_(ex_ids),
            IntentoExamen.evaluado_rm_id.isnot(None),
            IntentoExamen.score.isnot(None),
        ).all()
    }
    if not rm_ids:
        return []
    return db.query(RepresentanteMedico).filter(
        RepresentanteMedico.id.in_(rm_ids),
        RepresentanteMedico.pais_codigo == pais_codigo,
    ).all()


def estado_consolidacion(db: Session, ciclo_id: int, pais_codigo: str) -> dict:
    """Preview del gate sin escribir nada."""
    fila = db.query(ConsolidacionCiclo).filter(
        ConsolidacionCiclo.ciclo_id == ciclo_id,
        ConsolidacionCiclo.pais_codigo == pais_codigo,
    ).first()
    rms = rms_del_ciclo(db, ciclo_id, pais_codigo)
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
        ciclo_abierto = True
    except recalculo_service.CicloCerradoError:
        ciclo_abierto = False
    return {
        "ciclo_id": ciclo_id,
        "pais_codigo": pais_codigo,
        "estado": fila.estado if fila else "pendiente",
        "rms_con_nota": len(rms),
        "rms_con_nota_nombres": [r.nombre for r in rms],
        "nota_promedio_equipo": (
            float(fila.nota_promedio_equipo)
            if fila and fila.nota_promedio_equipo is not None else None
        ),
        "ultima_consolidacion": (
            fila.fecha_consolidacion.isoformat()
            if fila and fila.fecha_consolidacion else None
        ),
        "ciclo_abierto": ciclo_abierto,
    }


def _upsert_estado(db, ciclo_id, pais_codigo, n, promedio, usuario_id):
    fila = db.query(ConsolidacionCiclo).filter(
        ConsolidacionCiclo.ciclo_id == ciclo_id,
        ConsolidacionCiclo.pais_codigo == pais_codigo,
    ).first()
    if fila is None:
        fila = ConsolidacionCiclo(ciclo_id=ciclo_id, pais_codigo=pais_codigo)
        db.add(fila)
    fila.estado = "consolidado"
    fila.rms_consolidados = n
    fila.nota_promedio_equipo = promedio
    fila.fecha_consolidacion = datetime.now(timezone.utc)
    fila.consolidado_por_usuario_id = usuario_id


def consolidar_ciclo(db: Session, ciclo_id: int, pais_codigo: str, usuario_id: int | None) -> dict:
    """Escribe la nota EVAL_CONOCIMIENTOS de cada RM del (ciclo, país) a la FACT y
    dispara UN recálculo. Re-ejecutable mientras el ciclo esté abierto."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Consolidación abortada: ciclo {ciclo_id} cerrado")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_consolidados": 0,
                "nota_promedio_equipo": None}

    rms = rms_del_ciclo(db, ciclo_id, pais_codigo)
    notas = []
    for rm in rms:
        nota = examen_kpi_service.upsert_nota_rm(db, rm, ciclo_id)
        if nota is not None:
            notas.append(nota)
    promedio = round(sum(notas) / len(notas), 2) if notas else None
    _upsert_estado(db, ciclo_id, pais_codigo, len(notas), promedio, usuario_id)
    db.commit()
    logger.info(f"Consolidación ciclo {ciclo_id} país {pais_codigo}: {len(notas)} RM, prom={promedio}")

    recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
    return {"abortado": False, "rms_consolidados": len(notas),
            "nota_promedio_equipo": promedio, "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}
