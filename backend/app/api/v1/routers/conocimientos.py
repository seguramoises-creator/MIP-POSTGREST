"""Conocimientos: quién alimenta EVAL_CONOCIMIENTOS y la captura manual de notas.

Se gatea por rol —ADMIN, GERENTE_PRODUCTIVIDAD y CAPACITACION—, el mismo criterio
que `/integracion`: dar de alta un recurso en la matriz RBAC exigiría una
migración y, sin ella, quedaría denegado para todos.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.dimensiones import RepresentanteMedico
from app.models.usuario import Rol, Usuario
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fuentes

router = APIRouter(prefix="/conocimientos", tags=["Conocimientos"])

RequireCaptura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))


class FuenteIn(BaseModel):
    pais_codigo: str
    fuente: str


class NotaIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pais_codigo: str
    ciclo_id: int
    rm_id: int
    nota: Decimal
    fecha_evaluacion: date
    tema: str | None = None


class NotaEdit(BaseModel):
    nota: Decimal
    tema: str | None = None


def _validar_rm_del_pais(db: Session, rm_id: int, pais_codigo: str) -> None:
    """Cierra el hallazgo de la Tarea 3: `capturar_nota` no valida que el RM
    pertenezca al país recibido. `integrar_captura` selecciona por el
    `pais_codigo` del parámetro, mientras `_upsert_resultado` resuelve el
    indicador por `rm.pais_codigo` real — un país inconsistente aquí sería la
    misma discrepancia silenciosa que este sub-proyecto existe para eliminar.
    """
    rm = db.get(RepresentanteMedico, rm_id)
    if rm is None or rm.pais_codigo != pais_codigo:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El representante {rm_id} no pertenece a {pais_codigo}.")


@router.get("/fuente", summary="Quién alimenta EVAL_CONOCIMIENTOS en un país")
def ver_fuente(pais_codigo: str, db: Session = Depends(get_db),
               _: Usuario = RequireCaptura):
    return {"pais_codigo": pais_codigo,
            "fuente": fuentes.fuente_de(db, pais_codigo),
            "fuentes": list(fuentes.FUENTES)}


@router.put("/fuente", summary="Declarar quién alimenta EVAL_CONOCIMIENTOS")
def cambiar_fuente(datos: FuenteIn, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(get_current_active_user)):
    """Los otros caminos consultan esto antes de escribir: cambiarlo decide cuál
    de los tres puede alimentar el indicador en ese país."""
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    try:
        fila = fuentes.fijar_fuente(db, datos.pais_codigo, datos.fuente, usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"pais_codigo": fila.pais_codigo, "fuente": fila.fuente}


@router.get("/notas", summary="Notas capturadas del ciclo, y a quién le faltan")
def listar_notas(pais_codigo: str, ciclo_id: int, db: Session = Depends(get_db),
                 _: Usuario = RequireCaptura):
    return cs.notas_del_ciclo(db, pais_codigo, ciclo_id)


@router.post("/notas", summary="Capturar una nota")
def crear_nota(datos: NotaIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(get_current_active_user)):
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    _validar_rm_del_pais(db, datos.rm_id, datos.pais_codigo)
    try:
        fila = cs.capturar_nota(db, datos.pais_codigo, datos.ciclo_id, datos.rm_id,
                                datos.nota, datos.fecha_evaluacion, datos.tema,
                                usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"id": fila.id}


@router.put("/notas/{nota_id}", summary="Corregir una nota capturada")
def editar_nota(nota_id: int, datos: NotaEdit, db: Session = Depends(get_db),
                usuario: Usuario = Depends(get_current_active_user)):
    """Corrige EDITANDO la fila. Para añadir otra nota del mismo RM se usa POST:
    la tabla no lleva UNIQUE y corregir insertando dejaría la nota vieja
    entrando al promedio."""
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    try:
        cs.corregir_nota(db, nota_id, datos.nota, datos.tema, usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"ok": True}


@router.post("/integrar", summary="Integrar las notas capturadas al ciclo")
def integrar(pais_codigo: str, ciclo_id: int, db: Session = Depends(get_db),
             _: Usuario = RequireCaptura):
    """`integrar_captura` no hace commit propio (lo decide el llamador, igual
    que `capturar_nota`/`corregir_nota`/`fijar_fuente`) — sin este commit, el
    delete-then-insert se pierde al cerrarse la sesión con la petición."""
    try:
        resultado = cs.integrar_captura(db, pais_codigo, ciclo_id)
    except fuentes.FuenteAjenaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    db.commit()
    return resultado
