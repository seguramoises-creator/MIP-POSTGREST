"""PDF de la hoja de coaching (MORE) + envío por correo al RM.

Genera el PDF en memoria (ReportLab) con todo el contenido de la hoja y lo envía
adjunto al correo corporativo del RM. Es best-effort: si `settings.MAIL_SERVER`
está vacío, el envío es no-op (igual que notification_service). No bloquea el guardado.
"""
import base64
import smtplib
from io import BytesIO
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.application import MIMEApplication

from loguru import logger

from app.core.config import settings
from app.models.coaching_more_models import CoachingSesion, SECCIONES_MORE
from app.models.dimensiones import RepresentanteMedico

_ESCALA = {1: "D · Desarrollar", 2: "P · Perfeccionar", 3: "A · Adecuado", 4: "E · Excelente"}


def generar_pdf(db, sesion: CoachingSesion, prom: dict, rm: RepresentanteMedico) -> bytes:
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.units import mm
    from reportlab.lib import colors
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, Image,
    )
    from app.models.coaching_more_models import CoachingItemEvaluado
    from app.models.usuario import Usuario

    styles = getSampleStyleSheet()
    h = ParagraphStyle("h", parent=styles["Heading2"], textColor=colors.HexColor("#0057A8"), spaceAfter=4)
    sub = ParagraphStyle("sub", parent=styles["Heading4"], textColor=colors.HexColor("#374151"), spaceBefore=8, spaceAfter=2)
    normal = styles["BodyText"]

    buf = BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, topMargin=16 * mm, bottomMargin=16 * mm,
                            leftMargin=16 * mm, rightMargin=16 * mm, title=f"Coaching {sesion.id}")
    gd = db.query(Usuario).filter(Usuario.id == sesion.gd_usuario_id).first()
    el: list = []
    el.append(Paragraph("Hoja de Coaching — Modelo de Ventas MORE", h))
    el.append(Paragraph(
        f"<b>Representante:</b> {rm.nombre if rm else '—'} &nbsp;&nbsp; "
        f"<b>Gerente de Distrito:</b> {gd.nombre_completo if gd else '—'}<br/>"
        f"<b>Fecha del coaching:</b> {sesion.fecha_coaching.isoformat()} &nbsp;&nbsp; "
        f"<b>Médicos vistos:</b> {sesion.medicos_vistos}", normal))
    if sesion.corrige_a_id:
        el.append(Paragraph(f"<i>Hoja de corrección de la #{sesion.corrige_a_id}. "
                            f"Motivo: {sesion.motivo_correccion or '—'}</i>", normal))
    el.append(Spacer(1, 6))

    items = db.query(CoachingItemEvaluado).filter(CoachingItemEvaluado.sesion_id == sesion.id).all()
    for sec in SECCIONES_MORE:
        sec_items = [i for i in items if i.seccion == sec]
        if not sec_items:
            continue
        el.append(Paragraph(f"{sec} — promedio {prom['secciones'].get(sec, '—')}", sub))
        data = [[Paragraph(i.item_texto, normal), _ESCALA.get(i.calificacion, str(i.calificacion))]
                for i in sec_items]
        t = Table(data, colWidths=[135 * mm, 40 * mm])
        t.setStyle(TableStyle([
            ("FONTSIZE", (0, 0), (-1, -1), 8),
            ("VALIGN", (0, 0), (-1, -1), "TOP"),
            ("LINEBELOW", (0, 0), (-1, -1), 0.25, colors.HexColor("#e5e7eb")),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
        ]))
        el.append(t)

    el.append(Spacer(1, 8))
    el.append(Paragraph(f"<b>Evaluación promedio general:</b> {prom['general']}", sub))
    el.append(Paragraph(f"<b>Fortalezas:</b> {sesion.fortalezas}", normal))
    el.append(Paragraph(f"<b>Áreas a perfeccionar:</b> {sesion.areas_perfeccionar}", normal))
    el.append(Paragraph("<b>Plan de Acción</b>", sub))
    el.append(Paragraph(f"¿Qué harás?: {sesion.plan_que_haras}", normal))
    el.append(Paragraph(f"¿Cómo lo harás?: {sesion.plan_como_haras}", normal))
    el.append(Paragraph(f"¿Cómo te darás cuenta?: {sesion.plan_como_veras}", normal))
    el.append(Paragraph(f"Fecha de seguimiento: {sesion.plan_fecha_seguimiento.isoformat()}", normal))

    acuerdo = "De acuerdo" if sesion.rm_acuerdo == "de_acuerdo" else "No de acuerdo"
    el.append(Paragraph(f"<b>Acuerdo del representante:</b> {acuerdo}", sub))
    if sesion.rm_justificacion_desacuerdo:
        el.append(Paragraph(f"<b>Justificación:</b> {sesion.rm_justificacion_desacuerdo}", normal))

    # Firma (data URL base64 → imagen)
    el.append(Paragraph("<b>Firma del representante:</b>", sub))
    try:
        raw = sesion.rm_firma_imagen.split(",", 1)[-1]
        img = Image(BytesIO(base64.b64decode(raw)), width=90 * mm, height=32 * mm, kind="proportional")
        el.append(img)
    except Exception:  # noqa: BLE001
        el.append(Paragraph("<i>(firma capturada — no renderizable en PDF)</i>", normal))

    doc.build(el)
    return buf.getvalue()


