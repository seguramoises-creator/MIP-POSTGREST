"""Router del Módulo de Farmacias — Task 5 (plan `2026-07-22-modulo-farmacias.md`).

Prefijo: /farmacias. Espejo del módulo de Médicos (maestro país-level + panel del VM +
aprobación VM→GD). Servicios ya implementados (Tasks 1-4):
    - `app.services.maestro_farmacia_service`   (nombre_completo, anti-dup, bloqueantes)
    - `app.services.farmacia_aprobacion_service` (Acciones A/B, aprobar/rechazar/bandeja)

RBAC (matriz, `app.core.authz`): 3 recursos NUEVOS (ver `matrix.py`/`constantes.py`):
    - `farmacia.panel`   — VM lee/solicita su panel (own); GD lee su equipo (team); el
      resto de gerencias (salvo FINANZAS) leen todo (all). Espejo de `medico.panel`.
    - `farmacia.aprobar` — SOLO Gerente de Distrito (su equipo) + ADMIN aprueban/rechazan.
    - `farmacia.maestro` — SOLO GERENTE_PRODUCTIVIDAD + ADMIN administran el maestro
      directo (mismo patrón que `lsii.admin`/`etl.cargar`).

Auto-scope (mismo patrón que `cobertura_predictiva.py`): un REPRESENTANTE_MEDICO se
fuerza a su propio `rm_id`; un GERENTE_DISTRITO se fuerza a su propio `gerente_id`
(403 si no tiene uno asignado); el resto de roles con acceso pasan el valor libre.
"""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Response, UploadFile, File, status
from sqlalchemy.orm import Session

from app.core.deps import get_db
from app.core.authz.deps import require as _require_authz
from app.core.authz.constantes import Accion, Recurso
from app.models.usuario import Rol, Usuario
from app.models.dimensiones import Farmacia, RepresentanteMedico, Gerente
from app.models.visita import FarmaciaVisita, FactVisitaFarmacia
from app.services import maestro_farmacia_service as maestro_svc
from app.services import farmacia_aprobacion_service as aprobacion_svc
from app.services import visita_farmacia_service as visita_svc
from app.services import cobertura_farmacia_service as cobertura_svc
from app.schemas.schemas_farmacia import (
    FarmaciaMaestroCrear, FarmaciaMaestroActualizar, FarmaciaMaestroResponse,
    PanelAgregarIn, PanelCrearIn, PanelResponse, RechazarIn, EditarAprobarIn,
    VisitaFarmaciaRegistrar,
)

router = APIRouter(prefix="/farmacias", tags=["Farmacias"])

ReadPanel = Depends(_require_authz(Accion.READ, Recurso.FARMACIA_PANEL))
RegistrarPanel = Depends(_require_authz(Accion.REGISTER, Recurso.FARMACIA_PANEL))
ReadAprobar = Depends(_require_authz(Accion.READ, Recurso.FARMACIA_APROBAR))
AprobarGuard = Depends(_require_authz(Accion.APPROVE, Recurso.FARMACIA_APROBAR))
ReadMaestro = Depends(_require_authz(Accion.READ, Recurso.FARMACIA_MAESTRO))
ConfigurarMaestro = Depends(_require_authz(Accion.CONFIGURE, Recurso.FARMACIA_MAESTRO))


# ─────────────────────────────────────────────────────────────────────────
# Auto-scope (mismo patrón que cobertura_predictiva.py / visita.py)
# ─────────────────────────────────────────────────────────────────────────

def _scope_vm(current_user: Usuario, vm_id: Optional[int]) -> Optional[int]:
    """Un REPRESENTANTE_MEDICO se fuerza a su propio rm_id; los demás pasan vm_id libre."""
    if current_user.rol == Rol.REPRESENTANTE_MEDICO:
        rm = getattr(current_user, "rm_id", None)
        if not rm:
            raise HTTPException(403, "Tu usuario no está vinculado a un representante (rm_id).")
        return rm
    return vm_id


def _pais_de_vm(db: Session, vm_id: int) -> Optional[str]:
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm_id).first()
    return rm.pais_codigo if rm else None


