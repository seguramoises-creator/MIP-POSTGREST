"""
SCGCPR — Modelos: Todas las Tablas de Hechos (DW schema)
FACT_RendimientoComercial, FACT_Ventas, FACT_EVOIR,
FACT_Coaching, FACT_Capacitacion, FACT_Ranking,
FACT_Reconocimiento, FACT_Auditoria, FACT_CargaExcel
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Integer, Date, DateTime,
    Numeric, ForeignKey, Text, BigInteger
)
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class RendimientoComercial(Base):
    """Tabla de hechos principal — todos los KPIs de productividad por RM/ciclo."""
    __tablename__ = "FACT_RendimientoComercial"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    gerente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    indicador_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Indicador.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    mes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    # Valores
    valor_real: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=False, default=0)
    valor_meta: Mapped[Decimal] = mapped_column(Numeric(14, 4), nullable=True)
    porcentaje_cumplimiento: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)

    # Auditoría
    carga_excel_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Ventas(Base):
    __tablename__ = "FACT_Ventas"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    ventas_reales: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=False, default=0)
    cuota: Mapped[Decimal] = mapped_column(Numeric(16, 2), nullable=True)
    cumplimiento_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    crecimiento_pct: Mapped[Decimal | None] = mapped_column(Numeric(8, 4), nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class EvoIR(Base):
    __tablename__ = "FACT_EVOIR"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    producto_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    producto_nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    prescripciones_actuales: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    prescripciones_anteriores: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=0)
    evolucion_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Coaching(Base):
    __tablename__ = "FACT_Coaching"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    gerente_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=False)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    tipo: Mapped[str] = mapped_column(String(30), nullable=False)  # INDIVIDUAL | CAMPO
    coaching_programado: Mapped[int] = mapped_column(Integer, default=0)
    coaching_ejecutado: Mapped[int] = mapped_column(Integer, default=0)
    cumplimiento_pct: Mapped[Decimal] = mapped_column(Numeric(8, 4), default=0)
    calificacion_calidad: Mapped[Decimal] = mapped_column(Numeric(5, 2), default=0)
    peso_cantidad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.7)
    peso_calidad: Mapped[Decimal] = mapped_column(Numeric(4, 2), default=0.3)
    resultado_coaching: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_coaching: Mapped[date | None] = mapped_column(Date, nullable=True)
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class CapacitacionFact(Base):
    __tablename__ = "FACT_Capacitacion"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    capacitacion_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Capacitacion.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)

    asistio: Mapped[bool] = mapped_column(Boolean, default=False)
    calificacion: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    aprobado: Mapped[bool] = mapped_column(Boolean, default=False)
    horas_completadas: Mapped[Decimal] = mapped_column(Numeric(6, 2), default=0)
    fecha_actividad: Mapped[date | None] = mapped_column(Date, nullable=True)
    puntaje: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Ranking(Base):
    __tablename__ = "FACT_Ranking"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    linea_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    mes_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    tipo_ranking: Mapped[str] = mapped_column(String(30), nullable=False)  # MENSUAL | TRIMESTRAL | ANUAL | REGIONAL
    iup_total: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    iup_productividad: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    iup_comercial: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    iup_coaching: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    iup_capacitacion: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    iup_consistencia: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    posicion: Mapped[int] = mapped_column(Integer, nullable=False)
    posicion_anterior: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elegible: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_generacion: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))


class Reconocimiento(Base):
    __tablename__ = "FACT_Reconocimiento"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False, index=True)
    rm_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    gerente_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    premio_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Premio.id"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)

    iup_al_momento: Mapped[Decimal] = mapped_column(Numeric(10, 4), default=0)
    posicion_ranking: Mapped[int | None] = mapped_column(Integer, nullable=True)
    certificado_generado: Mapped[bool] = mapped_column(Boolean, default=False)
    certificado_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    aprobado_por: Mapped[str | None] = mapped_column(String(200), nullable=True)
    fecha_reconocimiento: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    observaciones: Mapped[str | None] = mapped_column(Text, nullable=True)


class Auditoria(Base):
    __tablename__ = "FACT_Auditoria"
    __table_args__ = {"schema": "Audit"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    fecha_hora: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc), index=True)
    usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    username: Mapped[str | None] = mapped_column(String(100), nullable=True)
    rol: Mapped[str | None] = mapped_column(String(50), nullable=True)
    accion: Mapped[str] = mapped_column(String(50), nullable=False)  # LOGIN | LOGOUT | CREATE | UPDATE | DELETE | ETL | RANKING
    modulo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    tabla: Mapped[str | None] = mapped_column(String(100), nullable=True)
    campo: Mapped[str | None] = mapped_column(String(100), nullable=True)
    registro_id: Mapped[str | None] = mapped_column(String(50), nullable=True)
    valor_anterior: Mapped[str | None] = mapped_column(Text, nullable=True)
    valor_nuevo: Mapped[str | None] = mapped_column(Text, nullable=True)
    ip_address: Mapped[str | None] = mapped_column(String(50), nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(500), nullable=True)
    exitoso: Mapped[bool] = mapped_column(Boolean, default=True)
    detalle: Mapped[str | None] = mapped_column(Text, nullable=True)


class CargaExcel(Base):
    __tablename__ = "FACT_CargaExcel"
    __table_args__ = {"schema": "ETL"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    usuario_id: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre_archivo: Mapped[str] = mapped_column(String(300), nullable=False)
    tipo_archivo: Mapped[str] = mapped_column(String(50), nullable=False)  # PRODUCTIVIDAD | COMERCIAL | COACHING | CAPACITACION
    ciclo_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    modo: Mapped[str] = mapped_column(String(20), nullable=False)  # SIMULACION | PRODUCCION
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE")  # PENDIENTE | PROCESANDO | EXITOSO | ERROR
    total_filas: Mapped[int] = mapped_column(Integer, default=0)
    filas_exitosas: Mapped[int] = mapped_column(Integer, default=0)
    filas_error: Mapped[int] = mapped_column(Integer, default=0)
    filas_advertencia: Mapped[int] = mapped_column(Integer, default=0)
    log_errores: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_advertencias: Mapped[str | None] = mapped_column(Text, nullable=True)
    duracion_segundos: Mapped[Decimal | None] = mapped_column(Numeric(8, 2), nullable=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
