"""Ranking de Formación (§8) — cálculo de puntos por ciclo.

Necesita PostgreSQL real: el cálculo cruza cuatro esquemas (formacion, exam, DW,
Config) con joins y rangos de fecha; probarlo con dobles verificaría los dobles.
Si no hay base alcanzable se salta, como el resto de pruebas del módulo.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import (
    CapacitacionDim, Ciclo, Linea, Pais, RepresentanteMedico,
)
from app.models.exam_models import AsignacionExamen, Examen, IntentoExamen
from app.models.formacion import (
    ParametroFormacion, RankingFormacionPuntos, RefuerzoCampana, RefuerzoCapsula,
    RefuerzoRespuesta, RefuerzoRondaProgramada,
)
from app.models.hechos import CapacitacionFact
from app.models.usuario import Rol, Usuario
from app.services import formacion_ranking_service as ranking

BD_PRUEBA = "vista_test_ranking_form"


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
    # Cada prueba parte de cero en las tablas que toca.
    for tabla in ('formacion."RankingFormacionPuntos"',
                  'formacion."RefuerzoRespuesta"', 'formacion."RefuerzoCapsula"',
                  'formacion."RefuerzoRondaProgramada"', 'formacion."RefuerzoCampana"',
                  'formacion."ParametroFormacion"',
                  'exam."FactIntentoExamen"', 'exam."FactAsignacionExamen"',
                  'exam."DimExamen"', '"DW"."FACT_Capacitacion"',
                  '"Config"."DIM_Capacitacion"', '"Security"."DIM_Usuario"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Un RM con un punto de cada fuente, dentro del ciclo 1.

    El ciclo 2 existe para probar la atribución por fecha: lo que caiga en él no
    debe sumar al ciclo 1.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    db.add(rm)
    c1 = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
               fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31))
    c2 = Ciclo(pais_codigo="DO", anio=2026, numero=2, nombre="Ciclo 2",
               fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28))
    db.add_all([c1, c2])
    db.flush()

    # 1 certificación aprobada en el ciclo 1. Ojo: `CapacitacionDim` NO lleva
    # pais_codigo (es un catálogo global); el país vive en el hecho.
    cert = CapacitacionDim(codigo="CERT1", nombre="Certificación Cardio",
                           tipo="CERTIFICACION")
    db.add(cert)
    db.flush()
    db.add(CapacitacionFact(pais_codigo="DO", rm_id=rm.id, capacitacion_id=cert.id,
                            ciclo_id=c1.id, asistio=True, aprobado=True))

    # 1 examen aprobado terminado dentro del ciclo 1. `Examen` exige autor
    # (`creado_por_usuario_id` es NOT NULL), así que hace falta un usuario.
    autor = Usuario(username="capacitacion_test", hashed_password="x",
                    nombre_completo="Capacitación de Prueba", rol=Rol.CAPACITACION)
    db.add(autor)
    db.flush()
    examen = Examen(nombre="Examen Cardio", estado="publicado",
                    creado_por_usuario_id=autor.id)
    db.add(examen)
    db.flush()
    asig = AsignacionExamen(examen_id=examen.id, evaluado_tipo="RM",
                            evaluado_rm_id=rm.id, estado="entregado")
    db.add(asig)
    db.flush()
    db.add(IntentoExamen(asignacion_id=asig.id, evaluado_tipo="RM",
                         evaluado_rm_id=rm.id, fecha_inicio=datetime(2026, 1, 10, 9, 0),
                         fecha_fin=datetime(2026, 1, 10, 10, 0), score=90, aprobado=True))

    # Refuerzo: campaña del ciclo 1 con una respuesta de 8 puntos.
    campana = RefuerzoCampana(pais_codigo="DO", nombre="Campaña 1", ciclo_id=c1.id,
                             duracion_dias=30, modo_espaciado="creciente")
    db.add(campana)
    db.flush()
    ronda = RefuerzoRondaProgramada(campana_id=campana.id, numero_ronda=1,
                                    fecha_hora_sugerida=datetime(2026, 1, 5, 9, 0),
                                    publicada=True)
    db.add(ronda)
    db.flush()
    capsula = RefuerzoCapsula(ronda_id=ronda.id, formato="microlectura",
                              enunciado="Lee esto", orden=1)
    db.add(capsula)
    db.flush()
    db.add(RefuerzoRespuesta(
        ronda_id=ronda.id, capsula_id=capsula.id, rm_id=rm.id,
        timestamp_recibido=datetime(2026, 1, 5, 9, 0),
        timestamp_respondido=datetime(2026, 1, 5, 9, 2),
        tiempo_respuesta_seg=120, puntos_obtenidos=8))
    db.commit()
    return {"db": db, "rm": rm, "c1": c1, "c2": c2, "linea": linea,
            "examen": examen, "asignacion": asig}


def test_calcula_los_cuatro_componentes(escenario):
    """Certificación 50 + examen 30 + refuerzo 8 + onboarding 0 = 88."""
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    p = ranking.pesos(db, "DO")

    r = ranking.calcular_componentes(db, rm.id, c1, p)

    assert r["puntos_certificacion"] == 50
    assert r["puntos_examenes"] == 30
    assert r["puntos_refuerzo"] == 8
    assert r["puntos_onboarding"] == 0
    assert r["puntos_total"] == 88


def test_examen_fuera_del_ciclo_no_suma(escenario):
    """La atribución es por fecha: un intento terminado en el ciclo 2 no cuenta
    en el ciclo 1, aunque sea del mismo RM."""
    db, rm, c1, c2 = (escenario["db"], escenario["rm"],
                      escenario["c1"], escenario["c2"])
    db.add(IntentoExamen(asignacion_id=escenario["asignacion"].id, evaluado_tipo="RM",
                         evaluado_rm_id=rm.id,
                         fecha_inicio=datetime(2026, 2, 10, 9, 0),
                         fecha_fin=datetime(2026, 2, 10, 10, 0),
                         score=95, aprobado=True))
    db.commit()
    p = ranking.pesos(db, "DO")

    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_examenes"] == 30
    assert ranking.calcular_componentes(db, rm.id, c2, p)["puntos_examenes"] == 30


def test_campana_sin_ciclo_no_suma(escenario):
    """`RefuerzoCampana.ciclo_id` es nullable: sin ciclo no se atribuye a ninguno,
    en vez de repartirla por fecha y arriesgar contarla dos veces."""
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    huerfana = RefuerzoCampana(pais_codigo="DO", nombre="Sin ciclo", ciclo_id=None,
                               duracion_dias=30, modo_espaciado="creciente")
    db.add(huerfana)
    db.flush()
    ronda = RefuerzoRondaProgramada(campana_id=huerfana.id, numero_ronda=1,
                                    fecha_hora_sugerida=datetime(2026, 1, 6, 9, 0),
                                    publicada=True)
    db.add(ronda)
    db.flush()
    capsula = RefuerzoCapsula(ronda_id=ronda.id, formato="microlectura",
                              enunciado="Huérfana", orden=1)
    db.add(capsula)
    db.flush()
    db.add(RefuerzoRespuesta(
        ronda_id=ronda.id, capsula_id=capsula.id, rm_id=rm.id,
        timestamp_recibido=datetime(2026, 1, 6, 9, 0),
        timestamp_respondido=datetime(2026, 1, 6, 9, 1),
        tiempo_respuesta_seg=60, puntos_obtenidos=99))
    db.commit()
    p = ranking.pesos(db, "DO")

    # Sigue siendo 8: los 99 de la campaña sin ciclo no entran.
    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_refuerzo"] == 8


def test_pesos_configurados_sobrescriben_los_de_defecto(escenario):
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    ranking.fijar_peso(db, "DO", "ranking_puntos_certificacion", 100.0)

    p = ranking.pesos(db, "DO")
    assert p["ranking_puntos_certificacion"] == 100.0
    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_certificacion"] == 100


def test_fijar_peso_rechaza_clave_desconocida(escenario):
    with pytest.raises(ValueError, match="Peso desconocido"):
        ranking.fijar_peso(escenario["db"], "DO", "peso_inventado", 1.0)


def test_recalcular_es_reejecutable(escenario):
    """Delete-then-insert: correrlo dos veces no duplica ni acumula."""
    db, c1 = escenario["db"], escenario["c1"]

    r1 = ranking.recalcular_ciclo(db, c1.id, "DO")
    r2 = ranking.recalcular_ciclo(db, c1.id, "DO")

    assert r1["rms_procesados"] == 1
    assert r2["rms_procesados"] == 1
    filas = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c1.id).all()
    assert len(filas) == 1
    assert filas[0].puntos_total == 88


def test_racha_cuenta_ciclos_consecutivos_y_se_corta(escenario):
    """La racha mira hacia atrás y se detiene en el primer ciclo sin puntos.

    El ciclo 2 no tiene actividad, así que al calcularlo la racha vuelve a 0
    aunque el ciclo 1 sí tuviera puntos.
    """
    db, c1, c2 = escenario["db"], escenario["c1"], escenario["c2"]

    ranking.recalcular_ciclo(db, c1.id, "DO")
    ranking.recalcular_ciclo(db, c2.id, "DO")

    fila_c1 = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c1.id).one()
    fila_c2 = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c2.id).one()
    assert fila_c1.racha_ciclos == 1      # su propio ciclo con puntos
    assert fila_c2.puntos_total == 0
    assert fila_c2.racha_ciclos == 0      # sin puntos, la racha se corta


def test_ranking_ordena_y_numera(escenario):
    """Un segundo RM sin actividad debe quedar detrás, con posición 2."""
    db, c1, linea = escenario["db"], escenario["c1"], escenario["linea"]
    otro = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                               codigo="VM02", nombre="Representante Dos")
    db.add(otro)
    db.commit()
    ranking.recalcular_ciclo(db, c1.id, "DO")

    filas = ranking.ranking(db, c1.id)

    assert [f["posicion"] for f in filas] == [1, 2]
    assert filas[0]["rm_nombre"] == "Representante Uno"
    assert filas[0]["puntos_total"] == 88
    assert filas[1]["puntos_total"] == 0


def test_ranking_filtra_por_rm_ids(escenario):
    """El auto-scope del GD se aplica en la lectura, no en el cálculo."""
    db, c1, rm = escenario["db"], escenario["c1"], escenario["rm"]
    ranking.recalcular_ciclo(db, c1.id, "DO")

    filas = ranking.ranking(db, c1.id, rm_ids=[rm.id])

    assert len(filas) == 1
    assert filas[0]["rm_id"] == rm.id
