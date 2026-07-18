"""
SCGCPR — Servicio de Notificaciones por Correo
CLAUDE.md §18 "Pendiente de Implementar": "Notificaciones email — Notificar
resultados de ranking y premios".

Usa smtplib + email.mime de la librería estándar (no hay librería de correo
en requirements.txt — evita agregar una dependencia nueva solo para esto).

DISEÑO — degradación elegante (mismo patrón que `config.Settings`):
si `settings.MAIL_SERVER` está vacío, TODAS las funciones son no-op
silencioso (retornan False/0 sin intentar conectar). Esto permite que el
resto del sistema funcione normalmente en entornos de desarrollo/pruebas
sin SMTP configurado.

REGLA — best effort, nunca bloquea procesos de negocio: un fallo de envío
de correo NO debe revertir ni interrumpir la generación de ranking o
reconocimientos (son procesos independientes del canal de notificación).
Por eso ninguna función de este módulo lanza excepciones hacia el
llamador — los errores se registran con `logger` y se continúa.
"""
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from typing import Optional

from sqlalchemy.orm import Session
from loguru import logger

from app.core.config import settings
from app.models.dimensiones import RepresentanteMedico, Pais, Ciclo, Premio

_COLOR_TITULO = "#1F4E79"
_COLOR_TEXTO_PIE = "#888888"


def mail_config() -> dict:
    """Config SMTP efectiva: primero la guardada por ADMIN en BD (config_service,
    claves MAIL_*), con fallback al `.env` (settings). Abre una sesión corta y
    nunca lanza — si la BD no está disponible usa el `.env`."""
    cfg = {
        "server": settings.MAIL_SERVER, "port": int(settings.MAIL_PORT),
        "username": settings.MAIL_USERNAME, "password": settings.MAIL_PASSWORD,
        "from": settings.MAIL_FROM, "from_name": settings.MAIL_FROM_NAME,
        "tls": bool(settings.MAIL_TLS), "ssl": bool(settings.MAIL_SSL),
    }
    try:
        from app.db.database import SessionLocal
        from app.services import config_service
        db = SessionLocal()
        try:
            def g(k, d):
                v = config_service.obtener(db, k)
                return v if v is not None else d
            cfg["server"] = g("MAIL_SERVER", cfg["server"])
            try:
                cfg["port"] = int(g("MAIL_PORT", str(cfg["port"])) or cfg["port"])
            except (TypeError, ValueError):
                pass
            cfg["username"] = g("MAIL_USERNAME", cfg["username"])
            pw = config_service.obtener(db, "MAIL_PASSWORD")
            if pw is not None:
                cfg["password"] = pw
            cfg["from"] = g("MAIL_FROM", cfg["from"])
            cfg["from_name"] = g("MAIL_FROM_NAME", cfg["from_name"])
            cfg["tls"] = config_service.obtener_bool(db, "MAIL_TLS", cfg["tls"])
            cfg["ssl"] = config_service.obtener_bool(db, "MAIL_SSL", cfg["ssl"])
        finally:
            db.close()
    except Exception as e:  # BD no disponible → usar .env
        logger.debug(f"mail_config: usando .env (BD no disponible): {e}")
    return cfg


def _habilitado() -> bool:
    """Notificaciones activas solo si hay servidor SMTP configurado (BD o .env)."""
    return bool(mail_config().get("server"))


def _enviar(destinatario: str, asunto: str, cuerpo_html: str) -> bool:
    """
    Envía un correo HTML vía SMTP. Retorna True/False según éxito — nunca
    lanza, los llamadores tratan el envío como best-effort.
    """
    cfg = mail_config()
    if not cfg.get("server"):
        logger.debug(f"Notificación omitida (SMTP sin configurar) — destinatario={destinatario!r}")
        return False
    if not destinatario:
        return False

    msg = MIMEMultipart("alternative")
    msg["Subject"] = asunto
    msg["From"] = f"{cfg['from_name']} <{cfg['from']}>"
    msg["To"] = destinatario
    msg.attach(MIMEText(cuerpo_html, "html", "utf-8"))

    servidor = None
    try:
        if cfg["ssl"]:
            servidor = smtplib.SMTP_SSL(cfg["server"], cfg["port"], timeout=15)
        else:
            servidor = smtplib.SMTP(cfg["server"], cfg["port"], timeout=15)
            if cfg["tls"]:
                servidor.starttls()
        if cfg["username"]:
            servidor.login(cfg["username"], cfg["password"])
        servidor.sendmail(cfg["from"], [destinatario], msg.as_string())
        logger.info(f"Notificación enviada — destinatario={destinatario!r}, asunto={asunto!r}")
        return True
    except Exception as e:
        logger.warning(f"Error enviando notificación a {destinatario!r}: {e}")
        return False
    finally:
        if servidor is not None:
            try:
                servidor.quit()
            except Exception:
                pass


