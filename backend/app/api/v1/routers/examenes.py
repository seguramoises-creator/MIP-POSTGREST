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

Endpoints de generación con IA (RequireCapacitacion):
  POST /examenes/generar-ia               — Crea examen borrador vía IA y lanza job background
  GET  /examenes/generar-ia/{job_id}      — Estado del job + cantidad de preguntas generadas

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

ORDERING NOTE: literal-path routes (mis-pendientes, mi-historial, generar-ia, generar-ia/{job_id})
MUST be declared before /{examen_id} routes to prevent FastAPI matching the string as an integer
path param.  generar-ia/{job_id} is safe even though job_id is an int because FastAPI does not
confuse it with /{examen_id} — they differ in the literal prefix segment "generar-ia/".
"""
import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, File, Form, HTTPException, Request, UploadFile, status
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, get_db, require_roles
from app.models.exam_models import AsignacionExamen, Examen, FuenteIA, IntentoExamen, Pregunta
from app.models.usuario import Rol
from app.schemas.examenes import (
    AsignacionCrear,
    AsignacionResponse,
    ExamenCrear,
    ExamenResponse,
    GenerarIAResponse,
    IntentoIniciado,
    JobIAEstado,
    PreguntaCrear,
    PreguntaResponse,
    PreguntaConOpcionesResponse,
    ReporteIntento,
    RespuestaEnviar,
    CalificarRespuesta,
)
from app.services import examen_intento_service as intento_svc
from app.services import examen_ia_service
from app.services import examen_service

# Reuse safe-filename helper from the ETL router (UUID-based, prevents Path Traversal)
from app.api.v1.routers.etl import _safe_filename
from app.core.config import settings

# Upload directory (mirrors ETL pattern; created at startup if absent)
UPLOAD_DIR = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "uploads", "ia_fuentes")

TIPOS_ARCHIVO_IA = {"pdf", "docx", "pptx", "texto"}
EXTENSIONES_IA = {".pdf", ".docx", ".pptx", ".txt"}

# Magic-byte signatures for the IA file types.
# Each extension maps to a tuple of accepted byte prefixes (checked against
# the first 4 bytes of the uploaded content).  .txt has no binary signature —
# we accept any content but optionally reject NUL-containing data as a hint
# that a binary file was renamed to .txt.
_MAGIC_IA: dict[str, tuple[bytes, ...] | None] = {
    ".pdf":  (b"%PDF",),
    ".docx": (b"PK\x03\x04",),   # OOXML = ZIP
    ".pptx": (b"PK\x03\x04",),   # OOXML = ZIP
    ".txt":  None,                # no binary signature; accepted unconditionally
}


def _validar_magic_bytes_ia(content: bytes, ext: str) -> bool:
    """Validates file magic bytes for IA-accepted types.

    Returns True if the content is consistent with the given extension:
    - .pdf  → must start with b"%PDF"
    - .docx / .pptx → must start with b"PK\\x03\\x04" (ZIP/OOXML)
    - .txt  → accepted as long as no NUL bytes in the first 1024 bytes
              (rejects binaries accidentally renamed to .txt)
    - any other extension → False (caller should have already blocked it)
    """
    sigs = _MAGIC_IA.get(ext)
    if sigs is None:
        # .txt: no binary signature; reject obvious binary data
        if ext == ".txt":
            return b"\x00" not in content[:1024]
        return False  # unknown extension
    return any(content[:len(sig)] == sig for sig in sigs)

# ---------------------------------------------------------------------------
# RBAC constants
# ---------------------------------------------------------------------------

RequireCapacitacion = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION))
RequireEquipo = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION, Rol.GERENTE_DISTRITO))
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


@router.get("/resumen", response_model=list[dict])
def resumen_capacitacion(
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Dashboard de capacitación: tabla de exámenes con sus KPIs principales."""
    from app.services import examen_resultados_service
    return examen_resultados_service.resumen_capacitacion(db)


