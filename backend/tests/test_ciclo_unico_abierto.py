"""Tests de la REGLA DE NEGOCIO: un solo ciclo abierto por país (decisión del cliente,
jul-2026: "solo debe haber un solo ciclo abierto, que el C07-2026").

La regla nunca estuvo escrita en el código: `Ciclo.cerrado` tiene `default=False`, así que
todo ciclo nacía ABIERTO por las tres vías (crear, importar, reabrir). Importar los 12 ciclos
del Excel dejaba 12 abiertos y el motor elegía el de número más alto (C12) en vez del del mes
en curso — origen de los médicos con alta en C12, la hoja de coaching archivada en diciembre
y el panel de cobertura en 0.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.routers.admin import _validar_ciclo_unico_abierto
from app.api.v1.routers.dims import _ciclo_nace_cerrado


def _db(abierto):
    """Sesión falsa: la consulta de "¿hay un ciclo abierto?" devuelve `abierto`."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = abierto
    return db


C07 = SimpleNamespace(id=41, nombre="C07-2026", fecha_inicio="2026-07-01", fecha_fin="2026-07-28")


# ── Reabrir un ciclo (PATCH /admin/ciclos/{id}/abrir) ─────────────────────────

def test_abrir_un_segundo_ciclo_se_rechaza():
    with pytest.raises(HTTPException) as e:
        _validar_ciclo_unico_abierto(_db(C07), "DO", "C12-2026")
    assert e.value.status_code == 409


def test_el_error_nombra_el_ciclo_que_estorba_y_que_hacer():
    """Un 409 que no dice cuál cerrar obliga al admin a adivinar."""
    with pytest.raises(HTTPException) as e:
        _validar_ciclo_unico_abierto(_db(C07), "DO", "C12-2026")
    detalle = e.value.detail
    assert "C07-2026" in detalle and "C12-2026" in detalle
    assert "ciérralo" in detalle.lower()


def test_abrir_cuando_no_hay_ninguno_abierto_se_permite():
    _validar_ciclo_unico_abierto(_db(None), "DO", "C08-2026")  # no levanta


# ── Nacimiento del ciclo (crear / importar) ───────────────────────────────────

def test_el_primer_ciclo_del_pais_nace_abierto():
    """Si naciera cerrado, el país quedaría sin ciclo de trabajo."""
    assert _ciclo_nace_cerrado(_db(None), "DO", set()) is False


def test_con_un_ciclo_ya_abierto_el_nuevo_nace_cerrado():
    assert _ciclo_nace_cerrado(_db(SimpleNamespace(id=41)), "DO", set()) is True


def test_importar_12_ciclos_deja_exactamente_uno_abierto():
    """EL BUG ORIGINAL: los 12 ciclos del Excel nacían abiertos. Las filas nuevas aún no
    están en la BD, así que el cupo se traquea en memoria durante la importación."""
    db = _db(None)  # base sin ciclos
    cupo: set[str] = set()
    nacimientos = [_ciclo_nace_cerrado(db, "DO", cupo) for _ in range(12)]
    assert nacimientos.count(False) == 1   # exactamente uno abierto
    assert nacimientos[0] is False         # y es el primero
    assert nacimientos.count(True) == 11


def test_el_cupo_es_por_pais_no_global():
    """Cada país tiene su propio ciclo abierto: DO no consume el cupo de CR."""
    db = _db(None)
    cupo: set[str] = set()
    assert _ciclo_nace_cerrado(db, "DO", cupo) is False
    assert _ciclo_nace_cerrado(db, "CR", cupo) is False   # país distinto, cupo propio
    assert _ciclo_nace_cerrado(db, "DO", cupo) is True    # DO ya lo gastó
