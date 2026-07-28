"""Genera el script SQL del esquema `ext` que se entrega a Laboratorio Mallen.

Se genera DESDE LOS MODELOS, nunca a mano: el script del cliente y el esquema
que VISTA crea en produccion tienen que ser el mismo, o Mallen desarrollaria su
carga contra una estructura que no es la real. `tests/test_integracion_ext.py`
vuelve a generarlo y lo compara con el archivo versionado, asi que un cambio en
los modelos que no se regenere aqui rompe la suite.

    python scripts/integracion/generar_ddl_ext.py
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402
from sqlalchemy.dialects import postgresql  # noqa: E402

from app.db.database import Base  # noqa: E402
from app.models import integracion_ext  # noqa: F401,E402

DESTINO = Path(__file__).with_name("crear_esquema_ext.sql")

CABECERA = """\
-- ===========================================================================
-- VISTA · Laboratorios Mallen — esquema de recepcion de datos `ext`
-- ===========================================================================
-- Requerimiento de Datos v1.0 (25-jul-2026), secciones 3 a 6.
-- PostgreSQL 17.
--
-- Mallen ESCRIBE en estas 22 tablas; VISTA las LEE y desde ahi alimenta sus
-- estructuras internas. VISTA nunca se conecta al SQL Server de Mallen.
--
-- Este archivo lo genera scripts/integracion/generar_ddl_ext.py a partir de los
-- modelos de la aplicacion: es exactamente el esquema que corre en produccion.
-- No editarlo a mano.
--
-- TRES DIFERENCIAS RESPECTO AL DDL IMPRESO EN EL DOCUMENTO
-- --------------------------------------------------------
-- 1. Los nombres van en MINUSCULAS y sin comillas. El documento crea las tablas
--    sin comillas (`CREATE TABLE ext.DimPais`, que PostgreSQL pliega a
--    `ext.dimpais`) pero luego las referencia entrecomilladas en las claves
--    foraneas y los indices (`ext."DimPais"`, que exige ese uso exacto de
--    mayusculas); corridas en ese orden, las sentencias de la seccion 6.4
--    fallan con "no existe la relacion". Se unifico sin comillas porque asi
--    `ext.DimPais`, `ext.dimpais` y `EXT.DIMPAIS` funcionan las tres desde
--    cualquier herramienta.
-- 2. Se incluyen las claves foraneas que el documento omite "por brevedad"
--    (seccion 6.4, ultima nota): lote_id, ciclo y representante en el resto de
--    las tablas de hecho.
-- 3. Se incluyen los indices unicos (pais_codigo, origen_id) de
--    factevaluacionconocimiento y factprescripciondetalle. La seccion 5.2 exige
--    idempotencia para TODOS los hechos, pero la 6.5 solo los declaraba para
--    tres: sin ellos, reenviar uno de esos dos lotes duplicaria filas.
--
-- Los dominios acotados (tipo_visita, frecuencia_objetivo, prioridad, estado)
-- NO llevan CHECK a proposito: la seccion 7.1 pide que las inconsistencias se
-- registren "sin detener el lote completo", y un CHECK rechazaria la fila
-- entera. VISTA valida esos dominios al integrar y deja constancia.
-- ===========================================================================

CREATE SCHEMA IF NOT EXISTS ext;
"""

PIE = """

-- ===========================================================================
-- Usuario de integracion — ver crear_usuario_mallen.sql
-- ===========================================================================
"""


def generar() -> str:
    dialecto = postgresql.dialect()
    tablas = [t for t in Base.metadata.sorted_tables if t.schema == "ext"]
    partes = [CABECERA]

    partes.append("\n-- --- Tablas (en orden de dependencia) ---")
    for t in tablas:
        ddl = str(CreateTable(t).compile(dialect=dialecto)).strip()
        partes.append(f"\n{ddl};")

    partes.append("\n\n-- --- Indices ---")
    for t in tablas:
        for idx in sorted(t.indexes, key=lambda i: i.name):
            partes.append(f"\n{str(CreateIndex(idx).compile(dialect=dialecto)).strip()};")

    partes.append(PIE)
    return "\n".join(partes).replace("\r\n", "\n") + ""


if __name__ == "__main__":
    DESTINO.write_text(generar(), encoding="utf-8", newline="\n")
    print(f"generado: {DESTINO}")
    print(f"tablas: {len([t for t in Base.metadata.sorted_tables if t.schema == 'ext'])}")
