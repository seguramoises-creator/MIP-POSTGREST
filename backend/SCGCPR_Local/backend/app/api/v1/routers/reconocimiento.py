"""
SCGCPR — Router: Reconocimiento y Premios
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import Reconocimiento, Ranking
from app.models.dimensiones import RepresentanteMedico, Premio
from app.schemas.schemas import ReconocimientoCreate, ReconocimientoResponse

router = APIRouter(prefix="/reconocimiento", tags=["Reconocimiento"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=List[dict], summary="Listar reconocimientos")
def list_reconocimientos(
    pais_id: Optional[int] = None,
    ciclo_id: Optional[int] = None,
    premio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        Reconocimiento,
        RepresentanteMedico.nombre.label("rm_nombre"),
        Premio.nombre.label("premio_nombre"),
        Premio.categoria.label("premio_categoria"),
        Premio.frecuencia.label("premio_frecuencia"),
    ).outerjoin(
        RepresentanteMedico, RepresentanteMedico.id == Reconocimiento.rm_id
    ).join(
        Premio, Premio.id == Reconocimiento.premio_id
    )

    if pais_id: q = q.filter(Reconocimiento.pais_id == pais_id)
    if ciclo_id: q = q.filter(Reconocimiento.ciclo_id == ciclo_id)
    if premio_id: q = q.filter(Reconocimiento.premio_id == premio_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(Reconocimiento.rm_id == current_user.rm_id)

    rows = q.order_by(Reconocimiento.fecha_reconocimiento.desc()).all()
    return [
        {
            "id": r.Reconocimiento.id,
            "rm_nombre": r.rm_nombre,
            "premio_nombre": r.premio_nombre,
            "premio_categoria": r.premio_categoria,
            "frecuencia": r.premio_frecuencia,
            "iup_al_momento": float(r.Reconocimiento.iup_al_momento),
            "posicion_ranking": r.Reconocimiento.posicion_ranking,
            "certificado_generado": r.Reconocimiento.certificado_generado,
            "certificado_url": r.Reconocimiento.certificado_url,
            "fecha_reconocimiento": r.Reconocimiento.fecha_reconocimiento,
        }
        for r in rows
    ]


@router.post("", response_model=ReconocimientoResponse, status_code=201, summary="Crear reconocimiento")
def create_reconocimiento(
    data: ReconocimientoCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD)),
):
    """
    Crea un reconocimiento manual. El certificado PDF se genera en background.
    """
    # Obtener IUP al momento del ranking
    iup = 0
    posicion = None
    if data.rm_id:
        rank = db.query(Ranking).filter(
            Ranking.rm_id == data.rm_id,
            Ranking.pais_id == data.pais_id,
        ).order_by(Ranking.fecha_generacion.desc()).first()
        if rank:
            iup = float(rank.iup_total)
            posicion = rank.posicion

    obj = Reconocimiento(
        **data.model_dump(),
        iup_al_momento=iup,
        posicion_ranking=posicion,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)

    # Generar certificado PDF en background
    from app.services.reconocimiento_service import generar_certificado_pdf
    background_tasks.add_task(generar_certificado_pdf, db=db, reconocimiento_id=obj.id)

    return obj


@router.get("/elegibilidad/{rm_id}", response_model=dict, summary="Evaluar elegibilidad de un RM")
def evaluar_elegibilidad(
    rm_id: int,
    pais_id: int,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """Evalúa si un RM cumple todas las reglas de elegibilidad configuradas."""
    from app.services.elegibilidad_service import evaluar_elegibilidad_rm
    return evaluar_elegibilidad_rm(db=db, rm_id=rm_id, pais_id=pais_id, ciclo_id=ciclo_id)


@router.post("/generar-automatico", response_model=dict, summary="Generar reconocimientos automáticos")
def generar_reconocimientos_automatico(
    pais_id: int,
    ciclo_id: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD)),
):
    """
    Genera automáticamente los reconocimientos para todos los RMs elegibles
    según el ranking y las reglas de premios configuradas.
    """
    from app.services.reconocimiento_service import generar_reconocimientos_automaticos
    background_tasks.add_task(
        generar_reconocimientos_automaticos,
        db=db, pais_id=pais_id, ciclo_id=ciclo_id,
        usuario_id=current_user.id,
    )
    return {"message": "Generación automática de reconocimientos iniciada", "pais_id": pais_id}


@router.get("/{id}/certificado", summary="Descargar certificado PDF")
def get_certificado(
    id: int,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """Descarga el certificado PDF de un reconocimiento."""
    from fastapi.responses import FileResponse
    import os
    obj = db.query(Reconocimiento).filter(Reconocimiento.id == id).first()
    if not obj:
        raise HTTPException(404, "Reconocimiento no encontrado")
    if not obj.certificado_url or not os.path.exists(obj.certificado_url):
        raise HTTPException(404, "Certificado aún no generado")
    return FileResponse(obj.certificado_url, media_type="application/pdf",
                        filename=f"certificado_{id}.pdf")
