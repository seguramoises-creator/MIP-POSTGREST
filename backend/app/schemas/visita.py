"""Schemas del Módulo de Visita Médica — Fase 1 (Panel Médico)."""
import re
from datetime import date
from decimal import Decimal
from pydantic import BaseModel, ConfigDict, Field, field_validator

# Formato estándar de contacto para el maestro de médicos (República Dominicana).
_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def _validar_email(v: str | None) -> str | None:
    """Valida y normaliza (minúsculas) un correo. '' → None (campo limpiado)."""
    if v is None:
        return None
    v = v.strip().lower()
    if not v:
        return None
    if not _EMAIL_RE.match(v):
        raise ValueError("Correo electrónico inválido (formato esperado: nombre@dominio.com)")
    return v


def validar_nombre_medico(v: str) -> str:
    """Normaliza (MAYÚSCULAS, espacios) y valida el nombre completo de un médico:
    sin abreviaciones con punto y con al menos 2 palabras. Compartida por el alta
    (siempre) y la edición (solo cuando el nombre realmente cambia — así un nombre
    heredado no conforme no bloquea editar los demás campos)."""
    v = " ".join((v or "").strip().upper().split())
    if "." in v:  # abreviaciones con punto (Dr. / M. / Manuel P.)
        raise ValueError("El nombre no debe llevar abreviaciones con punto (ej. Dr. o M.)")
    if len(v.split()) < 2:
        raise ValueError("El nombre debe tener al menos 2 palabras (nombre + apellido)")
    return v


def _validar_telefono(v: str | None) -> str | None:
    """Valida un teléfono dominicano y lo normaliza a 'XXX-XXX-XXXX'.
    Acepta espacios, guiones, paréntesis y un '+1'/'1' de país opcional.
    '' → None (campo limpiado)."""
    if v is None:
        return None
    raw = v.strip()
    if not raw:
        return None
    digitos = re.sub(r"\D", "", raw)
    if len(digitos) == 11 and digitos.startswith("1"):  # +1 país
        digitos = digitos[1:]
    if len(digitos) != 10:
        raise ValueError("Teléfono inválido: debe tener 10 dígitos (ej. 809-555-1234)")
    if digitos[:3] not in ("809", "829", "849"):
        raise ValueError("Código de área inválido para RD (debe ser 809, 829 o 849)")
    return f"{digitos[:3]}-{digitos[3:6]}-{digitos[6:]}"


class ClasificacionCrear(BaseModel):
    """Plantilla de clasificación (5 criterios del motor de categorización).

    Los valores de texto deben venir del vocabulario del país (GET /categorizacion/plantilla):
    escribirlos libre haría que no matcheen ninguna regla y el médico quedaría sin
    clasificar. La CATEGORÍA resultante no se pide ni se devuelve aquí: la calcula el
    sistema cuando el Gerente de Distrito aprueba el alta."""
    pacientes_semana: Decimal = Field(ge=0)
    costo_consulta: Decimal = Field(ge=0)
    potencial_prescripcion: str = Field(min_length=1, max_length=50)
    ubicacion_territorial: str = Field(min_length=1, max_length=50)
    kol_nivel: str = Field(min_length=1, max_length=100)


class MedicoVisitaCrear(BaseModel):
    vm_id: int
    codigo: str | None = None
    nombre_completo: str = Field(min_length=3, max_length=200)
    nombre: str | None = None
    apellidos: str | None = None
    especialidad_id: int | None = None
    subespecialidad: str | None = None
    # La categoría YA NO la elige el representante: la asigna el sistema al aprobarse el
    # alta, a partir de `clasificacion`. Se conserva opcional por compatibilidad con
    # cargas administrativas que sí traen la letra.
    categoria: str | None = Field(default=None, min_length=1, max_length=1)
    # OBLIGATORIA (Bloque B): sin la plantilla completa no se puede dar de alta el médico.
    clasificacion: ClasificacionCrear
    # Ubicación / zonificación
    centro_trabajo: str | None = None
    institucion_tipo: str | None = None          # Pública / Privada
    tipo_consultorio: str | None = None
    provincia: str | None = None
    municipio: str | None = None
    sector: str | None = None
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    # Contacto
    telefono: str | None = None
    email: str | None = None
    exequatur: str | None = None
    # Consulta / visita
    dias_consulta: str | None = None
    horario_consulta: str | None = None
    frecuencia_visita: str | None = None         # Semanal / Quincenal / Mensual / Bimestral
    acepta_visita: bool = True
    # Comercial
    potencial_prescripcion: str | None = None     # Alto / Medio / Bajo
    kol: bool = False
    segmento: str | None = None
    observaciones: str | None = None
    fecha_alta: date | None = None
    # Si el sistema detecta posible duplicado y el usuario decide registrar igual.
    confirmar_duplicado: bool = False

    @field_validator("nombre_completo")
    @classmethod
    def _nombre_valido(cls, v: str) -> str:
        return validar_nombre_medico(v)

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, v: str) -> str:
        v = v.strip().upper()
        if v not in ("A", "B", "C", "D"):
            raise ValueError("La categoría debe ser A, B, C o D")
        return v

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str | None) -> str | None:
        return _validar_email(v)

    @field_validator("telefono")
    @classmethod
    def _telefono_valido(cls, v: str | None) -> str | None:
        return _validar_telefono(v)


