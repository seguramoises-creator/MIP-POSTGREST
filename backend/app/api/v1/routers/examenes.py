"""SCGCPR — Router del Módulo de Exámenes.

Routers exportados:
  router         — prefix="/examenes"   (CRUD de exámenes + endpoints de evaluado)
  intentos_router — prefix="/intentos"  (responder/entregar/reporte por intento_id)

Endpoints de administración (RequireCapacitacion = ADMIN + CAPACITACION):
  POST /examenes                          — Crear examen (borrador)
  GET  /examenes                          — Listar exámenes activos
  GET  /examenes/{id}                     — Obtener examen por ID
  POST /examenes/{id}/publicar            — Publicar examen (RN-02: debe tener ≥1 pregunta)
  POST /examenes/{id}/preguntas           — Agregar pregunta (RN-01: solo borrador, 1 correcta)
  DELETE /examenes/{id}/preguntas/{pid}   — Eliminar pregunta
  PUT  /examenes/{id}/preguntas/orden     — Reordenar preguntas
  POST /examenes/{id}/asignar             — Asignar examen a lista de evaluados (RM/Gerente)

Endpoints de evaluado (RequireAnyAuth — cualquier usuario activo):
  GET  /examenes/mis-pendientes           — Asignaciones pendientes del evaluado logueado
  GET  /examenes/mi-historial             — Historial de intentos del evaluado logueado
  POST /examenes/{id}/iniciar             — Inicia un intento (sin exponer opción correcta)

  POST /intentos/{id}/responder           — Registra una respuesta para una pregunta
  POST /intentos/{id}/entregar            — Entrega el intento y devuelve el reporte (RN-07)
  GET  /intentos/{id}/reporte             — Obtiene el reporte de un intento ya entregado

Scope enforcement:
  - _resolver_evaluado: extrae (tipo, id) del usuario logueado vía rm_id / gerente_id; 403 si ninguno.
  - iniciar/responder/entregar/reporte verifican que la asignación/intento pertenezca al evaluado; 403 si no.
  - La opción correcta NUNCA se expone en /iniciar — solo en /reporte tras entregar (RN-07).

ORDERING NOTE: literal-path routes (mis-pendientes, mi-historial) MUST be declared before
/{examen_id} routes to prevent FastAPI matching the string as an integer path param.
"""
from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db, require_roles
from app.models.exam_models import AsignacionExamen, Examen, IntentoExamen
from app.models.usuario import Rol
from app.schemas.examenes import (
    AsignacionCrear,
    AsignacionResponse,
    ExamenCrear,
    ExamenResponse,
    IntentoIniciado,
    PreguntaCrear,
    PreguntaResponse,
    ReporteIntento,
    RespuestaEnviar,
)
from app.services import examen_intento_service as intento_svc
from app.services import examen_service

# ---------------------------------------------------------------------------
# RBAC constants
# ---------------------------------------------------------------------------

RequireCapacitacion = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION))
RequireAnyAuth = Depends(get_current_active_user)

# ---------------------------------------------------------------------------
# Routers
# ---------------------------------------------------------------------------

router = APIRouter(prefix="/examenes", tags=["Exámenes"])
intentos_router = APIRouter(prefix="/intentos", tags=["Exámenes — Intentos"])


# ---------------------------------------------------------------------------
# Helper: resolve evaluado from logged-in user
# ---------------------------------------------------------------------------

def _resolver_evaluado(current_user):
    """Extrae (evaluado_tipo, evaluado_id) del usuario autenticado.

    Prioriza rm_id (RM) sobre gerente_id (GERENTE).
    Lanza 403 si el usuario no está vinculado a ningún evaluado.
    """
    if getattr(current_user, "rm_id", None):
        return ("RM", current_user.rm_id)
    if getattr(current_user, "gerente_id", None):
        return ("GERENTE", current_user.gerente_id)
    raise HTTPException(
        status_code=status.HTTP_403_FORBIDDEN,
        detail="El usuario no es un evaluado (RM/Gerente): asocia rm_id o gerente_id al usuario.",
    )


def _contexto(request: Request) -> dict:
    """Construye el contexto de dispositivo/conexión desde los headers HTTP."""
    ua = request.headers.get("user-agent", "")
    ua_lower = ua.lower()
    if "mobile" in ua_lower or "android" in ua_lower or "iphone" in ua_lower:
        device_type = "mobile"
    elif "tablet" in ua_lower or "ipad" in ua_lower:
        device_type = "tablet"
    else:
        device_type = "desktop"

    plataforma = "web"
    if "postman" in ua_lower:
        plataforma = "postman"
    elif "curl" in ua_lower:
        plataforma = "curl"

    return {
        "user_agent": ua[:400] if ua else None,
        "device_type": device_type,
        "plataforma": plataforma,
        "ip_cliente": request.client.host if request.client else None,
    }


# ---------------------------------------------------------------------------
# Scope enforcement helper for intentos
# ---------------------------------------------------------------------------

def _verificar_intento_del_evaluado(intento: IntentoExamen, tipo: str, eid: int) -> None:
    """Lanza 403 si el intento no pertenece al evaluado resuelto."""
    if tipo == "RM":
        if intento.evaluado_tipo != "RM" or intento.evaluado_rm_id != eid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El intento no pertenece a este evaluado.",
            )
    else:  # GERENTE
        if intento.evaluado_tipo != "GERENTE" or intento.evaluado_gerente_id != eid:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="El intento no pertenece a este evaluado.",
            )


# ===========================================================================
# /examenes — EVALUADO endpoints (literal paths FIRST — before /{examen_id})
# ===========================================================================

