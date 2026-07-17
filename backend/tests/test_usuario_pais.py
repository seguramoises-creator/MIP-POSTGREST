"""Tests de la regla: el país del usuario es OBLIGATORIO salvo para los roles multipaís.

Sin país, `ciclo.store.init()` nunca llama a `setPais()` y la tienda de País+Ciclo queda vacía
para ese usuario (sin badge, sin `cicloId`, sin lista de ciclos). Falla en silencio: nada da
error y el usuario solo ve menos de lo que debería. En producción estaban así 7 de 9
representantes (jul-2026).
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.routers.admin import ROLES_MULTIPAIS, _validar_pais_usuario


def _db(pais_existe=True):
    """Sesión falsa: la consulta de "¿existe el país?" devuelve una fila (o None)."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = ('DO',) if pais_existe else None
    return db


# ── Roles que SÍ necesitan país ───────────────────────────────────────────────

@pytest.mark.parametrize("rol", ["REPRESENTANTE_MEDICO", "GERENTE_DISTRITO",
                                 "GERENTE_MARCA", "CAPACITACION", "CONSULTA"])
def test_sin_pais_se_rechaza(rol):
    with pytest.raises(HTTPException) as e:
        _validar_pais_usuario(_db(), rol, None)
    assert e.value.status_code == 422
    assert "obligatorio" in e.value.detail


def test_el_error_explica_la_consecuencia_no_solo_el_campo():
    with pytest.raises(HTTPException) as e:
        _validar_pais_usuario(_db(), "REPRESENTANTE_MEDICO", "")
    assert "ciclo de trabajo" in e.value.detail   # el porqué, no solo "campo requerido"


def test_pais_en_blanco_cuenta_como_ausente():
    with pytest.raises(HTTPException):
        _validar_pais_usuario(_db(), "REPRESENTANTE_MEDICO", "   ")


def test_con_pais_valido_pasa():
    _validar_pais_usuario(_db(), "REPRESENTANTE_MEDICO", "DO")   # no levanta


def test_pais_inexistente_se_rechaza():
    with pytest.raises(HTTPException) as e:
        _validar_pais_usuario(_db(pais_existe=False), "REPRESENTANTE_MEDICO", "XX")
    assert e.value.status_code == 422
    assert "no existe" in e.value.detail


# ── Roles multipaís: el país propio es opcional A PROPÓSITO ───────────────────

@pytest.mark.parametrize("rol", sorted(ROLES_MULTIPAIS))
def test_los_multipais_no_necesitan_pais(rol):
    """Ven todos los países y pueden cambiarlos; exigirles uno propio sería un error."""
    _validar_pais_usuario(_db(), rol, None)   # no levanta


def test_acepta_el_rol_como_enum_y_como_texto():
    """El router recibe el rol como str (create) o como enum Rol (update, desde el modelo)."""
    _validar_pais_usuario(_db(), SimpleNamespace(value="ADMIN"), None)      # enum-like
    _validar_pais_usuario(_db(), "admin", None)                            # minúsculas
