"""Lo que queda escrito en disco es UTC — y contra una BD de verdad.

Esta prueba existe porque el resto de la suite NO puede fallar por este defecto:
todo lo demás usa dobles, y la sesión de la aplicación abre ya con `timezone=UTC`,
o sea que corre justo en la única configuración donde el fallo no se reproduce. Una
prueba así pasa en verde diga lo que diga el código de escritura.

Así que aquí se hace lo contrario: se fuerza la sesión a `America/Santo_Domingo` —la
zona del cliente, y la que tenía el portátil donde se descubrió esto— y se miden LAS
DOS ramas contra PostgreSQL. Sin la rama que falla, la que pasa no demuestra nada.

El defecto: `datetime.now(timezone.utc)` es un valor CONSCIENTE, y al entrar en una
columna `TIMESTAMP WITHOUT TIME ZONE` PostgreSQL lo convierte a la zona de la sesión y
descarta el huso. Lo almacenado dependía de la máquina, no del código.
"""
from datetime import datetime, timezone

import pytest
from sqlalchemy import create_engine, text

from app.core.config import settings

ZONA_CLIENTE = "America/Santo_Domingo"          # UTC-4
INSTANTE = datetime(2026, 9, 10, 3, 49, 9, tzinfo=timezone.utc)   # 23:49 del 9 en RD


@pytest.fixture(scope="module")
def cx_en_rd():
    """Conexión CRUDA con la sesión en hora de RD: el escenario del defecto.

    No se usa el engine de la aplicación a propósito — ese ya impone UTC y con él
    ninguna de las dos ramas se distinguiría."""
    url = (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
           f"@{settings.DB_SERVER}:{settings.DB_PORT}/{settings.DB_NAME}")
    try:
        eng = create_engine(url)
        con = eng.connect()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
    con.execute(text(f"SET TimeZone = '{ZONA_CLIENTE}'"))
    con.execute(text("CREATE TEMP TABLE _prueba_utc (t timestamp without time zone)"))
    yield con
    con.close()
    eng.dispose()


def _ida_y_vuelta(cx, valor):
    cx.execute(text("DELETE FROM _prueba_utc"))
    cx.execute(text("INSERT INTO _prueba_utc VALUES (:v)"), {"v": valor})
    return cx.execute(text("SELECT t FROM _prueba_utc")).scalar()


def test_la_sesion_de_la_prueba_no_es_utc(cx_en_rd):
    """Control del control: si la sesión fuera UTC, las dos ramas darían igual y las
    dos pruebas de abajo pasarían sin medir nada."""
    assert cx_en_rd.execute(text("SHOW TimeZone")).scalar() == ZONA_CLIENTE


def test_un_valor_consciente_se_guarda_en_hora_local(cx_en_rd):
    """LA RAMA QUE FALLA. Es el defecto, escrito como prueba para que se vea."""
    guardado = _ida_y_vuelta(cx_en_rd, INSTANTE)
    assert guardado == datetime(2026, 9, 9, 23, 49, 9)     # 23:49 hora de RD, no UTC
    assert guardado != INSTANTE.replace(tzinfo=None)


def test_un_valor_naive_utc_se_guarda_verbatim(cx_en_rd):
    """LA RAMA QUE ARREGLA. Sin huso no hay nada que convertir: entra lo que dice
    el código, en cualquier máquina y con cualquier zona de servidor."""
    naive = INSTANTE.replace(tzinfo=None)
    assert _ida_y_vuelta(cx_en_rd, naive) == naive


def test_la_aplicacion_abre_sus_conexiones_en_utc():
    """Guarda la opción de conexión de `app/db/database.py`.

    Es la que sostiene los ~140 `datetime.now(timezone.utc)` que siguen repartidos por
    la aplicación fuera del módulo Visita. Si alguien la quita, lo que se rompe no da
    error: cambia en silencio el significado de lo que se guarda.

    El `assert` va FUERA del try a propósito. Envolviéndolo, al quitar la opción de
    conexión esta prueba salía «saltada» y no «fallada»: el `except` se tragaba el
    `AssertionError` y lo presentaba como «no hay base alcanzable». Un guardián que
    convierte su propio fallo en una ausencia no guarda nada — comprobado quitando la
    opción de verdad, que es la única forma de saber si una prueba puede fallar.
    """
    from app.db.database import SessionLocal
    db = SessionLocal()
    try:
        zona = db.execute(text("SHOW TimeZone")).scalar()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
    finally:
        db.close()
    assert zona == "UTC"


def test_el_modulo_visita_escribe_naive():
    """Y que el código lo diga por sí mismo, sin depender de la opción de conexión."""
    from app.models.visita import _ahora
    from app.services import visita_farmacia_service as vfs
    from app.services import visita_registro_service as vrs
    for fn in (_ahora, vrs._ahora_utc, vfs._ahora_utc):
        valor = fn()
        assert valor.tzinfo is None, fn
        # Y es UTC, no la hora local de la máquina (que es lo que se guardaba antes).
        assert abs((valor - datetime.now(timezone.utc).replace(tzinfo=None)).total_seconds()) < 5
