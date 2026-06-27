"""
SCGCPR — Router: Productividad
FIX W-03: Todos los endpoints de lista usan PaginationParams.
GET /api/v1/productividad              — KPIs generales
GET /api/v1/productividad/rm/{rm_id}  — KPIs de un RM
GET /api/v1/productividad/pais/{id}   — KPIs por país
GET /api/v1/productividad/resumen     — Resumen consolidado
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.core.pagination import PaginationParams, paginate_list
from app.models.usuario import Rol
from app.models.hechos import RendimientoComercial
from app.models.dimensiones import RepresentanteMedico, Indicador, Ciclo
from app.schemas.schemas import KPIProductividadResponse

router = APIRouter(prefix="/productividad", tags=["Productividad"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=dict, summary="KPIs generales de productividad (paginado)")
def get_productividad(
    pais_id: Optional[int] = Query(None),
    ciclo_id: Optional[int] = Query(None),
    linea_id: Optional[int] = Query(None),
    params: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """
    Retorna KPIs de productividad agregados.
    Filtra por rol automáticamente (RM solo ve su propia data).
    """
    q = db.query(
        RepresentanteMedico.id.label("rm_id"),
        RepresentanteMedico.codigo.label("rm_codigo"),
        RepresentanteMedico.nombre.label("rm_nombre"),
        Indicador.codigo.label("indicador_codigo"),
        func.sum(RendimientoComercial.valor_real).label("valor_real"),
        func.avg(RendimientoComercial.porcentaje_cumplimiento).label("cumplimiento_pct"),
        func.sum(RendimientoComercial.puntaje).label("puntaje"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == RendimientoComercial.rm_id
    ).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        Indicador.modulo == "PRODUCTIVIDAD",
        RendimientoComercial.activo == True,
    )

    if pais_id:
        q = q.filter(RendimientoComercial.pais_id == pais_id)
    if ciclo_id:
        q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)
    if linea_id:
        q = q.filter(RendimientoComercial.linea_id == linea_id)

    # Filtro por rol: RM solo ve su propia información
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(RendimientoComercial.rm_id == current_user.rm_id)

    results = q.group_by(
        RepresentanteMedico.id,
        RepresentanteMedico.codigo,
        RepresentanteMedico.nombre,
        Indicador.codigo,
    ).all()

    all_items = [
        {
            "rm_id": r.rm_id,
            "rm_codigo": r.rm_codigo,
            "rm_nombre": r.rm_nombre,
            "indicador": r.indicador_codigo,
            "valor_real": float(r.valor_real or 0),
            "cumplimiento_pct": float(r.cumplimiento_pct or 0),
            "puntaje": float(r.puntaje or 0),
        }
        for r in results
    ]
    return paginate_list(all_items, params)  # FIX W-03


@router.get("/rm/{rm_id}", response_model=dict, summary="KPIs de un RM específico")
def get_productividad_rm(
    rm_id: int,
    ciclo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """KPIs completos de productividad para un RM: F1, F2, Farmacias, Promedio Diario."""
    # RMs solo pueden ver su propia data
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id != rm_id:
        from fastapi import HTTPException
        raise HTTPException(403, "No tiene permiso para ver datos de otro RM")

    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
    if not rm:
        from fastapi import HTTPException
        raise HTTPException(404, "RM no encontrado")

    q = db.query(
        Indicador.codigo,
        Indicador.nombre,
        func.sum(RendimientoComercial.valor_real).label("valor"),
        func.avg(RendimientoComercial.porcentaje_cumplimiento).label("cumplimiento"),
        func.sum(RendimientoComercial.puntaje).label("puntaje"),
    ).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        RendimientoComercial.rm_id == rm_id,
        Indicador.modulo == "PRODUCTIVIDAD",
        RendimientoComercial.activo == True,
    )

    if ciclo_id:
        q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)

    rows = q.group_by(Indicador.codigo, Indicador.nombre).all()

    kpis = {r.codigo: {"nombre": r.nombre, "valor": float(r.valor or 0),
                       "cumplimiento_pct": float(r.cumplimiento or 0),
                       "puntaje": float(r.puntaje or 0)} for r in rows}

    return {
        "rm_id": rm_id,
        "rm_codigo": rm.codigo,
        "rm_nombre": rm.nombre,
        "ciclo_id": ciclo_id,
        "kpis": kpis,
        "puntaje_total_productividad": sum(v["puntaje"] for v in kpis.values()),
    }


@router.get("/pais/{pais_id}", response_model=List[dict], summary="Productividad por país")
def get_productividad_pais(
    pais_id: int,
    ciclo_id: Optional[int] = Query(None),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL,
        Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA
    )),
):
    """KPIs de productividad consolidados por país — todos los RMs."""
    q = db.query(
        RepresentanteMedico.id.label("rm_id"),
        RepresentanteMedico.nombre.label("rm_nombre"),
        func.avg(RendimientoComercial.porcentaje_cumplimiento).label("cumplimiento_promedio"),
        func.sum(RendimientoComercial.puntaje).label("puntaje_total"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == RendimientoComercial.rm_id
    ).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        RendimientoComercial.pais_id == pais_id,
        Indicador.modulo == "PRODUCTIVIDAD",
        RendimientoComercial.activo == True,
    )
    if ciclo_id:
        q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)

    rows = q.group_by(RepresentanteMedico.id, RepresentanteMedico.nombre).all()

    return [
        {
            "rm_id": r.rm_id,
            "rm_nombre": r.rm_nombre,
            "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
            "puntaje_total": float(r.puntaje_total or 0),
        }
        for r in rows
    ]


@router.get("/resumen", response_model=dict, summary="Resumen ejecutivo de productividad")
def get_resumen_productividad(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
    )),
):
    """Resumen estadístico de productividad para dashboards ejecutivos."""
    q = db.query(
        func.count(func.distinct(RendimientoComercial.rm_id)).label("total_rms"),
        func.avg(RendimientoComercial.porcentaje_cumplimiento).label("cumplimiento_promedio"),
        func.sum(RendimientoComercial.puntaje).label("puntaje_total"),
        func.max(RendimientoComercial.puntaje).label("puntaje_max"),
        func.min(RendimientoComercial.puntaje).label("puntaje_min"),
    ).join(
        Indicador, Indicador.id == RendimientoComercial.indicador_id
    ).filter(
        Indicador.modulo == "PRODUCTIVIDAD",
        RendimientoComercial.activo == True,
    )

    if pais_id:
        q = q.filter(RendimientoComercial.pais_id == pais_id)
    if ciclo_id:
        q = q.filter(RendimientoComercial.ciclo_id == ciclo_id)

    r = q.first()
    return {
        "total_rms": r.total_rms or 0,
        "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
        "puntaje_promedio": float(r.puntaje_promedio or 0) if hasattr(r, 'puntaje_promedio') else 0,
    }
