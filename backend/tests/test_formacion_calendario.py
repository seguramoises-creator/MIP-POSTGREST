"""Calendario de Coaching (Fase 4) — motor de reglas sobre el cuadrante LSII."""
from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.formacion import ParametroFrecuenciaLSII
from app.models.hechos import EvaluacionReceptividad
from app.services import formacion_calendario_service as cal

BD_PRUEBA = "vista_test_calcoach"


def test_reparto_de_una_visita_cae_a_mitad_del_ciclo():
    assert cal.distribuir_semanas(1, 8) == [4]


def test_reparto_de_cuatro_visitas_queda_espaciado():
    assert cal.distribuir_semanas(4, 8) == [1, 3, 5, 7]


def test_reparto_de_dos_visitas():
    assert cal.distribuir_semanas(2, 8) == [2, 6]


def test_cero_visitas_no_agenda_nada():
    assert cal.distribuir_semanas(0, 8) == []


def test_mas_visitas_que_semanas_se_acota_al_rango():
    # Nunca propone una semana fuera de [1, semanas]; puede repetir semana.
    r = cal.distribuir_semanas(10, 4)
    assert len(r) == 10
    assert all(1 <= s <= 4 for s in r)


def test_frecuencia_arranca_en_los_valores_por_defecto(db):
    f = cal.frecuencias(db, "DO")
    assert f == {"D1": 4, "D2": 3, "D3": 2, "D4": 1}


def test_un_pais_puede_sobrescribir_una_frecuencia(db):
    cal.fijar_frecuencia(db, "DO", "D1", 6)
    assert cal.frecuencias(db, "DO")["D1"] == 6
    # Override por país: otro país conserva el arranque.
    assert cal.frecuencias(db, "PA")["D1"] == 4


def test_fijar_un_cuadrante_invalido_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D9", 1)


def test_fijar_visitas_negativas_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D1", -1)


# --- infraestructura de BD (igual patrón que test_formacion_brechas) ---
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
    for t in ('formacion."CalendarioCoachingSugerido"', 'formacion."ParametroFrecuenciaLSII"',
              '"DW"."FACT_EvaluacionReceptividad"', '"Config"."DIM_RM"',
              '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Ciclo"',
              '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.add_all([Pais(codigo="DO", nombre="República Dominicana"),
               Pais(codigo="PA", nombre="Panamá")])
    s.commit()
    yield s
    s.close()


@pytest.fixture
def equipo(db):
    """Un GD con dos RM y un ciclo con fechas de 8 semanas."""
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea); db.flush()
    gd = Gerente(pais_codigo="DO", codigo="GD-1", nombre="GD Uno", tipo="DISTRITO")
    db.add(gd); db.flush()
    rm_a = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM01", nombre="Ana")
    rm_b = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM02", nombre="Beto")
    db.add_all([rm_a, rm_b])
    ciclo = Ciclo(pais_codigo="DO", nombre="C07-2026", anio=2026, numero=7,
                  cerrado=False, fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 7, 26))
    db.add(ciclo); db.commit()
    return {"db": db, "gd": gd, "rm_a": rm_a, "rm_b": rm_b, "ciclo": ciclo, "linea": linea}


def _eval(db, rm_id, ciclo_id, nivel):
    e = EvaluacionReceptividad(pais_codigo="DO", rm_id=rm_id, ciclo_id=ciclo_id,
                               score_receptividad=50, nivel_lsii=nivel,
                               estilo_liderazgo="X", activo=True)
    db.add(e); db.commit(); return e


def test_cuadrante_vigente_toma_la_ultima_evaluacion(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, rm.id, ciclo.id, "D3")
    _eval(db, rm.id, ciclo.id, "D1")   # más reciente
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) == "D1"


def test_rm_sin_evaluacion_no_tiene_cuadrante(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_b"], equipo["ciclo"]
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) is None
