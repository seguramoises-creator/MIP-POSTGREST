"""
SCGCPR — Servicio de Reconocimiento
Genera reconocimientos automáticos y certificados PDF.

REDISEÑO (jun-2026): la fuente del ranking pasó de FACT_Ranking
(campos iup_total/posicion) a FACT_RankingRM (score_total/posicion_global/
posicion_linea), y los reconocimientos se persisten en FACT_ReconocimientoRM
(antes FACT_Reconocimiento) con los campos renombrados score_total /
posicion_ranking. La generación de certificados PDF (ReportLab) se conserva
sin cambios funcionales — solo se actualizan los nombres de campo leídos.

REGLA DE NEGOCIO — ciclo abierto (jun-2026): los reconocimientos automáticos
se basan en el ranking del ciclo, así que también respetan el guard de
"solo ciclo abierto": si ciclo_id corresponde a un ciclo CERRADO, se aborta
sin crear ni modificar reconocimientos — los ciclos cerrados son snapshots
históricos inmutables (ver recalculo_service.validar_ciclo_abierto).
"""
import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from app.db.database import SessionLocal
from app.models.hechos import RankingRM, ReconocimientoRM
from app.models.dimensiones import RepresentanteMedico, Premio
from app.core.config import settings
from app.services.recalculo_service import validar_ciclo_abierto, CicloCerradoError
from app.services import notification_service


def generar_reconocimientos_automaticos(
    pais_codigo: str,
    ciclo_id: Optional[int],
    usuario_id: int,
):
    """
    Genera automáticamente reconocimientos para todos los RMs elegibles
    según el ranking vigente (FACT_RankingRM) y los premios configurados
    para el período.

    GUARD: si ciclo_id corresponde a un ciclo CERRADO, aborta sin crear ni
    modificar reconocimientos — regla de negocio "solo ciclo abierto".

    NOTA: se ejecuta como BackgroundTask, así que crea su PROPIA sesión de
    BD (convención de CLAUDE.md §19 — nunca reutilizar la sesión de la
    request, que ya estará cerrada cuando corra esta tarea en segundo plano).
    """
    logger.info(f"Generando reconocimientos automáticos — pais_codigo={pais_codigo}")
    db: Session = SessionLocal()
    try:
        if ciclo_id:
            try:
                validar_ciclo_abierto(db, ciclo_id)
            except CicloCerradoError as e:
                logger.warning(f"RECONOCIMIENTO abortado — {e}")
                return
            except ValueError as e:
                logger.error(f"RECONOCIMIENTO abortado — {e}")
                return

        premios = db.query(Premio).filter(Premio.activo == True).all()
        ranking = db.query(RankingRM).filter(
            RankingRM.pais_codigo == pais_codigo,
            RankingRM.tipo_ranking == "MENSUAL",
            RankingRM.elegible == True,
        )
        if ciclo_id:
            ranking = ranking.filter(RankingRM.ciclo_id == ciclo_id)
        ranking = ranking.order_by(RankingRM.posicion_global.asc()).all()

        if not ranking:
            logger.warning("No hay RMs elegibles para generar reconocimientos")
            return

        reconocimientos_creados = 0
        certificados_pendientes = []
        notificaciones_pendientes = []  # [(rm_id, premio, posicion_ranking, score_total)]
        for premio in premios:
            ganadores = _seleccionar_ganadores(ranking, premio)
            for rank in ganadores:
                # Evitar duplicados
                existe = db.query(ReconocimientoRM).filter(
                    ReconocimientoRM.rm_id == rank.rm_id,
                    ReconocimientoRM.premio_id == premio.id,
                    ReconocimientoRM.ciclo_id == ciclo_id,
                ).first()
                if existe:
                    continue

                rec = ReconocimientoRM(
                    pais_codigo=pais_codigo,
                    linea_id=rank.linea_id,
                    gerente_id=rank.gerente_id,
                    rm_id=rank.rm_id,
                    premio_id=premio.id,
                    ciclo_id=ciclo_id,
                    score_total=rank.score_total,
                    posicion_linea=rank.posicion_linea,
                    posicion_ranking=rank.posicion_global,
                    elegible=True,
                    aprobado_por="SISTEMA",
                    fecha_calculo=datetime.now(timezone.utc),
                )
                db.add(rec)
                db.flush()
                reconocimientos_creados += 1
                certificados_pendientes.append(rec.id)
                notificaciones_pendientes.append(
                    (rank.rm_id, premio, rank.posicion_global, rank.score_total)
                )

        db.commit()
        logger.info(f"Reconocimientos generados: {reconocimientos_creados}")

        # Notificaciones por correo (CLAUDE.md §18 — "Notificaciones email").
        # Best-effort: un fallo de envío NO revierte ni interrumpe el proceso
        # — ver notification_service (no-op silencioso si MAIL_SERVER="").
        if notificaciones_pendientes:
            try:
                rm_ids = [n[0] for n in notificaciones_pendientes]
                rms = {
                    rm.id: rm
                    for rm in db.query(RepresentanteMedico)
                    .filter(RepresentanteMedico.id.in_(rm_ids))
                    .all()
                }
                enviados = 0
                for rm_id, premio, posicion, score_total in notificaciones_pendientes:
                    rm = rms.get(rm_id)
                    if rm and notification_service.notificar_reconocimiento_otorgado(
                        db, rm=rm, premio=premio, ciclo_id=ciclo_id,
                        posicion_ranking=posicion, score_total=score_total,
                    ):
                        enviados += 1
                logger.info(
                    f"Notificaciones de reconocimiento enviadas: "
                    f"{enviados}/{len(notificaciones_pendientes)}"
                )
            except Exception as e:
                logger.warning(f"No se pudieron enviar notificaciones de reconocimiento: {e}")

        # Generar certificados PDF (cada uno gestiona su propia sesión)
        for rec_id in certificados_pendientes:
            generar_certificado_pdf(rec_id)
    finally:
        db.close()


