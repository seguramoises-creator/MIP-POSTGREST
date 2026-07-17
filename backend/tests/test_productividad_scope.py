"""Tests del alcance de datos en Productividad (jul-2026).

Regla del cliente: "los representantes solo deben ver sus datos, no pueden ver ningún otro
dato de ningún otro visitador; pueden ver el acumulado de su línea de negocio, no detalles
independientes de otros visitadores".
"""
import inspect

from app.api.v1.routers import productividad as router_prod
from app.models.usuario import Rol


# ── Fail-closed: un representante sin rm_id NO puede ver a todos ──────────────

def test_representante_sin_rm_id_se_deniega_no_se_ignora_el_filtro():
    """REGRESIÓN: el filtro era `if rol == RM and current_user.rm_id`. Con rm_id nulo la
    condición era falsa, el filtro NO se aplicaba y el representante veía a TODOS los RMs.
    Un fallo de seguridad que no da error: simplemente muestra de más."""
    fuente = inspect.getsource(router_prod.get_productividad)
    assert "if not current_user.rm_id" in fuente
    assert "403" in fuente
    # La condición vieja (fail-open) no debe volver.
    assert "REPRESENTANTE_MEDICO and current_user.rm_id" not in fuente


# ── Los endpoints agregados no admiten representantes ─────────────────────────

def _roles_de(fn):
    """Roles exigidos por el Depends(require_roles(...)) de la firma."""
    return inspect.getsource(fn)


def test_productividad_por_pais_no_admite_representantes():
    """Devuelve fila por fila de TODOS los RMs del país: un representante no puede entrar."""
    fuente = _roles_de(router_prod.get_productividad_pais)
    assert "REPRESENTANTE_MEDICO" not in fuente


def test_resumen_ejecutivo_no_admite_representantes():
    fuente = _roles_de(router_prod.get_resumen_productividad)
    assert "REPRESENTANTE_MEDICO" not in fuente


def test_kpis_de_otro_rm_se_deniegan():
    """`/productividad/rm/{id}` con el id de un colega debe rechazarse."""
    fuente = inspect.getsource(router_prod.get_productividad_rm)
    assert "current_user.rm_id != rm_id" in fuente


# ── Mi línea: agregado sí, individuos no ─────────────────────────────────────

def test_mi_linea_exige_ser_representante_y_tener_rm_id():
    fuente = inspect.getsource(router_prod.get_mi_linea)
    assert "!= Rol.REPRESENTANTE_MEDICO" in fuente
    assert "if not current_user.rm_id" in fuente


def test_mi_linea_solo_devuelve_agregados_de_la_linea():
    """De la línea solo pueden salir promedio y nº de RMs — nunca filas por representante."""
    fuente = inspect.getsource(router_prod.get_mi_linea)
    assert '"cumplimiento_pct"' in fuente and '"rms"' in fuente
    # Si alguien añadiera nombres de colegas al agregado, esto lo delata.
    assert "rm_nombre" not in fuente


def test_el_umbral_de_la_linea_impide_despejar_al_otro():
    """Con 2 RMs, promedio×2 − el mío = el del otro, exacto. El mínimo debe ser 3."""
    assert router_prod.MIN_RMS_LINEA >= 3


def test_bajo_el_umbral_se_oculta_el_promedio_con_motivo():
    fuente = inspect.getsource(router_prod.get_mi_linea)
    assert "MIN_RMS_LINEA" in fuente
    assert "linea_oculta_motivo" in fuente


def test_el_rol_representante_existe():
    """Ancla: si el enum se renombra, los asserts de arriba dejarían de proteger nada."""
    assert Rol.REPRESENTANTE_MEDICO.value == "REPRESENTANTE_MEDICO"
