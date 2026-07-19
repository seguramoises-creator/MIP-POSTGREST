"""Envío por correo de la hoja de coaching (MORE).

Regresión jul-2026: el módulo leía `settings.MAIL_*` directo, mientras el resto del
sistema usa la config guardada por el ADMIN en BD (`notification_service.mail_config`).
Si el SMTP se configuraba desde Admin y el `.env` estaba vacío, la hoja NUNCA se enviaba
—en silencio— aunque todos los demás correos sí llegaran.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import coaching_more_pdf as svc


def test_usa_la_config_de_la_bd_no_solo_el_env(monkeypatch):
    """Con el .env vacío pero SMTP configurado en BD, debe intentar enviar igual."""
    monkeypatch.setattr("app.services.notification_service.mail_config", lambda: {
        "server": "smtp.gmail.com", "port": 587, "username": "u", "password": "p",
        "from": "no-reply@vista.com", "from_name": "VISTA", "tls": True, "ssl": False})
    enviados = []

    class _SMTP:
        def __init__(self, *a, **k): pass
        def starttls(self): pass
        def login(self, u, p): pass
        def sendmail(self, de, para, msg): enviados.append((de, para))
        def quit(self): pass

    monkeypatch.setattr(svc.smtplib, "SMTP", _SMTP)
    ok = svc._enviar_pdf("rm@x.com", "Asunto", "<p>hola</p>", b"%PDF-", "c.pdf")
    assert ok and enviados == [("no-reply@vista.com", ["rm@x.com"])]


def test_sin_servidor_configurado_es_no_op(monkeypatch):
    monkeypatch.setattr("app.services.notification_service.mail_config", lambda: {
        "server": "", "port": 587, "username": "", "password": "",
        "from": "", "from_name": "", "tls": False, "ssl": False})
    assert svc._enviar_pdf("rm@x.com", "A", "<p>h</p>", b"%PDF-", "c.pdf") is False


def test_correo_cae_al_usuario_vinculado_si_el_catalogo_no_lo_tiene():
    """DIM_RM suele venir del Excel sin correo; el usuario vinculado sí lo tiene real."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = SimpleNamespace(email="real@vista.com")
    rm = SimpleNamespace(id=7, email=None)
    assert svc._correo_del_rm(db, rm) == "real@vista.com"


def test_prefiere_el_correo_del_catalogo_si_existe():
    db = MagicMock()
    rm = SimpleNamespace(id=7, email="  catalogo@vista.com ")
    assert svc._correo_del_rm(db, rm) == "catalogo@vista.com"
