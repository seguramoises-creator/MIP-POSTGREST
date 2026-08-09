"""Motor de cálculo de los cuatro indicadores de visita, derivados de `ext`.

Lo que estas pruebas cuidan por encima de todo: las dos fórmulas de §2.1 del
Requerimiento de Datos VISTA-Mallén v2 — cobertura cuenta MÉDICOS DISTINTOS
visitados (no visitas, no exige la frecuencia completa) y PROM_DIARIO divide
médicos distintos entre días laborables (no visitas).

Necesita PostgreSQL real: cruza dos esquemas con claves compuestas e índices
únicos.
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
from app.models.dimensiones import (
    Ciclo, Indicador, Linea, MetaIndicador, Pais, RepresentanteMedico,
)
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedico, ExtDimPais, ExtDimRepresentante,
    ExtFactVisitaMedico, ExtPanelMedico,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.services import integracion_indicadores_service as ind
from app.services import motor_calculo_service

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
    for tabla in ('"DW"."FACT_ResultadoIndicador"', '"Config"."DIM_MetaIndicador"',
                  '"Config"."DIM_Indicador"',
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
    indicadores = {}
    for codigo in ind.CODIGOS:
        fila_ind = Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                             modulo="PRODUCTIVIDAD", tipo_periodo="CICLO")
        db.add(fila_ind)
        indicadores[codigo] = fila_ind
    db.flush()
    # PROM_DIARIO (corrección 2) necesita una meta configurada para
    # convertirse en fracción de logro; se da de alta con `meta_100 = 1` para
    # que la mayoría de las pruebas (centradas en «médicos distintos, no
    # visitas») sigan viendo la misma tasa cruda que antes del fix (dividir
    # entre 1 no cambia el valor). Las pruebas que sí ejercitan la
    # normalización usan una meta distinta a propósito.
    db.add(MetaIndicador(indicador_id=indicadores[ind.PROM_DIARIO].id,
                         peso=0, meta_100=Decimal("1"), activo=True))
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
    return {"db": db, "rm": rm, "ciclo": ciclo, "indicadores": indicadores}


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
    mismo médico cuentan UNA vez, así que da 0.5 (FRACCIÓN 0-1, corrección
    C1 — antes se escribía en porcentaje 0-100, que el motor de puntuación
    volvía a multiplicar por 100 y saturaba). Si el numerador contara visitas
    en vez de médicos, daría 1.5 — un valor imposible.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _panel(db, "MD02", "F1", 2)
    _visitas(db, "MD01", 3)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 0.5


def test_una_sola_visita_ya_cubre_aunque_exija_mas(base):
    """`visitas_programadas` NO participa: basta una visita ejecutada.

    Un médico F1 que declara exigir 2 visitas y recibió 1 → cubierto, 1.0
    (fracción 0-1, ver corrección C1). Con la definición vieja («frecuencia
    completa») daría 0. Este test es el que impide que esa definición vuelva
    a colarse.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 1.0


def test_f1_y_f2_no_se_mezclan(base):
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F2", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 1.0
    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F2") == 0.0


