"""
SCGCPR — Servicio de Reconocimiento
Genera reconocimientos automáticos y certificados PDF.
"""
import os
from datetime import datetime, timezone
from typing import Optional
from sqlalchemy.orm import Session
from loguru import logger

from app.models.hechos import Ranking, Reconocimiento, Premio
from app.models.dimensiones import RepresentanteMedico
from app.core.config import settings


def generar_reconocimientos_automaticos(
    db: Session,
    pais_id: int,
    ciclo_id: Optional[int],
    usuario_id: int,
):
    """
    Genera automáticamente reconocimientos para todos los RMs elegibles
    según el ranking vigente y los premios configurados para el período.
    """
    logger.info(f"Generando reconocimientos automáticos — pais_id={pais_id}")

    premios = db.query(Premio).filter(Premio.activo == True).all()
    ranking = db.query(Ranking).filter(
        Ranking.pais_id == pais_id,
        Ranking.tipo_ranking == "MENSUAL",
        Ranking.elegible == True,
    )
    if ciclo_id:
        ranking = ranking.filter(Ranking.ciclo_id == ciclo_id)
    ranking = ranking.order_by(Ranking.posicion.asc()).all()

    if not ranking:
        logger.warning("No hay RMs elegibles para generar reconocimientos")
        return

    reconocimientos_creados = 0
    for premio in premios:
        ganadores = _seleccionar_ganadores(ranking, premio)
        for rank in ganadores:
            # Evitar duplicados
            existe = db.query(Reconocimiento).filter(
                Reconocimiento.rm_id == rank.rm_id,
                Reconocimiento.premio_id == premio.id,
                Reconocimiento.ciclo_id == ciclo_id,
            ).first()
            if existe:
                continue

            rec = Reconocimiento(
                pais_id=pais_id,
                rm_id=rank.rm_id,
                premio_id=premio.id,
                ciclo_id=ciclo_id,
                iup_al_momento=rank.iup_total,
                posicion_ranking=rank.posicion,
                aprobado_por="SISTEMA",
                fecha_reconocimiento=datetime.now(timezone.utc),
            )
            db.add(rec)
            db.flush()
            reconocimientos_creados += 1

            # Generar certificado PDF
            generar_certificado_pdf(db, rec.id)

    db.commit()
    logger.info(f"Reconocimientos generados: {reconocimientos_creados}")


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


def generar_certificado_pdf(db: Session, reconocimiento_id: int):
    """
    Genera un certificado PDF para un reconocimiento.
    Usa ReportLab para construcción del PDF.
    """
    try:
        from reportlab.lib.pagesizes import A4, landscape
        from reportlab.lib import colors
        from reportlab.lib.units import cm
        from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.enums import TA_CENTER

        rec = db.query(Reconocimiento).filter(Reconocimiento.id == reconocimiento_id).first()
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
            Paragraph(f"IUP al momento: <b>{float(rec.iup_al_momento):.2f}</b> pts | "
                      f"Posición: <b>#{rec.posicion_ranking or 'N/A'}</b>", sub_style),
            Spacer(1, 0.5*cm),
            Paragraph(f"Fecha: {rec.fecha_reconocimiento.strftime('%d de %B de %Y')}", sub_style),
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
