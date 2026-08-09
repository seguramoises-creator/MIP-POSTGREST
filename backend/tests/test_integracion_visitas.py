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
from app.services import cobertura_farmacia_service
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
                       encargado="", estado="ACTIVA", origen="CONFIG")
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
    assert panel.estado_aprobacion == "APROBADO"
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


def test_target_farmacia_integrado_es_visible_en_cobertura(farmacia):
    """El valor de `estado_aprobacion` que escribe la integración debe ser el
    mismo que filtra `cobertura_farmacia_service` («APROBADO», masculino) — un
    `assert estado_aprobacion == "APROBADO"` en el test anterior solo compara la
    constante contra sí misma y no habría detectado el valor mal escrito
    («APROBADA»). Este test cruza el dato con el consumidor real."""
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []

    viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    resultado = cobertura_farmacia_service.cobertura_rm(
        db, farmacia["rm"].id, farmacia["ciclo"].id)
    assert resultado["universo"] > 0


def test_target_farmacia_adopta_panel_pendiente_de_alta(farmacia):
    """Si el VM ya había solicitado esa farmacia a mano, el panel existe en
    PENDIENTE_ALTA. `mapeo.resolver` lo ADOPTA (mismo id, no lo duplica), y la
    integración debe reafirmar APROBADO en ese camino también — no solo al
    crear — porque el SFA es maestro oficial y no pasa por la cola VM→GD."""
    db = farmacia["db"]
    panel_previo = FarmaciaVisita(
        vm_id=farmacia["rm"].id, maestro_farmacia_id=farmacia["maestro"].id,
        estado_aprobacion="PENDIENTE_ALTA", activo=True,
        motivo="Dirección no verificable")
    db.add(panel_previo)
    db.commit()
    panel_id = panel_previo.id

    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []

    conteo = viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(FarmaciaVisita).count() == 1
    panel = db.query(FarmaciaVisita).one()
    assert panel.id == panel_id
    assert panel.estado_aprobacion == "APROBADO"
    # El motivo del rechazo anterior se limpia: un panel aprobado que conserva
    # el texto del rechazo lo sigue mostrando en el panel del VM.
    assert panel.motivo is None
    assert conteo.integrados == 0


