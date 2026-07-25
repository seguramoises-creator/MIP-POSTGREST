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


# ---------------------------------------------------------------------------
# Regional — jul-2026: ya NO recalcula ningún score, reutiliza el acumulado
# (decisión del cliente: "el Ranking Regional no cambia los resultados, es
# solo recalcular las posiciones... esto no altera su resultado acumulado").
# ---------------------------------------------------------------------------

def test_regional_reutiliza_ciclos_acumulados_no_recalcula():
    """Regional debe usar EXACTAMENTE la misma función de acumulado que
    GET /ranking (`_ciclos_acumulados`/`_ultimo_ciclo`), nunca un motor de
    score aparte."""
    fuente = inspect.getsource(router_rk._acumulado_por_pais)
    assert "_ultimo_ciclo(" in fuente
    assert "_ciclos_acumulados(" in fuente
    assert "calcular_iup" not in fuente
    assert "iup_service" not in fuente


def test_regional_solo_incluye_elegibles():
    fuente = inspect.getsource(router_rk.get_ranking_regional)
    assert "if elegible" in fuente


def test_regional_no_tiene_endpoint_generar_ni_anual():
    """El botón/endpoint de generar y la pestaña Anual se retiraron por
    completo (redundantes con el acumulado, que ya funciona bien) — no deben
    reaparecer como código muerto."""
    assert not hasattr(router_rk, "generar_ranking")
    assert not hasattr(router_rk, "get_ranking_anual")


def test_ranking_actual_no_resuelve_ultimo_ciclo_sin_pais():
    """Bug latente (jul-2026, hoy inalcanzable desde la UI): sin pais_codigo NI
    ciclo_id, `_ultimo_ciclo` elegía el ciclo mas reciente de CUALQUIER país
    (cada ciclo_id pertenece a uno solo) — el resultado terminaba siendo el de
    un país arbitrario disfrazado de "todos los países". Ahora debe quedar sin
    resolver (cae en el "sin datos" ya existente) en vez de adivinar mal."""
    fuente = inspect.getsource(router_rk.get_ranking)
    assert "_ultimo_ciclo(db, pais_codigo, tipo) if pais_codigo else None" in fuente
