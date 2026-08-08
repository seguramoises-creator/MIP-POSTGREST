"""Integración de los hechos de visita de Mallén (`ext`) a VISTA.

Lo que estas pruebas cuidan: que re-integrar un ciclo no duplique visitas, y que
una fila cuya dimensión no está sincronizada se omita con hallazgo en vez de
tumbar la corrida.

Necesita PostgreSQL real: cruza tres esquemas con claves compuestas.
"""
from datetime import date, datetime

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
from app.models.dimensiones import (
    Ciclo, Farmacia, Linea, Medico, Pais, RepresentanteMedico, TargetMedico,
)
from app.models.hechos import Visita as FactVisita
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimFarmacia, ExtDimMedico, ExtDimPais,
    ExtDimRepresentante, ExtFactVisitaFarmacia, ExtFactVisitaMedico,
    ExtPanelMedico, ExtTargetFarmacia,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_FARMACIA, ENT_MEDICO, ENT_REPRESENTANTE, MapeoExterno,
)
from app.models.visita import FactVisitaFarmacia, FarmaciaVisita
from app.services import integracion_visitas_service as viz

BD_PRUEBA = "vista_test_visitas_int"


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
    for tabla in ('"Visita"."FactVisitaFarmacia"', '"Visita"."DIM_FarmaciaVisita"',
                  '"Config"."DIM_Farmacia"', "ext.factvisitafarmacia",
                  "ext.targetfarmacia", "ext.dimfarmacia",
                  '"DW"."FACT_Visita"', '"Config"."DIM_TargetMedico"',
                  '"Config"."MapeoExterno"', "ext.factvisitamedico",
                  "ext.panelmedico", "ext.controlcarga", "ext.dimmedico",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Config"."DIM_Medico"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Dimensiones sincronizadas (con su mapeo) + un lote abierto.

    El mapeo se siembra a mano porque este sub-proyecto CONSUME el del
    sub-proyecto 2, no lo produce: probar la integración de hechos no debe
    depender de re-ejecutar la sincronización de dimensiones.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    medico = Medico(pais_codigo="DO", codigo="MD01", nombre="Doctor Uno")
    db.add_all([rm, ciclo, medico])
    db.flush()

    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", activo=True))
    db.add(ExtControlCarga(
        lote_id=1001, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=2,
        estado="VALIDADO"))
    db.flush()

    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id),
                                     (ENT_MEDICO, "MD01", medico.id)):
        db.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                            codigo_externo=codigo, id_interno=interno))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo, "medico": medico}


def _panel(db, medico="MD01", frecuencia="F1", programadas=2):
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo=frecuencia, prioridad="TOP",
        visitas_programadas=programadas, activo=True))
    db.flush()


def _visita(db, origen_id, medico="MD01", ejecutada=True, tipo="V", dia=15):
    db.add(ExtFactVisitaMedico(
        lote_id=1001, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo=medico,
        fecha_visita=date(2026, 1, dia), tipo_visita=tipo, ejecutada=ejecutada,
        acompanado=False))
    db.flush()


def test_panel_crea_el_target_medico(escenario):
    db = escenario["db"]
    _panel(db)
    db.commit()
    hallazgos = []

    conteo = viz.integrar_panel_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    t = db.query(TargetMedico).one()
    assert t.rm_id == escenario["rm"].id
    assert t.ciclo_id == escenario["ciclo"].id
    assert t.medico_codigo == "MD01"
    assert t.programado is True
    # `potencial` significa categoría A/B/C, NO prioridad TOP/REGULAR. La
    # prioridad de `ext` es del sub-proyecto de Médicos TOP; aquí no se
    # escribe. Este assert impide que alguien "aproveche" la columna.
    assert t.potencial is None


def test_visita_ejecutada_entra_como_realizada(escenario):
    db = escenario["db"]
    _visita(db, "V-0001")
    db.commit()
    hallazgos = []

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    v = db.query(FactVisita).one()
    assert v.estado_visita == "Realizada"
    assert v.tipo_contacto == "V"
    assert v.medico_codigo == "MD01"
    assert v.carga_excel_id is None


def test_visita_no_ejecutada_entra_como_cancelada(escenario):
    db = escenario["db"]
    _visita(db, "V-0002", ejecutada=False)
    db.commit()
    hallazgos = []

    viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(FactVisita).one().estado_visita == "Cancelada"


def test_reintegrar_no_duplica_visitas(escenario):
    """El origen_id del contrato es la clave de idempotencia: reenviar el mismo
    lote corrige, no duplica."""
    db = escenario["db"]
    _visita(db, "V-0001")
    db.commit()
    hallazgos = []
    viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert conteo.integrados == 0
    assert db.query(FactVisita).count() == 1


def test_visita_con_medico_sin_sincronizar_se_omite(escenario):
    """Una referencia sin mapeo NO se resuelve al vuelo: eso es trabajo de la
    sincronización de dimensiones. Se omite y el resto del lote sí entra."""
    db = escenario["db"]
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD99",
                        nombre="Doctor Sin Sincronizar", activo=True))
    db.flush()
    _visita(db, "V-0001")
    _visita(db, "V-0099", medico="MD99")
    db.commit()
    hallazgos = []

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    assert conteo.omitidos == 1
    assert db.query(FactVisita).count() == 1
    assert any(h.severidad == viz.SEVERIDAD_ERROR and h.origen_id == "V-0099"
               for h in hallazgos)


@pytest.fixture
def farmacia(escenario):
    """Una farmacia sincronizada, con su mapeo, lista para recibir hechos."""
    db = escenario["db"]
    maestro = Farmacia(pais_codigo="DO", nombre="Farmacia Central",
                       nombre_completo="FARMACIA CENTRAL", direccion="",
                       encargado="", estado="APROBADA", origen="CONFIG")
    db.add(maestro)
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.flush()
    db.add(MapeoExterno(entidad=ENT_FARMACIA, pais_codigo="DO",
                        codigo_externo="FAR01", id_interno=maestro.id))
    db.commit()
    return {**escenario, "maestro": maestro}


def test_target_farmacia_entra_aprobado(farmacia):
    """Viene del maestro oficial del SFA: no pasa por la cola de aprobación
    VM→GD, que existe para las altas que pide un representante."""
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []

    conteo = viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    panel = db.query(FarmaciaVisita).one()
    assert panel.estado_aprobacion == "APROBADA"
    assert panel.vm_id == farmacia["rm"].id
    assert panel.maestro_farmacia_id == farmacia["maestro"].id


def test_visita_farmacia_entra_sin_usuario_que_la_registro(farmacia):
    """`registrado_por` queda nulo: no la capturó nadie en VISTA."""
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []
    viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()
    db.add(ExtFactVisitaFarmacia(
        lote_id=1001, origen_id="VF-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", farmacia_codigo="FAR01",
        fecha_visita=date(2026, 1, 20), ejecutada=True))
    db.commit()

    conteo = viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    v = db.query(FactVisitaFarmacia).one()
    assert v.registrado_por is None
    assert v.ejecutada is True


def test_reintegrar_no_duplica_visitas_de_farmacia(farmacia):
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.add(ExtFactVisitaFarmacia(
        lote_id=1001, origen_id="VF-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", farmacia_codigo="FAR01",
        fecha_visita=date(2026, 1, 20), ejecutada=True))
    db.commit()
    hallazgos = []
    viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    conteo = viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert db.query(FactVisitaFarmacia).count() == 1
