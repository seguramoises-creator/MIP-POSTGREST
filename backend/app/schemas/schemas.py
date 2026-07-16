"""
SCGCPR — Schemas Pydantic v2 para todos los módulos
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict, Field


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class UsuarioCreate(BaseModel):
    username: str
    # Email OPCIONAL: si se envía debe ser válido; vacío/espacios → None (sin correo).
    email: Optional[EmailStr] = None
    password: str
    nombre_completo: str
    rol: str
    pais_codigo: Optional[str] = None
    rm_id: Optional[int] = None
    gerente_id: Optional[int] = None

    @field_validator("email", mode="before")
    @classmethod
    def _email_vacio_a_none(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: Optional[str] = None
    nombre_completo: str
    rol: str
    pais_codigo: Optional[str]
    rm_id: Optional[int] = None
    gerente_id: Optional[int] = None
    activo: bool
    bloqueado: bool = False          # cuenta bloqueada ahora (bloqueado_hasta futuro)
    ultimo_login: Optional[datetime]
    debe_cambiar_password: bool = False
    password_expira_en_dias: Optional[int] = None

class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[str] = None
    activo: Optional[bool] = None
    pais_codigo: Optional[str] = None
    rm_id: Optional[int] = None
    gerente_id: Optional[int] = None

    @field_validator("email", mode="before")
    @classmethod
    def _email_vacio_a_none(cls, v):
        if v is None:
            return None
        s = str(v).strip()
        return s or None

class PasswordChange(BaseModel):
    password_actual: str
    password_nuevo: str
    # La complejidad se valida en el endpoint (depende del rol + BD, ver
    # password_policy_service.validar_complejidad), no en el schema.


class ForgotPassword(BaseModel):
    """Paso 1 de recuperación: el usuario indica su correo."""
    email: EmailStr


class ResetPassword(BaseModel):
    """Paso 2 de recuperación: correo + código recibido + nueva contraseña."""
    email: EmailStr
    codigo: str
    password_nuevo: str


class AdminSetPassword(BaseModel):
    """Restablecimiento de contraseña por un ADMIN desde Administración de Usuarios."""
    password_nuevo: str


class CorreoConfig(BaseModel):
    """Configuración del servidor SMTP (editable por ADMIN desde el sistema)."""
    server: str = ""
    port: int = 587
    username: str = ""
    password: Optional[str] = None   # None/"" = no cambiar la existente
    from_email: str = ""
    from_name: str = ""
    tls: bool = True
    ssl: bool = False


class CorreoTest(BaseModel):
    email: EmailStr


# ── Catálogos ─────────────────────────────────────────────────────────────────

class PaisCreate(BaseModel):
    codigo: str
    nombre: str
    moneda: Optional[str] = None
    zona_horaria: Optional[str] = None

class PaisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    moneda: Optional[str]
    activo: bool

class LineaCreate(BaseModel):
    pais_codigo: str
    codigo: str
    nombre: str
    descripcion: Optional[str] = None

class LineaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    codigo: str
    nombre: str
    activo: bool

class GerenteCreate(BaseModel):
    pais_codigo: str
    linea_id: Optional[int] = None
    codigo: str
    nombre: str
    email: Optional[str] = None
    tipo: str  # DISTRITO | MARCA | REGIONAL
    fecha_ingreso: Optional[date] = None

class GerenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    linea_id: Optional[int] = None
    codigo: str
    nombre: str
    email: Optional[str] = None
    tipo: str
    fecha_ingreso: Optional[date] = None
    activo: bool

class RMCreate(BaseModel):
    pais_codigo: str
    linea_id: int
    gerente_id: Optional[int] = None
    codigo: str
    nombre: str
    cedula: Optional[str] = None
    email: Optional[str] = None
    zona: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    coaching_min_dia: int = Field(default=5, ge=1, le=9)

class RMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    linea_id: int
    gerente_id: Optional[int]
    codigo: str
    nombre: str
    cedula: Optional[str]
    email: Optional[str] = None
    zona: Optional[str] = None
    fecha_ingreso: Optional[date] = None
    coaching_min_dia: int = 5
    activo: bool


# ── Productos (DIM_Producto) ────────────────────────────────────────────────────
class ProductoCreate(BaseModel):
    codigo: str
    nombre: str
    area_terapeutica: Optional[str] = None
    descripcion: Optional[str] = None
    segmento_target: Optional[str] = None
    meta_muestras_visita: int = 1
    gerente_producto: Optional[str] = None
    linea_id: Optional[int] = None

class ProductoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    area_terapeutica: Optional[str] = None
    descripcion: Optional[str] = None
    segmento_target: Optional[str] = None
    meta_muestras_visita: int
    gerente_producto: Optional[str] = None
    linea_id: Optional[int] = None
    pais_codigo: Optional[str] = None
    activo: bool


# ── Indicadores ───────────────────────────────────────────────────────────────

class IndicadorCreate(BaseModel):
    pais_codigo: str
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    rol: str = "RM"
    modulo: str                          # GESTION | RESULTADOS
    tipo_periodo: str = "CICLO"          # CICLO | MES
    ponderacion_pct: int = 0             # 0-100
    escala: int = 1                      # 1 (%) ó 100 (puntos directos)
    valor_min: Optional[Decimal] = None
    valor_max: Optional[Decimal] = None
    formula: Optional[str] = None
    peso_iup: Decimal = Decimal("0")
    unidad: Optional[str] = None
    meta_global: Optional[Decimal] = None
    orden: int = 0

class IndicadorResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    codigo: str
    nombre: str
    rol: str
    modulo: str
    tipo_periodo: str
    ponderacion_pct: int
    escala: int
    valor_min: Optional[Decimal]
    valor_max: Optional[Decimal]
    peso_iup: Decimal
    activo: bool

class IndicadorTablaCreate(BaseModel):
    indicador_id: int
    pais_codigo: str
    rango_desde: Decimal
    rango_hasta: Decimal
    puntos: Decimal
    descripcion: Optional[str] = None

class IndicadorTablaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    indicador_id: int
    pais_codigo: str
    rango_desde: Decimal
    rango_hasta: Decimal
    puntos: Decimal


# ── Ciclos y Períodos ─────────────────────────────────────────────────────────

class CicloCreate(BaseModel):
    pais_codigo: str
    anio: int
    numero: int
    nombre: str
    nombre_canonico: Optional[str] = None   # CICLO-01-2026
    fecha_inicio: date
    fecha_fin: date
    dias_laborables: int = 0

class CicloUpdate(BaseModel):
    """Edición de un ciclo. `dias_laborables` NO se recibe: se recalcula en el backend
    a partir de fecha_inicio/fecha_fin y los feriados del país."""
    anio: Optional[int] = None
    numero: Optional[int] = None
    nombre: Optional[str] = None
    nombre_canonico: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None

class CicloResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    anio: int
    numero: int
    nombre: str
    nombre_canonico: Optional[str]
    fecha_inicio: date
    fecha_fin: date
    dias_laborables: int
    cerrado: bool
    activo: bool
    estado: str = "VIGENTE"      # PLANIFICADO | VIGENTE | POR_CERRAR | CERRADO
    vencido: bool = False        # abierto pero con fecha fin ya pasada


class FeriadoIn(BaseModel):
    pais_codigo: str
    fecha: date
    nombre: Optional[str] = None

class FeriadoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    fecha: date
    nombre: Optional[str]
    activo: bool


# ── Productividad ─────────────────────────────────────────────────────────────

class KPIProductividadResponse(BaseModel):
    rm_id: int
    rm_codigo: str
    rm_nombre: str
    pais_codigo: str
    ciclo_id: int
    cobertura_f1: Optional[Decimal] = None
    cobertura_f2: Optional[Decimal] = None
    cobertura_farmacias: Optional[Decimal] = None
    promedio_diario: Optional[Decimal] = None
    puntaje_productividad: Optional[Decimal] = None


# ── IUP ──────────────────────────────────────────────────────────────────────

class IUPResponse(BaseModel):
    rm_id: int
    rm_nombre: str
    iup_total: Decimal
    iup_productividad: Decimal
    iup_comercial: Decimal
    iup_coaching: Decimal
    iup_capacitacion: Decimal
    iup_consistencia: Decimal
    ciclo_id: int
    elegible: bool


# ── Coaching ─────────────────────────────────────────────────────────────────

class CoachingCreate(BaseModel):
    pais_codigo: str
    gerente_id: int
    rm_id: int
    ciclo_id: int
    tipo: str
    coaching_programado: int
    coaching_ejecutado: int
    calificacion_calidad: Decimal
    peso_cantidad: Decimal = Decimal("0.7")
    peso_calidad: Decimal = Decimal("0.3")
    fecha_coaching: Optional[date] = None
    observaciones: Optional[str] = None

class CoachingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rm_id: int
    gerente_id: int
    ciclo_id: int
    tipo: str
    coaching_programado: int
    coaching_ejecutado: int
    cumplimiento_pct: Decimal
    calificacion_calidad: Decimal
    resultado_coaching: Decimal
    puntaje: Decimal


# ── Capacitación ─────────────────────────────────────────────────────────────

class CapacitacionCreate(BaseModel):
    pais_codigo: str
    rm_id: int
    capacitacion_id: int
    ciclo_id: int
    asistio: bool = False
    calificacion: Optional[Decimal] = None
    horas_completadas: Decimal = Decimal("0")
    fecha_actividad: Optional[date] = None

class CapacitacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rm_id: int
    capacitacion_id: int
    ciclo_id: int
    asistio: bool
    calificacion: Optional[Decimal]
    aprobado: bool
    horas_completadas: Decimal
    puntaje: Decimal


# ── Categorización Médica (sustituye a Capacitación, ver admin.py) ───────────
# Mantenimiento de Categorías (DIM_CategoriaMedica) y Mantenimiento de
# Parámetros (DIM_CriterioCategoria + DIM_CriterioCategoriaTabla), mismo
# patrón que Indicador/IndicadorTabla.

class CategoriaMedicaCreate(BaseModel):
    codigo: str                          # A | B | C | D
    nombre: str
    descripcion: Optional[str] = None
    score_min: Decimal
    score_max: Decimal
    color_dashboard: Optional[str] = None
    orden: int = 0

class CategoriaMedicaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    descripcion: Optional[str]
    score_min: Decimal
    score_max: Decimal
    color_dashboard: Optional[str]
    orden: int
    activo: bool

class CriterioCategoriaCreate(BaseModel):
    codigo: str                          # PACIENTES_SEMANA | PODER_ADQUISITIVO | ...
    nombre: str
    tipo_valor: str = "NUMERICO"         # NUMERICO | ETIQUETA
    peso: Decimal = Decimal("0")
    orden: int = 0

class CriterioCategoriaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    tipo_valor: str
    peso: Decimal
    orden: int
    activo: bool

class CriterioCategoriaTablaCreate(BaseModel):
    criterio_id: int
    pais_codigo: Optional[str] = None        # NULL = aplica a todos los países
    rango_desde: Optional[Decimal] = None
    rango_hasta: Optional[Decimal] = None
    etiqueta: Optional[str] = None
    nivel: int                           # 1-5
    descripcion: Optional[str] = None

class CriterioCategoriaTablaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    criterio_id: int
    pais_codigo: Optional[str]
    rango_desde: Optional[Decimal]
    rango_hasta: Optional[Decimal]
    etiqueta: Optional[str]
    nivel: int
    descripcion: Optional[str]
    activo: bool


# ── Ranking ───────────────────────────────────────────────────────────────────

class RankingResponse(BaseModel):
    """Refleja FACT_RankingRM (rediseño jun-2026, antes FACT_Ranking).
    Los componentes iup_* por módulo ya no se persisten aquí — se
    calculan dinámicamente desde FACT_ResultadoIndicador (ver iup_service)."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    rm_id: int
    pais_codigo: str
    tipo_ranking: str
    score_total: Decimal
    categoria_id: Optional[int]
    posicion_global: int
    posicion_linea: Optional[int]
    posicion_anterior: Optional[int]
    elegible: bool
    fecha_generacion: datetime

