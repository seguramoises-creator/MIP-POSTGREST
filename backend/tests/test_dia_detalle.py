"""El detalle del día de un representante respeta el mismo alcance que el monitor."""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from fastapi import HTTPException

from app.api.v1.routers import visita_dia as r


def test_un_representante_no_ve_el_dia_de_otro():
    u = SimpleNamespace(rol="REPRESENTANTE_MEDICO", rm_id=4)
    with pytest.raises(HTTPException) as e:
        r.detalle_dia(rm_id=5, fecha=None, db=MagicMock(), current_user=u)
    assert e.value.status_code == 403


def test_un_gerente_no_ve_el_dia_de_otro_distrito():
    db = MagicMock()
    db.query.return_value.filter.return_value.all.return_value = [SimpleNamespace(id=4), SimpleNamespace(id=6)]
    u = SimpleNamespace(rol="GERENTE_DISTRITO", gerente_id=3)
    with pytest.raises(HTTPException) as e:
        r.detalle_dia(rm_id=9, fecha=None, db=db, current_user=u)
    assert e.value.status_code == 403


def test_un_gerente_sin_equipo_resuelto_no_ve_a_nadie():
    """Sin gerente_id el alcance es una lista VACÍA, no «todo»."""
    u = SimpleNamespace(rol="GERENTE_DISTRITO", gerente_id=None)
    with pytest.raises(HTTPException) as e:
        r.detalle_dia(rm_id=4, fecha=None, db=MagicMock(), current_user=u)
    assert e.value.status_code == 403
