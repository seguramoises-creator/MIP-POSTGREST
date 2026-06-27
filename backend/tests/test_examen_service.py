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
