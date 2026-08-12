"""
SCGCPR — Modelos: Todas las Dimensiones (DW schema)
DIM_Pais, DIM_Linea, DIM_Gerente, DIM_RM, DIM_Indicador,
DIM_IndicadorTabla, DIM_MetaIndicador, DIM_CategoriaDesempeno, DIM_KpiDashboard,
DIM_Ciclo, DIM_Mes, DIM_Premio, DIM_Capacitacion, DIM_ReglaElegibilidad
"""
from datetime import datetime, date, timezone
from decimal import Decimal
from sqlalchemy import (
    String, Boolean, Integer, Date, DateTime,
    Numeric, ForeignKey, Text, UniqueConstraint, Index, func
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
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    codigo: Mapped[str] = mapped_column(String(20), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Gerente(Base):
    __tablename__ = "DIM_Gerente"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)  # DISTRITO | MARCA | REGIONAL
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    rms: Mapped[list["RepresentanteMedico"]] = relationship("RepresentanteMedico", back_populates="gerente")


class RepresentanteMedico(Base):
    __tablename__ = "DIM_RM"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    linea_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False)
    gerente_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    codigo: Mapped[str] = mapped_column(String(20), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    cedula: Mapped[str | None] = mapped_column(String(30), nullable=True)          # ← DIM_RM.CEDULA
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    zona: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)
    fecha_ingreso: Mapped[date | None] = mapped_column(Date, nullable=True)
    # Mínimo de visitas ACOMPAÑADAS por día para habilitar una hoja de Coaching (MORE).
    # Por defecto 5; configurable de 1 a 9 desde Administración.
    coaching_min_dia: Mapped[int] = mapped_column(Integer, nullable=False, default=5, server_default="5")

    gerente: Mapped["Gerente"] = relationship("Gerente", back_populates="rms")


class Indicador(Base):
    __tablename__ = "DIM_Indicador"
    __table_args__ = (
        # El mismo codigo puede repetirse entre paises distintos (cada pais
        # define sus propios indicadores); lo que debe ser unico es la
        # combinacion (pais_codigo, codigo). La tabla original tenia un UNIQUE
        # solo sobre `codigo` (de cuando no existia pais_codigo) — se reemplaza
        # por esta restriccion compuesta via migracion.
        UniqueConstraint("pais_codigo", "codigo", name="UQ_Indicador_Pais_Codigo"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)  # ← por país
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
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)  # ← rangos por país
    codigo_indicador: Mapped[str | None] = mapped_column(String(50),  nullable=True)
    nombre_indicador: Mapped[str | None] = mapped_column(String(150), nullable=True)
    rango_desde: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    rango_hasta: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    puntos: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(100), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    indicador: Mapped["Indicador"] = relationship("Indicador", back_populates="tablas")


