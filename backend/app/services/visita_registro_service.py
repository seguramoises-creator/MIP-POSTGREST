"""Registro de Visita (Parte 4 del spec). Usa la hora del SERVIDOR (no del cliente)
para evitar manipulación; ventana de 60 min; comentario obligatorio y no genérico
(validado en el schema); registro de no-visita con causa.
"""
from datetime import datetime, timezone, timedelta

from loguru import logger
from sqlalchemy.orm import Session

from app.models.visita import MedicoVisita, VisitaRegistro
from app.schemas.visita import VisitaRegistrar, VisitaNoVisita
from app.services.visita_cobertura_service import ciclo_por_defecto
from app.services import recalculo_service


def _guard_ciclo_abierto(db, ciclo_id):
    """Bloquea escrituras sobre ciclos cerrados (inmutables)."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        raise ValueError("El ciclo está cerrado — solo lectura")


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


def registrar_visita(db: Session, vm_id: int, datos: VisitaRegistrar, usuario_id: int | None) -> VisitaRegistro:
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    # Hora del servidor menos los minutos indicados (ventana 60 min ya validada en el schema).
    fecha_hora = datetime.now(timezone.utc) - timedelta(minutes=datos.hace_minutos)
    productos = "|".join(f"{p.producto}:{p.mencion}" for p in datos.productos) or None
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita=datos.tipo_visita, fecha_hora=fecha_hora,
        comentario=datos.comentario, productos=productos, ejecutada=True, registrado_por=usuario_id,
        acompanado=bool(getattr(datos, "acompanado", False)),
        latitud=getattr(datos, "latitud", None), longitud=getattr(datos, "longitud", None),
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"Visita registrada id={v.id} VM={vm_id} médico={datos.medico_id} tipo={datos.tipo_visita}")
    return v


def registrar_no_visita(db: Session, vm_id: int, datos: VisitaNoVisita, usuario_id: int | None) -> VisitaRegistro:
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    _guard_ciclo_abierto(db, ciclo_id)
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita="V", fecha_hora=datetime.now(timezone.utc),
        comentario=(datos.comentario or None), ejecutada=False,
        causa_no_visita=datos.causa, registrado_por=usuario_id,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"No-visita registrada id={v.id} VM={vm_id} médico={datos.medico_id} causa='{datos.causa}'")
    return v


def _serializar_visitas(db: Session, vs: list) -> list[dict]:
    """Serializa registros de visita al dict del feed (con nombre del médico)."""
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
        "hora": v.fecha_hora.isoformat() if v.fecha_hora else None,
    } for v in vs]


def visitas_del_dia(db: Session, vm_id: int) -> list[dict]:
    """Visitas registradas HOY por el VM (para el feed del móvil)."""
    hoy = datetime.now(timezone.utc).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, tzinfo=timezone.utc)
    vs = db.query(VisitaRegistro).filter(
        VisitaRegistro.vm_id == vm_id, VisitaRegistro.fecha_hora >= inicio,
    ).order_by(VisitaRegistro.fecha_hora.desc()).all()
    return _serializar_visitas(db, vs)


def historial_visitas(db: Session, vm_id: int, dias: int = 30, limite: int = 200) -> list[dict]:
    """Visitas ANTERIORES del VM (últimos `dias` días, más recientes primero).

    SOLO LECTURA por diseño: el RM puede consultar sus visitas registradas y
    ver su comentario, pero no existe ningún endpoint de edición/borrado de
    visitas — el registro es inmutable."""
    dias = max(1, min(int(dias or 30), 365))
    desde = datetime.now(timezone.utc) - timedelta(days=dias)
    vs = (db.query(VisitaRegistro)
          .filter(VisitaRegistro.vm_id == vm_id, VisitaRegistro.fecha_hora >= desde)
          .order_by(VisitaRegistro.fecha_hora.desc())
          .limit(limite).all())
    return _serializar_visitas(db, vs)


# Días de la semana (Mon=0 .. Sun=6) para casar con PlaneacionCiclo.dia_semana.
_DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes", "Sábado", "Domingo"]


def agenda_hoy(db: Session, vm_id: int) -> list[dict]:
    """Médicos programados del VM para HOY (agenda). Sale de la Planeación del ciclo;
    si la planeación tiene día, filtra al día de hoy; si no, muestra lo planeado.
    Fallback: si no hay planeación, usa el panel activo. Marca 'registrada' cuando ya
    existe una visita ejecutada hoy para ese médico."""
    from app.models.visita import PlaneacionCiclo
    from app.models.dimensiones import Especialidad, RepresentanteMedico
    ciclo_id = ciclo_por_defecto(db, vm_id)  # ciclo ABIERTO del país del VM
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    linea_id = rm.linea_id if rm else None
    hoy = datetime.now(timezone.utc).date()
    hoy_nombre = _DIAS[hoy.weekday()]
    inicio = datetime(hoy.year, hoy.month, hoy.day, tzinfo=timezone.utc)

    plan = db.query(PlaneacionCiclo).filter(
        PlaneacionCiclo.vm_id == vm_id, PlaneacionCiclo.ciclo_id == ciclo_id).all() if ciclo_id else []
    con_dia = [p for p in plan if p.dia_semana]
    if con_dia:
        plan = [p for p in con_dia if p.dia_semana == hoy_nombre]

    # Un ítem por médico (si tiene V y R, prioriza R). Orden por hora estimada.
    por_medico: dict[int, PlaneacionCiclo] = {}
    for p in sorted(plan, key=lambda x: (x.hora_estimada or "99:99")):
        cur = por_medico.get(p.medico_id)
        if cur is None or (p.tipo_visita == "R" and cur.tipo_visita != "R"):
            por_medico[p.medico_id] = p

    medico_ids = list(por_medico)
    fuente_plan = True
    if not medico_ids:  # fallback: panel activo vigente (solo médicos APROBADOS)
        fuente_plan = False
        meds = db.query(MedicoVisita).filter(
            MedicoVisita.vm_id == vm_id, MedicoVisita.activo == True,
            MedicoVisita.estado_aprobacion == "APROBADO").all()
        medico_ids = [m.id for m in meds]

    # Solo médicos APROBADOS entran a la agenda (los pendientes no son visitables aún).
    medicos = {m.id: m for m in db.query(MedicoVisita).filter(
        MedicoVisita.id.in_(medico_ids), MedicoVisita.estado_aprobacion == "APROBADO").all()} if medico_ids else {}
    esp_ids = {m.especialidad_id for m in medicos.values() if m.especialidad_id}
    esp = dict(db.query(Especialidad.id, Especialidad.nombre).filter(Especialidad.id.in_(esp_ids)).all()) if esp_ids else {}

    visit_hoy = {}
    if medico_ids:
        for v in db.query(VisitaRegistro).filter(
                VisitaRegistro.vm_id == vm_id, VisitaRegistro.fecha_hora >= inicio,
                VisitaRegistro.medico_id.in_(medico_ids)).all():
            visit_hoy[v.medico_id] = v.ejecutada

    agenda = []
    for mid in medico_ids:
        m = medicos.get(mid)
        if not m:
            continue
        p = por_medico.get(mid)
        registrada = mid in visit_hoy
        agenda.append({
            "medico_id": mid, "nombre": m.nombre_completo,
            "especialidad": esp.get(m.especialidad_id), "categoria": m.categoria,
            "centro_trabajo": m.centro_trabajo, "provincia": m.provincia, "linea_id": linea_id,
            "tipo_visita": (p.tipo_visita if p else "V"),
            "hora_estimada": (p.hora_estimada if p else None),
            "estado": "registrada" if registrada else "pendiente",
            "no_visita": (registrada and visit_hoy.get(mid) is False),
        })
    agenda.sort(key=lambda a: (a["estado"] != "pendiente", a["hora_estimada"] or "99:99", a["nombre"]))
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
