"""Calendario de Coaching (§7). Consume el cuadrante LSII vigente; no lo recalcula."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_calendario_service as cal
from app.services.recalculo_service import CicloCerradoError

router = APIRouter(prefix="/formacion/calendario-coaching",
                   tags=["Formación — Calendario de Coaching"])

RequireEscritura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))
RequireLectura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO,
    Rol.PRESIDENCIA, Rol.GERENTE_MEDICO, Rol.CAPACITACION))
RequireConfig = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


def _gd_scope(usuario: Usuario, gd_id: int | None) -> int:
    """GERENTE_DISTRITO se fuerza a su propio equipo; el resto debe indicar gd_id."""
    if usuario.rol == Rol.GERENTE_DISTRITO:
        propio = getattr(usuario, "gerente_id", None)
        if propio is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Tu usuario no está enlazado a un Gerente de Distrito.")
        if gd_id is not None and gd_id != propio:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes ver tu propio equipo.")
        return propio
    if gd_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta gd_id.")
    return gd_id


class GenerarEntrada(BaseModel):
    ciclo_id: int
    gd_id: int | None = None
    persistir: bool = True


class MoverEntrada(BaseModel):
    semana: int = Field(ge=1)
    dia_semana: str


class FrecuenciaEntrada(BaseModel):
    pais_codigo: str
    cuadrante: str
    visitas_por_ciclo: int = Field(ge=0)
    descripcion: str | None = None


def _celda(c) -> dict:
    return {"id": c.id, "gd_id": c.gd_id, "ciclo_id": c.ciclo_id, "rm_id": c.rm_id,
            "semana": c.semana, "dia_semana": c.dia_semana,
            "cuadrante": c.cuadrante_al_generar,
            "editado_manualmente": c.editado_manualmente, "publicado": c.publicado}


@router.post("/generar", summary="Generar (o previsualizar) el calendario del GD")
def generar(datos: GenerarEntrada, db: Session = Depends(get_db),
            usuario: Usuario = RequireEscritura):
    gd = _gd_scope(usuario, datos.gd_id)
    try:
        return cal.generar(db, gd, datos.ciclo_id, persistir=datos.persistir)
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("", summary="Calendario del GD/ciclo")
def listar(ciclo_id: int, gd_id: int | None = None, db: Session = Depends(get_db),
           usuario: Usuario = RequireLectura):
    gd = _gd_scope(usuario, gd_id)
    return [_celda(c) for c in cal.listar(db, gd, ciclo_id)]


@router.put("/celda/{celda_id}", summary="Mover una celda (día/semana)")
def mover(celda_id: int, datos: MoverEntrada, db: Session = Depends(get_db),
          usuario: Usuario = RequireEscritura):
    c = db.get(cal.CalendarioCoachingSugerido, celda_id)
    if c is not None:
        _gd_scope(usuario, c.gd_id)   # valida scope del GD dueño de la celda
    try:
        return _celda(cal.mover_celda(db, celda_id, datos.semana, datos.dia_semana))
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/publicar", summary="Publicar el calendario del GD/ciclo")
def publicar(datos: GenerarEntrada, db: Session = Depends(get_db),
             usuario: Usuario = RequireEscritura):
    gd = _gd_scope(usuario, datos.gd_id)
    try:
        return {"publicadas": cal.publicar(db, gd, datos.ciclo_id)}
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/frecuencias", summary="Tabla de frecuencia vigente del país")
def frecuencias(pais_codigo: str, db: Session = Depends(get_db), _: Usuario = RequireLectura):
    return {"pais_codigo": pais_codigo, "valores": cal.frecuencias(db, pais_codigo),
            "cuadrantes": list(cal.CUADRANTES)}


@router.put("/frecuencias", summary="Fijar la frecuencia de un cuadrante para el país")
def fijar_frecuencia(datos: FrecuenciaEntrada, db: Session = Depends(get_db),
                     _: Usuario = RequireConfig):
    try:
        p = cal.fijar_frecuencia(db, datos.pais_codigo, datos.cuadrante,
                                 datos.visitas_por_ciclo, datos.descripcion)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"pais_codigo": p.pais_codigo, "cuadrante": p.cuadrante,
            "visitas_por_ciclo": p.visitas_por_ciclo, "descripcion": p.descripcion}
