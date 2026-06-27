"""
SCGCPR — Schemas Pydantic v2 para todos los módulos
"""
from datetime import datetime, date
from decimal import Decimal
from typing import Optional, List
from pydantic import BaseModel, EmailStr, field_validator, ConfigDict


# ── Auth ─────────────────────────────────────────────────────────────────────

class LoginRequest(BaseModel):
    username: str
    password: str

class UsuarioCreate(BaseModel):
    username: str
    email: EmailStr
    password: str
    nombre_completo: str
    rol: str
    pais_id: Optional[int] = None
    rm_id: Optional[int] = None

class UsuarioResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    username: str
    email: str
    nombre_completo: str
    rol: str
    pais_id: Optional[int]
    activo: bool
    ultimo_login: Optional[datetime]

class UsuarioUpdate(BaseModel):
    nombre_completo: Optional[str] = None
    email: Optional[EmailStr] = None
    rol: Optional[str] = None
    activo: Optional[bool] = None
    pais_id: Optional[int] = None

class PasswordChange(BaseModel):
    password_actual: str
    password_nuevo: str

    @field_validator("password_nuevo")
    @classmethod
    def validate_password(cls, v: str) -> str:
        if len(v) < 12:
            raise ValueError("La contraseña debe tener al menos 12 caracteres")
        if not any(c.isupper() for c in v):
            raise ValueError("Debe contener al menos una mayúscula")
        if not any(c.islower() for c in v):
            raise ValueError("Debe contener al menos una minúscula")
        if not any(c.isdigit() for c in v):
            raise ValueError("Debe contener al menos un número")
        return v


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
    pais_id: int
    codigo: str
    nombre: str
    descripcion: Optional[str] = None

class LineaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    codigo: str
    nombre: str
    activo: bool

class GerenteCreate(BaseModel):
    pais_id: int
    linea_id: Optional[int] = None
    codigo: str
    nombre: str
    email: Optional[str] = None
    tipo: str  # DISTRITO | MARCA | REGIONAL

class GerenteResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    codigo: str
    nombre: str
    tipo: str
    activo: bool

class RMCreate(BaseModel):
    pais_id: int
    linea_id: int
    gerente_id: Optional[int] = None
    codigo: str
    nombre: str
    cedula: Optional[str] = None
    email: Optional[str] = None
    zona: Optional[str] = None
    fecha_ingreso: Optional[date] = None

class RMResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    linea_id: int
    gerente_id: Optional[int]
    codigo: str
    nombre: str
    cedula: Optional[str]
    activo: bool


# ── Indicadores ───────────────────────────────────────────────────────────────

class IndicadorCreate(BaseModel):
    pais_id: int
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
    pais_id: int
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
    pais_id: int
    rango_desde: Decimal
    rango_hasta: Decimal
    puntos: Decimal
    descripcion: Optional[str] = None

class IndicadorTablaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    indicador_id: int
    pais_id: int
    rango_desde: Decimal
    rango_hasta: Decimal
    puntos: Decimal


# ── Ciclos y Períodos ─────────────────────────────────────────────────────────

class CicloCreate(BaseModel):
    pais_id: int
    anio: int
    numero: int
    nombre: str
    nombre_canonico: Optional[str] = None   # CICLO-01-2026
    fecha_inicio: date
    fecha_fin: date
    dias_laborables: int = 0

class CicloResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    anio: int
    numero: int
    nombre: str
    nombre_canonico: Optional[str]
    fecha_inicio: date
    fecha_fin: date
    cerrado: bool
    activo: bool


# ── Productividad ─────────────────────────────────────────────────────────────

class KPIProductividadResponse(BaseModel):
    rm_id: int
    rm_codigo: str
    rm_nombre: str
    pais_id: int
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
    pais_id: int
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
    pais_id: int
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


# ── Ranking ───────────────────────────────────────────────────────────────────

class RankingResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    rm_id: int
    pais_id: int
    tipo_ranking: str
    iup_total: Decimal
    iup_productividad: Decimal
    iup_comercial: Decimal
    iup_coaching: Decimal
    iup_capacitacion: Decimal
    iup_consistencia: Decimal
    posicion: int
    posicion_anterior: Optional[int]
    elegible: bool
    fecha_generacion: datetime

class RankingRequest(BaseModel):
    pais_id: int
    ciclo_id: Optional[int] = None
    tipo_ranking: str = "MENSUAL"  # MENSUAL | TRIMESTRAL | ANUAL | REGIONAL


# ── Reconocimiento ────────────────────────────────────────────────────────────

class ReconocimientoCreate(BaseModel):
    pais_id: int
    premio_id: int
    rm_id: Optional[int] = None
    gerente_id: Optional[int] = None
    ciclo_id: Optional[int] = None
    aprobado_por: Optional[str] = None
    observaciones: Optional[str] = None

class ReconocimientoResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    premio_id: int
    rm_id: Optional[int]
    gerente_id: Optional[int]
    iup_al_momento: Decimal
    posicion_ranking: Optional[int]
    certificado_generado: bool
    certificado_url: Optional[str]
    fecha_reconocimiento: datetime

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
    pais_id: int
    ciclo_id: int
    elegible: bool
    estado: str  # ELEGIBLE | NO_ELEGIBLE | CONDICIONADO
    reglas_evaluadas: List[dict]


# ── Dashboard ─────────────────────────────────────────────────────────────────

class KPIEjecutivoResponse(BaseModel):
    pais_id: Optional[int]
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
    pais_id: int
    ciclo_id: Optional[int] = None
    nombre: str
    indicador_codigo: str
    umbral_minimo: Decimal
    aplica_ranking: bool = True
    aplica_reconocimiento: bool = True

class ReglaElegibilidadResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_id: int
    nombre: str
    indicador_codigo: str
    umbral_minimo: Decimal
    aplica_ranking: bool
    aplica_reconocimiento: bool
    activo: bool
