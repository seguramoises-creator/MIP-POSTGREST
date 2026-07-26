"""Genera los scripts SQL de creación de la base de VISTA (Entregable 1 — Mallén).

Deriva el DDL del metadata de SQLAlchemy, que es exactamente lo que ejecuta el
`Base.metadata.create_all()` del baseline: por construcción, el resultado es equivalente a
`alembic upgrade head` para las tablas con modelo ORM. Lo que el ORM NO ve se añade desde su
fuente real: las 6 tablas de `_CAT_STG_DDL` del baseline, las vistas, la función y los triggers
de coaching, y los 2 índices creados a mano en `0008_indices_rendimiento`.

Estrategia de orden: las tablas se emiten SIN sus claves foráneas (agrupadas por categoría, como
pide el requerimiento) y las FK se añaden después con ALTER TABLE. Así el agrupamiento temático
no choca con el orden de dependencias.

Uso:
    python scripts/diagnostics/generar_ddl_entrega.py --dest RUTA_CARPETA
"""
import argparse
import importlib.util
import os
import re
import sys
from collections import OrderedDict, defaultdict
from datetime import date

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy.dialects import postgresql  # noqa: E402
from sqlalchemy.schema import CreateIndex, CreateTable  # noqa: E402

from app.models import (  # noqa: F401,E402
    cat_models, coaching_more_models, dimensiones, exam_models,
    hechos, seguridad_rbac, usuario, visita,
)
from app.db.database import Base  # noqa: E402
from app.models.usuario import Rol  # noqa: E402
from app.core.authz.constantes import RECURSOS_META  # noqa: E402
from app.core.authz.matrix import MATRIZ  # noqa: E402

DIALECTO = postgresql.dialect()
HOY = date.today().isoformat()

# Esquemas: 9 del baseline + `coaching`, que crea la migración 0007.
ESQUEMAS = ["Config", "DW", "ETL", "Audit", "Security", "exam", "Visita", "cat", "stg", "coaching"]

# Índices creados a mano en 0008 (no declarados en los modelos).
INDICES_MANUALES = [
    ('CREATE INDEX IF NOT EXISTS ix_dimmedico_nombre_trgm\n'
     '    ON "cat"."DimMedico" USING gin (LOWER("NombreMedico") gin_trgm_ops);'),
    ('CREATE INDEX IF NOT EXISTS ix_medicovisita_ciclos_sin_visita\n'
     '    ON "Visita"."DIM_MedicoVisita" (ciclos_sin_visita);'),
]

CATEGORIAS = OrderedDict([
    ("configuracion", "Tablas de configuración y seguridad"),
    ("dimensiones", "Tablas de dimensiones (dims)"),
    ("hechos", "Tablas de hechos (facts)"),
    ("operacionales", "Tablas operacionales / transaccionales"),
    ("log", "Tablas de log, ETL y auditoría"),
])


def clasificar(t) -> str:
    esq, nom = t.schema or "", t.name
    if esq in ("Audit", "ETL") or "Auditoria" in nom:
        return "log"
    if esq == "Security":
        return "configuracion"
    if nom.startswith(("DIM_", "Dim")):
        return "dimensiones"
    if nom.startswith(("FACT_", "Fact")):
        return "hechos"
    if esq == "Config":
        return "configuracion"
    return "operacionales"


def _ddl_tabla_sin_fk(t) -> tuple[str, list[str]]:
    """DDL de la tabla sin las FK, más la lista de ALTER TABLE que las añaden después."""
    ddl = str(CreateTable(t).compile(dialect=DIALECTO)).strip()
    # Las FK se compilan como restricciones a nivel de tabla; se extraen para el archivo 08.
    lineas, alters = [], []
    for linea in ddl.splitlines():
        if re.search(r"\bFOREIGN KEY\b", linea):
            cuerpo = linea.strip().rstrip(",")
            alters.append(f'ALTER TABLE "{t.schema}"."{t.name}" ADD {cuerpo};')
        else:
            lineas.append(linea)
    limpio = "\n".join(lineas)
    # Deja huérfana una coma cuando la FK era la última línea del bloque.
    limpio = re.sub(r",(\s*\n\s*\))", r"\1", limpio)
    return limpio.rstrip() + ";", alters


def _cabecera(titulo: str, detalle: str = "") -> str:
    barra = "═" * 78
    txt = f"-- {barra}\n-- {titulo}\n"
    if detalle:
        for linea in detalle.strip().splitlines():
            txt += f"-- {linea}\n"
    txt += f"-- VISTA · Laboratorios Mallén · generado {HOY}\n-- {barra}\n\n"
    return txt


