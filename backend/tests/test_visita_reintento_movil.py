"""Un reintento del móvil no puede crear una visita doble.

POR QUÉ IMPORTA. La app del visitador captura sin conexión y envía cuando vuelve la red.
El caso que rompe no es «no llegó»: es «llegó y se perdió la respuesta» —un parqueo
subterráneo basta—. Ahí el teléfono no puede distinguir un envío perdido de uno que
entró, así que reintenta; y sin huella de cliente el reintento crea una segunda visita:
cobertura inflada y un médico contado dos veces sin que nadie lo note.

Que el reintento devuelva la visita YA EXISTENTE, y no un error, es deliberado: para el
teléfono tiene que verse exactamente como si hubiera funcionado a la primera. Un 409
obligaría a cada cliente a distinguir «ya estaba» de «falló», y esa distinción se
implementa mal tarde o temprano.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from app.schemas.visita import VisitaNoVisita, VisitaRegistrar
from app.services import visita_registro_service as rs


def _db_con_visita(existente):
    """Una sesión que responde esa visita a la consulta por huella."""
    db = MagicMock()
    db.query.return_value.filter.return_value.first.return_value = existente
    return db


HUELLA = "8f14e45f-ea8b-4a4c-9f3d-0b1c2d3e4f50"


def test_el_reintento_devuelve_la_visita_que_ya_existe():
    ya = SimpleNamespace(id=42, uuid_cliente=HUELLA)
    db = _db_con_visita(ya)
    datos = VisitaRegistrar(medico_id=1, tipo_visita="V",
                            comentario="Se revisó el material de la línea",
                            uuid_cliente=HUELLA)

    v = rs.registrar_visita(db, vm_id=7, datos=datos, usuario_id=1)

    assert v is ya
    db.add.assert_not_called()
    db.commit.assert_not_called()


def test_el_reintento_de_una_no_visita_tampoco_duplica():
    ya = SimpleNamespace(id=43, uuid_cliente=HUELLA)
    db = _db_con_visita(ya)
    datos = VisitaNoVisita(medico_id=1, causa="Médico en Vacaciones", uuid_cliente=HUELLA)

    v = rs.registrar_no_visita(db, vm_id=7, datos=datos, usuario_id=1)

    assert v is ya
    db.add.assert_not_called()


def test_sin_huella_no_se_busca_nada():
    """La web no manda huella y no la necesita: ahí el usuario ve el resultado en
    pantalla y no hay reintento ciego. Sin `uuid_cliente` la búsqueda ni siquiera se
    hace — si no, todas las visitas de la web se verían como reintentos entre sí, que
    es exactamente el fallo que este mecanismo debe evitar."""
    db = MagicMock()
    assert rs._ya_registrada(db, vm_id=7, uuid_cliente=None) is None
    db.query.assert_not_called()


def test_la_huella_es_por_vm():
    """Se consulta filtrando por VM además de por huella: dos teléfonos distintos no
    deben poder anularse un envío por un choque de identificadores."""
    db = _db_con_visita(None)
    rs._ya_registrada(db, vm_id=7, uuid_cliente=HUELLA)
    # Dos condiciones en el filtro: la del VM y la de la huella.
    assert len(db.query.return_value.filter.call_args.args) == 2
