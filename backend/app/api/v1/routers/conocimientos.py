"""Conocimientos: quién alimenta EVAL_CONOCIMIENTOS y la captura manual de notas.

Se gatea por rol —ADMIN, GERENTE_PRODUCTIVIDAD y CAPACITACION—, el mismo criterio
que `/integracion`: dar de alta un recurso en la matriz RBAC exigiría una
migración y, sin ella, quedaría denegado para todos.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.database import get_db
from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.models.usuario import Rol, Usuario
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fuentes
from app.services import recalculo_service

router = APIRouter(prefix="/conocimientos", tags=["Conocimientos"])

# Única definición de la lista de roles. `require_roles` ya devuelve el
# `Usuario` autenticado, así que `usuario: Usuario = RequireCaptura` en la
# firma del endpoint basta — no hace falta repetir el chequeo `usuario.rol
# not in (...)` en cada handler (antes vivía copiado 4 veces: sin test que lo
# delatara, una copia se habría podido desincronizar de las otras).
RequireCaptura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))


class FuenteIn(BaseModel):
    pais_codigo: str
    fuente: str


class NotaIn(BaseModel):
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


def _validar_ciclo_del_pais(db: Session, ciclo_id: int, pais_codigo: str) -> None:
    """Mismo criterio que `_validar_rm_del_pais`, para el hallazgo IMPORTANT de
    la revisión final: nadie comprobaba `ciclo.pais_codigo == pais_codigo`, así
    que se podía capturar una nota dominicana contra un ciclo costarricense.
    `conocimientos_service.integrar_captura` repite este guard (defensa en
    profundidad: la captura y la integración pueden llamarse por separado, y
    un dato ya guardado con el par cruzado sería peor que rechazarlo aquí)."""
    ciclo = db.get(Ciclo, ciclo_id)
    if ciclo is None or ciclo.pais_codigo != pais_codigo:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El ciclo {ciclo_id} no pertenece a {pais_codigo}.")


@router.get("/fuente", summary="Quién alimenta EVAL_CONOCIMIENTOS en un país")
def ver_fuente(pais_codigo: str, db: Session = Depends(get_db),
               _: Usuario = RequireCaptura):
    return {"pais_codigo": pais_codigo,
            "fuente": fuentes.fuente_de(db, pais_codigo),
            "fuentes": list(fuentes.FUENTES)}


@router.put("/fuente", summary="Declarar quién alimenta EVAL_CONOCIMIENTOS")
def cambiar_fuente(datos: FuenteIn, db: Session = Depends(get_db),
                   usuario: Usuario = RequireCaptura):
    """Los otros caminos consultan esto antes de escribir: cambiarlo decide cuál
    de los tres puede alimentar el indicador en ese país."""
    try:
        fila = fuentes.fijar_fuente(db, datos.pais_codigo, datos.fuente, usuario.id)
        db.commit()
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    except IntegrityError:
        # pais_codigo inexistente: la FK revienta en el commit (INSERT nuevo)
        # o en el propio UPDATE si el motor la valida antes — se traduce a 422
        # con un mensaje de negocio en vez del 500 crudo del IntegrityError.
        db.rollback()
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            f"El país «{datos.pais_codigo}» no existe.")
    return {"pais_codigo": fila.pais_codigo, "fuente": fila.fuente}


@router.get("/notas", summary="Notas capturadas del ciclo, y a quién le faltan")
def listar_notas(pais_codigo: str, ciclo_id: int, db: Session = Depends(get_db),
                 _: Usuario = RequireCaptura):
    return cs.notas_del_ciclo(db, pais_codigo, ciclo_id)


@router.post("/notas", summary="Capturar una nota")
def crear_nota(datos: NotaIn, db: Session = Depends(get_db),
               usuario: Usuario = RequireCaptura):
    _validar_rm_del_pais(db, datos.rm_id, datos.pais_codigo)
    _validar_ciclo_del_pais(db, datos.ciclo_id, datos.pais_codigo)
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
                usuario: Usuario = RequireCaptura):
    """Corrige EDITANDO la fila. Para añadir otra nota del mismo RM se usa POST:
    la tabla no lleva UNIQUE y corregir insertando dejaría la nota vieja
    entrando al promedio."""
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
    delete-then-insert se pierde al cerrarse la sesión con la petición.

    Dispara el recálculo AQUÍ, en el router, y no dentro de
    `conocimientos_service.integrar_captura`: ese servicio lo comparte
    `integrar_conocimientos` (el integrador de Mallén), que corre dentro del
    orquestador por lotes `integracion_visitas_service.integrar_todo` — ese
    orquestador YA dispara un único recálculo al final de todo el lote. Si el
    recálculo viviera en el servicio compartido, un lote de Mallén recalcularía
    una vez por CADA integrador que lo llama, no una sola vez. La captura
    manual no tiene orquestador propio, así que el recálculo pertenece aquí.
    Solo se dispara si `integrar_captura` no abortó (ciclo cerrado): en el
    aborto el servicio no escribió nada, y recalcular una escritura vacía
    sería trabajo de sobra (aunque inofensivo — el guard de ciclo abierto
    también corta ahí)."""
    try:
        resultado = cs.integrar_captura(db, pais_codigo, ciclo_id)
    except fuentes.FuenteAjenaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
    except ValueError as exc:
        # Ciclo inexistente o de OTRO país (ver `_validar_ciclo_del_pais` /
        # el guard equivalente dentro de `integrar_captura`).
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    if not resultado.get("abortado"):
        recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
        # `completar_puntajes`/`generar_ranking` SÍ comitean por su cuenta
        # (`motor_calculo_service.py`) — este segundo commit no es lo que los
        # persiste. Es aquí por lo que hace `db.commit()` cuando no hay nada
        # pendiente: cerrar la transacción de esta sesión/petición antes de
        # devolver la respuesta. Inofensivo pero no imprescindible; se deja
        # explícito para no dejar la sesión con una transacción abierta.
        db.commit()
    return resultado
