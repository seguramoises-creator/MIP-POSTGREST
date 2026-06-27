"""
SCGCPR — Modelo: Usuario y Roles (Security schema)
"""
from datetime import datetime, timezone
from enum import Enum as PyEnum
from sqlalchemy import String, Boolean, DateTime, Enum, Integer, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class Rol(str, PyEnum):
    ADMIN                  = "ADMIN"
    PRESIDENCIA            = "PRESIDENCIA"
    DIR_COMERCIAL          = "DIR_COMERCIAL"
    GERENTE_PRODUCTIVIDAD  = "GERENTE_PRODUCTIVIDAD"
    GERENTE_DISTRITO       = "GERENTE_DISTRITO"
    GERENTE_MARCA          = "GERENTE_MARCA"
    REPRESENTANTE_MEDICO   = "REPRESENTANTE_MEDICO"
    CONSULTA               = "CONSULTA"


class Usuario(Base):
    __tablename__ = "DIM_Usuario"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    rol: Mapped[Rol] = mapped_column(Enum(Rol), nullable=False)
    pais_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=True)
    rm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))
