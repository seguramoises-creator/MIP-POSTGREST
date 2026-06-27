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


# ---------------------------------------------------------------------------
# Tests de registrar_respuesta — idempotencia (Task 8)
# ---------------------------------------------------------------------------

def test_registrar_respuesta_es_idempotente():
    """registrar_respuesta borra cualquier fila previa del mismo (intento, pregunta)
    antes de insertar la nueva — la segunda llamada no acumula duplicados."""
    db = MagicMock()

    # FakeQuery para el DELETE: filter(...).delete() debe ser llamado
    delete_query = MagicMock()
    delete_query.filter.return_value = delete_query
    delete_query.delete.return_value = 1  # simula 1 fila borrada

    # Stub de refresh: no-op
    db.refresh.return_value = None

    db.query.return_value = delete_query

    svc.registrar_respuesta(
        db,
        intento_id=1,
        pregunta_id=10,
        opcion_id=42,
        indice_presentado=0,
        indice_original=2,
        mapa={"0": {"opcion_id": 42, "indice_original": 2}},
    )

    # El DELETE fue invocado con los filtros correctos antes del INSERT
    delete_query.delete.assert_called_once()
    # db.add fue llamado una sola vez (la nueva fila)
    db.add.assert_called_once()
    db.commit.assert_called()


# ---------------------------------------------------------------------------
# Tests de calcular_score (Task 6 — Step 1)
# ---------------------------------------------------------------------------

def test_calcular_score():
    assert svc.calcular_score(8, 10) == 80.0
    assert svc.calcular_score(0, 0) == 0.0
    assert svc.calcular_score(1, 3) == 33.33


# ---------------------------------------------------------------------------
# Test anti-doble-entrega (Task 6 — Step 3)
# ---------------------------------------------------------------------------

def test_entregar_dos_veces_falla(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, fecha_fin=datetime.now(timezone.utc))
    db.query.return_value.filter.return_value.first.return_value = intento
    with pytest.raises(ValueError):
        svc.entregar_intento(db, 1)


# ---------------------------------------------------------------------------
# Tests de entregar_intento — happy path (Task 6 — Step 4)
# ---------------------------------------------------------------------------

def _build_entregar_db(*, aprobado_esperado=True, intentos_max=None, intentos_usados=0,
                        nota_minima=70, score_esperado=80.0):
    """Construye un db mock con el orden de queries que entregar_intento realiza."""
    from tests.conftest import FakeQuery

    db = MagicMock()

    # Intento sin fecha_fin (no entregado aún)
    intento = SimpleNamespace(
        id=10, fecha_fin=None, asignacion_id=5,
        fecha_inicio=datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc),
        score=None, aprobado=None, tiempo_usado_seg=None,
    )

    # Asignación
    asignacion = SimpleNamespace(
        id=5, examen_id=7,
        intentos_max=intentos_max, intentos_usados=intentos_usados,
        estado="pendiente",
    )

    # Examen con nota_minima configurable
    examen = SimpleNamespace(id=7, nota_minima=nota_minima)

    # Respuestas: 2 correctas de 2 (score=100) si aprobado_esperado=True,
    # o 0 de 2 (score=0) si False — pero simplificamos: siempre 2 respuestas.
    opcion_correcta = SimpleNamespace(id=201, es_correcta=True)
    opcion_incorrecta = SimpleNamespace(id=202, es_correcta=False)

    respuestas = [
        SimpleNamespace(id=1, opcion_elegida_id=201, es_correcta=None),
        SimpleNamespace(id=2, opcion_elegida_id=201, es_correcta=None),
    ]

    # db.query() se llama en orden:
    # 1. query(IntentoExamen) → intento
    # 2. query(AsignacionExamen) → asignacion
    # 3. query(Examen) → examen
    # 4. query(IntentoRespuesta) → respuestas list
    # 5. query(Pregunta).filter(...).count() → 2
    # 6+7. query(PreguntaOpcion) × 2 → opcion_correcta
    db.query.side_effect = [
        FakeQuery(first_result=intento),
        FakeQuery(first_result=asignacion),
        FakeQuery(first_result=examen),
        FakeQuery(all_result=respuestas),
        FakeQuery(all_result=[SimpleNamespace(), SimpleNamespace()]),  # count() = 2
        FakeQuery(first_result=opcion_correcta),
        FakeQuery(first_result=opcion_correcta),
    ]

    return db, intento, asignacion


def test_entregar_intento_happy_path_aprobado():
    """entregar_intento: 2/2 correctas → score=100 → aprobado=True → asignacion=completado."""
    db, intento, asignacion = _build_entregar_db(nota_minima=70)

    result = svc.entregar_intento(db, 10)

    assert intento.score == 100.0
    assert intento.aprobado is True
    assert intento.fecha_fin is not None
    assert intento.tiempo_usado_seg is not None and intento.tiempo_usado_seg >= 0
    assert asignacion.intentos_usados == 1
    assert asignacion.estado == "completado"
    db.commit.assert_called()


def test_entregar_intento_cierra_asignacion_si_agota_intentos():
    """RN-06: si no aprueba pero agota intentos_max → asignacion pasa a 'completado'."""
    from tests.conftest import FakeQuery

    db = MagicMock()

    intento = SimpleNamespace(
        id=10, fecha_fin=None, asignacion_id=5,
        fecha_inicio=datetime(2026, 6, 27, 10, 0, 0, tzinfo=timezone.utc),
        score=None, aprobado=None, tiempo_usado_seg=None,
    )
    asignacion = SimpleNamespace(
        id=5, examen_id=7, intentos_max=3, intentos_usados=2,  # este es el 3.° intento
        estado="pendiente",
    )
    examen = SimpleNamespace(id=7, nota_minima=90)  # nota alta → no aprueba con score=0
    opcion_incorrecta = SimpleNamespace(id=202, es_correcta=False)
    respuestas = [
        SimpleNamespace(id=1, opcion_elegida_id=202, es_correcta=None),
    ]

    db.query.side_effect = [
        FakeQuery(first_result=intento),
        FakeQuery(first_result=asignacion),
        FakeQuery(first_result=examen),
        FakeQuery(all_result=respuestas),
        FakeQuery(all_result=[SimpleNamespace()]),  # count=1
        FakeQuery(first_result=opcion_incorrecta),
    ]

    result = svc.entregar_intento(db, 10)

    assert intento.aprobado is False
    assert asignacion.intentos_usados == 3   # 2 + 1
    assert asignacion.estado == "completado"  # agotó intentos_max
