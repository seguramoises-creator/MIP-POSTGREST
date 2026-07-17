"""Tests de la elección del ciclo de trabajo (`visita_cobertura_service._elegir_ciclo`).

Regresión del patrón que ya mordió tres veces: usar "el ciclo abierto de número más alto"
donde va "el ciclo que corresponde a HOY". El ciclo de trabajo lo define el calendario,
no el número. Con un solo ciclo abierto el bug es invisible; aparece al abrir un segundo.
"""
from datetime import date
from types import SimpleNamespace

from app.services.visita_cobertura_service import _elegir_ciclo


def _ciclo(id_, numero, ini, fin, anio=2026):
    return SimpleNamespace(id=id_, numero=numero, anio=anio, fecha_inicio=ini, fecha_fin=fin,
                           nombre=f"C{numero:02d}-{anio}")


C07 = _ciclo(41, 7, date(2026, 7, 1), date(2026, 7, 28))
C08 = _ciclo(47, 8, date(2026, 8, 1), date(2026, 8, 28))
C12 = _ciclo(71, 12, date(2026, 12, 1), date(2026, 12, 28))


def test_elige_el_ciclo_que_contiene_hoy():
    assert _elegir_ciclo([C07, C08, C12], date(2026, 7, 16)).id == C07.id


def test_dos_ciclos_abiertos_no_gana_el_de_numero_mas_alto():
    """EL BUG: con C07 y C12 abiertos en julio se elegía diciembre (12 > 7), y el guard
    de ventana rechazaba todas las visitas del país."""
    assert _elegir_ciclo([C07, C12], date(2026, 7, 16)).id == C07.id


def test_el_orden_de_la_lista_no_altera_el_resultado():
    assert _elegir_ciclo([C12, C08, C07], date(2026, 7, 16)).id == C07.id


def test_un_solo_ciclo_abierto_se_elige_igual():
    """El caso de hoy en producción: seguía funcionando, pero por accidente."""
    assert _elegir_ciclo([C07], date(2026, 7, 16)).id == C07.id


def test_sin_ciclo_que_cubra_hoy_cae_al_mas_reciente():
    """Los ciclos van del 1 al 28: el 30 de julio no cae en ninguno."""
    assert _elegir_ciclo([C07, C08], date(2026, 7, 30)).id == C08.id


def test_sin_ciclos_devuelve_none():
    assert _elegir_ciclo([], date(2026, 7, 16)) is None


def test_los_limites_de_la_ventana_son_inclusivos():
    assert _elegir_ciclo([C07, C12], date(2026, 7, 1)).id == C07.id   # primer día
    assert _elegir_ciclo([C07, C12], date(2026, 7, 28)).id == C07.id  # último día


def test_gana_el_anio_mas_reciente_al_caer_al_fallback():
    c07_2025 = _ciclo(5, 7, date(2025, 7, 1), date(2025, 7, 28), anio=2025)
    assert _elegir_ciclo([c07_2025, C07], date(2026, 7, 30)).id == C07.id


def test_ciclo_con_fechas_nulas_no_revienta():
    """Un ciclo mal configurado no puede tumbar el registro de visitas."""
    roto = _ciclo(99, 9, None, None)
    assert _elegir_ciclo([roto, C07], date(2026, 7, 16)).id == C07.id
