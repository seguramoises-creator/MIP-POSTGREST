"""Todo correo debe llevar una parte `text/plain` además del HTML.

`_enviar` construía un `multipart/alternative` con UNA sola parte, la HTML. Eso tiene dos
consecuencias:

1. Un `multipart/alternative` cuya única alternativa es HTML es una señal de spam clásica
   (los filtros la puntúan como correo generado por una plantilla, no por una persona).
2. Cualquier cliente que no renderice HTML —o el usuario que lo desactiva por seguridad—
   se queda sin contenido, incluido el ENLACE DE ACTIVACIÓN, que es la única forma de
   entrar al sistema para un usuario nuevo.

El orden importa y es contraintuitivo: RFC 2046 §5.1.4 exige las partes de MENOR a MAYOR
fidelidad, así que `text/plain` va PRIMERO y `text/html` al final. Al revés, muchos
clientes muestran el texto pelado en lugar del HTML.
"""
import email

import pytest

from app.services import notification_service as ns

REMITENTE = "info@vista-mip.com"


class _SmtpFalso:
    capturado: dict = {}

    def __init__(self, *a, **k):
        pass

    def login(self, *a, **k):
        pass

    def starttls(self, *a, **k):
        pass

    def sendmail(self, remitente, destinatarios, mensaje):
        _SmtpFalso.capturado = {"mensaje": mensaje}

    def quit(self):
        pass


def _cfg():
    return {"server": "smtp.hostinger.com", "port": 465, "username": REMITENTE,
            "password": "secreta", "from": REMITENTE, "from_name": "VISTA — Gestión",
            "tls": False, "ssl": True}


@pytest.fixture
def smtp_falso(monkeypatch):
    monkeypatch.setattr(ns, "mail_config", _cfg)
    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", _SmtpFalso)
    _SmtpFalso.capturado = {}
    return _SmtpFalso


def _partes(mensaje: str):
    msg = email.message_from_string(mensaje)
    return [p for p in msg.walk() if p.get_content_maintype() != "multipart"]


def _texto_de(mensaje: str) -> str:
    for p in _partes(mensaje):
        if p.get_content_type() == "text/plain":
            return p.get_payload(decode=True).decode("utf-8")
    return ""


CUERPO = ("<html><body><h2>Título</h2><p>Hola <strong>Ana</strong>:</p>"
          "<ul><li>Uno</li><li>Dos</li></ul>"
          "<p>Costo &amp; ROI</p><p>Fin.<br>Gracias</p></body></html>")


def test_lleva_parte_de_texto_y_parte_html(smtp_falso):
    ns._enviar("destino@gmail.com", "Asunto", CUERPO)
    tipos = [p.get_content_type() for p in _partes(smtp_falso.capturado["mensaje"])]
    assert "text/plain" in tipos and "text/html" in tipos, tipos


def test_el_texto_plano_va_antes_del_html(smtp_falso):
    """RFC 2046: de menor a mayor fidelidad. Invertirlo hace que se muestre el texto."""
    ns._enviar("destino@gmail.com", "Asunto", CUERPO)
    tipos = [p.get_content_type() for p in _partes(smtp_falso.capturado["mensaje"])]
    assert tipos == ["text/plain", "text/html"], tipos


def test_el_texto_plano_no_arrastra_etiquetas(smtp_falso):
    ns._enviar("destino@gmail.com", "Asunto", CUERPO)
    texto = _texto_de(smtp_falso.capturado["mensaje"])
    assert "<" not in texto and ">" not in texto, texto
    assert "Ana" in texto and "Título" in texto


def test_las_vinetas_se_leen_como_lista(smtp_falso):
    ns._enviar("destino@gmail.com", "Asunto", CUERPO)
    texto = _texto_de(smtp_falso.capturado["mensaje"])
    assert "- Uno" in texto and "- Dos" in texto, texto


def test_las_entidades_html_se_decodifican(smtp_falso):
    ns._enviar("destino@gmail.com", "Asunto", CUERPO)
    assert "Costo & ROI" in _texto_de(smtp_falso.capturado["mensaje"])


def test_el_enlace_de_activacion_sobrevive_en_el_texto(smtp_falso):
    """Sin esto, un usuario con el HTML desactivado no puede activar su cuenta."""
    enlace = "https://vista-mip.com/activar/AbC123-token"
    ns.notificar_activacion_cuenta("nuevo@gmail.com", "Ana Pérez", "aperez", enlace)
    texto = _texto_de(smtp_falso.capturado["mensaje"])
    assert enlace in texto, texto


def test_hoja_de_coaching_lleva_texto_plano_junto_al_adjunto(monkeypatch):
    """El correo con PDF es `mixed`: dentro debe ir un `alternative` con las dos partes."""
    from app.services import coaching_more_pdf as pdf_svc

    monkeypatch.setattr(ns, "mail_config", _cfg)
    monkeypatch.setattr(pdf_svc.smtplib, "SMTP_SSL", _SmtpFalso)
    _SmtpFalso.capturado = {}

    assert pdf_svc._enviar_pdf("destino@gmail.com", "Hoja", "<p>Adjunta la <b>hoja</b>.</p>",
                               b"%PDF-1.4 fake", "hoja.pdf") is True
    tipos = [p.get_content_type() for p in _partes(_SmtpFalso.capturado["mensaje"])]
    assert tipos == ["text/plain", "text/html", "application/pdf"], tipos
