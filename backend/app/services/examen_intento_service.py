"""SCGCPR — Servicio de intentos de examen: aleatorización, corrección, reporte."""
import json
import random
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import (
    Examen,
    Pregunta,
    IntentoExamen,
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