def _nombre_pais(db: Session, pais_codigo: str) -> str:
    pais = db.query(Pais).filter(Pais.id == pais_codigo).first()
    return pais.nombre if pais else f"País #{pais_codigo}"


def _nombre_ciclo(db: Session, ciclo_id: Optional[int]) -> str:
    if not ciclo_id:
        return "—"
    ciclo = db.query(Ciclo).filter(Ciclo.id == ciclo_id).first()
    if not ciclo:
        return f"Ciclo #{ciclo_id}"
    return ciclo.nombre_canonico or ciclo.nombre


def _pie_pagina() -> str:
    return (
        f"<p style='color:{_COLOR_TEXTO_PIE};font-size:12px;margin-top:24px;'>"
        "Mensaje automático del Sistema MIP (SCGCPR) — por favor no responder "
        "a este correo.</p>"
    )


def notificar_costo_pendiente_aprobacion(db: Session, ciclo_id: Optional[int],
                                         linea_id: Optional[int], actor_nombre: str = "") -> int:
    """RBAC Fase 2 (deuda #5): avisa a los Directores (rol PRESIDENCIA) que hay una configuración de
    Costo/ROI en BORRADOR pendiente de su aprobación. Best-effort: no-op si el correo está
    deshabilitado o no hay Directores con email. Devuelve cuántos avisos se enviaron."""
    if not _habilitado():
        return 0
    from app.models.usuario import Usuario, Rol
    directores = (db.query(Usuario)
                  .filter(Usuario.rol == Rol.PRESIDENCIA, Usuario.activo == True, Usuario.email.isnot(None))
                  .all())
    if not directores:
        return 0
    ciclo = _nombre_ciclo(db, ciclo_id)
    linea_txt = f"línea #{linea_id}" if linea_id else "todas las líneas"
    asunto = "Costo/ROI pendiente de aprobación"
    cuerpo = (
        f"<h3>Costo/ROI pendiente de tu aprobación</h3>"
        f"<p>Finanzas{f' ({actor_nombre})' if actor_nombre else ''} guardó una configuración de "
        f"<b>Costo por Visita y ROI</b> ({ciclo}, {linea_txt}) que quedó en <b>BORRADOR</b> y espera "
        f"tu revisión y aprobación en la pantalla de Costo &amp; ROI.</p>" + _pie_pagina()
    )
    enviados = 0
    for d in directores:
        if _enviar(d.email, asunto, cuerpo):
            enviados += 1
    return enviados