def test_integrar_todo_corre_los_cuatro_hechos(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["ciclo_codigo"] == "C01-2026"
    assert [h["hecho"] for h in r["hechos"]] == [
        "panelmedico", "factvisitamedico", "targetfarmacia", "factvisitafarmacia"]
    panel = next(h for h in r["hechos"] if h["hecho"] == "panelmedico")
    assert panel["integrados"] == 1


def test_integrar_todo_es_idempotente(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    r = viz.integrar_todo(db, "DO", "C01-2026")

    visitas = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert visitas["integrados"] == 0
    assert visitas["actualizados"] == 1
    assert db.query(FactVisita).count() == 1


def test_resumen_cuenta_ext_y_integradas(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    filas = viz.resumen_visitas(db, "DO", "C01-2026")

    v = next(f for f in filas if f["hecho"] == "factvisitamedico")
    assert v["en_ext"] == 1
    assert v["integradas"] == 1


def test_resumen_no_mezcla_ciclos_del_mismo_pais(farmacia):
    """El defecto que esto reproduce: `MapeoExterno` no tiene columna
    `ciclo_codigo`, así que `integradas` contaba TODOS los mapeos del país sin
    filtrar por ciclo. Integrar un segundo ciclo (mismo país, mismo RM/médico
    ya sincronizados) NO debe cambiar el resumen del primero — un test con un
    solo ciclo no lo habría detectado, que es justo por qué se coló."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    resumen_c01_antes = viz.resumen_visitas(db, "DO", "C01-2026")

    # Segundo ciclo del mismo país, con su propio panel y visita.
    ciclo2 = Ciclo(pais_codigo="DO", anio=2026, numero=2, nombre="Ciclo 2",
                   fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28),
                   dias_laborables=20, cerrado=False)
    db.add(ciclo2)
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C02-2026", anio=2026,
                       numero=2, fecha_inicio=date(2026, 2, 1),
                       fecha_fin=date(2026, 2, 28), dias_laborables=20,
                       cerrado=False))
    db.add(MapeoExterno(entidad=ENT_CICLO, pais_codigo="DO",
                        codigo_externo="C02-2026", id_interno=ciclo2.id))
    db.add(ExtControlCarga(
        lote_id=1002, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C02-2026", fecha_extraccion=datetime(2026, 2, 28, 20, 0),
        fecha_recepcion=datetime(2026, 2, 28, 21, 0), filas_enviadas=2,
        estado="VALIDADO"))
    db.add(ExtPanelMedico(
        lote_id=1002, pais_codigo="DO", ciclo_codigo="C02-2026", rm_codigo="VM01",
        medico_codigo="MD01", frecuencia_objetivo="F1", prioridad="TOP",
        visitas_programadas=2, activo=True))
    db.add(ExtFactVisitaMedico(
        lote_id=1002, origen_id="V-0002", pais_codigo="DO",
        ciclo_codigo="C02-2026", rm_codigo="VM01", medico_codigo="MD01",
        fecha_visita=date(2026, 2, 15), tipo_visita="V", ejecutada=True,
        acompanado=False))
    db.commit()

    viz.integrar_todo(db, "DO", "C02-2026")

    resumen_c01_despues = viz.resumen_visitas(db, "DO", "C01-2026")
    resumen_c02 = viz.resumen_visitas(db, "DO", "C02-2026")

    for hecho in ("panelmedico", "factvisitamedico"):
        antes = next(f for f in resumen_c01_antes if f["hecho"] == hecho)
        despues = next(f for f in resumen_c01_despues if f["hecho"] == hecho)
        assert despues == antes, (
            f"integrar C02-2026 no debe alterar el resumen de C01-2026 ({hecho})")

    panel_c02 = next(f for f in resumen_c02 if f["hecho"] == "panelmedico")
    visita_c02 = next(f for f in resumen_c02 if f["hecho"] == "factvisitamedico")
    assert panel_c02["en_ext"] == 1
    assert panel_c02["integradas"] == 1
    assert visita_c02["en_ext"] == 1
    assert visita_c02["integradas"] == 1


def test_resumen_integradas_iguala_en_ext_y_baja_con_omitidos(escenario):
    """Cuando todo se integra bien, `integradas` coincide con `en_ext`. Si una
    fila se omite por falta de dimensión (médico sin sincronizar), no entra a
    `MapeoExterno` y `integradas` debe quedar por debajo de `en_ext`."""
    db = escenario["db"]
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD99",
                        nombre="Doctor Sin Sincronizar", activo=True))
    db.flush()
    _visita(db, "V-0001")
    _visita(db, "V-0099", medico="MD99")
    db.commit()
    hallazgos = []

    viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    filas = viz.resumen_visitas(db, "DO", "C01-2026")
    v = next(f for f in filas if f["hecho"] == "factvisitamedico")
    assert v["en_ext"] == 2
    assert v["integradas"] == 1
    assert v["integradas"] < v["en_ext"]


def test_integrar_dispara_el_recalculo_del_score(farmacia):
    """§7.1 paso 3: sin esto, integrar no movería el Score ni el ranking.

    Se comprueba sobre la salida del motor, no sobre un mock: `recalculo`
    trae el dict real de `recalculo_service.recalcular_ciclo`.
    """
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["recalculo"]["abortado"] is False
    assert "rankings_generados" in r["recalculo"]


def test_ciclo_cerrado_integra_los_hechos_pero_aborta_el_recalculo(farmacia):
    """Un ciclo cerrado es un snapshot histórico: los hechos entran, el Score
    no se toca. El guard vive en `recalculo_service`, no se duplica aquí."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    farmacia["ciclo"].cerrado = True
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["recalculo"]["abortado"] is True
    assert db.query(FactVisita).count() == 1   # los hechos SÍ entraron
    # …pero nada calculado se tocó: el motor de indicadores se abstuvo solo.
    assert r["indicadores"]["omitido_ciclo_cerrado"] is True


def test_lote_validado_pasa_a_integrado(farmacia):
    """§7.1 paso 4. Hasta ahora nadie escribía INTEGRADO."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == [1001]
    lote = db.query(ExtControlCarga).filter_by(lote_id=1001).one()
    assert lote.estado == "INTEGRADO"
    assert "factvisitamedico" in lote.mensaje


def test_lote_rechazado_no_se_rescata(farmacia):
    """Un lote que la validación rechazó no llega a INTEGRADO por el hecho de
    que la integración recorra sus filas."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "RECHAZADO"
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == []
    assert db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado == "RECHAZADO"


def test_reintegrar_no_revierte_el_estado_del_lote(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == []          # ya estaba cerrado
    assert db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado == "INTEGRADO"


# ===========================================================================
# DEFECTO 1 (CRITICAL) — un lote no VALIDADO/INTEGRADO no debe integrarse.
# ===========================================================================

def test_lote_rechazado_omite_las_filas_con_hallazgo(farmacia):
    """Ningún integrador miraba `ExtControlCarga.estado`: un lote RECHAZADO por
    la validación del sub-proyecto 1 se integraba igual. Ahora las filas de un
    lote que no está en VALIDADO/INTEGRADO se omiten con un hallazgo de
    severidad error, y ni `DIM_TargetMedico` ni `FACT_Visita` reciben nada."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "RECHAZADO"
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    panel = next(h for h in r["hechos"] if h["hecho"] == "panelmedico")
    visita = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert panel["integrados"] == 0
    assert panel["omitidos"] == 1
    assert visita["integrados"] == 0
    assert visita["omitidos"] == 1
    assert db.query(TargetMedico).count() == 0
    assert db.query(FactVisita).count() == 0
    assert any(h["severidad"] == viz.SEVERIDAD_ERROR and "RECHAZADO" in h["problema"]
               for h in r["hallazgos"])
    assert r["lotes_cerrados"] == []
    assert db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado == "RECHAZADO"


def test_lote_validado_si_integra_normalmente(farmacia):
    """Camino normal: un lote VALIDADO sigue integrando sus filas exactamente
    como antes — el guard del DEFECTO 1 no debe bloquear el flujo sano."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    assert (db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado
            == "VALIDADO")

    r = viz.integrar_todo(db, "DO", "C01-2026")

    panel = next(h for h in r["hechos"] if h["hecho"] == "panelmedico")
    visita = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert panel["integrados"] == 1
    assert visita["integrados"] == 1
    assert r["lotes_cerrados"] == [1001]


def test_lote_con_estado_en_minuscula_tambien_integra(farmacia):
    """El estado se compara tolerante a caja (`.strip().upper()`), igual que ya
    hacía el guard de cierre de lote original: el origen puede mandar
    variaciones de caja en el estado."""
    db = farmacia["db"]
    _panel(db)
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "validado"
    db.commit()

    conteo = viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert conteo.integrados == 1
    assert conteo.omitidos == 0


# ===========================================================================
# DEFECTO 2 (IMPORTANT) — claves de MapeoExterno.codigo_externo que desbordan
# String(60) se omiten, no tumban la corrida.
# ===========================================================================

def test_panel_medico_clave_larga_se_omite_no_trunca(escenario):
    """La clave `ciclo/rm/medico` puede superar los 60 caracteres de
    `MapeoExterno.codigo_externo`. Antes de la corrección esto tumbaba TODA la
    corrida con un DataError de PostgreSQL (rollback del ciclo completo); ahora
    la fila se omite con un hallazgo y el resto del lote entra normalmente.

    El representante se mapea a mano (como haría el sub-proyecto 2) para que
    la fila llegue hasta la construcción de la clave de `MapeoExterno` en vez
    de omitirse antes por falta de sincronización — si no, el test no
    ejercería el desbordamiento que reproduce el defecto.
    """
    db = escenario["db"]
    rm_largo = "RM" + "9" * 28       # 30 chars: el máximo de dimrepresentante
    medico_largo = "MD" + "8" * 38   # 40 chars: el máximo de dimmedico
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo=rm_largo,
                               nombre="Representante Largo", activo=True))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo=medico_largo,
                        nombre="Doctor Largo", activo=True))
    db.flush()
    db.add(MapeoExterno(entidad=ENT_REPRESENTANTE, pais_codigo="DO",
                        codigo_externo=rm_largo, id_interno=escenario["rm"].id))
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo=rm_largo, medico_codigo=medico_largo,
        frecuencia_objetivo="F1", prioridad="TOP", visitas_programadas=2,
        activo=True))
    _panel(db)  # una fila normal (MD01) que sí debe entrar
    db.commit()
    hallazgos = []

    conteo = viz.integrar_panel_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1   # la fila normal sí entró
    assert conteo.omitidos == 1     # la de clave larga se omitió, no rompió nada
    assert db.query(TargetMedico).count() == 1
    assert any(h.severidad == viz.SEVERIDAD_ERROR and "60 caracteres" in h.problema
               for h in hallazgos)


