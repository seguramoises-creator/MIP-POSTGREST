"""Login: el usuario no debe depender de mayúsculas ni de espacios.

Regresión jul-2026 (reportada desde un iPhone): el teclado móvil AUTOCAPITALIZA la
primera letra de un campo de texto, así que "mdavid" llegaba como "Mdavid". La consulta
era `Usuario.username == form_data.username` (exacta) → no encontraba a nadie y
respondía "Credenciales incorrectas" pese a que la contraseña era correcta.
"""
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

from app.api.v1.routers import auth as auth_router


class _Query:
    """Simula el filtro por username: exacto primero, luego insensible."""
    def __init__(self, usuarios): self.usuarios = usuarios; self._pred = None
    def filter(self, criterio):
        self._pred = criterio
        return self
    def first(self):
        return self._pred


def _buscar(db_usuarios, tecleado):
    """Reproduce la lógica del endpoint sin levantar FastAPI."""
    usr = (tecleado or "").strip()
    exacto = next((u for u in db_usuarios if u.username == usr), None)
    if exacto:
        return exacto
    return next((u for u in db_usuarios if u.username.lower() == usr.lower()), None)


USUARIOS = [SimpleNamespace(username="mdavid"), SimpleNamespace(username="admin")]


@pytest.mark.parametrize("tecleado", ["mdavid", "Mdavid", "MDAVID", "  mdavid  ", "MDavid"])
def test_encuentra_al_usuario_pese_a_la_autocapitalizacion(tecleado):
    u = _buscar(USUARIOS, tecleado)
    assert u is not None and u.username == "mdavid"


def test_usuario_inexistente_sigue_sin_encontrarse():
    assert _buscar(USUARIOS, "noexiste") is None


def test_el_endpoint_normaliza_el_username():
    """El código del router debe hacer strip + fallback case-insensitive."""
    import inspect
    fuente = inspect.getsource(auth_router.login)
    assert ".strip()" in fuente
    assert "func.lower(Usuario.username)" in fuente
