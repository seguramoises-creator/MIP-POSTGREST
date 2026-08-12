"""Equivalencias del módulo IR: prescriptor, producto y período.

Este sub-proyecto NO construye el indicador EVO_IR: construye los tres puentes
que la atribución necesita y mide qué tan bien resuelven. Ver el diseño en
`docs/superpowers/specs/2026-08-11-integracion-mallen-ir-equivalencias-design.md`.

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
from app.models.dimensiones import (
    Ciclo, Gerente, Linea, Medico, Pais, Producto, RepresentanteMedico,
)
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedicoIR, ExtDimPais, ExtDimPeriodoIR,
    ExtDimProducto, ExtDimProductoIR, ExtDimRepresentante, ExtFactPrescripcionDetalle,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.models.visita import MedicoVisita
from app.services import integracion_ir_service as ir

BD_PRUEBA = "vista_test_ir"


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
    for tabla in ("ext.factprescripciondetalle", "ext.dimmedicoir",
                  "ext.dimproductoir", "ext.dimperiodoir",
                  "ext.dimproducto", "ext.controlcarga",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Visita"."DIM_MedicoVisita"',
                  '"Config"."MapeoExterno"', '"Config"."DIM_Medico"',
                  '"Config"."DIM_Producto"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """País, línea, un representante, un ciclo y su equivalente en `ext`.

    Deja también el mapeo de ciclo y representante ya resuelto, como si el
    sub-proyecto 2 hubiera corrido: los puentes del IR se apoyan en él.
    """
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
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             gerente_id=gerente.id, codigo="VM01",
                             nombre="Representante Uno")
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
    db.add(ExtControlCarga(
        lote_id=2001, sistema_origen="CLOSEUP", modulo="IR", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="VALIDADO"))
    db.flush()
    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id)):
        db.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                            codigo_externo=codigo, id_interno=interno))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo, "linea": linea}


def _medico_maestro(db, nombre="MEDICO UNO", exequatur="EX-100"):
    m = Medico(pais_codigo="DO", nombre=nombre, exequatur=exequatur, activo=True)
    db.add(m)
    db.flush()
    return m


def _medico_ir(db, medico_ir_codigo="MIR-1", exequatur="EX-100",
               nombre="MEDICO UNO"):
    db.add(ExtDimMedicoIR(pais_codigo="DO", medico_ir_codigo=medico_ir_codigo,
                          nombre=nombre, exequatur=exequatur, activo=True))
    db.flush()


def _producto_ir(db, producto_ir_codigo="PIR-1", producto_codigo="P1",
                 es_propio=True):
    # ext.dimproductoir.producto_codigo tiene FK hacia ext.dimproducto (el
    # catálogo de Mallén en el propio esquema `ext`, distinto de
    # Config.DIM_Producto): hay que poblarlo o el insert de la fixture viola
    # la FK. No estaba en el brief; es solo wiring del dato externo, no una
    # decisión de negocio.
    if producto_codigo and db.get(ExtDimProducto, ("DO", producto_codigo)) is None:
        db.add(ExtDimProducto(pais_codigo="DO", producto_codigo=producto_codigo,
                              nombre=f"Producto ext {producto_codigo}",
                              activo=True))
        db.flush()
    db.add(ExtDimProductoIR(pais_codigo="DO", producto_ir_codigo=producto_ir_codigo,
                            nombre=f"Producto {producto_ir_codigo}",
                            producto_codigo=producto_codigo,
                            es_propio=es_propio, activo=True))
    db.flush()


def _periodo_ir(db, periodo_codigo="2026-01", ciclo_codigo="C01-2026"):
    db.add(ExtDimPeriodoIR(pais_codigo="DO", periodo_codigo=periodo_codigo,
                           anio=2026, mes=1, fecha_inicio=date(2026, 1, 1),
                           fecha_fin=date(2026, 1, 31),
                           ciclo_codigo=ciclo_codigo, cerrado=False))
    db.flush()


def _conteo(resultado, entidad):
    return next(c for c in resultado["entidades"] if c["entidad"] == entidad)


# ── Puente del prescriptor ───────────────────────────────────────────────

def test_prescriptor_con_exequatur_en_el_maestro_se_enlaza(escenario):
    db = escenario["db"]
    medico = _medico_maestro(db, exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_MEDICO_IR,
                 MapeoExterno.codigo_externo == "MIR-1").one())
    assert m.id_interno == medico.id
    assert _conteo(r, ir.ENT_MEDICO_IR)["enlazados"] == 1


def test_prescriptor_sin_contraparte_NO_crea_medico(escenario):
    """El test que protege los denominadores de cobertura y categorización:
    un prescriptor que ningún representante trabaja no debe entrar al maestro."""
    db = escenario["db"]
    _medico_ir(db, "MIR-9", exequatur="EX-999")
    db.commit()
    antes = db.query(Medico).count()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(Medico).count() == antes
    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    assert _conteo(r, ir.ENT_MEDICO_IR)["no_enlazados"] == 1


def test_exequatur_que_solo_difiere_en_formato_es_casi_enlace(escenario):
    """NO se enlaza: el maestro compara exacto y aquí no se inventa una
    normalización privada. Se cuenta aparte para que sea accionable."""
    db = escenario["db"]
    _medico_maestro(db, exequatur="12345")
    _medico_ir(db, "MIR-2", exequatur="12.345")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    c = _conteo(r, ir.ENT_MEDICO_IR)
    assert c["no_enlazados"] == 1
    assert c["casi_enlazados"] == 1


def test_cien_huerfanos_no_producen_hallazgos(escenario):
    """dimmedicoir trae TODO el mercado: un hallazgo por fila dejaría la
    pantalla inservible y enterraría los pocos que sí exigen acción."""
    db = escenario["db"]
    for i in range(100):
        _medico_ir(db, f"MIR-{i}", exequatur=f"EX-{i}", nombre=f"MEDICO {i}")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert _conteo(r, ir.ENT_MEDICO_IR)["no_enlazados"] == 100
    assert [h for h in r["hallazgos"] if h["entidad"] == ir.ENT_MEDICO_IR] == []


def test_exequatur_duplicado_en_el_maestro_no_enlaza_y_avisa(escenario):
    """Dos médicos con el mismo exequátur impiden decidir a cuál enlazar. Es un
    defecto del maestro, acotado, y por eso SÍ genera hallazgo."""
    db = escenario["db"]
    _medico_maestro(db, nombre="MEDICO UNO", exequatur="EX-100")
    _medico_maestro(db, nombre="MEDICO DOS", exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    errores = [h for h in r["hallazgos"]
               if h["entidad"] == ir.ENT_MEDICO_IR and h["severidad"] == "error"]
    assert len(errores) == 1


# ── Puente del producto ──────────────────────────────────────────────────

def test_producto_propio_con_equivalencia_se_enlaza(escenario):
    db = escenario["db"]
    p = Producto(codigo="P1", nombre="Producto Uno",
                 linea_id=escenario["linea"].id, activo=True)
    db.add(p)
    db.flush()
    _producto_ir(db, "PIR-1", producto_codigo="P1", es_propio=True)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_PRODUCTO_IR,
                 MapeoExterno.codigo_externo == "PIR-1").one())
    assert m.id_interno == p.id
    assert _conteo(r, ir.ENT_PRODUCTO_IR)["enlazados"] == 1


def test_producto_de_competencia_se_omite_SIN_hallazgo(escenario):
    """Los productos de otros laboratorios existen a propósito (§11.8): hacen
    falta para medir participación de mercado. Que no mapeen es lo esperado."""
    db = escenario["db"]
    _producto_ir(db, "PIR-C", producto_codigo=None, es_propio=False)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    c = _conteo(r, ir.ENT_PRODUCTO_IR)
    assert c["omitidos"] == 1
    assert c["no_enlazados"] == 0
    assert [h for h in r["hallazgos"] if h["entidad"] == ir.ENT_PRODUCTO_IR] == []


def test_producto_propio_sin_equivalencia_es_error(escenario):
    """Un producto de Mallén cuyas recetas nadie va a poder contar."""
    db = escenario["db"]
    _producto_ir(db, "PIR-X", producto_codigo=None, es_propio=True)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    errores = [h for h in r["hallazgos"]
               if h["entidad"] == ir.ENT_PRODUCTO_IR and h["severidad"] == "error"]
    assert len(errores) == 1
    assert _conteo(r, ir.ENT_PRODUCTO_IR)["no_enlazados"] == 1


# ── Puente del período ───────────────────────────────────────────────────

def test_periodo_con_ciclo_se_enlaza(escenario):
    db = escenario["db"]
    _periodo_ir(db, "2026-01", ciclo_codigo="C01-2026")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_PERIODO_IR,
                 MapeoExterno.codigo_externo == "2026-01").one())
    assert m.id_interno == escenario["ciclo"].id
    assert _conteo(r, ir.ENT_PERIODO_IR)["enlazados"] == 1


def test_periodo_sin_ciclo_avisa_y_no_se_enlaza(escenario):
    db = escenario["db"]
    _periodo_ir(db, "2026-02", ciclo_codigo=None)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_PERIODO_IR).count() == 0
    avisos = [h for h in r["hallazgos"]
              if h["entidad"] == ir.ENT_PERIODO_IR and h["severidad"] == "aviso"]
    assert len(avisos) == 1


def test_resincronizar_no_duplica_mapeos(escenario):
    db = escenario["db"]
    _medico_maestro(db, exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    _periodo_ir(db, "2026-01", ciclo_codigo="C01-2026")
    db.commit()

    ir.sincronizar_ir(db, "DO")
    r2 = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 1
    # La segunda corrida ya no crea el mapeo: lo encuentra.
    assert _conteo(r2, ir.ENT_MEDICO_IR)["enlazados"] == 0
    assert _conteo(r2, ir.ENT_MEDICO_IR)["ya_enlazados"] == 1
