"""
SCGCPR — Router: Coaching
GET/POST/PUT /api/v1/coaching
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from decimal import Decimal

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import Coaching
from app.models.dimensiones import RepresentanteMedico, Gerente
from app.schemas.schemas import CoachingCreate, CoachingResponse

router = APIRouter(prefix="/coaching", tags=["Coaching"])
AnyAuth = Depends(get_current_active_user)


def _calcular_resultado_coaching(programado: int, ejecutado: int,
                                  calidad: Decimal, peso_cant: Decimal, peso_cal: Decimal) -> Decimal:
    """Fórmula: (PesoCantidad × Cumplimiento%) + (PesoCalidad × Calidad%)"""
    cumplimiento = Decimal(ejecutado) / Decimal(max(programado, 1)) * 100
    return (peso_cant * cumplimiento) + (peso_cal * calidad)


@router.get("", response_model=List[dict], summary="Listar sesiones de coaching")
def list_coaching(
    pais_codigo: Optional[str] = None,
    rm_id: Optional[int] = None,
    gerente_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        Coaching,
        RepresentanteMedico.nombre.label("rm_nombre"),
        Gerente.nombre.label("gerente_nombre"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == Coaching.rm_id
    ).join(
        Gerente, Gerente.id == Coaching.gerente_id
    )

    if pais_codigo: q = q.filter(Coaching.pais_codigo == pais_codigo)
    if rm_id: q = q.filter(Coaching.rm_id == rm_id)
    if gerente_id: q = q.filter(Coaching.gerente_id == gerente_id)
    if ciclo_id: q = q.filter(Coaching.ciclo_id == ciclo_id)

    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(Coaching.rm_id == current_user.rm_id)

    rows = q.all()
    return [
        {
            "id": c.Coaching.id,
            "rm_id": c.Coaching.rm_id,
            "rm_nombre": c.rm_nombre,
            "gerente_nombre": c.gerente_nombre,
            "tipo": c.Coaching.tipo,
            "coaching_programado": c.Coaching.coaching_programado,
            "coaching_ejecutado": c.Coaching.coaching_ejecutado,
            "cumplimiento_pct": float(c.Coaching.cumplimiento_pct),
            "calificacion_calidad": float(c.Coaching.calificacion_calidad),
            "resultado_coaching": float(c.Coaching.resultado_coaching),
            "puntaje": float(c.Coaching.puntaje),
            "fecha_coaching": c.Coaching.fecha_coaching,
        }
        for c in rows
    ]


@router.post("", response_model=CoachingResponse, status_code=201, summary="Registrar coaching")
def create_coaching(
    data: CoachingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA
    )),
):
    cumplimiento_pct = Decimal(data.coaching_ejecutado) / Decimal(max(data.coaching_programado, 1)) * 100
    resultado = _calcular_resultado_coaching(
        data.coaching_programado, data.coaching_ejecutado,
        data.calificacion_calidad, data.peso_cantidad, data.peso_calidad
    )

    obj = Coaching(
        **data.model_dump(),
        cumplimiento_pct=cumplimiento_pct,
        resultado_coaching=resultado,
        puntaje=resultado,  # el servicio de negocio convertirá a puntaje real usando DIM_IndicadorTabla
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)
    return obj


@router.put("/{id}", response_model=CoachingResponse, summary="Actualizar coaching")
def update_coaching(
    id: int,
    data: CoachingCreate,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO)),
):
    obj = db.query(Coaching).filter(Coaching.id == id).first()
    if not obj:
        raise HTTPException(404, "Registro de coaching no encontrado")

    for k, v in data.model_dump().items():
        setattr(obj, k, v)

    obj.cumplimiento_pct = Decimal(obj.coaching_ejecutado) / Decimal(max(obj.coaching_programado, 1)) * 100
    obj.resultado_coaching = _calcular_resultado_coaching(
        obj.coaching_programado, obj.coaching_ejecutado,
        obj.calificacion_calidad, obj.peso_cantidad, obj.peso_calidad
    )
    db.commit()
    db.refresh(obj)
    return obj


@router.get("/resumen", response_model=dict, summary="Resumen de coaching")
def get_resumen_coaching(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO
    )),
):
    q = db.query(
        func.count(Coaching.id).label("total"),
        func.avg(Coaching.cumplimiento_pct).label("cumplimiento_promedio"),
        func.avg(Coaching.calificacion_calidad).label("calidad_promedio"),
        func.avg(Coaching.resultado_coaching).label("resultado_promedio"),
    )
    if pais_codigo: q = q.filter(Coaching.pais_codigo == pais_codigo)
    if ciclo_id: q = q.filter(Coaching.ciclo_id == ciclo_id)
    r = q.first()
    return {
        "total_registros": r.total or 0,
        "cumplimiento_promedio_pct": float(r.cumplimiento_promedio or 0),
        "calidad_promedio": float(r.calidad_promedio or 0),
        "resultado_promedio": float(r.resultado_promedio or 0),
    }
