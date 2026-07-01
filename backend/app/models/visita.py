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


class VisitaRegistro(Base):
    """Registro de visita médica (Parte 4 del spec). Fuente de la Cobertura.

    Tabla en el esquema `Visita` (distinta del `DW.FACT_Visita` de Cobertura Predictiva).
    tipo_visita: 'V' (Vista) / 'R' (Revisita). `ejecutada=False` = no-visita con causa.
    """
    __tablename__ = "FactVisita"
    __table_args__ = (
        Index("IX_FactVisita_vm_ciclo", "vm_id", "ciclo_id"),
        Index("IX_FactVisita_medico", "medico_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # V / R
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    comentario: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    ejecutada: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    causa_no_visita: Mapped[str | None] = mapped_column(String(80), nullable=True)
    registrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class PlaneacionCiclo(Base):
    """Planeación de visitas del ciclo (Parte 3 del spec). Una fila por médico y
    tipo (V/R). Reglas P01-P06 validadas al guardar."""
    __tablename__ = "PlaneacionCiclo"
    __table_args__ = (
        Index("IX_Planeacion_vm_ciclo", "vm_id", "ciclo_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    vm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_id: Mapped[int] = mapped_column(Integer, ForeignKey("Visita.DIM_MedicoVisita.id"), nullable=False)
    tipo_visita: Mapped[str] = mapped_column(CHAR(1), nullable=False)  # V / R
    semana: Mapped[int] = mapped_column(Integer, nullable=False)       # 1 a 4
    dia_semana: Mapped[str | None] = mapped_column(String(12), nullable=True)  # Lunes..Viernes
    hora_estimada: Mapped[str | None] = mapped_column(String(5), nullable=True)  # HH:MM
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    modificado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)


class CierreCicloVisita(Base):
    """Registro de un cierre de ciclo de visita (Parte 5 — Ruptura de Secuencia).

    Al cerrar un ciclo se hace rodar el contador `ciclos_sin_visita` de cada médico:
    se resetea a 0 si tuvo ≥1 visita ejecutada, o se incrementa si no tuvo ninguna.
    Esta tabla guarda el resumen del cierre y sirve de guard de idempotencia: un ciclo
    solo puede cerrarse una vez (evita doble incremento del contador)."""
    __tablename__ = "CierreCicloVisita"
    __table_args__ = (
        Index("IX_CierreVisita_ciclo", "ciclo_id"),
        {"schema": "Visita"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    fecha_cierre: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    panel: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    visitados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sin_visitar: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ruptura_nueva: Mapped[int] = mapped_column(Integer, nullable=False, default=0)   # contador incrementado este cierre
    ruptura_critica: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # quedaron con ≥3 ciclos sin visita
    cerrado_por: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