# ===========================================================================
# DEFECTO 3 (IMPORTANT) — `_cerrar_lotes` solo marca INTEGRADO si el lote
# aportó filas Y no le quedan filas de otro ciclo.
# ===========================================================================

def test_lote_sigue_validado_si_no_integro_ninguna_fila(escenario):
    """Sin dimensiones sincronizadas, todas las filas del lote se omiten (0
    integradas). El lote NO debe pasar a INTEGRADO: antes quedaba marcado
    igual, con «0 nuevas, 0 actualizadas» en el mensaje, y como `validar_lote`
    (sub-proyecto 1) rechaza re-validar un lote INTEGRADO, quedaba muerto."""
    db = escenario["db"]
    # Un médico que existe en `ext` pero SIN mapeo (dimensión no sincronizada).
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD99",
                        nombre="Doctor Sin Sincronizar", activo=True))
    db.flush()
    _visita(db, "V-0001", medico="MD99")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    visita = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert visita["integrados"] == 0
    assert visita["omitidos"] == 1
    assert r["lotes_cerrados"] == []
    lote = db.query(ExtControlCarga).filter_by(lote_id=1001).one()
    assert lote.estado == "VALIDADO"


def test_lote_no_se_cierra_si_tiene_filas_de_otro_ciclo(farmacia):
    """Un mismo lote puede traer filas de más de un ciclo (p. ej. un corte de
    mes a mitad del envío). Integrar solo el ciclo actual no debe cerrar el
    lote — las filas del otro ciclo quedarían huérfanas y, como el lote ya
    estaría INTEGRADO, ni siquiera se podrían re-validar."""
    db = farmacia["db"]
    _visita(db, "V-0001")   # ciclo C01-2026, lote 1001

    # Un segundo ciclo, sincronizado, con una fila del MISMO lote 1001.
    ciclo2 = Ciclo(pais_codigo="DO", anio=2026, numero=2, nombre="Ciclo 2",
                  fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28),
                  dias_laborables=20, cerrado=False)
    db.add(ciclo2)
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C02-2026", anio=2026,
                       numero=2, fecha_inicio=date(2026, 2, 1),
                       fecha_fin=date(2026, 2, 28), dias_laborables=20,
                       cerrado=False))
    db.add(MapeoExterno(entidad=ENT_CICLO, pais_codigo="DO",
                        codigo_externo="C02-2026", id_interno=ciclo2.id))
    db.add(ExtFactVisitaMedico(
        lote_id=1001, origen_id="V-0002", pais_codigo="DO",
        ciclo_codigo="C02-2026", rm_codigo="VM01", medico_codigo="MD01",
        fecha_visita=date(2026, 2, 15), tipo_visita="V", ejecutada=True,
        acompanado=False))
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    visita = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert visita["integrados"] == 1              # la fila de C01-2026 sí integró
    assert db.query(FactVisita).count() == 1
    assert r["lotes_cerrados"] == []               # pero el lote no se cierra
    lote = db.query(ExtControlCarga).filter_by(lote_id=1001).one()
    assert lote.estado == "VALIDADO"


# ===========================================================================
# DEFECTO 4 (MINOR) — visita a farmacia fuera de target: aviso, no error.
# ===========================================================================

def test_visita_farmacia_fuera_de_target_es_aviso_no_error(farmacia):
    """Una visita a una farmacia que no está en el target del ciclo es ruido
    normal (un VM puede visitar una farmacia no programada), no un error de
    integración: la severidad baja de `error` a `aviso`."""
    db = farmacia["db"]
    db.add(ExtFactVisitaFarmacia(
        lote_id=1001, origen_id="VF-0099", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", farmacia_codigo="FAR01",
        fecha_visita=date(2026, 1, 20), ejecutada=True))
    db.commit()
    hallazgos = []

    conteo = viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 0
    assert conteo.omitidos == 1
    assert db.query(FactVisitaFarmacia).count() == 0
    h = next(h for h in hallazgos if h.origen_id == "VF-0099")
    assert h.severidad == viz.SEVERIDAD_AVISO
