import pytest

from app.services import maestro_farmacia_service as svc


def test_sin_direccion_no_graba():
    with pytest.raises(ValueError, match="dirección de la farmacia"):
        svc.validar_bloqueantes({"encargado": "Ana", "direccion": "  "})


def test_sin_direccion_ausente_no_graba():
    with pytest.raises(ValueError, match="dirección de la farmacia"):
        svc.validar_bloqueantes({"encargado": "Ana"})


def test_sin_encargado_no_graba():
    with pytest.raises(ValueError, match="nombre del encargado"):
        svc.validar_bloqueantes({"direccion": "Calle 1", "encargado": ""})


def test_sin_encargado_ausente_no_graba():
    with pytest.raises(ValueError, match="nombre del encargado"):
        svc.validar_bloqueantes({"direccion": "Calle 1"})


def test_con_ambos_ok():
    svc.validar_bloqueantes({"direccion": "Calle 1", "encargado": "Ana"})  # no lanza
