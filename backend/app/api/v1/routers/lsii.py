"""
SCGCPR — Router: Matriz de Desarrollo LSII (Liderazgo Situacional II)

GET  /lsii/catalogo   — Dimensiones + opciones de comportamiento (lo único que ve el GD)
POST /lsii/evaluar    — Registra una evaluación de Receptividad y devuelve el cruce LSII
GET  /lsii/matriz     — Puntos de la matriz (eje X=receptividad, eje Y=desempeño) para el scatter
GET  /lsii/rm/{rm_id} — Histórico de evaluaciones LSII de un RM (detalle/tooltip)

Regla de negocio crítica: ningún endpoint de este router devuelve
`score_oculto` ni `peso_dimension` — esos campos solo existen en
DW.FACT_EvaluacionReceptividadDetalle y se usan exclusivamente dentro de
lsii_service.py. El evaluador (GD) solo ve `texto_comportamiento`.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import EvaluacionReceptividad
from app.models.dimensiones import RepresentanteMedico
from app.schemas.schemas import (
    ReceptividadDimensionPublic,
    EvaluacionLsiiCreate,
    EvaluacionLsiiResponse,
    MatrizLsiiItem,
    ReceptividadDimensionAdmin,
    ReceptividadOpcionAdmin,
    DimensionLsiiUpsert,
    OpcionLsiiUpdate,
    ConfiguracionLsiiPublic,
    ConfiguracionLsiiUpdate,
)
from app.services import lsii_service

router = APIRouter(prefix="/lsii", tags=["LSII - Matriz de Desarrollo"])
AnyAuth = Depends(get_current_active_user)
RequireEvaluador = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA
))
# Administración de la matriz (dimensiones/opciones) y del umbral D1-D4:
# mismo criterio que /dims (importación de catálogos) — ver CLAUDE.md sección 13.
RequireAdminLsii = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


@router.get(
    "/catalogo",
    response_model=List[ReceptividadDimensionPublic],
    summary="Catálogo de dimensiones y comportamientos observables (vista del GD)",
)
def get_catalogo(
    db: Session = Depends(get_db),
    current_user=RequireEvaluador,
):
    return lsii_service.obtener_dimensiones_catalogo(db)


@router.post(
    "/evaluar",
    response_model=EvaluacionLsiiResponse,
    status_code=201,
    summary="Registrar evaluación de Receptividad/Compromiso y obtener el cruce LSII",
)
def evaluar(
    data: EvaluacionLsiiCreate,
    db: Session = Depends(get_db),
    current_user=RequireEvaluador,
):
    try:
        cabecera = lsii_service.registrar_evaluacion(
            db,
            pais_codigo=data.pais_codigo,
            rm_id=data.rm_id,
            ciclo_id=data.ciclo_id,
            selecciones=[s.model_dump() for s in data.selecciones],
            gerente_id=data.gerente_id,
            evaluador_usuario_id=current_user.id,
            observaciones=data.observaciones,
        )
    except ValueError as e:
        mensaje = str(e)
        if "cerrado" in mensaje.lower() or "solo lectura" in mensaje.lower():
            raise HTTPException(409, mensaje)
        raise HTTPException(400, mensaje)
    return cabecera


@router.get(
    "/matriz",
    response_model=List[MatrizLsiiItem],
    summary="Puntos de la matriz LSII (scatter): última evaluación por RM en el ciclo",
)
def get_matriz(
    pais_codigo: Optional[str] = None,
    gerente_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = (
        db.query(EvaluacionReceptividad, RepresentanteMedico.codigo.label("rm_codigo"), RepresentanteMedico.nombre.label("rm_nombre"))
        .join(RepresentanteMedico, RepresentanteMedico.id == EvaluacionReceptividad.rm_id)
        .filter(EvaluacionReceptividad.activo == True)
    )
    if pais_codigo:
        q = q.filter(EvaluacionReceptividad.pais_codigo == pais_codigo)
    if gerente_id:
        q = q.filter(EvaluacionReceptividad.gerente_id == gerente_id)
    if ciclo_id:
        q = q.filter(EvaluacionReceptividad.ciclo_id == ciclo_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(EvaluacionReceptividad.rm_id == current_user.rm_id)

    rows = q.order_by(EvaluacionReceptividad.fecha_evaluacion.desc()).all()

    # Solo la evaluación más reciente por RM (rows ya viene ordenado desc)
    vistos: set[int] = set()
    items: List[dict] = []
    for ev, rm_codigo, rm_nombre in rows:
        if ev.rm_id in vistos:
            continue
        vistos.add(ev.rm_id)
        items.append({
            "rm_id": ev.rm_id,
            "rm_codigo": rm_codigo,
            "rm_nombre": rm_nombre,
            "pais_codigo": ev.pais_codigo,
            "gerente_id": ev.gerente_id,
            "ciclo_id": ev.ciclo_id,
            "score_desempeno": ev.score_desempeno if ev.score_desempeno is not None else 0,
            "score_receptividad": ev.score_receptividad,
            "nivel_lsii": ev.nivel_lsii,
            "estilo_liderazgo": ev.estilo_liderazgo,
            "fecha_evaluacion": ev.fecha_evaluacion,
        })
    return items


@router.get(
    "/rm/{rm_id}",
    response_model=List[EvaluacionLsiiResponse],
    summary="Histórico de evaluaciones LSII de un RM (detalle/tooltip)",
)
def get_historico_rm(
    rm_id: int,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id != rm_id:
        raise HTTPException(403, "No tiene permiso para ver evaluaciones de otro colaborador")

    rows = (
        db.query(EvaluacionReceptividad)
        .filter(EvaluacionReceptividad.rm_id == rm_id, EvaluacionReceptividad.activo == True)
        .order_by(EvaluacionReceptividad.fecha_evaluacion.desc())
        .all()
    )
    return rows


# ════════════════════════════════════════════════════════════════════════
# Administración — editar la matriz y los puntos desde la aplicación
# (sin tocar la base de datos). Roles: ADMIN, GERENTE_PRODUCTIVIDAD.
# Estos endpoints SÍ devuelven score_oculto/peso_dimension — a diferencia
# de /lsii/catalogo, que es la vista del evaluador (GD).
# ════════════════════════════════════════════════════════════════════════

@router.get(
    "/admin/dimensiones",
    response_model=List[ReceptividadDimensionAdmin],
    summary="[Admin] Catálogo completo de dimensiones y opciones (incluye puntos ocultos y pesos)",
)
def admin_listar_dimensiones(
    incluir_inactivas: bool = False,
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    return lsii_service.listar_dimensiones_admin(db, incluir_inactivas=incluir_inactivas)


@router.post(
    "/admin/dimensiones",
    response_model=ReceptividadDimensionAdmin,
    summary="[Admin] Crear o actualizar una dimensión completa (nombre, peso y sus opciones)",
)
def admin_guardar_dimension(
    data: DimensionLsiiUpsert,
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    try:
        return lsii_service.upsert_dimension_admin(
            db, data.model_dump(), actualizado_por=current_user.username
        )
    except ValueError as e:
        raise HTTPException(400, str(e))


@router.delete(
    "/admin/dimensiones/{dimension_codigo}",
    summary="[Admin] Desactivar una dimensión completa (soft-delete, preserva el historial)",
)
def admin_desactivar_dimension(
    dimension_codigo: str,
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    try:
        cantidad = lsii_service.desactivar_dimension_admin(db, dimension_codigo)
    except ValueError as e:
        raise HTTPException(404, str(e))
    return {"dimension_codigo": dimension_codigo, "opciones_desactivadas": cantidad}


@router.patch(
    "/admin/opciones/{opcion_id}",
    response_model=ReceptividadOpcionAdmin,
    summary="[Admin] Editar puntualmente una opción (texto, puntaje oculto o estado)",
)
def admin_actualizar_opcion(
    opcion_id: int,
    data: OpcionLsiiUpdate,
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    try:
        return lsii_service.actualizar_opcion_admin(
            db, opcion_id, data.model_dump(exclude_unset=True)
        )
    except ValueError as e:
        raise HTTPException(404, str(e))


@router.get(
    "/admin/configuracion",
    response_model=ConfiguracionLsiiPublic,
    summary="[Admin] Umbral de corte vigente para los cuadrantes D1-D4",
)
def admin_obtener_configuracion(
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    return lsii_service.obtener_configuracion(db)


@router.put(
    "/admin/configuracion",
    response_model=ConfiguracionLsiiPublic,
    summary="[Admin] Actualizar el umbral de corte D1-D4 (eje Desempeño / eje Receptividad)",
)
def admin_actualizar_configuracion(
    data: ConfiguracionLsiiUpdate,
    db: Session = Depends(get_db),
    current_user=RequireAdminLsii,
):
    return lsii_service.actualizar_configuracion(
        db,
        corte_desempeno=data.corte_desempeno,
        corte_receptividad=data.corte_receptividad,
        actualizado_por=current_user.username,
    )