def _ddl_no_orm() -> list[str]:
    """Las 6 tablas creadas por DDL explícito en el baseline (sin modelo ORM)."""
    ruta = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(
        os.path.abspath(__file__)))), "alembic", "versions", "0001_baseline_postgres.py")
    spec = importlib.util.spec_from_file_location("baseline", ruta)
    mod = importlib.util.module_from_spec(spec)
    sys.modules["baseline"] = mod
    spec.loader.exec_module(mod)
    return list(mod._CAT_STG_DDL)


def generar(dest: str) -> dict:
    os.makedirs(dest, exist_ok=True)
    tablas = sorted(Base.metadata.tables.values(), key=lambda t: (t.schema or "", t.name))
    por_cat = defaultdict(list)
    for t in tablas:
        por_cat[clasificar(t)].append(t)

    alters_fk, indices = [], []
    resumen = {}

    # ── 01 esquemas ────────────────────────────────────────────────────────────
    with open(f"{dest}/01_esquemas.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "01 · ESQUEMAS",
            "Los 9 primeros los crea el baseline; `coaching` lo añade la migración 0007.\n"
            "Sin estos esquemas nada de lo que sigue puede crearse."))
        for e in ESQUEMAS:
            f.write(f'CREATE SCHEMA IF NOT EXISTS "{e}";\n')

    # ── 02 extensiones y tipos ─────────────────────────────────────────────────
    with open(f"{dest}/02_extensiones_y_tipos.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "02 · EXTENSIONES Y TIPOS ENUMERADOS",
            "pg_trgm: la usa el índice trigram de búsqueda de médicos (migración 0008).\n"
            "Tipo `rol`: 13 valores. Los 9 primeros nacen con el enum; los 4 últimos los\n"
            "añadió la migración 0017 (RBAC Fase 1). Aquí se crean todos de una vez."))
        f.write("CREATE EXTENSION IF NOT EXISTS pg_trgm;\n\n")
        valores = ",\n        ".join(f"'{r.value}'" for r in Rol)
        f.write("DO $$\nBEGIN\n    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'rol') THEN\n"
                f"        CREATE TYPE rol AS ENUM (\n        {valores}\n        );\n"
                "    END IF;\nEND\n$$;\n")

    # ── 03-07 tablas por categoría ─────────────────────────────────────────────
    archivos_cat = {
        "configuracion": "03_tablas_configuracion.sql",
        "dimensiones": "04_tablas_dimensiones.sql",
        "hechos": "05_tablas_hechos.sql",
        "operacionales": "06_tablas_operacionales.sql",
        "log": "07_tablas_log_etl_auditoria.sql",
    }
    notas = {
        "configuracion": "Catálogos maestros, parámetros del sistema y seguridad (usuarios, roles,\n"
                         "permisos). Definen CÓMO se comporta el sistema, no QUÉ midió.",
        "dimensiones": "Entidades de negocio por las que se analiza: países, líneas, ciclos,\n"
                       "representantes, médicos, indicadores, criterios.",
        "hechos": "Mediciones y resultados: KPIs, scores, rankings, ventas, visitas agregadas,\n"
                  "reconocimientos. La mayoría son CALCULADAS por VISTA (ver Entregable 3).",
        "operacionales": "Transaccionales de los módulos (Visita, Exámenes, Coaching): capturan la\n"
                         "operación diaria. No encajan como dimensión ni como hecho analítico.",
        "log": "Auditoría, control de cargas ETL y staging. Trazabilidad, no negocio.",
    }
    for cat, archivo in archivos_cat.items():
        lista = por_cat[cat]
        resumen[cat] = len(lista)
        with open(f"{dest}/{archivo}", "w", encoding="utf-8") as f:
            f.write(_cabecera(
                f"{archivo[:2]} · {CATEGORIAS[cat].upper()}",
                f"{notas[cat]}\n\nTablas en este archivo: {len(lista)}.\n"
                "Las claves foráneas NO se declaran aquí: van en 08, para que el agrupamiento\n"
                "temático no dependa del orden de dependencias entre tablas."))
            for t in lista:
                ddl, alters = _ddl_tabla_sin_fk(t)
                alters_fk.extend(alters)
                indices.extend(str(CreateIndex(i).compile(dialect=DIALECTO)).strip() + ";"
                               for i in t.indexes)
                f.write(f'-- ── {t.schema}.{t.name} ({len(t.columns)} columnas)\n{ddl}\n\n')
            if cat == "dimensiones":
                f.write(_cabecera("Tablas de dimensión SIN modelo ORM",
                                  "Creadas por DDL explícito en el baseline. No aparecen al\n"
                                  "inspeccionar los modelos: se toman de su fuente real."))
                for ddl in _ddl_no_orm():
                    if '"stg"' not in ddl and "Fact" not in ddl:
                        f.write(f"{ddl.strip()};\n\n")
            if cat == "hechos":
                for ddl in _ddl_no_orm():
                    if "FactMedicoCategoriaDetalle" in ddl:
                        f.write("-- ── cat.FactMedicoCategoriaDetalle (sin modelo ORM)\n"
                                f"{ddl.strip()};\n\n")
            if cat == "log":
                for ddl in _ddl_no_orm():
                    if '"stg"' in ddl:
                        f.write("-- ── stg.MedicoCategoriaInput (staging, sin modelo ORM)\n"
                                f"{ddl.strip()};\n\n")

    # ── 08 FK, restricciones e índices ────────────────────────────────────────
    with open(f"{dest}/08_llaves_restricciones_indices.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "08 · CLAVES FORÁNEAS, RESTRICCIONES E ÍNDICES",
            f"{len(alters_fk)} claves foráneas y {len(indices)} índices declarados en los modelos,\n"
            "más los 2 índices creados a mano en la migración 0008.\n"
            "Se aplican después de existir todas las tablas: así el orden de creación por\n"
            "categoría nunca rompe una dependencia."))
        f.write("-- Claves foráneas\n")
        for a in alters_fk:
            f.write(a + "\n")
        f.write("\n-- Índices declarados en los modelos\n")
        for i in indices:
            f.write(i + "\n")
        f.write("\n-- Índices creados a mano (migración 0008)\n")
        for i in INDICES_MANUALES:
            f.write(i + "\n")
    resumen["fks"] = len(alters_fk)
    resumen["indices"] = len(indices) + len(INDICES_MANUALES)

    # ── 10 datos semilla (RBAC) ───────────────────────────────────────────────
    with open(f"{dest}/10_datos_semilla.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "10 · DATOS SEMILLA MÍNIMOS — matriz RBAC",
            "OBLIGATORIO, no opcional: el motor de autorización DENIEGA a todos los roles un\n"
            "recurso que no esté sembrado aquí (una vez cargado su caché no recurre a los\n"
            "valores del código). Sin este archivo, módulos completos responden 403 a todos,\n"
            "incluido ADMIN.\n\n"
            f"{len(RECURSOS_META)} recursos × {len(list(Rol))} roles."))
        f.write("-- Catálogo de recursos\n")
        for slug, (nombre, modulo) in RECURSOS_META.items():
            n = nombre.replace("'", "''")
            m = modulo.replace("'", "''")
            f.write('INSERT INTO "Security"."DIM_Recurso" ("slug", "nombre", "modulo")\n'
                    f"    SELECT '{slug}', '{n}', '{m}'\n"
                    '    WHERE NOT EXISTS (SELECT 1 FROM "Security"."DIM_Recurso" '
                    f"WHERE \"slug\" = '{slug}');\n")
        f.write("\n-- Matriz de permisos (rol × recurso → acción + alcance)\n")
        n_perm = 0
        for recurso, fila in MATRIZ.items():
            for rol, celda in fila.items():
                if celda is None:
                    continue
                accion, alcance = celda
                f.write('INSERT INTO "Security"."FACT_RolPermiso" ("rol", "recurso", "accion", "alcance")\n'
                        f"    SELECT '{rol.value}', '{recurso}', '{accion.value}', '{alcance.value}'\n"
                        '    WHERE NOT EXISTS (SELECT 1 FROM "Security"."FACT_RolPermiso" '
                        f"WHERE \"rol\" = '{rol.value}' AND \"recurso\" = '{recurso}' "
                        f"AND \"accion\" = '{accion.value}');\n")
                n_perm += 1
        f.write(f"\n-- Total: {len(RECURSOS_META)} recursos y {n_perm} permisos.\n")
    resumen["recursos"] = len(RECURSOS_META)
    resumen["permisos"] = n_perm
    return resumen


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    r = generar(ap.parse_args().dest)
    print("Scripts generados:")
    for k, v in r.items():
        print(f"  {k:<16} {v}")