def _resolver_pais(db: Session, current_user: Usuario, pais_codigo: Optional[str]) -> str:
    """Para VM sin pais_codigo explícito, lo resuelve de su propio RM. Para el resto,
    pais_codigo es obligatorio en la query."""
    if pais_codigo:
        return pais_codigo
    if current_user.rol == Rol.REPRESENTANTE_MEDICO:
        rm_id = getattr(current_user, "rm_id", None)
        pais = _pais_de_vm(db, rm_id) if rm_id else None
        if pais:
            return pais
    raise HTTPException(400, "Indica pais_codigo.")


def _panel_del_gd(db: Session, panel: FarmaciaVisita) -> Optional[int]:
    """gerente_id del VM dueño de este registro de panel (None si el VM no tiene equipo)."""
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == panel.vm_id).first()
    return rm.gerente_id if rm else None


def _verificar_alcance_gd(current_user: Usuario, panel: FarmaciaVisita, db: Session) -> None:
    """GERENTE_DISTRITO solo puede actuar sobre solicitudes de su propio equipo. ADMIN
    (y cualquier otro rol que haya pasado el guard `require(APPROVE, ...)`) sin restricción
    adicional — hoy solo GD y ADMIN tienen esa acción en la matriz."""
    if current_user.rol == Rol.GERENTE_DISTRITO:
        if not current_user.gerente_id:
            raise HTTPException(403, "Tu usuario no tiene un gerente_id asignado.")
        if _panel_del_gd(db, panel) != current_user.gerente_id:
            raise HTTPException(403, "Esta solicitud no pertenece a tu equipo.")


def _cargar_panel_pendiente(db: Session, panel_id: int) -> FarmaciaVisita:
    panel = db.query(FarmaciaVisita).filter(FarmaciaVisita.id == panel_id).first()
    if panel is None:
        raise HTTPException(404, f"Solicitud de panel ID={panel_id} no encontrada.")
    return panel


def _raise_negocio(e: ValueError) -> None:
    """Traduce un ValueError de negocio del servicio de aprobación a su HTTP correspondiente."""
    msg = str(e)
    if "no existe" in msg.lower():
        raise HTTPException(status.HTTP_404_NOT_FOUND, msg)
    if "motivo" in msg.lower():
        raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)
    # "no tiene una alta pendiente" / "ya está en tu panel": conflicto de estado
    raise HTTPException(status.HTTP_409_CONFLICT, msg)


def _raise_captura_error(e: ValueError) -> None:
    """Traduce un ValueError del registro de visita a farmacia: F22 (panel no
    aprobado/maestro no activa) y ciclo cerrado son conflictos de estado (409);
    el resto (p.ej. 'No hay ciclo activo') son errores de negocio (400)."""
    if isinstance(e, visita_svc.PanelNoAprobadoError):
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    msg = str(e)
    if "cerrado" in msg.lower() or "solo lectura" in msg.lower():
        raise HTTPException(status.HTTP_409_CONFLICT, msg)
    raise HTTPException(status.HTTP_400_BAD_REQUEST, msg)


# ─────────────────────────────────────────────────────────────────────────
# Búsqueda anti-dup del maestro (F25/F09) — VM+
# ─────────────────────────────────────────────────────────────────────────

@router.get("/maestro/buscar", response_model=dict, summary="Buscar en el maestro (anti-dup)")
def buscar_maestro(
    cadena: Optional[str] = Query(None),
    sucursal: Optional[str] = Query(None),
    nombre: Optional[str] = Query(None, description="Si la farmacia no es cadena, buscar por nombre"),
    pais_codigo: Optional[str] = Query(None, description="Requerido salvo para VM (se resuelve de su propio país)"),
    db: Session = Depends(get_db),
    current_user: Usuario = ReadPanel,
):
    """Búsqueda usada por el formulario del VM antes de dar de alta (F25): si no hay
    coincidencia dura, el frontend habilita el formulario de creación (Acción B)."""
    pais = _resolver_pais(db, current_user, pais_codigo)
    dups = maestro_svc.detectar_duplicados(
        db, pais, cadena=cadena or nombre, sucursal=sucursal or "")
    return {"duros": dups["duros"], "existe": bool(dups["duros"])}


