"""
SCGCPR — Router: Capacitación
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import CapacitacionFact
from app.models.dimensiones import RepresentanteMedico, CapacitacionDim
from app.schemas.schemas import CapacitacionCreate, CapacitacionResponse

router = APIRouter(prefix="/capacitacion", tags=["Capacitación"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=List[dict], summary="Listar registros de capacitación")
def list_capacitacion(
    pais_codigo: Optional[str] = None,
    rm_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        CapacitacionFact,
        RepresentanteMedico.nombre.label("rm_nombre"),
        CapacitacionDim.nombre.label("capacitacion_nombre"),
        CapacitacionDim.tipo.label("capacitacion_tipo"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == CapacitacionFact.rm_id
    ).join(
        CapacitacionDim, CapacitacionDim.id == CapacitacionFact.capacitacion_id
    )

    if pais_codigo: q = q.filter(CapacitacionFact.pais_codigo == pais_codigo)
    if rm_id: q = q.filter(CapacitacionFact.rm_id == rm_id)
    if ciclo_id: q = q.filter(CapacitacionFact.ciclo_id == ciclo_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(CapacitacionFact.rm_id == current_user.rm_id)

    rows = q.all()
    return [
        {
            "id": r.CapacitacionFact.id,
            "rm_id": r.CapacitacionFact.rm_id,
            "rm_nombre": r.rm_nombre,
            "capacitacion_nombre": r.capacitacion_nombre,
            "tipo": r.capacitacion_tipo,
            "asistio": r.CapacitacionFact.asistio,
            "calificacion": float(r.CapacitacionFact.calificacion or 0),
            "aprobado": r.CapacitacionFact.aprobado,
            "horas_completadas": float(r.CapacitacionFact.horas_completadas),
            "puntaje": float(r.CapacitacionFact.puntaje),
            "fecha_actividad": r.CapacitacionFact.fecha_actividad,
        }
        for r in rows
    ]


@router.post("", response_model=CapacitacionResponse, status_code=201, summary="Registrar capacitación")
def create_capacitacion(
    data: CapacitacionCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD)),
):
    cap_dim = db.query(CapacitacionDim).filter(CapacitacionDim.id == data.capacitacion_id).first()
    if not cap_dim:
        raise HTTPException(404, "Capacitación no encontrada en catálogo")

    aprobado = False
    if data.calificacion is not None and cap_dim.puntaje_aprobacion is not None:
        aprobado = data.calificacion >= cap_dim.puntaje_aprobacion

    obj = CapacitacionFact(
        **data.model_dump(),
        aprobado=aprobado,
        puntaje=data.calificacion or 0,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/resumen", response_model=dict, summary="Resumen de capacitación")
def get_resumen_capacitacion(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
    )),
):
    q = db.query(
        func.count(CapacitacionFact.id).label("total"),
        func.sum(CapacitacionFact.horas_completadas).label("horas_total"),
        func.avg(CapacitacionFact.calificacion).label("calificacion_promedio"),
        func.count(func.nullif(CapacitacionFact.aprobado, False)).label("aprobados"),
    )
    if pais_codigo: q = q.filter(CapacitacionFact.pais_codigo == pais_codigo)
    if ciclo_id: q = q.filter(CapacitacionFact.ciclo_id == ciclo_id)
    r = q.first()

    total = r.total or 1
    return {
        "total_registros": r.total or 0,
        "horas_formacion_total": float(r.horas_total or 0),
        "calificacion_promedio": float(r.calificacion_promedio or 0),
        "total_aprobados": r.aprobados or 0,
        "tasa_aprobacion_pct": round((r.aprobados or 0) / total * 100, 2),
    }


@router.get("/catalogo", response_model=List[dict], summary="Catálogo de capacitaciones")
def list_catalogo(db: Session = Depends(get_db), current_user=AnyAuth):
    rows = db.query(CapacitacionDim).filter(CapacitacionDim.activo == True).all()
    return [
        {
            "id": r.id, "codigo": r.codigo, "nombre": r.nombre,
            "tipo": r.tipo, "duracion_horas": float(r.duracion_horas or 0),
            "puntaje_aprobacion": float(r.puntaje_aprobacion or 0),
            "obligatorio": r.obligatorio,
        }
        for r in rows
    ]
