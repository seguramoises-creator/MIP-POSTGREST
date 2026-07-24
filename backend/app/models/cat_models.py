"""
Modelos SQLAlchemy 2.0 para el nuevo módulo de Categorización Médica.

Schemas: cat.* (dimensiones y facts) + stg.* (staging).

Estos modelos son INDEPENDIENTES de los existentes en Config/DW —
no reemplazan DIM_CategoriaMedica, DIM_CriterioCategoria, etc., que
siguen existiendo como código muerto en dimensiones.py/hechos.py.
"""

from __future__ import annotations
from datetime import date, datetime
from decimal import Decimal
from typing import Optional

from sqlalchemy import (
    BigInteger, Boolean, Date, DateTime, Numeric, Integer,
    String, SmallInteger, ForeignKey, UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


# ── cat.LoadBatch ──────────────────────────────────────────────────────────────
class LoadBatch(Base):
    __tablename__ = "LoadBatch"
    __table_args__ = {"schema": "cat"}

    load_batch_key: Mapped[int]     = mapped_column("LoadBatchKey", BigInteger, primary_key=True, autoincrement=True)
    archivo_origen: Mapped[str]     = mapped_column("ArchivoOrigen", String(260), nullable=False)
    periodo: Mapped[str]            = mapped_column("Periodo", String(20), nullable=False)
    codigo_pais_default: Mapped[Optional[str]] = mapped_column("CodigoPaisDefault", String(2))
    fecha_carga_utc: Mapped[datetime] = mapped_column("FechaCargaUtc", DateTime, nullable=False)
    usuario_carga: Mapped[Optional[str]] = mapped_column("UsuarioCarga", String(150))
    estado: Mapped[str]             = mapped_column("Estado", String(20), nullable=False, default="RECIBIDO")
    mensaje: Mapped[Optional[str]]  = mapped_column("Mensaje", String(1000))

    snapshots: Mapped[list["FactMedicoCategoriaSnapshot"]] = relationship(
        "FactMedicoCategoriaSnapshot", back_populates="batch"
    )


# ── cat.DimPais ────────────────────────────────────────────────────────────────
class CatDimPais(Base):
    __tablename__ = "DimPais"
    __table_args__ = {"schema": "cat"}

    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, primary_key=True, autoincrement=True)
    pais_id_origen: Mapped[Optional[int]] = mapped_column("PaisIdOrigen", Integer)
    codigo_pais: Mapped[str]        = mapped_column("CodigoPais", String(2), nullable=False, unique=True)
    nombre_pais: Mapped[str]        = mapped_column("NombrePais", String(100), nullable=False)
    moneda: Mapped[Optional[str]]   = mapped_column("Moneda", String(3))
    zona_horaria: Mapped[Optional[str]] = mapped_column("ZonaHoraria", String(80))
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)
    fecha_carga_utc: Mapped[datetime] = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.DimComponenteCategoria ─────────────────────────────────────────────────
class DimComponenteCategoria(Base):
    __tablename__ = "DimComponenteCategoria"
    __table_args__ = {"schema": "cat"}

    componente_key: Mapped[int]     = mapped_column("ComponenteKey", Integer, primary_key=True, autoincrement=True)
    codigo_componente: Mapped[str]  = mapped_column("CodigoComponente", String(50), nullable=False, unique=True)
    nombre_componente: Mapped[str]  = mapped_column("NombreComponente", String(150), nullable=False)
    tipo_evaluacion: Mapped[str]    = mapped_column("TipoEvaluacion", String(30), nullable=False)
    peso_componente_pct: Mapped[Decimal] = mapped_column("PesoComponentePct", Numeric(9, 6), nullable=False)
    requerido: Mapped[bool]         = mapped_column("Requerido", Boolean, nullable=False, default=True)
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)
    fecha_carga_utc: Mapped[datetime] = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.DimClasificacionMedica ─────────────────────────────────────────────────
