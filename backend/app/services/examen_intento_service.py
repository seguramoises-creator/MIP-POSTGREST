"""SCGCPR — Servicio de intentos de examen: aleatorización, corrección, reporte."""
import json
import random
from datetime import datetime, timedelta, timezone

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

    if asignacion.fecha_limite is not None:
        # fecha_limite se persiste como DateTime (naive en SQL Server) y representa
        # una FECHA DE CALENDARIO LOCAL (la que eligió quien asignó). Se compara
        # contra la fecha local — no UTC — porque en husos negativos (ej. GMT-4) la
        # fecha UTC ya es del día siguiente al final de la tarde y haría "vencer" la
        # asignación un día antes. El plazo es inclusivo de todo el día límite.
        limite = asignacion.fecha_limite
        limite_date = limite.date() if isinstance(limite, datetime) else limite
        if datetime.now().date() > limite_date:
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
    mapa_presentacion: dict = {}  # { str(pregunta_id): { str(indice_pres): {opcion_id, indice_original} } }
    for p in preguntas:
        ops = list(p.opciones)
        if examen.rand_opciones:
            barajar(ops, rng)
        opciones_con_mapa = [
            {
                "indice_presentado": i,
                "texto_opcion": o.texto_opcion,
                "_opcion_id": o.id,
                "_indice_original": o.indice_original,
            }
            for i, o in enumerate(ops)
        ]
        presentadas.append({
            "pregunta_id": p.id,
            "tipo": p.tipo,
            "escenario": p.escenario,
            "texto": p.texto,
            "opciones": opciones_con_mapa,
        })
        mapa_presentacion[str(p.id)] = {
            str(op["indice_presentado"]): {
                "opcion_id": op["_opcion_id"],
                "indice_original": op["_indice_original"],
            }
            for op in opciones_con_mapa
        }

    # Persist the shuffle map so responder can reconstruct opcion_id from indice_presentado
    intento.mapa_presentacion_json = json.dumps(mapa_presentacion)
    db.commit()

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
    """Persiste una respuesta del evaluado para una pregunta del intento.

    Idempotente: si ya existe una respuesta para (intento_id, pregunta_id),
    la elimina antes de insertar la nueva. Última respuesta gana.
    """
    db.query(IntentoRespuesta).filter(
        IntentoRespuesta.intento_id == intento_id,
        IntentoRespuesta.pregunta_id == pregunta_id,
    ).delete()
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


def validar_intento_vigente(db: Session, intento) -> None:
    """Levanta ValueError si el intento ya no puede recibir respuestas por vencimiento.

    Comprueba dos condiciones independientes:
    1. La asignación tiene fecha_limite y ya expiró (comparación datetime UTC-aware).
    2. El examen tiene tiempo_limite_min y el tiempo desde fecha_inicio fue superado.

    Ambas fechas almacenadas se tratan como UTC si son naive (sin tzinfo), igual que
    el resto del proyecto (datetime.now(timezone.utc), nunca utcnow()).
    """
    asignacion = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id
    ).first()
    if asignacion is None:
        raise ValueError("Asignación del intento no encontrada")

    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    if examen is None:
        raise ValueError("Examen del intento no encontrado")

    ahora = datetime.now(timezone.utc)

    if asignacion.fecha_limite is not None:
        fl = asignacion.fecha_limite
        # Tratar naive como UTC (consistente con el resto del proyecto)
        if fl.tzinfo is None:
            fl = fl.replace(tzinfo=timezone.utc)
        if ahora > fl:
            raise ValueError("La asignación está vencida")

    if examen.tiempo_limite_min is not None and intento.fecha_inicio is not None:
        fi = intento.fecha_inicio
        if fi.tzinfo is None:
            fi = fi.replace(tzinfo=timezone.utc)
        if ahora > fi + timedelta(minutes=examen.tiempo_limite_min):
            raise ValueError("Se agotó el tiempo del examen")


