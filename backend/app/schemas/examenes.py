from datetime import datetime
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
