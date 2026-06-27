"""
SCGCPR — Modelos: Todas las Dimensiones (DW schema)
DIM_Pais, DIM_Linea, DIM_Gerente, DIM_RM, DIM_Indicador,
DIM_IndicadorTabla, DIM_Ciclo, DIM_Mes, DIM_Premio,
DIM_Capacitacion, DIM_ReglaElegibilidad
"""
from datetime import datetime, date
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Integer, Date, DateTime,
    Numeric, ForeignKey, Text
)
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.db.database import Base


class Pais(Base):
    __tablename__ = "DIM_Pais"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    moneda: Mapped[str] = mapped_column(String(10), nullable=True)
    zona_horaria: Mapped[str] = mapped_column(String(50), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Linea(Base):
    __tablename__ = "DIM_Linea"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Gerente(Base):
    __tablename__ = "DIM_Gerente"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # DISTRITO | MARCA | REGIONAL
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    rms: Mapped[list["RepresentanteMedico"]] = relationship("RepresentanteMedico", back_populates="gerente")


class RepresentanteMedico(Base):
    __tablename__ = "DIM_RM"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    cedula: Mapped[str | None] = mapped_column(String(30), nullable=True)          # ← DIM_RM.CEDULA
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    zona: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)

    gerente: Mapped["Gerente"] = relationship("Gerente", back_populates="rms")


class Indicador(Base):
    __tablename__ = "DIM_Indicador"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)  # ← por país
    codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    rol: Mapped[str] = mapped_column(String(20), nullable=False, default="RM")    # ← DIM_INDICADOR.ROL
    modulo: Mapped[str] = mapped_column(String(50), nullable=False)               # GESTION | RESULTADOS
    tipo_periodo: Mapped[str] = mapped_column(String(10), nullable=False, default="CICLO")  # CICLO | MES
    ponderacion_pct: Mapped[int] = mapped_column(Integer, nullable=False, default=0)        # 0-100
    escala: Mapped[int] = mapped_column(Integer, nullable=False, default=1)                 # 1 (%) ó 100 (puntos)
    valor_min: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    valor_max: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=True)
    # Campos adicionales del modelo interno
    formula: Mapped[str | None] = mapped_column(Text, nullable=True)
    peso_iup: Mapped[Decimal] = mapped_column(Numeric(5, 4), default=0)
    unidad: Mapped[str | None] = mapped_column(String(30), nullable=True)
    meta_global: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    orden: Mapped[int] = mapped_column(Integer, default=0)

    tablas: Mapped[list["IndicadorTabla"]] = relationship("IndicadorTabla", back_populates="indicador")


class IndicadorTabla(Base):
    """Tablas de conversión KPI → Puntaje, parametrizadas por indicador Y país."""
    __tablename__ = "DIM_IndicadorTabla"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicador_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Indicador.id"), nullable=False)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)  # ← rangos por país
    rango_desde: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    rango_hasta: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    puntos: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    indicador: Mapped["Indicador"] = relationship("Indicador", back_populates="tablas")


class Ciclo(Base):
    __tablename__ = "DIM_Ciclo"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–13 según país
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre_canonico: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ← CICLO-01-2026
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    dias_laborables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cerrado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Mes(Base):
    __tablename__ = "DIM_Mes"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    mes: Mapped[int] = mapped_column(Integer, nullable=False)
    nombre: Mapped[str] = mapped_column(String(20), nullable=False)
    abrev: Mapped[str | None] = mapped_column(String(5), nullable=True)   # ← DIM_MES.MESABREV
    ciclo_mes: Mapped[int | None] = mapped_column(Integer, nullable=True)  # ← DIM_MES.CICLOMES
    trimestre: Mapped[int] = mapped_column(Integer, nullable=False)
    semestre: Mapped[int] = mapped_column(Integer, nullable=False)


class Premio(Base):
    __tablename__ = "DIM_Premio"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    categoria: Mapped[str] = mapped_column(String(50), nullable=False)  # RM | GD | GM | LINEA | PAIS | REGIONAL
    frecuencia: Mapped[str] = mapped_column(String(20), nullable=False)  # MENSUAL | TRIMESTRAL | SEMESTRAL | ANUAL
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CapacitacionDim(Base):
    __tablename__ = "DIM_Capacitacion"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # CURSO | CERTIFICACION | EVALUACION | PROGRAMA
    duracion_horas: Mapped[Decimal | None] = mapped_column(Numeric(6, 2), nullable=True)
    puntaje_aprobacion: Mapped[Decimal | None] = mapped_column(Numeric(5, 2), nullable=True)
    obligatorio: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ReglaElegibilidad(Base):
    __tablename__ = "DIM_ReglaElegibilidad"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    indicador_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    umbral_minimo: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    aplica_ranking: Mapped[bool] = mapped_column(Boolean, default=True)
    aplica_reconocimiento: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
