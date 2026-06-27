import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.models.usuario import Rol
from app.schemas.examenes import ExamenCrear
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
                             preguntas=[SimpleNamespace(id=9)], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    resultado = examen_service.publicar_examen(db, 1)
    assert resultado.estado == "activo"
    assert resultado.fecha_publicacion is not None
    assert db.commit.called


def test_publicar_examen_no_borrador_falla(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo",
                             preguntas=[SimpleNamespace(id=9)], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.publicar_examen(db, 1)
