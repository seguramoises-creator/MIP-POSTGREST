"""`ext.factevaluacionconocimiento` -> `EVAL_CONOCIMIENTOS`, promediando por RM.

Sustituye a la opción B del contrato con Mallén: notas externas en vez de los
exámenes de VISTA. Necesita PostgreSQL real.
"""
from datetime import date, datetime
from decimal import Decimal

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
from app.models.hechos import NotaConocimiento, ResultadoIndicador
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimPais, ExtDimRepresentante,
    ExtFactEvaluacionConocimiento,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fs
from app.services import integracion_visitas_service as viz
from app.services import motor_calculo_service

BD_PRUEBA = "vista_test_conoc_ext"


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
    for tabla in ("ext.factevaluacionconocimiento", "ext.controlcarga",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Config"."MapeoExterno"', '"Config"."FuenteIndicador"',
                  # Tarea 2 (revisión final): `test_integrar_todo_ejecuta_
                  # conocimientos` atraviesa `integrar_todo` -> recálculo
                  # completo -> `generar_ranking`, que sí escribe estas tres
                  # tablas (a diferencia de los tests que solo llaman
                  # `completar_puntajes`). Sin borrarlas aquí, el `DELETE FROM
                  # DIM_RM` de más abajo revienta por FK en el siguiente test
                  # del módulo (mismo `motor`, module-scoped).
                  '"DW"."FACT_RankingGerente"', '"DW"."FACT_RankingRM"',
                  '"DW"."FACT_ScoreIntegralRM"',
                  '"DW"."FACT_NotaConocimiento"', '"DW"."FACT_ResultadoIndicador"',
                  '"Config"."DIM_Indicador"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()

    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
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

    s.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                      numero=1, fecha_inicio=date(2026, 1, 1),
                      fecha_fin=date(2026, 1, 31), dias_laborables=20,
                      cerrado=False))
    s.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                              nombre="Representante Uno", activo=True))
    s.add(ExtControlCarga(
        lote_id=3001, sistema_origen="LMS", modulo="CONOCIMIENTOS",
        pais_codigo="DO", ciclo_codigo="C01-2026",
        fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="VALIDADO"))
    s.flush()

    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id)):
        s.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                           codigo_externo=codigo, id_interno=interno))
    s.commit()
    yield {"db": s, "rm": rm, "ciclo": ciclo, "linea": linea,
           "gerente": gerente, "ind": indicadores}
    s.close()


def _resultado(e, codigo):
    return (e["db"].query(ResultadoIndicador)
            .filter(ResultadoIndicador.indicador_id == e["ind"][codigo].id,
                    ResultadoIndicador.ciclo_id == e["ciclo"].id).first())


def _nota_ext(db, origen_id, nota, rm="VM01", lote_id=3001, tema=None):
    db.add(ExtFactEvaluacionConocimiento(
        lote_id=lote_id, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo=rm,
        fecha_evaluacion=date(2026, 1, 15), nota=Decimal(str(nota)), tema=tema))
    db.flush()


def test_promedia_las_notas_del_rm(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 60)
    _nota_ext(e["db"], "N-2", 100)
    e["db"].commit()

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    assert out["rms_integrados"] == 1
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")


def test_atraviesa_el_motor_y_puntua(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()
    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()

    fila = _resultado(e, "EVAL_CONOCIMIENTOS")
    assert fila.resultado_porcentaje == Decimal("80.0000")
    assert fila.puntos_obtenidos == Decimal("8.0000")


def test_se_niega_si_el_pais_no_es_de_notas_externas(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_CAPTURA_MANUAL, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert any(h.severidad == "error" for h in hallazgos)
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_pais_de_otra_fuente_sin_notas_de_mallen_no_genera_hallazgo(escenario):
    """Regresión de la ola anterior: al cablear `integrar_conocimientos` dentro
    de `integrar_todo` (Tarea 2), un país que NO es NOTA_EXTERNA (el default es
    CAPTURA_MANUAL) generaba un `Hallazgo` de error en TODAS las corridas,
    aunque Mallén no hubiera enviado ni una sola fila para ese ciclo. Sin datos
    que integrar no hay nada que avisar — debe devolver el dict de "no
    integrado" en silencio, sin tocar `hallazgos`."""
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_CAPTURA_MANUAL, usuario_id=1)
    # A propósito: NINGUNA fila en ext.factevaluacionconocimiento.
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)

    assert out["abortado"] is False
    assert out["rms_integrados"] == 0
    assert hallazgos == []
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_filas_de_un_lote_no_validado_se_omiten(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ExtControlCarga(
        lote_id=3002, sistema_origen="LMS", modulo="CONOCIMIENTOS",
        pais_codigo="DO", ciclo_codigo="C01-2026",
        fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="RECHAZADO"))
    e["db"].flush()
    _nota_ext(e["db"], "N-9", 99, lote_id=3002)
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
    # Ronda de correcciones 1: sin esto el operador no tenía ninguna pista de
    # que había una fila descartada por el lote, ni por qué estado.
    avisos = [h for h in hallazgos if h.severidad == "aviso"]
    assert len(avisos) == 1
    assert "RECHAZADO" in avisos[0].problema
    assert "1" in avisos[0].problema


