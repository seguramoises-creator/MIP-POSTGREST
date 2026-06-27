"""
SCGCPR — Fixtures y helpers compartidos para tests unitarios.

Los servicios críticos (`iup_service`, `puntaje_service`,
`elegibilidad_service`, `recalculo_service`, `reconocimiento_service`)
reciben `db: Session` y construyen queries encadenadas
(`.filter().join().order_by().all()` etc). Para probarlos como unidades
—sin una BD real— se usa `FakeQuery`: un doble de prueba que ignora los
argumentos de cada eslabón de la cadena y simplemente retorna el resultado
terminal configurado (`all`, `first`, `scalar`).

Esto permite testear la LÓGICA DE NEGOCIO (cálculos, reglas, ramas
condicionales) sin acoplar los tests a la estructura SQL exacta.
"""
import pytest
from unittest.mock import MagicMock


class FakeQuery:
    """
    Doble de prueba para `Session.query(...)`. Encadena cualquier método
    típico de SQLAlchemy (`filter`, `join`, `outerjoin`, `order_by`,
    `group_by`, `limit`, `distinct`) devolviéndose a sí mismo, y resuelve
    en el resultado terminal configurado.
    """

    def __init__(self, all_result=None, first_result=None, scalar_result=None):
        self._all = all_result if all_result is not None else []
        self._first = first_result
        self._scalar = scalar_result

    # -- eslabones de la cadena: no-ops que retornan self --
    def filter(self, *a, **k):
        return self

    def filter_by(self, *a, **k):
        return self

    def join(self, *a, **k):
        return self

    def outerjoin(self, *a, **k):
        return self

    def order_by(self, *a, **k):
        return self

    def group_by(self, *a, **k):
        return self

    def limit(self, *a, **k):
        return self

    def offset(self, *a, **k):
        return self

    def distinct(self, *a, **k):
        return self

    # -- terminales --
    def all(self):
        return self._all

    def first(self):
        return self._first

    def scalar(self):
        return self._scalar

    def count(self):
        return len(self._all)


@pytest.fixture
def fake_db():
    """
    Sesión de BD falsa (`MagicMock`) cuyo `.query(Modelo)` se controla vía
    `fake_db.query.side_effect = [FakeQuery(...), FakeQuery(...), ...]`
    — una entrada por cada llamada a `db.query(...)` en el orden en que
    ocurren dentro de la función bajo prueba.
    """
    db = MagicMock()
    return db
