"""
Tests de aislamiento por país — GET /dashboard/ejecutivo (jul-2026).

Bug latente (hoy inalcanzable desde la UI, el selector global de país nunca
manda vacío): sin `pais_codigo`, `dashboard_ejecutivo` resolvía "el último
ciclo" con `MAX(RankingRM.ciclo_id)` sin filtro de país — como cada ciclo_id
pertenece a un solo país, el resultado terminaba siendo el de un país
arbitrario, disfrazado de "todos los países". Mismo defecto en la resolución
del "ciclo anterior" (para el delta de KPIs).

Se verifica por inspección de código fuente (igual que test_ranking_scope.py)
en vez de mockear toda la cadena SQLAlchemy de una función tan grande.
"""
import inspect

from app.api.v1.routers import dashboard as router_dash


def test_ciclo_efectivo_no_se_resuelve_sin_pais():
    """Sin pais_codigo, no debe intentar `MAX(ciclo_id)` sin filtro de país —
    debe quedar sin resolver (None) en vez de adivinar un país arbitrario."""
    fuente = inspect.getsource(router_dash.dashboard_ejecutivo)
    assert "if not ciclo_efectivo and pais_codigo:" in fuente


def test_ciclo_anterior_no_se_resuelve_sin_pais():
    """Mismo defecto en el calculo del 'ciclo anterior' para el delta de KPIs."""
    fuente = inspect.getsource(router_dash.dashboard_ejecutivo)
    assert "if ciclo_efectivo and pais_codigo:" in fuente