def registrar_respuesta_presentada(
    db: Session,
    intento_id: int,
    pregunta_id: int,
    indice_presentado: int,
) -> IntentoRespuesta:
    """Fachada pública: reconstruye el mapeo presentado→original y persiste la respuesta.

    El router solo debe llamar a esta función — nunca a `_reconstruir_mapa_opcion`
    directamente. El mapeo y la lógica de traducción quedan encapsulados aquí.
    """
    # _reconstruir_mapa_opcion also loads the intento; we need it first for the guard.
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    validar_intento_vigente(db, intento)

    opcion_id, indice_pres, indice_orig = _reconstruir_mapa_opcion(
        db, intento_id, pregunta_id, indice_presentado
    )
    mapa = {str(indice_pres): {"opcion_id": opcion_id, "indice_original": indice_orig}}
    return registrar_respuesta(
        db,
        intento_id=intento_id,
        pregunta_id=pregunta_id,
        opcion_id=opcion_id,
        indice_presentado=indice_pres,
        indice_original=indice_orig,
        mapa=mapa,
    )


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
    preguntas = db.query(Pregunta).filter(
        Pregunta.examen_id == examen.id,
        Pregunta.activo == True,
    ).all()
    total = len(preguntas)
    # Peso efectivo (base 100): el peso manual de la pregunta, o el reparto igual
    # 100÷N cuando no se asignó peso. Si todos son NULL, equivale al % de correctas.
    peso_igual = (100.0 / total) if total else 0.0
    peso_map = {q.id: (float(q.peso) if q.peso is not None else peso_igual) for q in preguntas}

    # Corregir cada respuesta (RN-05) y sumar el peso de las correctas. Las
    # preguntas abiertas/caso-abierto (respuesta de texto) quedan pendientes de
    # calificación manual: no se autocalifican y no suman hasta que el Gerente
    # les asigne puntos.
    correctas = 0
    puntos = 0.0
    pendiente = False
    for r in respuestas:
        if r.opcion_elegida_id is None and r.respuesta_texto is not None:
            if r.puntos is None:
                pendiente = True
            else:
                puntos += float(r.puntos)
            continue
        opcion = db.query(PreguntaOpcion).filter(
            PreguntaOpcion.id == r.opcion_elegida_id
        ).first()
        r.es_correcta = bool(opcion and opcion.es_correcta)
        r.puntos = peso_map.get(r.pregunta_id, peso_igual) if r.es_correcta else 0
        if r.es_correcta:
            correctas += 1
            puntos += float(r.puntos)

    intento.score = round(min(puntos, 100.0), 2)
    intento.aprobado = (not pendiente) and intento.score >= examen.nota_minima
    intento.fecha_fin = datetime.now(timezone.utc)

    if intento.fecha_inicio is not None:
        # fecha_inicio viene de SQL Server como naive; normalizar a UTC aware
        # antes de restar (fecha_fin es aware) para evitar TypeError.
        ini = intento.fecha_inicio
        if ini.tzinfo is None:
            ini = ini.replace(tzinfo=timezone.utc)
        intento.tiempo_usado_seg = int((intento.fecha_fin - ini).total_seconds())

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
        f"aprobado={intento.aprobado} correctas={correctas}/{total} pendiente={pendiente}"
    )

    # Si quedan preguntas abiertas sin calificar, el resultado es provisional: el
    # puente al indicador y el correo se disparan al completar la calificación.
    if not pendiente:
        _finalizar_resultado(db, intento, examen, asignacion, correctas, total)

    return intento


def _finalizar_resultado(db, intento, examen, asignacion, correctas: int, total: int) -> None:
    """Dispara el puente EVAL_CONOCIMIENTOS y el correo de resultado. Solo se invoca
    cuando el resultado es definitivo (sin preguntas abiertas pendientes). Ningún
    fallo aquí debe romper la entrega/calificación."""
    try:
        from app.services import examen_kpi_service
        examen_kpi_service.alimentar_eval_conocimientos(db, intento)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Puente EVAL_CONOCIMIENTOS falló (no bloquea): {e}")
    if asignacion is not None and getattr(asignacion, "notif_activa", False):
        try:
            _notificar_resultado_examen(db, intento, examen, correctas, total)
        except Exception as e:  # noqa: BLE001
            logger.error(f"Correo de resultado falló (no bloquea): {e}")


