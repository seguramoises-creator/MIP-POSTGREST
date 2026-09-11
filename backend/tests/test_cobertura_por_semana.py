"""Las listas de pendientes de Cobertura se leen por semana del ciclo (sep-2026)."""
import datetime as dt
from types import SimpleNamespace
from unittest.mock import MagicMock

import app.core.tiempo as tiempo
from app.services import visita_cobertura_service as svc


def test_agrupa_la_semana_y_el_dia_de_vista_y_revisita():
    filas = [(1, "V", 1, "Lunes"), (1, "R", 3, "Lunes"), (2, "V", 4, None)]
    assert svc._agrupar_planeacion(filas) == {
        1: {"V": (1, "Lunes"), "R": (3, "Lunes")},
        2: {"V": (4, None)},
    }


def test_vencido_por_dia_planeado_o_por_semana_entera():
    """Viernes 11-sep-2026, semana 2 de C09-2026 (empieza el martes 1-sep)."""
    ciclo = SimpleNamespace(fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2026, 9, 28))
    hoy = dt.date(2026, 9, 11)
    assert svc._vencido(ciclo, hoy, 1, "Lunes") is True      # 31-ago, ya pasó
    assert svc._vencido(ciclo, hoy, 2, "Jueves") is True     # ayer
    assert svc._vencido(ciclo, hoy, 2, "Viernes") is False   # hoy todavía se puede
    assert svc._vencido(ciclo, hoy, 3, "Lunes") is False     # aún no llega
    assert svc._vencido(ciclo, hoy, 1, None) is True         # sin día: la semana 1 entera pasó
    assert svc._vencido(ciclo, hoy, 2, None) is False        # la semana 2 no ha terminado
    assert svc._vencido(ciclo, hoy, None, None) is False     # sin planear: nada que vencer


def test_semana_en_curso_y_fuera_de_fechas(monkeypatch):
    ciclo = SimpleNamespace(pais_codigo="DO", fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2026, 9, 28))
    db = MagicMock()
    db.get.return_value = ciclo
    monkeypatch.setattr(svc, "hoy_local", lambda db, p: dt.date(2026, 9, 11))
    assert svc._semana_en_curso(db, 53) == 2
    # Fuera de las fechas del ciclo no hay semana «en curso»: None, no una inventada.
    monkeypatch.setattr(svc, "hoy_local", lambda db, p: dt.date(2026, 10, 2))
    assert svc._semana_en_curso(db, 53) is None
