"""`ext.factventa` -> `DW.FACT_Ventas`, AGREGANDO por (pais, ciclo, RM).

La granularidad no coincide: el contrato manda detalle por producto (con
`producto_codigo` opcional) y `FACT_Ventas` es una fila por pais+linea+RM+ciclo,
sin columna de producto. Estas pruebas cuidan la suma, la idempotencia (vía
`MapeoExterno`, la Única que tiene esta tabla sin UNIQUE) y el aviso de cuota
repetida.

Necesita PostgreSQL real: cruza tres esquemas con claves compuestas.
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
from app.models.hechos import ResultadoIndicador, Ventas
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimPais, ExtDimProducto, ExtDimRepresentante,
    ExtFactVenta,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.services import integracion_indicadores_service as ind
from app.services import integracion_visitas_service as viz
from app.services import motor_calculo_service
from app.services import visita_costo_service

BD_PRUEBA = "vista_test_ventas"


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
    # `FACT_ResultadoIndicador`/`DIM_Indicador` los usan las pruebas del
    # indicador VENTAS (Tarea 2): sin limpiarlos aqui, la segunda prueba de la
    # sesion que llame `_indicador_ventas` chocaria con el UNIQUE
    # (pais_codigo, codigo) del indicador anterior, sin relacion con lo que
    # esa prueba intenta verificar.
    for tabla in ('"DW"."FACT_ResultadoIndicador"', '"DW"."FACT_Ventas"',
                  "ext.factventa", "ext.dimproducto",
                  '"Config"."MapeoExterno"', "ext.controlcarga",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Indicador"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Dimensiones sincronizadas (con su mapeo) + un lote abierto + el
    catalogo de productos que usan las pruebas (P1/P2/P3) -- necesario porque
    `ext.factventa.producto_codigo` tiene FK compuesta a `ext.dimproducto`
    cuando no viene nulo."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="gerente@ejemplo.com", tipo="DISTRITO")
    db.add(gerente)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gerente.id,
                             codigo="VM01", nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    db.add_all([rm, ciclo])
    db.flush()

    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    for producto in ("P1", "P2", "P3"):
        db.add(ExtDimProducto(pais_codigo="DO", producto_codigo=producto,
                              nombre=f"Producto {producto}", activo=True))
    db.add(ExtControlCarga(
        lote_id=1001, sistema_origen="SFA", modulo="VENTAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=2,
        estado="VALIDADO"))
    db.flush()

    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id)):
        db.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                            codigo_externo=codigo, id_interno=interno))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo}


def _venta(db, origen_id, valor, cuota, producto="P1", rm="VM01", lote_id=1001):
    db.add(ExtFactVenta(
        lote_id=lote_id, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo=rm, producto_codigo=producto,
        valor_venta=Decimal(str(valor)), cuota=Decimal(str(cuota))))
    db.flush()


def test_agrega_el_detalle_por_producto_en_una_fila(escenario):
    """FACT_Ventas es una fila por (pais, linea, RM, ciclo): el detalle por
    producto se suma, no se replica."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 50, producto="P1")
    _venta(db, "V-2", 200, 50, producto="P2")
    _venta(db, "V-3", 300, 50, producto="P3")
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    v = db.query(Ventas).one()
    assert v.ventas_reales == Decimal("600.00")
    assert v.rm_id == escenario["rm"].id
    assert v.ciclo_id == escenario["ciclo"].id


def test_una_fila_sin_producto_se_agrega_igual(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 40, producto=None)
    _venta(db, "V-2", 50, 60, producto="P1")
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).one().ventas_reales == Decimal("150.00")


