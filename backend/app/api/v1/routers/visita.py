"""Router del Módulo de Visita Médica — Fase 1 (Panel Médico).

Prefijo: /visita.  Reutiliza Config.DIM_RM (VM), Config.DIM_Especialidad.
RBAC: el VM (REPRESENTANTE_MEDICO) gestiona su propio panel (auto-filtro por rm_id);
ADMIN/GERENTE ven/gestionan el de cualquier VM.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles, get_current_active_user
from app.models.usuario import Rol
from app.schemas.visita import (
    MedicoVisitaCrear, MedicoVisitaResponse, VisitaRegistrar, VisitaNoVisita,
    _CAUSAS_NO_VISITA,
)
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


@router.get("/cobertura/resumen", response_model=dict)
def cobertura_resumen(ciclo_id: int | None = None, vm_id: int | None = None,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Dashboard de Cobertura: gauges (cobertura/V+R/gap), desglose A/B/C, listas y ruptura.
    El VM ve su propia cobertura; ADMIN/GERENTE ven el equipo o filtran por ?vm_id=."""
    from app.services import visita_cobertura_service
    vm = _scope_vm(current_user, vm_id)
    return visita_cobertura_service.resumen_cobertura(db, ciclo_id, vm)


@router.get("/cobertura/ranking", response_model=dict)
def cobertura_ranking(metrica: str = "cobertura", ciclo_id: int | None = None,
                      db: Session = Depends(get_db), current_user=RequireVisita):
    """Detalle desplegable por visitador: ranking de quién cumple/no el indicador.
    metrica: 'cobertura' | 'completa' | 'sin_visitar'."""
    from app.services import visita_cobertura_service
    return visita_cobertura_service.ranking_visitadores(db, ciclo_id, metrica)


# ── Registro de visita (Parte 4) ──────────────────────────────────────────────
def _vm_registro(current_user, vm_id: int | None) -> int:
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(status_code=400, detail="Indica el visitador (vm_id).")
    return vm


@router.get("/causas", response_model=list[str])
def causas_no_visita(current_user=RequireVisita):
    """Catálogo de causas de no-visita (para el selector)."""
    return sorted(_CAUSAS_NO_VISITA)


@router.get("/mis-visitas-hoy", response_model=list[dict])
def mis_visitas_hoy(vm_id: int | None = None, db: Session = Depends(get_db), current_user=RequireVisita):
    """Visitas registradas hoy por el VM (feed del móvil)."""
    from app.services import visita_registro_service
    return visita_registro_service.visitas_del_dia(db, _vm_registro(current_user, vm_id))


@router.post("/registrar", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_visita(datos: VisitaRegistrar, vm_id: int | None = None,
                     db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra una visita ejecutada. Usa la hora del servidor (ventana 60 min)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "tipo": v.tipo_visita, "hora": v.fecha_hora.isoformat() if v.fecha_hora else None}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/no-visita", response_model=dict, status_code=status.HTTP_201_CREATED)
def registrar_no_visita(datos: VisitaNoVisita, vm_id: int | None = None,
                        db: Session = Depends(get_db), current_user=RequireVisita):
    """Registra una no-visita con su causa (no cuenta como visita, no penaliza cobertura)."""
    from app.services import visita_registro_service
    try:
        v = visita_registro_service.registrar_no_visita(db, _vm_registro(current_user, vm_id), datos, getattr(current_user, "id", None))
        return {"id": v.id, "causa": v.causa_no_visita}
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
