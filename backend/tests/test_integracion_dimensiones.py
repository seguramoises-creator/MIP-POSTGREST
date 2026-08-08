"""Sincronización de dimensiones `ext` → catálogos internos de VISTA.

Lo que estas pruebas cuidan por encima de todo: que sincronizar NO duplique el
maestro que VISTA ya tiene cargado, y que no toque el estado `cerrado` de un
ciclo (del que dependen recálculos y premios).

Necesita PostgreSQL real: cruza dos esquemas con claves compuestas e índices
únicos.
"""
from datetime import date

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
from app.models.dimensiones import (
    CentroMedico, Especialidad, Farmacia, Medico, Municipio, Producto, Provincia,
)
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.models.integracion_ext import (
    ExtDimEspecialidad, ExtDimFarmacia, ExtDimMedico, ExtDimProducto,
)
from app.services import integracion_dimensiones_service as dim

BD_PRUEBA = "vista_test_dimensiones"


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
    for tabla in ('"Config"."DIM_Medico"', '"Config"."DIM_CentroMedico"',
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
    """País y línea en AMBOS lados: el punto de partida de todo el resto."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    db.add(ExtDimLinea(pais_codigo="DO", linea_codigo="CARD",
                       nombre="Cardiología", activo=True))
    db.commit()
    return db


def test_adopta_el_representante_que_vista_ya_tenia(base):
    """El caso de la primera corrida en producción.

    VISTA lleva el piloto con 48 representantes cargados por Excel. Si la
    sincronización no los adoptara, quedarían 96.
    """
    db = base
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    db.add(RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                               codigo="VM01", nombre="Representante Uno"))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               linea_codigo="CARD", nombre="Representante Uno",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1     # NO se duplicó


def test_crea_el_representante_que_no_existia(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo Representante",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    rm = db.query(RepresentanteMedico).one()
    assert rm.codigo == "VM99"
    assert rm.linea_id is not None      # resolvió la FK contra la línea mapeada


def test_no_toca_el_estado_cerrado_del_ciclo(base):
    """Decisión del cliente: el abrir/cerrar de un ciclo es de VISTA.

    De `cerrado` dependen los recálculos y los premios; que un envío externo
    reabra un ciclo cerrado dispararía cálculos sobre datos históricos.
    """
    db = base
    db.add(Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                 fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                 dias_laborables=22, cerrado=False))
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, nombre="Ciclo 1 Mallén",
                       fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                       dias_laborables=20, cerrado=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_ciclo(db, "DO", hallazgos)
    db.commit()

    ciclo = db.query(Ciclo).one()
    assert ciclo.cerrado is False                  # sigue abierto: manda VISTA
    assert ciclo.dias_laborables == 20             # lo demás sí se sincroniza
    assert conteo.adoptados == 1
    assert any(h.severidad == dim.SEVERIDAD_AVISO for h in hallazgos)


def test_codigo_demasiado_largo_se_omite_sin_truncar(base):
    """DIM_Gerente.codigo es String(20) y ext permite 30.

    Truncar juntaría dos códigos distintos que compartan los primeros 20
    caracteres, que es peor que no cargar la fila.
    """
    db = base
    db.add(ExtDimGerente(pais_codigo="DO",
                         gerente_codigo="GER-DISTRITO-NORTE-2026-A",
                         nombre="Gerente Norte", tipo="DISTRITO", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_gerente(db, "DO", hallazgos)
    db.commit()

    assert conteo.omitidos == 1
    assert conteo.creados == 0
    assert db.query(Gerente).count() == 0
    assert any(h.severidad == dim.SEVERIDAD_ERROR for h in hallazgos)


def test_sincronizar_dos_veces_no_duplica(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)
    dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1


def test_especialidad_se_adopta_por_nombre(base):
    """DIM_Especialidad no tiene código: su identidad es el nombre."""
    db = base
    db.add(Especialidad(nombre="Cardiología"))
    db.add(ExtDimEspecialidad(especialidad_codigo="CARD", nombre="cardiología",
                              activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_especialidad(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Especialidad).count() == 1     # no duplicó por may/minúsculas


def test_medico_crea_sus_catalogos_auxiliares(base):
    """`ext` trae centro, provincia y municipio como TEXTO; DIM_Medico los
    referencia por FK. Se crean al vuelo en vez de descartar el dato."""
    db = base
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", especialidad_codigo=None,
                        centro_trabajo="Clínica Central", provincia="Santo Domingo",
                        municipio="Distrito Nacional", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    medico = db.query(Medico).one()
    assert medico.provincia_id is not None
    assert medico.municipio_id is not None
    assert medico.centro_medico_id is not None
    assert db.query(Provincia).one().nombre == "Santo Domingo"
    assert db.query(Municipio).one().nombre == "Distrito Nacional"
    assert db.query(CentroMedico).one().nombre == "Clínica Central"


def test_medico_se_adopta_por_exequatur(base):
    """Si el código no coincide pero el exequátur sí, es la misma persona: el
    exequátur es el identificador profesional único."""
    db = base
    db.add(Medico(pais_codigo="DO", codigo="VIEJO-01", nombre="Doctor Uno",
                  exequatur="EX-123"))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", exequatur="EX-123", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Medico).count() == 1


def test_farmacia_se_crea_como_maestro_oficial(base):
    """Viene del sistema oficial, no de un VM pidiendo alta: entra aprobada y
    con origen CONFIG. `direccion` y `encargado` son NOT NULL y `ext` no los
    envía, así que quedan vacíos para completarse en VISTA."""
    db = base
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    f = db.query(Farmacia).one()
    assert f.origen == "CONFIG"
    assert f.estado == "APROBADA"
    assert f.nombre_completo == "Farmacia Central"


def test_farmacia_no_pisa_lo_que_vista_completo(base):
    """`direccion` y `encargado` los enriquece VISTA y `ext` no los conoce."""
    db = base
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()
    f = db.query(Farmacia).one()
    f.direccion = "Av. Principal 100"
    f.encargado = "Ana Pérez"
    db.commit()

    dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    f = db.query(Farmacia).one()
    assert f.direccion == "Av. Principal 100"
    assert f.encargado == "Ana Pérez"


def test_producto_se_sincroniza_sin_pisar_campos_de_vista(base):
    """`area_terapeutica` y compañía son de VISTA; `ext` no los conoce."""
    db = base
    db.add(Producto(codigo="ONCX-301", nombre="Producto Viejo",
                    area_terapeutica="Oncología"))
    db.add(ExtDimProducto(pais_codigo="DO", producto_codigo="ONCX-301",
                          nombre="Producto Nuevo", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_producto(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    p = db.query(Producto).one()
    assert p.nombre == "Producto Nuevo"            # sí se sincroniza
    assert p.area_terapeutica == "Oncología"       # no se pisa


def test_sincronizar_todo_devuelve_las_nueve_dimensiones(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()

    r = dim.sincronizar_todo(db, "DO")

    assert r["pais_codigo"] == "DO"
    assert len(r["dimensiones"]) == 9
    entidades = [d["entidad"] for d in r["dimensiones"]]
    assert entidades == list(dim.ENTIDADES)          # y en orden de dependencia
    rep = next(d for d in r["dimensiones"] if d["entidad"] == "representante")
    assert rep["creados"] == 1


def test_sincronizar_todo_es_idempotente(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()
    dim.sincronizar_todo(db, "DO")

    r = dim.sincronizar_todo(db, "DO")

    rep = next(d for d in r["dimensiones"] if d["entidad"] == "representante")
    assert rep["creados"] == 0
    assert rep["actualizados"] == 1
    assert db.query(RepresentanteMedico).count() == 1


def test_resumen_cuenta_ext_y_mapeadas(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()
    dim.sincronizar_todo(db, "DO")

    filas = dim.resumen_dimensiones(db, "DO")

    rep = next(f for f in filas if f["entidad"] == "representante")
    assert rep["en_ext"] == 1
    assert rep["mapeadas"] == 1


# ===========================================================================
# Revisión final — 7 hallazgos (2 críticos)
# ===========================================================================

def test_medico_categorizacion_se_adopta_por_nombre_y_centro(base):
    """C1. Universo Categorización/Panel: identidad = (pais, nombre, centro),
    con `codigo` NULL en VISTA. Sin el tercer intento de búsqueda por
    nombre+centro, esta fila se duplicaría —o, si el centro coincidiera,
    reventaría `UQ_Medico_Pais_Nombre_Centro` y con ella la sincronización
    completa de las nueve dimensiones."""
    db = base
    centro = CentroMedico(pais_codigo="DO", nombre="Clinica Abreu")
    db.add(centro)
    db.flush()
    db.add(Medico(pais_codigo="DO", codigo=None, nombre="Juan Perez",
                  centro_medico_id=centro.id))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Juan Perez", centro_trabajo="Clinica Abreu",
                        activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Medico).count() == 1


def test_medico_categorizacion_se_adopta_pese_a_acentos_y_espacios(base):
    """C1-bis. La comparación usa `maestro_medico_service.normalizar_nombre`
    (quita acentos, colapsa espacios), no el `_norm` local del módulo, que solo
    hace `casefold`."""
    db = base
    centro = CentroMedico(pais_codigo="DO", nombre="Clinica Abreu")
    db.add(centro)
    db.flush()
    db.add(Medico(pais_codigo="DO", codigo=None, nombre="Juan Pérez",
                  centro_medico_id=centro.id))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="JUAN  PEREZ", centro_trabajo="Clinica Abreu",
                        activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Medico).count() == 1


def test_farmacia_con_acento_se_adopta(base):
    """C2. VISTA guarda `nombre_completo` normalizado (sin acentos, mayúsculas);
    `ext` manda el nombre con tilde tal cual lo tiene Mallén. Comparar con el
    `_norm` local (que no quita acentos) nunca empataría."""
    db = base
    db.add(Farmacia(pais_codigo="DO", es_cadena=False,
                    nombre_completo="FARMACIA SAN JOSE",
                    direccion="", encargado="", estado="APROBADA",
                    origen="CONFIG"))
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia San José", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Farmacia).count() == 1


def test_farmacia_adoptada_no_pisa_nombre_completo_normalizado(base):
    """I5. `nombre_completo` solo se fija al CREAR: una fila adoptada no debe
    perder el valor que el maestro ya guardaba normalizado (o derivado de
    cadena+sucursal)."""
    db = base
    db.add(Farmacia(pais_codigo="DO", es_cadena=True, cadena="Cadena X",
                    sucursal="Sucursal Y", nombre_completo="CADENA X SUCURSAL Y",
                    direccion="Av. Principal 1", encargado="Juan Pérez",
                    estado="APROBADA", origen="CONFIG"))
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="cadena x sucursal y", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    f = db.query(Farmacia).one()
    assert f.nombre_completo == "CADENA X SUCURSAL Y"


def test_representante_no_secuestra_el_codigo_de_otro_pais(base):
    """I3. `DIM_RM.codigo` es único GLOBAL. Sin el guard, un `VM01` de Panamá
    sobrescribiría el nombre y la línea del `VM01` dominicano existente."""
    db = base
    linea_do = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea_do)
    db.flush()
    rm_do = RepresentanteMedico(pais_codigo="DO", linea_id=linea_do.id,
                                codigo="VM01", nombre="Representante DO")
    db.add(rm_do)
    db.commit()
    linea_id_do = rm_do.linea_id

    db.add(Pais(codigo="PA", nombre="Panamá"))
    db.add(ExtDimPais(pais_codigo="PA", nombre="Panamá", activo=True))
    db.flush()
    db.add(ExtDimLinea(pais_codigo="PA", linea_codigo="CARD",
                       nombre="Cardiología", activo=True))
    db.add(ExtDimRepresentante(pais_codigo="PA", rm_codigo="VM01",
                               linea_codigo="CARD", nombre="Representante PA",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "PA", hallazgos)

    conteo = dim.sincronizar_representante(db, "PA", hallazgos)
    db.commit()

    rm_do_recargado = db.query(RepresentanteMedico).filter_by(codigo="VM01").one()
    assert rm_do_recargado.pais_codigo == "DO"
    assert rm_do_recargado.nombre == "Representante DO"    # no se pisó
    assert rm_do_recargado.linea_id == linea_id_do          # no se pisó
    assert conteo.omitidos == 1
    assert conteo.creados == 0
    assert conteo.adoptados == 0
    assert any(h.severidad == dim.SEVERIDAD_ERROR for h in hallazgos)


def test_producto_nombre_demasiado_largo_se_omite_sin_reventar(base):
    """I4. `dimproducto.nombre` permite 200 caracteres en `ext` y
    `DIM_Producto.nombre` solo 120: sin el chequeo, la fila revienta con un
    error de la base de datos en vez de dejar un Hallazgo y seguir."""
    db = base
    nombre_largo = "P" * 150
    db.add(ExtDimProducto(pais_codigo="DO", producto_codigo="PRD01",
                          nombre=nombre_largo, activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_producto(db, "DO", hallazgos)
    db.commit()

    assert conteo.omitidos == 1
    assert conteo.creados == 0
    assert db.query(Producto).count() == 0
    assert any(h.severidad == dim.SEVERIDAD_ERROR for h in hallazgos)
