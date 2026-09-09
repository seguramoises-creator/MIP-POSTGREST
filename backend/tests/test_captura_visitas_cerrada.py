"""Quién puede CAPTURAR visitas dentro de VISTA, y quién no.

Historia, porque explica la forma de estas pruebas. La captura se cerró entera cuando
llegó Mallén: allí las visitas vienen de su propio SFA (esquema `ext`) y una segunda
puerta habría dado dos fuentes de verdad para el mismo hecho, con los indicadores
dejando de cuadrar. El cierre era correcto para Mallén y equivocado como regla global:
en una instalación donde la fuerza de ventas registra en VISTA —el caso de la app móvil
del visitador— no hay ningún SFA del que traer nada, y cerrar la captura deja el sistema
sin datos.

Así que la decisión pasó a ser de la INSTALACIÓN (`MODO_INGESTA`), y esto prueba las dos
mitades: que Mallén sigue viendo exactamente el mismo 409 con el mismo texto, y que una
instalación de captura puede escribir.

No necesitan base de datos: comprueban el guard y su cableado.
"""
import inspect

import pytest
from fastapi import HTTPException

from app.api.v1.routers import farmacias, visita
from app.services import captura_service

#: Los cinco endpoints de escritura de visitas. Si mañana aparece un sexto, esta lista
#: es el sitio donde se nota que le falta el guard.
CAPTURA = [
    (visita, "registrar_visita"),
    (visita, "registrar_no_visita"),
    (visita, "subir_foto_visita"),
    (farmacias, "registrar_visita_farmacia"),
    (farmacias, "subir_foto_visita_farmacia"),
]


class _ConfigFalsa:
    """Una sesión que solo sabe responder qué modo de ingesta tiene la instalación."""
    def __init__(self, modo):
        self.modo = modo


@pytest.fixture
def modo(monkeypatch):
    def fijar(valor):
        monkeypatch.setattr(captura_service._cfg, "obtener",
                            lambda db, clave: valor if clave == "MODO_INGESTA" else None)
        return _ConfigFalsa(valor)
    return fijar


def test_mallen_sigue_cerrado(modo):
    """Con `integracion`, la captura no existe."""
    db = modo("integracion")
    assert captura_service.captura_habilitada(db) is False
    with pytest.raises(HTTPException) as exc:
        captura_service.exigir_captura_habilitada(db)
    assert exc.value.status_code == 409


def test_el_mensaje_de_mallen_no_cambia(modo):
    """Palabra por palabra el de antes.

    No es un capricho: ese texto ya se muestra en pantalla en la instalación del
    cliente. Cambiarlo porque nosotros movimos el guard de archivo sería hacerle un
    cambio visible a un cliente que no pidió nada."""
    db = modo("integracion")
    with pytest.raises(HTTPException) as exc:
        captura_service.exigir_captura_habilitada(db)
    assert exc.value.detail == (
        "El registro de visitas está cerrado: las visitas provienen del SFA de "
        "Mallén y se integran automáticamente. Lo ya registrado sigue disponible "
        "para consulta.")


@pytest.mark.parametrize("valor", ["excel", "vista", "", None, "EXCEL", "cualquier-cosa"])
def test_las_demas_instalaciones_capturan(modo, valor):
    """Solo `integracion` cierra. Cualquier otro valor —incluido uno mal tecleado o
    ausente— deja capturar: ante la duda, que el visitador pueda registrar su trabajo.
    Perder una jornada de campo por un valor mal escrito es peor que un dato de más,
    que al menos se ve y se corrige."""
    db = modo(valor)
    assert captura_service.captura_habilitada(db) is True
    captura_service.exigir_captura_habilitada(db)  # no levanta


def test_es_insensible_a_mayusculas_y_espacios(modo):
    assert captura_service.captura_habilitada(modo("  Integracion  ")) is False


@pytest.mark.parametrize("modulo,nombre", CAPTURA)
def test_todos_los_endpoints_de_escritura_piden_el_guard(modulo, nombre):
    """El cableado, comprobado sobre el código fuente.

    Es la prueba que evita el peor final posible de este trabajo: que alguien reabra la
    captura de un endpoint sin el interruptor y Mallén empiece a aceptar visitas por una
    puerta que no debía existir. Un test de integración no lo cubriría —haría falta la
    instalación de Mallén montada—; el cableado sí se puede leer."""
    funcion = getattr(modulo, nombre, None)
    assert funcion is not None, f"No existe {modulo.__name__}.{nombre}"
    fuente = inspect.getsource(funcion)
    assert "exigir_captura_habilitada" in fuente, (
        f"{nombre} escribe visitas y no consulta el interruptor de la instalación")
