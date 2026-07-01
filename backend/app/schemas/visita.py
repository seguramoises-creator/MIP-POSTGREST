"""Schemas del Módulo de Visita Médica — Fase 1 (Panel Médico)."""
from pydantic import BaseModel, ConfigDict, Field, field_validator


class MedicoVisitaCrear(BaseModel):
    vm_id: int
    nombre_completo: str = Field(min_length=3, max_length=200)
    especialidad_id: int | None = None
    categoria: str = Field(min_length=1, max_length=1)
    tipo_consultorio: str | None = None
    direccion: str | None = None
    telefono: str | None = None
    # Si el sistema detecta posible duplicado y el usuario decide registrar igual.
    confirmar_duplicado: bool = False

    @field_validator("nombre_completo")
    @classmethod
    def _nombre_valido(cls, v: str) -> str:
        v = " ".join(v.strip().upper().split())  # MAYÚSCULAS, espacios normalizados
        if "." in v:  # abreviaciones con punto (Dr. / M. / Manuel P.)
            raise ValueError("El nombre no debe llevar abreviaciones con punto (ej. Dr. o M.)")
        if len(v.split()) < 2:
            raise ValueError("El nombre debe tener al menos 2 palabras (nombre + apellido)")
        return v

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("A", "B", "C"):
            raise ValueError("La categoría debe ser A, B o C")
        return v


class MedicoVisitaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vm_id: int
    nombre_completo: str
    especialidad_id: int | None
    especialidad_nombre: str | None = None
    categoria: str
    tipo_consultorio: str | None
    direccion: str | None
    telefono: str | None
    ciclos_sin_visita: int
    activo: bool


class PosibleDuplicado(BaseModel):
    id: int
    nombre_completo: str
    direccion: str | None = None
    palabras_coinciden: int


# Comentarios genéricos rechazados (lista negra, spec 4.3)
_COMENTARIOS_GENERICOS = {
    "VISITA OK", "VISITA REALIZADA", "OK", "BIEN", "VISITA", "REALIZADA",
    "TODO BIEN", "SIN NOVEDAD", "OK VISITA", "VISITA HECHA", "HECHA", "NORMAL",
}
_CAUSAS_NO_VISITA = {
    "Médico en Vacaciones", "Médico Enfermo / Incapacitado",
    "Médico en Congreso o Evento Científico", "Consultorio Cerrado (sin aviso previo)",
    "Zona Inaccesible (transporte / clima)", "Reprogramada por el Médico",
}


class VisitaRegistrar(BaseModel):
    medico_id: int
    tipo_visita: str = Field(min_length=1, max_length=1)  # V / R
    comentario: str = Field(min_length=10, max_length=1000)
    hace_minutos: int = Field(default=0, ge=0, le=60)  # ventana de 60 min (spec 4.2)

    @field_validator("tipo_visita")
    @classmethod
    def _tipo_valido(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("V", "R"):
            raise ValueError("El tipo de visita debe ser V (Vista) o R (Revisita)")
        return v

    @field_validator("comentario")
    @classmethod
    def _comentario_valido(cls, v: str) -> str:
        v = v.strip()
        if len(v) < 10:
            raise ValueError("El comentario debe tener al menos 10 caracteres")
        if v.upper() in _COMENTARIOS_GENERICOS:
            raise ValueError("El comentario es demasiado genérico; describe algo relevante de la visita")
        return v


class VisitaNoVisita(BaseModel):
    medico_id: int
    causa: str
    comentario: str | None = None

    @field_validator("causa")
    @classmethod
    def _causa_valida(cls, v: str) -> str:
        if v.strip() not in _CAUSAS_NO_VISITA:
            raise ValueError("Causa de no-visita inválida")
        return v.strip()


class PlaneacionItem(BaseModel):
    medico_id: int
    tipo_visita: str = Field(min_length=1, max_length=1)  # V / R
    semana: int = Field(ge=1, le=4)
    dia_semana: str | None = None
    hora_estimada: str | None = None

    @field_validator("tipo_visita")
    @classmethod
    def _tipo(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("V", "R"):
            raise ValueError("tipo_visita debe ser V o R")
        return v


class PlaneacionGuardar(BaseModel):
    items: list[PlaneacionItem] = Field(default_factory=list)
