"""Plan de Cierre de Brechas (§12) — el motor de reglas y su cableado.

Las 5 reglas se prueban alimentando un reporte de KPI CONSTRUIDO A MANO
(monkeypatch de `kpi.reporte`), no datos reales: cada regla existe para
distinguir una causa de otra, y la única forma de probar que las distingue es
darle el caso exacto donde una aplica y las demás no. Fabricar ese caso desde
respuestas reales de representantes sería frágil y opaco.

El flujo de persistencia (generar → listar → atender) y los umbrales sí van
contra PostgreSQL, porque ahí lo que se prueba es el delete-then-insert y las FK.
"""
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
from app.models.formacion import ParametroFormacion, PlanCierreBrecha
from app.services import formacion_brechas_service as brechas

BD_PRUEBA = "vista_test_brechas"


# ===========================================================================
# Fábrica de reportes de KPI para las pruebas de reglas
# ===========================================================================

def _pregunta(capsula_id: int, enunciado: str, pct: float) -> dict:
    return {"capsula_id": capsula_id, "enunciado": enunciado,
            "pct_aciertos": pct, "respuestas": 5}


def _segmento(clave: str, valor, *, pct_aciertos=95.0, tiempo=100,
              participacion=95.0, peor=None, mejor=None) -> dict:
    return {clave: valor, "respuestas": 5, "tiempo_promedio_seg": tiempo,
            "pct_participacion": participacion, "pct_aciertos": pct_aciertos,
            "pregunta_menos_acertada": peor, "pregunta_mas_acertada": mejor}


def _reporte(*, por_representante=None, por_producto=None, por_pais=None,
             por_gd=None, general=None) -> dict:
    return {
        "total_respuestas": 10,
        "general": general or {"respuestas": 10, "tiempo_promedio_seg": 120,
                               "pct_participacion": 90.0, "pct_aciertos": 90.0},
        "por_representante": por_representante or [],
        "por_producto": por_producto or [],
        "por_pais": por_pais or [],
        "por_gd": por_gd or [],
    }


@pytest.fixture
def parchar_reporte(monkeypatch):
    """Sustituye el KPI real por uno fabricado, para aislar cada regla."""
    def _set(reporte: dict):
        monkeypatch.setattr(brechas.kpi, "reporte",
                            lambda *a, **k: reporte)
    return _set


# ===========================================================================
# Regla 1 (Alta) — contenido generalizado
# ===========================================================================

def test_una_pregunta_peor_en_mas_de_la_mitad_de_segmentos_es_contenido(parchar_reporte, db):
    """§12.2 Regla 1: si la MISMA pregunta es la peor en medio mundo, la causa es
    el contenido, no las personas. Total 4 segmentos (2 rep + 1 prod + 1 país),
    la cápsula 10 es la peor en los 4 → 4 > 2 → dispara."""
    peor = _pregunta(10, "Mecanismo de acción de CardioZ", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=peor)],
        por_producto=[_segmento("producto_id", 7, peor=peor)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    reglas = [a["regla_aplicada"] for a in alertas]
    assert "contenido_generalizado" in reglas
    generalizada = next(a for a in alertas if a["regla_aplicada"] == "contenido_generalizado")
    assert generalizada["prioridad"] == brechas.PRIORIDAD_ALTA
    assert generalizada["_capsula_id"] == 10


def test_una_pregunta_peor_en_un_solo_segmento_no_es_generalizada(parchar_reporte, db):
    """El complemento: fallar en 1 de 4 segmentos (1 no es > 2) NO es contenido —
    esa la recoge la regla 2 como problema localizado, no la 1."""
    peor = _pregunta(10, "Dosis inicial", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=_pregunta(11, "Otra", 88.0))],
        por_producto=[_segmento("producto_id", 7, peor=_pregunta(12, "Otra2", 90.0))],
        por_pais=[_segmento("pais_codigo", "DO", peor=_pregunta(13, "Otra3", 91.0))]))

    alertas = brechas.generar(db, "DO", persistir=False)
    assert "contenido_generalizado" not in [a["regla_aplicada"] for a in alertas]


# ===========================================================================
# Regla 2 (Media) — concentrada y su exclusión de lo generalizado
# ===========================================================================

