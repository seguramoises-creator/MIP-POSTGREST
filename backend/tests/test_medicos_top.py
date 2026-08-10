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
from app.services import visita_top_service as top
from app.models.dimensiones import (
    Ciclo, Farmacia, Gerente, Linea, Medico, Pais, RepresentanteMedico, TargetMedico,
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
                  '"Config"."DIM_Gerente"',
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
    # Gerente de Distrito por defecto: la Tarea 5 (avisos de médicos TOP) escala
    # al gerente del RM, así que el escenario base ya trae uno con correo. El
    # test que necesita el caso "sin gerente" lo anula explícitamente (rm.gerente_id = None).
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="gerente@ejemplo.com", tipo="DISTRITO")
    db.add(gerente)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gerente.id,
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
    # Las listas TOP son un SUBCONJUNTO, no un reemplazo: el TOP tiene que
    # seguir contando en la lista general. Sin este assert, sacarlo de
    # `sin_visita` no haría fallar ningún test.
    assert "DOCTOR TOP" in [x["nombre"] for x in r["sin_visita"]]


def test_top_con_vista_sin_revisita(escenario):
    db = escenario["db"]
    top = _medico(db, escenario, "DOCTOR TOP", True)
    _visita_reg(db, escenario, top, tipo="V")
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert r["top_sin_visita"] == []
    assert [x["nombre"] for x in r["top_falta_revisita"]] == ["DOCTOR TOP"]
    # Subconjunto, no reemplazo (ver el test anterior).
    assert "DOCTOR TOP" in [x["nombre"] for x in r["falta_revisita"]]


def test_medico_normal_no_entra_en_las_listas_top(escenario):
    db = escenario["db"]
    _medico(db, escenario, "DOCTOR NORMAL", False)
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["sin_visita"]] == ["DOCTOR NORMAL"]
    assert r["top_sin_visita"] == []


def test_visita_no_ejecutada_no_cubre_al_top(escenario):
    db = escenario["db"]
    top_medico = _medico(db, escenario, "DOCTOR TOP", True)
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=top_medico.id, tipo_visita="V", ejecutada=False,
                          fecha_hora=datetime(2026, 1, 15, 10, 0)))
    db.commit()

    r = cob.resumen_cobertura(db, ciclo_id=escenario["ciclo"].id, vm_id=escenario["rm"].id)

    assert [x["nombre"] for x in r["top_sin_visita"]] == ["DOCTOR TOP"]


def test_fecha_planeada_semana_1_lunes(escenario):
    """El ciclo empieza el jueves 1-ene-2026. La semana 1 es la que CONTIENE
    fecha_inicio, así que su lunes es el 29-dic — anterior al ciclo. La fecha
    se acota a fecha_inicio: no se puede planear antes de que el ciclo empiece."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 1, "Lunes") == date(2026, 1, 1)


def test_fecha_planeada_semana_2_miercoles(escenario):
    """Lunes de la semana 1 = 29-dic-2025; semana 2 = +7 días = 5-ene;
    miércoles = +2 = 7-ene-2026."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 2, "Miércoles") == date(2026, 1, 7)


def test_fecha_planeada_se_acota_al_fin_del_ciclo(escenario):
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 40, "Viernes") == c.fecha_fin


def test_fecha_planeada_dia_irreconocible_es_none(escenario):
    """Un dato de planeación incompleto no debe generar un correo de reclamo."""
    c = escenario["ciclo"]
    assert top.fecha_planeada(c, 1, None) is None
    assert top.fecha_planeada(c, 1, "Cualquiera") is None


def test_recordatorio_respeta_los_dias_de_gracia(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")   # 1-ene-2026
    db.commit()

    # 2-ene: solo 1 día hábil transcurrido, con gracia de 2 no toca avisar
    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 2), 2) == []
    # 6-ene: ya pasaron 3 días hábiles desde el 2 (2, 5 y 6; el 3 y 4 son fin
    # de semana), así que supera la gracia de 2
    r = top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 6), 2)
    assert [x["medico"] for x in r] == ["DOCTOR TOP"]


def test_recordatorio_no_incluye_lo_ya_visitado(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    _visita_reg(db, escenario, t, tipo="V")
    db.commit()

    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 20), 2) == []


def test_recordatorio_ignora_a_los_no_top(escenario):
    db = escenario["db"]
    n = _medico(db, escenario, "DOCTOR NORMAL", False)
    _planear(db, escenario, n, tipo="V", semana=1, dia="Lunes")
    db.commit()

    assert top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 20), 2) == []


def test_recordatorio_ignora_visita_no_ejecutada(escenario):
    """Restricción central: solo las EJECUTADAS cuentan como cobertura. Una fila
    de `FactVisita` con `ejecutada=False` (no-visita con causa) no puede tapar
    a un TOP vencido — si lo hiciera, el representante nunca recibiría el
    recordatorio pese a no haberlo visitado de verdad."""
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")   # 1-ene-2026
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=t.id, tipo_visita="V", ejecutada=False,
                          fecha_hora=datetime(2026, 1, 1, 10, 0)))
    db.commit()

    r = top.pendientes_recordatorio(db, escenario["ciclo"], date(2026, 1, 6), 2)

    assert [x["medico"] for x in r] == ["DOCTOR TOP"]


def test_escalamiento_ignora_visita_no_ejecutada(escenario):
    """Mismo principio que arriba, del lado de escalamiento: una no-visita con
    causa no debe sacar al TOP de la lista que ve el Gerente de Distrito."""
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.add(VisitaRegistro(vm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                          medico_id=t.id, tipo_visita="V", ejecutada=False,
                          fecha_hora=datetime(2026, 1, 1, 10, 0)))
    db.commit()

    r = top.pendientes_escalamiento(db, escenario["ciclo"])

    assert [x["medico"] for x in r] == ["DOCTOR TOP"]