def registrar_respuesta_abierta(db: Session, intento_id: int, pregunta_id: int, texto: str) -> IntentoRespuesta:
    """Persiste la respuesta de texto libre de una pregunta abierta / caso-abierto.

    Idempotente (última respuesta gana). Queda pendiente de calificación manual
    (`puntos=None`) hasta que el Gerente le asigne puntos.
    """
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    validar_intento_vigente(db, intento)
    db.query(IntentoRespuesta).filter(
        IntentoRespuesta.intento_id == intento_id,
        IntentoRespuesta.pregunta_id == pregunta_id,
    ).delete()
    resp = IntentoRespuesta(
        intento_id=intento_id,
        pregunta_id=pregunta_id,
        respuesta_texto=(texto or "").strip(),
        fecha_respuesta=datetime.now(timezone.utc),
    )
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


def calificar_respuesta(db: Session, intento_id: int, respuesta_id: int, puntos: float) -> IntentoExamen:
    """El Gerente asigna puntos a una respuesta abierta (0..peso de la pregunta).

    Recalcula el score del intento; si ya no quedan abiertas pendientes, finaliza
    (puente EVAL_CONOCIMIENTOS + correo). Devuelve el intento actualizado.
    """
    if puntos is None or puntos < 0:
        raise ValueError("Los puntos deben ser un número >= 0")
    resp = db.query(IntentoRespuesta).filter(
        IntentoRespuesta.id == respuesta_id,
        IntentoRespuesta.intento_id == intento_id,
    ).first()
    if resp is None:
        raise ValueError("Respuesta no encontrada para este intento")

    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    asignacion = db.query(AsignacionExamen).filter(AsignacionExamen.id == intento.asignacion_id).first()
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()

    preguntas = db.query(Pregunta).filter(
        Pregunta.examen_id == examen.id, Pregunta.activo == True,
    ).all()
    total = len(preguntas)
    peso_igual = (100.0 / total) if total else 0.0
    peso_map = {q.id: (float(q.peso) if q.peso is not None else peso_igual) for q in preguntas}

    # Acota los puntos al peso de la pregunta (no se puede otorgar más que su peso).
    tope = peso_map.get(resp.pregunta_id, peso_igual)
    resp.puntos = round(min(float(puntos), tope), 2)
    db.flush()

    # Recalcular el score del intento con todas las respuestas.
    respuestas = db.query(IntentoRespuesta).filter(IntentoRespuesta.intento_id == intento_id).all()
    total_puntos = 0.0
    pendiente = False
    correctas = 0
    for r in respuestas:
        if r.opcion_elegida_id is None and r.respuesta_texto is not None:
            if r.puntos is None:
                pendiente = True
            else:
                total_puntos += float(r.puntos)
        elif r.es_correcta:
            correctas += 1
            total_puntos += float(r.puntos or 0)

    intento.score = round(min(total_puntos, 100.0), 2)
    intento.aprobado = (not pendiente) and intento.score >= examen.nota_minima
    if intento.aprobado and asignacion.estado != "completado":
        asignacion.estado = "completado"
    db.commit()
    db.refresh(intento)
    logger.info(f"Respuesta {respuesta_id} calificada — intento {intento_id} score={intento.score} pendiente={pendiente}")

    if not pendiente:
        _finalizar_resultado(db, intento, examen, asignacion, correctas, total)
    return intento


def _notificar_resultado_examen(db, intento, examen, correctas: int, total: int) -> None:
    """Resuelve el email del evaluado (vía su usuario) y envía el correo de resultado."""
    from app.models.usuario import Usuario
    from app.services import notification_service

    q = db.query(Usuario)
    if intento.evaluado_tipo == "RM":
        usuario = q.filter(Usuario.rm_id == intento.evaluado_rm_id).first()
    else:
        usuario = q.filter(Usuario.gerente_id == intento.evaluado_gerente_id).first()
    if usuario is None or not usuario.email:
        return
    notification_service.notificar_resultado_examen(
        destinatario=usuario.email,
        nombre_visitador=usuario.nombre_completo or usuario.username,
        examen_nombre=examen.nombre,
        producto=examen.producto,
        score=float(intento.score) if intento.score is not None else 0,
        aprobado=bool(intento.aprobado),
        correctas=correctas,
        total=total,
        fecha_fin=str(intento.fecha_fin) if intento.fecha_fin else None,
    )