class DimClasificacionMedica(Base):
    __tablename__ = "DimClasificacionMedica"
    __table_args__ = (
        UniqueConstraint("PaisKey", "Clase", "VigenteDesde", name="UQ_DimClasificacion"),
        {"schema": "cat"},
    )

    clasificacion_key: Mapped[int]  = mapped_column("ClasificacionKey", Integer, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    clase: Mapped[str]              = mapped_column("Clase", String(1), nullable=False)
    puntaje_min_pct: Mapped[Decimal] = mapped_column("PuntajeMinPct", Numeric(9, 6), nullable=False)
    puntaje_max_pct: Mapped[Decimal] = mapped_column("PuntajeMaxPct", Numeric(9, 6), nullable=False)
    orden_clase: Mapped[int]        = mapped_column("OrdenClase", SmallInteger, nullable=False)
    vigente_desde: Mapped[date]     = mapped_column("VigenteDesde", Date, nullable=False)
    vigente_hasta: Mapped[Optional[date]] = mapped_column("VigenteHasta", Date)
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)
    fecha_carga_utc: Mapped[datetime] = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.DimEspecialidad ────────────────────────────────────────────────────────
class CatDimEspecialidad(Base):
    __tablename__ = "DimEspecialidad"
    __table_args__ = (
        UniqueConstraint("PaisKey", "Especialidad", name="UQ_DimEspecialidad"),
        {"schema": "cat"},
    )

    especialidad_key: Mapped[int]   = mapped_column("EspecialidadKey", Integer, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    especialidad: Mapped[str]       = mapped_column("Especialidad", String(150), nullable=False)
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)


# ── cat.DimMedico ──────────────────────────────────────────────────────────────
class CatDimMedico(Base):
    __tablename__ = "DimMedico"
    __table_args__ = {"schema": "cat"}

    medico_key: Mapped[int]         = mapped_column("MedicoKey", BigInteger, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    medico_id: Mapped[Optional[int]] = mapped_column("MedicoId", Integer)          # ID numérico del Excel (llave de negocio)
    codigo_medico: Mapped[Optional[str]] = mapped_column("CodigoMedico", String(50))
    nombre_medico: Mapped[str]      = mapped_column("NombreMedico", String(200), nullable=False)
    especialidad_key: Mapped[Optional[int]] = mapped_column("EspecialidadKey", Integer, ForeignKey("cat.DimEspecialidad.EspecialidadKey"), index=True)
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)