@router.get("/mis-pendientes", response_model=list[AsignacionResponse])
def mis_pendientes(
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Devuelve las asignaciones en estado 'pendiente' para el evaluado logueado."""
    tipo, eid = _resolver_evaluado(current_user)
    return intento_svc.listar_pendientes(db, tipo, eid)


@router.get("/mi-historial", response_model=list[dict])
def mi_historial(
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Devuelve todos los intentos del evaluado logueado, del más reciente al más antiguo."""
    tipo, eid = _resolver_evaluado(current_user)
    intentos = intento_svc.listar_historial(db, tipo, eid)
    return [
        {
            "intento_id": i.id,
            "asignacion_id": i.asignacion_id,
            "fecha_inicio": i.fecha_inicio,
            "fecha_fin": i.fecha_fin,
            "score": float(i.score) if i.score is not None else None,
            "aprobado": i.aprobado,
            "tiempo_usado_seg": i.tiempo_usado_seg,
        }
        for i in intentos
    ]


# ===========================================================================
# /examenes — ADMIN endpoints (parameterized paths after literal paths)
# ===========================================================================

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
        examen_service.eliminar_pregunta(db, examen_id, pregunta_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.put("/{examen_id}/preguntas/orden", status_code=status.HTTP_204_NO_CONTENT)
def reordenar_preguntas(
    examen_id: int,
    orden_ids: list[int],
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    try:
        examen_service.reordenar_preguntas(db, examen_id, orden_ids)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{examen_id}/asignar", response_model=list[AsignacionResponse], status_code=status.HTTP_201_CREATED)
def asignar(
    examen_id: int,
    datos: AsignacionCrear,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    try:
        return examen_service.asignar_examen(
            db, examen_id, datos.evaluados, datos.fecha_limite, datos.intentos_max, datos.notif_activa
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@router.post("/{examen_id}/iniciar", response_model=IntentoIniciado)
def iniciar(
    examen_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Inicia un intento de examen para el evaluado logueado.

    Scope: 403 si no hay asignación pendiente para este evaluado en este examen.
    No-leak: las opciones en la respuesta solo exponen indice_presentado + texto_opcion.
    """
    tipo, eid = _resolver_evaluado(current_user)
    try:
        resultado = intento_svc.iniciar_para_evaluado(db, examen_id, tipo, eid, _contexto(request))
    except PermissionError as e:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return resultado


# ===========================================================================
# /intentos — Evaluado endpoints (responder / entregar / reporte)
# ===========================================================================

@intentos_router.post("/{intento_id}/responder", status_code=status.HTTP_204_NO_CONTENT)
def responder(
    intento_id: int,
    payload: RespuestaEnviar,
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Registra la respuesta del evaluado para una pregunta del intento.

    El cliente envía pregunta_id + indice_presentado (el índice que vio en pantalla).
    El servicio traduce indice_presentado → opcion_id usando el mapa persistido en el intento.
    Scope: 403 si el intento no pertenece al evaluado logueado.
    """
    tipo, eid = _resolver_evaluado(current_user)

    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intento no encontrado")
    _verificar_intento_del_evaluado(intento, tipo, eid)

    if intento.fecha_fin is not None:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="El intento ya fue entregado; no se pueden registrar más respuestas.",
        )

    try:
        intento_svc.registrar_respuesta_presentada(
            db,
            intento_id=intento_id,
            pregunta_id=payload.pregunta_id,
            indice_presentado=payload.indice_presentado,
        )
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@intentos_router.post("/{intento_id}/entregar", response_model=ReporteIntento)
def entregar(
    intento_id: int,
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Entrega el intento, calcula el score y devuelve el reporte completo (RN-07).

    La opción correcta se expone aquí por primera y única vez (feedback obligatorio).
    Scope: 403 si el intento no pertenece al evaluado logueado.
    Anti-doble-entrega: 400 si el intento ya fue entregado.
    """
    tipo, eid = _resolver_evaluado(current_user)

    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intento no encontrado")
    _verificar_intento_del_evaluado(intento, tipo, eid)

    try:
        intento_entregado = intento_svc.entregar_intento(db, intento_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))

    # La entrega ya fue confirmada (commit en entregar_intento). El reporte es
    # opcional: si falla por cualquier razón, devolvemos un payload mínimo válido
    # en lugar de retornar 500 al cliente — la entrega NO debe parecer fallida.
    try:
        reporte = intento_svc.generar_reporte(db, intento_id)
    except Exception:
        # Fallback: construir ReporteIntento mínimo desde el intento ya entregado.
        asignacion = db.query(AsignacionExamen).filter(
            AsignacionExamen.id == intento_entregado.asignacion_id
        ).first()
        examen = (
            db.query(Examen).filter(
                Examen.id == asignacion.examen_id
            ).first()
            if asignacion
            else None
        )
        reporte = {
            "intento_id": intento_entregado.id,
            "examen_nombre": examen.nombre if examen else "",
            "producto": examen.producto if examen else None,
            "score": float(intento_entregado.score or 0),
            "aprobado": bool(intento_entregado.aprobado),
            "nota_minima": examen.nota_minima if examen else 0,
            "correctas": 0,
            "total": 0,
            "fecha_fin": intento_entregado.fecha_fin,
            "respuestas": [],
        }

    return reporte


@intentos_router.get("/{intento_id}/reporte", response_model=ReporteIntento)
def reporte(
    intento_id: int,
    db: Session = Depends(get_db),
    current_user=RequireAnyAuth,
):
    """Devuelve el reporte de un intento ya entregado (RN-07: siempre feedback).

    Scope: 403 si el intento no pertenece al evaluado logueado.
    400 si el intento aún no ha sido entregado.
    """
    tipo, eid = _resolver_evaluado(current_user)

    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Intento no encontrado")
    _verificar_intento_del_evaluado(intento, tipo, eid)

    try:
        return intento_svc.generar_reporte(db, intento_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
