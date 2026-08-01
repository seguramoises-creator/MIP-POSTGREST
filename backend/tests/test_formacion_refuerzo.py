"""Refuerzo de Memoria y su KPI — casos 5, 6 y 7 del §16.

La tabla de participación se prueba SIN base de datos porque es una función
pura: los límites de cada tramo son la parte que el documento deja ambigua y la
que más fácil se rompe al tocar el código.
"""
from datetime import datetime, timedelta, timezone

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Gerente, Linea, Pais, RepresentanteMedico
from app.models.formacion import (
    RefuerzoCampana, RefuerzoCapsula, RefuerzoRondaProgramada,
)
from app.services import formacion_kpi_refuerzo_service as kpi
from app.services import formacion_refuerzo_service as refuerzo

BD_PRUEBA = "vista_test_refuerzo"


# ===========================================================================
# §16 caso 5 — tabla de participación (función pura, sin base)
# ===========================================================================

@pytest.mark.parametrize("minutos, esperado", [
    (0, 100), (1, 100), (4.9, 100),
    (12, 80),           # el ejemplo literal del caso 5
    (29, 80),
    (35, 70), (44, 70),
    (50, 50),           # el otro ejemplo literal del caso 5
    (600, 50),
])
def test_el_puntaje_de_participacion_sigue_la_tabla(minutos, esperado):
    """§10.6: 0-5 → 100%, 5-30 → 80%, 30-45 → 70%, más de 45 → 50%."""
    assert refuerzo.puntaje_participacion(int(minutos * 60)) == esperado


@pytest.mark.parametrize("minutos, esperado", [(5, 100), (30, 80), (45, 70)])
def test_los_limites_exactos_favorecen_al_representante(minutos, esperado):
    """El caso 5 pide verificar los límites exactos, y ahí el documento se
    contradice: escribe "0 a 5" y "5 a 30", que se solapan en el 5.

    Se resolvió a favor del tramo mejor —responder a los 5 minutos EXACTOS
    puntúa 100%— porque castigar por un segundo sería arbitrario. Es una
    interpretación, no una regla literal: está señalada para confirmar con
    Capacitación."""
    assert refuerzo.puntaje_participacion(minutos * 60) == esperado


def test_un_segundo_despues_del_limite_ya_baja_de_tramo():
    """El complemento del anterior: el límite es inclusivo, pero no elástico."""
    assert refuerzo.puntaje_participacion(5 * 60 + 1) == 80
    assert refuerzo.puntaje_participacion(30 * 60 + 1) == 70
    assert refuerzo.puntaje_participacion(45 * 60 + 1) == 50


# ===========================================================================
# Calendario de rondas (§10.2)
# ===========================================================================

def test_el_espaciado_creciente_de_30_dias_da_las_cinco_rondas_del_documento():
    """§10.2 describe el caso canónico: 24-48h, día 4, día 7, día 14 y cierre
    el 30."""
    assert refuerzo.calcular_offsets(30, "creciente") == [1, 4, 7, 14, 30]


def test_el_espaciado_creciente_se_adapta_a_otras_duraciones():
    """Con 15 días no caben las cinco: la del día 14 quedaría pegada al cierre,
    que es lo contrario de espaciar."""
    assert refuerzo.calcular_offsets(15, "creciente") == [1, 4, 7, 15]
    assert refuerzo.calcular_offsets(60, "creciente") == [1, 4, 7, 14, 30, 60]


def test_el_espaciado_fijo_reparte_cada_48_horas():
    """La alternativa que pidió el cliente originalmente (§10.2.1)."""
    assert refuerzo.calcular_offsets(10, "fijo_48h") == [2, 4, 6, 8, 10]


def test_un_modo_de_espaciado_inventado_falla():
    with pytest.raises(ValueError):
        refuerzo.calcular_offsets(30, "cada_luna_llena")


