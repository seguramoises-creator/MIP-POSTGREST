"""Médicos TOP: `es_top` en el panel de visita.

`ext.panelmedico.prioridad` (TOP/REGULAR) es un criterio ortogonal a la
categoría A/B/C/D y a la frecuencia F1/F2 (§11.5 del requerimiento: "marcar
TOP no es marcar categoría A"). Estas pruebas cuidan que la integración
poblé y reafirme `es_top` en cada corrida, sin tocar `categoria` ni
`potencial_prescripcion`.

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
from app.models.visita import (
    FactVisitaFarmacia, FarmaciaVisita, MedicoVisita, VisitaRegistro,
)
from app.services import cobertura_farmacia_service
from app.services import integracion_visitas_service as viz
from app.services import visita_cobertura_service as cob
from app.models.visita import AvisoTopEnviado
from app.models.visita import PlaneacionCiclo
from app.schemas.visita import PlaneacionItem
from app.services import visita_planeacion_service as plan

BD_PRUEBA = "vista_test_medicos_top"


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
    for tabla in ('"Visita"."AvisoTopEnviado"', '"Visita"."PlaneacionEvento"',
                  '"Visita"."PlaneacionCiclo"', '"Visita"."FactVisita"',
                  '"Visita"."DIM_MedicoVisita"', '"Visita"."FactVisitaFarmacia"',
                  '"Visita"."DIM_FarmaciaVisita"',
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


def _panel_ext(db, medico="MD01", prioridad="TOP"):
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo="F1", prioridad=prioridad,
        visitas_programadas=2, activo=True))
    db.flush()


def test_prioridad_top_marca_es_top(escenario):
    db = escenario["db"]
    _panel_ext(db, prioridad="TOP")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is True


def test_prioridad_regular_no_marca(escenario):
    db = escenario["db"]
    _panel_ext(db, prioridad="REGULAR")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is False


def test_prioridad_tolera_la_caja(escenario):
    """El origen ya ha demostrado mandar variaciones de caja."""
    db = escenario["db"]
    _panel_ext(db, prioridad="  top  ")
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is True


def test_dejar_de_ser_top_se_reafirma(escenario):
    """El caso que distingue «reafirmar siempre» de «escribir solo al crear».

    Un médico que era TOP y llega como REGULAR en el siguiente lote debe
    quedar en False: es dato maestro del SFA, no una edición del representante.
    """
    db = escenario["db"]
    _panel_ext(db, prioridad="TOP")
    db.commit()
    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()
    db.query(ExtPanelMedico).one().prioridad = "REGULAR"
    db.commit()

    viz.integrar_panel_medico(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(MedicoVisita).one().es_top is False


def test_medico_de_alta_manual_no_es_top(escenario):
    """Nunca pasa por `ext`: su default debe ser False, no nulo. Si fuera nulo
    y se tratara como TOP, bloquearía la publicación por una ficha que el
    representante creó a mano."""
    db = escenario["db"]
    m = MedicoVisita(vm_id=escenario["rm"].id, nombre_completo="DOCTOR MANUAL")
    db.add(m)
    db.commit()

    assert m.es_top is False


def _medico(db, escenario, nombre, es_top, estado="APROBADO"):
    m = MedicoVisita(vm_id=escenario["rm"].id, nombre_completo=nombre,
                     es_top=es_top, estado_aprobacion=estado, activo=True)
    db.add(m)
    db.flush()
    return m


def _planear(db, escenario, medico, tipo="V", semana=1, dia="Lunes"):
    db.add(PlaneacionCiclo(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                           medico_id=medico.id, tipo_visita=tipo, semana=semana,
                           dia_semana=dia))
    db.flush()


def test_publicar_falla_si_falta_un_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, otro)
    db.commit()

    with pytest.raises(plan.TopSinPlanearError) as exc:
        plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert "DOCTOR TOP" in str(exc.value)
    assert top.id is not None


def test_publicar_ok_si_estan_todos_los_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, top)
    db.commit()

    r = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert r["publicada"] is True


def test_publicar_ok_con_normal_sin_planear(escenario):
    """Distingue «faltan TOP» de «falta el panel entero» (§7.3).

    Un médico normal sin ninguna fila en la planeación NO debe bloquear la
    publicación — solo los TOP la bloquean. Si alguien ampliara el bloqueo a
    cualquier médico sin planear (quitando `m.es_top` del filtro), este test
    debe fallar.
    """
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _medico(db, escenario, "DOCTOR NORMAL", False)  # sin planear, a propósito
    _planear(db, escenario, top)
    db.commit()

    r = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert r["publicada"] is True


def test_un_top_con_alta_pendiente_no_bloquea(escenario):
    """El caso que distingue `cuenta_en_ciclo` de `activo`.

    Un TOP cuya alta el Gerente aún no aprobó NO cuenta en el ciclo: exigir
    planearlo dejaría al representante bloqueado sin poder hacer nada.
    """
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR PENDIENTE", True, estado="PENDIENTE_ALTA")
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, otro)
    db.commit()

    r = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert r["publicada"] is True


def test_resumen_lista_los_top_sin_planear(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    db.commit()

    r = plan.resumen_planeacion(db, escenario["rm"].id, escenario["ciclo"].id)

    assert [x["nombre"] for x in r["top_sin_planear"]] == ["DOCTOR TOP"]


def test_resumen_no_incluye_normal_sin_planear_en_top_sin_planear(escenario):
    """El equivalente en el aviso: un médico normal sin planear no se cuela en
    `top_sin_planear` — la lista es exclusiva de médicos TOP."""
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR NORMAL", False)  # sin planear
    db.commit()

    r = plan.resumen_planeacion(db, escenario["rm"].id, escenario["ciclo"].id)

    assert r["top_sin_planear"] == []


def test_top_planeado_solo_con_vista_avisa_pero_no_bloquea(escenario):
    """§7.3 exige que el TOP esté «incluido» — con V basta para publicar.
    §3.4 dice que no puede terminar sin V y R, así que se avisa."""
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, top, tipo="V")
    db.commit()

    r = plan.resumen_planeacion(db, escenario["rm"].id, escenario["ciclo"].id)
    pub = plan.publicar_planeacion(db, escenario["rm"].id, escenario["ciclo"].id, None)

    assert [x["nombre"] for x in r["top_sin_revisita"]] == ["DOCTOR TOP"]
    assert pub["publicada"] is True


def test_guardar_borrador_nunca_se_bloquea_por_top(escenario):
    """El bloqueo es solo al publicar: el representante guarda cuantas veces quiera."""
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    otro = _medico(db, escenario, "DOCTOR NORMAL", False)
    db.commit()

    n = plan.guardar_planeacion(
        db, escenario["rm"].id, escenario["ciclo"].id,
        [PlaneacionItem(medico_id=otro.id, tipo_visita="V", semana=1, dia_semana="Lunes")],
        None)

    assert n == 1


def _visita_reg(db, escenario, medico, tipo="V"):
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=medico.id, tipo_visita=tipo, ejecutada=True,
                          fecha_hora=datetime(2026, 1, 15, 10, 0)))
    db.flush()


def test_top_sin_visita_sale_en_su_lista(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR TOP", True)
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["top_sin_visita"]] == ["DOCTOR TOP"]
    assert r["top_falta_revisita"] == []


def test_top_con_vista_sin_revisita(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _visita_reg(db, escenario, top, tipo="V")
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert r["top_sin_visita"] == []
    assert [x["nombre"] for x in r["top_falta_revisita"]] == ["DOCTOR TOP"]


def test_medico_normal_no_entra_en_las_listas_top(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR NORMAL", False)
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["sin_visita"]] == ["DOCTOR NORMAL"]
    assert r["top_sin_visita"] == []


def test_visita_no_ejecutada_no_cubre_al_top(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=top.id, tipo_visita="V", ejecutada=False,
                          fecha_hora=datetime(2026, 1, 15, 10, 0)))
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["top_sin_visita"]] == ["DOCTOR TOP"]