def test_nota_fuera_de_rango_se_omite_con_hallazgo(escenario):
    """Ronda de correcciones 1: el camino manual pasa por `_validar_nota`, pero
    el integrador escribía `resultado_real` tal cual. Una nota de 150 debe
    omitirse (no recortarse en silencio) con un hallazgo de error, y el resto
    de las notas válidas del RM sí deben promediarse."""
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 150)
    _nota_ext(e["db"], "N-2", 80)
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 1
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")
    errores = [h for h in hallazgos if h.severidad == "error"]
    assert len(errores) == 1
    assert "150" in errores[0].problema


def test_ciclo_cerrado_no_escribe_ni_borra(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("55"), activo=True))
    _nota_ext(e["db"], "N-1", 90)
    e["ciclo"].cerrado = True
    e["db"].commit()

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    assert out["abortado"] is True
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("55.0000")


def test_reintegrar_no_duplica(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()

    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()
    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["EVAL_CONOCIMIENTOS"].id).all())
    assert len(filas) == 1


def test_integrar_todo_ejecuta_conocimientos(escenario):
    """IMPORTANT de la revisión final: antes de este fix, `integrar_todo` (el
    orquestador por lotes que sí llama Capacitación/el resto de la app) nunca
    invocaba `integrar_conocimientos` — un país declarado NOTA_EXTERNA se
    quedaba SIN NINGUNA vía real de alimentar el indicador: el Excel lo omite
    siempre, exámenes/captura devuelven 409 (fuente ajena), y nadie más lo
    llamaba. Este test prueba el cableado end-to-end vía `integrar_todo`, no
    llamando a `cs.integrar_conocimientos` directo (eso ya lo cubren los tests
    de arriba)."""
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()

    r = viz.integrar_todo(e["db"], "DO", "C01-2026")

    assert r["conocimientos"]["abortado"] is False
    assert r["conocimientos"]["rms_integrados"] == 1
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")
    # Un solo recálculo al final del lote (no uno por integrador): la salida
    # de `integrar_todo` solo tiene una clave "recalculo".
    assert r["recalculo"]["abortado"] is False


def test_integrar_todo_no_pisa_un_pais_de_otra_fuente(escenario):
    """El país sigue protegido dentro del orquestador por lotes: si es de
    CAPTURA_MANUAL (o EXAMEN_VISTA), `integrar_todo` no debe escribir el
    indicador aunque `ext` traiga notas de Mallén — el `Hallazgo` lo explica,
    no una excepción que tumbaría el resto del lote (ventas, visitas...)."""
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_CAPTURA_MANUAL, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()

    r = viz.integrar_todo(e["db"], "DO", "C01-2026")

    assert r["conocimientos"]["abortado"] is True
    assert r["conocimientos"]["motivo"] == "fuente_ajena"
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
    assert any(h["hecho"] == "factevaluacionconocimiento" and h["severidad"] == "error"
               for h in r["hallazgos"])


def test_integrar_todo_sin_notas_de_mallen_no_genera_falsa_alarma(escenario):
    """El mismo caso que motivó la corrección, pero atravesando `integrar_todo`
    (el punto donde realmente se manifestaba: antes de cablearla, nadie la
    llamaba, así que la falsa alarma nunca se veía). Un país CAPTURA_MANUAL
    (el default) sin ninguna fila de Mallén no debe dejar ningún `Hallazgo`
    de `factevaluacionconocimiento`, y el resto de la corrida sigue normal."""
    e = escenario
    # Fuente por defecto (CAPTURA_MANUAL) — ni siquiera se fija a mano.
    # A propósito: NINGUNA fila en ext.factevaluacionconocimiento.

    r = viz.integrar_todo(e["db"], "DO", "C01-2026")

    assert r["conocimientos"]["abortado"] is False
    assert r["conocimientos"]["rms_integrados"] == 0
    assert not any(h["hecho"] == "factevaluacionconocimiento" for h in r["hallazgos"])
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
    # El resto de la corrida no se vio afectado.
    assert r["recalculo"]["abortado"] is False


def test_rm_sin_mapeo_se_omite_con_hallazgo_y_el_resto_entra(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                                    nombre="Sin mapear", activo=True))
    e["db"].flush()
    _nota_ext(e["db"], "N-1", 80)
    _nota_ext(e["db"], "N-9", 10, rm="VM99")
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 1
    assert any(h.severidad == "error" for h in hallazgos)
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")
