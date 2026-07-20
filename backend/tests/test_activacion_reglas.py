# -*- coding: utf-8 -*-
"""Reglas de negocio del alta de usuario por enlace de activación (jul-2026).

Estas reglas viven en los routers (necesitan Request/HTTPException), así que se
verifican sobre el código fuente. Es una prueba de contrato deliberadamente
tosca, pero cubre justo las tres cosas que dejarían a un usuario fuera del
sistema sin que nadie se entere hasta que él llame por teléfono.
"""
import inspect

from app.api.v1.routers import admin as admin_router
from app.api.v1.routers import auth as auth_router
from app.services import password_reset_service


# ── El login no debe castigar a quien todavía no activó ──────────────────────

def test_el_login_corta_antes_de_verificar_la_password_de_una_cuenta_sin_activar():
    """Una cuenta sin activar tiene una contraseña aleatoria que nadie conoce. Si se
    dejara caer en la verificación normal, sumaría intentos fallidos y a los 3 quedaría
    BLOQUEADA por algo que el usuario no puede resolver adivinando."""
    fuente = inspect.getsource(auth_router.login)
    pos_guard = fuente.find("activado_en is None")
    pos_verify = fuente.find("verify_password")
    assert pos_guard != -1, "falta el guard de cuenta sin activar en el login"
    assert pos_guard < pos_verify, ("el guard debe ir ANTES de verify_password; si no, el "
                                    "usuario suma intentos fallidos y se autobloquea")


def test_el_mensaje_de_cuenta_sin_activar_dice_que_hacer():
    fuente = inspect.getsource(auth_router.login)
    assert "no ha sido activada" in fuente
    assert "enlace de activación" in fuente


# ── Puente con "¿Olvidó su contraseña?" ──────────────────────────────────────

def test_restablecer_por_codigo_tambien_activa_la_cuenta():
    """El login remite a "¿Olvidó su contraseña?" cuando el enlace venció. Si ese flujo
    no marcara `activado_en`, el usuario fijaría una contraseña válida y el login se la
    seguiría rechazando por "cuenta sin activar" — un callejón sin salida."""
    fuente = inspect.getsource(password_reset_service.restablecer)
    assert "activado_en" in fuente


# ── Alta de usuario ──────────────────────────────────────────────────────────

def test_sin_correo_y_sin_password_el_alta_se_rechaza():
    """No hay dónde enviar el enlace: crear la cuenta así la dejaría inaccesible para
    siempre, con una contraseña aleatoria que nadie conoce."""
    fuente = inspect.getsource(admin_router.create_usuario)
    assert "422" in fuente
    assert "enlace de activación" in fuente


def test_sin_password_se_genera_un_hash_aleatorio_y_queda_sin_activar():
    fuente = inspect.getsource(admin_router.create_usuario)
    assert "secrets.token_urlsafe" in fuente, "la contraseña provisional debe ser aleatoria"
    assert 'payload["activado_en"] = None' in fuente


def test_con_password_del_admin_la_cuenta_nace_activada():
    """El administrador entregó credenciales que ya funcionan: exigirle además abrir un
    enlace de activación sería pedirle dos pasos para lo mismo."""
    fuente = inspect.getsource(admin_router.create_usuario)
    assert "por_activacion" in fuente
    assert "debe_cambiar_password" in fuente


def test_el_alta_manda_enlace_de_activacion_y_no_la_contrasena():
    fuente = inspect.getsource(admin_router.create_usuario)
    assert "enviar_activacion" in fuente
    # La contraseña nunca debe acabar dentro de un correo.
    assert "password" not in fuente.split("notificar_bienvenida")[1][:400]


# ── Reenvío por el administrador ─────────────────────────────────────────────

def test_reenviar_a_una_cuenta_ya_activada_se_rechaza():
    """Si no, cualquiera que sepa el correo de un usuario podría pedir un enlace y
    cambiarle la contraseña. Para eso está la recuperación por código."""
    fuente = inspect.getsource(admin_router.reenviar_activacion_usuario)
    assert "409" in fuente
    assert "activado_en is not None" in fuente


def test_reenviar_sin_correo_se_rechaza_con_mensaje_util():
    fuente = inspect.getsource(admin_router.reenviar_activacion_usuario)
    assert "no tiene correo registrado" in fuente


def test_si_el_correo_no_sale_el_admin_se_entera():
    """Un reenvío que responde OK sin haber enviado nada es peor que un error: el admin
    se queda esperando y el usuario nunca recibe el enlace."""
    fuente = inspect.getsource(admin_router.reenviar_activacion_usuario)
    assert "502" in fuente


# ── Endpoints públicos: sin filtrar información ──────────────────────────────

def test_el_reenvio_publico_responde_siempre_lo_mismo():
    """No debe revelar si el correo está registrado ni si la cuenta ya estaba activada."""
    fuente = inspect.getsource(auth_router.reenviar_activacion)
    assert "_MSG_ACTIVACION_GENERICO" in fuente
    # Un único return: cualquier bifurcación sería un canal para deducir el estado.
    assert fuente.count("return ") == 1


def test_una_password_debil_no_consume_el_enlace():
    """Si la política rechazara la contraseña DESPUÉS de marcar el token como usado, un
    error de tipeo dejaría al usuario sin enlace y sin cuenta."""
    from app.services import activacion_service
    fuente = inspect.getsource(activacion_service.activar)
    pos_valida = fuente.find("validar_complejidad")
    pos_consume = fuente.find("fila.usado = True")
    assert pos_valida < pos_consume
