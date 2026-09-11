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


def test_semana_en_curso_y_fuera_de_fechas(monkeypatch):
    ciclo = SimpleNamespace(pais_codigo="DO", fecha_inicio=dt.date(2026, 9, 1), fecha_fin=dt.date(2026, 9, 28))
    db = MagicMock()
    db.get.return_value = ciclo
    monkeypatch.setattr(svc, "hoy_local", lambda db, p: dt.date(2026, 9, 11))
    assert svc._semana_en_curso(db, 53) == 2
    # Fuera de las fechas del ciclo no hay semana «en curso»: None, no una inventada.
    monkeypatch.setattr(svc, "hoy_local", lambda db, p: dt.date(2026, 10, 2))
    assert svc._semana_en_curso(db, 53) is None
