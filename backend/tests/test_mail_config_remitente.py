"""mail_config: el remitente debe ser SIEMPRE una dirección válida.

Regresión jul-2026: en producción el ADMIN escribió el NOMBRE del sistema en el campo
MAIL_FROM ("VISTA - Sistema Corporativo de Gestión Comercial"). Ese valor se usa como
remitente de sobre en sendmail(), el servidor lo rechaza por no ser una dirección, y
TODOS los correos del sistema dejan de salir — sin error visible en la aplicación.
"""
import pytest

from app.services import notification_service as svc
from app.services import config_service


@pytest.fixture
def cfg_bd(monkeypatch):
    """Simula la configuración SMTP guardada en BD (Admin → Servidor de Correo)."""
    def _hacer(valores: dict):
        monkeypatch.setattr(config_service, "obtener",
                            lambda db, k: valores.get(k), raising=False)
        monkeypatch.setattr(config_service, "obtener_bool",
                            lambda db, k, d=False: d, raising=False)
        return svc.mail_config()
    return _hacer


def test_nombre_en_el_campo_from_se_corrige(cfg_bd):
    cfg = cfg_bd({"MAIL_SERVER": "smtp.gmail.com", "MAIL_USERNAME": "cuenta@gmail.com",
                  "MAIL_FROM": "VISTA - Sistema Corporativo de Gestión Comercial",
                  "MAIL_FROM_NAME": ""})
    assert "@" in cfg["from"], "el remitente debe ser una dirección válida"
    assert cfg["from"] == "cuenta@gmail.com"
    # El texto mal puesto no se pierde: se reaprovecha como nombre para mostrar.
    assert cfg["from_name"] == "VISTA - Sistema Corporativo de Gestión Comercial"


def test_direccion_valida_se_respeta(cfg_bd):
    cfg = cfg_bd({"MAIL_SERVER": "smtp.gmail.com", "MAIL_USERNAME": "cuenta@gmail.com",
                  "MAIL_FROM": "noreply@vista-mip.com", "MAIL_FROM_NAME": "VISTA"})
    assert cfg["from"] == "noreply@vista-mip.com" and cfg["from_name"] == "VISTA"


def test_from_vacio_usa_la_cuenta_autenticada(cfg_bd):
    cfg = cfg_bd({"MAIL_SERVER": "smtp.gmail.com", "MAIL_USERNAME": "cuenta@gmail.com",
                  "MAIL_FROM": "", "MAIL_FROM_NAME": "VISTA"})
    assert cfg["from"] == "cuenta@gmail.com" and cfg["from_name"] == "VISTA"
