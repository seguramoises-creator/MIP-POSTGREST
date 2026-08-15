"""Modelos de alcance: países del usuario y líneas del gerente.

La regla que estos tests protegen es la del spec §3: SIN FILAS significa "todos
los países". Un modelo que exigiera al menos una fila obligaría a migrar a mano
los 37 usuarios existentes antes de activar la frontera — y ese es justo el paso
que se olvida y deja a todo el mundo sin acceso.
"""
from app.models.alcance import GerenteLinea, UsuarioPais


def test_usuario_pais_declara_su_tabla_y_esquema():
    assert UsuarioPais.__tablename__ == "FACT_UsuarioPais"
    assert UsuarioPais.__table__.schema == "Security"


def test_gerente_linea_declara_su_tabla_y_esquema():
    assert GerenteLinea.__tablename__ == "DIM_GerenteLinea"
    assert GerenteLinea.__table__.schema == "Config"


def test_la_pareja_usuario_pais_es_unica():
    """Sin el único, asignar dos veces el mismo país duplica filas y el conteo
    de 'cuántos países tiene' deja de ser fiable."""
    unicos = [set(c.columns.keys()) for c in UsuarioPais.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert {"usuario_id", "pais_codigo"} in unicos


def test_la_pareja_gerente_linea_es_unica():
    unicos = [set(c.columns.keys()) for c in GerenteLinea.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert {"gerente_id", "linea_id"} in unicos