class RankingRequest(BaseModel):
    pais_codigo: str
    ciclo_id: Optional[int] = None
    tipo_ranking: str = "MENSUAL"  # MENSUAL | TRIMESTRAL | ANUAL | REGIONAL


# ── Reconocimiento ────────────────────────────────────────────────────────────

class ReconocimientoCreate(BaseModel):
    pais_codigo: str
    premio_id: int
    rm_id: Optional[int] = None
    gerente_id: Optional[int] = None
    ciclo_id: Optional[int] = None
    aprobado_por: Optional[str] = None
    observaciones: Optional[str] = None

class ReconocimientoResponse(BaseModel):
    """Refleja FACT_ReconocimientoRM (rediseño jun-2026, antes FACT_Reconocimiento).
    `iup_al_momento`/`fecha_reconocimiento` se renombraron a
    `score_total`/`fecha_calculo` para alinearse con el resto del modelo nuevo."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    premio_id: int
    rm_id: Optional[int]
    gerente_id: Optional[int]
    score_total: Decimal
    posicion_linea: Optional[int]
    posicion_ranking: Optional[int]
    certificado_generado: bool
    certificado_url: Optional[str]
    fecha_calculo: datetime

class PremioCreate(BaseModel):
    codigo: str
    nombre: str
    descripcion: Optional[str] = None
    categoria: str
    frecuencia: str

class PremioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    codigo: str
    nombre: str
    categoria: str
    frecuencia: str
    activo: bool


# ── Elegibilidad ──────────────────────────────────────────────────────────────

class ElegibilidadResponse(BaseModel):
    rm_id: int
    rm_nombre: str
    pais_codigo: str
    ciclo_id: int
    elegible: bool
    estado: str  # ELEGIBLE | NO_ELEGIBLE | CONDICIONADO
    reglas_evaluadas: List[dict]


# ── Dashboard ─────────────────────────────────────────────────────────────────

class KPIEjecutivoResponse(BaseModel):
    pais_codigo: Optional[str]
    iup_regional: Decimal
    total_rms: int
    rms_elegibles: int
    pct_elegibles: Decimal
    top_rm: Optional[dict]
    top_pais: Optional[dict]
    iup_productividad_promedio: Decimal
    iup_comercial_promedio: Decimal
    iup_coaching_promedio: Decimal
    iup_capacitacion_promedio: Decimal
    periodo: str


# ── ETL ───────────────────────────────────────────────────────────────────────

class ETLJobResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre_archivo: str
    tipo_archivo: str
    modo: str
    estado: str
    total_filas: int
    filas_exitosas: int
    filas_error: int
    filas_advertencia: int
    duracion_segundos: Optional[Decimal]
    fecha_inicio: datetime
    fecha_fin: Optional[datetime]

class ETLJobStatus(BaseModel):
    job_id: int
    estado: str
    progreso_pct: int
    mensaje: str


# ── Reglas de Elegibilidad ────────────────────────────────────────────────────

class ReglaElegibilidadCreate(BaseModel):
    pais_codigo: str
    ciclo_id: Optional[int] = None
    nombre: str
    indicador_codigo: str
    umbral_minimo: Decimal
    aplica_ranking: bool = True
    aplica_reconocimiento: bool = True

class ReglaElegibilidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    nombre: str
    indicador_codigo: str
    umbral_minimo: Decimal
    aplica_ranking: bool
    aplica_reconocimiento: bool
    activo: bool


# ── LSII (Matriz de Desarrollo) ────────────────────────────────────────────
# Importante: estos schemas NUNCA exponen score_oculto ni peso_dimension al
# evaluador (GD). Solo viajan dimension_nombre/dimension_descripcion y
# texto_comportamiento — el cálculo ocurre 100% en el backend.

class ReceptividadOpcionPublic(BaseModel):
    """Una opción de comportamiento observable, tal como la ve el GD."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    orden_opcion: int
    texto_comportamiento: str

