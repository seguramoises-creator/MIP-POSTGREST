"""Maestro de Médicos — dedup en cascada + alta/edición central.

Reglas de dedup (país-level):
  DURA  (bloquea): exequátur o cédula ya existentes → DuplicadoDuroError.
  BLANDA (advierte): mismo nombre normalizado + mismo centro/provincia →
         PosibleDuplicadoError, salvo confirmar_duplicado=True.
"""
import unicodedata
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, or_
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
            "centro_medico_id": m.centro_medico_id, "telefono": m.telefono}


def detectar_duplicados(db: Session, pais_codigo: str, *, exequatur=None, cedula=None,
                        nombre=None, centro_medico_id=None, provincia_id=None,
                        excluir_id=None) -> dict:
    base = db.query(Medico).filter(Medico.pais_codigo == pais_codigo, Medico.activo == True)  # noqa: E712
    if excluir_id:
        base = base.filter(Medico.id != excluir_id)

    duros = []
    claves = [c for c in (exequatur, cedula) if c]
    if exequatur or cedula:
        conds = []
        if exequatur: conds.append(Medico.exequatur == exequatur)
        if cedula:    conds.append(Medico.cedula == cedula)
        duros = [_dto(m) for m in base.filter(or_(*conds)).all()]

    blandos = []
    if nombre:
        norm = normalizar_nombre(nombre)
        q = base.filter(func.upper(func.trim(Medico.nombre)) == norm)  # comparación básica; refinar acentos en Python
        for m in q.all():
            if normalizar_nombre(m.nombre) != norm:
                continue
            mismo_centro = centro_medico_id is not None and m.centro_medico_id == centro_medico_id
            mismo_prov = provincia_id is not None and m.provincia_id == provincia_id
            if mismo_centro or mismo_prov or (centro_medico_id is None and provincia_id is None):
                if m.id not in {d["id"] for d in duros}:
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
