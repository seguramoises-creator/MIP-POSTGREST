"""SCGCPR — Router: Maestro de Médicos · prefix="/medicos".

Fuente única del dato general del médico (país-level). La categorización
(cat.*) y la asignación (Visita.DIM_MedicoVisita) referencian a este maestro.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import Medico
from app.schemas.schemas import (MaestroMedicoCrear, MaestroMedicoActualizar,
                                 MaestroMedicoResponse)
from app.services import maestro_medico_service as svc

router = APIRouter(prefix="/medicos", tags=["Maestro de Médicos"])

RequireLectura = Depends(get_current_active_user)
RequireEscritura = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
RequireSupervisor = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA))


@router.get("/maestro", response_model=list[MaestroMedicoResponse])
def listar(q: str | None = None, especialidad_id: int | None = None,
           provincia_id: int | None = None, estado: str | None = None,
           activo: bool | None = None, skip: int = 0, limit: int = Query(100, le=500),
           db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    query = db.query(Medico)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(func.upper(Medico.nombre).like(like) |
                             func.upper(func.coalesce(Medico.codigo, "")).like(like) |
                             func.upper(func.coalesce(Medico.cedula, "")).like(like))
    if especialidad_id: query = query.filter(Medico.especialidad_id == especialidad_id)
    if provincia_id:    query = query.filter(Medico.provincia_id == provincia_id)
    if estado:          query = query.filter(Medico.estado_validacion == estado)
    if activo is not None: query = query.filter(Medico.activo == activo)
    return query.order_by(Medico.nombre).offset(skip).limit(limit).all()


@router.get("/maestro/kpis")
def kpis(db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    from app.models.visita import MedicoVisita
    total = db.query(func.count(Medico.id)).scalar() or 0
    activos = db.query(func.count(Medico.id)).filter(Medico.activo == True).scalar() or 0  # noqa: E712
    ini_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nuevos = db.query(func.count(Medico.id)).filter(Medico.created_at >= ini_mes).scalar() or 0
    pendientes = db.query(func.count(Medico.id)).filter(Medico.estado_validacion == "PENDIENTE").scalar() or 0
    asignados = {mid for (mid,) in db.query(MedicoVisita.maestro_medico_id)
                 .filter(MedicoVisita.maestro_medico_id.isnot(None)).distinct().all()}
    sin_asig = db.query(func.count(Medico.id)).filter(
        Medico.activo == True, ~Medico.id.in_(asignados or {-1})).scalar() or 0  # noqa: E712
    return {"total": total, "activos": activos, "nuevos_mes": nuevos,
            "sin_asignacion": sin_asig, "pendientes_validacion": pendientes}


@router.get("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def obtener(medico_id: int, db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return m


@router.post("/maestro", response_model=MaestroMedicoResponse, status_code=201)
def crear(datos: MaestroMedicoCrear, db: Session = Depends(get_db),
          current_user: Usuario = RequireEscritura):
    payload = datos.model_dump(exclude={"pais_codigo", "confirmar_duplicado"})
    try:
        return svc.crear_maestro(db, datos.pais_codigo, payload, origen="MANUAL",
                                 confirmar_duplicado=datos.confirmar_duplicado,
                                 usuario_id=current_user.id)
    except svc.DuplicadoDuroError as e:
        raise HTTPException(409, detail={"tipo": "duro",
            "mensaje": "Ya existe un médico con ese exequátur o cédula. No se puede crear.",
            "coincidencias": e.coincidencias})
    except svc.PosibleDuplicadoError as e:
        raise HTTPException(409, detail={"tipo": "blando",
            "mensaje": "Posible médico duplicado (mismo nombre y ubicación). "
                       "Reenvíe con confirmar_duplicado=true para crear de todas formas.",
            "coincidencias": e.coincidencias})


@router.put("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def actualizar(medico_id: int, datos: MaestroMedicoActualizar,
               db: Session = Depends(get_db), current_user: Usuario = RequireSupervisor):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return svc.actualizar_maestro(db, m, datos.model_dump(exclude_unset=True), current_user.id)
