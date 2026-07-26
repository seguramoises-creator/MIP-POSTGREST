"""Segunda parte de la generación del Entregable 1: vistas, triggers y semillas no-RBAC.

Se separa de `generar_ddl_entrega.py` porque estos objetos NO viven en el metadata de
SQLAlchemy: hay que tomarlos de las migraciones que los crean, que son su única fuente real.
"""
import argparse
import importlib.util
import os
import sys
from datetime import date

BACKEND = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, BACKEND)
VERSIONS = os.path.join(BACKEND, "alembic", "versions")
HOY = date.today().isoformat()


def _cargar(nombre_archivo, alias):
    spec = importlib.util.spec_from_file_location(alias, os.path.join(VERSIONS, nombre_archivo))
    mod = importlib.util.module_from_spec(spec)
    sys.modules[alias] = mod
    spec.loader.exec_module(mod)
    return mod


def _cabecera(titulo, detalle=""):
    barra = "═" * 78
    txt = f"-- {barra}\n-- {titulo}\n"
    for linea in detalle.strip().splitlines():
        txt += f"-- {linea}\n"
    txt += f"-- VISTA · Laboratorios Mallén · generado {HOY}\n-- {barra}\n\n"
    return txt


def generar(dest):
    vistas = _cargar("0002_views_postgres.py", "vw")
    coach = _cargar("0007_modulo_coaching_more.py", "co")

    # ── 09 vistas, función y triggers ─────────────────────────────────────────
    with open(f"{dest}/09_vistas_funciones_triggers.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "09 · VISTAS, FUNCIONES Y TRIGGERS",
            "Objetos que no son tablas y que ningún modelo ORM declara: se toman de las\n"
            "migraciones que los crean (0002 y 0007).\n\n"
            "Los 2 triggers implementan una REGLA DE NEGOCIO, no una optimización: la hoja de\n"
            "coaching firmada es append-only. Ninguna ruta de la aplicación puede actualizarla\n"
            "ni borrarla; una corrección se registra como hoja nueva (`corrige_a_id`)."))
        f.write("-- Vista de conciliación de categorización médica (calculada vs. Excel)\n")
        f.write(vistas._VW_CONCILIACION.strip() + ";\n\n")
        f.write("-- Vista del dashboard de cobertura predictiva por Gerente de Distrito\n")
        f.write(vistas._VW_DASHBOARD.strip() + ";\n\n")
        f.write("-- Inmutabilidad de la hoja de coaching (append-only)\n")
        f.write("""CREATE OR REPLACE FUNCTION coaching._rechazar_mutacion() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'Hoja de coaching inmutable (append-only): % no permitido en %.
Use una hoja de corrección (nuevo registro con corrige_a_id).', TG_OP, TG_TABLE_NAME;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_coaching_sesion_inmutable
    BEFORE UPDATE OR DELETE ON coaching."Sesion"
    FOR EACH ROW EXECUTE FUNCTION coaching._rechazar_mutacion();

CREATE TRIGGER trg_coaching_item_inmutable
    BEFORE UPDATE OR DELETE ON coaching."ItemEvaluado"
    FOR EACH ROW EXECUTE FUNCTION coaching._rechazar_mutacion();
""")

    # ── 10b semillas funcionales (no RBAC) ────────────────────────────────────
    n_items = 0
    with open(f"{dest}/10b_datos_semilla_funcionales.sql", "w", encoding="utf-8") as f:
        f.write(_cabecera(
            "10b · SEMILLAS FUNCIONALES (catálogo MORE de coaching)",
            "Los 26 ítems del formulario MORE son el catálogo que hace funcionar el módulo de\n"
            "Coaching: sin ellos, la hoja de acompañamiento no tiene qué evaluar.\n\n"
            "NO se incluyen aquí las semillas de `0004_seed_provincias_rd` ni de\n"
            "`0005_sync_dims_maestras`: son DATOS de la operación dominicana actual (provincias\n"
            "de RD, dimensiones maestras ya cargadas), no requisitos de arranque. Mallén cargará\n"
            "su propia información en el arranque."))
        for seccion, orden_sec, items in coach._ITEMS:
            for i, texto in enumerate(items, start=1):
                t = texto.replace("'", "''")
                s = seccion.replace("'", "''")
                f.write('INSERT INTO coaching."ItemCatalogo" '
                        '("seccion", "orden_seccion", "orden_item", "texto", "activo")\n'
                        f"    SELECT '{s}', {orden_sec}, {i}, '{t}', TRUE\n"
                        '    WHERE NOT EXISTS (SELECT 1 FROM coaching."ItemCatalogo" '
                        f"WHERE \"seccion\" = '{s}' AND \"orden_item\" = {i});\n")
                n_items += 1
        f.write(f"\n-- Total: {n_items} ítems del catálogo MORE.\n")
    return {"items_more": n_items}


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--dest", required=True)
    print(generar(ap.parse_args().dest))
