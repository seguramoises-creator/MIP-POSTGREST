"""RBAC Fase 1 — T4: filtros de alcance own/team/all + guard anti-IDOR."""
import pytest
from types import SimpleNamespace
from fastapi import HTTPException

from app.models.usuario import Rol
from app.core.authz.constantes import Alcance
from app.core.authz import scope


class _FakeQuery:
    def __init__(self, ids):
        self._ids = ids

    def filter(self, *a, **k):
        return self

    def all(self):
        return [(i,) for i in self._ids]


class _FakeDB:
    def __init__(self, ids):
        self._ids = ids

    def query(self, *a, **k):
        return _FakeQuery(self._ids)


def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id)


def test_all_no_filtra():
    assert scope.rm_ids_visibles(_FakeDB([1, 2, 3]), U(Rol.PRESIDENCIA), Alcance.ALL) is None


def test_own_solo_su_rm():
    assert scope.rm_ids_visibles(_FakeDB([]), U(Rol.REPRESENTANTE_MEDICO, rm_id=7), Alcance.OWN) == {7}


def test_own_sin_rm_id_vacio():
    assert scope.rm_ids_visibles(_FakeDB([]), U(Rol.REPRESENTANTE_MEDICO), Alcance.OWN) == set()


def test_team_usa_equipo_del_gd():
    got = scope.rm_ids_visibles(_FakeDB([4, 5]), U(Rol.GERENTE_DISTRITO, gerente_id=9), Alcance.TEAM)
    assert got == {4, 5}


def test_none_vacio():
    assert scope.rm_ids_visibles(_FakeDB([]), U(Rol.CONSULTA), Alcance.NONE) == set()


def test_assert_ve_rm_all_permite_todo():
    scope.assert_ve_rm(U(Rol.PRESIDENCIA), 999, Alcance.ALL)  # no lanza


def test_assert_ve_rm_own_propio_ok():
    scope.assert_ve_rm(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), 7, Alcance.OWN)  # no lanza


def test_assert_ve_rm_own_ajeno_403():
    with pytest.raises(HTTPException) as e:
        scope.assert_ve_rm(U(Rol.REPRESENTANTE_MEDICO, rm_id=7), 8, Alcance.OWN)
    assert e.value.status_code == 403


def test_assert_ve_rm_team_usa_conjunto_precomputado():
    scope.assert_ve_rm(U(Rol.GERENTE_DISTRITO), 5, Alcance.TEAM, ids_equipo={4, 5})  # no lanza
    with pytest.raises(HTTPException) as e:
        scope.assert_ve_rm(U(Rol.GERENTE_DISTRITO), 9, Alcance.TEAM, ids_equipo={4, 5})
    assert e.value.status_code == 403


def test_assert_ve_rm_linea_usa_conjunto_precomputado():
    """Simétrico al de TEAM: LINEA comparte la misma rama de `assert_ve_rm`
    (el caller precomputa `ids_equipo` con `rm_ids_visibles(db, user, LINEA)`)."""
    scope.assert_ve_rm(U(Rol.GERENTE_MARCA), 5, Alcance.LINEA, ids_equipo={4, 5})  # no lanza
    with pytest.raises(HTTPException) as e:
        scope.assert_ve_rm(U(Rol.GERENTE_MARCA), 9, Alcance.LINEA, ids_equipo={4, 5})
    assert e.value.status_code == 403
