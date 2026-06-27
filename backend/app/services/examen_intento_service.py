"""SCGCPR — Servicio de intentos de examen: aleatorización, corrección, reporte."""
import json
import random
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import (
    AsignacionExamen,
    Examen,
    IntentoExamen,
    IntentoRespuesta,
    Pregunta,
    PreguntaOpcion,
)


def barajar(items: list, rng: random.Random) -> list:
    """Fisher-Yates in-place; retorna la misma lista barajada."""
    for i in range(len(items) - 1, 0, -1):
        j = rng.randint(0, i)
        items[i], items[j] = items[j], items[i]
    return items


def preparar_intento(db: Session, asignacion, evaluado_tipo, evaluado_id, contexto, rng=None):
    """Valida que la asignación es tomable, baraja preguntas/opciones según flags
    del examen, persiste el IntentoExamen y adjunta `_preguntas_presentadas`
    como atributo transitorio para el router.

    RN-06: bloquea si estado != pendiente o si intentos_usados >= intentos_max.
    RN-01: bloquea si el examen no está en estado 'activo'.
    """
    # --- RN-06: estado de la asignación ---
    if asignacion.estado not in ("pendiente",):
        raise ValueError("La asignación no está disponible para un nuevo intento")

    if asignacion.intentos_max is not None and asignacion.intentos_usados >= asignacion.intentos_max:
        raise ValueError("Se agotaron los intentos permitidos")

    if asignacion.fecha_limite is not None and datetime.now(timezone.utc).date() > asignacion.fecha_limite:
        raise ValueError("La asignación está vencida")

    rng = rng or random.Random()

    # --- RN-01: examen activo ---
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    if examen is None or examen.estado != "activo":
        raise ValueError("El examen no está disponible")

    # --- Obtener preguntas activas ordenadas ---
    preguntas = list(
        db.query(Pregunta)
        .filter(Pregunta.examen_id == examen.id, Pregunta.activo == True)
        .order_by(Pregunta.orden)
        .all()
    )

    if examen.rand_preguntas:
        barajar(preguntas, rng)

    orden_ids = [p.id for p in preguntas]

    # --- Crear y persistir el intento ---
    intento = IntentoExamen(
        asignacion_id=asignacion.id,
        evaluado_tipo=evaluado_tipo,
        evaluado_rm_id=evaluado_id if evaluado_tipo == "RM" else None,
        evaluado_gerente_id=evaluado_id if evaluado_tipo == "GERENTE" else None,
        fecha_inicio=datetime.now(timezone.utc),
        orden_preguntas_json=json.dumps(orden_ids),
        user_agent=contexto.get("user_agent"),
        device_type=contexto.get("device_type"),
        plataforma=contexto.get("plataforma"),
        ip_cliente=contexto.get("ip_cliente"),
    )
    db.add(intento)
    db.commit()
    db.refresh(intento)

    logger.info(
        f"Intento {intento.id} creado para asignacion {asignacion.id} "
        f"({evaluado_tipo} id={evaluado_id})"
    )

    # --- Construir estructura presentada (opciones barajadas si aplica) ---
    # _opcion_id y _indice_original son internos: el router los usa para el mapa
    # de respuestas pero NO deben exponerse al evaluado en la respuesta pública.
    presentadas = []
    for p in preguntas:
        ops = list(p.opciones)
        if examen.rand_opciones:
            barajar(ops, rng)
        presentadas.append({
            "pregunta_id": p.id,
            "tipo": p.tipo,
            "escenario": p.escenario,
            "texto": p.texto,
            "opciones": [
                {
                    "indice_presentado": i,
                    "texto_opcion": o.texto_opcion,
                    "_opcion_id": o.id,
                    "_indice_original": o.indice_original,
                }
                for i, o in enumerate(ops)
            ],
        })

    intento._preguntas_presentadas = presentadas  # transitorio para el router
    return intento


# ---------------------------------------------------------------------------
# Responder, calcular score y entregar (Task 6)
# ---------------------------------------------------------------------------

def calcular_score(correctas: int, total: int) -> float:
    """Porcentaje de respuestas correctas, redondeado a 2 decimales."""
    if total <= 0:
        return 0.0
    return round(correctas / total * 100, 2)


def registrar_respuesta(
    db: Session,
    intento_id: int,
    pregunta_id: int,
    opcion_id: int | None,
    indice_presentado: int | None,
    indice_original: int | None,
    mapa: dict,
) -> IntentoRespuesta:
    """Persiste una respuesta del evaluado para una pregunta del intento."""
    resp = IntentoRespuesta(
        intento_id=intento_id,
        pregunta_id=pregunta_id,
        opcion_elegida_id=opcion_id,
        indice_opcion_presentada=indice_presentado,
        indice_original_elegido=indice_original,
        mapa_opciones_json=json.dumps(mapa),
        fecha_respuesta=datetime.now(timezone.utc),
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


def entregar_intento(db: Session, intento_id: int) -> IntentoExamen:
    """Cierra el intento: corrige respuestas, calcula score/aprobado y aplica RN-06.

    RN-05: la corrección usa la opción original (es_correcta en DimPreguntaOpcion),
           no el índice presentado — el barajado no afecta la clave de corrección.
    RN-06: cierra la asignación (estado='completado') si el evaluado aprueba
           o agota todos sus intentos disponibles.
    Anti-doble-entrega: lanza ValueError si fecha_fin ya está establecida.
    """
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    if intento.fecha_fin is not None:
        raise ValueError("El intento ya fue entregado")  # anti-doble-entrega

    asignacion = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id
    ).first()
    if asignacion is None:
        raise ValueError("Asignación del intento no encontrada")
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    if examen is None:
        raise ValueError("Examen del intento no encontrado")

    respuestas = list(
        db.query(IntentoRespuesta).filter(IntentoRespuesta.intento_id == intento_id).all()
    )
    total = db.query(Pregunta).filter(
        Pregunta.examen_id == examen.id,
        Pregunta.activo == True,
    ).count()

    # Corregir cada respuesta consultando la opción original (RN-05)
    correctas = 0
    for r in respuestas:
        opcion = db.query(PreguntaOpcion).filter(
            PreguntaOpcion.id == r.opcion_elegida_id
        ).first()
        r.es_correcta = bool(opcion and opcion.es_correcta)
        if r.es_correcta:
            correctas += 1

    intento.score = calcular_score(correctas, total)
    intento.aprobado = intento.score >= examen.nota_minima
    intento.fecha_fin = datetime.now(timezone.utc)

    if intento.fecha_inicio is not None:
        intento.tiempo_usado_seg = int(
            (intento.fecha_fin - intento.fecha_inicio).total_seconds()
        )

    asignacion.intentos_usados += 1

    # RN-06: cerrar asignación si aprobó o agotó intentos disponibles
    if intento.aprobado or (
        asignacion.intentos_max is not None
        and asignacion.intentos_usados >= asignacion.intentos_max
    ):
        asignacion.estado = "completado"

    db.commit()
    db.refresh(intento)

    logger.info(
        f"Intento {intento_id} entregado — score={intento.score} "
        f"aprobado={intento.aprobado} correctas={correctas}/{total}"
    )
    return intento
