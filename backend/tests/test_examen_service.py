import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.usuario import Rol
from app.schemas.examenes import ExamenCrear, PreguntaCrear, PreguntaOpcionCrear
from app.services import examen_service


def test_rol_capacitacion_existe():
    assert Rol.CAPACITACION.value == "CAPACITACION"


def test_crear_examen_arranca_en_borrador_manual():
    db = MagicMock()
    datos = ExamenCrear(nombre="Producto X", producto="X")
    examen = examen_service.crear_examen(db, datos, creado_por_usuario_id=1)
    assert examen.estado == "borrador"
    assert examen.fuente == "manual"
    assert examen.nombre == "Producto X"
    assert db.add.called and db.commit.called


def test_publicar_sin_preguntas_falla(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador", preguntas=[], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.publicar_examen(db, 1)


def test_publicar_con_preguntas_activa(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador",
                             preguntas=[SimpleNamespace(id=9, activo=True, peso=None)], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    resultado = examen_service.publicar_examen(db, 1)
    assert resultado.estado == "activo"


def _examen_pesos(pesos):
    return SimpleNamespace(
        id=1, estado="borrador", fecha_publicacion=None,
        preguntas=[SimpleNamespace(id=i, activo=True, peso=p) for i, p in enumerate(pesos)],
    )


def test_publicar_pesos_suman_100_ok(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: _examen_pesos([60, 40]))
    assert examen_service.publicar_examen(db, 1).estado == "activo"


def test_publicar_pesos_no_suman_100_falla(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: _examen_pesos([50, 40]))
    with pytest.raises(ValueError, match="suma de los pesos"):
        examen_service.publicar_examen(db, 1)


def test_publicar_pesos_parciales_falla(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: _examen_pesos([100, None]))
    with pytest.raises(ValueError, match="todas las preguntas deben tener peso"):
        examen_service.publicar_examen(db, 1)


def test_publicar_examen_no_borrador_falla(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo",
                             preguntas=[SimpleNamespace(id=9)], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.publicar_examen(db, 1)


# ---------------------------------------------------------------------------
# Task 3: CRUD de preguntas/opciones
# ---------------------------------------------------------------------------


def _pcrear(n_correctas=1):
    ops = [PreguntaOpcionCrear(texto_opcion=f"o{i}", es_correcta=(i < n_correctas)) for i in range(5)]
    return PreguntaCrear(texto="¿?", opciones=ops)


def test_agregar_pregunta_requiere_examen_borrador(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo", preguntas=[])
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear())


def test_agregar_pregunta_exige_una_correcta(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador", preguntas=[])
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear(n_correctas=0))
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear(n_correctas=2))


def test_agregar_pregunta_multi_requiere_5_opciones(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador", preguntas=[])
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    ops = [PreguntaOpcionCrear(texto_opcion=f"o{i}", es_correcta=(i == 0)) for i in range(4)]
    with pytest.raises(ValueError, match="5 opciones"):
        examen_service.agregar_pregunta(db, 1, PreguntaCrear(tipo="multi", texto="¿?", opciones=ops))


def test_reordenar_preguntas_valida_ids_exactos():
    """reordenar_preguntas debe alzar ValueError si orden_ids no coincide exactamente."""
    db = MagicMock()
    # Stub: el examen 1 tiene las preguntas con id 1 y 2
    db.query.return_value.filter.return_value.all.return_value = [(1,), (2,)]
    with pytest.raises(ValueError, match="orden_ids debe contener exactamente"):
        examen_service.reordenar_preguntas(db, examen_id=1, orden_ids=[1, 99])


# ---------------------------------------------------------------------------
# Task 4: Asignar examen a evaluados
# ---------------------------------------------------------------------------

from app.schemas.examenes import EvaluadoRef


def test_asignar_requiere_examen_activo(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.asignar_examen(db, 1, [EvaluadoRef(tipo="RM", id=5)], None, None, False)


def test_asignar_crea_una_por_evaluado(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    res = examen_service.asignar_examen(
        db, 1, [EvaluadoRef(tipo="RM", id=5), EvaluadoRef(tipo="GERENTE", id=9)], "2026-12-31", 1, False)
    assert len(res) == 2
    assert res[0].evaluado_tipo == "RM" and res[0].evaluado_rm_id == 5
    assert res[1].evaluado_tipo == "GERENTE" and res[1].evaluado_gerente_id == 9


def test_asignar_requiere_fecha_limite(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError, match="fecha límite"):
        examen_service.asignar_examen(db, 1, [EvaluadoRef(tipo="RM", id=5)], None, None, False)


def test_asignar_intentos_por_defecto_1(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    res = examen_service.asignar_examen(
        db, 1, [EvaluadoRef(tipo="RM", id=5)], "2026-12-31", None, False)
    assert res[0].intentos_max == 1


# ---------------------------------------------------------------------------
# Eliminar examen — regla: solo si NO ha sido tomado (sin intentos)
# ---------------------------------------------------------------------------


def _db_para_eliminar(examen, n_intentos):
    db = MagicMock()
    q = db.query.return_value
    q.filter.return_value.first.return_value = examen          # obtener el examen
    q.join.return_value.filter.return_value.count.return_value = n_intentos  # contar intentos
    q.filter.return_value.delete.return_value = None           # bulk delete asignaciones/fuentes
    return db


def test_eliminar_examen_no_encontrado():
    db = _db_para_eliminar(None, 0)
    with pytest.raises(ValueError):
        examen_service.eliminar_examen(db, 99)


def test_eliminar_examen_con_intentos_se_preserva():
    examen = SimpleNamespace(id=1)
    db = _db_para_eliminar(examen, 2)
    with pytest.raises(examen_service.ExamenConIntentosError):
        examen_service.eliminar_examen(db, 1)
    assert not db.delete.called  # no se borró nada


def test_eliminar_examen_sin_intentos_borra():
    examen = SimpleNamespace(id=1)
    db = _db_para_eliminar(examen, 0)
    examen_service.eliminar_examen(db, 1)
    db.delete.assert_called_once_with(examen)
    assert db.commit.called