# ─────────────────────────────────────────────────────────────────────────
# Panel del VM — Acciones A/B + lectura
# ─────────────────────────────────────────────────────────────────────────

@router.post("/panel/agregar", response_model=PanelResponse, status_code=status.HTTP_201_CREATED,
             summary="Acción A: agregar al panel una farmacia existente")
def panel_agregar(
    body: PanelAgregarIn,
    vm_id: Optional[int] = Query(None, description="Solo ADMIN puede indicar otro VM"),
    db: Session = Depends(get_db),
    current_user: Usuario = RegistrarPanel,
):
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(400, "Indica el VM (vm_id).")
    try:
        panel = aprobacion_svc.solicitar_agregar_al_panel(
            db, vm_id=vm, maestro_farmacia_id=body.maestro_farmacia_id,
            usuario_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    return _panel_a_response(panel)


@router.post("/panel/crear", response_model=PanelResponse, status_code=status.HTTP_201_CREATED,
             summary="Acción B: dar de alta una farmacia nueva (bloqueantes + anti-dup)")
def panel_crear(
    body: PanelCrearIn,
    vm_id: Optional[int] = Query(None, description="Solo ADMIN puede indicar otro VM"),
    db: Session = Depends(get_db),
    current_user: Usuario = RegistrarPanel,
):
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(400, "Indica el VM (vm_id).")
    try:
        panel = aprobacion_svc.solicitar_crear(
            db, vm_id=vm, datos=body.model_dump(exclude_unset=True), usuario_id=current_user.id)
    except maestro_svc.DuplicadoDuroError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return _panel_a_response(panel)


def _panel_a_response(panel: FarmaciaVisita) -> PanelResponse:
    return PanelResponse(
        id=panel.id, maestro_farmacia_id=panel.maestro_farmacia_id,
        estado_aprobacion=panel.estado_aprobacion, vm_id=panel.vm_id,
        fecha_solicitud=panel.fecha_solicitud, fecha_aprobacion=panel.fecha_aprobacion,
        motivo=panel.motivo,
    )


@router.get("/panel", response_model=list, summary="Panel de farmacias de un VM")
def panel_listar(
    vm_id: Optional[int] = Query(None, description="VM auto-scope; otros roles pueden filtrar"),
    incluir_inactivos: bool = Query(False),
    db: Session = Depends(get_db),
    current_user: Usuario = ReadPanel,
):
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(400, "Indica el VM (vm_id).")

    if current_user.rol == Rol.GERENTE_DISTRITO:
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm).first()
        if not rm or not current_user.gerente_id or rm.gerente_id != current_user.gerente_id:
            raise HTTPException(403, "Este VM no pertenece a tu equipo.")

    q = db.query(FarmaciaVisita).filter(FarmaciaVisita.vm_id == vm)
    if not incluir_inactivos:
        q = q.filter(FarmaciaVisita.activo == True)  # noqa: E712

    paneles = q.order_by(FarmaciaVisita.fecha_registro.desc()).all()
    if not paneles:
        return []

    maestro_ids = {p.maestro_farmacia_id for p in paneles}
    maestros = {f.id: f for f in db.query(Farmacia).filter(Farmacia.id.in_(maestro_ids)).all()}

    def _motivo(p: FarmaciaVisita) -> Optional[str]:
        """F26: motivo de rechazo — primero el del panel (siempre lo trae `rechazar()`,
        Acción A o B); si por algún dato legado faltara, cae al `motivo_rechazo` del maestro
        cuando éste quedó RECHAZADA."""
        if p.motivo:
            return p.motivo
        maestro = maestros.get(p.maestro_farmacia_id)
        if maestro is not None and maestro.estado == "RECHAZADA":
            return maestro.motivo_rechazo
        return None

    return [
        {
            "panel_id": p.id,
            "maestro_farmacia_id": p.maestro_farmacia_id,
            "nombre_completo": (maestros[p.maestro_farmacia_id].nombre_completo
                                if p.maestro_farmacia_id in maestros else None),
            "direccion": (maestros[p.maestro_farmacia_id].direccion
                         if p.maestro_farmacia_id in maestros else None),
            "encargado": (maestros[p.maestro_farmacia_id].encargado
                         if p.maestro_farmacia_id in maestros else None),
            "estado_maestro": (maestros[p.maestro_farmacia_id].estado
                              if p.maestro_farmacia_id in maestros else None),
            "estado_aprobacion": p.estado_aprobacion,
            "ciclos_sin_visita": p.ciclos_sin_visita,
            "motivo": _motivo(p),
        }
        for p in paneles
    ]


