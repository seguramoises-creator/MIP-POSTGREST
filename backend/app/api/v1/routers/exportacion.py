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

from app.core.deps import get_db
from app.core.authz.deps import autorizar_export, Autorizacion
from app.core.authz.constantes import Recurso
from app.core.authz import scope
from app.core.authz.audit import registrar_evento_seguridad
from app.services import exportacion_service

router = APIRouter(prefix="/exportacion", tags=["Exportación"])

# RBAC Fase 2: exportar es un permiso INDEPENDIENTE de leer, y su alcance se CAPA por la lectura
# del módulo (ranking.rkt). Deniega a quien no lee el módulo (p.ej. GERENTE_MEDICO) y filtra los
# datos por scope (GD → solo su equipo). Reconocimientos se derivan del ranking → mismo recurso.
ExportRanking = Depends(autorizar_export(Recurso.RANKING_RKT))


def _rm_ids(db: Session, auth: Autorizacion):
    """Conjunto de rm_id exportables según el alcance efectivo (None = todos)."""
    return scope.rm_ids_visibles(db, auth.usuario, auth.alcance)


def _auditar(db: Session, auth: Autorizacion, detalle: str):
    registrar_evento_seguridad(db, auth.usuario, "EXPORTACION", recurso=Recurso.RANKING_RKT,
                               accion="export", alcance=auth.alcance.value, detalle=detalle)

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
    auth: Autorizacion = ExportRanking,
):
    buffer = exportacion_service.exportar_ranking_excel(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, tipo_ranking=tipo_ranking, rm_ids=_rm_ids(db, auth))
    _auditar(db, auth, "ranking/excel")
    return _stream(buffer, _XLSX_MEDIA_TYPE, _nombre_archivo(f"ranking_{tipo_ranking.lower()}", "xlsx"))


@router.get("/ranking/pdf", summary="Exportar ranking a PDF (tabular)")
def exportar_ranking_pdf(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    tipo_ranking: str = "MENSUAL",
    top: Optional[int] = None,
    db: Session = Depends(get_db),
    auth: Autorizacion = ExportRanking,
):
    buffer = exportacion_service.exportar_ranking_pdf(
        db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, tipo_ranking=tipo_ranking, top=top, rm_ids=_rm_ids(db, auth)
    )
    _auditar(db, auth, "ranking/pdf")
    return _stream(buffer, _PDF_MEDIA_TYPE, _nombre_archivo(f"ranking_{tipo_ranking.lower()}", "pdf"))


@router.get("/reconocimientos/excel", summary="Exportar reconocimientos a Excel (.xlsx)")
def exportar_reconocimientos_excel(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    auth: Autorizacion = ExportRanking,
):
    buffer = exportacion_service.exportar_reconocimientos_excel(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, rm_ids=_rm_ids(db, auth))
    _auditar(db, auth, "reconocimientos/excel")
    return _stream(buffer, _XLSX_MEDIA_TYPE, _nombre_archivo("reconocimientos", "xlsx"))


@router.get("/reconocimientos/pdf", summary="Exportar reconocimientos a PDF (tabular)")
def exportar_reconocimientos_pdf(
    pais_codigo: Optional[str] = None,
    ciclo_id: Optional[int] = None,
    db: Session = Depends(get_db),
    auth: Autorizacion = ExportRanking,
):
    buffer = exportacion_service.exportar_reconocimientos_pdf(db, pais_codigo=pais_codigo, ciclo_id=ciclo_id, rm_ids=_rm_ids(db, auth))
    _auditar(db, auth, "reconocimientos/pdf")
    return _stream(buffer, _PDF_MEDIA_TYPE, _nombre_archivo("reconocimientos", "pdf"))
