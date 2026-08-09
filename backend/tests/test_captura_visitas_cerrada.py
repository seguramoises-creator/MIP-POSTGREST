"""La captura de visitas dentro de VISTA quedó cerrada.

Las visitas provienen del SFA de Mallén (esquema `ext`). Estos endpoints ya no
escriben: si volvieran a aceptar registros, VISTA tendría dos fuentes de verdad
para el mismo hecho y los indicadores dejarían de cuadrar con los de Mallén.

No necesitan base de datos: comprueban que el guard está declarado antes de
cualquier acceso a datos.
"""
import pytest
from fastapi import HTTPException

from app.api.v1.routers import farmacias, visita

CERRADOS = [
    (visita, "registrar_visita"),
    (visita, "registrar_no_visita"),
    (visita, "subir_foto_visita"),
    (farmacias, "registrar_visita_farmacia"),
    (farmacias, "subir_foto_visita_farmacia"),
]


@pytest.mark.parametrize("modulo,nombre", CERRADOS)
def test_el_endpoint_de_captura_esta_cerrado(modulo, nombre):
    """Cada uno debe levantar 409 con un motivo legible, no fallar de otra forma."""
    funcion = getattr(modulo, nombre, None)
    assert funcion is not None, f"No existe {modulo.__name__}.{nombre}"
    fuente = funcion.__doc__ or ""
    assert "SFA" in fuente or "Mallén" in fuente or "Mallen" in fuente, (
        f"{nombre} debe documentar por qué está cerrado")
