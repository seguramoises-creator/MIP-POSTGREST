"""SCGCPR — Router del Módulo de Exámenes.

POST /examenes                          — Crear examen (borrador)
GET  /examenes                          — Listar exámenes activos
GET  /examenes/{id}                     — Obtener examen por ID
POST /examenes/{id}/publicar            — Publicar examen (RN-02: debe tener ≥1 pregunta)
POST /examenes/{id}/preguntas           — Agregar pregunta (RN-01: solo borrador, 1 correcta)
DELETE /examenes/{id}/preguntas/{pid}   — Eliminar pregunta
PUT  /examenes/{id}/preguntas/orden     — Reordenar preguntas

RBAC: RequireCapacitacion = ADMIN + CAPACITACION.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.usuario import Rol
from app.schemas.examenes import ExamenCrear, ExamenResponse, PreguntaCrear, PreguntaResponse
from app.services import examen_service

router = APIRouter(prefix="/examenes", tags=["Exámenes"])

RequireCapacitacion = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION))


@router.post("", response_model=ExamenResponse, status_code=status.HTTP_201_CREATED)
def crear(
    datos: ExamenCrear,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    return examen_service.crear_examen(db, datos, creado_por_usuario_id=current_user.id)


@router.get("", response_model=list[ExamenResponse])
def listar(
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    return examen_service.listar_examenes(db)


@router.get("/{examen_id}", response_model=ExamenResponse)
def obtener(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    examen = examen_service.obtener_examen(db, examen_id)
    if examen is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Examen no encontrado")
    return examen


@router.post("/{examen_id}/publicar", response_model=ExamenResponse)
def publicar(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    try:
        return examen_service.publicar_examen(db, examen_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{examen_id}/preguntas", response_model=PreguntaResponse, status_code=status.HTTP_201_CREATED)
def agregar_pregunta(
    examen_id: int,
    datos: PreguntaCrear,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    try:
        return examen_service.agregar_pregunta(db, examen_id, datos)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.delete("/{examen_id}/preguntas/{pregunta_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_pregunta(
    examen_id: int,
    pregunta_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    try:
        examen_service.eliminar_pregunta(db, pregunta_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{examen_id}/preguntas/orden", status_code=status.HTTP_204_NO_CONTENT)
def reordenar_preguntas(
    examen_id: int,
    orden_ids: list[int],
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    examen_service.reordenar_preguntas(db, examen_id, orden_ids)
