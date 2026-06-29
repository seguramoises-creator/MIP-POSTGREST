"""SCGCPR — KPIs y resultados del Módulo de Exámenes (capacitación / GD).

KPIs (spec §9): promedio del equipo, % aprobación, completitud, score individual
(último intento), ranking (último intento, RN-09), % error por pregunta (sobre
todos los intentos, RN-08).
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import (
    Examen, Pregunta, AsignacionExamen, IntentoExamen, IntentoRespuesta,
)


def _ultimo_intento_por_asignacion(db: Session, examen_id: int) -> dict[int, IntentoExamen]:
    """Mapea asignacion_id → último IntentoExamen entregado (por fecha_fin)."""
    intentos = (
        db.query(IntentoExamen)
        .join(AsignacionExamen, AsignacionExamen.id == IntentoExamen.asignacion_id)
        .filter(AsignacionExamen.examen_id == examen_id,
                IntentoExamen.fecha_fin.isnot(None))
        .order_by(IntentoExamen.fecha_fin.asc())
        .all()
    )
    # como van ascendentes por fecha_fin, el último que se asigna es el más reciente
    ultimo: dict[int, IntentoExamen] = {}
    for it in intentos:
        ultimo[it.asignacion_id] = it
    return ultimo


def _porcentaje(parte: int, total: int) -> float:
    return round(parte / total * 100, 2) if total else 0.0


def resumen_examen(db: Session, examen_id: int) -> dict:
    """Resultados consolidados de un examen: completitud, promedio, %aprobación, ranking."""
    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if examen is None:
        raise ValueError("Examen no encontrado")

    asignaciones = db.query(AsignacionExamen).filter(
        AsignacionExamen.examen_id == examen_id).all()
    total_asignados = len(asignaciones)
    completados = sum(1 for a in asignaciones if a.estado == "completado")

    ultimos = _ultimo_intento_por_asignacion(db, examen_id)
    scores = [float(it.score) for it in ultimos.values() if it.score is not None]
    aprobados = sum(1 for it in ultimos.values() if it.aprobado)
    promedio = round(sum(scores) / len(scores), 2) if scores else 0.0

    # Nombres de evaluados resueltos en lote (evita N+1)
    from app.models.dimensiones import RepresentanteMedico, Gerente
    rm_ids = {a.evaluado_rm_id for a in asignaciones if a.evaluado_rm_id}
    ger_ids = {a.evaluado_gerente_id for a in asignaciones if a.evaluado_gerente_id}
    rm_nombres = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
                      .filter(RepresentanteMedico.id.in_(rm_ids)).all()) if rm_ids else {}
    ger_nombres = dict(db.query(Gerente.id, Gerente.nombre)
                       .filter(Gerente.id.in_(ger_ids)).all()) if ger_ids else {}

    def _nombre(a):
        if a.evaluado_tipo == "RM":
            return rm_nombres.get(a.evaluado_rm_id) or f"RM #{a.evaluado_rm_id}"
        return ger_nombres.get(a.evaluado_gerente_id) or f"Gerente #{a.evaluado_gerente_id}"

    # Ranking por último score desc (RN-09)
    ranking = []
    for asig in asignaciones:
        it = ultimos.get(asig.id)
        ranking.append({
            "evaluado_tipo": asig.evaluado_tipo,
            "evaluado_rm_id": asig.evaluado_rm_id,
            "evaluado_gerente_id": asig.evaluado_gerente_id,
            "evaluado_nombre": _nombre(asig),
            "fecha_limite": asig.fecha_limite.isoformat() if asig.fecha_limite else None,
            "ultimo_score": float(it.score) if it and it.score is not None else None,
            "aprobado": bool(it.aprobado) if it else False,
            "intentos_usados": asig.intentos_usados,
            "estado": asig.estado,
        })
    ranking.sort(key=lambda r: (r["ultimo_score"] is None, -(r["ultimo_score"] or 0)))

    return {
        "examen_id": examen.id,
        "nombre": examen.nombre,
        "producto": examen.producto,
        "estado": examen.estado,
        "nota_minima": examen.nota_minima,
        "asignados": total_asignados,
        "completados": completados,
        "completitud_pct": _porcentaje(completados, total_asignados),
        "promedio_score": promedio,
        "aprobacion_pct": _porcentaje(aprobados, len(ultimos)),
        "ranking": ranking,
    }


def analisis_preguntas(db: Session, examen_id: int) -> list[dict]:
    """% de error por pregunta sobre TODOS los intentos del examen (RN-08)."""
    preguntas = db.query(Pregunta).filter(
        Pregunta.examen_id == examen_id, Pregunta.activo == True).order_by(Pregunta.orden).all()
    salida = []
    for p in preguntas:
        respuestas = db.query(IntentoRespuesta).filter(
            IntentoRespuesta.pregunta_id == p.id).all()
        total = len(respuestas)
        incorrectas = sum(1 for r in respuestas if r.es_correcta is False)
        salida.append({
            "pregunta_id": p.id,
            "texto": p.texto,
            "orden": p.orden,
            "total_respuestas": total,
            "incorrectas": incorrectas,
            "error_pct": _porcentaje(incorrectas, total),
        })
    return salida


def resumen_equipo(db: Session, gerente_id: int) -> list[dict]:
    """Resultados de exámenes del equipo de un GD: cada RM (cuyo DIM_RM.gerente_id
    coincide) con sus exámenes asignados, último score, aprobación y promedio."""
    from app.models.dimensiones import RepresentanteMedico

    rms = db.query(RepresentanteMedico).filter(
        RepresentanteMedico.gerente_id == gerente_id).all()
    salida = []
    for rm in rms:
        asigns = db.query(AsignacionExamen).filter(
            AsignacionExamen.evaluado_tipo == "RM",
            AsignacionExamen.evaluado_rm_id == rm.id,
        ).all()
        examenes_rm = []
        scores = []
        for a in asigns:
            ex = db.query(Examen).filter(Examen.id == a.examen_id).first()
            ultimo = (
                db.query(IntentoExamen)
                .filter(IntentoExamen.asignacion_id == a.id, IntentoExamen.fecha_fin.isnot(None))
                .order_by(IntentoExamen.fecha_fin.desc())
                .first()
            )
            sc = float(ultimo.score) if ultimo and ultimo.score is not None else None
            if sc is not None:
                scores.append(sc)
            examenes_rm.append({
                "examen_id": a.examen_id,
                "examen_nombre": ex.nombre if ex else f"#{a.examen_id}",
                "ultimo_score": sc,
                "aprobado": bool(ultimo.aprobado) if ultimo else False,
                "estado": a.estado,
            })
        salida.append({
            "rm_id": rm.id,
            "nombre": rm.nombre,
            "asignados": len(asigns),
            "completados": sum(1 for e in examenes_rm if e["estado"] == "completado"),
            "promedio": round(sum(scores) / len(scores), 2) if scores else None,
            "examenes": examenes_rm,
        })
    return salida


def resumen_capacitacion(db: Session) -> list[dict]:
    """Tabla de exámenes con sus KPIs principales (dashboard de capacitación)."""
    examenes = db.query(Examen).filter(Examen.activo == True).order_by(Examen.id.desc()).all()
    filas = []
    for ex in examenes:
        r = resumen_examen(db, ex.id)
        filas.append({
            "examen_id": ex.id, "nombre": ex.nombre, "producto": ex.producto,
            "estado": ex.estado, "asignados": r["asignados"], "completados": r["completados"],
            "completitud_pct": r["completitud_pct"], "promedio_score": r["promedio_score"],
            "aprobacion_pct": r["aprobacion_pct"],
        })
    return filas
