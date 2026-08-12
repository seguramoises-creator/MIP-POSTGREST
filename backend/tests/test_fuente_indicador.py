"""El dueño de EVAL_CONOCIMIENTOS, por país.

Tres caminos escriben ese indicador con delete-then-insert, así que sin un dueño
declarado gana el último en correr, sin error y sin rastro. Aquí se prueba la
regla; las puertas que la aplican se prueban en sus propios módulos.

Necesita PostgreSQL real.
"""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, integracion_hallazgo, mapeo_externo,
    seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import FuenteIndicador, Pais
from app.services import fuente_indicador_service as fs

BD_PRUEBA = "vista_test_fuente"


def _url(nombre: str) -> str:
    return (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_SERVER}:{settings.DB_PORT}/{nombre}")


@pytest.fixture(scope="module")
def motor():
    try:
        admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as cx:
            cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
            cx.execute(text(f"CREATE DATABASE {BD_PRUEBA}"))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"Config"."FuenteIndicador"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.commit()
    yield s
    s.close()


def test_pais_sin_fila_responde_el_default(db):
    """El default es CAPTURA_MANUAL, no un error: un país recién creado tiene
    que poder capturar sin que nadie configure nada primero."""
    assert (fuente := fs.fuente_de(db, "DO"))
    assert fuente == fs.FUENTE_CAPTURA_MANUAL


def test_fijar_fuente_deja_autor_y_fecha(db):
    fila = fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=7)
    db.commit()

    assert fila.fuente == fs.FUENTE_EXAMEN_VISTA
    assert fila.actualizado_por_usuario_id == 7
    assert fila.actualizado_en is not None
    assert fs.fuente_de(db, "DO") == fs.FUENTE_EXAMEN_VISTA


def test_fijar_fuente_dos_veces_actualiza_la_misma_fila(db):
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=7)
    db.commit()
    fs.fijar_fuente(db, "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=8)
    db.commit()

    filas = db.query(FuenteIndicador).filter(
        FuenteIndicador.pais_codigo == "DO").all()
    assert len(filas) == 1
    assert filas[0].fuente == fs.FUENTE_NOTA_EXTERNA


def test_una_fuente_inventada_se_rechaza(db):
    """EXCEL entre ellas: no es que no sea el dueño, es que dejó de ser una vía."""
    for invento in ("EXCEL", "excel", "", "OTRA_COSA"):
        with pytest.raises(ValueError):
            fs.fijar_fuente(db, "DO", invento, usuario_id=1)


def test_asegurar_duenio_pasa_cuando_coincide(db):
    fs.fijar_fuente(db, "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    db.commit()

    fs.asegurar_duenio(db, "DO", fs.FUENTE_NOTA_EXTERNA)   # no levanta


def test_asegurar_duenio_nombra_al_dueno_real(db):
    """El mensaje tiene que decir QUIÉN es el dueño: 'no tienes permiso' deja al
    operador sin saber qué cambiar."""
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    db.commit()

    with pytest.raises(fs.FuenteAjenaError) as exc:
        fs.asegurar_duenio(db, "DO", fs.FUENTE_CAPTURA_MANUAL)

    assert exc.value.duenio == fs.FUENTE_EXAMEN_VISTA
    assert exc.value.intento == fs.FUENTE_CAPTURA_MANUAL
    assert fs.FUENTE_EXAMEN_VISTA in str(exc.value)


def test_el_dueno_es_por_pais(db):
    db.add(Pais(codigo="PR", nombre="Puerto Rico"))
    db.commit()
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    db.commit()

    assert fs.fuente_de(db, "DO") == fs.FUENTE_EXAMEN_VISTA
    assert fs.fuente_de(db, "PR") == fs.FUENTE_CAPTURA_MANUAL
