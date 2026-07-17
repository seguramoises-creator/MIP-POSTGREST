"""Tests de la ventana de 48h del feedback + las notificaciones de examen (jul-2026).

Reglas del cliente:
  1. El representante recibe correo cuando le asignan un examen (antes: no existía).
  2. Al entregar, el correo es un AVISO — el resultado se ve solo in-app, no por correo/PDF.
  3. El feedback (detalle bien/mal) se ve solo 48h desde la entrega; después, solo la nota.
"""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from unittest.mock import patch

from app.services import examen_intento_service as svc
from app.services import notification_service as notif


# ── Ventana de 48h: feedback_vencido ──────────────────────────────────────────

def _intento(horas_desde_entrega, tz=True):
    fin = datetime.now(timezone.utc) - timedelta(hours=horas_desde_entrega)
    if not tz:
        fin = fin.replace(tzinfo=None)   # como se guarda en la BD (naïve-UTC)
    return SimpleNamespace(fecha_fin=fin)


def test_dentro_de_48h_el_feedback_no_esta_vencido():
    assert svc.feedback_vencido(_intento(1)) is False
    assert svc.feedback_vencido(_intento(47)) is False


def test_pasadas_48h_el_feedback_esta_vencido():
    assert svc.feedback_vencido(_intento(49)) is True


def test_el_borde_de_48h_es_exacto():
    # 48h justas aún no venció (>, no >=); 48h y pico, sí.
    assert svc.feedback_vencido(_intento(48 - 0.01)) is False
    assert svc.feedback_vencido(_intento(48 + 0.01)) is True


def test_fecha_fin_naive_se_trata_como_utc():
    """La BD guarda `fecha_fin` sin tz; compararla ingenuamente reventaría o daría mal."""
    assert svc.feedback_vencido(_intento(49, tz=False)) is True
    assert svc.feedback_vencido(_intento(1, tz=False)) is False


def test_intento_sin_entregar_no_esta_vencido():
    assert svc.feedback_vencido(SimpleNamespace(fecha_fin=None)) is False


def test_el_endpoint_poda_el_detalle_cuando_vence():
    """Regresión: el guard vive en el endpoint (tiene el rol), no en generar_reporte."""
    import inspect
    from app.api.v1.routers import examenes
    fuente = inspect.getsource(examenes.reporte)
    assert "feedback_vencido" in fuente
    assert '"respuestas"] = []' in fuente or "'respuestas'] = []" in fuente


# ── Notificaciones: son best-effort y sin contenido sensible ──────────────────

def test_notificar_asignacion_no_manda_sin_smtp():
    with patch.object(notif, "_habilitado", return_value=False):
        assert notif.notificar_asignacion_examen("a@b.com", "Ana", "Examen X") is False


def test_notificar_asignacion_sin_destinatario_no_manda():
    with patch.object(notif, "_habilitado", return_value=True):
        assert notif.notificar_asignacion_examen("", "Ana", "Examen X") is False


def test_el_aviso_de_feedback_no_lleva_score_ni_detalle():
    """El correo post-entrega es solo un aviso: nada de score/correctas/respuestas."""
    capturado = {}
    with patch.object(notif, "_habilitado", return_value=True), \
         patch.object(notif, "_enviar", side_effect=lambda d, a, c: capturado.update(asunto=a, cuerpo=c) or True):
        notif.notificar_feedback_disponible("a@b.com", "Ana", "Examen X", horas=48, link="/mis-examenes")
    assert "48" in capturado["cuerpo"]                 # menciona la ventana
    assert "plataforma" in capturado["cuerpo"].lower()  # lo manda a la app
    # No filtra el resultado:
    for prohibido in ("score", "correctas", "aprobado", "reprobado", "%"):
        assert prohibido.lower() not in capturado["cuerpo"].lower(), f"el aviso no debe traer {prohibido!r}"


def test_asignar_examen_dispara_la_notificacion():
    """Regresión del bug original: asignar_examen recibía notif_activa pero no notificaba."""
    import inspect
    from app.services import examen_service
    fuente = inspect.getsource(examen_service.asignar_examen)
    assert "_notificar_asignaciones" in fuente
