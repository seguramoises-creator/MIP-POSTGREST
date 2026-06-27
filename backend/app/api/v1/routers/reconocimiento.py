"""
SCGCPR — Router: Reconocimiento y Premios

REDISEÑO (jun-2026): la fuente pasó de FACT_Reconocimiento/FACT_Ranking
(campos iup_al_momento/posicion/fecha_reconocimiento) a
FACT_ReconocimientoRM/FACT_RankingRM (score_total/posicion_global/
fecha_calculo). Ver hechos.ReconocimientoRM y hechos.RankingRM.
"""
from typing import List, Optional
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Rol
from app.models.hechos import ReconocimientoRM, RankingRM
from app.models.dimensiones import RepresentanteMedico, Premio
from app.schemas.schemas import ReconocimientoCreate, ReconocimientoResponse

router = APIRouter(prefix="/reconocimiento", tags=["Reconocimiento"])
AnyAuth = Depends(get_current_active_user)


@router.get("", response_model=List[dict], summary="Listar reconocimientos")
def list_reconocimientos(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    premio_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    q = db.query(
        ReconocimientoRM,
        RepresentanteMedico.nombre.label("rm_nombre"),
        Premio.nombre.label("premio_nombre"),
        Premio.categoria.label("premio_categoria"),
        Premio.frecuencia.label("premio_frecuencia"),
    ).outerjoin(
        RepresentanteMedico, RepresentanteMedico.id == ReconocimientoRM.rm_id
    ).join(
        Premio, Premio.id == ReconocimientoRM.premio_id
    )

    if pais_codigo: q = q.filter(ReconocimientoRM.pais_codigo == pais_codigo)
    if ciclo_id: q = q.filter(ReconocimientoRM.ciclo_id == ciclo_id)
    if premio_id: q = q.filter(ReconocimientoRM.premio_id == premio_id)
    if current_user.rol == Rol.REPRESENTANTE_MEDICO and current_user.rm_id:
        q = q.filter(ReconocimientoRM.rm_id == current_user.rm_id)

    rows = q.order_by(ReconocimientoRM.fecha_calculo.desc()).all()
    return [
        {
            "id": r.ReconocimientoRM.id,
            "rm_nombre": r.rm_nombre,
            "premio_nombre": r.premio_nombre,
            "premio_categoria": r.premio_categoria,
            "frecuencia": r.premio_frecuencia,
            "score_total": float(r.ReconocimientoRM.score_total),
            "posicion_ranking": r.ReconocimientoRM.posicion_ranking,
            "posicion_linea": r.ReconocimientoRM.posicion_linea,
            "certificado_generado": r.ReconocimientoRM.certificado_generado,
            "certificado_url": r.ReconocimientoRM.certificado_url,
            "fecha_calculo": r.ReconocimientoRM.fecha_calculo,
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
    # Obtener score y posición al momento, desde el ranking vigente del RM
    score = 0
    posicion = None
    posicion_linea = None
    linea_id = None
    gerente_id = data.gerente_id
    if data.rm_id:
        rank = db.query(RankingRM).filter(
            RankingRM.rm_id == data.rm_id,
            RankingRM.pais_codigo == data.pais_codigo,
        ).order_by(RankingRM.fecha_generacion.desc()).first()
        if rank:
            score = float(rank.score_total)
            posicion = rank.posicion_global
            posicion_linea = rank.posicion_linea
            linea_id = rank.linea_id
            gerente_id = gerente_id or rank.gerente_id

    obj = ReconocimientoRM(
        **data.model_dump(),
        linea_id=linea_id,
        gerente_id=gerente_id,
        score_total=score,
        posicion_ranking=posicion,
        posicion_linea=posicion_linea,
    )
    db.add(obj)
    db.commit()
    db.refresh(obj)

    # Generar certificado PDF en background (la función crea su propia sesión —
    # ver CLAUDE.md §19, nunca reutilizar la sesión de la request en BackgroundTasks)
    from app.services.reconocimiento_service import generar_certificado_pdf
    background_tasks.add_task(generar_certificado_pdf, reconocimiento_id=obj.id)

    return obj


@router.get("/elegibilidad/{rm_id}", response_model=dict, summary="Evaluar elegibilidad de un RM")
def evaluar_elegibilidad(
    rm_id: int,
    pais_codigo: str,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """Evalúa si un RM cumple todas las reglas de elegibilidad configuradas."""
    from app.services.elegibilidad_service import evaluar_elegibilidad_rm
    return evaluar_elegibilidad_rm(db=db, rm_id=rm_id, pais_codigo=pais_codigo, ciclo_id=ciclo_id)


@router.post("/generar-automatico", response_model=dict, summary="Generar reconocimientos automáticos")
def generar_reconocimientos_automatico(
    pais_codigo: str,
    ciclo_id: Optional[int] = None,
    background_tasks: BackgroundTasks = BackgroundTasks(),
    db: Session = Depends(get_db),
    current_user=Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD)),
):
    """
    Genera automáticamente los reconocimientos para todos los RMs elegibles
    según el ranking y las reglas de premios configuradas.

    Nota: si `ciclo_id` corresponde a un ciclo CERRADO, el motor (ver
    reconocimiento_service.generar_reconocimientos_automaticos) aborta sin
    crear ni modificar nada — regla de negocio "solo ciclo abierto".
    """
    # La función crea su propia sesión de BD (BackgroundTask — ver CLAUDE.md §19)
    from app.services.reconocimiento_service import generar_reconocimientos_automaticos
    background_tasks.add_task(
        generar_reconocimientos_automaticos,
        pais_codigo=pais_codigo, ciclo_id=ciclo_id,
        usuario_id=current_user.id,
    )
    return {"message": "Generación automática de reconocimientos iniciada", "pais_codigo": pais_codigo}


@router.get("/{id}/certificado", summary="Descargar certificado PDF")
def get_certificado(
    id: int,
    db: Session = Depends(get_db),
    current_user=AnyAuth,
):
    """Descarga el certificado PDF de un reconocimiento."""
    from fastapi.responses import FileResponse
    import os
    obj = db.query(ReconocimientoRM).filter(ReconocimientoRM.id == id).first()
    if not obj:
        raise HTTPException(404, "Reconocimiento no encontrado")
    if not obj.certificado_url or not os.path.exists(obj.certificado_url):
        raise HTTPException(404, "Certificado aún no generado")
    return FileResponse(obj.certificado_url, media_type="application/pdf",
                        filename=f"certificado_{id}.pdf")
