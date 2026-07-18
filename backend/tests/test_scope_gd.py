"""Tests del alcance del GERENTE_DISTRITO: agregado de empresa, nombres solo de su equipo.

Regla (jul-2026): el GD ve el AGREGADO de toda la empresa pero solo identifica por nombre a
los RMs de su equipo. En un listado, las filas ajenas se ANONIMIZAN (no se filtran) para que
los agregados sigan siendo de empresa.
"""
from types import SimpleNamespace
from unittest.mock import patch

from app.core import scope_gd
from app.models.usuario import Rol


def _items():
    return [
        {"rm_id": 1, "rm_nombre": "MI RM UNO", "rm_codigo": "VM01", "gerente_nombre": "PAULA", "puntaje": 90},
        {"rm_id": 2, "rm_nombre": "AJENO DOS", "rm_codigo": "VM02", "gerente_nombre": "DARWIN", "puntaje": 80},
        {"rm_id": 3, "rm_nombre": "MI RM TRES", "rm_codigo": "VM03", "gerente_nombre": "PAULA", "puntaje": 70},
    ]


def _gd(gerente_id=4):
    return SimpleNamespace(rol=Rol.GERENTE_DISTRITO, gerente_id=gerente_id)


def test_el_gd_solo_ve_el_nombre_de_su_equipo():
    with patch.object(scope_gd, "rm_ids_de_gd", return_value={1, 3}):  # su equipo: rm 1 y 3
        out = scope_gd.anonimizar_para_gd(_items(), _gd(), db=None)
    porid = {i["rm_id"]: i for i in out}
    assert porid[1]["rm_nombre"] == "MI RM UNO"          # suyo → nombre real
    assert porid[3]["rm_nombre"] == "MI RM TRES"          # suyo → nombre real
    assert porid[2]["rm_nombre"] == scope_gd.ANONIMO     # ajeno → anónimo
    assert porid[2]["rm_codigo"] is None
    assert porid[2]["gerente_nombre"] == "—"


def test_los_puntajes_ajenos_se_conservan_para_el_agregado():
    """El agregado (promedio/conteo) DEBE seguir siendo de empresa: no se filtra, se anonimiza."""
    with patch.object(scope_gd, "rm_ids_de_gd", return_value={1, 3}):
        out = scope_gd.anonimizar_para_gd(_items(), _gd(), db=None)
    assert len(out) == 3                                  # las 3 filas siguen ahí
    assert sum(i["puntaje"] for i in out) == 240          # 90+80+70, el ajeno cuenta


def test_el_rm_id_se_conserva_como_key_opaca():
    with patch.object(scope_gd, "rm_ids_de_gd", return_value={1}):
        out = scope_gd.anonimizar_para_gd(_items(), _gd(), db=None)
    assert {i["rm_id"] for i in out} == {1, 2, 3}          # ids intactos (keys del frontend)


def test_admin_ve_todos_los_nombres():
    admin = SimpleNamespace(rol=Rol.ADMIN, gerente_id=None)
    out = scope_gd.anonimizar_para_gd(_items(), admin, db=None)
    assert all(i["rm_nombre"] != scope_gd.ANONIMO for i in out)


def test_gerente_de_productividad_ve_todos_los_nombres():
    gp = SimpleNamespace(rol=Rol.GERENTE_PRODUCTIVIDAD, gerente_id=None)
    out = scope_gd.anonimizar_para_gd(_items(), gp, db=None)
    assert all(i["rm_nombre"] != scope_gd.ANONIMO for i in out)


def test_gd_sin_gerente_id_no_identifica_a_nadie():
    """Fail-closed: un GD sin gerente_id no tiene equipo, así que todo queda anónimo."""
    out = scope_gd.anonimizar_para_gd(_items(), _gd(gerente_id=None), db=None)
    assert all(i["rm_nombre"] == scope_gd.ANONIMO for i in out)


def test_los_endpoints_aplican_el_helper():
    import inspect
    from app.api.v1.routers import productividad, ranking
    assert "anonimizar_para_gd" in inspect.getsource(productividad.get_productividad)
    assert "anonimizar_para_gd" in inspect.getsource(ranking.get_ranking)
