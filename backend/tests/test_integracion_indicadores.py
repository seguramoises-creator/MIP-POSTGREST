"""Motor de cálculo de los cuatro indicadores de visita, derivados de `ext`.

Lo que estas pruebas cuidan por encima de todo: las dos fórmulas de §2.1 del
Requerimiento de Datos VISTA-Mallén v2 — cobertura cuenta MÉDICOS DISTINTOS
visitados (no visitas, no exige la frecuencia completa) y PROM_DIARIO divide
médicos distintos entre días laborables (no visitas).

Necesita PostgreSQL real: cruza dos esquemas con claves compuestas e índices
únicos.
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
from app.models.dimensiones import Ciclo, Indicador, Linea, Pais, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedico, ExtDimPais, ExtDimRepresentante,
    ExtFactVisitaMedico, ExtPanelMedico,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.services import integracion_indicadores_service as ind

BD_PRUEBA = "vista_test_indicadores"


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
    # Hijos antes que padres.
    for tabla in ('"DW"."FACT_ResultadoIndicador"', '"Config"."DIM_Indicador"',
                  "ext.panelmedico", "ext.factvisitamedico", "ext.targetfarmacia",
                  "ext.factvisitafarmacia", "ext.controlcarga",
                  '"Config"."DIM_Medico"', '"Config"."DIM_CentroMedico"',
                  '"Config"."DIM_Municipio"', '"Config"."DIM_Provincia"',
                  '"Config"."DIM_Farmacia"', '"Config"."DIM_Producto"',
                  '"Config"."DIM_Especialidad"', "ext.dimmedico", "ext.dimfarmacia",
                  "ext.dimproducto", "ext.dimespecialidad",
                  '"Config"."MapeoExterno"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', "ext.dimrepresentante",
                  "ext.dimgerente", "ext.dimciclo", "ext.dimlinea",
                  "ext.dimpais", '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def base(db):
    """Dimensiones mapeadas + los 4 indicadores dados de alta en el país."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    db.add_all([rm, ciclo])
    db.flush()
    for codigo in ind.CODIGOS:
        db.add(Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                         modulo="PRODUCTIVIDAD", tipo_periodo="CICLO"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="RD", activo=True))
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtControlCarga(
        lote_id=1001, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=0,
        estado="VALIDADO"))
    db.flush()
    db.add(MapeoExterno(entidad=ENT_REPRESENTANTE, pais_codigo="DO",
                        codigo_externo="VM01", id_interno=rm.id))
    db.add(MapeoExterno(entidad=ENT_CICLO, pais_codigo="DO",
                        codigo_externo="C01-2026", id_interno=ciclo.id))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo}


def _valor(db, rm_id, ciclo_id, codigo):
    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(ResultadoIndicador.rm_id == rm_id,
                    ResultadoIndicador.ciclo_id == ciclo_id,
                    Indicador.codigo == codigo).first())
    return float(fila.resultado_real) if fila else None


def _panel(db, medico, frecuencia, programadas):
    # `panelmedico` y `factvisitamedico` llevan FK a `ext.dimmedico`: sin esta
    # fila, la carga de panel o de visitas revienta con ForeignKeyViolation.
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo=medico,
                        nombre=f"Doctor {medico}", activo=True))
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo=frecuencia, prioridad="TOP",
        visitas_programadas=programadas, activo=True))


def _visitas(db, medico, cuantas, ejecutada=True, desde=1):
    for i in range(cuantas):
        db.add(ExtFactVisitaMedico(
            lote_id=1001, origen_id=f"V-{medico}-{i}", pais_codigo="DO",
            ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo=medico,
            fecha_visita=date(2026, 1, desde + i), tipo_visita="V",
            ejecutada=ejecutada, acompanado=False))


def test_cobertura_cuenta_medicos_distintos_no_visitas(base):
    """El caso que fija «médicos distintos visitados» (§2.1 del requerimiento).

    Dos médicos F1: uno visitado 3 veces, el otro ninguna. Las 3 visitas al
    mismo médico cuentan UNA vez, así que da 50. Si el numerador contara
    visitas en vez de médicos, daría 150 — un valor imposible.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _panel(db, "MD02", "F1", 2)
    _visitas(db, "MD01", 3)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 50.0


def test_una_sola_visita_ya_cubre_aunque_exija_mas(base):
    """`visitas_programadas` NO participa: basta una visita ejecutada.

    Un médico F1 que declara exigir 2 visitas y recibió 1 → cubierto, 100.
    Con la definición vieja («frecuencia completa») daría 0. Este test es el
    que impide que esa definición vuelva a colarse.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0


def test_f1_y_f2_no_se_mezclan(base):
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F2", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0
    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F2") == 0.0


def test_promedio_diario_cuenta_medicos_distintos_no_visitas(base):
    """§2.1: «MÉDICOS visitados / días laborables», no visitas.

    Un médico visitado 10 veces en un ciclo de 20 días → 1/20 = 0.05.
    Si contara visitas daría 0.5: diez veces más. Es la diferencia que
    justifica este test.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_promedio_diario_suma_medicos_distintos(base):
    """10 médicos distintos visitados / 20 días laborables = 0.5."""
    db = base["db"]
    for i in range(10):
        _panel(db, f"MD{i:02d}", "F1", 1)
        _visitas(db, f"MD{i:02d}", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.5


def test_las_no_ejecutadas_no_cuentan_pero_su_medico_si(base):
    """No visitar no reduce el universo: el médico sigue en el denominador."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F1", 1)
    _visitas(db, "MD01", 1)
    _visitas(db, "MD02", 1, ejecutada=False, desde=10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 50.0
    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_visitas_programadas_nulo_no_afecta_el_calculo(base):
    """`visitas_programadas` no entra en la fórmula, así que un nulo no rompe
    nada ni genera hallazgo: no hay frecuencia que exigir."""
    db = base["db"]
    _panel(db, "MD01", "F1", None)
    _visitas(db, "MD01", 1)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0
    assert hallazgos == []


def test_recalcular_no_duplica_ni_toca_otros_indicadores(base):
    """Delete-then-insert acotado a los 4 códigos: los otros no se rozan."""
    db = base["db"]
    otro = Indicador(pais_codigo="DO", codigo="VENTAS", nombre="Ventas",
                     modulo="COMERCIAL", tipo_periodo="MES")
    db.add(otro)
    db.flush()
    db.add(ResultadoIndicador(rm_id=base["rm"].id, pais_codigo="DO",
                              linea_id=base["rm"].linea_id,
                              ciclo_id=base["ciclo"].id, indicador_id=otro.id,
                              resultado_real=88, activo=True))
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()
    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(ResultadoIndicador).count() == 5   # 4 calculados + VENTAS
    assert _valor(db, base["rm"].id, base["ciclo"].id, "VENTAS") == 88.0


def test_no_escribe_puntos_solo_el_valor(base):
    """La conversión a puntos sigue siendo del motor existente."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "COB_MD_F1").one())
    assert fila.resultado_real is not None
    assert fila.puntos_obtenidos is None
