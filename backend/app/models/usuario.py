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
    CAPACITACION           = "CAPACITACION"

class Usuario(Base):
    __tablename__ = "DIM_Usuario"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    email: Mapped[str] = mapped_column(String(200), unique=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    nombre_completo: Mapped[str] = mapped_column(String(200), nullable=False)
    rol: Mapped[Rol] = mapped_column(Enum(Rol), nullable=False)
    pais_codigo: Mapped[str | None] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=True)
    rm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    debe_cambiar_password: Mapped[bool] = mapped_column(Boolean, default=True)
    intentos_fallidos: Mapped[int] = mapped_column(Integer, default=0)
    bloqueado_hasta: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    ultimo_login: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))


class TokenRevocado(Base):
    """
    Blacklist de refresh tokens persistida en BD (esquema Security).

    Reemplaza la blacklist en memoria (FIX W-04 v1): el set en memoria no se
    comparte entre workers de uvicorn, por lo que un logout en un proceso no
    revocaba el token en los demás. Persistir en SQL Server hace la revocación
    consistente entre todos los workers y sobrevive a reinicios.

    `jti` es el identificador único del token (claim `jti`, o el fallback
    `sub:exp` para tokens emitidos antes de añadir el claim). `expira_en`
    permite purgar filas cuyo token ya expiró de forma natural.
    """
    __tablename__ = "FACT_TokenRevocado"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    jti: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    motivo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    expira_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    revocado_en: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
