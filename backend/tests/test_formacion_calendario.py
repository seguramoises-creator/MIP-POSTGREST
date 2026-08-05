"""Calendario de Coaching (Fase 4) — motor de reglas sobre el cuadrante LSII."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Pais
from app.models.formacion import ParametroFrecuenciaLSII
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