# ─────────────────────────────────────────────────────────────────────────
# Cobertura interna de Farmacias (Task 7) — AD-HOC, SIN F1/F2, COEXISTE con el SFA.
# Reusa el recurso farmacia.panel (acción READ) — no se crea ningún recurso nuevo.
# ─────────────────────────────────────────────────────────────────────────

@router.get("/cobertura", response_model=dict,
            summary="Cobertura interna de farmacias (AD-HOC, sin F1/F2; NO se cablea al Score)")
def cobertura_farmacias(
    ciclo_id: int = Query(..., description="Ciclo a evaluar"),
    rm_id: Optional[int] = Query(None, description="VM auto-scope; GD/ADMIN pueden filtrar un VM puntual"),
    db: Session = Depends(get_db),
    current_user: Usuario = ReadPanel,
):
    """
    cobertura = (farmacias del panel APROBADO+activas del VM con >=1 visita
    ejecutada en el ciclo) / (farmacias del panel APROBADO+activas del VM).
    F22: PENDIENTE_APROBACION/PENDIENTE_ALTA no cuentan. Coexiste con el SFA:
    esto NO alimenta `COB_FARMACIAS` del Score/Ranking (sigue viniendo del SFA).
    """
    vm = _scope_vm(current_user, rm_id)

    if current_user.rol == Rol.GERENTE_DISTRITO:
        if not current_user.gerente_id:
            raise HTTPException(403, "Tu usuario no tiene un gerente_id asignado.")
        if vm:
            rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == vm).first()
            if not rm or rm.gerente_id != current_user.gerente_id:
                raise HTTPException(403, "Este VM no pertenece a tu equipo.")
            return cobertura_svc.cobertura_rm(db, vm, ciclo_id)
        return {"equipo": cobertura_svc.cobertura_equipo(db, current_user.gerente_id, ciclo_id)}

    if vm:
        return cobertura_svc.cobertura_rm(db, vm, ciclo_id)

    # ADMIN/gerencias sin filtrar: agrega la cobertura de todos los distritos.
    equipo: list = []
    for g in db.query(Gerente).all():
        equipo.extend(cobertura_svc.cobertura_equipo(db, g.id, ciclo_id))
    return {"equipo": equipo}


# ─────────────────────────────────────────────────────────────────────────
# Registro de visita a Farmacia (Task 6) — AD-HOC, guard F22 + ciclo abierto.
# Tabla paralela Visita.FactVisitaFarmacia (Opción A): se registra en el MISMO
# módulo de Visita (mismo VM, misma auto-scope), reusando el recurso
# farmacia.panel con la acción REGISTER — no se crea ningún recurso nuevo.
# ─────────────────────────────────────────────────────────────────────────

def _cargar_panel_del_vm(db: Session, panel_id: int, vm_id: int) -> FarmaciaVisita:
    """Carga el registro de panel y verifica que pertenece al VM que llama
    (403 si no) — mismo criterio de auto-scope que el resto del router."""
    panel = db.query(FarmaciaVisita).filter(FarmaciaVisita.id == panel_id).first()
    if panel is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, f"Panel de farmacia ID={panel_id} no encontrado.")
    if panel.vm_id != vm_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Esta farmacia no pertenece a tu panel.")
    return panel


