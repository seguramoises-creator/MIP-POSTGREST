"""Correo de bienvenida al crear un usuario."""
from app.services import notification_service as svc


def _capturar(monkeypatch):
    """Intercepta el envío y devuelve lo que se habría mandado."""
    salida = {}
    monkeypatch.setattr(svc, "_habilitado", lambda: True)
    monkeypatch.setattr(svc, "mail_config", lambda: {
        "server": "smtp.gmail.com", "port": 587, "username": "u", "password": "p",
        "from": "no-reply@vista.com", "from_name": "VISTA", "tls": True, "ssl": False})
    monkeypatch.setattr(svc, "_enviar",
                        lambda dest, asunto, cuerpo: salida.update(
                            dest=dest, asunto=asunto, cuerpo=cuerpo) or True)
    return salida


def test_lleva_nombre_del_sistema_y_enlace(monkeypatch):
    out = _capturar(monkeypatch)
    monkeypatch.setattr(svc.settings, "PUBLIC_BASE_URL", "https://vista-mip.com", raising=False)
    assert svc.notificar_bienvenida("nuevo@x.com", "Ana Pérez", "aperez") is True
    assert "VISTA" in out["asunto"]
    assert "https://vista-mip.com" in out["cuerpo"], "debe incluir el enlace de acceso"
    assert "aperez" in out["cuerpo"], "debe indicar el usuario"
    assert "cambiarla" in out["cuerpo"], "debe avisar que se le pedirá cambiar la contraseña"


def test_nunca_incluye_una_contrasena(monkeypatch):
    """Una clave enviada por correo queda para siempre en el buzón: el correo no la lleva."""
    out = _capturar(monkeypatch)
    svc.notificar_bienvenida("nuevo@x.com", "Ana", "aperez")
    cuerpo = out["cuerpo"]
    assert "contraseña temporal que te entregó" in cuerpo   # se referencia, no se incluye
    for pista in ("password=", "clave:", "contraseña:"):
        assert pista not in cuerpo.lower()


def test_sin_destinatario_no_envia(monkeypatch):
    _capturar(monkeypatch)
    assert svc.notificar_bienvenida("", "Ana", "aperez") is False