class ReceptividadDimensionPublic(BaseModel):
    """Una dimensión de receptividad con sus 5 opciones de comportamiento."""
    dimension_codigo: str
    dimension_nombre: str
    dimension_descripcion: Optional[str] = None
    orden_dimension: int
    opciones: List[ReceptividadOpcionPublic]

class SeleccionReceptividadIn(BaseModel):
    """Selección del GD para una dimensión: solo indica qué opción eligió."""
    dimension_codigo: str
    opcion_id: int

class EvaluacionLsiiCreate(BaseModel):
    pais_codigo: str
    rm_id: int
    ciclo_id: int
    gerente_id: Optional[int] = None
    observaciones: Optional[str] = None
    selecciones: List[SeleccionReceptividadIn]

    @field_validator("selecciones")
    @classmethod
    def validar_selecciones(cls, v: List[SeleccionReceptividadIn]) -> List[SeleccionReceptividadIn]:
        # El número exacto de dimensiones ya no está fijo en 5: un ADMIN puede
        # agregar/quitar dimensiones desde la pantalla de administración. La
        # validación de "una selección por cada dimensión activa" se hace en
        # lsii_service.registrar_evaluacion contra el catálogo vigente en BD.
        if len(v) == 0:
            raise ValueError("Debe seleccionar al menos un comportamiento")
        codigos = [s.dimension_codigo for s in v]
        if len(set(codigos)) != len(codigos):
            raise ValueError("Cada dimensión debe tener una sola selección")
        return v

