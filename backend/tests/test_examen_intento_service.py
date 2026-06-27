"""Tests para examen_intento_service: Fisher-Yates + preparar_intento."""
import json
import random
from datetime import datetime, timedelta, timezone

import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import examen_intento_service as svc


# ---------------------------------------------------------------------------
# Tests de barajar
# ---------------------------------------------------------------------------

def test_barajar_es_permutacion_determinista():
    rng = random.Random(42)
    original = [1, 2, 3, 4, 5]
    barajado = svc.barajar(list(original), rng)
    assert sorted(barajado) == original   # es permutación
    rng2 = random.Random(42)
    assert svc.barajar(list(original), rng2) == barajado  # determinista con misma semilla


def test_barajar_sin_elementos():
    assert svc.barajar([], random.Random(1)) == []


# ---------------------------------------------------------------------------
# Helpers para preparar_intento
# ---------------------------------------------------------------------------

def _asig(estado="pendiente", intentos_max=None, intentos_usados=0, fecha_limite=None):
    return SimpleNamespace(
        id=1, estado=estado, intentos_max=intentos_max,
        intentos_usados=intentos_usados, fecha_limite=fecha_limite,
        examen_id=7, evaluado_tipo="RM", evaluado_rm_id=5, evaluado_gerente_id=None,
    )


def _examen_mock(estado="activo", rand_preguntas=False, rand_opciones=False):
    ex = SimpleNamespace(
        id=7, estado=estado, rand_preguntas=rand_preguntas, rand_opciones=rand_opciones,
    )
    return ex


def _pregunta_mock(pid, opciones_count=3):
    opciones = [
        SimpleNamespace(
            id=100 + pid * 10 + i,
            texto_opcion=f"Opcion {i}",
            indice_original=i,
            es_correcta=(i == 0),
        )
        for i in range(opciones_count)
    ]
    return SimpleNamespace(
        id=pid, tipo="multi", escenario=None, texto=f"Pregunta {pid}",
        orden=pid, activo=True, opciones=opciones,
    )


# ---------------------------------------------------------------------------
# Tests de preparar_intento — validaciones (RN-06, RN-01)
# ---------------------------------------------------------------------------

def test_preparar_intento_bloquea_si_agoto_intentos(monkeypatch):
    db = MagicMock()
    asig = _asig(intentos_max=2, intentos_usados=2)
    with pytest.raises(ValueError, match="intentos"):
        svc.preparar_intento(db, asig, "RM", 5, {})


def test_preparar_intento_bloquea_si_estado_no_pendiente():
    db = MagicMock()
    asig = _asig(estado="completado")
    with pytest.raises(ValueError, match="disponible"):
        svc.preparar_intento(db, asig, "RM", 5, {})


def test_preparar_intento_bloquea_si_examen_no_activo():
    db = MagicMock()
    asig = _asig()
    examen = _examen_mock(estado="borrador")
    db.query.return_value.filter.return_value.first.return_value = examen
    with pytest.raises(ValueError, match="disponible"):
        svc.preparar_intento(db, asig, "RM", 5, {})


def test_preparar_intento_crea_intento_y_preguntas_presentadas():
    """Happy path: examen activo, sin barajado, crea IntentoExamen y _preguntas_presentadas."""
    db = MagicMock()
    asig = _asig()
    examen = _examen_mock(estado="activo", rand_preguntas=False, rand_opciones=False)
    preguntas = [_pregunta_mock(1), _pregunta_mock(2)]

    # Use FakeQuery pattern to control both db.query() calls in order.
    # Call 1: db.query(Examen).filter(...).first() → examen
    # Call 2: db.query(Pregunta).filter(...).filter(...).order_by(...).all() → preguntas
    from tests.conftest import FakeQuery

    db.query.side_effect = [
        FakeQuery(first_result=examen),
        FakeQuery(all_result=preguntas),
    ]

    rng = random.Random(0)
    result = svc.preparar_intento(db, asig, "RM", 5, {}, rng=rng)

    assert hasattr(result, "_preguntas_presentadas")
    assert len(result._preguntas_presentadas) == 2
    # Cada entrada tiene los campos esperados
    for entrada in result._preguntas_presentadas:
        assert "pregunta_id" in entrada
        assert "opciones" in entrada
        for op in entrada["opciones"]:
            assert "_opcion_id" in op
            assert "_indice_original" in op
            assert "indice_presentado" in op


def test_preparar_intento_vencido_falla():
    """RN-06: fecha_limite en el pasado debe levantar ValueError antes de cualquier query."""
    db = MagicMock()
    fecha_pasada = (datetime.now(timezone.utc) - timedelta(days=1)).date()
    asig = _asig(estado="pendiente", fecha_limite=fecha_pasada)
    with pytest.raises(ValueError, match="vencida"):
        svc.preparar_intento(db, asig, "RM", 5, {})
    # El guard dispara antes de tocar la BD
    db.query.assert_not_called()


def test_preparar_intento_baraja_preguntas_y_opciones():
    """rand_preguntas=True + rand_opciones=True con semilla=7 reordena los IDs de preguntas
    y ninguna opción expone es_correcta al evaluado."""
    # Seed=7 transforma [p1,p2,p3] → [p3,p1,p2] con el Fisher-Yates del servicio.
    SEED = 7
    db = MagicMock()
    asig = _asig()
    examen = _examen_mock(estado="activo", rand_preguntas=True, rand_opciones=True)
    preguntas = [_pregunta_mock(1), _pregunta_mock(2), _pregunta_mock(3)]

    from tests.conftest import FakeQuery

    db.query.side_effect = [
        FakeQuery(first_result=examen),
        FakeQuery(all_result=preguntas),
    ]

    rng = random.Random(SEED)
    result = svc.preparar_intento(db, asig, "RM", 5, {}, rng=rng)

    orden_json = json.loads(result.orden_preguntas_json)
    ids_originales = [p.id for p in preguntas]  # [1, 2, 3]

    # Es una permutación de los IDs originales
    assert sorted(orden_json) == sorted(ids_originales)
    # El barajado produjo un orden distinto al original (semilla=7 garantiza esto)
    assert orden_json != ids_originales

    # Las preguntas presentadas coinciden en cantidad y sin es_correcta expuesto
    assert len(result._preguntas_presentadas) == len(preguntas)
    for entrada in result._preguntas_presentadas:
        for op in entrada["opciones"]:
            assert "es_correcta" not in op
