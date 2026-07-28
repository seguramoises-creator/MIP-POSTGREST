"""Esquema `ext` — contrato de integración con Laboratorio Mallén.

Estas pruebas cuidan un contrato con un TERCERO. No prueban lógica de negocio:
prueban que la estructura que Mallén va a recibir sigue siendo la que se acordó,
porque un cambio silencioso aquí rompe la carga de otra empresa y se descubre
tarde, en su ambiente, no en el nuestro.

No necesitan base de datos: leen la metadata de SQLAlchemy, que es la misma
fuente de la que salen la migración y el script SQL que se entrega.
"""
import re
from pathlib import Path

import pytest

from app.db.database import Base
from app.models import integracion_ext  # noqa: F401

RAIZ = Path(__file__).resolve().parents[1]

TABLAS = {n.split(".", 1)[1]: t for n, t in Base.metadata.tables.items()
          if n.startswith("ext.")}

# Hechos que llevan origen_id: la sección 5.2 exige que reenviar un lote no
# duplique, y eso lo garantiza el único sobre (pais_codigo, origen_id).
HECHOS_CON_ORIGEN = [
    "factvisitamedico", "factvisitafarmacia", "factventa",
    "factevaluacionconocimiento", "factprescripciondetalle",
]


def test_son_las_22_tablas_del_documento():
    """Nueve dimensiones + cinco del módulo IR + ocho de movimientos."""
    assert len(TABLAS) == 22, sorted(TABLAS)
    esperadas = {
        "dimpais", "dimlinea", "dimgerente", "dimrepresentante", "dimciclo",
        "dimespecialidad", "dimmedico", "dimfarmacia", "dimproducto",
        "dimperiodoir", "dimmercadoir", "dimproductoir", "dimmedicoir", "dimterritorio",
        "controlcarga", "panelmedico", "factvisitamedico", "targetfarmacia",
        "factvisitafarmacia", "factventa", "factevaluacionconocimiento",
        "factprescripciondetalle",
    }
    assert set(TABLAS) == esperadas


def test_los_nombres_van_en_minusculas():
    """Si un nombre llevara mayúsculas, PostgreSQL exigiría comillas en CADA
    referencia y `INSERT INTO ext.DimPais` fallaría desde las herramientas de
    Mallén. Es la decisión que resuelve la contradicción del DDL del documento,
    donde las tablas se crean sin comillas pero se referencian con ellas."""
    con_mayusculas = [n for n in TABLAS if n != n.lower()]
    assert not con_mayusculas, con_mayusculas


@pytest.mark.parametrize("tabla", sorted(
    n for n, t in TABLAS.items() if len(t.primary_key.columns) > 1))
def test_la_clave_primaria_compuesta_empieza_por_pais(tabla):
    """El documento define `PRIMARY KEY (pais_codigo, ...)`. No es cosmético:
    el índice de la clave solo sirve para filtrar por país —la consulta más
    frecuente en un sistema multipaís— si `pais_codigo` va primero."""
    primera = list(TABLAS[tabla].primary_key.columns)[0].name
    assert primera == "pais_codigo"


@pytest.mark.parametrize("tabla", HECHOS_CON_ORIGEN)
def test_cada_hecho_es_idempotente_por_origen(tabla):
    """Sección 5.2: reenviar un lote corregido no puede duplicar filas.

    La sección 6.5 del documento solo declaraba este índice para tres de los
    cinco hechos; se añadió para los otros dos, que si no duplicarían en
    silencio al reenviar un período."""
    t = TABLAS[tabla]
    assert "origen_id" in t.c, f"{tabla} no tiene origen_id"
    unicos = [{c.name for c in i.columns} for i in t.indexes if i.unique]
    assert {"pais_codigo", "origen_id"} in unicos, f"{tabla}: únicos = {unicos}"


