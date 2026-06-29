"""SCGCPR — Servicio del Módulo de Exámenes: CRUD y ciclo de vida."""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import AsignacionExamen, Examen, Pregunta, PreguntaOpcion
from app.schemas.examenes import AsignacionCrear, EvaluadoRef, ExamenCrear, PreguntaCrear


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


def agregar_pregunta(db: Session, examen_id: int, datos: PreguntaCrear) -> Pregunta:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "borrador":
        raise ValueError("Solo se editan preguntas de un examen en borrador")  # RN-01
    n_correctas = sum(1 for o in datos.opciones if o.es_correcta)
    if n_correctas != 1:
        raise ValueError("La pregunta debe tener exactamente 1 opción correcta")
    orden = len(examen.preguntas)
    pregunta = Pregunta(
        examen_id=examen_id,
        tipo=datos.tipo,
        escenario=datos.escenario,
        texto=datos.texto,
        explicacion=datos.explicacion,
        orden=orden,
    )
    for idx, op in enumerate(datos.opciones):
        pregunta.opciones.append(
            PreguntaOpcion(
                texto_opcion=op.texto_opcion,
                indice_original=idx,
                es_correcta=op.es_correcta,
            )
        )
    db.add(pregunta)
    db.commit()
    db.refresh(pregunta)
    logger.info(f"Pregunta id={pregunta.id} agregada a examen id={examen_id}")
    return pregunta


def eliminar_pregunta(db: Session, examen_id: int, pregunta_id: int) -> None:
    pregunta = (
        db.query(Pregunta)
        .filter(Pregunta.id == pregunta_id, Pregunta.examen_id == examen_id)
        .first()
    )
    if pregunta is None:
        raise ValueError("Pregunta no encontrada")
    db.delete(pregunta)
    db.commit()
    logger.info(f"Pregunta id={pregunta_id} eliminada")


class ExamenConIntentosError(Exception):
    """El examen ya fue tomado (tiene intentos) y por regla de negocio no se borra."""


def eliminar_examen(db: Session, examen_id: int) -> None:
    """Elimina un examen SOLO si no ha sido tomado (sin intentos).

    Regla de negocio: si el examen tiene al menos un intento, se preserva
    (levanta ExamenConIntentosError → 409). Si no tiene intentos, borra en
    cascada: asignaciones, fuentes IA, y el examen (que arrastra preguntas y
    opciones vía cascade delete-orphan del modelo).
    """
    from app.models.exam_models import IntentoExamen, FuenteIA

    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if examen is None:
        raise ValueError("Examen no encontrado")

    intentos = (
        db.query(IntentoExamen)
        .join(AsignacionExamen, IntentoExamen.asignacion_id == AsignacionExamen.id)
        .filter(AsignacionExamen.examen_id == examen_id)
        .count()
    )
    if intentos > 0:
        raise ExamenConIntentosError(
            f"El examen ya fue tomado ({intentos} intento(s)); no se puede eliminar."
        )

    # Sin intentos: limpiar referencias que no cuelgan del cascade del Examen
    db.query(AsignacionExamen).filter(AsignacionExamen.examen_id == examen_id).delete(synchronize_session=False)
    db.query(FuenteIA).filter(FuenteIA.examen_id == examen_id).delete(synchronize_session=False)
    db.delete(examen)  # cascade → preguntas → opciones
    db.commit()
    logger.info(f"Examen id={examen_id} eliminado (sin intentos)")


def reordenar_preguntas(db: Session, examen_id: int, orden_ids: list[int]) -> None:
    filas = db.query(Pregunta.id).filter(Pregunta.examen_id == examen_id).all()
    ids_actuales = {fila[0] for fila in filas}
    if set(orden_ids) != ids_actuales:
        raise ValueError("orden_ids debe contener exactamente los IDs de las preguntas del examen")
    for nuevo_orden, pid in enumerate(orden_ids):
        db.query(Pregunta).filter(
            Pregunta.id == pid, Pregunta.examen_id == examen_id
        ).update({"orden": nuevo_orden})
    db.commit()
    logger.info(f"Preguntas del examen id={examen_id} reordenadas")


def asignar_examen(
    db: Session,
    examen_id: int,
    evaluados: list[EvaluadoRef],
    fecha_limite,
    intentos_max,
    notif_activa: bool,
) -> list[AsignacionExamen]:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "activo":
        raise ValueError("Solo se asigna un examen activo (publicado)")
    creadas = []
    for ev in evaluados:
        if ev.tipo not in ("RM", "GERENTE"):
            raise ValueError(f"Tipo de evaluado inválido: {ev.tipo}")
        asig = AsignacionExamen(
            examen_id=examen_id,
            evaluado_tipo=ev.tipo,
            evaluado_rm_id=ev.id if ev.tipo == "RM" else None,
            evaluado_gerente_id=ev.id if ev.tipo == "GERENTE" else None,
            fecha_limite=fecha_limite,
            intentos_max=intentos_max,
            intentos_usados=0,
            estado="pendiente",
            notif_activa=notif_activa,
        )
        db.add(asig)
        creadas.append(asig)
    db.commit()
    for a in creadas:
        db.refresh(a)
    logger.info(f"Examen id={examen_id} asignado a {len(creadas)} evaluado(s)")
    return creadas


def publicar_examen(db: Session, examen_id: int) -> Examen:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "borrador":
        raise ValueError(f"Solo se publica un examen en borrador (estado actual: {examen.estado})")
    if not examen.preguntas:  # RN-02
        raise ValueError("El examen debe tener al menos 1 pregunta para publicarse")
    examen.estado = "activo"
    examen.fecha_publicacion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(examen)
    logger.info(f"Examen id={examen.id} publicado")
    return examen
