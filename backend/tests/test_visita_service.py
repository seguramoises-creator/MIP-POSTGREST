"""Tests Módulo de Visita Médica — Fase 1 (antiduplicados + validación de nombre)."""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.services import visita_service
from app.schemas.visita import MedicoVisitaCrear


def _db_con(medicos):
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = medicos
    return db


def test_duplicado_dispara_con_2_palabras():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL ANTONIO", direccion="x")])
    dups = visita_service.detectar_duplicados(db, "PEREZ VALDEZ JUAN")
    assert len(dups) == 1 and dups[0]["palabras_coinciden"] == 2


def test_duplicado_no_dispara_con_1_palabra():
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    # Solo "VALDEZ" en común (1 palabra) → no se considera duplicado.
    assert visita_service.detectar_duplicados(db, "GOMEZ VALDEZ CARLOS") == []
    # Ninguna palabra en común → tampoco.
    assert visita_service.detectar_duplicados(db, "GOMEZ SUERO CARLOS") == []


def test_crear_sin_confirmar_levanta_duplicado(monkeypatch):
    db = _db_con([SimpleNamespace(id=1, nombre_completo="PEREZ VALDEZ MANUEL", direccion=None)])
    datos = MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ VALDEZ JUAN", categoria="A")
    with pytest.raises(visita_service.DuplicadoMedicoError):
        visita_service.crear_medico(db, datos, usuario_id=1)


def test_nombre_se_normaliza_a_mayusculas():
    m = MedicoVisitaCrear(vm_id=1, nombre_completo="manuel  perez garcia", categoria="a")
    assert m.nombre_completo == "MANUEL PEREZ GARCIA" and m.categoria == "A"


def test_nombre_1_palabra_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="PEREZ", categoria="A")


def test_nombre_con_punto_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="DR. PEREZ GARCIA", categoria="A")


def test_categoria_invalida_falla():
    with pytest.raises(ValueError):
        MedicoVisitaCrear(vm_id=1, nombre_completo="MANUEL PEREZ", categoria="D")