def test_linea_id_sale_del_representante(escenario):
    """`DIM_Producto.linea_id` es nullable y el hecho puede no traer producto:
    la linea del RM es el unico origen fiable."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 100, producto=None)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).one().linea_id == escenario["rm"].linea_id


def test_reintegrar_no_duplica_ni_dobla_los_ingresos(escenario):
    """El test que justifica el mapeo: FACT_Ventas NO tiene llave natural, y el
    ROI SUMA ventas_reales -- duplicar seria inventar ingresos."""
    db = escenario["db"]
    _venta(db, "V-1", 500, 400)
    db.commit()
    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).count() == 1
    assert db.query(Ventas).one().ventas_reales == Decimal("500.00")


def test_adopta_una_fila_legacy_sin_mapeo(escenario):
    """En produccion hay 9 filas cargadas por el Excel legacy, sin mapeo. Se
    ADOPTAN por clave natural en vez de duplicarse."""
    db = escenario["db"]
    legacy = Ventas(pais_codigo="DO", linea_id=escenario["rm"].linea_id,
                    rm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                    ventas_reales=Decimal("1.00"), cuota=Decimal("1.00"))
    db.add(legacy)
    db.commit()
    legacy_id = legacy.id
    _venta(db, "V-1", 900, 800)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(Ventas).count() == 1
    v = db.query(Ventas).one()
    assert v.id == legacy_id                    # la misma fila, no una nueva
    assert v.ventas_reales == Decimal("900.00")


def test_cuotas_distintas_se_suman_sin_aviso(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 30)
    _venta(db, "V-2", 100, 70)
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).one().cuota == Decimal("100.00")
    assert hallazgos == []


def test_cuotas_identicas_se_suman_pero_avisan(escenario):
    """La firma de un ERP que repite el total del RM en cada fila de producto.
    Se suma igual (decision del cliente) pero se avisa: si esa fuera la causa,
    la cuota quedaria multiplicada por el numero de productos y el
    cumplimiento de TODOS se desplomaria sin que nada lo delatara."""
    db = escenario["db"]
    _venta(db, "V-1", 100, 500, producto="P1")
    _venta(db, "V-2", 200, 500, producto="P2")
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).one().cuota == Decimal("1000.00")   # se suma igual
    assert any(h.severidad == "aviso" and "cuota" in h.problema.lower()
               for h in hallazgos)


def test_una_sola_fila_nunca_dispara_el_aviso_de_cuota(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 500)
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert hallazgos == []


def test_lote_no_validado_no_entra(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 100)
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "RECHAZADO"
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).count() == 0
    assert any(h.severidad == "error" for h in hallazgos)


def test_rm_sin_sincronizar_se_omite_y_el_resto_entra(escenario):
    db = escenario["db"]
    _venta(db, "V-1", 100, 100, rm="VM01")
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               nombre="Sin mapeo", activo=True))
    db.flush()
    _venta(db, "V-2", 999, 999, rm="VM99")
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).count() == 1
    assert db.query(Ventas).one().ventas_reales == Decimal("100.00")
    assert any(h.severidad == "error" for h in hallazgos)


def test_ciclo_no_sincronizado_se_omite_con_hallazgo(escenario):
    """Rama simétrica a `test_rm_sin_sincronizar...`: si el CICLO no tiene
    mapeo (en vez del RM), el grupo se omite igual, con hallazgo de error, y
    no se escribe ninguna fila."""
    db = escenario["db"]
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C99-2026", anio=2026,
                       numero=99, fecha_inicio=date(2026, 12, 1),
                       fecha_fin=date(2026, 12, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtControlCarga(
        lote_id=1099, sistema_origen="SFA", modulo="VENTAS", pais_codigo="DO",
        ciclo_codigo="C99-2026", fecha_extraccion=datetime(2026, 12, 31, 20, 0),
        fecha_recepcion=datetime(2026, 12, 31, 21, 0), filas_enviadas=1,
        estado="VALIDADO"))
    db.flush()
    db.add(ExtFactVenta(
        lote_id=1099, origen_id="V-1", pais_codigo="DO",
        ciclo_codigo="C99-2026", rm_codigo="VM01", producto_codigo="P1",
        valor_venta=Decimal("100"), cuota=Decimal("100")))
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C99-2026", hallazgos)
    db.commit()

    assert db.query(Ventas).count() == 0
    assert any(h.severidad == "error" for h in hallazgos)


def test_lotes_multiples_del_mismo_rm_se_acreditan_todos(escenario):
    """El defecto Important de la ronda 1: agrupar por RM puede juntar filas
    de VARIOS lotes (un reenvio/correccion parcial de Mallen). Acreditar solo
    el lote de la primera fila dejaba al resto atascado en VALIDADO aunque sus
    datos SI se hubieran integrado -- `_cerrar_lotes` nunca los habria
    pasado a INTEGRADO.
    """
    db = escenario["db"]
    db.add(ExtControlCarga(
        lote_id=1002, sistema_origen="SFA", modulo="VENTAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="VALIDADO"))
    db.flush()
    _venta(db, "V-1", 100, 40, producto="P1", lote_id=1001)
    _venta(db, "V-2", 200, 60, producto="P2", lote_id=1002)
    db.commit()

    conteo = viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    assert conteo.lotes_aportados == {1001, 1002}
    assert db.query(Ventas).one().ventas_reales == Decimal("300.00")

    # Bonus: con ambos lotes acreditados, `_cerrar_lotes` (el consumidor real
    # de `lotes_aportados` dentro de `integrar_todo`) los pasa a INTEGRADO a
    # los dos -- no solo al que aporto la primera fila del grupo.
    cerrados = viz._cerrar_lotes(
        db, [1001, 1002], "Integrado en VISTA.", "C01-2026", conteo.lotes_aportados)
    db.commit()

    assert cerrados == [1001, 1002]
    estados = {row.lote_id: row.estado for row in
               db.query(ExtControlCarga).filter(
                   ExtControlCarga.lote_id.in_([1001, 1002])).all()}
    assert estados == {1001: "INTEGRADO", 1002: "INTEGRADO"}


def test_filas_legacy_duplicadas_generan_hallazgo_de_error(escenario):
    """IMPORTANT de la revisión final de rama: `FACT_Ventas` no tiene ningún
    UNIQUE y el ETL legacy de Excel es *append-only* (`etl_service.py` agrega
    una fila por cada fila del Excel, sin buscar ni deduplicar). Nada garantiza
    una sola fila legacy por RM/ciclo -- y como el ciclo es un biciclo mientras
    el Excel de ventas era mensual, dos filas por RM en el mismo `ciclo_id` es
    un escenario esperable, no exótico.

    `_buscar` hace `.first()`: adopta o actualiza UNA sola fila. Si hay más,
    quedan sumando en silencio al ROI un ingreso que ya no corresponde -- el
    daño exacto que `ENT_VENTAS_RM_CICLO` se creó para evitar, entrando por la
    puerta de los datos preexistentes en vez de por la de los reintentos.

    La comprobación no puede vivir dentro de `_buscar`: una vez que existe el
    mapeo, `integracion_mapeo.resolver` ya NO vuelve a llamar `buscar_natural`
    en las corridas siguientes, así que el aviso se emitiría una sola vez en
    la vida y nunca más aunque el duplicado siga ahí -- tiene que repetirse en
    cada corrida, fuera del callable `_buscar`.
    """
    db = escenario["db"]
    legacy1 = Ventas(pais_codigo="DO", linea_id=escenario["rm"].linea_id,
                     rm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                     ventas_reales=Decimal("100.00"), cuota=Decimal("100.00"))
    legacy2 = Ventas(pais_codigo="DO", linea_id=escenario["rm"].linea_id,
                     rm_id=escenario["rm"].id, ciclo_id=escenario["ciclo"].id,
                     ventas_reales=Decimal("200.00"), cuota=Decimal("100.00"))
    db.add_all([legacy1, legacy2])
    db.commit()
    _venta(db, "V-1", 700, 500)
    db.commit()
    hallazgos = []

    viz.integrar_ventas(db, "DO", "C01-2026", hallazgos)
    db.commit()

    # (b) no se borró nada: siguen las dos filas.
    filas = db.query(Ventas).filter(Ventas.rm_id == escenario["rm"].id).all()
    assert len(filas) == 2

    # (a) hay un hallazgo de severidad ERROR que menciona la duplicación.
    errores = [h for h in hallazgos if h.severidad == "error"]
    assert any("duplicad" in h.problema.lower() or "adicional" in h.problema.lower()
               for h in errores), errores

    # (c) una de ellas quedó con el monto de Mallén; la otra sigue con su
    # monto legacy original, intacta (no se tocó ni se sumó).
    montos = {v.ventas_reales for v in filas}
    assert Decimal("700.00") in montos
    assert montos == {Decimal("700.00"), Decimal("200.00")} or \
        montos == {Decimal("700.00"), Decimal("100.00")}


# --- Tarea 2: el indicador VENTAS (ext.factventa -> DW.FACT_ResultadoIndicador) ---


def _indicador_ventas(db):
    """VENTAS con escala=1 y ponderacion 15, igual que en produccion."""
    i = Indicador(pais_codigo="DO", codigo="VENTAS", nombre="Ventas vs Cuota",
                  modulo="RESULTADOS", tipo_periodo="MES", escala=1,
                  ponderacion_pct=15)
    db.add(i)
    db.flush()
    return i


def test_ventas_atraviesa_el_motor_y_puntua_bien(escenario):
    """EL test que faltó en el sub-proyecto 3: afirmar sobre `resultado_real`
    compara el valor consigo mismo. Lo que importa es qué PUNTOS salen al
    final, porque VENTAS tiene escala=1 y el motor multiplica por 100."""
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 88, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, escenario["ciclo"].id, "DO")

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("0.8800")      # FRACCION, no 88
    assert fila.resultado_porcentaje == Decimal("88.0000")
    assert fila.puntos_obtenidos == Decimal("13.2000")   # 88% de 15


def test_sobrecumplimiento_no_se_acota_en_el_dato_crudo(escenario):
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 120, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    motor_calculo_service.completar_puntajes(db, escenario["ciclo"].id, "DO")

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("1.2000")       # crudo, sin acotar
    assert fila.resultado_porcentaje == Decimal("100.0000")  # el motor sí acota


def test_venta_negativa_no_baja_de_cero(escenario):
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", -50, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").one())
    assert fila.resultado_real == Decimal("0.0000")


def test_sin_cuota_no_se_escribe_la_fila(escenario):
    """Dividir por cero no es cumplimiento cero: es ausencia de meta, y un 0
    penalizaria a un RM al que nadie le fijo cuota."""
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 500, 0)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").count()) == 0
    assert any(h.severidad == "aviso" for h in hallazgos)


def test_cuota_negativa_agregada_no_escribe_fila(escenario):
    """Minor 2 de la revisión final de rama: el guard original era
    `cuota is None or cuota == 0`. Con una cuota AGREGADA de -100 (posible,
    porque `total_cuota` es la SUMA de las filas del RM), pasaba de largo,
    `bruto` salía negativo y `max(bruto, 0)` escribía `resultado_real = 0` --
    justo lo que la regla "ausencia de meta no es cumplimiento cero" quería
    impedir: 0 es indistinguible de "cumplió 0%" y penaliza al representante.
    El guard debe ser `cuota <= 0`, no solo `== 0`."""
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 500, -100)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").count()) == 0
    assert any(h.severidad == "aviso" for h in hallazgos)


def test_sin_cuota_no_pisa_un_valor_anterior(escenario):
    """Al no escribirse, tampoco entra en el delete-then-insert: lo que hubiera
    cargado el Excel se conserva.

    Minor 1 de la Ronda de correcciones 1: se agrega un SEGUNDO RM con cuota
    VALIDA en la MISMA corrida (`VM02`), para que el delete-then-insert
    realmente se ejecute en esta llamada -- sin esto, la prueba pasaría igual
    con o sin la funcionalidad implementada, porque nunca habría ningún
    borrado real que demostrar (solo "no hubo borrado" desde el principio).
    """
    db = escenario["db"]
    i = _indicador_ventas(db)
    db.add(ResultadoIndicador(
        rm_id=escenario["rm"].id, pais_codigo="DO",
        linea_id=escenario["rm"].linea_id, ciclo_id=escenario["ciclo"].id,
        indicador_id=i.id, resultado_real=Decimal("0.9"), activo=True))
    _venta(db, "V-1", 500, 0)

    otro_rm = RepresentanteMedico(
        pais_codigo="DO", linea_id=escenario["rm"].linea_id,
        gerente_id=escenario["rm"].gerente_id, codigo="VM02",
        nombre="Representante Dos")
    db.add(otro_rm)
    db.flush()
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM02",
                               nombre="Representante Dos", activo=True))
    db.add(MapeoExterno(entidad=ENT_REPRESENTANTE, pais_codigo="DO",
                        codigo_externo="VM02", id_interno=otro_rm.id))
    _venta(db, "V-2", 80, 100, rm="VM02")
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS",
                    ResultadoIndicador.rm_id == escenario["rm"].id).one())
    assert fila.resultado_real == Decimal("0.9000")   # intacto, no borrado

    fila_otro = (db.query(ResultadoIndicador)
                 .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
                 .filter(Indicador.codigo == "VENTAS",
                         ResultadoIndicador.rm_id == otro_rm.id).one())
    assert fila_otro.resultado_real == Decimal("0.8000")  # el borrado SÍ ocurrió, para el otro RM


def test_prom_diario_no_se_calcula_ni_pisa_para_rm_solo_de_ventas(escenario):
    """Important de la Ronda de correcciones 1.

    `PROM_DIARIO` es el único indicador de este módulo SIN noción de
    universo: no pasa por `candidatos`, así que `_promedio_diario` siempre
    devuelve una tasa cruda, `0` incluido. Un RM cuya única fuente en el
    ciclo sea `ext.factventa` (el caso normal cuando ventas y visitas son
    feeds separados de Mallén que no llegan el mismo día) no tiene panel
    médico ni target de farmacias -- así que no pertenece al universo de
    visita, y su PROM_DIARIO real (el que cargó el feed de visitas en otra
    corrida) NO debe pisarse con un `0` solo porque esta corrida trae ventas.
    """
    db = escenario["db"]
    _indicador_ventas(db)
    prom = Indicador(pais_codigo="DO", codigo="PROM_DIARIO",
                     nombre="Promedio Diario de Visitas", modulo="RESULTADOS",
                     tipo_periodo="CICLO", escala=1, ponderacion_pct=10)
    db.add(prom)
    db.flush()
    db.add(ResultadoIndicador(
        rm_id=escenario["rm"].id, pais_codigo="DO",
        linea_id=escenario["rm"].linea_id, ciclo_id=escenario["ciclo"].id,
        indicador_id=prom.id, resultado_real=Decimal("0.75"), activo=True))
    _venta(db, "V-1", 88, 100)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila_ventas = (db.query(ResultadoIndicador)
                   .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
                   .filter(Indicador.codigo == "VENTAS").one())
    assert fila_ventas.resultado_real == Decimal("0.8800")  # VENTAS sí se calculó

    fila_prom = (db.query(ResultadoIndicador)
                 .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
                 .filter(Indicador.codigo == "PROM_DIARIO").one())
    assert fila_prom.resultado_real == Decimal("0.7500")   # intacto, NO pisado con 0


# --- Tarea 3: el circuito Mallen -> FACT_Ventas -> ROI (Visita) ---


def test_las_ventas_integradas_alimentan_el_roi(escenario):
    """El §7.2 pide que Ventas alimente «los ingresos del ROI». Este test cierra
    el circuito Mallen -> FACT_Ventas -> ROI de punta a punta."""
    db = escenario["db"]
    _venta(db, "V-1", 700, 500)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    r = visita_costo_service.roi(db, escenario["ciclo"].id, escenario["rm"].id)

    assert r["ingresos"] == 700.0


def test_el_roi_no_toma_ventas_de_otro_pais(escenario):
    """No prueba un arreglo: `DIM_Ciclo` YA lleva pais_codigo, asi que cada
    ciclo es de un solo pais y el ROI nunca pudo mezclar. Fija la propiedad
    para que nadie la rompa quitando el pais del ciclo."""
    db = escenario["db"]
    otro_pais = Pais(codigo="CR", nombre="Costa Rica")
    db.add(otro_pais)
    db.flush()
    otra_linea = Linea(pais_codigo="CR", codigo="CARD", nombre="Cardiologia")
    db.add(otra_linea)
    db.flush()
    otro_rm = RepresentanteMedico(pais_codigo="CR", linea_id=otra_linea.id,
                                  codigo="VM01-CR", nombre="RM de CR")
    otro_ciclo = Ciclo(pais_codigo="CR", anio=2026, numero=1, nombre="Ciclo 1",
                       fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                       dias_laborables=20, cerrado=False)
    db.add_all([otro_rm, otro_ciclo])
    db.flush()
    db.add(Ventas(pais_codigo="CR", linea_id=otra_linea.id, rm_id=otro_rm.id,
                  ciclo_id=otro_ciclo.id, ventas_reales=Decimal("9999.00"),
                  cuota=Decimal("1.00")))
    _venta(db, "V-1", 700, 500)
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()

    r = visita_costo_service.roi(db, escenario["ciclo"].id, None)

    assert r["ingresos"] == 700.0        # las de CR no se cuelan


# --- Revisión final de rama: puntos Minor 3 y 4 ---


def test_cumplimiento_pct_y_resultado_real_cuentan_la_misma_historia(escenario):
    """Minor 3: `integrar_ventas` (que rellena `FACT_Ventas.cumplimiento_pct`)
    y `_cumplimiento_ventas` (que produce el `resultado_real` del indicador
    VENTAS) agregan `ext.factventa` cada uno por su cuenta, en archivos
    distintos -- hoy dan el mismo número, pero nada avisará si mañana uno de
    los dos cambia y divergen. Se usan VARIAS filas de venta del mismo RM (no
    una sola), que es donde la agregación puede divergir de verdad.

    Este test debería pasar en verde a la primera (no hay comportamiento
    nuevo): lo que fija es la RELACIÓN entre las dos piezas.
    """
    db = escenario["db"]
    _indicador_ventas(db)
    _venta(db, "V-1", 30, 40, producto="P1")
    _venta(db, "V-2", 45, 60, producto="P2")
    db.commit()

    viz.integrar_ventas(db, "DO", "C01-2026", [])
    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    v = db.query(Ventas).filter(Ventas.rm_id == escenario["rm"].id).one()
    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS",
                    ResultadoIndicador.rm_id == escenario["rm"].id).one())

    # 75/100 = 75% en ambos caminos -- ni frontera de 100%, ni cero.
    assert v.cumplimiento_pct == Decimal("75.00")
    assert fila.resultado_real == Decimal("0.7500")
    assert v.cumplimiento_pct == fila.resultado_real * 100


def test_integrar_ventas_sobre_ciclo_cerrado_si_escribe_pero_el_indicador_no(escenario):
    """Minor 4: declara, a propósito, la asimetría entre los dos integradores
    de este sub-proyecto frente a un ciclo cerrado:

    - `integrar_ventas` (este módulo) NO tiene guard de ciclo cerrado, y es
      CORRECTO que no lo tenga: no borra nada -- solo actualiza/adopta/crea
      una fila de `FACT_Ventas` -- y los hechos entran siempre porque son
      historia (misma regla que los otros cuatro integradores de
      `_INTEGRADORES`, ninguno de los cuales tiene guard tampoco).
    - `calcular_indicadores` (`integracion_indicadores_service`) SÍ lo tiene,
      porque hace delete-then-insert sobre `FACT_ResultadoIndicador`: sin el
      guard, un ciclo cerrado perdería los `puntos_obtenidos` que ya calculó
      el motor, y el recálculo posterior los rechazaría sin reponerlos (el
      ciclo cerrado es un snapshot inmutable).

    Este test debería pasar en verde a la primera -- existe para que nadie
    "arregle" la ausencia de guard en `integrar_ventas` agregando uno por
    simetría con el indicador, en la dirección equivocada.
    """
    db = escenario["db"]
    _indicador_ventas(db)
    escenario["ciclo"].cerrado = True
    db.commit()
    _venta(db, "V-1", 700, 500)
    db.commit()

    conteo = viz.integrar_ventas(db, "DO", "C01-2026", [])
    db.commit()
    assert conteo.integrados == 1
    assert db.query(Ventas).filter(
        Ventas.rm_id == escenario["rm"].id).one().ventas_reales == Decimal("700.00")

    resumen = ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()
    assert resumen["omitido_ciclo_cerrado"] is True
    assert (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "VENTAS").count()) == 0