# ── cat.DimRepresentanteMedico ─────────────────────────────────────────────────
class CatDimRepresentante(Base):
    __tablename__ = "DimRepresentanteMedico"
    __table_args__ = (
        UniqueConstraint("PaisKey", "CodigoRepresentante", name="UQ_DimRepresentanteMedico"),
        {"schema": "cat"},
    )

    representante_key: Mapped[int]  = mapped_column("RepresentanteKey", Integer, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    representante_id_origen: Mapped[Optional[int]] = mapped_column("RepresentanteIdOrigen", Integer)
    codigo_representante: Mapped[str] = mapped_column("CodigoRepresentante", String(30), nullable=False)
    nombre_representante: Mapped[str] = mapped_column("NombreRepresentante", String(150), nullable=False)
    linea_id_origen: Mapped[Optional[int]] = mapped_column("LineaIdOrigen", Integer)
    gerente_id_origen: Mapped[Optional[int]] = mapped_column("GerenteIdOrigen", Integer)
    email: Mapped[Optional[str]]    = mapped_column("Email", String(150))
    zona: Mapped[Optional[str]]     = mapped_column("Zona", String(80))
    fecha_ingreso: Mapped[Optional[date]] = mapped_column("FechaIngreso", Date)
    cedula: Mapped[Optional[str]]   = mapped_column("Cedula", String(30))
    codigo_origen_excel: Mapped[Optional[str]] = mapped_column("CodigoOrigenExcel", String(50))
    equipo_texto: Mapped[Optional[str]] = mapped_column("EquipoTexto", String(120))
    activo: Mapped[bool]            = mapped_column("Activo", Boolean, nullable=False, default=True)


# ── cat.FactMedicoCategoriaSnapshot ───────────────────────────────────────────
class FactMedicoCategoriaSnapshot(Base):
    __tablename__ = "FactMedicoCategoriaSnapshot"
    __table_args__ = {"schema": "cat"}

    medico_categoria_key: Mapped[int] = mapped_column("MedicoCategoriaKey", BigInteger, primary_key=True, autoincrement=True)
    load_batch_key: Mapped[int]     = mapped_column("LoadBatchKey", BigInteger, ForeignKey("cat.LoadBatch.LoadBatchKey"), nullable=False, index=True)
    row_number: Mapped[int]         = mapped_column("RowNumber", Integer, nullable=False)
    periodo: Mapped[str]            = mapped_column("Periodo", String(20), nullable=False)
    pais_key: Mapped[int]           = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    medico_key: Mapped[int]         = mapped_column("MedicoKey", BigInteger, ForeignKey("cat.DimMedico.MedicoKey"), nullable=False, index=True)
    centro_medico_key: Mapped[Optional[int]] = mapped_column("CentroMedicoKey", Integer)
    geografia_key: Mapped[Optional[int]] = mapped_column("GeografiaKey", Integer)
    representante_key: Mapped[Optional[int]] = mapped_column("RepresentanteKey", Integer)
    equipo: Mapped[Optional[str]]   = mapped_column("Equipo", String(120))
    provincia: Mapped[Optional[str]] = mapped_column("Provincia", String(120))
    municipio: Mapped[Optional[str]] = mapped_column("Municipio", String(120))
    linea_id_origen: Mapped[Optional[int]] = mapped_column("LineaIdOrigen", Integer)
    pacientes_semana: Mapped[Optional[Decimal]] = mapped_column("PacientesSemana", Numeric(18, 4))
    costo_consulta: Mapped[Optional[Decimal]] = mapped_column("CostoConsulta", Numeric(18, 4))
    recetas_semana: Mapped[Optional[str]] = mapped_column("RecetasSemana", String(80))
    ubicacion_territorial_cm: Mapped[Optional[str]] = mapped_column("UbicacionTerritorialCM", String(80))
    kol: Mapped[Optional[str]]      = mapped_column("KOL", String(150))
    puntaje_total_pct: Mapped[Optional[Decimal]] = mapped_column("PuntajeTotalPct", Numeric(9, 6))
    clasificacion_key: Mapped[Optional[int]] = mapped_column("ClasificacionKey", Integer, ForeignKey("cat.DimClasificacionMedica.ClasificacionKey"), index=True)
    categoria_calculada: Mapped[Optional[str]] = mapped_column("CategoriaCalculada", String(1))
    categoria_excel: Mapped[Optional[str]] = mapped_column("CategoriaExcel", String(20))
    estado_conciliacion: Mapped[Optional[str]] = mapped_column("EstadoConciliacion", String(30))
    estado_calculo: Mapped[str]     = mapped_column("EstadoCalculo", String(20), nullable=False)
    mensaje_calculo: Mapped[Optional[str]] = mapped_column("MensajeCalculo", String(500))
    load_batch_key: Mapped[Optional[int]] = mapped_column("LoadBatchKey", BigInteger, ForeignKey("cat.LoadBatch.LoadBatchKey"), index=True)
    batch: Mapped[Optional["LoadBatch"]] = relationship("LoadBatch", back_populates="snapshots")


# ═══════════════════════════════════════════════════════════════════════════════
# MÓDULO COBERTURA PREDICTIVA — cat.* (jun-2026)
# Tablas independientes de las de Categorización Médica, pero reutilizan
# cat.DimPais, cat.DimRepresentanteMedico, cat.DimMedico.
# ═══════════════════════════════════════════════════════════════════════════════

# ── cat.DimCiclo ───────────────────────────────────────────────────────────────
class CatDimCiclo(Base):
    """Ciclos promocionales por país/línea con metas de cobertura y contactos."""
    __tablename__ = "DimCiclo"
    __table_args__ = (
        UniqueConstraint("PaisKey", "CodigoCiclo", "LineaId", name="UQ_DimCiclo_Pais_Codigo_Linea"),
        {"schema": "cat"},
    )

    ciclo_key: Mapped[int]              = mapped_column("CicloKey", Integer, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]               = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    codigo_ciclo: Mapped[str]           = mapped_column("CodigoCiclo", String(20), nullable=False)
    linea_id: Mapped[Optional[int]]     = mapped_column("LineaId", Integer)
    linea: Mapped[Optional[str]]        = mapped_column("Linea", String(100))
    fecha_inicio: Mapped[date]          = mapped_column("FechaInicio", Date, nullable=False)
    fecha_fin: Mapped[date]             = mapped_column("FechaFin", Date, nullable=False)
    dias_habiles_ciclo: Mapped[Optional[int]] = mapped_column("DiasHabilesCiclo", Integer)
    meta_cobertura_pct: Mapped[Decimal] = mapped_column("MetaCoberturaPct", Numeric(5, 4), nullable=False, default=Decimal("0.90"))
    meta_contactos_ciclo: Mapped[Optional[int]] = mapped_column("MetaContactosCiclo", Integer)
    ciclo_numero_anual: Mapped[Optional[int]] = mapped_column("CicloNumeroAnual", Integer)
    activo: Mapped[bool]                = mapped_column("Activo", Boolean, nullable=False, default=True)
    fecha_carga_utc: Mapped[datetime]   = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.DimCalendario ──────────────────────────────────────────────────────────
class CatDimCalendario(Base):
    """Calendario hábil por país — base para cálculo NETWORKDAYS en el SP."""
    __tablename__ = "DimCalendario"
    __table_args__ = (
        UniqueConstraint("PaisKey", "Fecha", name="UQ_DimCalendario_Pais_Fecha"),
        {"schema": "cat"},
    )

    fecha_key: Mapped[int]              = mapped_column("FechaKey", Integer, primary_key=True, autoincrement=True)
    pais_key: Mapped[int]               = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    fecha: Mapped[date]                 = mapped_column("Fecha", Date, nullable=False)
    ciclo_key: Mapped[Optional[int]]    = mapped_column("CicloKey", Integer, ForeignKey("cat.DimCiclo.CicloKey"), index=True)
    es_habil: Mapped[bool]              = mapped_column("EsHabil", Boolean, nullable=False, default=True)
    es_feriado: Mapped[bool]            = mapped_column("EsFeriado", Boolean, nullable=False, default=False)
    semana: Mapped[Optional[int]]       = mapped_column("Semana", Integer)
    mes: Mapped[Optional[int]]          = mapped_column("Mes", Integer)
    anio: Mapped[Optional[int]]         = mapped_column("Anio", Integer)
    nota: Mapped[Optional[str]]         = mapped_column("Nota", String(200))
    fecha_carga_utc: Mapped[datetime]   = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.FactTargetMedicoCiclo ──────────────────────────────────────────────────
class CatFactTargetMedicoCiclo(Base):
    """Universo de médicos programados por VM/ciclo — hoja COB_TARGET_MEDICO_CICLO."""
    __tablename__ = "FactTargetMedicoCiclo"
    __table_args__ = (
        UniqueConstraint("CicloKey", "RepresentanteKey", "CodigoMedicoOrigen",
                         name="UQ_Target_Ciclo_Rep_Medico"),
        {"schema": "cat"},
    )

    target_medico_key: Mapped[int]      = mapped_column("TargetMedicoKey", BigInteger, primary_key=True, autoincrement=True)
    ciclo_key: Mapped[int]              = mapped_column("CicloKey", Integer, ForeignKey("cat.DimCiclo.CicloKey"), nullable=False, index=True)
    pais_key: Mapped[int]               = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    representante_key: Mapped[int]      = mapped_column("RepresentanteKey", Integer, ForeignKey("cat.DimRepresentanteMedico.RepresentanteKey"), nullable=False, index=True)
    medico_key: Mapped[Optional[int]]   = mapped_column("MedicoKey", BigInteger, ForeignKey("cat.DimMedico.MedicoKey"), index=True)
    codigo_medico_origen: Mapped[str]   = mapped_column("CodigoMedicoOrigen", String(50), nullable=False)
    nombre_medico: Mapped[Optional[str]] = mapped_column("NombreMedico", String(200))
    especialidad_key: Mapped[Optional[int]] = mapped_column("EspecialidadKey", Integer)
    potencial: Mapped[Optional[str]]    = mapped_column("Potencial", String(5))
    territorio: Mapped[Optional[str]]   = mapped_column("Territorio", String(100))
    frecuencia_objetivo: Mapped[Optional[int]] = mapped_column("FrecuenciaObjetivo", Integer)
    programado_flag: Mapped[bool]       = mapped_column("ProgramadoFlag", Boolean, nullable=False, default=True)
    categoria_medica: Mapped[Optional[str]] = mapped_column("CategoriaMedica", String(5))
    fuente: Mapped[Optional[str]]       = mapped_column("Fuente", String(100))
    fecha_carga_utc: Mapped[datetime]   = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.FactVisitaMedica ───────────────────────────────────────────────────────
class CatFactVisitaMedica(Base):
    """Bitácora de visitas realizadas — hoja COB_FACT_VISITAS."""
    __tablename__ = "FactVisitaMedica"
    __table_args__ = {"schema": "cat"}

    visita_key: Mapped[int]             = mapped_column("VisitaKey", BigInteger, primary_key=True, autoincrement=True)
    visita_id_origen: Mapped[Optional[str]] = mapped_column("VisitaIdOrigen", String(50))
    fecha_visita: Mapped[date]          = mapped_column("FechaVisita", Date, nullable=False)
    ciclo_key: Mapped[int]              = mapped_column("CicloKey", Integer, ForeignKey("cat.DimCiclo.CicloKey"), nullable=False, index=True)
    pais_key: Mapped[int]               = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    representante_key: Mapped[int]      = mapped_column("RepresentanteKey", Integer, ForeignKey("cat.DimRepresentanteMedico.RepresentanteKey"), nullable=False, index=True)
    codigo_medico_origen: Mapped[str]   = mapped_column("CodigoMedicoOrigen", String(50), nullable=False)
    medico_key: Mapped[Optional[int]]   = mapped_column("MedicoKey", BigInteger)
    tipo_contacto: Mapped[Optional[str]] = mapped_column("TipoContacto", String(50))
    estado_visita: Mapped[str]          = mapped_column("EstadoVisita", String(50), nullable=False, default="Realizada")
    producto_foco: Mapped[Optional[str]] = mapped_column("ProductoFoco", String(100))
    fuente: Mapped[Optional[str]]       = mapped_column("Fuente", String(100))
    fecha_carga_utc: Mapped[datetime]   = mapped_column("FechaCargaUtc", DateTime, nullable=False)


# ── cat.KpiCoberturaPredictiva ─────────────────────────────────────────────────
class CatKpiCoberturaPredictiva(Base):
    """
    Tabla de salida del SP cat.sp_CalcularCoberturaPredictiva.
    Una fila por (FechaCorte, CicloKey, RepresentanteKey).
    Usar la vista cat.vwDashboardCoberturaPredictivaGD para incluir
    nombres y códigos de las dimensiones.
    """
    __tablename__ = "KpiCoberturaPredictiva"
    __table_args__ = (
        UniqueConstraint("FechaCorte", "CicloKey", "RepresentanteKey",
                         name="UQ_Kpi_Corte_Ciclo_Rep"),
        {"schema": "cat"},
    )

    kpi_key: Mapped[int]                = mapped_column("KpiKey", BigInteger, primary_key=True, autoincrement=True)
    fecha_corte: Mapped[date]           = mapped_column("FechaCorte", Date, nullable=False)
    ciclo_key: Mapped[int]              = mapped_column("CicloKey", Integer, ForeignKey("cat.DimCiclo.CicloKey"), nullable=False, index=True)
    pais_key: Mapped[int]               = mapped_column("PaisKey", Integer, ForeignKey("cat.DimPais.PaisKey"), nullable=False, index=True)
    linea: Mapped[Optional[str]]        = mapped_column("Linea", String(100))
    gd: Mapped[Optional[str]]           = mapped_column("GD", String(150))
    representante_key: Mapped[int]      = mapped_column("RepresentanteKey", Integer, ForeignKey("cat.DimRepresentanteMedico.RepresentanteKey"), nullable=False, index=True)
    nombre_vm: Mapped[Optional[str]]    = mapped_column("NombreVM", String(150))
    medicos_programados: Mapped[int]    = mapped_column("MedicosProgramados", Integer, nullable=False, default=0)
    medicos_visitados_unicos: Mapped[int] = mapped_column("MedicosVisitadosUnicos", Integer, nullable=False, default=0)
    cobertura_actual_pct: Mapped[Decimal] = mapped_column("CoberturaActualPct", Numeric(9, 6), nullable=False, default=Decimal("0"))
    cobertura_esperada_pct: Mapped[Decimal] = mapped_column("CoberturaEsperadaPct", Numeric(9, 6), nullable=False, default=Decimal("0"))
    cobertura_proyectada_pct: Mapped[Decimal] = mapped_column("CoberturaProyectadaPct", Numeric(9, 6), nullable=False, default=Decimal("0"))
    meta_cobertura_pct: Mapped[Decimal] = mapped_column("MetaCoberturaPct", Numeric(9, 6), nullable=False, default=Decimal("0.9"))
    brecha_actual_vs_esperada: Mapped[Decimal] = mapped_column("BrechaActualVsEsperada", Numeric(9, 6), nullable=False, default=Decimal("0"))
    brecha_proyectada_vs_meta: Mapped[Decimal] = mapped_column("BrechaProyectadaVsMeta", Numeric(9, 6), nullable=False, default=Decimal("0"))
    medicos_requeridos_meta: Mapped[int] = mapped_column("MedicosRequeridosMeta", Integer, nullable=False, default=0)
    medicos_pendientes_meta: Mapped[int] = mapped_column("MedicosPendientesMeta", Integer, nullable=False, default=0)
    medicos_diarios_requeridos: Mapped[int] = mapped_column("MedicosDiariosRequeridos", Integer, nullable=False, default=0)
    contactos_meta_ciclo: Mapped[int]   = mapped_column("ContactosMetaCiclo", Integer, nullable=False, default=0)
    contactos_realizados: Mapped[int]   = mapped_column("ContactosRealizados", Integer, nullable=False, default=0)
    cumplimiento_contactos_pct: Mapped[Decimal] = mapped_column("CumplimientoContactosPct", Numeric(9, 6), nullable=False, default=Decimal("0"))
    contactos_proyectados: Mapped[Decimal] = mapped_column("ContactosProyectados", Numeric(12, 4), nullable=False, default=Decimal("0"))
    contactos_pendientes: Mapped[Decimal] = mapped_column("ContactosPendientes", Numeric(12, 4), nullable=False, default=Decimal("0"))
    contactos_diarios_requeridos: Mapped[int] = mapped_column("ContactosDiariosRequeridos", Integer, nullable=False, default=0)
    dias_habiles_totales: Mapped[int]   = mapped_column("DiasHabilesTotales", Integer, nullable=False, default=0)
    dias_habiles_transcurridos: Mapped[int] = mapped_column("DiasHabilesTranscurridos", Integer, nullable=False, default=0)
    dias_habiles_restantes: Mapped[int] = mapped_column("DiasHabilesRestantes", Integer, nullable=False, default=0)
    estado_cobertura: Mapped[str]       = mapped_column("EstadoCobertura", String(10), nullable=False, default="Rojo")
    estado_ritmo: Mapped[str]           = mapped_column("EstadoRitmo", String(10), nullable=False, default="Rojo")
    estado_psp: Mapped[str]             = mapped_column("EstadoPSP", String(10), nullable=False, default="Rojo")
    lectura_accionable: Mapped[Optional[str]] = mapped_column("LecturaAccionable", String(2000))
    fecha_carga_utc: Mapped[datetime]   = mapped_column("FechaCargaUtc", DateTime, nullable=False)