def _enviar_pdf(destinatario: str, asunto: str, cuerpo_html: str, pdf: bytes, nombre: str) -> bool:
    """SMTP con adjunto PDF.

    FIX jul-2026: usa `notification_service.mail_config()` — la MISMA fuente que el resto
    de los correos (config guardada por el ADMIN en BD, con fallback al `.env`). Antes leía
    `settings.MAIL_*` directo, así que si el SMTP se había configurado desde
    Admin → Servidor de Correo (BD) y el `.env` estaba vacío, esta función salía por el
    no-op y la hoja de coaching NUNCA se enviaba, mientras todos los demás correos sí
    llegaban. Divergencia silenciosa: no dejaba error, solo un log en debug.
    """
    from app.services.notification_service import mail_config
    cfg = mail_config()
    if not cfg["server"]:
        logger.debug(f"Coaching PDF: correo omitido (sin servidor SMTP configurado) — {destinatario!r}")
        return False
    msg = MIMEMultipart("mixed")
    msg["Subject"] = asunto
    msg["From"] = f"{cfg['from_name']} <{cfg['from']}>"
    msg["To"] = destinatario
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))
    adj = MIMEApplication(pdf, _subtype="pdf")
    adj.add_header("Content-Disposition", "attachment", filename=nombre)
    msg.attach(adj)
    try:
        if cfg["ssl"]:
            srv = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=15)
        else:
            srv = smtplib.SMTP(cfg["server"], cfg["port"], timeout=15)
            if cfg["tls"]:
                srv.starttls()
        if cfg["username"]:
            srv.login(cfg["username"], cfg["password"])
        srv.sendmail(cfg["from"], [destinatario], msg.as_string())
        srv.quit()
        logger.info(f"Coaching PDF enviado a {destinatario}")
        return True
    except Exception as exc:  # noqa: BLE001
        logger.warning(f"Coaching PDF: fallo SMTP a {destinatario}: {exc}")
        return False


def _correo_del_rm(db, rm: RepresentanteMedico) -> str:
    """Correo del representante: primero el del catálogo (DIM_RM), y si está vacío el del
    USUARIO vinculado — ese sí se mantiene real (se usa para login y recuperación de
    contraseña), mientras que el del catálogo suele venir del Excel y quedar vacío."""
    correo = (rm.email or "").strip() if rm else ""
    if correo:
        return correo
    try:
        from app.models.usuario import Usuario
        u = db.query(Usuario).filter(Usuario.rm_id == rm.id).first()
        return (u.email or "").strip() if u else ""
    except Exception:  # noqa: BLE001
        return ""


def generar_y_enviar(db, sesion: CoachingSesion, prom: dict, rm: RepresentanteMedico) -> None:
    """Genera el PDF y lo envía al correo del RM (best-effort)."""
    pdf = generar_pdf(db, sesion, prom, rm)
    correo = _correo_del_rm(db, rm)
    if not correo:
        logger.warning(f"Coaching MORE: RM {getattr(rm, 'id', '?')} sin correo "
                       f"(ni en DIM_RM ni en su usuario) — no se envió PDF.")
        return
    cuerpo = (
        f"<p>Hola {rm.nombre},</p>"
        f"<p>Adjuntamos la hoja de coaching (Modelo MORE) del "
        f"<b>{sesion.fecha_coaching.isoformat()}</b>, con evaluación promedio "
        f"<b>{prom['general']}</b>. Esta hoja es un registro firmado e inmutable.</p>"
        f"<p>— Sistema VISTA</p>"
    )
    _enviar_pdf(correo, f"Hoja de Coaching MORE — {sesion.fecha_coaching.isoformat()}",
                cuerpo, pdf, f"coaching_{sesion.id}.pdf")
