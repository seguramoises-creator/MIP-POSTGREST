"""
SCGCPR — Router: ETL (Carga de archivos Excel)
FIX C-06: Sanitiza el nombre del archivo para prevenir Path Traversal.
FIX W-06: Valida magic bytes del archivo antes de guardar.
FIX W-01: datetime.now(timezone.utc) en lugar de utcnow() deprecado.

POST /api/v1/etl/cargar         — Subir y procesar archivo
GET  /api/v1/etl/status/{id}    — Estado de un job
GET  /api/v1/etl/historial       — Historial de cargas
POST /api/v1/etl/reprocesar/{id} — Reprocesar carga anterior
"""
import os
import uuid
import re
from typing import Optional
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.usuario import Rol, Usuario
from app.models.hechos import CargaExcel
from app.schemas.schemas import ETLJobResponse, ETLJobStatus
from app.core.config import settings

router = APIRouter(prefix="/etl", tags=["ETL — Carga Excel"])
from app.core.authz.deps import require as _require_authz
from app.core.authz.constantes import Accion as _Acc, Recurso as _Rec
AdminOrGerProd = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
# RBAC Fase 2 (deuda #3): recurso etl.cargar.
ConfigEtl = Depends(_require_authz(_Acc.CONFIGURE, _Rec.ETL_CARGAR))
ReadEtl = Depends(_require_authz(_Acc.READ, _Rec.ETL_CARGAR))

TIPOS_PERMITIDOS      = {"KPI_RM", "PRODUCTIVIDAD", "COMERCIAL", "COACHING", "CAPACITACION"}
EXTENSIONES_PERMITIDAS= {".xlsx", ".xls"}

# FIX W-06: Magic bytes de archivos Excel válidos
MAGIC_BYTES_XLSX = b"PK\x03\x04"           # ZIP (OOXML)
MAGIC_BYTES_XLS  = b"\xd0\xcf\x11\xe0"     # OLE2 Compound


def _safe_filename(original: str) -> str:
    """
    FIX C-06: Genera un nombre de archivo seguro usando UUID.
    Elimina completamente el nombre original para prevenir Path Traversal
    y evitar caracteres especiales, secuencias ../ u otros vectores.
    La extensión se valida antes de llamar esta función.
    """
    ext = os.path.splitext(original)[1].lower() if original else ".xlsx"
    unique_id = uuid.uuid4().hex
    ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    return f"{ts}_{unique_id}{ext}"


def _validar_magic_bytes(content: bytes, ext: str) -> bool:
    """FIX W-06: Verifica que el contenido coincida con los magic bytes esperados."""
    if ext == ".xlsx" and content[:4] == MAGIC_BYTES_XLSX:
        return True
    if ext == ".xls" and content[:4] == MAGIC_BYTES_XLS:
        return True
    # xlsx también puede ser .xls renombrado — aceptar ambos
    if content[:4] in (MAGIC_BYTES_XLSX, MAGIC_BYTES_XLS):
        return True
    return False


@router.post("/cargar", response_model=ETLJobResponse, status_code=202, summary="Cargar archivo Excel")
async def cargar_excel(
    background_tasks: BackgroundTasks,
    archivo: UploadFile = File(..., description="Archivo Excel (.xlsx)"),
    tipo_archivo: str = Form(..., description="KPI_RM | PRODUCTIVIDAD | COMERCIAL | COACHING | CAPACITACION"),
    pais_codigo: Optional[str] = Form(None, description="Opcional para KPI_RM — se lee del archivo"),
    ciclo_id: Optional[int] = Form(None, description="Opcional para KPI_RM — se lee del archivo"),
    modo: str = Form("SIMULACION", description="SIMULACION | PRODUCCION"),
    db: Session = Depends(get_db),
    current_user: Usuario = ConfigEtl,
):
    """
    Sube un archivo Excel y lo procesa mediante el motor ETL.
    - SIMULACION: valida sin guardar en BD
    - PRODUCCION: carga real en Data Warehouse
    """
    if tipo_archivo.upper() not in TIPOS_PERMITIDOS:
        raise HTTPException(400, f"Tipo inválido. Permitidos: {TIPOS_PERMITIDOS}")
    if modo.upper() not in {"SIMULACION", "PRODUCCION"}:
        raise HTTPException(400, "Modo debe ser SIMULACION o PRODUCCION")

    ext = os.path.splitext(archivo.filename or "")[1].lower()
    if ext not in EXTENSIONES_PERMITIDAS:
        raise HTTPException(400, f"Solo se permiten: {EXTENSIONES_PERMITIDAS}")

    content = await archivo.read()

    # FIX W-06: Validar magic bytes
    if not _validar_magic_bytes(content, ext):
        raise HTTPException(
            400,
            "El contenido del archivo no corresponde a un Excel válido. "
            "Verifique que no esté corrupto o renombrado."
        )

    max_bytes = settings.ETL_MAX_FILE_SIZE_MB * 1024 * 1024
    if len(content) > max_bytes:
        raise HTTPException(413, f"Archivo excede el límite de {settings.ETL_MAX_FILE_SIZE_MB} MB")

    # FIX C-06: Nombre de archivo seguro (UUID, sin nombre original del cliente)
    os.makedirs(settings.ETL_UPLOAD_DIR, exist_ok=True)
    filename = _safe_filename(archivo.filename or "upload.xlsx")
    filepath = os.path.join(settings.ETL_UPLOAD_DIR, filename)

    # Doble verificación: el path resultante debe estar dentro del directorio permitido
    real_path    = os.path.realpath(filepath)
    allowed_base = os.path.realpath(settings.ETL_UPLOAD_DIR)
    if not real_path.startswith(allowed_base):
        raise HTTPException(400, "Ruta de archivo inválida")
    with open(filepath, "wb") as f:
        f.write(content)

    # Registrar job en BD
    job = CargaExcel(
        pais_codigo=pais_codigo,
        usuario_id=current_user.id,
        nombre_archivo=filename,
        tipo_archivo=tipo_archivo.upper(),
        ciclo_id=ciclo_id,
        modo=modo.upper(),
        estado="PENDIENTE",
    )
    db.add(job)
    db.commit()
    db.refresh(job)

    # Disparar procesamiento en background
    from app.services.etl_service import procesar_excel_task
    background_tasks.add_task(
        procesar_excel_task,
        job_id=job.id,
        filepath=filepath,
        tipo_archivo=tipo_archivo.upper(),
        pais_codigo=pais_codigo,
        ciclo_id=ciclo_id,
        modo=modo.upper(),
        usuario_id=current_user.id,
    )

    return job


