"""Schemas del Módulo de Farmacias (Task 5, plan `2026-07-22-modulo-farmacias.md`).

Espejo de `app/schemas/visita.py` (módulo de Médicos). Los bloqueantes F23/F24
(`direccion`/`encargado`) se validan en `maestro_farmacia_service.validar_bloqueantes`
(servicio, ya cubierto por Tarea 3) — aquí solo se exige longitud mínima no vacía a
nivel de payload; el mensaje EXACTO del negocio (F23/F24) lo produce el servicio y el
router lo traduce a 422.
"""
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


# ─────────────────────────────────────────────────────────────────────────
# Maestro (Config.DIM_Farmacia)
# ─────────────────────────────────────────────────────────────────────────

class FarmaciaMaestroCrear(BaseModel):
    """Alta directa del maestro (ADMIN/GERENTE_PRODUCTIVIDAD, sin aprobación) o payload
    de las Acciones A/B del VM (el router agrega `pais_codigo` desde el propio VM).

    NOTA: `direccion`/`encargado` NO llevan `min_length` aquí a propósito — F23/F24 son
    bloqueantes de NEGOCIO validados por `maestro_farmacia_service.validar_bloqueantes`
    (que produce el mensaje EXACTO del txt de requerimientos). Si Pydantic los rechazara
    primero, el 422 llevaría el mensaje genérico de Pydantic en vez del de negocio."""
    es_cadena: bool = False
    cadena: str | None = Field(default=None, max_length=120)
    sucursal: str | None = Field(default=None, max_length=120)
    nombre: str | None = Field(default=None, max_length=200)
    direccion: str = Field(default="", max_length=300)
    provincia: str | None = Field(default=None, max_length=100)
    municipio: str | None = Field(default=None, max_length=100)
    sector: str | None = Field(default=None, max_length=100)
    latitud: float | None = None
    longitud: float | None = None
    encargado: str = Field(default="", max_length=200)
    telefono: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)


class FarmaciaMaestroActualizar(BaseModel):
    """Edición parcial del maestro (PUT /farmacias/maestro/{id})."""
    es_cadena: bool | None = None
    cadena: str | None = Field(default=None, max_length=120)
    sucursal: str | None = Field(default=None, max_length=120)
    nombre: str | None = Field(default=None, max_length=200)
    direccion: str | None = Field(default=None, max_length=300)
    provincia: str | None = Field(default=None, max_length=100)
    municipio: str | None = Field(default=None, max_length=100)
    sector: str | None = Field(default=None, max_length=100)
    latitud: float | None = None
    longitud: float | None = None
    encargado: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    activo: bool | None = None


class FarmaciaMaestroResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    pais_codigo: str
    es_cadena: bool
    cadena: str | None = None
    sucursal: str | None = None
    nombre: str | None = None
    nombre_completo: str
    direccion: str
    provincia: str | None = None
    municipio: str | None = None
    sector: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    encargado: str
    telefono: str | None = None
    email: str | None = None
    estado: str
    origen: str
    activo: bool
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────────────────────────────────
# Panel del VM (Visita.DIM_FarmaciaVisita) — Acciones A/B
# ─────────────────────────────────────────────────────────────────────────

class PanelAgregarIn(BaseModel):
    """Acción A: agregar al panel una farmacia YA existente y ACTIVA en el maestro."""
    maestro_farmacia_id: int


class PanelCrearIn(FarmaciaMaestroCrear):
    """Acción B: dar de alta una farmacia que no existe en el maestro (bloqueantes
    F23/F24 + anti-dup F25/F09, validados por el servicio)."""
    pass


class PanelResponse(BaseModel):
    id: int
    maestro_farmacia_id: int
    estado_aprobacion: str
    vm_id: int
    fecha_solicitud: datetime | None = None
    fecha_aprobacion: datetime | None = None
    motivo: str | None = None


class PanelItem(BaseModel):
    """Fila del panel del VM: datos del maestro + estado de aprobación del panel."""
    panel_id: int
    maestro_farmacia_id: int
    nombre_completo: str
    direccion: str
    encargado: str
    estado_maestro: str
    estado_aprobacion: str
    ciclos_sin_visita: int


# ─────────────────────────────────────────────────────────────────────────
# Bandeja de aprobación (GD)
# ─────────────────────────────────────────────────────────────────────────

class RechazarIn(BaseModel):
    """`motivo` SIN `min_length` a propósito (igual que F23/F24 arriba): la validación
    ("Debe indicar el motivo del rechazo.") vive en `farmacia_aprobacion_service.rechazar`
    y el router la traduce a 400 — un min_length de Pydantic la interceptaría antes con
    un mensaje genérico."""
    motivo: str | None = Field(default=None, max_length=300)


class EditarAprobarIn(BaseModel):
    """Cambios opcionales al maestro (p.ej. dirección/encargado) aplicados en el mismo
    paso de la aprobación."""
    direccion: str | None = Field(default=None, max_length=300)
    encargado: str | None = Field(default=None, max_length=200)
    telefono: str | None = Field(default=None, max_length=40)
    email: str | None = Field(default=None, max_length=200)
    provincia: str | None = Field(default=None, max_length=100)
    municipio: str | None = Field(default=None, max_length=100)
    sector: str | None = Field(default=None, max_length=100)


# ─────────────────────────────────────────────────────────────────────────
# Registro de visita a Farmacia (Task 6) — AD-HOC, sin planeación de ciclo.
# Tabla paralela Visita.FactVisitaFarmacia (Opción A).
# ─────────────────────────────────────────────────────────────────────────

class VisitaFarmaciaRegistrar(BaseModel):
    """Registro AD-HOC de una visita a una farmacia del panel (guard F22 en el
    servicio: el panel debe estar APROBADO y el maestro ACTIVA)."""
    comentario: str | None = Field(default=None, max_length=1000)
    hace_minutos: int = Field(default=0, ge=0, le=60)  # hora servidor menos ventana
    ejecutada: bool = True
    causa_no_visita: str | None = Field(default=None, max_length=80)
    latitud: float | None = None
    longitud: float | None = None


class VisitaFarmaciaResponse(BaseModel):
    id: int
    vm_id: int
    ciclo_id: int
    farmacia_id: int
    ejecutada: bool
    fecha_hora: datetime | None = None
