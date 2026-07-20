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
    for pista in ("password=", "clave:", "contraseña:"):
        assert pista not in cuerpo.lower()


def test_dice_EXPLICITAMENTE_que_la_contrasena_no_viene_en_el_correo(monkeypatch):
    """Regresión jul-2026: el texto decía "ingresa con la contraseña temporal que te entregó
    tu administrador" y el destinatario la buscaba dentro del mensaje, reportando que "el
    correo dice contraseña temporal pero no llega la contraseña". No basta con omitirla: hay
    que decir que no está aquí y por dónde se obtiene."""
    out = _capturar(monkeypatch)
    svc.notificar_bienvenida("nuevo@x.com", "Ana", "aperez")
    cuerpo = out["cuerpo"].lower()
    assert "no se envía por correo" in cuerpo
    assert "olvidó su contraseña" in cuerpo, "debe ofrecer la vía de autoservicio"


def test_no_promete_una_contrasena_dentro_del_mensaje(monkeypatch):
    """Ninguna frase debe sugerir que la clave viaja en este correo."""
    out = _capturar(monkeypatch)
    svc.notificar_bienvenida("nuevo@x.com", "Ana", "aperez")
    cuerpo = out["cuerpo"].lower()
    for frase in ("contraseña temporal que te entregó", "tu contraseña es", "a continuación"):
        assert frase not in cuerpo, f"redacción ambigua: {frase!r}"


def test_sin_destinatario_no_envia(monkeypatch):
    _capturar(monkeypatch)
    assert svc.notificar_bienvenida("", "Ana", "aperez") is False
