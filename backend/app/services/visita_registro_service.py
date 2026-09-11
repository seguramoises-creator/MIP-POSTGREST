"""Registro de Visita (Parte 4 del spec). Usa la hora del SERVIDOR (no del cliente)
para evitar manipulación; ventana de 60 min; comentario obligatorio y no genérico
(validado en el schema); registro de no-visita con causa.

DOS RELOJES, Y NO SON EL MISMO. Lo que se GUARDA es UTC (el instante, sin ambigüedad);
lo que se PREGUNTA —«¿qué hizo hoy este visitador?»— es el día LOCAL de su país. Confundir
uno con otro no da error, da un número creíble: medido el 2026-09-09 a las 23:49 hora de
RD, la visita recién registrada no aparecía en el día porque para UTC ya era el día 10.
El día local se resuelve con `app/core/tiempo.py`, que lee `DIM_Pais.zona_horaria`.
"""
from datetime import datetime, timezone, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.core.tiempo import hoy_local, ventana_dia_local, zona_horaria
from app.models.visita import MedicoVisita, VisitaRegistro
from app.schemas.visita import VisitaRegistrar, VisitaNoVisita
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services import recalculo_service


def _pais_del_vm(db: Session, vm_id: int) -> str | None:
    from app.models.dimensiones import RepresentanteMedico
    return db.query(RepresentanteMedico.pais_codigo).filter(
        RepresentanteMedico.id == vm_id).scalar()