class EvaluacionLsiiResponse(BaseModel):
    """Resultado de una evaluación LSII — nunca incluye score_oculto/peso_dimension."""
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    rm_id: int
    gerente_id: Optional[int]
    ciclo_id: int
    score_receptividad: Decimal
    score_desempeno: Optional[Decimal]
    nivel_lsii: str             # D1 | D2 | D3 | D4
    estilo_liderazgo: str       # Dirigir | Entrenar | Apoyar | Delegar
    observaciones: Optional[str]
    fecha_evaluacion: datetime

class MatrizLsiiItem(BaseModel):
    """Un punto de la matriz LSII (eje X=receptividad, eje Y=desempeño)."""
    rm_id: int
    rm_codigo: Optional[str] = None
    rm_nombre: str
    pais_codigo: str
    gerente_id: Optional[int] = None
    ciclo_id: int
    score_desempeno: Decimal      # eje Y
    score_receptividad: Decimal   # eje X
    nivel_lsii: str
    estilo_liderazgo: str
    fecha_evaluacion: datetime


# ── LSII — Administración (matriz y puntos editables desde la app) ────────
# A diferencia de los schemas públicos de arriba, estos SÍ incluyen
# score_oculto y peso_dimension. Solo se usan en los endpoints /lsii/admin/*
# protegidos con RequireAdmin (ADMIN, GERENTE_PRODUCTIVIDAD) — nunca en
# /lsii/catalogo (pantalla de evaluación del GD).