def notificar_ranking_generado(
    db: Session,
    pais_codigo: str,
    ciclo_id: Optional[int],
    tipo_ranking: str,
    resultados: list,
) -> int:
    """
    Notifica por correo los resultados del ranking recién generado a cada
    RM con email registrado: su posición global/de línea, score (IUP) y
    elegibilidad; con un mensaje adicional de felicitación para el Top 3
    global.

    `resultados` es la lista de dicts construida por
    `ranking_service.generar_ranking_task` — cada elemento contiene al
    menos: rm_id, posicion_global, posicion_linea, score_total, elegible.

    Retorna la cantidad de correos enviados exitosamente (0 si las
    notificaciones están deshabilitadas o no hay destinatarios con email).
    Nunca lanza — cada error de envío individual se registra y se continúa.
    """
    if not _habilitado() or not resultados:
        return 0

    nombre_pais = _nombre_pais(db, pais_codigo)
    nombre_ciclo = _nombre_ciclo(db, ciclo_id)

    rm_ids = [r["rm_id"] for r in resultados]
    rms = {
        rm.id: rm
        for rm in db.query(RepresentanteMedico)
        .filter(RepresentanteMedico.id.in_(rm_ids))
        .all()
    }

    enviados = 0
    for r in resultados:
        rm = rms.get(r["rm_id"])
        if not rm or not rm.email:
            continue

        felicitacion = ""
        if r["posicion_global"] <= 3:
            felicitacion = (
                f"<p style='color:{_COLOR_TITULO};font-weight:bold;'>"
                f"¡Felicitaciones! Terminaste en el Top {r['posicion_global']} "
                "del ranking global de este ciclo.</p>"
            )

        cuerpo = f"""\
<html><body style="font-family:Arial,sans-serif;color:#333333;line-height:1.5;">
  <h2 style="color:{_COLOR_TITULO};">Resultados del Ranking {tipo_ranking.title()}</h2>
  <p>Hola {rm.nombre},</p>
  <p>Se generó el ranking <strong>{tipo_ranking}</strong> de
     <strong>{nombre_pais}</strong> — ciclo <strong>{nombre_ciclo}</strong> —
     con los siguientes resultados para ti:</p>
  <ul>
    <li>Posición global: <strong>{r['posicion_global']}</strong></li>
    <li>Posición en tu línea: <strong>{r['posicion_linea']}</strong></li>
    <li>Score total (IUP): <strong>{float(r['score_total']):.2f}</strong></li>
    <li>Elegible para reconocimiento: <strong>{'Sí' if r['elegible'] else 'No'}</strong></li>
  </ul>
  {felicitacion}
  {_pie_pagina()}
</body></html>"""

        asunto = f"Resultados de tu ranking {tipo_ranking.lower()} — {nombre_ciclo}"
        if _enviar(rm.email, asunto, cuerpo):
            enviados += 1

    logger.info(
        f"Notificaciones de ranking enviadas: {enviados}/{len(resultados)} "
        f"(pais_codigo={pais_codigo}, ciclo_id={ciclo_id}, tipo={tipo_ranking})"
    )
    return enviados


def notificar_reconocimiento_otorgado(
    db: Session,
    rm: RepresentanteMedico,
    premio: Premio,
    ciclo_id: Optional[int],
    posicion_ranking: Optional[int],
    score_total,
) -> bool:
    """
    Notifica a un RM que recibió un reconocimiento/premio recién generado.

    Retorna True si el correo se envió exitosamente; False si las
    notificaciones están deshabilitadas, el RM no tiene email registrado,
    o el envío falló. Nunca lanza — el llamador no debe interrumpir la
    generación de reconocimientos por un fallo de notificación.
    """
    if not _habilitado() or not rm or not rm.email:
        return False

    nombre_ciclo = _nombre_ciclo(db, ciclo_id)
    try:
        score_fmt = f"{float(score_total):.2f}"
    except (TypeError, ValueError):
        score_fmt = "—"

    cuerpo = f"""\
<html><body style="font-family:Arial,sans-serif;color:#333333;line-height:1.5;">
  <h2 style="color:{_COLOR_TITULO};">¡Tienes un nuevo reconocimiento!</h2>
  <p>Hola {rm.nombre},</p>
  <p>Te otorgamos el premio <strong>{premio.nombre}</strong> correspondiente
     al ciclo <strong>{nombre_ciclo}</strong>, en reconocimiento a tu
     desempeño:</p>
  <ul>
    <li>Posición en el ranking: <strong>{posicion_ranking if posicion_ranking is not None else '—'}</strong></li>
    <li>Score total (IUP): <strong>{score_fmt}</strong></li>
  </ul>
  <p>Tu certificado estará disponible próximamente en el sistema.</p>
  {_pie_pagina()}
</body></html>"""

    asunto = f"¡Felicitaciones! Recibiste el premio {premio.nombre}"
    return _enviar(rm.email, asunto, cuerpo)


