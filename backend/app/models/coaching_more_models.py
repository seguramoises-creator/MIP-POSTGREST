"""
SCGCPR — Modelos del Módulo de Coaching (Modelo de Ventas MORE), esquema `coaching`.

Módulo autocontenido. Digitaliza la hoja de acompañamiento GD→RM (Laboratorio Mallén):
7 secciones / 26 ítems MORE calificados en escala D/P/A/E (1..4), promedio automático,
plan de desarrollo + plan de acción, acuerdo/desacuerdo del RM y firma táctil.

REGLA DURA — INMUTABILIDAD (append-only): una hoja guardada NUNCA se edita ni borra.
Se aplica a nivel de BD con un trigger (ver migración): rechaza UPDATE/DELETE sobre
`coaching.Sesion` y `coaching.ItemEvaluado`. Las CORRECCIONES son una hoja NUEVA que
enmienda a la anterior vía `corrige_a_id` (el original nunca se toca).

Equivalencia de roles: GD = "Gerente" (crea/llena); RM = "VM" = Config.DIM_RM (evaluado,
solo lectura + firma).
"""
from datetime import datetime, timezone, date

from sqlalchemy import Integer, String, Boolean, DateTime, Date, Numeric, Text, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


# Secciones del modelo MORE, en orden (para agrupar y calcular promedios de sección).
SECCIONES_MORE = [
    "Planificación",
    "Apertura",
    "Desarrollo de la Visita",
    "AV: Ayuda Visual",
    "Conocimientos Científicos",
    "Cierre",
    "Seguimiento",
]


class CoachingItemCatalogo(Base):
    """Catálogo editable de los ítems MORE (Sección 5 del spec). Sembrado con los 26
    ítems del instrumento fuente; Gerencia puede ajustar la redacción sin deploy.
    NO es inmutable (a diferencia de las hojas)."""
    __tablename__ = "ItemCatalogo"
    __table_args__ = {"schema": "coaching"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    seccion: Mapped[str] = mapped_column(String(60), nullable=False)
    orden_seccion: Mapped[int] = mapped_column(Integer, nullable=False)
    orden_item: Mapped[int] = mapped_column(Integer, nullable=False)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CoachingSesion(Base):
    """Hoja de coaching (append-only). Una fila por acompañamiento GD→RM."""
    __tablename__ = "Sesion"
    __table_args__ = {"schema": "coaching"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    # Autor (GD) y evaluado (RM/VM)
    gd_usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=False)
    gd_gerente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)  # para KPI por GD
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)  # KPI por ciclo

    # Encabezado
    fecha_coaching: Mapped[date] = mapped_column(Date, nullable=False)
    medicos_vistos: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # Resultado calculado (promedio simple de los 7 promedios de sección)
    evaluacion_promedio: Mapped[float] = mapped_column(Numeric(5, 2), nullable=False)

    # Plan de desarrollo (obligatorios por decisión de negocio) + plan de acción
    fortalezas: Mapped[str] = mapped_column(Text, nullable=False)
    areas_perfeccionar: Mapped[str] = mapped_column(Text, nullable=False)
    plan_que_haras: Mapped[str] = mapped_column(Text, nullable=False)
    plan_como_haras: Mapped[str] = mapped_column(Text, nullable=False)
    plan_como_veras: Mapped[str] = mapped_column(Text, nullable=False)
    plan_fecha_seguimiento: Mapped[date] = mapped_column(Date, nullable=False)

    # Acuerdo del RM + firma
    rm_acuerdo: Mapped[str] = mapped_column(String(20), nullable=False)  # de_acuerdo | no_de_acuerdo
    rm_justificacion_desacuerdo: Mapped[str | None] = mapped_column(Text, nullable=True)
    rm_firma_imagen: Mapped[str] = mapped_column(Text, nullable=False)  # data URL base64 (PNG)
    rm_firma_timestamp: Mapped[datetime] = mapped_column(DateTime, default=_ahora)

    # Corrección (append-only): esta hoja enmienda a otra sin editarla.
    corrige_a_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("coaching.Sesion.id"), nullable=True)
    motivo_correccion: Mapped[str | None] = mapped_column(Text, nullable=True)

    pdf_generado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=_ahora)

    items: Mapped[list["CoachingItemEvaluado"]] = relationship(
        "CoachingItemEvaluado", back_populates="sesion", cascade="all, delete-orphan")


class CoachingItemEvaluado(Base):
    """Detalle: una fila por ítem MORE calificado en una hoja (append-only).
    Guarda snapshot de sección + texto para que ediciones futuras del catálogo no
    alteren hojas históricas."""
    __tablename__ = "ItemEvaluado"
    __table_args__ = {"schema": "coaching"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    sesion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("coaching.Sesion.id"), nullable=False)
    item_catalogo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("coaching.ItemCatalogo.id"), nullable=True)
    seccion: Mapped[str] = mapped_column(String(60), nullable=False)
    item_texto: Mapped[str] = mapped_column(Text, nullable=False)
    calificacion: Mapped[int] = mapped_column(Integer, nullable=False)  # 1..4 (D/P/A/E)

    sesion: Mapped["CoachingSesion"] = relationship("CoachingSesion", back_populates="items")
