"""Tests del alcance de datos en Ranking (jul-2026).

Decisión del cliente: el representante ve SU POSICIÓN ("estás 12 de 45"), no el ranking
completo. Publicar la tabla con nombres y puntajes sería exponer el dato individual de cada
colega a los otros 44 — lo contrario de la regla que fijó para Productividad.
"""
import inspect

from app.api.v1.routers import ranking as router_rk


def test_representante_sin_rm_id_se_deniega_no_ve_el_ranking_completo():
    """REGRESIÓN: el filtro era `if rol == RM and current_user.rm_id`. Con rm_id nulo la
    condición era falsa, el filtro NO se aplicaba y el representante veía el ranking COMPLETO
    de sus 44 compañeros. Fallo de seguridad silencioso: no da error, solo muestra de más."""
    fuente = inspect.getsource(router_rk.get_ranking)
    assert "if not current_user.rm_id" in fuente
    assert "403" in fuente
    assert "REPRESENTANTE_MEDICO and current_user.rm_id" not in fuente  # la vieja, fail-open


def test_mi_posicion_exige_ser_representante_con_rm_id():
    fuente = inspect.getsource(router_rk.get_mi_posicion)
    assert "!= Rol.REPRESENTANTE_MEDICO" in fuente
    assert "if not current_user.rm_id" in fuente


def test_mi_posicion_no_devuelve_datos_de_colegas():
    """Del universo solo pueden salir CONTEOS. Si alguien añadiera nombres o filas ajenas,
    esto lo delata."""
    fuente = inspect.getsource(router_rk.get_mi_posicion)
    assert ".count()" in fuente                      # el universo se cuenta...
    assert "rm_nombre" not in fuente                 # ...nunca se nombra
    assert '"posicion"' in fuente and '"total"' in fuente   # el letrero "X de Y"


def test_mi_posicion_filtra_por_su_propio_rm_id():
    fuente = inspect.getsource(router_rk.get_mi_posicion)
    assert "RankingRM.rm_id == current_user.rm_id" in fuente


def test_percentil_no_revienta_con_un_solo_participante():
    """`(total - pos) / (total - 1)` dividiría por cero con total=1."""
    fuente = inspect.getsource(router_rk.get_mi_posicion)
    assert "if total > 1 else None" in fuente