def test_pct_ciclo_transcurrido(escenario):
    """Ciclo 1-ene a 31-ene-2026: 22 días hábiles. Al 15-ene han pasado 11."""
    db = escenario["db"]
    assert top.pct_ciclo_transcurrido(db, escenario["ciclo"], date(2026, 1, 15)) == 50


def test_escalamiento_solo_para_top_sin_cubrir(escenario):
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    cubierto = _medico(db, escenario, "DOCTOR CUBIERTO", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    _planear(db, escenario, cubierto, tipo="V", semana=1, dia="Lunes")
    _visita_reg(db, escenario, cubierto, tipo="V")
    db.commit()

    r = top.pendientes_escalamiento(db, escenario["ciclo"])

    assert [x["medico"] for x in r] == ["DOCTOR TOP"]


from app.models.visita import AVISO_ESCALAMIENTO, AVISO_RECORDATORIO


def test_procesar_avisos_registra_y_no_repite(escenario, monkeypatch):
    """El test que justifica la tabla `AvisoTopEnviado`: sin ella, el cron
    diario reenviaría el mismo correo cada mañana."""
    db = escenario["db"]
    enviados = []
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: (enviados.append(a) or True))
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r1 = top.procesar_avisos(db, hoy=date(2026, 1, 20))
    r2 = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r1["recordatorios"] == 1
    assert r2["recordatorios"] == 0          # no se repite
    assert len(enviados) == 1
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_RECORDATORIO).count() == 1


def test_no_registra_si_el_correo_no_salio(escenario, monkeypatch):
    """Marcar como enviado lo que no salió dejaría al representante sin aviso
    para siempre, en silencio."""
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: False)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r["recordatorios"] == 0
    assert db.query(AvisoTopEnviado).count() == 0


def test_ciclo_cerrado_no_genera_avisos(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    escenario["ciclo"].cerrado = True
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert r["recordatorios"] == 0
    assert db.query(AvisoTopEnviado).count() == 0


def test_escalamiento_solo_pasado_el_umbral(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_escalado",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    # 15-ene = 50% del ciclo, por debajo del umbral de 70
    r_antes = top.procesar_avisos(db, hoy=date(2026, 1, 15))
    # 28-ene ya supera el 70%
    r_despues = top.procesar_avisos(db, hoy=date(2026, 1, 28))

    assert r_antes["escalamientos"] == 0
    assert r_despues["escalamientos"] == 1
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_ESCALAMIENTO).count() == 1


def test_representante_sin_gerente_no_tumba_el_job(escenario, monkeypatch):
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    escenario["rm"].gerente_id = None
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 28))

    assert r["escalamientos"] == 0
    assert r["recordatorios"] == 1   # el recordatorio al RM sí sale


def test_gerente_sin_correo_no_tumba_el_job(escenario, monkeypatch):
    """Distinto de «sin gerente»: el gerente existe pero no tiene correo.

    Sin este test, quitar el guard `not g.email` no haría fallar nada y el job
    intentaría escalar a un destinatario vacío.
    """
    db = escenario["db"]
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda *a, **k: True)
    escenario["rm"].email = "rm@ejemplo.com"
    db.query(Gerente).filter(Gerente.id == escenario["rm"].gerente_id).one().email = None
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 28))

    assert r["escalamientos"] == 0
    assert r["recordatorios"] == 1
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_ESCALAMIENTO).count() == 0


def test_un_solo_correo_agrupa_a_todos_los_medicos_del_representante(escenario, monkeypatch):
    """Se agrupa por destinatario: un correo por representante con TODOS sus
    médicos pendientes, no uno por médico.

    Sin este test, mandar un correo por cada médico pendiente pasaría
    inadvertido — y con un panel real serían decenas al mismo buzón.
    """
    db = escenario["db"]
    llamadas = []
    monkeypatch.setattr(
        "app.services.notification_service.notificar_top_pendiente",
        lambda destinatario, nombre, medicos: (llamadas.append(medicos) or True))
    escenario["rm"].email = "rm@ejemplo.com"
    for nombre in ("DOCTOR TOP UNO", "DOCTOR TOP DOS", "DOCTOR TOP TRES"):
        m = _medico(db, escenario, nombre, True)
        _planear(db, escenario, m, tipo="V", semana=1, dia="Lunes")
    db.commit()

    r = top.procesar_avisos(db, hoy=date(2026, 1, 20))

    assert len(llamadas) == 1            # UN correo, no tres
    assert len(llamadas[0]) == 3         # con los tres médicos dentro
    assert r["recordatorios"] == 3
    assert db.query(AvisoTopEnviado).filter_by(tipo_aviso=AVISO_RECORDATORIO).count() == 3


def test_una_visita_no_cubre_una_revisita_planeada(escenario):
    """El emparejamiento es por (medico_id, tipo_visita): una Revisita planeada
    solo la cubre una Revisita ejecutada.

    Sin este test, simplificar la clave a solo `medico_id` no haría fallar nada
    — y una V ejecutada taparía silenciosamente la R que falta, que es justo lo
    que el §3.4 del requerimiento no permite dejar pasar en un médico TOP.
    """
    db = escenario["db"]
    t = _medico(db, escenario, "DOCTOR TOP", True)
    _planear(db, escenario, t, tipo="R", semana=2, dia="Martes")
    _visita_reg(db, escenario, t, tipo="V")   # ejecutó la Visita, no la Revisita
    db.commit()

    r = top.pendientes_escalamiento(db, escenario["ciclo"])

    assert [(x["medico"], x["tipo_visita"]) for x in r] == [("DOCTOR TOP", "R")]
