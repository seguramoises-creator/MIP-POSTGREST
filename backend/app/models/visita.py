"""SCGCPR — Modelos del Módulo de Visita Médica (esquema `Visita`).

Adapta la especificación "VISTA — Módulo de Visita Médica" al stack del proyecto
(SQL Server + SQLAlchemy 2.0). Reutiliza Config.DIM_RM (visitador médico / VM),
Config.DIM_Ciclo y Config.DIM_Especialidad en lugar de crear catálogos nuevos.

Fase 1: Panel Médico (catálogo de médicos del universo de visita).
"""
from datetime import datetime, timezone

from sqlalchemy import (
    String, Boolean, Integer, DateTime, ForeignKey, CHAR, Index,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class MedicoVisita(Base):
    """Médico del panel de visita de un VM (Parte 2 del spec).

    `ciclos_sin_visita` lo mantiene el cierre de ciclo (Ruptura de Secuencia, Parte 5):
    se resetea a 0 si hubo ≥1 visita en el ciclo, o se incrementa si no hubo ninguna.
    """
    __tablename__ = "DIM_MedicoVisita"
    __table_args__ = (
        Index("IX_MedicoVisita_vm", "vm_id"),
        Index("IX_MedicoVisita_nombre", "nombre_completo"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)  # solo MAYÚSCULAS
    especialidad_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Especialidad.id"), nullable=True)
    categoria: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # A / B / C
    tipo_consultorio: Mapped[str | None] = mapped_column(String(60), nullable=True)
    direccion: Mapped[str | None] = mapped_column(String(300), nullable=True)
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ciclos_sin_visita: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    fecha_registro: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    registrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