def _ahora_utc() -> datetime:
    """El instante actual tal y como se guarda: UTC y sin huso.

    Sin el `replace` sería un valor consciente, y al entrar en una columna
    `TIMESTAMP WITHOUT TIME ZONE` PostgreSQL lo pasaría a la zona de la sesión: lo
    guardado dependería de la máquina y no del código (ver `app/db/database.py`)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _a_local(db: Session, pais_codigo: str | None, dt: datetime | None):
    """Un `fecha_hora` guardado (UTC sin huso) visto en la zona del país."""
    if dt is None:
        return None
    return dt.replace(tzinfo=timezone.utc).astimezone(zona_horaria(db, pais_codigo))


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


def _guard_ventana_ciclo(db, ciclo_id, fecha):
    """Control de calidad temporal: la fecha de la visita debe caer dentro de la ventana
    [fecha_inicio, fecha_fin] del ciclo. Evita registrar visitas sobre un ciclo cuya
    ventana ya venció (ciclo 'zombi'), que ensuciaría cobertura/ritmo."""
    from datetime import date as _date
    from app.models.dimensiones import Ciclo
    c = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    if (c is not None and isinstance(getattr(c, "fecha_inicio", None), _date)
            and isinstance(getattr(c, "fecha_fin", None), _date)
            and not (c.fecha_inicio <= fecha <= c.fecha_fin)):
        raise ValueError(
            f"Hoy ({fecha}) está fuera de la ventana del ciclo vigente "
            f"'{c.nombre}' ({c.fecha_inicio} a {c.fecha_fin}). "
            "El administrador debe actualizar/abrir el ciclo del mes en curso antes de registrar visitas."
        )


def _medico_del_vm(db: Session, vm_id: int, medico_id: int) -> MedicoVisita:
    m = db.query(MedicoVisita).filter(
        MedicoVisita.id == medico_id, MedicoVisita.activo == True).first()  # noqa: E712
    if m is None:
        raise ValueError("Médico no encontrado")
    if m.vm_id != vm_id:
        raise ValueError("El médico no pertenece a tu panel")
    # Un médico pendiente de aprobación (o rechazado) aún no forma parte oficial del
    # panel: no se le puede registrar visita hasta que el Gerente de Distrito lo apruebe.
    if m.estado_aprobacion != "APROBADO":
        raise ValueError("El médico está pendiente de aprobación del Gerente de Distrito — aún no puedes registrarle visita.")
    return m


def _ya_registrada(db: Session, vm_id: int, uuid_cliente: str | None) -> VisitaRegistro | None:
    """La visita que ese teléfono ya envió con esa huella, si existe.

    Es lo que hace SEGURO reintentar desde el móvil. Sin esto, la única forma de que la
    cola no duplique sería no reintentar nunca — y entonces una respuesta perdida en un
    parqueo subterráneo se lleva por delante el trabajo de la mañana.

    Devolver la visita existente y no un error: para el teléfono el reintento tiene que
    verse EXACTAMENTE como si hubiera funcionado a la primera. Un 409 aquí obligaría a
    cada cliente a distinguir «ya estaba» de «falló», y esa distinción se implementa mal
    tarde o temprano."""
    if not uuid_cliente:
        return None
    return db.query(VisitaRegistro).filter(
        VisitaRegistro.vm_id == vm_id,
        VisitaRegistro.uuid_cliente == uuid_cliente).first()


def registrar_visita(db: Session, vm_id: int, datos: VisitaRegistrar, usuario_id: int | None) -> VisitaRegistro:
    repetida = _ya_registrada(db, vm_id, getattr(datos, "uuid_cliente", None))
    if repetida is not None:
        logger.info(f"Reintento de visita ya registrada id={repetida.id} VM={vm_id} "
                    f"uuid={datos.uuid_cliente} — se devuelve la existente")
        return repetida
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    # Hora del servidor menos los minutos indicados (ventana 60 min ya validada en el schema).
    fecha_hora = _ahora_utc() - timedelta(minutes=datos.hace_minutos)
    # La ventana del ciclo son fechas de NEGOCIO (del calendario del país), así que se
    # compara contra el día local del visitador. Con la fecha UTC, una visita capturada
    # el último día del ciclo a las 21:00 en RD caía «fuera de la ventana» y se rechazaba.
    pais = _pais_del_vm(db, vm_id)
    _guard_ventana_ciclo(db, ciclo_id, _a_local(db, pais, fecha_hora).date())
    productos = "|".join(f"{p.producto}:{p.mencion}" for p in datos.productos) or None
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita=datos.tipo_visita, fecha_hora=fecha_hora,
        comentario=datos.comentario, productos=productos, ejecutada=True, registrado_por=usuario_id,
        acompanado=bool(getattr(datos, "acompanado", False)),
        latitud=getattr(datos, "latitud", None), longitud=getattr(datos, "longitud", None),
        uuid_cliente=getattr(datos, "uuid_cliente", None),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"Visita registrada id={v.id} VM={vm_id} médico={datos.medico_id} tipo={datos.tipo_visita}")
    return v


def registrar_no_visita(db: Session, vm_id: int, datos: VisitaNoVisita, usuario_id: int | None) -> VisitaRegistro:
    repetida = _ya_registrada(db, vm_id, getattr(datos, "uuid_cliente", None))
    if repetida is not None:
        logger.info(f"Reintento de no-visita ya registrada id={repetida.id} VM={vm_id} "
                    f"uuid={datos.uuid_cliente} — se devuelve la existente")
        return repetida
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    _guard_ventana_ciclo(db, ciclo_id, hoy_local(db, _pais_del_vm(db, vm_id)))
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita="V", fecha_hora=_ahora_utc(),
        comentario=(datos.comentario or None), ejecutada=False,
        causa_no_visita=datos.causa, registrado_por=usuario_id,
        uuid_cliente=getattr(datos, "uuid_cliente", None),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"No-visita registrada id={v.id} VM={vm_id} médico={datos.medico_id} causa='{datos.causa}'")
    return v


def _serializar_visitas(db: Session, vs: list, pais_codigo: str | None = None) -> list[dict]:
    """Serializa registros de visita al dict del feed (con nombre del médico).

    `hora` sale en la hora LOCAL del país, que es la única que el visitador reconoce
    como suya. Guardado va UTC; enseñado va local."""
    mids = {v.medico_id for v in vs}
    nombres = dict(db.query(MedicoVisita.id, MedicoVisita.nombre_completo)
                   .filter(MedicoVisita.id.in_(mids)).all()) if mids else {}
    def _prods(s):
        if not s:
            return []
        return [p.split(":")[0] for p in s.split("|")]
    return [{
        "id": v.id, "medico_id": v.medico_id, "medico": nombres.get(v.medico_id, "?"),
        "tipo_visita": v.tipo_visita, "ejecutada": v.ejecutada,
        "acompanado": bool(v.acompanado),
        "causa_no_visita": v.causa_no_visita, "comentario": v.comentario,
        "productos": _prods(v.productos),
        "tiene_gps": v.latitud is not None and v.longitud is not None,
        "tiene_foto": v.foto is not None,
        "hora": (_a_local(db, pais_codigo, v.fecha_hora).replace(tzinfo=None).isoformat()
                 if v.fecha_hora else None),
    } for v in vs]


def visitas_del_dia(db: Session, vm_id: int) -> list[dict]:
    """Visitas registradas HOY por el VM (para el feed del móvil).

    «Hoy» es el día del visitador, no el del meridiano de Greenwich: se acota al día
    local de su país traducido a UTC. El filtro anterior arrancaba en la medianoche UTC
    —las 8 de la noche en RD—, así que a partir de esa hora el feed empezaba a contar
    el trabajo de la jornada siguiente y a soltar el de la que el visitador estaba
    terminando."""
    pais = _pais_del_vm(db, vm_id)
    _, inicio, fin = ventana_dia_local(db, pais)
    vs = db.query(VisitaRegistro).filter(
        VisitaRegistro.vm_id == vm_id,
        VisitaRegistro.fecha_hora >= inicio, VisitaRegistro.fecha_hora < fin,
    ).order_by(VisitaRegistro.fecha_hora.desc()).all()
    return _serializar_visitas(db, vs, pais)


def historial_visitas(db: Session, vm_id: int, dias: int = 30, limite: int = 200) -> list[dict]:
    """Visitas ANTERIORES del VM (últimos `dias` días, más recientes primero).

    SOLO LECTURA por diseño: el RM puede consultar sus visitas registradas y
    ver su comentario, pero no existe ningún endpoint de edición/borrado de
    visitas — el registro es inmutable."""
    dias = max(1, min(int(dias or 30), 365))
    desde = _ahora_utc() - timedelta(days=dias)
    vs = (db.query(VisitaRegistro)
          .filter(VisitaRegistro.vm_id == vm_id, VisitaRegistro.fecha_hora >= desde)
          .order_by(VisitaRegistro.fecha_hora.desc())
          .limit(limite).all())
    return _serializar_visitas(db, vs, _pais_del_vm(db, vm_id))


# Días de la semana (Mon=0 .. Sun=6) para casar con PlaneacionCiclo.dia_semana.
_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def _planeados_para_hoy(plan, ciclo, hoy) -> dict[int, str]:
    """Médico → tipo (V/R) planeado para HOY: SEMANA del ciclo + día.

    Antes solo se miraba el día de la semana, así que un viernes entraban «del día» los
    planeados para CUALQUIER viernes del ciclo (cinco médicos en la app frente a uno en
    Hoy y en el monitor web). Es la misma fecha que usan el monitor y los avisos TOP."""
    from app.services.visita_top_service import fecha_planeada
    out: dict[int, str] = {}
    if ciclo is None:
        return out
    for p in plan:
        if fecha_planeada(ciclo, p.semana, p.dia_semana) == hoy:
            out.setdefault(p.medico_id, p.tipo_visita)
    return out


def agenda_hoy(db: Session, vm_id: int) -> list[dict]:
    """Médicos PLANEADOS del VM en el ciclo. Sale EXCLUSIVAMENTE de la Planeación del
    ciclo — si el VM no ha planeado, la agenda va vacía (no hay fallback al panel).
    Cada médico trae `grupo`: 'dia' (tiene una visita planeada para HOY: semana del ciclo
    + día) o 'ciclo' (planeado para otra fecha). `tipo_visita` es el de hoy en el grupo
    del día; en el resto, el próximo pendiente (V y luego R). 'registrada' cuando ya no
    queda tipo por registrar; `visitada_hoy` si hoy se registró una visita ejecutada."""
    from app.models.visita import PlaneacionCiclo
    from app.models.dimensiones import Ciclo, Especialidad, RepresentanteMedico
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    linea_id = rm.linea_id if rm else None
    # El día —y con él el día de la SEMANA contra el que casa la planeación— es el del
    # país del visitador. En UTC, a partir de las 8 de la noche en RD la agenda pasaba
    # a mostrar la del día siguiente mientras el visitador aún trabajaba el suyo.
    pais = rm.pais_codigo if rm else None
    hoy = hoy_local(db, pais)
    hoy_nombre = _DIAS[hoy.weekday()]

    plan_all = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all() if ciclo_id else []
    if not plan_all:
        return []  # sin planeación → nada que registrar (la visita se programa en Planeación del Ciclo)
    de_hoy = _planeados_para_hoy(plan_all, db.get(Ciclo, ciclo_id), hoy)

    # Por médico: tipos planeados y día/hora por tipo (V y R pueden caer en días distintos).
    tipos_plan: dict[int, set[str]] = {}
    dia_por_tipo: dict[tuple[int, str], str | None] = {}
    hora_por_tipo: dict[tuple[int, str], str | None] = {}
    for p in plan_all:
        tipos_plan.setdefault(p.medico_id, set()).add(p.tipo_visita)
        dia_por_tipo[(p.medico_id, p.tipo_visita)] = p.dia_semana
        hora_por_tipo[(p.medico_id, p.tipo_visita)] = p.hora_estimada

    medico_ids = list(tipos_plan)
    # Solo médicos APROBADOS entran a la agenda (los pendientes no son visitables aún).
    medicos = {m.id: m for m in db.query(MedicoVisita).filter(
        MedicoVisita.id.in_(medico_ids), MedicoVisita.estado_aprobacion == "APROBADO").all()} if medico_ids else {}
    esp_ids = {m.especialidad_id for m in medicos.values() if m.especialidad_id}
    esp = dict(db.query(Especialidad.id, Especialidad.nombre).filter(Especialidad.id.in_(esp_ids)).all()) if esp_ids else {}

    # Tipos EJECUTADOS en el ciclo (para saber qué queda pendiente) + no-visita de hoy.
    ejec_tipos: dict[int, set[str]] = {}
    no_vis_hoy: set[int] = set()
    vis_hoy: set[int] = set()
    for v in db.query(VisitaRegistro).filter(
            VisitaRegistro.vm_id == vm_id, VisitaRegistro.ciclo_id == ciclo_id,
            VisitaRegistro.medico_id.in_(medico_ids)).all():
        es_hoy = bool(v.fecha_hora) and _a_local(db, pais, v.fecha_hora).date() == hoy
        if v.ejecutada:
            ejec_tipos.setdefault(v.medico_id, set()).add(v.tipo_visita)
            if es_hoy:
                vis_hoy.add(v.medico_id)
        elif es_hoy:
            no_vis_hoy.add(v.medico_id)

    agenda = []
    for mid in medico_ids:
        m = medicos.get(mid)
        if not m:
            continue
        req = tipos_plan[mid]
        ejec = ejec_tipos.get(mid, set())
        pend = req - ejec
        completo = not pend
        no_visita = (not ejec) and (mid in no_vis_hoy)
        if mid in de_hoy:
            # En el grupo del día se enseña la visita planeada PARA HOY, y cuenta como
            # registrada en cuanto ese tipo se ejecutó (aunque quede la Revisita de otra semana).
            tipo_rel = de_hoy[mid]
            registrada = completo or no_visita or tipo_rel in ejec
        else:
            # Tipo relevante = el próximo pendiente (Vista antes que Revisita); si ya está
            # completo, el último tipo planeado (para ubicar su día).
            tipo_rel = "V" if "V" in pend else ("R" if "R" in pend else ("R" if "R" in req else "V"))
            registrada = completo or no_visita
        dia_rel = dia_por_tipo.get((mid, tipo_rel))
        hora_rel = hora_por_tipo.get((mid, tipo_rel))
        grupo = "dia" if mid in de_hoy else "ciclo"
        agenda.append({
            "medico_id": mid, "nombre": m.nombre_completo,
            "especialidad": esp.get(m.especialidad_id), "categoria": m.categoria,
            "centro_trabajo": m.centro_trabajo, "provincia": m.provincia, "linea_id": linea_id,
            "tipo_visita": tipo_rel,
            "dia_semana": dia_rel, "hora_estimada": hora_rel, "grupo": grupo,
            "estado": "registrada" if registrada else "pendiente",
            "no_visita": no_visita,
            "visitada_hoy": mid in vis_hoy,
        })
    # Del día primero, luego pendientes antes que registradas, luego por hora y nombre.
    agenda.sort(key=lambda a: (a["grupo"] != "dia", a["estado"] != "pendiente", a["hora_estimada"] or "99:99", a["nombre"]))
    return agenda


# ── Foto de visita (BLOB) — v2 ────────────────────────────────────────────
MAX_FOTO_BYTES = 15 * 1024 * 1024   # 15 MB — servidor sin límite; permite fotos de buena calidad
_MAGIC_JPEG = b"\xff\xd8\xff"
_MAGIC_PNG = b"\x89PNG\r\n"


def _es_imagen(contenido: bytes) -> bool:
    return contenido[:3] == _MAGIC_JPEG or contenido[:6] == _MAGIC_PNG


def guardar_foto_visita(db: Session, visita_id: int, contenido: bytes, mime: str) -> None:
    """Valida (magic bytes JPEG/PNG + tamaño ≤ 15MB) y guarda la foto como BLOB.
    El frontend ya normaliza la foto a JPEG comprimido antes de subir."""
    if len(contenido) > MAX_FOTO_BYTES:
        raise ValueError("La foto excede el tamaño máximo (15 MB)")
    if not _es_imagen(contenido):
        raise ValueError("El archivo no es una imagen JPEG/PNG válida")
    v = db.query(VisitaRegistro).filter(VisitaRegistro.id == visita_id).first()
    if v is None:
        raise ValueError("Visita no encontrada")
    v.foto = contenido
    v.foto_mime = mime or "image/jpeg"
    db.commit()


def obtener_foto_visita(db: Session, visita_id: int):
    """Devuelve (bytes, mime) de la foto, o None si la visita no existe o no tiene foto."""
    v = db.query(VisitaRegistro).filter(VisitaRegistro.id == visita_id).first()
    if v is None or not v.foto:
        return None
    return bytes(v.foto), (v.foto_mime or "image/jpeg")