class MedicoVisitaActualizar(BaseModel):
    """Actualización parcial de un médico. Todos los campos opcionales: solo se
    aplican los enviados (patrón PATCH). Incluye `activo` para activar/desactivar.

    `clasificacion`: obligatoria cuando el REPRESENTANTE modifica un médico de su panel
    (el cambio queda pendiente de validación del Gerente de Distrito). El GD/ADMIN —que
    es quien valida— edita directo y no la necesita."""
    clasificacion: "ClasificacionCrear | None" = None
    codigo: str | None = None
    nombre_completo: str | None = Field(default=None, min_length=3, max_length=200)
    nombre: str | None = None
    apellidos: str | None = None
    especialidad_id: int | None = None
    subespecialidad: str | None = None
    categoria: str | None = None
    centro_trabajo: str | None = None
    institucion_tipo: str | None = None
    tipo_consultorio: str | None = None
    provincia: str | None = None
    municipio: str | None = None
    sector: str | None = None
    direccion: str | None = None
    latitud: float | None = None
    longitud: float | None = None
    telefono: str | None = None
    email: str | None = None
    exequatur: str | None = None
    dias_consulta: str | None = None
    horario_consulta: str | None = None
    frecuencia_visita: str | None = None
    acepta_visita: bool | None = None
    potencial_prescripcion: str | None = None
    kol: bool | None = None
    segmento: str | None = None
    observaciones: str | None = None
    fecha_alta: date | None = None
    activo: bool | None = None

    # Nota: el nombre NO se valida a nivel de schema en la edición. La validación
    # (sin puntos, ≥2 palabras) se aplica en `visita_service.actualizar_medico`
    # SOLO si el nombre realmente cambia, para no bloquear la edición de otros
    # campos en médicos con nombre heredado no conforme (ej. "DR. PEREZ GARCIA").
    @field_validator("nombre_completo")
    @classmethod
    def _nombre_normaliza(cls, v: str | None) -> str | None:
        return " ".join(v.strip().upper().split()) if v is not None else v

    @field_validator("categoria")
    @classmethod
    def _categoria_valida(cls, v: str | None) -> str | None:
        if v is None:
            return v
        v = v.strip().upper()
        if v not in ("A", "B", "C", "D"):
            raise ValueError("La categoría debe ser A, B, C o D")
        return v

    @field_validator("email")
    @classmethod
    def _email_valido(cls, v: str | None) -> str | None:
        return _validar_email(v)

    @field_validator("telefono")
    @classmethod
    def _telefono_valido(cls, v: str | None) -> str | None:
        return _validar_telefono(v)


class MedicoVisitaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    vm_id: int
    codigo: str | None = None
    nombre_completo: str
    nombre: str | None = None
    apellidos: str | None = None
    especialidad_id: int | None
    especialidad_nombre: str | None = None
    subespecialidad: str | None = None
    categoria: str
    centro_trabajo: str | None = None
    institucion_tipo: str | None = None
    tipo_consultorio: str | None
    provincia: str | None = None
    municipio: str | None = None
    sector: str | None = None
    direccion: str | None
    latitud: float | None = None
    longitud: float | None = None
    telefono: str | None
    email: str | None = None
    exequatur: str | None = None
    dias_consulta: str | None = None
    horario_consulta: str | None = None
    frecuencia_visita: str | None = None
    acepta_visita: bool | None = None
    potencial_prescripcion: str | None = None
    kol: bool | None = None
    segmento: str | None = None
    observaciones: str | None = None
    fecha_alta: date | None = None
    estado_aprobacion: str | None = None
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