@router.get("/evaluados", response_model=dict)
def listar_evaluados(
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Catálogo para el selector de asignación: Representantes Médicos y Gerentes
    de Distrito activos (id + nombre), para elegir el evaluado por nombre en vez
    de escribir 'tipo:id' a mano."""
    from app.models.dimensiones import RepresentanteMedico, Gerente
    rms = (db.query(RepresentanteMedico.id, RepresentanteMedico.nombre)
           .filter(RepresentanteMedico.activo == True)  # noqa: E712
           .order_by(RepresentanteMedico.nombre).all())
    gers = (db.query(Gerente.id, Gerente.nombre, Gerente.tipo)
            .filter(Gerente.activo == True)  # noqa: E712
            .order_by(Gerente.nombre).all())
    return {
        "rms": [{"id": r.id, "nombre": r.nombre} for r in rms],
        "gerentes": [{"id": g.id, "nombre": g.nombre, "tipo": g.tipo} for g in gers],
    }


_XLSX_MEDIA = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _resolver_gid_equipo(current_user, gerente_id: int | None) -> int:
    """Resuelve el gerente_id del equipo: un GD se fuerza al suyo; ADMIN/CAPACITACION lo pasan."""
    rol = current_user.rol.value if hasattr(current_user.rol, "value") else str(current_user.rol)
    gid = gerente_id
    if rol == "GERENTE_DISTRITO":
        gid = getattr(current_user, "gerente_id", None)
        if not gid:
            raise HTTPException(status_code=403, detail="Tu usuario no está vinculado a un gerente (gerente_id).")
    if not gid:
        raise HTTPException(status_code=400, detail="Indica el gerente_id del equipo.")
    return gid


@router.get("/equipo/resumen", response_model=list[dict])
def resumen_equipo_examenes(
    gerente_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=RequireEquipo,
):
    """Resultados del equipo. Un GERENTE_DISTRITO ve solo su equipo (vía su
    gerente_id); ADMIN/CAPACITACION pueden pasar ?gerente_id=."""
    gid = _resolver_gid_equipo(current_user, gerente_id)
    from app.services import examen_resultados_service
    return examen_resultados_service.resumen_equipo(db, gid)


@router.get("/equipo/resumen.xlsx")
def exportar_equipo_excel(
    gerente_id: int | None = None,
    db: Session = Depends(get_db),
    current_user=RequireEquipo,
):
    """Exporta a Excel los resultados de exámenes del equipo (una fila por examen de cada visitador)."""
    gid = _resolver_gid_equipo(current_user, gerente_id)
    from app.services import examen_resultados_service, exportacion_service
    data = examen_resultados_service.resumen_equipo(db, gid)
    filas = []
    for rm in data:
        prom = rm["promedio"] if rm["promedio"] is not None else ""
        if not rm["examenes"]:
            filas.append([rm["nombre"], "(sin exámenes)", "", "", "", prom])
        for ex in rm["examenes"]:
            filas.append([
                rm["nombre"], ex["examen_nombre"],
                ex["ultimo_score"] if ex["ultimo_score"] is not None else "",
                "Sí" if ex["aprobado"] else "No", ex["estado"], prom,
            ])
    buf = exportacion_service._construir_workbook(
        "Equipo - Exámenes",
        ["Visitador", "Examen", "Último score", "Aprobado", "Estado", "Promedio RM"],
        filas,
    )
    return StreamingResponse(buf, media_type=_XLSX_MEDIA,
                             headers={"Content-Disposition": 'attachment; filename="examenes_equipo.xlsx"'})


# ===========================================================================
# /examenes — IA endpoints (literal paths — must come before /{examen_id})
# ===========================================================================

@router.post("/generar-ia", response_model=GenerarIAResponse, status_code=status.HTTP_202_ACCEPTED)
async def generar_ia(
    background_tasks: BackgroundTasks,
    nombre: str = Form(..., min_length=1, max_length=200),
    producto: str | None = Form(default=None),
    n_multi: int = Form(default=5, ge=0, le=50),
    n_casos: int = Form(default=0, ge=0, le=50),
    n_vf: int = Form(default=0, ge=0, le=50),
    texto_pegado: str | None = Form(default=None),
    archivo: UploadFile | None = File(default=None),
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Crea un examen en estado borrador y lanza la generación de preguntas con IA en background.

    Acepta opcionalmente un archivo (pdf/docx/pptx/txt) o texto pegado directamente.
    Devuelve job_id (=FuenteIA.id) y examen_id para consultar el estado luego.
    El examen permanece en borrador hasta revisión manual — nunca se auto-publica.
    """
    if n_multi + n_casos + n_vf == 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="n_multi + n_casos + n_vf debe ser > 0",
        )

    ruta_archivo: str | None = None
    nombre_archivo: str | None = None
    tipo_archivo: str | None = None

    if archivo and archivo.filename:
        ext = os.path.splitext(archivo.filename)[1].lower()
        if ext not in EXTENSIONES_IA:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Extensión no soportada. Permitidas: {EXTENSIONES_IA}",
            )
        content = await archivo.read()
        # Size cap — reuse the same limit as the ETL router
        max_bytes = settings.ETL_MAX_FILE_SIZE_MB * 1024 * 1024
        if len(content) > max_bytes:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail=f"El archivo excede el límite de {settings.ETL_MAX_FILE_SIZE_MB} MB",
            )
        if not _validar_magic_bytes_ia(content, ext):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="El archivo no tiene un formato válido (magic bytes inválidos para el tipo declarado)",
            )
        os.makedirs(UPLOAD_DIR, exist_ok=True)
        safe_name = _safe_filename(archivo.filename)
        ruta_archivo = os.path.join(UPLOAD_DIR, safe_name)
        with open(ruta_archivo, "wb") as f:
            f.write(content)
        nombre_archivo = safe_name
        # Map extension to tipo_archivo used by extraer_texto_fuente
        tipo_archivo = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx", ".txt": "texto"}.get(ext, "texto")
    elif not texto_pegado:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Debe proporcionar un archivo o texto_pegado",
        )

    # Create the exam in borrador state
    examen = Examen(
        nombre=nombre,
        producto=producto,
        estado="borrador",
        fuente="ia",
        creado_por_usuario_id=current_user.id,
    )
    db.add(examen)
    db.flush()  # get examen.id without committing yet

    # Serialize n_multi / n_casos / texto_pegado into prompt_usado JSON
    # (no migration needed — reuses the existing Text column)
    params_json = json.dumps({
        "n_multi": n_multi,
        "n_casos": n_casos,
        "n_vf": n_vf,
        "texto_pegado": texto_pegado,
    })

    fuente = FuenteIA(
        examen_id=examen.id,
        tipo_archivo=tipo_archivo,
        nombre_archivo=nombre_archivo,
        ruta_archivo=ruta_archivo,
        estado_generacion="pendiente",
        prompt_usado=params_json,
        cargado_por_usuario_id=current_user.id,
    )
    db.add(fuente)
    db.commit()
    db.refresh(fuente)

    background_tasks.add_task(examen_ia_service.procesar_generacion_ia, fuente.id)

    return GenerarIAResponse(job_id=fuente.id, examen_id=examen.id, estado="pendiente")


