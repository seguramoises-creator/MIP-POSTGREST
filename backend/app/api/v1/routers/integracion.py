"""Integración con Laboratorio Mallén — recepción y validación de lotes.

Operación de TI, no de negocio: se gatea por rol (ADMIN, GERENTE_PRODUCTIVIDAD),
el mismo criterio que usan `/admin` y `/ia/conexiones` (cada uno con su propio
conjunto de roles) — y no por la matriz RBAC, que exigiría una migración para
dar de alta el recurso —y sin ella quedaría denegado para todos.

Este router NO integra datos a los esquemas internos de VISTA: solo valida lo que
Mallén dejó en `ext` y reporta qué corregir.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import integracion_dimensiones_service as dimensiones
from app.services import integracion_ir_service as ir
from app.services import integracion_validacion_service as validacion
from app.services import integracion_visitas_service as visitas

router = APIRouter(prefix="/integracion", tags=["Integración — Mallén"])

RequireTI = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


@router.get("/lotes", summary="Lotes recibidos de Mallén")
def listar(pais_codigo: str | None = None, estado: str | None = None,
           limite: int = 100, db: Session = Depends(get_db),
           _: Usuario = RequireTI):
    return validacion.listar_lotes(db, pais_codigo, estado, limite)


@router.get("/lotes/{lote_id}", summary="Detalle del lote y sus hallazgos")
def detalle(lote_id: int, db: Session = Depends(get_db), _: Usuario = RequireTI):
    try:
        return validacion.detalle_lote(db, lote_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/lotes/{lote_id}/validar", summary="Validar (o re-validar) un lote")
def validar(lote_id: int, db: Session = Depends(get_db), _: Usuario = RequireTI):
    try:
        return validacion.validar_lote(db, lote_id)
    except validacion.LoteYaIntegrado as exc:
        # 409 y no 422: la petición es válida, lo que pasa es que el lote ya
        # está en un estado que no admite esta operación.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/resumen", summary="Conteo de lotes por estado")
def ver_resumen(pais_codigo: str | None = None, db: Session = Depends(get_db),
                _: Usuario = RequireTI):
    return validacion.resumen(db, pais_codigo)


@router.post("/dimensiones/sincronizar",
             summary="Sincronizar las 9 dimensiones de un país")
def sincronizar_dimensiones(pais_codigo: str, db: Session = Depends(get_db),
                            _: Usuario = RequireTI):
    """Adopta lo que VISTA ya tiene en vez de duplicarlo: mirar `adoptados` en la
    primera corrida es la forma de comprobar que el emparejamiento funcionó."""
    return dimensiones.sincronizar_todo(db, pais_codigo)


@router.get("/dimensiones/resumen", summary="Filas en ext frente a mapeadas")
def resumen_dimensiones(pais_codigo: str, db: Session = Depends(get_db),
                        _: Usuario = RequireTI):
    return dimensiones.resumen_dimensiones(db, pais_codigo)


@router.post("/visitas/integrar",
             summary="Integrar los hechos de visita de un ciclo, recalcular y cerrar los lotes")
def integrar_visitas(pais_codigo: str, ciclo_codigo: str,
                     db: Session = Depends(get_db), _: Usuario = RequireTI):
    """Los cuatro pasos del §7.1 en una acción: integra los cinco hechos
    (panel médico, visitas médico, target farmacia, visitas farmacia y
    ventas), calcula los 5 indicadores (los 4 de visita más VENTAS, que no es
    de visita), dispara el recálculo del Score/ranking/premios y marca los
    lotes recorridos como INTEGRADO."""
    return visitas.integrar_todo(db, pais_codigo, ciclo_codigo)


@router.get("/visitas/resumen", summary="Filas en ext frente a integradas")
def resumen_visitas(pais_codigo: str, ciclo_codigo: str,
                    db: Session = Depends(get_db), _: Usuario = RequireTI):
    return visitas.resumen_visitas(db, pais_codigo, ciclo_codigo)


@router.post("/ir/sincronizar",
             summary="Resolver las equivalencias del módulo IR de un país")
def sincronizar_ir(pais_codigo: str, db: Session = Depends(get_db),
                   _: Usuario = RequireTI):
    """Enlaza prescriptor, producto y período con los catálogos de VISTA.

    A diferencia de las dimensiones, este paso NO crea registros internos: un
    prescriptor de Close-Up que ningún representante trabaja no debe entrar al
    maestro de médicos. Lo que no enlaza se cuenta y se ve en el diagnóstico.
    """
    return ir.sincronizar_ir(db, pais_codigo)


@router.get("/ir/diagnostico",
            summary="Qué tan bien enlaza el IR y qué recetas serían atribuibles")
def diagnostico_ir(pais_codigo: str, db: Session = Depends(get_db),
                   _: Usuario = RequireTI):
    """Solo lectura. Es la comprobación que el requerimiento manda hacer con
    muestra real antes de construir el indicador EVO_IR (§11.9)."""
    return ir.diagnosticar_ir(db, pais_codigo)