# ---------------------------------------------------------------------------
# Reporte post-entrega, pendientes, historial e iniciar (Task 7)
# ---------------------------------------------------------------------------

def generar_reporte(db: Session, intento_id: int) -> dict:
    """Genera el reporte completo de un intento ya entregado (RN-07: siempre feedback).

    Incluye por cada respuesta: texto de la pregunta, explicación, opción elegida,
    opción correcta y si acertó. La opción correcta SOLO se expone aquí, no en iniciar.
    """
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    if intento.fecha_fin is None:
        raise ValueError("El intento aún no ha sido entregado")

    asignacion = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id
    ).first()
    if asignacion is None:
        raise ValueError("Asignación del intento no encontrada")

    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    if examen is None:
        raise ValueError("Examen del intento no encontrado")

    respuestas = list(
        db.query(IntentoRespuesta)
        .filter(IntentoRespuesta.intento_id == intento_id)
        .all()
    )
    total = db.query(Pregunta).filter(
        Pregunta.examen_id == examen.id,
        Pregunta.activo == True,
    ).count()

    detalle = []
    correctas = 0
    for r in respuestas:
        pregunta = db.query(Pregunta).filter(Pregunta.id == r.pregunta_id).first()
        elegida = (
            db.query(PreguntaOpcion).filter(PreguntaOpcion.id == r.opcion_elegida_id).first()
            if r.opcion_elegida_id
            else None
        )
        correcta = db.query(PreguntaOpcion).filter(
            PreguntaOpcion.pregunta_id == r.pregunta_id,
            PreguntaOpcion.es_correcta == True,
        ).first()
        if r.es_correcta:
            correctas += 1
        detalle.append({
            "pregunta_texto": pregunta.texto if pregunta else "",
            "explicacion": pregunta.explicacion if pregunta else None,
            "indice_elegido_presentado": r.indice_opcion_presentada,
            "texto_elegido": elegida.texto_opcion if elegida else None,
            "texto_correcto": correcta.texto_opcion if correcta else "",
            "es_correcta": bool(r.es_correcta),
        })

    return {
        "intento_id": intento.id,
        "examen_nombre": examen.nombre,
        "producto": examen.producto,
        "score": float(intento.score or 0),
        "aprobado": bool(intento.aprobado),
        "nota_minima": examen.nota_minima,
        "correctas": correctas,
        "total": total,
        "fecha_fin": intento.fecha_fin,
        "respuestas": detalle,
    }


def listar_pendientes(db: Session, evaluado_tipo: str, evaluado_id: int) -> list:
    """Devuelve las asignaciones en estado 'pendiente' para el evaluado dado."""
    q = db.query(AsignacionExamen).filter(AsignacionExamen.estado == "pendiente")
    if evaluado_tipo == "RM":
        q = q.filter(
            AsignacionExamen.evaluado_tipo == "RM",
            AsignacionExamen.evaluado_rm_id == evaluado_id,
        )
    else:  # GERENTE
        q = q.filter(
            AsignacionExamen.evaluado_tipo == "GERENTE",
            AsignacionExamen.evaluado_gerente_id == evaluado_id,
        )
    return q.all()


def listar_historial(db: Session, evaluado_tipo: str, evaluado_id: int) -> list:
    """Devuelve todos los intentos (en cualquier estado) del evaluado, del más reciente al más antiguo."""
    q = db.query(IntentoExamen)
    if evaluado_tipo == "RM":
        q = q.filter(
            IntentoExamen.evaluado_tipo == "RM",
            IntentoExamen.evaluado_rm_id == evaluado_id,
        )
    else:  # GERENTE
        q = q.filter(
            IntentoExamen.evaluado_tipo == "GERENTE",
            IntentoExamen.evaluado_gerente_id == evaluado_id,
        )
    return q.order_by(IntentoExamen.fecha_inicio.desc()).all()