class ReceptividadOpcionAdmin(BaseModel):
    """Una opción de comportamiento — vista/edición completa para administración."""
    model_config = ConfigDict(from_attributes=True)
    id: Optional[int] = None
    orden_opcion: int = Field(..., ge=1)
    texto_comportamiento: str = Field(..., min_length=1)
    score_oculto: int = Field(..., ge=1, le=10)
    activo: bool = True

class ReceptividadDimensionAdmin(BaseModel):
    """Una dimensión completa de receptividad (catálogo + puntaje), para admin."""
    model_config = ConfigDict(from_attributes=True)
    dimension_codigo: str
    dimension_nombre: str
    dimension_descripcion: Optional[str] = None
    orden_dimension: int
    peso_dimension: Decimal
    activo: bool = True
    opciones: List[ReceptividadOpcionAdmin]

class DimensionLsiiUpsert(BaseModel):
    """Payload para crear o actualizar una dimensión completa con sus opciones.

    Si `dimension_codigo` ya existe en Config.DIM_ReceptividadOpcion, se
    actualizan nombre/descripción/orden/peso y se sincronizan las opciones
    (upsert por `orden_opcion`: las existentes se actualizan, las nuevas se
    insertan). Las opciones que ya no vienen en el payload se desactivan
    (activo=False) en vez de borrarse, para no romper el historial de
    evaluaciones ya registradas (FACT_EvaluacionReceptividadDetalle.opcion_id).
    Si `dimension_codigo` no existe, se crea como dimensión nueva.
    """
    dimension_codigo: str = Field(..., min_length=1, max_length=50)
    dimension_nombre: str = Field(..., min_length=1, max_length=200)
    dimension_descripcion: Optional[str] = None
    orden_dimension: int = Field(..., ge=1)
    peso_dimension: Decimal = Field(..., gt=0, le=1)
    opciones: List[ReceptividadOpcionAdmin] = Field(..., min_length=2)

    @field_validator("opciones")
    @classmethod
    def validar_opciones(cls, v: List[ReceptividadOpcionAdmin]) -> List[ReceptividadOpcionAdmin]:
        ordenes = [o.orden_opcion for o in v]
        if len(set(ordenes)) != len(ordenes):
            raise ValueError("orden_opcion debe ser único dentro de la misma dimensión")
        return v

