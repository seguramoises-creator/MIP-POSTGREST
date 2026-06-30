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
