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


def test_un_representante_no_ve_la_foto_de_otro():
    """La foto del monitor tiene el alcance del monitor, no solo el del país."""
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 5   # la visita es de VM 5
    u = SimpleNamespace(rol="REPRESENTANTE_MEDICO", rm_id=4)
    for tipo in ("medico", "farmacia"):
        with pytest.raises(HTTPException) as e:
            r.foto_dia(tipo=tipo, visita_id=938, db=db, current_user=u)
        assert e.value.status_code == 403


def test_un_gerente_no_ve_la_foto_de_otro_distrito():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 9
    db.query.return_value.filter.return_value.all.return_value = [SimpleNamespace(id=4)]
    u = SimpleNamespace(rol="GERENTE_DISTRITO", gerente_id=3)
    with pytest.raises(HTTPException) as e:
        r.foto_dia(tipo="medico", visita_id=1, db=db, current_user=u)
    assert e.value.status_code == 403


def test_la_foto_propia_se_devuelve_como_imagen():
    db = MagicMock()
    db.query.return_value.filter.return_value.scalar.return_value = 4
    db.query.return_value.filter.return_value.first.return_value = (b"\xff\xd8\xffJPEG", "image/jpeg")
    u = SimpleNamespace(rol="REPRESENTANTE_MEDICO", rm_id=4)
    resp = r.foto_dia(tipo="medico", visita_id=938, db=db, current_user=u)
    assert resp.media_type == "image/jpeg" and resp.body.startswith(b"\xff\xd8\xff")


def test_tipo_desconocido_es_404():
    u = SimpleNamespace(rol="ADMIN")
    with pytest.raises(HTTPException) as e:
        r.foto_dia(tipo="otro", visita_id=1, db=MagicMock(), current_user=u)
    assert e.value.status_code == 404


def test_un_gerente_sin_equipo_resuelto_no_ve_a_nadie():
    """Sin gerente_id el alcance es una lista VACÍA, no «todo»."""
    u = SimpleNamespace(rol="GERENTE_DISTRITO", gerente_id=None)
    with pytest.raises(HTTPException) as e:
        r.detalle_dia(rm_id=4, fecha=None, db=MagicMock(), current_user=u)
    assert e.value.status_code == 403