def notificar_resultado_examen(
    destinatario: str,
    nombre_visitador: str,
    examen_nombre: str,
    producto: Optional[str],
    score,
    aprobado: bool,
    correctas: int,
    total: int,
    fecha_fin: Optional[str] = None,
    link: Optional[str] = None,
) -> bool:
    """
    Notifica al evaluado el resultado de un examen entregado (spec §8).

    Retorna True si el correo se envió; False si las notificaciones están
    deshabilitadas o no hay destinatario. Nunca lanza — el llamador no debe
    interrumpir la entrega del examen por un fallo de notificación.
    """
    if not _habilitado() or not destinatario:
        return False

    estado = "APROBADO" if aprobado else "REPROBADO"
    color = "#2e7d32" if aprobado else "#c62828"
    prod = f"<li>Producto: <strong>{producto}</strong></li>" if producto else ""
    enlace = (f"<p><a href='{link}'>Ver el reporte en la plataforma</a></p>" if link else "")
    fecha = f"<li>Fecha: <strong>{fecha_fin}</strong></li>" if fecha_fin else ""

    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2>Resultado de Examen</h2>
  <p>Hola <strong>{nombre_visitador}</strong>, este es el resultado de tu examen:</p>
  <ul>
    <li>Examen: <strong>{examen_nombre}</strong></li>
    {prod}
    <li>Score: <strong>{score}%</strong></li>
    <li>Estado: <strong style="color:{color};">{estado}</strong></li>
    <li>Respuestas correctas: <strong>{correctas} de {total}</strong></li>
    {fecha}
  </ul>
  {enlace}
  {_pie_pagina()}
</body></html>"""

    asunto = f"Resultado de Examen - {examen_nombre} - {score}%"
    return _enviar(destinatario, asunto, cuerpo)


def notificar_asignacion_examen(destinatario: str, nombre: str, examen_nombre: str,
                                fecha_limite: Optional[str] = None,
                                link: Optional[str] = None) -> bool:
    """Avisa al evaluado que se le asignó un examen. SIN preguntas ni contenido — solo el
    aviso y el enlace a la plataforma. Best-effort (no rompe la asignación si falla)."""
    if not _habilitado() or not destinatario:
        return False
    fecha = f"<li>Fecha límite: <strong>{fecha_limite}</strong></li>" if fecha_limite else ""
    enlace = (f"<p><a href='{link}'>Entra a la plataforma para tomarlo</a></p>" if link else
              "<p>Entra a la plataforma, sección <strong>Mis Exámenes</strong>, para tomarlo.</p>")
    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2 style="color:{_COLOR_TITULO};">Nuevo examen asignado</h2>
  <p>Hola <strong>{nombre}</strong>, se te asignó un examen:</p>
  <ul>
    <li>Examen: <strong>{examen_nombre}</strong></li>
    {fecha}
  </ul>
  {enlace}
  {_pie_pagina()}
</body></html>"""
    return _enviar(destinatario, f"Nuevo examen asignado - {examen_nombre}", cuerpo)


def notificar_feedback_disponible(destinatario: str, nombre: str, examen_nombre: str,
                                  horas: int = 48, link: Optional[str] = None) -> bool:
    """Avisa que el feedback de un examen entregado ya está disponible EN LA PLATAFORMA.
    NO incluye score, correctas, estado ni PDF — el resultado solo se ve dentro de la app,
    y solo durante `horas` horas. Best-effort."""
    if not _habilitado() or not destinatario:
        return False
    enlace = (f"<p><a href='{link}'>Ver mi feedback en la plataforma</a></p>" if link else
              "<p>Entra a la plataforma, sección <strong>Mis Exámenes</strong>, para revisarlo.</p>")
    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2 style="color:{_COLOR_TITULO};">Tu feedback está disponible</h2>
  <p>Hola <strong>{nombre}</strong>, ya puedes revisar el feedback de tu examen
     <strong>{examen_nombre}</strong> en la plataforma.</p>
  <p style="color:#c0392b;"><strong>Disponible solo durante las próximas {horas} horas.</strong>
     Revísalo a tiempo — después dejará de mostrarse el detalle.</p>
  {enlace}
  {_pie_pagina()}