@router.get("/status/{job_id}", response_model=dict, summary="Estado de job ETL")
def get_etl_status(
    job_id: int,
    db: Session = Depends(get_db),
    current_user=ReadEtl,
):
    job = db.query(CargaExcel).filter(CargaExcel.id == job_id).first()
    if not job:
        raise HTTPException(404, "Job ETL no encontrado")

    progreso = 0
    if job.estado == "PROCESANDO":
        progreso = 50
    elif job.estado == "EXITOSO":
        progreso = 100

    return {
        "job_id": job.id,
        "nombre_archivo": job.nombre_archivo,
        "tipo_archivo": job.tipo_archivo,
        "modo": job.modo,
        "estado": job.estado,
        "progreso_pct": progreso,
        "total_filas": job.total_filas,
        "filas_exitosas": job.filas_exitosas,
        "filas_error": job.filas_error,
        "filas_advertencia": job.filas_advertencia,
        "duracion_segundos": float(job.duracion_segundos or 0),
        "fecha_inicio": job.fecha_inicio,
        "fecha_fin": job.fecha_fin,
        "log_errores": job.log_errores,
        "log_advertencias": job.log_advertencias,
    }


@router.post("/recalcular/{ciclo_id}", response_model=dict,
             summary="Recalcular puntajes IUP y ranking de un ciclo")
def recalcular(
    ciclo_id: int,
    pais_codigo: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user=ConfigEtl,
):
    """
    Ejecuta el proceso de cálculo post-carga (solo si el ciclo está ABIERTO —
    ver recalculo_service.validar_ciclo_abierto; ciclos cerrados se abortan
    sin escribir):
    1. Completa resultado_porcentaje y puntos_obtenidos en FACT_ResultadoIndicador
    2. Calcula score integral agrupado por módulo
    3. Borra y regenera FACT_ScoreIntegralRM / FACT_RankingRM (delete-then-regenerate)
    """
    from app.services.recalculo_service import recalcular_ciclo
    resultado = recalcular_ciclo(db, ciclo_id=ciclo_id, pais_codigo=pais_codigo)
    return resultado


@router.get("/historial", response_model=list, summary="Historial de cargas ETL")
def get_etl_historial(
    pais_codigo: Optional[str] = None,
    tipo: Optional[str] = None,
    limit: int = 50,
    db: Session = Depends(get_db),
    current_user=ReadEtl,
):
    q = db.query(CargaExcel)
    if pais_codigo: q = q.filter(CargaExcel.pais_codigo == pais_codigo)
    if tipo: q = q.filter(CargaExcel.tipo_archivo == tipo.upper())
    rows = q.order_by(CargaExcel.fecha_inicio.desc()).limit(limit).all()

    return [
        {
            "id": r.id,
            "fecha_inicio": r.fecha_inicio.isoformat() if r.fecha_inicio else None,
            "fecha_fin": r.fecha_fin.isoformat() if r.fecha_fin else None,
            "tipo_archivo": r.tipo_archivo,
            "estado": r.estado,
            "total_filas": r.total_filas,
            "filas_exitosas": r.filas_exitosas,
            "filas_error": r.filas_error,
            "filas_advertencia": r.filas_advertencia,
            "log_advertencias": r.log_advertencias,
        }
        for r in rows
    ]
