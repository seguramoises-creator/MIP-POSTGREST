"""Ranking de Formación (§8) — el podio del módulo.

Es un ranking PROPIO: no alimenta el Score Integral ni los premios (ver el
docstring de `formacion_ranking_service`). Por eso su recálculo es una acción
manual de Capacitación y no un paso del ETL.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authz import scope
from app.core.authz.constantes import Alcance
from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_ranking_service as ranking_srv

router = APIRouter(prefix="/formacion/ranking", tags=["Formación — Ranking"])

RequireCapacitacion = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))
RequireAnyAuth = Depends(get_current_active_user)

#: Quién ve el ranking completo del país. El representante TAMBIÉN lo ve entero:
#: un podio en el que cada quien solo se ve a sí mismo no es un podio.
_VEN_TODO = {Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
             Rol.PRESIDENCIA, Rol.GERENTE_MEDICO, Rol.REPRESENTANTE_MEDICO}


class PesoEntrada(BaseModel):
    pais_codigo: str
    clave: str
    valor: float
    descripcion: str | None = None


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu usuario no está enlazado a un representante.")
    return rm_id


@router.post("/recalcular", summary="Recalcular los puntos del ciclo")
def recalcular(ciclo_id: int, pais_codigo: str, db: Session = Depends(get_db),
               _: Usuario = RequireCapacitacion):
    try:
        return ranking_srv.recalcular_ciclo(db, ciclo_id, pais_codigo)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("", summary="Ranking de Formación del ciclo")
def listar(ciclo_id: int, db: Session = Depends(get_db),
           usuario: Usuario = RequireAnyAuth):
    """El Gerente de Distrito ve solo su equipo; los demás roles, todo el país."""
    if usuario.rol in _VEN_TODO:
        rm_ids = None
    elif usuario.rol == Rol.GERENTE_DISTRITO:
        visibles = scope.rm_ids_visibles(db, usuario, Alcance.TEAM)
        rm_ids = sorted(visibles) if visibles is not None else None
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu rol no tiene acceso al Ranking de Formación.")
    return ranking_srv.ranking(db, ciclo_id, rm_ids)


@router.get("/mis-puntos", summary="Mi desglose de puntos del ciclo")
def mis_puntos(ciclo_id: int, db: Session = Depends(get_db),
               usuario: Usuario = RequireAnyAuth):
    return ranking_srv.mis_puntos(db, _rm_propio(usuario), ciclo_id)


@router.get("/pesos", summary="Pesos vigentes del país")
def ver_pesos(pais_codigo: str, db: Session = Depends(get_db),
              _: Usuario = RequireAnyAuth):
    return ranking_srv.pesos(db, pais_codigo)


@router.put("/pesos", summary="Fijar un peso")
def fijar_peso(datos: PesoEntrada, db: Session = Depends(get_db),
               _: Usuario = RequireCapacitacion):
    try:
        p = ranking_srv.fijar_peso(db, datos.pais_codigo, datos.clave,
                                   datos.valor, datos.descripcion)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"clave": p.clave, "valor": float(p.valor)}