class MetaIndicador(Base):
    """Metas/umbrales y parámetros de cálculo por indicador (configuración de dashboard).

    Origen: hoja DIM_META_INDICADOR del Excel DIM_MIP_FINAL.xlsx (estructura V3:
    incluye PUNTAJE_MAXIMO, META_100, TIPO_CALCULO y ORDEN_DASHBOARD).
    Cada indicador (ya es por país vía DIM_Indicador.pais_codigo) tiene una sola meta.
    """
    __tablename__ = "DIM_MetaIndicador"
    __table_args__ = (
        UniqueConstraint("indicador_id", name="UQ_MetaIndicador_Indicador"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    indicador_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Indicador.id"), nullable=False)
    peso: Mapped[Decimal] = mapped_column(Numeric(6, 2), nullable=False, default=0)
    minimo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    objetivo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    maximo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    puntaje_maximo: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    meta_100: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    tipo_calculo: Mapped[str | None] = mapped_column(String(30), nullable=True)   # PORCENTAJE | PUNTAJE | INDICE
    orden_dashboard: Mapped[int | None] = mapped_column(Integer, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    indicador: Mapped["Indicador"] = relationship("Indicador")


class CategoriaDesempeno(Base):
    """Categorías de clasificación por score (Excelente/Bueno/En Desarrollo/Crítico/Sin Datos).

    Origen: hoja DIM_CATEGORIA_DESEMPENO del Excel DIM_MIP_FINAL.xlsx.
    Tabla global de configuración (sin FK a otras DIM — no depende de país).
    """
    __tablename__ = "DIM_CategoriaDesempeno"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(30), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    score_min: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    score_max: Mapped[Decimal | None] = mapped_column(Numeric(10, 4), nullable=True)
    color_dashboard: Mapped[str | None] = mapped_column(String(30), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class KpiDashboard(Base):
    """Catálogo de KPIs mostrados en los dashboards (página, fórmula de cálculo).

    Origen: hoja DIM_KPI_DASHBOARD del Excel DIM_MIP_FINAL.xlsx.
    Tabla global de configuración (sin FK a otras DIM — no depende de país).
    """
    __tablename__ = "DIM_KpiDashboard"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    pagina_dashboard: Mapped[str | None] = mapped_column(String(100), nullable=True)
    tipo_calculo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Ciclo(Base):
    __tablename__ = "DIM_Ciclo"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    anio: Mapped[int] = mapped_column(Integer, nullable=False)
    numero: Mapped[int] = mapped_column(Integer, nullable=False)  # 1–13 según país
    nombre: Mapped[str] = mapped_column(String(50), nullable=False)
    nombre_canonico: Mapped[str | None] = mapped_column(String(50), nullable=True)  # ← CICLO-01-2026
    fecha_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    fecha_fin: Mapped[date] = mapped_column(Date, nullable=False)
    dias_laborables: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cerrado: Mapped[bool] = mapped_column(Boolean, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    @property
    def estado(self) -> str:
        """Ciclo de vida derivado de las fechas + `cerrado`:
        PLANIFICADO (aún no inicia) · VIGENTE (hoy dentro de la ventana) ·
        POR_CERRAR (fecha fin ya pasó, aún abierto) · CERRADO (snapshot inmutable)."""
        from datetime import date as _date
        if self.cerrado:
            return "CERRADO"
        hoy = _date.today()
        if self.fecha_inicio and hoy < self.fecha_inicio:
            return "PLANIFICADO"
        if self.fecha_fin and hoy > self.fecha_fin:
            return "POR_CERRAR"
        return "VIGENTE"

    @property
    def vencido(self) -> bool:
        """True si está abierto pero su fecha fin ya pasó (ciclo 'zombi' por cerrar)."""
        from datetime import date as _date
        return (not self.cerrado) and self.fecha_fin is not None and _date.today() > self.fecha_fin


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
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    indicador_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    umbral_minimo: Mapped[Decimal] = mapped_column(Numeric(8, 4), nullable=False)
    aplica_ranking: Mapped[bool] = mapped_column(Boolean, default=True)
    aplica_reconocimiento: Mapped[bool] = mapped_column(Boolean, default=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ReceptividadOpcion(Base):
    """Catálogo de opciones de comportamiento observable — Matriz de Desarrollo LSII.

    Modelo de Liderazgo Situacional II (Hersey-Blanchard): el eje de
    Receptividad/Compromiso (0-100) se calcula a partir de 5 dimensiones
    conductuales, cada una con 5 opciones de comportamiento observable.

    Regla de negocio crítica: el GD (evaluador) solo debe ver `texto_comportamiento`
    en la pantalla de evaluación — `score_oculto` y `peso_dimension` NUNCA se
    exponen al evaluador, para evitar que sesgue su selección. El sistema los
    usa internamente para calcular el score de Receptividad (ver lsii_service.py).

    Tabla global de configuración (sin FK a país — el modelo conductual es
    genérico, igual que DIM_CategoriaDesempeno / DIM_KpiDashboard).
    """
    __tablename__ = "DIM_ReceptividadOpcion"
    __table_args__ = (
        UniqueConstraint("dimension_codigo", "orden_opcion", name="UQ_ReceptividadOpcion_Dim_Orden"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    dimension_codigo: Mapped[str] = mapped_column(String(50), nullable=False)       # ej: ACEPTA_RESPONSABILIDADES
    dimension_nombre: Mapped[str] = mapped_column(String(200), nullable=False)      # ej: "Acepta nuevas responsabilidades"
    dimension_descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden_dimension: Mapped[int] = mapped_column(Integer, nullable=False, default=0)  # 1-5, orden de la dimensión
    orden_opcion: Mapped[int] = mapped_column(Integer, nullable=False, default=0)      # 1-5, orden dentro de la dimensión
    texto_comportamiento: Mapped[str] = mapped_column(Text, nullable=False)          # ÚNICO campo visible al GD
    score_oculto: Mapped[int] = mapped_column(Integer, nullable=False)               # 1-5 — NUNCA exponer al GD
    peso_dimension: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.20"))  # NUNCA exponer al GD
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ConfiguracionLsii(Base):
    """Umbral de corte para clasificar los cuadrantes D1-D4 de la Matriz LSII.

    Fila única de configuración global (sin FK a país, igual que
    DIM_ReceptividadOpcion). Editable desde la pantalla de Administración
    para que un usuario ADMIN/GERENTE_PRODUCTIVIDAD pueda ajustar los
    puntos de corte de Desempeño y Receptividad sin tocar el código
    (ver lsii_service.obtener_configuracion / actualizar_configuracion).
    """
    __tablename__ = "DIM_ConfiguracionLSII"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    corte_desempeno: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("80"))
    corte_receptividad: Mapped[Decimal] = mapped_column(Numeric(5, 2), nullable=False, default=Decimal("80"))
    actualizado_en: Mapped[datetime] = mapped_column(DateTime, nullable=False)
    actualizado_por: Mapped[str | None] = mapped_column(String(100), nullable=True)


# ═════════════════════════════════════════════════════════════════════════
# NUEVO — Módulo de Cobertura Predictiva y Ritmo de Ejecución (4DX)
# Origen: Modulo_Cobertura_Predictiva_Ejemplo_VM_v3.xlsx (hojas Parametros,
# Target_Medicos, Diccionario). Reemplaza el dashboard Comercial/Ventas+EVO_IR
# del GD por un motor de cobertura médica y ritmo de visitas con lectura
# accionable diaria (ver cobertura_predictiva_service.py).
# ═════════════════════════════════════════════════════════════════════════

class TargetMedico(Base):
    """Universo de médicos target (programados) por RM y ciclo — Config.DIM_TargetMedico.

    Origen: hoja Target_Medicos del Excel de referencia. Cada fila es un
    médico asignado al territorio de un RM en un ciclo dado. No existe una
    DIM_Medico separada en MSM — el médico se identifica por su código
    fuente (`medico_codigo`), igual que en la columna B (medico_id) del Excel.

    Motor_Formulas:
      J (médicos programados)      = COUNT(*) WHERE rm_id=X, ciclo_id=Y, programado=True
      K (médicos requeridos meta)  = CEILING(J × meta_cobertura, 1)
    """
    __tablename__ = "DIM_TargetMedico"
    __table_args__ = (
        UniqueConstraint("rm_id", "ciclo_id", "medico_codigo", name="UQ_TargetMedico_RM_Ciclo_Medico"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    rm_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_RM.id"), nullable=False)
    ciclo_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    medico_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    medico_nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    especialidad: Mapped[str | None] = mapped_column(String(100), nullable=True)
    potencial: Mapped[str | None] = mapped_column(String(20), nullable=True)  # ej: A | B | C
    programado: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)  # ← columna I (programado_flag)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Feriado(Base):
    """Feriados / días no laborables por país — usados para NETWORKDAYS en el
    cálculo de días hábiles del Motor_Formulas (columnas N/O/P).

    Origen: Parametros!$B$17:$B$25 del Excel de referencia (lista vacía en
    el ejemplo). Aquí se modela como catálogo editable por país en lugar de
    un rango fijo de celdas.
    """
    __tablename__ = "DIM_Feriado"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "fecha", name="UQ_Feriado_Pais_Fecha"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    fecha: Mapped[date] = mapped_column(Date, nullable=False)
    nombre: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class ParametroCobertura(Base):
    """Meta de cobertura médica, parametrizable por línea/ciclo — Motor_Formulas!H.

    Resuelve la nota de negocio registrada en la hoja Diccionario del Excel
    ("Nota Moisés: Debe quedar parametrizable por línea/ciclo"): en el Excel
    de referencia la meta (90%) es un único valor global (Parametros!$B$4);
    aquí se permite definir una meta específica por (país, línea, ciclo),
    con resolución en cascada desde la más específica a la más general:
      1. (pais_codigo, linea_id, ciclo_id)  — meta exacta del ciclo
      2. (pais_codigo, linea_id, NULL)      — meta por defecto de la línea
      3. (pais_codigo, NULL, NULL)          — meta por defecto del país
    Ver cobertura_predictiva_service.obtener_meta_cobertura().
    """
    __tablename__ = "DIM_ParametroCobertura"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "linea_id", "ciclo_id", name="UQ_ParametroCobertura_Pais_Linea_Ciclo"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    ciclo_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    meta_cobertura: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0.90"))
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ═════════════════════════════════════════════════════════════════════════
# NUEVO — Módulo de Categorización Médica (sustituye a Capacitación, ver
# capacitacion.py/Capacitacion.tsx, no registrado). Origen: "Plantilla
# Calculo de Categorias BFD(OCT) usar este maximo.xlsx" (hoja Bases y
# Criterios). Clasifica cada médico en A/B/C/D según un score ponderado de
# 5 criterios (ver categorizacion_service.py).
#
# Reutiliza entidades ya existentes en vez de duplicarlas:
#   - "Distrito"/"Equipo" del Excel      → Config.DIM_Gerente (tipo=DISTRITO)
#   - "Representante" del Excel          → Config.DIM_RM
# Por eso NO se crean DIM_Distrito ni DIM_Representante nuevas.
# ═════════════════════════════════════════════════════════════════════════

class Producto(Base):
    """Catálogo de productos promocionales (DIM_Producto). Lo mantiene el Gerente de
    Producto y alimenta la Parrilla Promocional: incluye el gerente de producto
    responsable de la promoción, el área terapéutica y el segmento target por defecto."""
    __tablename__ = "DIM_Producto"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False)  # ONCX-301
    nombre: Mapped[str] = mapped_column(String(120), nullable=False)
    area_terapeutica: Mapped[str | None] = mapped_column(String(80), nullable=True)   # Oncología
    descripcion: Mapped[str | None] = mapped_column(String(150), nullable=True)        # Inhibidor selectivo
    segmento_target: Mapped[str | None] = mapped_column(String(120), nullable=True)    # Cat. A + B Oncología
    meta_muestras_visita: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    gerente_producto: Mapped[str | None] = mapped_column(String(150), nullable=True)   # gerente de producto de promoción
    linea_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Linea.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Especialidad(Base):
    """Catálogo de especialidades médicas. Global (no depende de país),
    igual que DIM_CategoriaDesempeno / DIM_KpiDashboard."""
    __tablename__ = "DIM_Especialidad"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(150), unique=True, nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Provincia(Base):
    """Provincias por país (división administrativa de primer nivel)."""
    __tablename__ = "DIM_Provincia"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "nombre", name="UQ_Provincia_Pais_Nombre"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class Municipio(Base):
    """Municipios — división administrativa de segundo nivel, hijos de Provincia."""
    __tablename__ = "DIM_Municipio"
    __table_args__ = (
        UniqueConstraint("provincia_id", "nombre", name="UQ_Municipio_Provincia_Nombre"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    provincia_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Provincia.id"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CentroMedico(Base):
    """Centros médicos / clínicas / consultorios donde ejerce el médico."""
    __tablename__ = "DIM_CentroMedico"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "nombre", name="UQ_CentroMedico_Pais_Nombre"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    provincia_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Provincia.id"), nullable=True)
    municipio_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Municipio.id"), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


# ═══════════════════════════════════════════════════════════════════════════════
# CÓDIGO MUERTO — Categorización Médica v1.0 (Config schema)
# Sustituido en jun-2026 por cat_models.py (esquemas cat.* / stg.*).
# Estas clases NO se usan en ningún endpoint activo.
# No eliminar hasta confirmar que la migración cat001 se aplicó y los datos
# de Config.DIM_CategoriaMedica ya no son necesarios.
# ═══════════════════════════════════════════════════════════════════════════════
class CategoriaMedica(Base):
    """Categorías A/B/C/D (+ PENDIENTE) de clasificación médica por score_total.

    Mismo patrón que DIM_CategoriaDesempeno: catálogo global parametrizable
    (codigo/nombre/rango/color), sin FK a país — los rangos aplican igual
    en todos los países salvo que el negocio decida lo contrario.

    score_min/score_max son nullable (REVISADO) para soportar la fila
    catálogo 'PENDIENTE': representa "datos insuficientes para categorizar"
    (los 5 criterios sin capturar), no un rango de score — por lo tanto no
    tiene rango numérico y nunca debe poder ser encontrada por
    obtener_categoria_por_score() (un score_total real nunca compara
    verdadero contra NULL). Ver categorizacion_service.calcular_score().
    """
    __tablename__ = "DIM_CategoriaMedica"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(10), unique=True, nullable=False)  # A | B | C | D | PENDIENTE
    nombre: Mapped[str] = mapped_column(String(100), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(Text, nullable=True)
    score_min: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    score_max: Mapped[Decimal | None] = mapped_column(Numeric(6, 4), nullable=True)
    color_dashboard: Mapped[str | None] = mapped_column(String(30), nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)


class CriterioCategoria(Base):
    """Los 5 criterios ponderados del Motor de Cálculo de Categorización.

    codigo: PACIENTES_SEMANA | PODER_ADQUISITIVO | POTENCIAL_PRESCRIPCION |
            UBICACION_TERRITORIAL | KOL
    tipo_valor: NUMERICO (compara rango_desde/rango_hasta en DIM_CriterioCategoriaTabla)
              | ETIQUETA (compara contra el campo `etiqueta`, ej. KOL/Ubicación)
    peso: fracción decimal (0.30, 0.20, 0.10, 0.30, 0.10 — suman 1.0)
    """
    __tablename__ = "DIM_CriterioCategoria"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    nombre: Mapped[str] = mapped_column(String(150), nullable=False)
    tipo_valor: Mapped[str] = mapped_column(String(20), nullable=False, default="NUMERICO")
    peso: Mapped[Decimal] = mapped_column(Numeric(5, 4), nullable=False, default=Decimal("0"))
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    tablas: Mapped[list["CriterioCategoriaTabla"]] = relationship("CriterioCategoriaTabla", back_populates="criterio")


class CriterioCategoriaTabla(Base):
    """Tabla unificada de niveles (1-5) por criterio, parametrizada por país.

    Soporta los dos tipos de criterio del Excel de referencia en una sola
    tabla (mismo patrón que DIM_IndicadorTabla pero con un campo adicional
    `etiqueta` para los criterios tipo ETIQUETA):
      - NUMERICO: usa rango_desde/rango_hasta (ambos límites inclusivos),
        ej. Pacientes/Semana 6-10 → nivel 2.
      - ETIQUETA: usa `etiqueta` (comparación case-insensitive contra el
        valor capturado), ej. KOL "Director de Clínica" → nivel 3.

    pais_codigo es NULL cuando el rango aplica a todos los países (caso de
    Pacientes/Semana, Potencial de Prescripción, KOL y Ubicación en el
    Excel de referencia); solo Poder Adquisitivo (Costo de Consulta) tiene
    rangos específicos por país (ej. República Dominicana en RD$).
    Resolución: buscar primero (criterio_id, pais_codigo) específico, si no
    hay match usar (criterio_id, pais_codigo=NULL).
    """
    __tablename__ = "DIM_CriterioCategoriaTabla"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    criterio_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_CriterioCategoria.id"), nullable=False)
    pais_codigo: Mapped[str | None] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=True)
    rango_desde: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    rango_hasta: Mapped[Decimal | None] = mapped_column(Numeric(12, 4), nullable=True)
    etiqueta: Mapped[str | None] = mapped_column(String(100), nullable=True)
    nivel: Mapped[int] = mapped_column(Integer, nullable=False)  # 1-5
    descripcion: Mapped[str | None] = mapped_column(String(150), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    criterio: Mapped["CriterioCategoria"] = relationship("CriterioCategoria", back_populates="tablas")


class Medico(Base):
    """Médicos — universo objetivo de DOS módulos distintos que comparten
    esta misma tabla (fusión decidida jun-2026, ver dims.py DIM_MEDICOCOBERTURA):

    1) Categorización Médica (Excel propio, sin código estable): identidad
       por (pais_codigo, nombre, centro_medico_id) — `centro_medico_nombre` es
       obligatorio en este flujo porque nombres genéricos de médico
       residente ("Residencia Medicina Interna", etc.) se repiten en
       centros distintos y colapsarían en un registro si el centro no
       formara parte de la llave. Ver categorizacion_service.resolver_medico().

    2) Cobertura Predictiva/4DX, hoja DIM_MEDICOCOBERTURA: SÍ trae un
       código de médico estable (MEDICO_ID → columna `codigo`). Identidad
       por (pais_codigo, codigo); no captura centro médico, por lo que
       `centro_medico_id` queda NULL para estas filas. Ver
       categorizacion_service.resolver_medico_por_codigo().

    Dedup (REVISADO jun-2026): por eso `centro_medico_id` ahora es NULLABLE y
    la unicidad se implementa con DOS ÍNDICES ÚNICOS:
      - `UQ_Medico_Pais_Codigo`        ON (pais_codigo, codigo)
      - `UQ_Medico_Pais_Nombre_Centro` ON (pais_codigo, nombre, centro_medico_id)
    En PostgreSQL un índice único trata múltiples NULL como DISTINTOS, así que
    cada universo (con `codigo` o con `centro_medico_id` en NULL) convive sin
    colisionar sin necesidad de índices filtrados.
    """
    __tablename__ = "DIM_Medico"
    __table_args__ = (
        Index("UQ_Medico_Pais_Codigo", "pais_codigo", "codigo", unique=True),
        Index("UQ_Medico_Pais_Nombre_Centro", "pais_codigo", "nombre", "centro_medico_id", unique=True),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    codigo: Mapped[str | None]          = mapped_column(String(50),  nullable=True, index=True)
    nombre: Mapped[str]                 = mapped_column(String(200), nullable=False)
    especialidad_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Especialidad.id"), nullable=True, index=True)
    centro_medico_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_CentroMedico.id"), nullable=True, index=True)
    provincia_id: Mapped[int | None]    = mapped_column(Integer, ForeignKey("Config.DIM_Provincia.id"), nullable=True)
    municipio_id: Mapped[int | None]    = mapped_column(Integer, ForeignKey("Config.DIM_Municipio.id"), nullable=True)
    cedula: Mapped[str | None]          = mapped_column(String(30),  nullable=True)
    email: Mapped[str | None]           = mapped_column(String(200), nullable=True)
    activo: Mapped[bool]                = mapped_column(Boolean, nullable=False, default=True, server_default="1")

    # --- Maestro de Médicos (jul-2026): datos generales que antes vivían
    #     duplicados en Visita.DIM_MedicoVisita. Ver plan maestro-medicos. ---
    telefono: Mapped[str | None]     = mapped_column(String(40),  nullable=True)
    direccion: Mapped[str | None]    = mapped_column(String(300), nullable=True)
    sector: Mapped[str | None]       = mapped_column(String(100), nullable=True)
    exequatur: Mapped[str | None]    = mapped_column(String(50),  nullable=True, index=True)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # APROBADO (creado/validado por Admin/Supervisor o Excel) | PENDIENTE (creado desde Panel por un rep)
    estado_validacion: Mapped[str]   = mapped_column(String(16), nullable=False, default="APROBADO", server_default="APROBADO")
    # MANUAL | EXCEL | PANEL | CATEGORIZACION | COBERTURA
    origen: Mapped[str]              = mapped_column(String(16), nullable=False, default="MANUAL", server_default="MANUAL")
    created_at: Mapped[datetime]     = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))


class ParametroSistema(Base):
    """Parámetros de sistema clave-valor, editables en runtime (sin reiniciar).
    Ej.: EXAMEN_IA_DEMO ('true'/'false') para alternar la generación de exámenes
    entre el modo DEMO (local, sin gastar API) y la IA real de Claude."""
    __tablename__ = "DIM_Parametro"
    __table_args__ = {"schema": "Config"}

    clave: Mapped[str] = mapped_column(String(80), primary_key=True)
    valor: Mapped[str] = mapped_column(String(400), nullable=False)
    actualizado: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class CatalogoError(Base):
    """Matriz de errores del sistema: catálogo mantenible (Administración) que documenta cada
    error con su descripción, causa probable y solución, para que se entienda qué está pasando.
    `codigo` es la llave estable que la app puede mostrar/relacionar con un mensaje amigable."""
    __tablename__ = "DIM_CatalogoError"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    codigo: Mapped[str] = mapped_column(String(40), unique=True, nullable=False, index=True)
    titulo: Mapped[str] = mapped_column(String(160), nullable=False)
    descripcion: Mapped[str | None] = mapped_column(String(600), nullable=True)
    causa: Mapped[str | None] = mapped_column(String(600), nullable=True)
    solucion: Mapped[str | None] = mapped_column(String(600), nullable=True)
    categoria: Mapped[str | None] = mapped_column(String(60), nullable=True)   # Validación/Sistema/Permisos/Datos…
    http_status: Mapped[int | None] = mapped_column(Integer, nullable=True)     # 400/403/409/500…
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="1")


class Farmacia(Base):
    """Maestro único de farmacias (país-level). Los paneles de VM referencian aquí (F19)."""
    __tablename__ = "DIM_Farmacia"
    __table_args__ = (
        Index("IX_Farmacia_cadena_sucursal", "pais_codigo", "cadena", "sucursal"),
        Index("IX_Farmacia_estado", "estado"),
        {"schema": "Config"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    es_cadena: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    cadena: Mapped[str | None] = mapped_column(String(120), nullable=True)
    sucursal: Mapped[str | None] = mapped_column(String(120), nullable=True)
    nombre: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nombre_completo: Mapped[str] = mapped_column(String(250), nullable=False, default="")
    direccion: Mapped[str] = mapped_column(String(300), nullable=False)     # F23 bloqueante
    provincia: Mapped[str | None] = mapped_column(String(100), nullable=True)
    municipio: Mapped[str | None] = mapped_column(String(100), nullable=True)
    sector: Mapped[str | None] = mapped_column(String(100), nullable=True)
    latitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    longitud: Mapped[float | None] = mapped_column(Numeric(10, 7), nullable=True)
    encargado: Mapped[str] = mapped_column(String(200), nullable=False)     # F24 bloqueante
    telefono: Mapped[str | None] = mapped_column(String(40), nullable=True)
    email: Mapped[str | None] = mapped_column(String(200), nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="PENDIENTE_APROBACION")
    origen: Mapped[str] = mapped_column(String(12), nullable=False, default="VM")   # VM | CONFIG
    solicitado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    aprobado_por: Mapped[int | None] = mapped_column(Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_solicitud: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    fecha_aprobacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    motivo_rechazo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime, default=lambda: datetime.now(timezone.utc),
                                                 onupdate=lambda: datetime.now(timezone.utc))


class FuenteIndicador(Base):
    """Quién alimenta un indicador en un país. Hoy solo se usa para
    EVAL_CONOCIMIENTOS, que tiene tres caminos posibles y hasta ahora se los
    disputaban en silencio: los tres hacen delete-then-insert, así que ganaba
    el último en correr.

    Es por PAÍS y no por ciclo a propósito: la elección entre exámenes de VISTA,
    notas de Mallén y captura manual es una política que se toma una vez, no
    algo que alterne entre ciclos.
    """
    __tablename__ = "FuenteIndicador"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "indicador_codigo",
                         name="UQ_FuenteIndicador_clave"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    indicador_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    #: EXAMEN_VISTA | NOTA_EXTERNA | CAPTURA_MANUAL — EXCEL no es una fuente
    fuente: Mapped[str] = mapped_column(String(20), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    actualizado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
