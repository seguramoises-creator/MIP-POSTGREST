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
from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.hechos import Ventas
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimPais, ExtDimProducto, ExtDimRepresentante,
    ExtFactVenta,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.services import integracion_visitas_service as viz

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
    for tabla in ('"DW"."FACT_Ventas"', "ext.factventa", "ext.dimproducto",
                  '"Config"."MapeoExterno"', "ext.controlcarga",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
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
