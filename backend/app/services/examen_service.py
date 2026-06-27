"""SCGCPR — Servicio del Módulo de Exámenes: CRUD y ciclo de vida."""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen
from app.schemas.examenes import ExamenCrear


def crear_examen(db: Session, datos: ExamenCrear, creado_por_usuario_id: int) -> Examen:
    examen = Examen(
        nombre=datos.nombre,
        producto=datos.producto,
        nota_minima=datos.nota_minima,
        tiempo_limite_min=datos.tiempo_limite_min,
        rand_preguntas=datos.rand_preguntas,
        rand_opciones=datos.rand_opciones,
        indicador_codigo=datos.indicador_codigo,
        ciclo_id=datos.ciclo_id,
        creado_por_usuario_id=creado_por_usuario_id,
        estado="borrador",
        fuente="manual",
    )
    db.add(examen)
    db.commit()
    db.refresh(examen)
    logger.info(f"Examen creado id={examen.id} '{examen.nombre}'")
    return examen


def listar_examenes(db: Session) -> list[Examen]:
    return db.query(Examen).filter(Examen.activo == True).order_by(Examen.id.desc()).all()


def obtener_examen(db: Session, examen_id: int) -> Examen | None:
    return db.query(Examen).filter(Examen.id == examen_id).first()
