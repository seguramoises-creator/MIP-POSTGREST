from app.models.usuario import Rol


def test_rol_capacitacion_existe():
    assert Rol.CAPACITACION.value == "CAPACITACION"
