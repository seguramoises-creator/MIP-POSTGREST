"""
SCGCPR — Router: Exportación de Reportes (PDF / Excel)
CLAUDE.md §18 "Pendiente de Implementar": "Exportación PDF/Excel de reportes".

GET /api/v1/exportacion/ranking/excel          — Ranking → .xlsx
GET /api/v1/exportacion/ranking/pdf            — Ranking → .pdf (tabular)
GET /api/v1/exportacion/reconocimientos/excel  — Reconocimientos → .xlsx
GET /api/v1/exportacion/reconocimientos/pdf    — Reconocimientos → .pdf (tabular)

Los archivos se generan EN MEMORIA (BytesIO) y se transmiten directamente
con StreamingResponse — no se guardan en `settings.REPORTS_DIR` (a diferencia
de los certificados de premio, que sí se cachean en disco por diseño).

RBAC: mismo criterio que `/dashboard/ejecutivo` y `/ranking/regional` —
roles con visión consolidada/gerencial (no autoservicio del RM individual,
que ya tiene sus propias vistas filtradas).
"""
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from app.core.deps import get_db, require_roles
from app.models.usuario import Rol
from app.services import exportacion_service

router = APIRouter(prefix="/exportacion", tags=["Exportación"])

RequireReportes = Depends(require_roles(
    Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL, Rol.GERENTE_PRODUCTIVIDAD
))

_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
_PDF_MEDIA_TYPE = "application/pdf"


def _nombre_archivo(prefijo: str, extension: str) -> str:
    marca = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M")
    return f"{prefijo}_{marca}.{extension}"


def _stream(buffer, media_type: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        buffer,
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/ranking/excel", summary="Exportar ranking a Excel (.xlsx)")
def exportar_ranking_excel(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    tipo_ranking: str = "MENSUAL",
    db: Session = Depends(get_db),
    current_user=RequireReportes,
):
    buffer = exportacion_service.exportar_ranking_excel(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, tipo_ranking=tipo_ranking)
    return _stream(buffer, _XLSX_MEDIA_TYPE, _nombre_archivo(f"ranking_{tipo_ranking.lower()}", "xlsx"))


@router.get("/ranking/pdf", summary="Exportar ranking a PDF (tabular)")
def exportar_ranking_pdf(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    tipo_ranking: str = "MENSUAL",
    top: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=RequireReportes,
):
    buffer = exportacion_service.exportar_ranking_pdf(
        db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, tipo_ranking=tipo_ranking, top=top
    )
    return _stream(buffer, _PDF_MEDIA_TYPE, _nombre_archivo(f"ranking_{tipo_ranking.lower()}", "pdf"))


@router.get("/reconocimientos/excel", summary="Exportar reconocimientos a Excel (.xlsx)")
def exportar_reconocimientos_excel(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=RequireReportes,
):
    buffer = exportacion_service.exportar_reconocimientos_excel(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id)
    return _stream(buffer, _XLSX_MEDIA_TYPE, _nombre_archivo("reconocimientos", "xlsx"))


@router.get("/reconocimientos/pdf", summary="Exportar reconocimientos a PDF (tabular)")
def exportar_reconocimientos_pdf(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    current_user=RequireReportes,
):
    buffer = exportacion_service.exportar_reconocimientos_pdf(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id)
    return _stream(buffer, _PDF_MEDIA_TYPE, _nombre_archivo("reconocimientos", "pdf"))
