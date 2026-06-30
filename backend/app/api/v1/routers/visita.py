"""Router del Módulo de Visita Médica — Fase 1 (Panel Médico).

Prefijo: /visita.  Reutiliza Config.DIM_RM (VM), Config.DIM_Especialidad.
RBAC: el VM (REPRESENTANTE_MEDICO) gestiona su propio panel (auto-filtro por rm_id);
ADMIN/GERENTE ven/gestionan el de cualquier VM.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles, get_current_active_user
from app.models.usuario import Rol
from app.schemas.visita import MedicoVisitaCrear, MedicoVisitaResponse
from app.services import visita_service

router = APIRouter(prefix="/visita", tags=["Visita Médica"])

RequireVisita = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_DISTRITO, Rol.GERENTE_PRODUCTIVIDAD, Rol.REPRESENTANTE_MEDICO))
RequireAnyAuth = Depends(get_current_active_user)


def _rol(u) -> str:
    return u.rol.value if hasattr(u.rol, "value") else str(u.rol)


def _scope_vm(current_user, vm_id: int | None) -> int | None:
    """Un REPRESENTANTE_MEDICO se fuerza a su propio rm_id; los demás pasan vm_id libre."""
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        rm = getattr(current_user, "rm_id", None)
        if not rm:
            raise HTTPException(status_code=403, detail="Tu usuario no está vinculado a un representante (rm_id).")
        return rm
    return vm_id


@router.get("/especialidades", response_model=list[dict])
def listar_especialidades(db: Session = Depends(get_db), current_user=RequireVisita):
    """Catálogo de especialidades (para el selector al registrar médicos)."""
    from app.models.dimensiones import Especialidad
    return [{"id": e.id, "nombre": e.nombre}
            for e in db.query(Especialidad).filter(Especialidad.activo == True)  # noqa: E712
            .order_by(Especialidad.nombre).all()]


@router.get("/vms", response_model=list[dict])
def listar_vms(db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitadores médicos (DIM_RM) — para que ADMIN/GERENTE elijan el panel a ver."""
    from app.models.dimensiones import RepresentanteMedico
    return [{"id": r.id, "nombre": r.nombre}
            for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)  # noqa: E712
            .order_by(RepresentanteMedico.nombre).all()]


@router.get("/medicos", response_model=list[dict])
def listar_medicos(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Panel médico. El VM ve solo el suyo; ADMIN/GERENTE pueden filtrar por ?vm_id=."""
    vm = _scope_vm(current_user, vm_id)
    return visita_service.listar_medicos(db, vm_id=vm)


@router.post("/medicos", response_model=MedicoVisitaResponse, status_code=status.HTTP_201_CREATED)
def crear_medico(datos: MedicoVisitaCrear, db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra un médico nuevo. Si hay posible duplicado y no se confirmó, responde
    409 con la lista de coincidencias (el cliente muestra el aviso y reintenta con
    confirmar_duplicado=true)."""
    # El VM solo registra en su propio panel.
    if _rol(current_user) == "REPRESENTANTE_MEDICO":
        datos.vm_id = _scope_vm(current_user, None)
    try:
        return visita_service.crear_medico(db, datos, getattr(current_user, "id", None))
    except visita_service.DuplicadoMedicoError as e:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={"mensaje": "Posible duplicidad — verificar", "duplicados": e.duplicados},
        )