@router.post("/{panel_id}/visita", response_model=dict, status_code=status.HTTP_201_CREATED,
             summary="Registrar visita a una farmacia del panel (AD-HOC, guard F22)")
def registrar_visita_farmacia(
    panel_id: int,
    body: VisitaFarmaciaRegistrar,
    vm_id: Optional[int] = Query(None, description="Solo ADMIN puede indicar otro VM"),
    db: Session = Depends(get_db),
    current_user: Usuario = RegistrarPanel,
):
    vm = _scope_vm(current_user, vm_id)
    if not vm:
        raise HTTPException(400, "Indica el VM (vm_id).")
    panel = _cargar_panel_del_vm(db, panel_id, vm)
    try:
        v = visita_svc.registrar_visita(db, vm, panel, body, usuario_id=current_user.id)
    except ValueError as e:
        _raise_captura_error(e)
    return {
        "id": v.id, "vm_id": v.vm_id, "ciclo_id": v.ciclo_id, "farmacia_id": v.farmacia_id,
        "ejecutada": v.ejecutada,
        "hora": v.fecha_hora.isoformat() if v.fecha_hora else None,
    }


@router.post("/{visita_id}/foto", response_model=dict, status_code=status.HTTP_201_CREATED,
             summary="Subir foto de una visita a farmacia (JPEG/PNG, máx 3 MB)")
async def subir_foto_visita_farmacia(
    visita_id: int, archivo: UploadFile = File(...),
    db: Session = Depends(get_db), current_user: Usuario = RegistrarPanel,
):
    contenido = await archivo.read()
    try:
        visita_svc.guardar_foto_visita(db, visita_id, contenido, archivo.content_type or "image/jpeg")
    except ValueError as e:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, str(e))
    return {"id": visita_id, "bytes": len(contenido)}


@router.get("/{visita_id}/foto", summary="Obtener la foto de una visita a farmacia")
def obtener_foto_visita_farmacia(
    visita_id: int, db: Session = Depends(get_db), current_user: Usuario = ReadPanel,
):
    data = visita_svc.obtener_foto_visita(db, visita_id)
    if data is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Sin foto")
    contenido, mime = data
    return Response(content=contenido, media_type=mime)


# ─────────────────────────────────────────────────────────────────────────
# Bandeja de aprobación (GD/ADMIN)
# ─────────────────────────────────────────────────────────────────────────

@router.get("/aprobacion/pendientes", response_model=list, summary="Bandeja del GD: altas pendientes")
def aprobacion_pendientes(
    gerente_id: Optional[int] = Query(None, description="GD auto-scope; ADMIN puede indicarlo u omitirlo (todas)"),
    db: Session = Depends(get_db),
    current_user: Usuario = ReadAprobar,
):
    if current_user.rol == Rol.GERENTE_DISTRITO:
        if not current_user.gerente_id:
            raise HTTPException(403, "Tu usuario no tiene un gerente_id asignado.")
        gerente_id = current_user.gerente_id

    if gerente_id is not None:
        return aprobacion_svc.pendientes_del_gd(db, gerente_id)

    # ADMIN sin filtrar: agrega la bandeja de todos los distritos.
    salida: list = []
    for g in db.query(Gerente).all():
        salida.extend(aprobacion_svc.pendientes_del_gd(db, g.id))
    return salida


@router.post("/aprobacion/{panel_id}/aprobar", response_model=PanelResponse, summary="Aprobar una solicitud")
def aprobacion_aprobar(
    panel_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = AprobarGuard,
):
    panel = _cargar_panel_pendiente(db, panel_id)
    _verificar_alcance_gd(current_user, panel, db)
    try:
        panel = aprobacion_svc.aprobar(db, panel_id, usuario_id=current_user.id)
    except ValueError as e:
        _raise_negocio(e)
    return _panel_a_response(panel)


