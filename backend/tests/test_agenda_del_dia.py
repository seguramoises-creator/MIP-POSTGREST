"""Qué entra «del día» en la agenda de la app: semana del ciclo + día, no solo el día.

Regresión (sep-2026): un viernes la app ponía «del día» a los planeados para CUALQUIER
viernes del ciclo (cinco médicos) mientras Hoy y el monitor web decían uno.
"""
import datetime as dt
from types import SimpleNamespace

from app.services.visita_registro_service import _planeados_para_hoy

# C09-2026 empieza el martes 1-sep: la semana 1 es la del lunes 31-ago.
CICLO = SimpleNamespace(fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2026, 9, 28))
VIERNES_SEMANA_2 = dt.date(2026, 9, 11)


def _p(mid, tipo, semana, dia):
    return SimpleNamespace(medico_id=mid, tipo_visita=tipo, semana=semana, dia_semana=dia)


def test_solo_entra_lo_planeado_para_esta_semana_y_este_dia():
    plan = [_p(1, "V", 2, "Viernes"),   # hoy
            _p(2, "V", 1, "Viernes"),   # viernes de la semana 1: NO es hoy
            _p(3, "V", 4, "Viernes"),   # viernes de la semana 4: NO es hoy
            _p(4, "V", 2, "Jueves")]    # semana 2 pero otro día
    assert _planeados_para_hoy(plan, CICLO, VIERNES_SEMANA_2) == {1: "V"}


def test_trae_el_tipo_que_toca_hoy():
    plan = [_p(7, "V", 1, "Lunes"), _p(7, "R", 2, "Viernes")]
    assert _planeados_para_hoy(plan, CICLO, VIERNES_SEMANA_2) == {7: "R"}


def test_sin_dia_o_sin_ciclo_no_se_inventa_hoy():
    assert _planeados_para_hoy([_p(1, "V", 2, None)], CICLO, VIERNES_SEMANA_2) == {}
    assert _planeados_para_hoy([_p(1, "V", 2, "Viernes")], None, VIERNES_SEMANA_2) == {}