# ===========================================================================
# Lo que necesita base de datos
# ===========================================================================

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
    """Una campaña publicada con un reto de opción múltiple y dos representantes
    de gerentes distintos, para poder desglosar."""
    Sesion = sessionmaker(bind=motor)
    db = Sesion()
    for t in ('formacion."RefuerzoRespuesta"', 'formacion."RefuerzoCapsula"',
              'formacion."RefuerzoRondaProgramada"', 'formacion."RefuerzoCampana"',
              '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
              '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        db.execute(text(f"DELETE FROM {t}"))
    db.commit()

    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    gd_norte = Gerente(pais_codigo="DO", codigo="GD-N", nombre="GD Norte", tipo="DISTRITO")
    gd_sur = Gerente(pais_codigo="DO", codigo="GD-S", nombre="GD Sur", tipo="DISTRITO")
    db.add_all([gd_norte, gd_sur])
    db.flush()
    rm_a = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd_norte.id,
                               codigo="VM01", nombre="Ana")
    rm_b = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd_sur.id,
                               codigo="VM02", nombre="Beto")
    db.add_all([rm_a, rm_b])
    campana = RefuerzoCampana(pais_codigo="DO", nombre="CardioZ — refuerzo",
                              duracion_dias=30, modo_espaciado="creciente")
    db.add(campana)
    db.commit()

    rondas = refuerzo.generar_calendario(db, campana.id, inicio=datetime(2026, 7, 1, tzinfo=timezone.utc))
    ronda = rondas[0]
    reto = RefuerzoCapsula(
        ronda_id=ronda.id, formato="reto",
        enunciado="¿Cuál es la dosis inicial de CardioZ?",
        opciones={"A": "5 mg", "B": "10 mg", "C": "20 mg", "D": "40 mg"},
        opcion_correcta="B",
        explicacion="La ficha técnica indica 10 mg como dosis de inicio.")
    abierta = RefuerzoCapsula(
        ronda_id=ronda.id, formato="reflexion_abierta", orden=2,
        enunciado="¿Qué objeción escuchaste esta semana?")
    db.add_all([reto, abierta])
    db.commit()
    refuerzo.programar_ronda(db, ronda.id)
    refuerzo.publicar_ronda(db, ronda.id)
    db.refresh(ronda)
    yield {"db": db, "campana": campana, "ronda": ronda, "reto": reto,
           "abierta": abierta, "rm_a": rm_a, "rm_b": rm_b,
           "gd_norte": gd_norte, "gd_sur": gd_sur}
    db.close()


# ---------------------------------------------------------------------------
# §16 caso 6 — revelado inmediato
# ---------------------------------------------------------------------------

def test_al_fallar_se_devuelve_la_correcta_y_su_explicacion(escenario):
    """§10.7: la corrección es instantánea, en la misma interacción. Devolverla
    aquí es lo que permite resaltarla sin una segunda llamada."""
    r = refuerzo.registrar_respuesta(
        escenario["db"], escenario["reto"].id, escenario["rm_a"].id, opcion="C")
    assert r["es_acierto"] is False
    assert r["opcion_correcta"] == "B"
    assert "10 mg" in r["explicacion"]


