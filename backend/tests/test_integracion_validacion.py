"""Validación de los lotes que envía Mallén (esquema `ext`).

Necesita PostgreSQL real: la validación recorre siete tablas con claves
compuestas y foráneas entre esquemas; probarlo con dobles verificaría los dobles.
Si no hay base alcanzable se salta, como el resto de pruebas de integración.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, integracion_hallazgo,
    seguridad_rbac, usuario, visita,
)
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedico, ExtDimPais, ExtDimRepresentante,
    ExtFactVisitaMedico, ExtPanelMedico,
)
from app.models.integracion_hallazgo import IntegracionHallazgo
from app.services import integracion_validacion_service as validacion

BD_PRUEBA = "vista_test_integracion"


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
    # Hijos antes que padres: los hallazgos apuntan al lote y los hechos también.
    for tabla in ('"Audit"."IntegracionHallazgo"', "ext.factvisitamedico",
                  "ext.panelmedico", "ext.controlcarga", "ext.dimmedico",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais"):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


def _lote(db, lote_id: int = 1001, filas: int = 2, estado: str = "RECIBIDO"):
    db.add(ExtControlCarga(
        lote_id=lote_id, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", periodo="2026-01",
        fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0),
        filas_enviadas=filas, estado=estado))
    db.flush()


@pytest.fixture
def escenario(db):
    """Un lote limpio: dimensiones completas, un panel y una visita válidos."""
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=21,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", activo=True))
    db.flush()
    _lote(db)
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo="MD01", frecuencia_objetivo="F1", prioridad="TOP",
        categoria="A", visitas_programadas=2, activo=True))
    db.add(ExtFactVisitaMedico(
        lote_id=1001, origen_id="V-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo="MD01",
        fecha_visita=date(2026, 1, 15), tipo_visita="V", ejecutada=True,
        acompanado=False))
    db.commit()
    return {"db": db, "lote_id": 1001}


def test_lote_limpio_queda_validado(escenario):
    r = validacion.validar_lote(escenario["db"], escenario["lote_id"])

    assert r["estado"] == "VALIDADO"
    assert r["errores"] == 0
    assert r["filas_declaradas"] == r["filas_reales"] == 2


def test_tipo_visita_invalido_rechaza_el_lote(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["errores"] == 1
    h = db.query(IntegracionHallazgo).one()
    assert h.tabla == "factvisitamedico"
    assert h.campo == "tipo_visita"
    assert h.origen_id == "V-0001"
    assert h.severidad == "error"


def test_minuscula_no_se_acepta_en_silencio(escenario):
    """La comparación es sensible a mayúsculas: normalizar ocultaría que el
    origen de Mallén envía inconsistente."""
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "v"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["errores"] == 1


def test_panel_con_frecuencia_y_prioridad_invalidas(escenario):
    db = escenario["db"]
    panel = db.query(ExtPanelMedico).one()
    panel.frecuencia_objetivo = "F3"
    panel.prioridad = "ALTA"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["errores"] == 2
    campos = {h.campo for h in db.query(IntegracionHallazgo).all()}
    assert campos == {"frecuencia_objetivo", "prioridad"}


def test_conteo_descuadrado_es_error_de_lote(escenario):
    """Síntoma clásico de una carga cortada a la mitad. El hallazgo no pertenece
    a ninguna fila, así que va sin origen_id ni campo."""
    db = escenario["db"]
    db.get(ExtControlCarga, escenario["lote_id"]).filas_enviadas = 99
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["filas_declaradas"] == 99
    assert r["filas_reales"] == 2
    h = db.query(IntegracionHallazgo).one()
    assert h.origen_id is None and h.campo is None
    assert h.severidad == "error"


def test_revalidar_no_duplica_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()

    validacion.validar_lote(db, escenario["lote_id"])
    validacion.validar_lote(db, escenario["lote_id"])

    assert db.query(IntegracionHallazgo).count() == 1


def test_no_se_revalida_un_lote_integrado(escenario):
    db = escenario["db"]
    db.get(ExtControlCarga, escenario["lote_id"]).estado = "INTEGRADO"
    db.commit()

    with pytest.raises(validacion.LoteYaIntegrado):
        validacion.validar_lote(db, escenario["lote_id"])


def test_lote_inexistente(escenario):
    with pytest.raises(ValueError, match="no encontrado"):
        validacion.validar_lote(escenario["db"], 999999)


def test_listar_lotes_incluye_conteo_de_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()
    validacion.validar_lote(db, escenario["lote_id"])

    filas = validacion.listar_lotes(db)

    assert len(filas) == 1
    assert filas[0]["lote_id"] == 1001
    assert filas[0]["estado"] == "RECHAZADO"
    assert filas[0]["hallazgos"] == 1


def test_listar_lotes_filtra_por_estado(escenario):
    validacion.validar_lote(escenario["db"], escenario["lote_id"])

    assert len(validacion.listar_lotes(escenario["db"], estado="VALIDADO")) == 1
    assert validacion.listar_lotes(escenario["db"], estado="RECHAZADO") == []


def test_detalle_lote_trae_sus_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtPanelMedico).one().prioridad = "ALTA"
    db.commit()
    validacion.validar_lote(db, escenario["lote_id"])

    d = validacion.detalle_lote(db, escenario["lote_id"])

    assert d["lote"]["estado"] == "RECHAZADO"
    assert len(d["hallazgos"]) == 1
    assert d["hallazgos"][0]["campo"] == "prioridad"


def test_resumen_cuenta_por_estado(escenario):
    validacion.validar_lote(escenario["db"], escenario["lote_id"])

    r = validacion.resumen(escenario["db"])

    assert r["VALIDADO"] == 1
    assert r["RECIBIDO"] == 0