@router.post("/aprobacion/{panel_id}/rechazar", response_model=PanelResponse, summary="Rechazar una solicitud")
def aprobacion_rechazar(
    panel_id: int,
    body: RechazarIn,
    db: Session = Depends(get_db),
    current_user: Usuario = AprobarGuard,
):
    panel = _cargar_panel_pendiente(db, panel_id)
    _verificar_alcance_gd(current_user, panel, db)
    try:
        panel = aprobacion_svc.rechazar(db, panel_id, body.motivo, usuario_id=current_user.id)
    except ValueError as e:
        _raise_negocio(e)
    return _panel_a_response(panel)


@router.post("/aprobacion/{panel_id}/editar-aprobar", response_model=PanelResponse,
             summary="Corregir el maestro y aprobar en el mismo paso")
def aprobacion_editar_y_aprobar(
    panel_id: int,
    body: EditarAprobarIn,
    db: Session = Depends(get_db),
    current_user: Usuario = AprobarGuard,
):
    panel = _cargar_panel_pendiente(db, panel_id)
    _verificar_alcance_gd(current_user, panel, db)
    cambios = body.model_dump(exclude_unset=True)
    try:
        panel = aprobacion_svc.editar_y_aprobar(db, panel_id, cambios, usuario_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return _panel_a_response(panel)


# ─────────────────────────────────────────────────────────────────────────
# Maestro — CRUD directo (ADMIN/GERENTE_PRODUCTIVIDAD, sin aprobación)
# ─────────────────────────────────────────────────────────────────────────

@router.get("/maestro", response_model=list[FarmaciaMaestroResponse], summary="Listado del maestro")
def maestro_listar(
    pais_codigo: Optional[str] = Query(None),
    estado: Optional[str] = Query(None),
    q: Optional[str] = Query(None, description="Búsqueda libre por nombre_completo"),
    db: Session = Depends(get_db),
    current_user: Usuario = ReadMaestro,
):
    query = db.query(Farmacia)
    if pais_codigo:
        query = query.filter(Farmacia.pais_codigo == pais_codigo)
    if estado:
        query = query.filter(Farmacia.estado == estado)
    if q:
        query = query.filter(Farmacia.nombre_completo.ilike(f"%{q}%"))
    return query.order_by(Farmacia.nombre_completo).all()


@router.get("/maestro/{farmacia_id}", response_model=FarmaciaMaestroResponse, summary="Ficha del maestro")
def maestro_obtener(
    farmacia_id: int,
    db: Session = Depends(get_db),
    current_user: Usuario = ReadMaestro,
):
    f = db.query(Farmacia).filter(Farmacia.id == farmacia_id).first()
    if not f:
        raise HTTPException(404, f"Farmacia ID={farmacia_id} no encontrada.")
    return f


@router.post("/maestro", response_model=FarmaciaMaestroResponse, status_code=status.HTTP_201_CREATED,
            summary="Alta directa en el maestro (sin aprobación)")
def maestro_crear(
    body: FarmaciaMaestroCrear,
    pais_codigo: str = Query(..., description="País de la farmacia"),
    db: Session = Depends(get_db),
    current_user: Usuario = ConfigurarMaestro,
):
    try:
        f = maestro_svc.crear_maestro(
            db, pais_codigo, body.model_dump(exclude_unset=True),
            origen="CONFIG", estado="ACTIVA", usuario_id=current_user.id)
    except maestro_svc.DuplicadoDuroError as e:
        raise HTTPException(status.HTTP_409_CONFLICT, str(e))
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return f


@router.put("/maestro/{farmacia_id}", response_model=FarmaciaMaestroResponse, summary="Editar el maestro")
def maestro_actualizar(
    farmacia_id: int,
    body: FarmaciaMaestroActualizar,
    db: Session = Depends(get_db),
    current_user: Usuario = ConfigurarMaestro,
):
    f = db.query(Farmacia).filter(Farmacia.id == farmacia_id).first()
    if not f:
        raise HTTPException(404, f"Farmacia ID={farmacia_id} no encontrada.")
    try:
        f = maestro_svc.actualizar_maestro(db, f, body.model_dump(exclude_unset=True),
                                           usuario_id=current_user.id)
    except ValueError as e:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(e))
    return f
