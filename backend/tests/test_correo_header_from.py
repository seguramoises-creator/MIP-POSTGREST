"""El header `From` debe llevar una dirección parseable, aunque el nombre tenga acentos.

Regresión jul-2026 (producción). El nombre del remitente configurado en
Admin → Servidor de Correo era "VISTA-Sistema Corporativo de Gestión Comercial". El código
armaba el header como UNA sola cadena, `f"{nombre} <{dirección}>"`. Al serializar, la
política `compat32` de Python intenta codificar el header en us-ascii, falla por la tilde
de "Gestión" y recodifica TODO el valor como una palabra RFC 2047 — arrastrando la
dirección adentro:

    From: =?utf-8?q?VISTA-..._Gesti=C3=B3n_Comercial_=3Cinfo=40vista-mip=2Ecom=3E?=

Ese `=3C` es el '<' y ese `=40` es la '@': la dirección quedó sepultada y el header no
tiene ninguna dirección válida. Hostinger lo aceptaba y lo entregaba en buzones del MISMO
dominio (no valida RFC 5322), así que el correo interno parecía funcionar; Google lo
rechazaba con `550 5.7.1 Messages missing a valid address in From: header`, y TODO el
correo externo —altas de usuario incluidas— rebotaba sin que la aplicación se enterara,
porque `sendmail()` sí había tenido éxito.

La cura es `email.utils.formataddr`, que codifica SOLO el nombre y deja la dirección como
angle-addr fuera de la palabra codificada.
"""
import email
from email.utils import parseaddr

import pytest

from app.services import notification_service as ns

NOMBRE_CON_TILDE = "VISTA-Sistema Corporativo de Gestión Comercial"
REMITENTE = "info-inteligeciacomercial@vista-mip.com"


class _SmtpFalso:
    """Doble de smtplib: guarda el mensaje serializado en vez de enviarlo."""

    capturado: dict = {}

    def __init__(self, *a, **k):
        pass

    def login(self, *a, **k):
        pass

    def starttls(self, *a, **k):
        pass

    def sendmail(self, remitente, destinatarios, mensaje):
        _SmtpFalso.capturado = {"remitente": remitente,
                                "destinatarios": destinatarios, "mensaje": mensaje}

    def quit(self):
        pass


def _cfg():
    return {"server": "smtp.hostinger.com", "port": 465, "username": REMITENTE,
            "password": "secreta", "from": REMITENTE, "from_name": NOMBRE_CON_TILDE,
            "tls": False, "ssl": True}


@pytest.fixture
def smtp_falso(monkeypatch):
    """Config SMTP con nombre acentuado (la real de producción) + SMTP capturado."""
    monkeypatch.setattr(ns, "mail_config", _cfg)
    monkeypatch.setattr(ns.smtplib, "SMTP_SSL", _SmtpFalso)
    _SmtpFalso.capturado = {}
    return _SmtpFalso


def _header_from(mensaje: str) -> str:
    return email.message_from_string(mensaje)["From"]


def test_from_lleva_una_direccion_parseable(smtp_falso):
    assert ns._enviar("destino@gmail.com", "Asunto de prueba", "<p>hola</p>") is True
    cabecera = _header_from(smtp_falso.capturado["mensaje"])
    _, direccion = parseaddr(cabecera)
    assert direccion == REMITENTE, (
        "Google rechaza con 550 5.7.1 un From sin dirección parseable. "
        f"Header generado: {cabecera!r}")


def test_la_direccion_no_queda_dentro_de_la_palabra_codificada(smtp_falso):
    ns._enviar("destino@gmail.com", "Asunto de prueba", "<p>hola</p>")
    cabecera = _header_from(smtp_falso.capturado["mensaje"])
    assert "=3C" not in cabecera and "=40" not in cabecera, (
        "el '<' y la '@' quedaron codificados dentro del encoded-word RFC 2047: "
        f"la dirección está sepultada en el nombre. Header: {cabecera!r}")


def test_el_nombre_acentuado_se_conserva(smtp_falso):
    """La cura no debe ser borrar la tilde: el nombre visible se conserva codificado."""
    ns._enviar("destino@gmail.com", "Asunto de prueba", "<p>hola</p>")
    cabecera = _header_from(smtp_falso.capturado["mensaje"])
    nombre, _ = parseaddr(cabecera)
    assert email.header.make_header(
        email.header.decode_header(nombre)).__str__() == NOMBRE_CON_TILDE


def test_hoja_de_coaching_usa_el_mismo_header_valido(monkeypatch):
    """`coaching_more_pdf._enviar_pdf` arma el header por su cuenta: mismo defecto."""
    from app.services import coaching_more_pdf as pdf_svc

    monkeypatch.setattr(ns, "mail_config", _cfg)
    monkeypatch.setattr(pdf_svc.smtplib, "SMTP_SSL", _SmtpFalso)
    _SmtpFalso.capturado = {}

    assert pdf_svc._enviar_pdf("destino@gmail.com", "Hoja de coaching",
                               "<p>adjunta</p>", b"%PDF-1.4 fake", "hoja.pdf") is True
    cabecera = _header_from(_SmtpFalso.capturado["mensaje"])
    _, direccion = parseaddr(cabecera)
    assert direccion == REMITENTE, f"Header generado: {cabecera!r}"
