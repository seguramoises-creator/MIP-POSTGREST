"""
SCGCPR — Router: Coaching (Modelo de Ventas MORE)  ·  prefix="/coaching-more"

Hoja de acompañamiento GD→RM. El GD (Gerente de Distrito) es el único que crea/llena;
el RM (VM) solo lee sus hojas y firma. La hoja es INMUTABLE tras guardar (trigger de BD);
las correcciones son una hoja nueva que enmienda a la anterior. Alimenta el KPI Coaching.
"""
from datetime import date
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import RepresentanteMedico
from app.models.coaching_more_models import CoachingItemCatalogo
from app.services import coaching_more_service as svc
from app.services.recalculo_service import CicloCerradoError

router = APIRouter(prefix="/coaching-more", tags=["Coaching (MORE)"])

RequireAuth = Depends(get_current_active_user)
# Crear/llenar: GD (spec). Se amplía a ADMIN/GERENTE_PRODUCTIVIDAD para supervisión/carga.
RequireCrear = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))
RequireKpi = Depends(require_roles(
    Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))


class ItemIn(BaseModel):
    item_catalogo_id: Optional[int] = None
    seccion: str
    item_texto: str
    calificacion: int


class HojaIn(BaseModel):
    rm_id: int
    # fecha_coaching la fija el SERVIDOR (no se acepta del cliente, evita backdating).
    medicos_vistos: Optional[int] = None
    items: list[ItemIn] = []
    fortalezas: str = ""
    areas_perfeccionar: str = ""
    plan_que_haras: str = ""
    plan_como_haras: str = ""
    plan_como_veras: str = ""
    plan_fecha_seguimiento: Optional[date] = None
    rm_acuerdo: str = ""
    rm_justificacion_desacuerdo: Optional[str] = None
    rm_firma_imagen: str = ""
    corrige_a_id: Optional[int] = None
    motivo_correccion: Optional[str] = None
    # atributo poblado por el servidor
    fecha_coaching: Optional[date] = None


@router.get("/catalogo", summary="Ítems MORE (para llenar la hoja)")
def catalogo(db: Session = Depends(get_db), _u: Usuario = RequireAuth):
    filas = (db.query(CoachingItemCatalogo)
             .filter(CoachingItemCatalogo.activo == True)  # noqa: E712
             .order_by(CoachingItemCatalogo.orden_seccion, CoachingItemCatalogo.orden_item).all())
    return [{"id": f.id, "seccion": f.seccion, "orden_seccion": f.orden_seccion,
             "orden_item": f.orden_item, "texto": f.texto} for f in filas]


@router.get("/vms", summary="RMs que el usuario puede evaluar (selector)")
def vms(db: Session = Depends(get_db), current_user: Usuario = RequireCrear):
    q = db.query(RepresentanteMedico).filter(RepresentanteMedico.activo == True)  # noqa: E712
    if current_user.rol == Rol.GERENTE_DISTRITO:
        q = q.filter(RepresentanteMedico.gerente_id == (current_user.gerente_id or -1))
    return [{"id": r.id, "nombre": r.nombre, "email": r.email,
             "coaching_min_dia": r.coaching_min_dia or 5}
            for r in q.order_by(RepresentanteMedico.nombre).all()]


@router.get("/acompanadas-hoy", summary="Visitas acompañadas de HOY del RM (habilita la hoja)")
def acompanadas_hoy(rm_id: int = Query(...), db: Session = Depends(get_db),
                    current_user: Usuario = RequireCrear):
    """Suma de visitas ACOMPAÑADAS por el GD registradas HOY para el RM. La hoja de
    Coaching solo se habilita si esa suma >= `coaching_min_dia` del RM."""
    from datetime import datetime, timezone
    from sqlalchemy import func
    from app.models.visita import VisitaRegistro
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rm_id).first()
    if not rm:
        raise HTTPException(status_code=404, detail="RM no encontrado")
    hoy = datetime.now(timezone.utc).date()
    acompanadas = (db.query(func.count(VisitaRegistro.id))
                   .filter(VisitaRegistro.vm_id == rm_id,
                           VisitaRegistro.ejecutada == True,      # noqa: E712
                           VisitaRegistro.acompanado == True,     # noqa: E712
                           func.date(VisitaRegistro.fecha_hora) == hoy)
                   .scalar() or 0)
    minimo = rm.coaching_min_dia or 5
    return {"rm_id": rm_id, "fecha": hoy.isoformat(), "acompanadas": acompanadas,
            "minimo": minimo, "habilitado": acompanadas >= minimo}