def _seleccionar_ganadores(ranking: list, premio: Premio) -> list:
    """Selecciona ganadores según categoría del premio."""
    elegibles = [r for r in ranking if r.elegible]
    if not elegibles:
        return []

    if premio.categoria in ("RM", "REPRESENTANTE_MEDICO"):
        return elegibles[:1]  # Solo el #1
    elif premio.categoria == "TOP3":
        return elegibles[:3]
    elif premio.categoria == "TOP5":
        return elegibles[:5]
    else:
        return elegibles[:1]


def generar_certificado_pdf(reconocimiento_id: int):
    """
    Genera un certificado PDF para un reconocimiento.
    Usa ReportLab para construcción del PDF.

    NOTA: se invoca como BackgroundTask (desde el router o desde
    generar_reconocimientos_automaticos), así que crea su PROPIA sesión de
    BD (convención de CLAUDE.md §19) — nunca reutiliza la sesión de la
    request, que podría estar cerrada para cuando esta tarea corre.
    """
    db: Session = SessionLocal()
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        rec = db.query(ReconocimientoRM).filter(ReconocimientoRM.id == reconocimiento_id).first()
        if not rec:
            return

        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == rec.rm_id).first()
        premio = db.query(Premio).filter(Premio.id == rec.premio_id).first()

        if not rm or not premio:
            return

        os.makedirs(settings.REPORTS_DIR, exist_ok=True)
        pdf_path = os.path.join(settings.REPORTS_DIR, f"certificado_{reconocimiento_id}.pdf")

        doc = SimpleDocTemplate(pdf_path, pagesize=landscape(A4),
                                leftMargin=2*cm, rightMargin=2*cm,
                                topMargin=2*cm, bottomMargin=2*cm)

        styles = getSampleStyleSheet()
        titulo_style = ParagraphStyle("titulo", parent=styles["Title"],
                                      fontSize=28, textColor=colors.HexColor("#1F4E79"),
                                      alignment=TA_CENTER, spaceAfter=20)
        sub_style = ParagraphStyle("sub", parent=styles["Normal"],
                                   fontSize=16, alignment=TA_CENTER, spaceAfter=10)
        nombre_style = ParagraphStyle("nombre", parent=styles["Normal"],
                                      fontSize=22, fontName="Helvetica-Bold",
                                      alignment=TA_CENTER, spaceAfter=20,
                                      textColor=colors.HexColor("#2E75B6"))

        story = [
            Spacer(1, 1*cm),
            Paragraph("CERTIFICADO DE RECONOCIMIENTO", titulo_style),
            Spacer(1, 0.5*cm),
            Paragraph("La organización reconoce con orgullo a:", sub_style),
            Spacer(1, 0.5*cm),
            Paragraph(rm.nombre, nombre_style),
            Spacer(1, 0.3*cm),
            Paragraph(f"Por haber obtenido el premio:", sub_style),
            Paragraph(f"<b>{premio.nombre}</b>", nombre_style),
            Spacer(1, 0.5*cm),
            Paragraph(f"Score integral al momento: <b>{float(rec.score_total):.2f}</b> pts | "
                      f"Posición: <b>#{rec.posicion_ranking or 'N/A'}</b>", sub_style),
            Spacer(1, 0.5*cm),
            Paragraph(f"Fecha: {rec.fecha_calculo.strftime('%d de %B de %Y')}", sub_style),
        ]

        doc.build(story)

        rec.certificado_generado = True
        rec.certificado_url = pdf_path
        db.commit()

        logger.info(f"Certificado generado: {pdf_path}")

    except ImportError:
        logger.warning("ReportLab no disponible — certificado no generado")
    except Exception as e:
        logger.error(f"Error generando certificado {reconocimiento_id}: {e}")
    finally:
        db.close()
