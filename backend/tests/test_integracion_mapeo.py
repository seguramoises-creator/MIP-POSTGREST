"""La primitiva de mapeo: buscar, ADOPTAR, crear.

El caso que estas pruebas cuidan es el de adopción: VISTA ya tiene su maestro
cargado por Excel, sin ningún identificador de Mallén. Si la sincronización solo
supiera crear, la primera corrida duplicaría cada representante y cada médico.

Necesita PostgreSQL real: se prueba contra las tablas y sus índices únicos.
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
from app.models.dimensiones import Linea, Pais
from app.models.mapeo_externo import ENT_LINEA, MapeoExterno
from app.services import integracion_mapeo as mapeo

BD_PRUEBA = "vista_test_mapeo"


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
        pytest.skip(f"sin PostgreSQL alcanzable para pruebas de integración: {exc}")
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
    for tabla in ('"Config"."MapeoExterno"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def pais(db):
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.commit()
    return "DO"


def _crear_linea(db, codigo: str, nombre: str):
    """Callable de creación: añade, hace flush y devuelve el registro con id."""
    def _hacer():
        linea = Linea(pais_codigo="DO", codigo=codigo, nombre=nombre)
        db.add(linea)
        db.flush()
        return linea
    return _hacer


def _buscar_linea(db, codigo: str):
    def _hacer():
        return (db.query(Linea)
                .filter(Linea.pais_codigo == "DO", Linea.codigo == codigo)
                .first())
    return _hacer


def test_adopta_el_registro_que_ya_existe_en_vista(db, pais):
    """El caso que da sentido a todo: VISTA ya tenía la línea cargada por Excel.

    Sin adopción, la sincronización crearía una segunda línea con el mismo
    código y el maestro quedaría duplicado.
    """
    existente = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(existente)
    db.commit()

    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_ADOPTADO
    assert registro.id == existente.id
    assert db.query(Linea).count() == 1          # NO se duplicó
    assert db.query(MapeoExterno).count() == 1


def test_crea_cuando_no_existe(db, pais):
    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "DERM", Linea,
        _buscar_linea(db, "DERM"), _crear_linea(db, "DERM", "Dermatología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_CREADO
    assert registro.codigo == "DERM"
    assert db.query(Linea).count() == 1


def test_segunda_llamada_actualiza_por_el_mapeo(db, pais):
    """Idempotencia: la segunda vez ya hay mapeo, así que ni adopta ni crea."""
    mapeo.resolver(db, ENT_LINEA, "DO", "CARD", Linea,
                   _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_ACTUALIZADO
    assert db.query(Linea).count() == 1
    assert db.query(MapeoExterno).count() == 1


def test_mapeo_huerfano_se_reconstruye(db, pais):
    """Si alguien borró el registro interno a mano, el mapeo apunta al vacío.

    Un mapeo es un dato derivado: se descarta y se vuelve a resolver, en vez de
    dejar la sincronización bloqueada para siempre.
    """
    registro, _ = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()
    db.query(Linea).filter(Linea.id == registro.id).delete()
    db.commit()

    nuevo, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_CREADO
    assert db.query(MapeoExterno).count() == 1
    assert db.query(MapeoExterno).one().id_interno == nuevo.id


def test_id_mapeado_devuelve_el_id_interno(db, pais):
    registro, _ = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert mapeo.id_mapeado(db, ENT_LINEA, "DO", "CARD") == registro.id
    assert mapeo.id_mapeado(db, ENT_LINEA, "DO", "NO-EXISTE") is None
