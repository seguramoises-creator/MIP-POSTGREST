"""RBAC Fase 1 — catálogo de recursos, matriz rol→permiso y auditoría de seguridad.

Fuente de verdad de la matriz: `app/core/authz/matrix.py` (código). Estas tablas son el
espejo sembrado (idempotente) para inspección/auditoría y para el contrato del frontend.
Ver spec `docs/superpowers/specs/2026-07-18-rbac-abac-seguridad-design.md`.
"""
from datetime import datetime, timezone

from sqlalchemy import String, Integer, DateTime, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class Recurso(Base):
    """Catálogo de los 28 recursos (funcionalidades) de la matriz."""
    __tablename__ = "DIM_Recurso"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    modulo: Mapped[str] = mapped_column(String(60), nullable=False)


class RolPermiso(Base):
    """Matriz rol→recurso→acción→alcance (espejo de matrix.MATRIZ). Llave natural única."""
    __tablename__ = "FACT_RolPermiso"
    __table_args__ = (
        UniqueConstraint("rol", "recurso", "accion", name="UQ_RolPermiso"),
        {"schema": "Security"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recurso: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String(20), nullable=False)
    alcance: Mapped[str] = mapped_column(String(10), nullable=False)
    # Sello de versión del caché de runtime: el motor recarga la matriz cuando cambia MAX(actualizado_en).
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc),
        onupdate=lambda: datetime.now(timezone.utc), nullable=True)


class AuditoriaSeguridad(Base):
    """Log append-only de acciones sensibles (asignación de rol, configure/approve, export,
    excepción Superadmin). Nunca guarda datos personales sensibles."""
    __tablename__ = "FACT_AuditoriaSeguridad"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_rol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evento: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recurso: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alcance: Mapped[str | None] = mapped_column(String(10), nullable=True)
    objetivo: Mapped[str | None] = mapped_column(String(160), nullable=True)  # p.ej. "user:5"
    detalle: Mapped[str | None] = mapped_column(String(500), nullable=True)   # texto corto, sin PII
    resultado: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OK|DENEGADO|ERROR
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True)