def iniciar_para_evaluado(
    db: Session,
    examen_id: int,
    evaluado_tipo: str,
    evaluado_id: int,
    contexto: dict,
) -> dict:
    """Localiza la asignación pendiente del evaluado para el examen, crea el intento
    y construye el payload IntentoIniciado SIN exponer la opción correcta.

    Scope enforcement: 403 si no existe una asignación pendiente para este evaluado
    exacto en este examen.
    """
    # Buscar asignación pendiente que pertenezca a este evaluado
    q = db.query(AsignacionExamen).filter(
        AsignacionExamen.examen_id == examen_id,
        AsignacionExamen.estado == "pendiente",
    )
    if evaluado_tipo == "RM":
        q = q.filter(
            AsignacionExamen.evaluado_tipo == "RM",
            AsignacionExamen.evaluado_rm_id == evaluado_id,
        )
    else:
        q = q.filter(
            AsignacionExamen.evaluado_tipo == "GERENTE",
            AsignacionExamen.evaluado_gerente_id == evaluado_id,
        )
    asignacion = q.first()
    if asignacion is None:
        raise PermissionError("Sin asignación pendiente para este evaluado en el examen indicado")

    # preparar_intento levanta ValueError si la asignación no es tomable (RN-06, RN-01)
    intento = preparar_intento(db, asignacion, evaluado_tipo, evaluado_id, contexto)

    # Obtener el examen para el nombre y tiempo_limite_min
    examen = db.query(Examen).filter(Examen.id == examen_id).first()

    # Construir payload público: opciones sin _opcion_id ni _indice_original (no-leak)
    preguntas_publicas = []
    for p in intento._preguntas_presentadas:
        opciones_publicas = [
            {
                "indice_presentado": op["indice_presentado"],
                "texto_opcion": op["texto_opcion"],
            }
            for op in p["opciones"]
        ]
        preguntas_publicas.append({
            "pregunta_id": p["pregunta_id"],
            "tipo": p["tipo"],
            "escenario": p["escenario"],
            "texto": p["texto"],
            "opciones": opciones_publicas,
        })

    return {
        "intento_id": intento.id,
        "examen_nombre": examen.nombre if examen else "",
        "tiempo_limite_min": examen.tiempo_limite_min if examen else None,
        "preguntas": preguntas_publicas,
    }


def _reconstruir_mapa_opcion(db: Session, intento_id: int, pregunta_id: int, indice_presentado: int):
    """Reconstruye indice_presentado → (opcion_id, indice_original) desde el mapa persistido en el intento.

    El mapa se persiste en IntentoExamen.mapa_presentacion_json durante preparar_intento,
    lo que garantiza que la traducción sea correcta incluso si rand_opciones=True barajó
    las opciones de una forma no repetible.

    Fallback: si el mapa no existe (intentos creados antes de esta columna), busca por
    indice_original == indice_presentado (equivalente a sin-barajado).

    Retorna (opcion_id, indice_presentado, indice_original).
    """
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")

    if intento.mapa_presentacion_json:
        mapa = json.loads(intento.mapa_presentacion_json)
        pregunta_mapa = mapa.get(str(pregunta_id), {})
        entrada = pregunta_mapa.get(str(indice_presentado))
        if entrada:
            return entrada["opcion_id"], indice_presentado, entrada["indice_original"]

    # Fallback: sin rand_opciones → indice_presentado == indice_original
    opcion = db.query(PreguntaOpcion).filter(
        PreguntaOpcion.pregunta_id == pregunta_id,
        PreguntaOpcion.indice_original == indice_presentado,
    ).first()
    if opcion is None:
        raise ValueError(f"Índice presentado {indice_presentado} no válido para pregunta {pregunta_id}")
    return opcion.id, indice_presentado, opcion.indice_original
