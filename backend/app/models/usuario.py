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
    # RBAC Fase 1 (jul-2026): roles canónicos de la matriz de seguridad (spec
    # 2026-07-18-rbac-abac-seguridad-design.md). GERENTE_MARCA=Gerente de Producto,
    # GERENTE_PRODUCTIVIDAD=Gerente de Capacitación y Productividad, PRESIDENCIA=Director
    # General, ADMIN=Superadmin. Estos 4 no tenían equivalente y se agregan nuevos.
    GERENTE_MARKETING      = "GERENTE_MARKETING"
    GERENTE_MEDICO         = "GERENTE_MEDICO"
    ANALISTA_DATOS         = "ANALISTA_DATOS"
    FINANZAS               = "FINANZAS"

class Usuario(Base):
    __tablename__ = "DIM_Usuario"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False, index=True)
    # Email OPCIONAL (jul-2026): usuarios sin correo (login por username). Único cuando
    # existe; en Postgres un índice único admite múltiples NULL, así que varios usuarios
    # pueden no tener correo sin colisionar.
    email: Mapped[str | None] = mapped_column(String(200), unique=True, nullable=True)
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
    password_actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    # RBAC Fase 1: al cambiar el rol se fija a now(); un access token con iat anterior deja de
    # ser válido (revocación de permisos, ver deps.get_current_user).
    roles_actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    @property
    def bloqueado(self) -> bool:
        """True si la cuenta está bloqueada AHORA (bloqueado_hasta en el futuro).
        Comparación timezone-aware: bloqueado_hasta se guarda naive (UTC)."""
        if self.bloqueado_hasta is None:
            return False
        bh = self.bloqueado_hasta
        if bh.tzinfo is None:
            bh = bh.replace(tzinfo=timezone.utc)
        return bh > datetime.now(timezone.utc)


class TokenRevocado(Base):
    """
    Blacklist de refresh tokens persistida en BD (esquema Security).

    Reemplaza la blacklist en memoria (FIX W-04 v1): el set en memoria no se
    comparte entre workers de uvicorn, por lo que un logout en un proceso no
    revocaba el token en los demás. Persistir en la base de datos hace la revocación
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


class PasswordHistorial(Base):
    """Hashes de contraseñas previas por usuario, para impedir la reutilización
    de las últimas N. Se poda al insertar (ver password_policy_service)."""
    __tablename__ = "FACT_PasswordHistorial"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), index=True, nullable=False)
    hashed_password: Mapped[str] = mapped_column(String(255), nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))


class PasswordResetCode(Base):
    """Código de recuperación de contraseña ("Olvidó su contraseña").

    El código se guarda HASHEADO (bcrypt), nunca en claro. Es de un solo uso
    (`usado`), expira (`expira_en`) y al solicitar uno nuevo se invalidan los
    previos del mismo usuario. `intentos` limita la cantidad de validaciones
    fallidas antes de invalidarlo (defensa contra fuerza bruta del código corto)."""
    __tablename__ = "FACT_PasswordReset"
    __table_args__ = {"schema": "Security"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), index=True, nullable=False)
    codigo_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    expira_en: Mapped[datetime] = mapped_column(DateTime, nullable=False, index=True)
    usado: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    intentos: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc))