def test_una_pregunta_peor_solo_en_un_equipo_es_problema_localizado(parchar_reporte, db):
    peor = _pregunta(20, "Interacción con betabloqueantes", 55.0)
    parchar_reporte(_reporte(
        por_gd=[_segmento("gerente_id", 3, peor=peor)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    concentradas = [a for a in alertas if a["regla_aplicada"] == "concentrada_equipo_pais"]
    assert len(concentradas) == 1
    assert concentradas[0]["prioridad"] == brechas.PRIORIDAD_MEDIA
    assert "3" in concentradas[0]["alcance"]


def test_lo_ya_marcado_generalizado_no_se_repite_como_concentrado(parchar_reporte, db):
    """§12.2: si a la cápsula 10 le pasa a TODOS (regla 1), señalar además a un
    equipo concreto sería ruido que desvía la atención. La regla 2 la excluye."""
    peor = _pregunta(10, "Mecanismo de acción", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=peor)],
        por_producto=[_segmento("producto_id", 7, peor=peor)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor)],
        por_gd=[_segmento("gerente_id", 3, peor=peor)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    assert "contenido_generalizado" in [a["regla_aplicada"] for a in alertas]
    concentradas_de_10 = [a for a in alertas
                          if a["regla_aplicada"] == "concentrada_equipo_pais"
                          and a["_capsula_id"] == 10]
    assert concentradas_de_10 == [], "la 10 ya es generalizada, no se repite por equipo"


# ===========================================================================
# Regla 3 (Media) — el material, no las personas
# ===========================================================================

def test_quien_domina_todo_y_aun_asi_falla_apunta_al_material(parchar_reporte, db):
    """§12.2 Regla 3: un representante que acierta el 92% del temario pero falla
    esta pregunta señala que el material está mal escrito, no que le falte
    estudiar. Es la regla menos evidente y la más útil."""
    peor = _pregunta(30, "Contraindicación absoluta", 60.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 5, pct_aciertos=92.0, peor=peor)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    material = [a for a in alertas if a["regla_aplicada"] == "material_no_personas"]
    assert len(material) == 1
    assert "representante 5" in material[0]["alcance"]


def test_quien_falla_porque_no_domina_no_dispara_la_regla_del_material(parchar_reporte, db):
    """Si acierta solo el 70% (bajo el umbral de dominio 85%), fallar una
    pregunta es esperable: no es señal de que el material esté mal."""
    peor = _pregunta(30, "Contraindicación", 60.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 5, pct_aciertos=70.0, peor=peor)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    assert "material_no_personas" not in [a["regla_aplicada"] for a in alertas]


# ===========================================================================
# Regla 4 (Alta) — escalamiento por métricas múltiples en rojo
# ===========================================================================

def test_dos_metricas_en_rojo_a_la_vez_escalan_a_coaching(parchar_reporte, db):
    """§12.2 Regla 4: con una métrica baja puede ser una mala semana; con dos,
    más cápsulas automáticas no lo arreglan. Aciertos 60% (<70) y participación
    50% (<70) → dos en rojo → escala."""
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 9, pct_aciertos=60.0,
                                     participacion=50.0, tiempo=100)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    escalamiento = [a for a in alertas if a["regla_aplicada"] == "escalamiento_individual"]
    assert len(escalamiento) == 1
    assert escalamiento[0]["prioridad"] == brechas.PRIORIDAD_ALTA
    assert escalamiento[0]["link_accion"] == "/lsii?rm_id=9"


def test_una_sola_metrica_en_rojo_no_escala(parchar_reporte, db):
    """Solo aciertos bajos (una métrica) no basta: el umbral es 2 a la vez."""
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 9, pct_aciertos=60.0,
                                     participacion=95.0, tiempo=100)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    assert "escalamiento_individual" not in [a["regla_aplicada"] for a in alertas]


# ===========================================================================
# Regla 5 (Informativa) — problema operativo, no de contenido
# ===========================================================================

def test_un_equipo_peor_en_las_tres_metricas_es_adopcion_no_contenido(parchar_reporte, db):
    """§12.2 Regla 5: por debajo del promedio en las TRES a la vez apunta a que
    las notificaciones no llegan, no a un tema concreto."""
    general = {"respuestas": 10, "tiempo_promedio_seg": 120,
               "pct_participacion": 90.0, "pct_aciertos": 90.0}
    parchar_reporte(_reporte(
        general=general,
        por_gd=[_segmento("gerente_id", 4, pct_aciertos=70.0,
                          participacion=60.0, tiempo=300)]))

    alertas = brechas.generar(db, "DO", persistir=False)
    operativas = [a for a in alertas if a["regla_aplicada"] == "operativa_gestion"]
    assert len(operativas) == 1
    assert operativas[0]["prioridad"] == brechas.PRIORIDAD_INFO


# ===========================================================================
# Orquestación — orden y contrato de salida
# ===========================================================================