def _guardar(db: Session, current_user: Usuario, datos: HojaIn):
    datos.fecha_coaching = date.today()  # fecha del servidor
    try:
        s = svc.crear_hoja(db, current_user, datos)
    except ValueError as e:
        raise HTTPException(422, str(e))
    return {"id": s.id, "evaluacion_promedio": float(s.evaluacion_promedio),
            "rm_correo_enviado": bool((db.query(RepresentanteMedico.email)
                                       .filter(RepresentanteMedico.id == s.rm_id).scalar() or "").strip())}


@router.post("", summary="Crear hoja de coaching (inmutable)")
def crear(datos: HojaIn, db: Session = Depends(get_db), current_user: Usuario = RequireCrear):
    datos.corrige_a_id = None  # una hoja normal no corrige a nadie
    return _guardar(db, current_user, datos)


@router.post("/{sesion_id}/correccion", summary="Crear hoja de corrección (enmienda a otra)")
def corregir(sesion_id: int, datos: HojaIn, db: Session = Depends(get_db),
             current_user: Usuario = RequireCrear):
    datos.corrige_a_id = sesion_id
    return _guardar(db, current_user, datos)


@router.get("", summary="Listar hojas (según rol)")
def listar(rm_id: Optional[int] = None, ciclo_id: Optional[int] = None,
           db: Session = Depends(get_db), current_user: Usuario = RequireAuth):
    return svc.listar_hojas(db, current_user, rm_id=rm_id, ciclo_id=ciclo_id)


@router.get("/kpi", summary="KPI Coaching (por ciclo, equipo y GD)")
def kpi(ciclo_id: Optional[int] = None, pais_codigo: Optional[str] = None,
        db: Session = Depends(get_db), _u: Usuario = RequireKpi):
    return svc.kpi_coaching(db, ciclo_id, pais_codigo)


RequireConsolidar = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


@router.post("/consolidar", summary="Consolidar el Coaching MORE al KPI Coaching del Score")
def consolidar(
    destino: str = Query(..., description="'coaching' (FACT_Coaching) | 'indicador' (EVAL_COACHING)"),
    ciclo_id: int = Query(..., description="Ciclo ABIERTO a consolidar"),
    pais_codigo: str = Query(..., description="País, ej. DO"),
    db: Session = Depends(get_db), _u: Usuario = RequireConsolidar,
):
    """Vuelca los promedios MORE del ciclo hacia el flujo que alimenta el Score.
    Idempotente; solo opera sobre el ciclo abierto y dispara el recálculo."""
    from app.services import coaching_more_consolidacion as cons
    if destino not in ("coaching", "indicador"):
        raise HTTPException(422, "destino debe ser 'coaching' o 'indicador'.")
    try:
        if destino == "coaching":
            return cons.consolidar_fact_coaching(db, ciclo_id, pais_codigo)
        return cons.consolidar_indicador(db, ciclo_id, pais_codigo)
    except CicloCerradoError as e:
        raise HTTPException(409, str(e))
    except ValueError as e:
        raise HTTPException(422, str(e))


@router.get("/{sesion_id}", summary="Detalle de una hoja")
def detalle(sesion_id: int, db: Session = Depends(get_db), current_user: Usuario = RequireAuth):
    try:
        h = svc.obtener_hoja(db, sesion_id, current_user)
    except PermissionError as e:
        raise HTTPException(403, str(e))
    if not h:
        raise HTTPException(404, "Hoja de coaching no encontrada.")
    return h
