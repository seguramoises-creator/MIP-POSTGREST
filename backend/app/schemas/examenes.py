from datetime import datetime, date
from pydantic import BaseModel, ConfigDict, Field


class ExamenCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    producto: str | None = None
    nota_minima: int = Field(default=70, ge=0, le=100)
    tiempo_limite_min: int | None = Field(default=None, ge=1)
    rand_preguntas: bool = False
    rand_opciones: bool = False
    indicador_codigo: str | None = None
    ciclo_id: int | None = None


class ExamenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    producto: str | None
    nota_minima: int
    tiempo_limite_min: int | None
    estado: str
    fuente: str
    rand_preguntas: bool
    rand_opciones: bool
    indicador_codigo: str | None
    ciclo_id: int | None
    fecha_creacion: datetime
    fecha_publicacion: datetime | None


# ---------------------------------------------------------------------------
# Phase 2 schemas — Preguntas, Asignaciones, Intentos, Reportes
# ---------------------------------------------------------------------------


class PreguntaOpcionCrear(BaseModel):
    texto_opcion: str = Field(min_length=1)
    es_correcta: bool = False


class PreguntaCrear(BaseModel):
    tipo: str = Field(default="multi")  # multi | caso
    escenario: str | None = None
    texto: str = Field(min_length=1)
    explicacion: str | None = None
    opciones: list[PreguntaOpcionCrear] = Field(min_length=4, max_length=4)


class OpcionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    texto_opcion: str
    indice_original: int
    es_correcta: bool


class PreguntaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    examen_id: int
    tipo: str
    escenario: str | None
    texto: str
    explicacion: str | None
    orden: int


# EvaluadoRef must be defined BEFORE AsignacionCrear to avoid forward references
class EvaluadoRef(BaseModel):
    tipo: str  # RM | GERENTE
    id: int


class AsignacionCrear(BaseModel):
    examen_id: int
    evaluados: list[EvaluadoRef] = Field(min_length=1)
    fecha_limite: date | None = None
    intentos_max: int | None = Field(default=None, ge=1)
    notif_activa: bool = False


class AsignacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    examen_id: int
    evaluado_tipo: str
    evaluado_rm_id: int | None
    evaluado_gerente_id: int | None
    fecha_limite: datetime | None
    intentos_max: int | None
    intentos_usados: int
    estado: str


class OpcionPresentada(BaseModel):
    indice_presentado: int
    texto_opcion: str


class PreguntaPresentada(BaseModel):
    pregunta_id: int
    tipo: str
    escenario: str | None
    texto: str
    opciones: list[OpcionPresentada]


class IntentoIniciado(BaseModel):
    intento_id: int
    examen_nombre: str
    tiempo_limite_min: int | None
    preguntas: list[PreguntaPresentada]


class RespuestaEnviar(BaseModel):
    pregunta_id: int
    indice_presentado: int


class ReporteRespuesta(BaseModel):
    pregunta_texto: str
    explicacion: str | None
    indice_elegido_presentado: int | None
    texto_elegido: str | None
    texto_correcto: str
    es_correcta: bool


class ReporteIntento(BaseModel):
    intento_id: int
    examen_nombre: str
    producto: str | None
    score: float
    aprobado: bool
    nota_minima: int
    correctas: int
    total: int
    fecha_fin: datetime | None
    respuestas: list[ReporteRespuesta]
