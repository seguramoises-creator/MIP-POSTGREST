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

    m = Medico(pais_codigo=pais_codigo, origen=origen, estado_validacion=estado,
               activo=True, **{k: v for k, v in datos.items() if hasattr(Medico, k)})
    db.add(m); db.commit(); db.refresh(m)
    logger.info(f"Maestro médico creado id={m.id} '{m.nombre}' pais={pais_codigo} origen={origen}")
    return m


def actualizar_maestro(db: Session, medico: Medico, cambios: dict, usuario_id=None) -> Medico:
    for k, v in cambios.items():
        if hasattr(Medico, k) and k not in ("id", "pais_codigo", "created_at"):
            setattr(medico, k, v)
    medico.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(medico)
    logger.info(f"Maestro médico actualizado id={medico.id} campos={list(cambios)} por={usuario_id}")
    return medico