class ProductoDetallado(BaseModel):
    producto: str = Field(min_length=1, max_length=120)
    mencion: int = Field(default=1, ge=1, le=9)   # 1ª/2ª/3ª mención…


class VisitaRegistrar(BaseModel):
    medico_id: int
    tipo_visita: str = Field(min_length=1, max_length=1)  # V / R
    comentario: str = Field(min_length=10, max_length=1000)
    hace_minutos: int = Field(default=0, ge=0, le=60)  # ventana de 60 min (spec 4.2)
    productos: list[ProductoDetallado] = Field(default_factory=list)
    acompanado: bool = False  # visita acompañada por el Gerente de Distrito
    latitud: float | None = None
    longitud: float | None = None

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


# ── Parrilla promocional / Muestras (Parte 6) ─────────────────────────
class ParrillaItem(BaseModel):
    producto_id: int | None = None                      # del catálogo DIM_Producto
    producto: str = Field(min_length=2, max_length=120)  # código/nombre (display)
    mensaje_clave: str | None = Field(default=None, max_length=300)
    segmento_target: str | None = Field(default=None, max_length=120)
    prioridad: int = Field(default=1, ge=1, le=20)
    meta_muestras: int = Field(default=0, ge=0)          # meta muestras / visita

    @field_validator("producto")
    @classmethod
    def _producto(cls, v: str) -> str:
        v = " ".join(v.strip().split())
        if len(v) < 2:
            raise ValueError("El producto debe tener al menos 2 caracteres")
        return v


class ParrillaGuardar(BaseModel):
    ciclo_id: int | None = None
    linea_id: int
    items: list[ParrillaItem] = Field(default_factory=list)


class MuestraItem(BaseModel):
    producto: str = Field(min_length=2, max_length=120)
    cantidad: int = Field(ge=1, le=9999)

    @field_validator("producto")
    @classmethod
    def _producto(cls, v: str) -> str:
        return " ".join(v.strip().split())


class MuestrasRegistrar(BaseModel):
    medico_id: int
    ciclo_id: int | None = None
    entregas: list[MuestraItem] = Field(min_length=1)


# ── Costo & ROI (Parte 8) ─────────────────────────────────────────────
class ParametroCostoGuardar(BaseModel):
    ciclo_id: int | None = None
    linea_id: int | None = None                       # None = valor por defecto del ciclo
    costo_visita: float = Field(ge=0)
    costo_muestra: float = Field(ge=0)
    costo_fijo_ciclo: float = Field(default=0, ge=0)
    moneda: str = Field(default="RD$", min_length=1, max_length=8)


# ── Costo & ROI de Visita (modelo financiero completo) ────────────────
class CostoProductoItem(BaseModel):
    producto_id: int | None = None
    producto: str = Field(min_length=1, max_length=120)
    orden: int = 1
    costo_unitario_muestra: float = Field(default=0, ge=0)
    cantidad_muestras: int = Field(default=0, ge=0)
    pool_ventas: float = Field(default=0, ge=0)
    visitas_detalladas: int = Field(default=0, ge=0)
    presupuesto_anual: float = Field(default=0, ge=0)
    precio_prom: float = Field(default=0, ge=0)


class CostoEstructuraGuardar(BaseModel):
    ciclo_id: int | None = None
    linea_id: int | None = None
    moneda: str = Field(default="RD$", min_length=1, max_length=8)
    salario_mensual: float = Field(default=0, ge=0)
    cargas_pct: float = Field(default=0, ge=0, le=200)
    viaticos_dia: float = Field(default=0, ge=0)
    materiales_ciclo: float = Field(default=0, ge=0)
    dias_campo: int = Field(default=19, ge=1)
    total_visitas: int = Field(default=190, ge=1)
    dias_mes: int = Field(default=21, ge=1, le=31)
    visitadores: int = Field(default=1, ge=1)
    visitas_ciclo_vm: int = Field(default=190, ge=1)
    ciclos_anio: int = Field(default=11, ge=1, le=13)
    coef_conservador: float = Field(default=0.40, ge=0, le=1)
    coef_optimista: float = Field(default=0.70, ge=0, le=1)
    psp_a: float = Field(default=0, ge=0)
    psp_b: float = Field(default=0, ge=0)
    psp_c: float = Field(default=0, ge=0)
    med_sin_visitar_a: int | None = None
    med_sin_visitar_b: int | None = None
    med_sin_visitar_c: int | None = None
    productos: list[CostoProductoItem] = Field(default_factory=list)
