"""Maestro de Médicos — dedup en cascada + alta/edición central.

Reglas de dedup (país-level):
  DURA  (bloquea): exequátur o cédula ya existentes → DuplicadoDuroError.
  BLANDA (advierte): mismo nombre normalizado + mismo centro/provincia →
         PosibleDuplicadoError, salvo confirmar_duplicado=True.
"""
import unicodedata
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.dimensiones import Medico


class DuplicadoDuroError(Exception):
    def __init__(self, coincidencias): self.coincidencias = coincidencias; super().__init__("Médico duplicado (exequátur/cédula)")

class PosibleDuplicadoError(Exception):
    def __init__(self, coincidencias): self.coincidencias = coincidencias; super().__init__("Posible médico duplicado")


def normalizar_nombre(nombre: str) -> str:
    if not nombre:
        return ""
    s = unicodedata.normalize("NFKD", nombre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def _dto(m: Medico) -> dict:
    return {"id": m.id, "nombre": m.nombre, "codigo": m.codigo,
            "exequatur": m.exequatur, "cedula": m.cedula,
            "centro_medico_id": m.centro_medico_id, "provincia_id": m.provincia_id,
            "telefono": m.telefono}


def _base(db: Session, pais_codigo: str, excluir_id=None):
    q = db.query(Medico).filter(Medico.pais_codigo == pais_codigo, Medico.activo == True)  # noqa: E712
    if excluir_id:
        q = q.filter(Medico.id != excluir_id)
    return q


def detectar_duplicados(db: Session, pais_codigo: str, *, exequatur=None, cedula=None,
                        nombre=None, centro_medico_id=None, provincia_id=None,
                        excluir_id=None) -> dict:
    """Dedup en cascada (país-level):
      DURA  = coincidencia de exequátur O cédula.
      BLANDA = mismo nombre normalizado (acentos incluidos) Y mismo centro O provincia.
               Requiere al menos centro_medico_id o provincia_id: sin contexto de
               ubicación NO se marca (evita falsos positivos por homónimos)."""
    duros = []
    if exequatur or cedula:
        conds = []
        if exequatur: conds.append(Medico.exequatur == exequatur)
        if cedula:    conds.append(Medico.cedula == cedula)
        duros = [_dto(m) for m in _base(db, pais_codigo, excluir_id).filter(or_(*conds)).all()]

    blandos = []
    # Solo aplica si hay nombre Y al menos una dimensión de ubicación (centro/provincia).
    if nombre and (centro_medico_id is not None or provincia_id is not None):
        norm = normalizar_nombre(nombre)
        loc_conds = []
        if centro_medico_id is not None: loc_conds.append(Medico.centro_medico_id == centro_medico_id)
        if provincia_id is not None:     loc_conds.append(Medico.provincia_id == provincia_id)
        # Se acota por ubicación en SQL y se compara el nombre YA normalizado en Python
        # (así los acentos no excluyen candidatos antes de la comparación real).
        duros_ids = {d["id"] for d in duros}
        for m in _base(db, pais_codigo, excluir_id).filter(or_(*loc_conds)).all():
            if normalizar_nombre(m.nombre) == norm and m.id not in duros_ids:
                blandos.append(_dto(m))
    return {"duros": duros, "blandos": blandos}


def _auditar(db: Session, usuario_id, medico_id, accion: str, detalle: str) -> None:
    """Deja rastro estructurado en Audit.FACT_Auditoria (fuente del historial del médico)."""
    from app.models.hechos import Auditoria
    db.add(Auditoria(usuario_id=usuario_id, accion=accion, modulo="MAESTRO_MEDICOS",
                     tabla="DIM_Medico", registro_id=str(medico_id), detalle=detalle))


def crear_maestro(db: Session, pais_codigo: str, datos: dict, *, origen="MANUAL",
                  estado="APROBADO", confirmar_duplicado=False, usuario_id=None) -> Medico:
    dups = detectar_duplicados(db, pais_codigo,
                               exequatur=datos.get("exequatur"), cedula=datos.get("cedula"),
                               nombre=datos.get("nombre"),
                               centro_medico_id=datos.get("centro_medico_id"),
                               provincia_id=datos.get("provincia_id"))
    if dups["duros"]:
        raise DuplicadoDuroError(dups["duros"])
    if dups["blandos"] and not confirmar_duplicado:
        raise PosibleDuplicadoError(dups["blandos"])

    # `activo` puede venir en `datos` (el formulario trae "Estado: Activo/Inactivo"); no se pasa
    # explícito aquí para no chocar con ese keyword. Si no viene, el modelo usa default=True.
    campos = {k: v for k, v in datos.items() if hasattr(Medico, k)}
    campos.setdefault("activo", True)
    m = Medico(pais_codigo=pais_codigo, origen=origen, estado_validacion=estado, **campos)
    db.add(m); db.flush()
    _auditar(db, usuario_id, m.id, "CREATE", f"Alta (origen={origen}, estado={estado})")
    db.commit(); db.refresh(m)
    logger.info(f"Maestro médico creado id={m.id} '{m.nombre}' pais={pais_codigo} origen={origen}")
    return m


def actualizar_maestro(db: Session, medico: Medico, cambios: dict, usuario_id=None) -> Medico:
    aplicados = []
    for k, v in cambios.items():
        if hasattr(Medico, k) and k not in ("id", "pais_codigo", "created_at"):
            setattr(medico, k, v); aplicados.append(k)
    medico.updated_at = datetime.now(timezone.utc)
    _auditar(db, usuario_id, medico.id, "UPDATE", f"Campos: {', '.join(aplicados) or 'ninguno'}")
    db.commit(); db.refresh(medico)
    logger.info(f"Maestro médico actualizado id={medico.id} campos={list(cambios)} por={usuario_id}")
    return medico


# ── Importación Excel (upsert idempotente por llave dura) ───────────────────────
_COLS_GENERALES = ("codigo", "cedula", "exequatur", "telefono", "email",
                   "direccion", "sector", "observaciones",
                   "especialidad_id", "provincia_id", "municipio_id", "centro_medico_id")


def _s(v):
    """Normaliza a str no vacío o None (tolera NaN/None/espacios)."""
    if v is None:
        return None
    s = str(v).strip()
    return s or None if s.lower() != "nan" else None


def _campos_generales(fila: dict) -> dict:
    """Campos generales presentes y no vacíos (no pisa con vacío al actualizar)."""
    out = {}
    for k in _COLS_GENERALES:
        if k in fila:
            v = fila[k]
            v = _s(v) if not str(k).endswith("_id") else v
            if v not in (None, "") and not (isinstance(v, float) and v != v):  # descarta NaN
                out[k] = v
    return out


def _resolver_por_llave_dura(db: Session, pais_codigo: str, exequatur=None, cedula=None,
                             codigo=None) -> Medico | None:
    """Busca un médico existente por exequátur → cédula → código (en ese orden)."""
    base = db.query(Medico).filter(Medico.pais_codigo == pais_codigo, Medico.activo == True)  # noqa: E712
    for campo, valor in ((Medico.exequatur, exequatur), (Medico.cedula, cedula), (Medico.codigo, codigo)):
        if valor:
            m = base.filter(campo == valor).first()
            if m:
                return m
    return None


def preview_excel(db: Session, pais_codigo: str, filas: list[dict]) -> dict:
    """Cuenta el efecto de importar SIN persistir: nuevos, actualizados, posibles duplicados."""
    nuevos = actualiza = dups = 0
    errores = []
    for i, fila in enumerate(filas, start=2):  # fila 1 = encabezado
        nombre = _s(fila.get("nombre"))
        if not nombre:
            errores.append({"fila": i, "error": "nombre vacío"}); continue
        existente = _resolver_por_llave_dura(db, pais_codigo, _s(fila.get("exequatur")),
                                             _s(fila.get("cedula")), _s(fila.get("codigo")))
        if existente:
            actualiza += 1
        else:
            d = detectar_duplicados(db, pais_codigo, nombre=nombre,
                                    centro_medico_id=fila.get("centro_medico_id"),
                                    provincia_id=fila.get("provincia_id"))
            if d["blandos"]:
                dups += 1
            nuevos += 1
    return {"filas": len(filas), "nuevos": nuevos, "actualizados": actualiza,
            "posibles_duplicados": dups, "errores": len(errores), "detalle_errores": errores[:20]}


def importar_excel(db: Session, pais_codigo: str, filas: list[dict], usuario_id=None) -> dict:
    """Upsert por llave dura (exequátur→cédula→código). El Excel es fuente autorizada:
    si hay coincidencia blanda (nombre+centro) pero no dura, crea igual y la contabiliza."""
    creados = actualizados = duplicados_marcados = 0
    errores = []
    for i, fila in enumerate(filas, start=2):
        try:
            nombre = _s(fila.get("nombre"))
            if not nombre:
                errores.append({"fila": i, "error": "nombre vacío"}); continue
            campos = _campos_generales(fila)
            existente = _resolver_por_llave_dura(db, pais_codigo, campos.get("exequatur"),
                                                 campos.get("cedula"), campos.get("codigo"))
            if existente:
                actualizar_maestro(db, existente, campos, usuario_id)
                actualizados += 1
            else:
                d = detectar_duplicados(db, pais_codigo, nombre=nombre,
                                        centro_medico_id=fila.get("centro_medico_id"),
                                        provincia_id=fila.get("provincia_id"))
                if d["blandos"]:
                    duplicados_marcados += 1
                crear_maestro(db, pais_codigo, {"nombre": nombre, **campos}, origen="EXCEL",
                              confirmar_duplicado=True, usuario_id=usuario_id)
                creados += 1
        except Exception as e:
            db.rollback()
            errores.append({"fila": i, "error": str(e)})
    return {"creados": creados, "actualizados": actualizados,
            "duplicados_marcados": duplicados_marcados, "errores": errores}
