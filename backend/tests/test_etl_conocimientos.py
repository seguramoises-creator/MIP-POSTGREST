"""El Excel deja de alimentar EVAL_CONOCIMIENTOS, y deja de barrer el ciclo entero.

Dos reglas:
  1. Las filas de EVAL_CONOCIMIENTOS del archivo se omiten SIEMPRE (decisión del
     cliente: "nunca más Excel para este proceso") y se reportan como
     advertencia, sin tumbar el resto del archivo.
  2. El borrado previo se acota a los indicadores que ESE archivo trae. Antes
     barría el ciclo completo, lo que desde la integración de Mallén destruía
     indicadores que el Excel no repone.

Necesita PostgreSQL real.
"""
from datetime import date
from decimal import Decimal

import pandas as pd
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
from app.models.dimensiones import Ciclo, Gerente, Indicador, Linea, Pais, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.services import etl_service

BD_PRUEBA = "vista_test_etl_conoc"


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
def escenario(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"DW"."FACT_ResultadoIndicador"', '"Config"."DIM_Indicador"',
                  '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()

    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    s.add(linea)
    s.flush()
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="g@ejemplo.com", tipo="DISTRITO")
    s.add(gerente)
    s.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             gerente_id=gerente.id, codigo="VM01",
                             nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    s.add_all([rm, ciclo])
    s.flush()
    indicadores = {}
    for codigo, escala in (("EVAL_CONOCIMIENTOS", 100), ("COB_MD_F1", 1),
                           ("VENTAS", 1)):
        i = Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                      modulo="RESULTADOS", tipo_periodo="CICLO", escala=escala,
                      ponderacion_pct=10, activo=True)
        s.add(i)
        s.flush()
        indicadores[codigo] = i
    s.commit()
    yield {"db": s, "rm": rm, "ciclo": ciclo, "linea": linea,
           "gerente": gerente, "ind": indicadores}
    s.close()


def _mapas(e):
    ind = {("DO", c): i.id for c, i in e["ind"].items()}
    return {
        "rm": {"VM01": {"id": e["rm"].id, "linea_id": e["linea"].id,
                        "gerente_id": e["gerente"].id, "pais_codigo": "DO"}},
        "gerente": {}, "cap": {}, "ind": ind,
        "ciclo": {("DO", 2026, 1): e["ciclo"].id},
        "pais": {"DO": "DO"},
    }


def _df(filas):
    return pd.DataFrame(filas)


def _resultado(e, codigo):
    return (e["db"].query(ResultadoIndicador)
            .filter(ResultadoIndicador.indicador_id == e["ind"][codigo].id,
                    ResultadoIndicador.ciclo_id == e["ciclo"].id).first())


def test_las_filas_de_conocimientos_se_omiten_y_las_demas_cargan(escenario):
    e = escenario
    df = _df([
        {"rm_codigo": "VM01", "indicador_codigo": "EVAL_CONOCIMIENTOS",
         "valor_real": 88, "pais_codigo": "DO", "anio": 2026, "ciclo_id": 1},
        {"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
         "valor_real": 0.9, "pais_codigo": "DO", "anio": 2026, "ciclo_id": 1},
    ])

    exitosas, errores, advertencias = etl_service._cargar_datos(
        e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert exitosas == 1
    assert errores == []
    assert _resultado(e, "COB_MD_F1") is not None
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
    assert any("EVAL_CONOCIMIENTOS" in a for a in advertencias)


def test_el_excel_no_borra_lo_que_no_repone(escenario):
    """El defecto de fondo: el borrado previo barría el ciclo ENTERO. Desde la
    integración de Mallén eso destruye VENTAS y los indicadores de visita, que
    el Excel no repone."""
    e = escenario
    for codigo, valor in (("VENTAS", Decimal("0.9")),
                          ("EVAL_CONOCIMIENTOS", Decimal("77"))):
        e["db"].add(ResultadoIndicador(
            rm_id=e["rm"].id, indicador_id=e["ind"][codigo].id,
            ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
            gerente_id=e["gerente"].id, resultado_real=valor, activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
               "valor_real": 0.5, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    etl_service._cargar_datos(e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert _resultado(e, "VENTAS").resultado_real == Decimal("0.9000")
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("77.0000")
    assert _resultado(e, "COB_MD_F1") is not None


def test_el_excel_si_reemplaza_lo_suyo(escenario):
    """La otra mitad de la regla: acotar el borrado no puede volverlo inútil —
    un indicador que el archivo SÍ trae se reemplaza, no se duplica."""
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["COB_MD_F1"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("0.1"), activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
               "valor_real": 0.5, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    etl_service._cargar_datos(e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["COB_MD_F1"].id).all())
    assert len(filas) == 1
    assert filas[0].resultado_real == Decimal("0.5000")


def test_un_archivo_solo_de_conocimientos_no_borra_nada(escenario):
    """Caso límite del acotado: si tras excluir no queda ningún indicador que
    reponer, no debe borrarse nada en absoluto."""
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("77"), activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "EVAL_CONOCIMIENTOS",
               "valor_real": 88, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    exitosas, _, _ = etl_service._cargar_datos(
        e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert exitosas == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("77.0000")
