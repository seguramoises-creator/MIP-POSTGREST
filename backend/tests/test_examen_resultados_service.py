"""Tests de KPIs/resultados (app.services.examen_resultados_service)."""
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import examen_resultados_service as res


def test_porcentaje():
    assert res._porcentaje(8, 10) == 80.0
    assert res._porcentaje(0, 0) == 0.0
    assert res._porcentaje(1, 3) == 33.33


def test_ultimo_intento_por_asignacion_toma_el_mas_reciente():
    # Intentos ordenados ascendentes por fecha_fin; el último por asignación gana.
    db = MagicMock()
    i1 = SimpleNamespace(asignacion_id=1, score=50)
    i2 = SimpleNamespace(asignacion_id=1, score=80)   # más reciente (viene después)
    i3 = SimpleNamespace(asignacion_id=2, score=70)
    db.query.return_value.join.return_value.filter.return_value.order_by.return_value.all.return_value = [i1, i2, i3]
    ultimos = res._ultimo_intento_por_asignacion(db, examen_id=9)
    assert ultimos[1].score == 80   # se quedó con el segundo (más reciente)
    assert ultimos[2].score == 70
