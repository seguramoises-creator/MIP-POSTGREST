"""Traza de validación de los lotes que envía Laboratorio Mallén.

POR QUÉ ESTA TABLA VIVE EN `Audit` Y NO EN `ext`
------------------------------------------------
`ext` es el contrato con un tercero: el SQL ya se le entregó a Mallén y su
usuario `mallen_etl` tiene permisos concedidos tabla por tabla. Agregarle una
tabla obligaría a reeditar lo entregado y a repetir la concesión de permisos,
para guardar un dato que además es NUESTRO (el resultado de nuestra validación,
no algo que ellos envíen). `Audit` es exactamente su sitio: la traza de qué vino
mal y cuándo.

`controlcarga.mensaje` es String(500) y solo lleva el resumen; el detalle fila a
fila vive aquí.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

#: Un dominio inválido o un conteo descuadrado RECHAZA el lote; una referencia
#: que todavía no llegó solo avisa (es normal que un hecho venga en un lote y su
#: dimensión en otro).
SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"


class IntegracionHallazgo(Base):
    """Una inconsistencia detectada al validar un lote de Mallén."""
    __tablename__ = "IntegracionHallazgo"
    __table_args__ = (
        Index("IX_IntegHallazgo_lote", "lote_id"),
        {"schema": "Audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ext.controlcarga.lote_id"), nullable=False)
    tabla: Mapped[str] = mapped_column(String(40), nullable=False)
    # Nulos a propósito: los hallazgos de lote (conteo descuadrado, lote vacío)
    # no pertenecen a ninguna fila ni a ningún campo.
    origen_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    campo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    problema: Mapped[str] = mapped_column(String(300), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    detectado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
