"""Registro de eventos sensibles en Security.FACT_AuditoriaSeguridad (append-only).

Eventos típicos: ROL_ASIGNADO, CONFIG_PUBLICADA, APROBACION, EXPORTACION, EXCEPCION_SUPERADMIN.
Best-effort: no debe romper el flujo de negocio si el registro falla. Nunca guarda PII sensible.
"""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.seguridad_rbac import AuditoriaSeguridad


def registrar_evento_seguridad(db: Session, actor, evento: str, *, recurso=None, accion=None,
                               alcance=None, objetivo=None, detalle=None, resultado="OK") -> None:
    try:
        db.add(AuditoriaSeguridad(
            actor_usuario_id=getattr(actor, "id", None),
            actor_rol=getattr(getattr(actor, "rol", None), "value", None),
            evento=evento, recurso=recurso, accion=accion, alcance=alcance,
            objetivo=objetivo, detalle=detalle, resultado=resultado))
        db.commit()
    except Exception as e:  # noqa: BLE001 — auditoría best-effort, no interrumpe negocio
        db.rollback()
        logger.warning(f"[authz.audit] no se pudo registrar '{evento}': {e}")