def test_el_exequatur_del_prescriptor_es_obligatorio_y_unico():
    """Es la llave que lleva la receta de Close-Up al panel del representante.
    Si dos prescriptores compartieran exequátur, la receta se atribuiría al
    representante equivocado (§3.2)."""
    t = TABLAS["dimmedicoir"]
    assert t.c.exequatur.nullable is False
    unicos = [{c.name for c in i.columns} for i in t.indexes if i.unique]
    assert {"pais_codigo", "exequatur"} in unicos


def test_el_exequatur_del_maestro_es_unico_pero_opcional():
    """En el maestro de médicos el índice es PARCIAL —solo donde el exequátur
    está informado— para no bloquear la carga mientras el dato falte en algunos
    médicos, que hoy es el caso (pendiente 6 de §10)."""
    t = TABLAS["dimmedico"]
    assert t.c.exequatur.nullable is True
    parcial = [i for i in t.indexes
               if i.unique and i.dialect_options["postgresql"].get("where") is not None]
    assert parcial, "el único sobre exequátur debe ser parcial"


def test_la_prioridad_del_panel_es_obligatoria():
    """Regla de negocio nueva (§3.4): un panel con la prioridad incompleta se
    rechaza, porque sin ella no se sabe qué médicos son de visita obligatoria y
    las alertas de TOP nunca se disparan."""
    assert TABLAS["panelmedico"].c.prioridad.nullable is False


def test_no_hay_check_en_los_dominios_acotados():
    """Decisión deliberada, no un olvido. Un CHECK rechazaría la fila entera, y
    §7.1 pide lo contrario: las inconsistencias se registran «sin detener el
    lote completo». El dominio se valida al integrar."""
    con_check = [n for n, t in TABLAS.items()
                 if any(type(c).__name__ == "CheckConstraint" for c in t.constraints)]
    assert not con_check, con_check


def test_todo_hecho_esta_amarrado_a_su_lote():
    """`ControlCarga` es lo que permite reconciliar y repetir una carga. Un
    hecho sin lote no se podría rastrear ni reintegrar (§3.3)."""
    for nombre in HECHOS_CON_ORIGEN + ["panelmedico", "targetfarmacia"]:
        t = TABLAS[nombre]
        destinos = {fk.column.table.name for fk in t.foreign_keys}
        assert "controlcarga" in destinos, f"{nombre} no referencia ControlCarga"


def test_el_sql_entregado_al_cliente_coincide_con_los_modelos():
    """El script que Mallén replica en su ambiente y el esquema que corre en
    producción tienen que ser el mismo: si divergen, Mallén desarrollaría su
    carga contra una estructura que no existe.

    Si esta prueba falla, regenerar:
        python scripts/integracion/generar_ddl_ext.py
    """
    import sys
    sys.path.insert(0, str(RAIZ / "scripts" / "integracion"))
    import generar_ddl_ext

    archivo = RAIZ / "scripts" / "integracion" / "crear_esquema_ext.sql"
    assert archivo.exists(), "falta el script de entrega"
    esperado = generar_ddl_ext.generar().replace("\r\n", "\n")
    actual = archivo.read_text(encoding="utf-8").replace("\r\n", "\n")
    assert actual == esperado, "el .sql quedó desincronizado de los modelos"


def test_el_usuario_de_integracion_no_puede_borrar():
    """Sección 8.2: una corrección se hace reenviando con el mismo origen_id,
    nunca borrando, para que la trazabilidad quede intacta. Y los permisos por
    defecto son imprescindibles: sin ellos, una tabla añadida después nace sin
    permisos y la carga falla con «permiso denegado»."""
    sql = (RAIZ / "scripts" / "integracion" / "crear_usuario_mallen.sql").read_text(encoding="utf-8")
    concesiones = re.findall(r"^GRANT\s+([A-Z, ]+?)\s+ON", sql, re.M)
    assert concesiones, "el script no concede nada"
    assert not any("DELETE" in c for c in concesiones), concesiones
    assert "ALTER DEFAULT PRIVILEGES" in sql