@router.get("/generar-ia/{job_id}", response_model=JobIAEstado)
def estado_generacion_ia(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Devuelve el estado del job de generación IA y la cantidad de preguntas ya insertadas."""
    fuente = db.query(FuenteIA).filter(FuenteIA.id == job_id).first()
    if fuente is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Job no encontrado")
    total = (
        db.query(Pregunta).filter(Pregunta.examen_id == fuente.examen_id).count()
        if fuente.examen_id
        else 0
    )
    return JobIAEstado(
        job_id=fuente.id,
        estado=fuente.estado_generacion,
        mensaje_error=fuente.mensaje_error,
        examen_id=fuente.examen_id,
        total_preguntas=total,
    )


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


@router.delete("/{examen_id}", status_code=status.HTTP_204_NO_CONTENT)
def eliminar_examen(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Elimina un examen. Solo si NO ha sido tomado (sin intentos); si ya tiene
    intentos, se preserva y devuelve 409."""
    try:
        examen_service.eliminar_examen(db, examen_id)
    except examen_service.ExamenConIntentosError as e:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(e))
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


@router.get("/{examen_id}/resultados", response_model=dict)
def resultados_examen(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """KPIs consolidados del examen: completitud, promedio, %aprobación, ranking (último intento)."""
    from app.services import examen_resultados_service
    try:
        return examen_resultados_service.resumen_examen(db, examen_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


@router.get("/{examen_id}/resultados.xlsx")
def exportar_resultados_excel(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Exporta a Excel el ranking de resultados del examen (último intento por evaluado)."""
    from app.services import examen_resultados_service, exportacion_service
    try:
        res = examen_resultados_service.resumen_examen(db, examen_id)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))
    filas = [
        [
            r.get("evaluado_nombre") or f"{r['evaluado_tipo']} #{r['evaluado_rm_id'] or r['evaluado_gerente_id']}",
            "Rep. Médico" if r["evaluado_tipo"] == "RM" else "Gerente Distrito",
            r.get("fecha_limite") or "",
            r["ultimo_score"] if r["ultimo_score"] is not None else "",
            "Sí" if r["aprobado"] else "No",
            r["intentos_usados"], r["estado"],
        ]
        for r in res["ranking"]
    ]
    buf = exportacion_service._construir_workbook(
        f"Resultados - {res['nombre'][:25]}",
        ["Evaluado", "Tipo", "Fecha límite", "Último score", "Aprobado", "Intentos", "Estado"],
        filas,
    )
    return StreamingResponse(buf, media_type=_XLSX_MEDIA,
                             headers={"Content-Disposition": f'attachment; filename="resultados_examen_{examen_id}.xlsx"'})


@router.get("/{examen_id}/analisis-preguntas", response_model=list[dict])
def analisis_preguntas_examen(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """% de error por pregunta sobre todos los intentos (RN-08)."""
    from app.services import examen_resultados_service
    return examen_resultados_service.analisis_preguntas(db, examen_id)


@router.get("/{examen_id}/abiertas", response_model=list[dict])
def respuestas_abiertas_examen(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Respuestas de preguntas abiertas / caso-abierto para calificación manual del Gerente."""
    from app.services import examen_resultados_service
    return examen_resultados_service.respuestas_abiertas(db, examen_id)


@router.get("/{examen_id}/preguntas", response_model=list[PreguntaConOpcionesResponse])
def listar_preguntas_examen(
    examen_id: int,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """Lista las preguntas (con sus opciones) del examen — para revisión/edición
    por Capacitación, incluidas las generadas por IA antes de publicar."""
    from app.models.exam_models import Pregunta
    return (
        db.query(Pregunta)
        .filter(Pregunta.examen_id == examen_id, Pregunta.activo == True)
        .order_by(Pregunta.orden)
        .all()
    )


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
        if payload.respuesta_texto is not None:
            # Pregunta abierta / caso-abierto: respuesta de texto libre.
            intento_svc.registrar_respuesta_abierta(
                db,
                intento_id=intento_id,
                pregunta_id=payload.pregunta_id,
                texto=payload.respuesta_texto,
            )
        elif payload.indice_presentado is not None:
            intento_svc.registrar_respuesta_presentada(
                db,
                intento_id=intento_id,
                pregunta_id=payload.pregunta_id,
                indice_presentado=payload.indice_presentado,
            )
        else:
            raise ValueError("Debe enviar indice_presentado (opción) o respuesta_texto (abierta)")
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))


@intentos_router.post("/{intento_id}/calificar", response_model=dict)
def calificar(
    intento_id: int,
    payload: CalificarRespuesta,
    db: Session = Depends(get_db),
    current_user=RequireCapacitacion,
):
    """El Gerente (Capacitación) asigna puntos a una respuesta abierta y recalcula el score."""
    try:
        intento = intento_svc.calificar_respuesta(db, intento_id, payload.respuesta_id, payload.puntos)
    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    return {
        "intento_id": intento.id,
        "score": float(intento.score) if intento.score is not None else None,
        "aprobado": bool(intento.aprobado),
    }


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
