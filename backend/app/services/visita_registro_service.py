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


def _medico_del_vm(db: Session, vm_id: int, medico_id: int) -> MedicoVisita:
    m = db.query(MedicoVisita).filter(
        MedicoVisita.id == medico_id, MedicoVisita.activo == True).first()  # noqa: E712
    if m is None:
        raise ValueError("Médico no encontrado")
    if m.vm_id != vm_id:
        raise ValueError("El médico no pertenece a tu panel")
    return m


def registrar_visita(db: Session, vm_id: int, datos: VisitaRegistrar, usuario_id: int | None) -> VisitaRegistro:
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
    # Hora del servidor menos los minutos indicados (ventana 60 min ya validada en el schema).
    fecha_hora = datetime.now(timezone.utc) - timedelta(minutes=datos.hace_minutos)
    v = VisitaRegistro(
        vm_id=vm_id, ciclo_id=ciclo_id, medico_id=datos.medico_id,
        tipo_visita=datos.tipo_visita, fecha_hora=fecha_hora,
        comentario=datos.comentario, ejecutada=True, registrado_por=usuario_id,
    )
    db.add(v)
    db.commit()
    db.refresh(v)
    logger.info(f"Visita registrada id={v.id} VM={vm_id} médico={datos.medico_id} tipo={datos.tipo_visita}")
    return v


def registrar_no_visita(db: Session, vm_id: int, datos: VisitaNoVisita, usuario_id: int | None) -> VisitaRegistro:
    _medico_del_vm(db, vm_id, datos.medico_id)
    ciclo_id = ciclo_por_defecto(db)
    if ciclo_id is None:
        raise ValueError("No hay ciclo activo")
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


def visitas_del_dia(db: Session, vm_id: int) -> list[dict]:
    """Visitas registradas HOY por el VM (para el feed del móvil)."""
    hoy = datetime.now(timezone.utc).date()
    inicio = datetime(hoy.year, hoy.month, hoy.day, tzinfo=timezone.utc)
    vs = db.query(VisitaRegistro).filter(
        VisitaRegistro.vm_id == vm_id, VisitaRegistro.fecha_hora >= inicio,
    ).order_by(VisitaRegistro.fecha_hora.desc()).all()
    mids = {v.medico_id for v in vs}
    nombres = dict(db.query(MedicoVisita.id, MedicoVisita.nombre_completo)
                   .filter(MedicoVisita.id.in_(mids)).all()) if mids else {}
    return [{
        "id": v.id, "medico_id": v.medico_id, "medico": nombres.get(v.medico_id, "?"),
        "tipo_visita": v.tipo_visita, "ejecutada": v.ejecutada,
        "causa_no_visita": v.causa_no_visita, "comentario": v.comentario,
        "hora": v.fecha_hora.isoformat() if v.fecha_hora else None,
    } for v in vs]