</body></html>"""
    return _enviar(destinatario, f"Feedback disponible - {examen_nombre}", cuerpo)


def _correo_evaluado(db, intento) -> Optional[str]:
    """Resuelve el email del evaluado (RM/Gerente) de un intento. None si no tiene."""
    from app.models.dimensiones import RepresentanteMedico, Gerente
    if intento.evaluado_rm_id:
        rm = db.query(RepresentanteMedico).filter(
            RepresentanteMedico.id == intento.evaluado_rm_id).first()
        return getattr(rm, "email", None) if rm else None
    g = db.query(Gerente).filter(Gerente.id == intento.evaluado_gerente_id).first()
    return getattr(g, "email", None) if g else None


def notificar_correcciones_examen(db, examen_id: int) -> int:
    """Envía a cada participante (último intento por asignación) la corrección de sus
    preguntas incorrectas: enunciado, opción elegida (✗), opción correcta (✓) y
    explicación. Best-effort: en modo demo (correo deshabilitado) NO envía pero cuenta
    los que habría notificado. Devuelve el número de correos (enviados o simulados)."""
    from app.models.exam_models import (
        Examen, IntentoRespuesta, Pregunta, PreguntaOpcion)
    from app.services.examen_resultados_service import (
        _ultimo_intento_por_asignacion, _nombres_por_intento)

    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if examen is None:
        return 0
    ultimos = _ultimo_intento_por_asignacion(db, examen_id)
    nombres = _nombres_por_intento(db, examen_id)
    habilitado = _habilitado()
    contador = 0
    for intento in ultimos.values():
        incorrectas = db.query(IntentoRespuesta).filter(
            IntentoRespuesta.intento_id == intento.id,
            IntentoRespuesta.es_correcta == False,
        ).all()
        if not incorrectas:
            continue
        filas = []
        for r in incorrectas:
            p = db.query(Pregunta).filter(Pregunta.id == r.pregunta_id).first()
            elegida = (db.query(PreguntaOpcion).filter(
                PreguntaOpcion.id == r.opcion_elegida_id).first()
                if r.opcion_elegida_id else None)
            correcta = next((o for o in (p.opciones if p else []) if o.es_correcta), None)
            filas.append(
                f"<li style='margin-bottom:10px;'><strong>{p.texto if p else ''}</strong><br>"
                f"<span style='color:#c62828;'>✗ Tu respuesta: {elegida.texto_opcion if elegida else '—'}</span><br>"
                f"<span style='color:#2e7d32;'>✓ Correcta: {correcta.texto_opcion if correcta else '—'}</span><br>"
                f"<em>{(p.explicacion if p else '') or ''}</em></li>")
        cuerpo = (f"<html><body style=\"font-family:Arial,sans-serif;color:#333;\">"
                  f"<h2>Correcciones — {examen.nombre}</h2>"
                  f"<p>Hola <strong>{nombres.get(intento.id, '')}</strong>, estas son las "
                  f"correcciones de las preguntas que respondiste incorrectamente:</p>"
                  f"<ul>{''.join(filas)}</ul>{_pie_pagina()}</body></html>")
        asunto = f"Correcciones de tu examen — {examen.nombre}"
        destinatario = _correo_evaluado(db, intento)
        if habilitado and destinatario:
            if _enviar(destinatario, asunto, cuerpo):
                contador += 1
        elif not habilitado:
            contador += 1  # modo demo: cuenta como simulado
    logger.info(f"Correcciones examen {examen_id}: {contador} correos (enviados/simulados)")
    return contador


def notificar_codigo_recuperacion(destinatario: str, nombre: str, codigo: str, minutos: int = 15) -> bool:
    """Envía el código de recuperación de contraseña ("Olvidó su contraseña").

    Retorna True si se envió; False si las notificaciones están deshabilitadas o
    no hay destinatario. Nunca lanza (el endpoint responde genérico igual)."""
    if not _habilitado() or not destinatario:
        return False
    cuerpo = f"""<html><body style="font-family:Arial,sans-serif;color:#333;">
  <h2>Recuperación de contraseña</h2>
  <p>Hola {nombre or ''},</p>
  <p>Recibimos una solicitud para restablecer tu contraseña. Usa el siguiente código:</p>
  <p style="font-size:28px;font-weight:bold;letter-spacing:6px;color:#1a237e;margin:16px 0;">{codigo}</p>
  <p>Este código vence en <strong>{minutos} minutos</strong> y solo puede usarse una vez.</p>
  <p style="color:#888;font-size:13px;">Si no solicitaste este cambio, ignora este correo; tu contraseña no cambiará.</p>
  <hr><p style="color:#aaa;font-size:12px;">Sistema MIP — SCGCPR</p>
</body></html>"""
    return _enviar(destinatario, "Código de recuperación de contraseña", cuerpo)