class OpcionLsiiUpdate(BaseModel):
    """Edición puntual de una sola opción existente (texto, score o estado)."""
    texto_comportamiento: Optional[str] = Field(None, min_length=1)
    score_oculto: Optional[int] = Field(None, ge=1, le=10)
    activo: Optional[bool] = None

class ConfiguracionLsiiPublic(BaseModel):
    """Umbral de corte D1-D4 vigente."""
    model_config = ConfigDict(from_attributes=True)
    corte_desempeno: Decimal
    corte_receptividad: Decimal
    actualizado_en: datetime
    actualizado_por: Optional[str] = None

class ConfiguracionLsiiUpdate(BaseModel):
    """Nuevo umbral de corte para los cuadrantes D1-D4 (eje Y / eje X, 0-100)."""
    corte_desempeno: Decimal = Field(..., gt=0, le=100)
    corte_receptividad: Decimal = Field(..., gt=0, le=100)


# ── Maestro de Médicos ──────────────────────────────────────────────────────
class MaestroMedicoBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=200)
    codigo: str | None = Field(None, max_length=50)
    cedula: str | None = Field(None, max_length=30)
    exequatur: str | None = Field(None, max_length=50)
    especialidad_id: int | None = None
    telefono: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=200)
    direccion: str | None = Field(None, max_length=300)
    provincia_id: int | None = None
    municipio_id: int | None = None
    centro_medico_id: int | None = None
    sector: str | None = Field(None, max_length=100)
    observaciones: str | None = Field(None, max_length=500)
    activo: bool = True


class MaestroMedicoCrear(MaestroMedicoBase):
    pais_codigo: str = Field(..., max_length=10)
    confirmar_duplicado: bool = False


class MaestroMedicoActualizar(BaseModel):
    nombre: str | None = Field(None, min_length=2, max_length=200)
    codigo: str | None = None
    cedula: str | None = None
    exequatur: str | None = None
    especialidad_id: int | None = None
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    provincia_id: int | None = None
    municipio_id: int | None = None
    centro_medico_id: int | None = None
    sector: str | None = None
    observaciones: str | None = None
    activo: bool | None = None


class MaestroMedicoResponse(MaestroMedicoBase):
    id: int
    pais_codigo: str
    estado_validacion: str
    origen: str
    model_config = ConfigDict(from_attributes=True)


class MaestroMedicoDuplicados(BaseModel):
    tipo: str  # "duro" | "blando"
    mensaje: str
    coincidencias: list[dict]
