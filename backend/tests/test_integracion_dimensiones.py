"""Sincronización de dimensiones `ext` → catálogos internos de VISTA.

Lo que estas pruebas cuidan por encima de todo: que sincronizar NO duplique el
maestro que VISTA ya tiene cargado, y que no toque el estado `cerrado` de un
ciclo (del que dependen recálculos y premios).

Necesita PostgreSQL real: cruza dos esquemas con claves compuestas e índices
únicos.
"""
from datetime import date

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
from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.services import integracion_dimensiones_service as dim

BD_PRUEBA = "vista_test_dimensiones"


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
    # Hijos antes que padres.
    for tabla in ('"Config"."MapeoExterno"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', "ext.dimrepresentante",
                  "ext.dimgerente", "ext.dimciclo", "ext.dimlinea",
                  "ext.dimpais", '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def base(db):
    """País y línea en AMBOS lados: el punto de partida de todo el resto."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    db.add(ExtDimLinea(pais_codigo="DO", linea_codigo="CARD",
                       nombre="Cardiología", activo=True))
    db.commit()
    return db


def test_adopta_el_representante_que_vista_ya_tenia(base):
    """El caso de la primera corrida en producción.

    VISTA lleva el piloto con 48 representantes cargados por Excel. Si la
    sincronización no los adoptara, quedarían 96.
    """
    db = base
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    db.add(RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                               codigo="VM01", nombre="Representante Uno"))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               linea_codigo="CARD", nombre="Representante Uno",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1     # NO se duplicó


def test_crea_el_representante_que_no_existia(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo Representante",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    rm = db.query(RepresentanteMedico).one()
    assert rm.codigo == "VM99"
    assert rm.linea_id is not None      # resolvió la FK contra la línea mapeada


def test_no_toca_el_estado_cerrado_del_ciclo(base):
    """Decisión del cliente: el abrir/cerrar de un ciclo es de VISTA.

    De `cerrado` dependen los recálculos y los premios; que un envío externo
    reabra un ciclo cerrado dispararía cálculos sobre datos históricos.
    """
    db = base
    db.add(Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                 fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                 dias_laborables=22, cerrado=False))
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, nombre="Ciclo 1 Mallén",
                       fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                       dias_laborables=20, cerrado=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_ciclo(db, "DO", hallazgos)
    db.commit()

    ciclo = db.query(Ciclo).one()
    assert ciclo.cerrado is False                  # sigue abierto: manda VISTA
    assert ciclo.dias_laborables == 20             # lo demás sí se sincroniza
    assert conteo.adoptados == 1
    assert any(h.severidad == dim.SEVERIDAD_AVISO for h in hallazgos)


def test_codigo_demasiado_largo_se_omite_sin_truncar(base):
    """DIM_Gerente.codigo es String(20) y ext permite 30.

    Truncar juntaría dos códigos distintos que compartan los primeros 20
    caracteres, que es peor que no cargar la fila.
    """
    db = base
    db.add(ExtDimGerente(pais_codigo="DO",
                         gerente_codigo="GER-DISTRITO-NORTE-2026-A",
                         nombre="Gerente Norte", tipo="DISTRITO", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_gerente(db, "DO", hallazgos)
    db.commit()

    assert conteo.omitidos == 1
    assert conteo.creados == 0
    assert db.query(Gerente).count() == 0
    assert any(h.severidad == dim.SEVERIDAD_ERROR for h in hallazgos)


def test_sincronizar_dos_veces_no_duplica(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)
    dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1
