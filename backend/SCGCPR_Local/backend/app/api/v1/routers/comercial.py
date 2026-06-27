"""
SCGCPR — Router: Comercial (Ventas + EVO IR)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, Query, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import Ventas, EvoIR
from app.models.dimensiones import RepresentanteMedico, Ciclo

router = APIRouter(prefix="/comercial", tags=["Comercial"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=dict, summary="KPIs comerciales generales")
def get_comercial(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """Resumen de KPIs comerciales: ventas y EVO IR."""
    qv = db.query(
        func.count(func.distinct(Ventas.rm_id)).label("total_rms"),
        func.sum(Ventas.ventas_reales).label("ventas_totales"),
        func.sum(Ventas.cuota).label("cuota_total"),
        func.avg(Ventas.cumplimiento_pct).label("cumplimiento_promedio"),
    ).filter(Ventas.ventas_reales >= 0)

    if pais_id:
        qv = qv.filter(Ventas.pais_id == pais_id)
    if ciclo_id:
        qv = qv.filter(Ventas.ciclo_id == ciclo_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        qv = qv.filter(Ventas.rm_id == current_user.rm_id)

    v = qv.first()

    return {
        "total_rms": v.total_rms or 0,
        "ventas_totales": float(v.ventas_totales or 0),
        "cuota_total": float(v.cuota_total or 0),
        "cumplimiento_promedio_pct": float(v.cumplimiento_promedio or 0),
        "pais_id": pais_id,
        "ciclo_id": ciclo_id,
    }


@router.get("/ventas", response_model=List[dict], summary="Detalle de ventas por RM")
def get_ventas(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    linea_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        Ventas.rm_id,
        RepresentanteMedico.nombre.label("rm_nombre"),
        Ventas.ciclo_id,
        Ventas.ventas_reales,
        Ventas.cuota,
        Ventas.cumplimiento_pct,
        Ventas.crecimiento_pct,
        Ventas.puntaje,
    ).join(RepresentanteMedico, RepresentanteMedico.id == Ventas.rm_id)

    if pais_id: q = q.filter(Ventas.pais_id == pais_id)
    if ciclo_id: q = q.filter(Ventas.ciclo_id == ciclo_id)
    if linea_id: q = q.filter(Ventas.linea_id == linea_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(Ventas.rm_id == current_user.rm_id)

    rows = q.order_by(Ventas.cumplimiento_pct.desc()).all()

    return [
        {
            "rm_id": r.rm_id, "rm_nombre": r.rm_nombre,
            "ciclo_id": r.ciclo_id,
            "ventas_reales": float(r.ventas_reales or 0),
            "cuota": float(r.cuota or 0),
            "cumplimiento_pct": float(r.cumplimiento_pct or 0),
            "crecimiento_pct": float(r.crecimiento_pct or 0),
            "puntaje": float(r.puntaje or 0),
        }
        for r in rows
    ]


@router.get("/evoir", response_model=List[dict], summary="EVO IR — Evolución Prescriptiva")
def get_evoir(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        EvoIR.rm_id,
        RepresentanteMedico.nombre.label("rm_nombre"),
        EvoIR.producto_codigo,
        EvoIR.producto_nombre,
        EvoIR.prescripciones_actuales,
        EvoIR.prescripciones_anteriores,
        EvoIR.evolucion_pct,
        EvoIR.puntaje,
    ).join(RepresentanteMedico, RepresentanteMedico.id == EvoIR.rm_id)

    if pais_id: q = q.filter(EvoIR.pais_id == pais_id)
    if ciclo_id: q = q.filter(EvoIR.ciclo_id == ciclo_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(EvoIR.rm_id == current_user.rm_id)

    rows = q.order_by(EvoIR.evolucion_pct.desc()).all()

    return [
        {
            "rm_id": r.rm_id, "rm_nombre": r.rm_nombre,
            "producto_codigo": r.producto_codigo, "producto_nombre": r.producto_nombre,
            "prescripciones_actuales": float(r.prescripciones_actuales or 0),
            "prescripciones_anteriores": float(r.prescripciones_anteriores or 0),
            "evolucion_pct": float(r.evolucion_pct or 0),
            "puntaje": float(r.puntaje or 0),
        }
        for r in rows
    ]