def test_las_alertas_salen_ordenadas_por_prioridad(parchar_reporte, db):
    """Alta antes que media antes que informativa: Capacitación tiene tiempo
    limitado y debe ver primero lo que más importa."""
    peor_gen = _pregunta(10, "Generalizada", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor_gen),
                           _segmento("rm_id", 2, peor=peor_gen)],
        por_producto=[_segmento("producto_id", 7, peor=peor_gen)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor_gen)],
        por_gd=[_segmento("gerente_id", 4, pct_aciertos=70.0,
                          participacion=60.0, tiempo=300,
                          peor=_pregunta(99, "Otra", 65.0))]))

    prioridades = [a["prioridad"] for a in brechas.generar(db, "DO", persistir=False)]
    orden = {brechas.PRIORIDAD_ALTA: 0, brechas.PRIORIDAD_MEDIA: 1,
             brechas.PRIORIDAD_INFO: 2}
    assert prioridades == sorted(prioridades, key=lambda p: orden[p])


# ===========================================================================
# Umbrales configurables (§12.3)
# ===========================================================================

def test_los_umbrales_arrancan_en_los_valores_del_documento(db):
    valores = brechas.umbrales(db, "DO")
    assert valores["brecha_generalizada_fraccion"] == 0.5
    assert valores["material_dominio_pct"] == 85.0


def test_un_pais_puede_sobrescribir_un_umbral_sin_tocar_codigo(db):
    brechas.fijar_umbral(db, "DO", "material_dominio_pct", 90.0)
    assert brechas.umbrales(db, "DO")["material_dominio_pct"] == 90.0
    # El override es por país: otro país conserva el valor de arranque.
    assert brechas.umbrales(db, "PA")["material_dominio_pct"] == 85.0


def test_fijar_un_umbral_inexistente_es_un_error(db):
    with pytest.raises(ValueError):
        brechas.fijar_umbral(db, "DO", "umbral_que_no_existe", 1.0)


# ===========================================================================
# Persistencia: generar → listar → atender (contra PostgreSQL real)
# ===========================================================================

def test_generar_persiste_y_listar_lo_devuelve(parchar_reporte, db):
    peor = _pregunta(10, "Generalizada", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=peor)],
        por_producto=[_segmento("producto_id", 7, peor=peor)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor)]))

    brechas.generar(db, "DO", ciclo_id=None, persistir=True)
    guardadas = brechas.listar(db, "DO")
    assert guardadas, "debería haber persistido al menos la generalizada"
    assert all(isinstance(a, PlanCierreBrecha) for a in guardadas)


def test_regenerar_reemplaza_la_foto_anterior(parchar_reporte, db):
    """§12: el plan es una foto del estado actual, no un historial. Regenerar
    borra lo anterior del mismo país y ciclo — acumular dejaría a Capacitación
    mirando brechas ya cerradas."""
    peor = _pregunta(10, "Generalizada", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=peor)],
        por_producto=[_segmento("producto_id", 7, peor=peor)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor)]))

    brechas.generar(db, "DO", persistir=True)
    primera = len(brechas.listar(db, "DO"))
    brechas.generar(db, "DO", persistir=True)
    segunda = len(brechas.listar(db, "DO"))
    assert segunda == primera, "regenerar reemplaza, no acumula"


def test_marcar_atendida_la_saca_del_listado_por_defecto(parchar_reporte, db):
    peor = _pregunta(10, "Generalizada", 40.0)
    parchar_reporte(_reporte(
        por_representante=[_segmento("rm_id", 1, peor=peor),
                           _segmento("rm_id", 2, peor=peor)],
        por_producto=[_segmento("producto_id", 7, peor=peor)],
        por_pais=[_segmento("pais_codigo", "DO", peor=peor)]))
    brechas.generar(db, "DO", persistir=True)

    alerta = brechas.listar(db, "DO")[0]
    brechas.marcar_atendida(db, alerta.id)
    assert alerta.id not in [a.id for a in brechas.listar(db, "DO")]
    # Pero sigue existiendo: atendida ≠ borrada.
    assert alerta.id in [a.id for a in brechas.listar(db, "DO", incluir_atendidas=True)]


# ===========================================================================
# Infraestructura de base de datos
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
def db(motor):
    """Sesión limpia con los países de referencia que exigen las FK."""
    Sesion = sessionmaker(bind=motor)
    sesion = Sesion()
    for t in ('formacion."PlanCierreBrecha"', 'formacion."ParametroFormacion"',
              '"Config"."DIM_Pais"'):
        sesion.execute(text(f"DELETE FROM {t}"))
    sesion.add_all([Pais(codigo="DO", nombre="República Dominicana"),
                    Pais(codigo="PA", nombre="Panamá")])
    sesion.commit()
    yield sesion
    sesion.close()
