"""CRITICAL de la revisión final del sub-proyecto 7: EXAMEN_VISTA escribía la
nota en escala 0-10 en `FACT_ResultadoIndicador.resultado_real`, pero
EVAL_CONOCIMIENTOS tiene `escala=100` — el motor usa `resultado_real` DIRECTO,
sin normalizar. Un examen de score 80 debía dar 8 puntos (ponderación 10) y en
cambio daba 0.80: una décima parte de lo que dan CAPTURA_MANUAL/NOTA_EXTERNA
para el MISMO desempeño real.

`test_examen_consolidacion_service.py` monkeypatchea `upsert_nota_rm`, así que
nunca pasa por el motor — este archivo es el que faltaba: afirma sobre
`puntos_obtenidos` atravesando `motor_calculo_service.completar_puntajes` de
verdad, igual que ya hacen `test_conocimientos_captura.py`/
`test_conocimientos_integracion.py` para los otros dos caminos.

Necesita PostgreSQL real.
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
from app.models.exam_models import AsignacionExamen, Examen, IntentoExamen
from app.models.hechos import ResultadoIndicador
from app.models.usuario import Rol, Usuario
from app.services import examen_consolidacion_service as exc
from app.services import fuente_indicador_service as fs
from app.services import motor_calculo_service

BD_PRUEBA = "vista_test_examen_kpi_motor"


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
    except Exception as exc_:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable: {exc_}")
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
    for tabla in ('"exam"."FactConsolidacionCiclo"', '"exam"."FactIntentoExamen"',
                  '"exam"."FactAsignacionExamen"', '"exam"."DimExamen"',
                  # `consolidar_ciclo` dispara `recalculo_service.recalcular_ciclo`
                  # -> `generar_ranking`, que escribe estas tres — sin borrarlas
                  # aquí, el `DELETE FROM DIM_RM` de más abajo revienta por FK en
                  # el siguiente test (mismo `motor`, module-scoped).
                  '"DW"."FACT_RankingGerente"', '"DW"."FACT_RankingRM"',
                  '"DW"."FACT_ScoreIntegralRM"',
                  '"DW"."FACT_ResultadoIndicador"', '"Config"."FuenteIndicador"',
                  '"Security"."DIM_Usuario"', '"Config"."DIM_Indicador"',
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
    usuario_admin = Usuario(username="capacitacion1", hashed_password="x",
                            nombre_completo="Capacitación Uno", rol=Rol.CAPACITACION,
                            activado_en=datetime(2026, 1, 1))
    s.add_all([rm, ciclo, usuario_admin])
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
    yield {"db": s, "rm": rm, "ciclo": ciclo, "linea": linea, "gerente": gerente,
           "ind": indicadores, "usuario": usuario_admin}
    s.close()


def _resultado(e, codigo):
    return (e["db"].query(ResultadoIndicador)
            .filter(ResultadoIndicador.indicador_id == e["ind"][codigo].id,
                    ResultadoIndicador.ciclo_id == e["ciclo"].id).first())


def _examen_con_intento(e, score):
    """Un examen marcado EVAL_CONOCIMIENTOS, con una asignación y un intento
    finalizado del RM del escenario, con el `score` (0-100) dado."""
    db = e["db"]
    examen = Examen(nombre="Examen Cardio", nota_minima=70, estado="publicado",
                    fuente="manual", creado_por_usuario_id=e["usuario"].id,
                    indicador_codigo="EVAL_CONOCIMIENTOS", ciclo_id=e["ciclo"].id)
    db.add(examen)
    db.flush()
    asignacion = AsignacionExamen(examen_id=examen.id, evaluado_tipo="RM",
                                  evaluado_rm_id=e["rm"].id)
    db.add(asignacion)
    db.flush()
    intento = IntentoExamen(asignacion_id=asignacion.id, evaluado_tipo="RM",
                            evaluado_rm_id=e["rm"].id,
                            fecha_fin=datetime(2026, 1, 15, 10, 0),
                            score=Decimal(str(score)), aprobado=score >= 70)
    db.add(intento)
    db.flush()
    return examen


def test_consolidar_atraviesa_el_motor_y_puntua_como_los_otros_caminos(escenario):
    """El corazón del CRITICAL: un examen de score 80 (ponderación 10) debe
    dar 8 puntos — EXACTAMENTE lo mismo que ya prueban
    `test_conocimientos_captura.test_integrar_atraviesa_el_motor_y_puntua` y
    `test_conocimientos_integracion.test_atraviesa_el_motor_y_puntua` para
    CAPTURA_MANUAL/NOTA_EXTERNA con la misma nota real."""
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=e["usuario"].id)
    e["db"].commit()
    _examen_con_intento(e, 80)
    e["db"].commit()

    out = exc.consolidar_ciclo(e["db"], e["ciclo"].id, "DO", e["usuario"].id)

    assert out["abortado"] is False
    assert out["rms_consolidados"] == 1
    # `nota_promedio_equipo` sigue en escala 0-10: es lo que se le muestra al
    # usuario, y NO debe cambiar con este fix (solo cambia lo que entra al KPI).
    assert out["nota_promedio_equipo"] == 8.0

    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()

    fila = _resultado(e, "EVAL_CONOCIMIENTOS")
    # Antes del fix: `resultado_real` == Decimal("8.00") (la nota 0-10) y
    # `puntos_obtenidos` == Decimal("0.8000") — una décima parte de lo debido.
    assert fila.resultado_real == Decimal("80.00")
    assert fila.resultado_porcentaje == Decimal("80.0000")
    assert fila.puntos_obtenidos == Decimal("8.0000")


def test_mismo_desempeno_real_puntua_igual_por_examen_que_por_captura(escenario):
    """Cruce explícito entre los dos caminos: el mismo 80 de desempeño real
    debe dar el mismo `puntos_obtenidos` sin importar si entró por examen o
    por captura manual — antes del fix, examen daba 0.80 y captura daba 8.00
    para el MISMO número."""
    e = escenario
    from app.services import conocimientos_service as cs

    # Camino 1: examen, en DO.
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=e["usuario"].id)
    e["db"].commit()
    _examen_con_intento(e, 80)
    e["db"].commit()
    exc.consolidar_ciclo(e["db"], e["ciclo"].id, "DO", e["usuario"].id)
    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()
    puntos_examen = _resultado(e, "EVAL_CONOCIMIENTOS").puntos_obtenidos

    # Camino 2: captura manual, mismo RM/ciclo — se limpia la fuente y se
    # reintegra sobre el mismo indicador para comparar cabeza a cabeza.
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_CAPTURA_MANUAL, usuario_id=e["usuario"].id)
    e["db"].commit()
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=e["usuario"].id)
    e["db"].commit()
    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()
    puntos_captura = _resultado(e, "EVAL_CONOCIMIENTOS").puntos_obtenidos

    assert puntos_examen == puntos_captura == Decimal("8.0000")
