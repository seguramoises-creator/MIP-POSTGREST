"""
SCGCPR — Router: Ranking
FIX W-03: Paginación en todos los endpoints de lista.
GET /api/v1/ranking              — Ranking activo
GET /api/v1/ranking/regional     — Multi-país
GET /api/v1/ranking/anual        — Histórico anual
POST /api/v1/ranking/generar     — Disparar cálculo (Admin)
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from sqlalchemy import func

from app.core.deps import get_db, get_current_active_user, require_roles
from app.core.pagination import PaginationParams, paginate_query
from app.models.usuario import Rol
from app.models.hechos import Ranking
from app.models.dimensiones import RepresentanteMedico, Pais
from app.schemas.schemas import RankingResponse, RankingRequest

router = APIRouter(prefix="/ranking", tags=["Ranking"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=dict, summary="Ranking actual (paginado)")
def get_ranking(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    tipo: str = "MENSUAL",
    top: Optional[int] = None,
    params: PaginationParams = Depends(),
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """
    Ranking ordenado por posición ascendente.
    Tipos: MENSUAL | TRIMESTRAL | ANUAL | REGIONAL
    """
    q = db.query(
        Ranking,
        RepresentanteMedico.nombre.label("rm_nombre"),
        RepresentanteMedico.codigo.label("rm_codigo"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == Ranking.rm_id
    ).filter(
        Ranking.tipo_ranking == tipo.upper()
    )

    if pais_id: q = q.filter(Ranking.pais_id == pais_id)
    if ciclo_id: q = q.filter(Ranking.ciclo_id == ciclo_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(Ranking.rm_id == current_user.rm_id)

    q = q.order_by(Ranking.posicion.asc())
    if top:
        q = q.limit(top)

    # FIX W-03: paginación
    total = q.count()
    rows  = q.offset(params.offset).limit(params.size).all()

    items = [
        {
            "posicion": r.Ranking.posicion,
            "posicion_anterior": r.Ranking.posicion_anterior,
            "variacion": (r.Ranking.posicion_anterior or r.Ranking.posicion) - r.Ranking.posicion,
            "rm_id": r.Ranking.rm_id,
            "rm_codigo": r.rm_codigo,
            "rm_nombre": r.rm_nombre,
            "pais_id": r.Ranking.pais_id,
            "iup_total": float(r.Ranking.iup_total),
            "iup_productividad": float(r.Ranking.iup_productividad),
            "iup_comercial": float(r.Ranking.iup_comercial),
            "iup_coaching": float(r.Ranking.iup_coaching),
            "iup_capacitacion": float(r.Ranking.iup_capacitacion),
            "iup_consistencia": float(r.Ranking.iup_consistencia),
            "elegible": r.Ranking.elegible,
            "tipo_ranking": r.Ranking.tipo_ranking,
            "fecha_generacion": r.Ranking.fecha_generacion,
        }
        for r in rows
    ]
    return {"items": items, "total": total, "page": params.page,
            "size": params.size, "pages": max(1, -(-total // params.size))}


@router.get("/regional", response_model=List[dict], summary="Ranking regional multi-país")
def get_ranking_regional(
    ciclo_id: Optional[int] = None,
    top: int = 10,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(
        Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
    )),
):
    """Top N RMs a nivel regional (todos los países combinados)."""
    q = db.query(
        Ranking,
        RepresentanteMedico.nombre.label("rm_nombre"),
        RepresentanteMedico.codigo.label("rm_codigo"),
        Pais.nombre.label("pais_nombre"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == Ranking.rm_id
    ).join(
        Pais, Pais.id == Ranking.pais_id
    ).filter(
        Ranking.tipo_ranking == "REGIONAL",
        Ranking.elegible == True,
    )

    if ciclo_id: q = q.filter(Ranking.ciclo_id == ciclo_id)

    rows = q.order_by(Ranking.posicion.asc()).limit(top).all()
    return [
        {
            "posicion": r.Ranking.posicion,
            "rm_id": r.Ranking.rm_id,
            "rm_codigo": r.rm_codigo,
            "rm_nombre": r.rm_nombre,
            "pais_nombre": r.pais_nombre,
            "iup_total": float(r.Ranking.iup_total),
            "elegible": r.Ranking.elegible,
        }
        for r in rows
    ]


@router.get("/anual", response_model=List[dict], summary="Ranking histórico anual")
def get_ranking_anual(
    pais_id: Optional[int] = None,
    anio: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        Ranking,
        RepresentanteMedico.nombre.label("rm_nombre"),
    ).join(
        RepresentanteMedico, RepresentanteMedico.id == Ranking.rm_id
    ).filter(
        Ranking.tipo_ranking == "ANUAL"
    )

    if pais_id: q = q.filter(Ranking.pais_id == pais_id)

    rows = q.order_by(Ranking.posicion.asc()).all()
    return [
        {
            "posicion": r.Ranking.posicion,
            "rm_id": r.Ranking.rm_id,
            "rm_nombre": r.rm_nombre,
            "iup_total": float(r.Ranking.iup_total),
            "elegible": r.Ranking.elegible,
            "fecha_generacion": r.Ranking.fecha_generacion,
        }
        for r in rows
    ]


@router.post("/generar", response_model=dict, summary="Generar ranking (disparar cálculo)")
def generar_ranking(
    request: RankingRequest,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD)),
):
    """
    Dispara el cálculo de ranking en background.
    El proceso: Recalcular KPIs → Calcular IUP → Evaluar elegibilidad → Ordenar → Guardar.
    """
    from app.services.ranking_service import generar_ranking_task
    background_tasks.add_task(
        generar_ranking_task,
        pais_id=request.pais_id,
        ciclo_id=request.ciclo_id,
        tipo_ranking=request.tipo_ranking,
        db=db,
    )
    return {"message": "Calculo de ranking iniciado en background", "pais_id": request.pais_id, "ciclo_id": request.ciclo_id}