def test_al_acertar_tambien_se_devuelve_la_correcta(escenario):
    """El documento dice "sin importar cuál eligió el RM": el resaltado ocurre
    igual, no solo cuando se equivoca."""
    r = refuerzo.registrar_respuesta(
        escenario["db"], escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    assert r["es_acierto"] is True
    assert r["opcion_correcta"] == "B"


# ---------------------------------------------------------------------------
# §16 caso 7 — las dos métricas son independientes
# ---------------------------------------------------------------------------

def test_una_respuesta_rapida_y_equivocada_da_alta_participacion_y_bajo_acierto(escenario):
    """El caso que el §10.8 existe para poder ver. Si las métricas se mezclaran
    en un solo número, este representante parecería promedio."""
    db = escenario["db"]
    ahora = datetime.now(timezone.utc)
    r = refuerzo.registrar_respuesta(
        db, escenario["reto"].id, escenario["rm_a"].id, opcion="A",
        recibido_en=ahora - timedelta(minutes=2), respondido_en=ahora)
    assert r["pct_participacion"] == 100
    assert r["es_acierto"] is False


def test_una_respuesta_lenta_y_correcta_da_baja_participacion_y_acierto(escenario):
    """El caso simétrico."""
    db = escenario["db"]
    ahora = datetime.now(timezone.utc)
    r = refuerzo.registrar_respuesta(
        db, escenario["reto"].id, escenario["rm_b"].id, opcion="B",
        recibido_en=ahora - timedelta(minutes=50), respondido_en=ahora)
    assert r["pct_participacion"] == 50
    assert r["es_acierto"] is True


def test_la_reflexion_abierta_no_tiene_acierto_pero_si_participacion(escenario):
    """§10.5: es el único formato de texto libre, "no calificado por
    correctitud, solo por participación". `es_acierto` queda en None, que NO es
    lo mismo que False — contarlo como fallo hundiría el % de aciertos."""
    r = refuerzo.registrar_respuesta(
        escenario["db"], escenario["abierta"].id, escenario["rm_a"].id,
        texto_libre="Me preguntaron por el precio.")
    assert r["es_acierto"] is None
    assert r["pct_participacion"] > 0


def test_no_se_puede_responder_dos_veces_la_misma_capsula(escenario):
    """Reintentar permitiría subir el % de aciertos repitiendo hasta acertar."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="A")
    segunda = refuerzo.registrar_respuesta(
        db, escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    assert segunda["repetida"] is True
    assert segunda["es_acierto"] is False, "conserva el primer intento"


# ---------------------------------------------------------------------------
# §10.3 / §10.4 — nada se envía sin confirmar
# ---------------------------------------------------------------------------

def test_una_ronda_sin_fecha_confirmada_no_se_publica(escenario):
    """§10.3: ninguna cápsula se envía sin que Capacitación confirme, aunque
    solo acepte la sugerencia."""
    db = escenario["db"]
    otra = db.query(RefuerzoRondaProgramada).filter(
        RefuerzoRondaProgramada.campana_id == escenario["campana"].id,
        RefuerzoRondaProgramada.numero_ronda == 2).first()
    with pytest.raises(refuerzo.CampanaNoPublicable) as e:
        refuerzo.publicar_ronda(db, otra.id)
    assert "programarla" in str(e.value)


def test_una_ronda_sin_capsulas_no_se_publica(escenario):
    """Publicarla dispararía la notificación dual hacia una pantalla vacía."""
    db = escenario["db"]
    otra = db.query(RefuerzoRondaProgramada).filter(
        RefuerzoRondaProgramada.campana_id == escenario["campana"].id,
        RefuerzoRondaProgramada.numero_ronda == 3).first()
    refuerzo.programar_ronda(db, otra.id)
    with pytest.raises(refuerzo.CampanaNoPublicable) as e:
        refuerzo.publicar_ronda(db, otra.id)
    assert "cápsulas" in str(e.value)


# ---------------------------------------------------------------------------
# §11 — el reporte de KPI
# ---------------------------------------------------------------------------

def test_el_reporte_trae_los_cuatro_desgloses(escenario):
    """§11.3: individual, por línea/producto, por GD y por país."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="A")
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_b"].id, opcion="B")
    r = kpi.reporte(db, campana_id=escenario["campana"].id)
    for desglose in ("por_representante", "por_producto", "por_gd", "por_pais"):
        assert desglose in r, desglose
    assert len(r["por_representante"]) == 2
    assert len(r["por_gd"]) == 2, "dos gerentes distintos"


def test_cada_fila_trae_la_pregunta_mas_y_menos_acertada(escenario):
    """§11.4, en CADA desglose: es el insumo del Plan de Cierre de Brechas."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    r = kpi.reporte(db, campana_id=escenario["campana"].id)
    fila = r["por_representante"][0]
    assert fila["pregunta_mas_acertada"] is not None
    assert "enunciado" in fila["pregunta_mas_acertada"]
    assert fila["pregunta_menos_acertada"] is not None


def test_las_dos_metricas_se_calculan_sobre_universos_distintos(escenario):
    """La participación cuenta TODAS las respuestas; el acierto solo las de
    opción múltiple. Contar la reflexión abierta como fallo hundiría el
    indicador sin que nadie entendiera por qué."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    refuerzo.registrar_respuesta(db, escenario["abierta"].id, escenario["rm_a"].id,
                                 texto_libre="algo")
    fila = next(f for f in kpi.reporte(db, campana_id=escenario["campana"].id)["por_representante"]
                if f["rm_id"] == escenario["rm_a"].id)
    assert fila["respuestas"] == 2
    assert fila["pct_aciertos"] == 100.0, "solo cuenta el reto, que acertó"


def test_un_gerente_solo_ve_las_respuestas_de_su_equipo(escenario):
    """§11.5: el GD ve los desgloses acotados a su distrito."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_b"].id, opcion="A")
    r = kpi.reporte(db, campana_id=escenario["campana"].id,
                    rm_ids=[escenario["rm_a"].id], incluir_por_gd=False)
    assert r["total_respuestas"] == 1
    assert "por_gd" not in r, "comparar su propio equipo consigo mismo no aporta"


def test_un_gerente_sin_equipo_no_ve_el_consolidado(escenario):
    """Una lista vacía de representantes debe devolver vacío, no todo: es el
    fallo clásico de tratar `[]` como "sin filtro"."""
    db = escenario["db"]
    refuerzo.registrar_respuesta(db, escenario["reto"].id, escenario["rm_a"].id, opcion="B")
    r = kpi.reporte(db, campana_id=escenario["campana"].id, rm_ids=[])
    assert r["total_respuestas"] == 0