def test_promedio_diario_cuenta_medicos_distintos_no_visitas(base):
    """§2.1: «MÉDICOS visitados / días laborables», no visitas.

    Un médico visitado 10 veces en un ciclo de 20 días → 1/20 = 0.05 de tasa
    cruda. La fixture `base` da de alta la meta de PROM_DIARIO en
    `meta_100 = 1` (corrección C2: sin meta no hay con qué normalizar),
    valor elegido a propósito para que dividir entre la meta no altere el
    número y este test siga aislando lo que le importa: que cuenta médicos
    distintos, no visitas (si contara visitas daría 0.5: diez veces más).
    La normalización contra una meta distinta de 1 se prueba aparte, en
    `test_motor_prom_diario_mitad_de_meta_da_50_tras_motor`.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_promedio_diario_suma_medicos_distintos(base):
    """10 médicos distintos visitados / 20 días laborables = 0.5 (meta=1,
    ver nota en `test_promedio_diario_cuenta_medicos_distintos_no_visitas`)."""
    db = base["db"]
    for i in range(10):
        _panel(db, f"MD{i:02d}", "F1", 1)
        _visitas(db, f"MD{i:02d}", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.5


def test_las_no_ejecutadas_no_cuentan_pero_su_medico_si(base):
    """No visitar no reduce el universo: el médico sigue en el denominador.

    COB_MD_F1 se lee en fracción 0-1 (corrección C1); PROM_DIARIO usa la
    meta por defecto de la fixture (`meta_100 = 1`, ver nota de
    `test_promedio_diario_cuenta_medicos_distintos_no_visitas`).
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F1", 1)
    _visitas(db, "MD01", 1)
    _visitas(db, "MD02", 1, ejecutada=False, desde=10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 0.5
    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_visitas_programadas_nulo_no_afecta_el_calculo(base):
    """`visitas_programadas` no entra en la fórmula, así que un nulo no rompe
    nada ni genera hallazgo: no hay frecuencia que exigir. La fixture `base`
    ya deja configurada la meta de PROM_DIARIO, así que tampoco dispara el
    hallazgo de la corrección C2."""
    db = base["db"]
    _panel(db, "MD01", "F1", None)
    _visitas(db, "MD01", 1)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 1.0
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


def test_ciclo_cerrado_no_borra_puntos_ya_calculados(base):
    """El defecto que este test delata: reintegrar un ciclo YA CERRADO hacía
    delete-then-insert de las 4 filas y perdía `puntos_obtenidos` para
    siempre, porque el recálculo posterior (`recalculo_service`) también
    rechaza el ciclo cerrado y nunca los repone.

    Secuencia: ciclo abierto → se calculan los indicadores → el motor llena
    `puntos_obtenidos` → se cierra el ciclo → llega un lote tardío y alguien
    vuelve a integrar. Las 4 filas y sus puntos deben seguir intactos.
    """
    db = base["db"]
    rm_id, ciclo_id = base["rm"].id, base["ciclo"].id
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    filas_antes = (db.query(ResultadoIndicador)
                   .filter(ResultadoIndicador.rm_id == rm_id,
                           ResultadoIndicador.ciclo_id == ciclo_id).all())
    assert len(filas_antes) == 4
    # Simula lo que hace el motor de cálculo: llena puntos_obtenidos.
    for fila in filas_antes:
        fila.puntos_obtenidos = Decimal("77.5")
        fila.resultado_porcentaje = Decimal("77.5")
    db.commit()

    base["ciclo"].cerrado = True
    db.commit()

    hallazgos = []
    resultado = ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert resultado["omitido_ciclo_cerrado"] is True
    assert resultado == {"rms": 0, "filas": 0, "omitido_ciclo_cerrado": True}

    filas_despues = (db.query(ResultadoIndicador)
                      .filter(ResultadoIndicador.rm_id == rm_id,
                              ResultadoIndicador.ciclo_id == ciclo_id).all())
    assert len(filas_despues) == 4
    for fila in filas_despues:
        assert fila.puntos_obtenidos == Decimal("77.5")
        assert fila.resultado_porcentaje == Decimal("77.5")

    assert len(hallazgos) == 1
    assert hallazgos[0].severidad == "aviso"
    assert "cerrado" in hallazgos[0].problema.lower()


def test_ciclo_abierto_reporta_omitido_ciclo_cerrado_false(base):
    """Los demás casos deben devolver la clave siempre, en False, para que
    quien consuma el dict pueda leerla sin comprobar antes si existe."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    resultado = ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert resultado["omitido_ciclo_cerrado"] is False


def test_rms_solo_cuenta_los_efectivamente_calculados(base):
    """`rms` no debe contar representantes sin mapeo: si no se calculó nada
    para ellos, el panel del operador no puede decir que sí se calculó."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    # Un segundo RM con actividad en `ext` pero SIN mapeo interno: no debe
    # sumar a `rms`, solo generar su propio hallazgo de error.
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM02",
                               nombre="Representante Dos", activo=True))
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM02", medico_codigo="MD01", frecuencia_objetivo="F1",
        prioridad="TOP", visitas_programadas=1, activo=True))
    db.commit()

    hallazgos = []
    resultado = ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert resultado["rms"] == 1
    assert resultado["filas"] == 4
    assert any(h.origen_id == "VM02" for h in hallazgos)


# ---------------------------------------------------------------------------
# Corrección C1/C2 (defecto CRITICAL): pruebas que ATRAVIESAN el motor de
# puntuación real (`motor_calculo_service.completar_puntajes`), no solo
# `resultado_real`. El defecto original sobrevivió 6 revisiones precisamente
# porque ninguna prueba llegaba hasta acá: todas comparaban `resultado_real`
# contra sí mismo, nunca contra lo que el motor hace con ese valor.
# ---------------------------------------------------------------------------

def _fila(db, rm_id, ciclo_id, codigo):
    return (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(ResultadoIndicador.rm_id == rm_id,
                    ResultadoIndicador.ciclo_id == ciclo_id,
                    Indicador.codigo == codigo).one())


def test_motor_50pct_cobertura_da_mitad_de_puntos_tras_motor(base):
    """El test que blinda el defecto CRITICAL: un RM con 50% de cobertura
    real (1 de 2 médicos F1 visitados) debe salir con `resultado_porcentaje
    == 50` y la mitad de los puntos de la ponderación tras correr el motor
    de puntuación real — no puntaje perfecto.

    Contra el código viejo (`_pct` devolviendo 50.0 en vez de 0.5), el motor
    hacía `50.0 * 100 = 5000`, lo acotaba a 100, y este RM con la mitad de
    su panel sin visitar salía con el 100% de los puntos. Revertido el fix,
    este test falla (evidencia en `.superpowers/sdd/fix-c1-report.md`).
    """
    db = base["db"]
    ind_f1 = base["indicadores"][ind.COB_MD_F1]
    ind_f1.ponderacion_pct = 30
    db.commit()

    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, base["ciclo"].id, "DO")
    db.commit()

    fila = _fila(db, base["rm"].id, base["ciclo"].id, ind.COB_MD_F1)
    assert fila.resultado_porcentaje == Decimal("50")
    assert fila.puntos_obtenidos == Decimal("15")   # mitad de 30


def test_motor_100pct_cobertura_da_puntos_completos_tras_motor(base):
    """El extremo bueno: cobertura del 100% debe seguir dando
    `resultado_porcentaje == 100` y los puntos completos tras el fix — la
    corrección no debe romper el caso que ya funcionaba."""
    db = base["db"]
    ind_f1 = base["indicadores"][ind.COB_MD_F1]
    ind_f1.ponderacion_pct = 30
    db.commit()

    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, base["ciclo"].id, "DO")
    db.commit()

    fila = _fila(db, base["rm"].id, base["ciclo"].id, ind.COB_MD_F1)
    assert fila.resultado_porcentaje == Decimal("100")
    assert fila.puntos_obtenidos == Decimal("30")


def test_motor_prom_diario_mitad_de_meta_da_50_tras_motor(base):
    """Corrección C2: PROM_DIARIO normalizado contra una meta configurada
    (no 1, para ejercitar de verdad la división, a diferencia de las pruebas
    de fórmula que usan la meta=1 por defecto de la fixture). Meta = 0.2
    médicos/día, tasa real = 2 médicos distintos / 20 días = 0.1 (la mitad
    de la meta) → tras el motor, `resultado_porcentaje == 50`."""
    db = base["db"]
    ind_prom = base["indicadores"][ind.PROM_DIARIO]
    ind_prom.ponderacion_pct = 10
    meta = (db.query(MetaIndicador)
            .filter(MetaIndicador.indicador_id == ind_prom.id).one())
    meta.meta_100 = Decimal("0.2")
    db.commit()

    for i in range(2):
        _panel(db, f"MD{i:02d}", "F1", 1)
        _visitas(db, f"MD{i:02d}", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, base["ciclo"].id, "DO")
    db.commit()

    fila = _fila(db, base["rm"].id, base["ciclo"].id, ind.PROM_DIARIO)
    assert fila.resultado_porcentaje == Decimal("50")
    assert fila.puntos_obtenidos == Decimal("5")   # mitad de 10


def test_prom_diario_sin_meta_no_escribe_fila_y_emite_hallazgo_error(base):
    """Corrección C2: sin meta configurada no hay con qué normalizar la tasa
    cruda de PROM_DIARIO. Escribirla tal cual sería peor que no escribir
    nada (se leería como un cumplimiento ridículamente bajo), así que no se
    escribe la fila y se reporta un hallazgo de error señalando qué falta
    configurar. La fixture `base` deja una meta por defecto para el resto de
    las pruebas; aquí se retira a propósito para probar este camino."""
    db = base["db"]
    ind_prom_id = base["indicadores"][ind.PROM_DIARIO].id
    db.query(MetaIndicador).filter(MetaIndicador.indicador_id == ind_prom_id).delete()
    db.commit()

    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    hallazgos = []
    resultado = ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert resultado["filas"] == 3   # COB_MD_F1, COB_MD_F2, COB_FARMACIAS — sin PROM_DIARIO

    fila = (db.query(ResultadoIndicador)
            .filter(ResultadoIndicador.rm_id == base["rm"].id,
                    ResultadoIndicador.ciclo_id == base["ciclo"].id,
                    ResultadoIndicador.indicador_id == ind_prom_id).first())
    assert fila is None

    errores = [h for h in hallazgos
              if h.severidad == "error" and h.origen_id == ind.PROM_DIARIO]
    assert len(errores) == 1
    assert "meta" in errores[0].problema.lower()
