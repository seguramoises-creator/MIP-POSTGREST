"""
Migración de datos SQL Server → PostgreSQL (edición PostgreSQL).
=================================================================

Copia TODAS las tablas (catálogos, configuración, hechos e histórico) de la BD
SQL Server de la edición actual a la BD PostgreSQL, preservando las llaves
primarias (integridad referencial 1:1) y en orden seguro de FKs. Deja la edición
PostgreSQL como un reemplazo idéntico del sistema en SQL Server.

Por qué DOS fases: cada edición tiene un solo driver de BD instalado
(SQL Server → pymssql, PostgreSQL → psycopg2). Un único proceso no puede hablar
con ambas, así que se separa en exportar (venv SQL Server) e importar (venv PG).
El intercambio va por archivos JSONL con tipos etiquetados (Decimal, datetime,
date, bytes) para no perder precisión entre los dos motores.

────────────────────────────────────────────────────────────────────────────
USO
────────────────────────────────────────────────────────────────────────────
  # FASE 1 — exportar (correr con el python de la edición SQL SERVER, que tiene
  # pymssql). Se corre desde MSM-postgres/backend para que use ESTE esquema:
  <MSM>/backend/venv/Scripts/python.exe scripts/migracion/migrar_datos.py export \
      --source-env "C:/.../MSM/backend/.env" --out dump/

  # FASE 2 — importar (con el python de la edición PostgreSQL, que tiene psycopg2):
  ./venv/Scripts/python.exe scripts/migracion/migrar_datos.py import --in dump/

Idempotente: la fase import hace TRUNCATE ... RESTART IDENTITY CASCADE de las
tablas destino antes de cargar, y resincroniza las secuencias SERIAL al final.
"""
from __future__ import annotations

import argparse
import base64
import datetime as _dt
import json
import os
import sys
from decimal import Decimal
from pathlib import Path

# Permite ejecutar desde cualquier CWD (añade la raíz del backend al path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from sqlalchemy import create_engine, text  # noqa: E402

# Esquemas a migrar (todos los de la aplicación). El orden aquí no importa;
# el orden de carga real se calcula por dependencias de FK (ver _orden_carga).
SCHEMAS = ["Config", "DW", "ETL", "Audit", "Security", "exam", "Visita", "cat", "stg"]


# ── Serialización con tipos etiquetados ─────────────────────────────────────────
def _enc(v):
    """Codifica un valor Python a algo JSON-serializable sin perder el tipo."""
    if v is None or isinstance(v, bool):
        return v
    if isinstance(v, Decimal):
        return {"__t": "dec", "v": str(v)}
    if isinstance(v, _dt.datetime):
        return {"__t": "dt", "v": v.isoformat()}
    if isinstance(v, _dt.date):
        return {"__t": "date", "v": v.isoformat()}
    if isinstance(v, (bytes, bytearray)):
        return {"__t": "b", "v": base64.b64encode(bytes(v)).decode("ascii")}
    return v  # int, float, str


def _dec(v):
    """Reconstruye el valor Python desde el JSON etiquetado."""
    if isinstance(v, dict) and "__t" in v:
        t, x = v["__t"], v["v"]
        if t == "dec":
            return Decimal(x)
        if t == "dt":
            return _dt.datetime.fromisoformat(x)
        if t == "date":
            return _dt.date.fromisoformat(x)
        if t == "b":
            return base64.b64decode(x)
    return v


# ── Descubrimiento de esquema (information_schema, portable a ambos motores) ─────
def _tablas_base(conn) -> list[tuple[str, str]]:
    rows = conn.execute(text(
        "SELECT table_schema, table_name FROM information_schema.tables "
        "WHERE table_type='BASE TABLE' AND table_schema IN :schemas"
    ).bindparams(__import__("sqlalchemy").bindparam("schemas", expanding=True)),
        {"schemas": SCHEMAS}).all()
    return [(r[0], r[1]) for r in rows]


def _columnas(conn, schema: str, tabla: str) -> list[str]:
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=:s AND table_name=:t ORDER BY ordinal_position"
    ), {"s": schema, "t": tabla}).all()
    return [r[0] for r in rows]


def _columnas_boolean(conn, schema: str, tabla: str) -> set[str]:
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=:s AND table_name=:t AND data_type='boolean'"
    ), {"s": schema, "t": tabla}).all()
    return {r[0] for r in rows}


def _columnas_not_null(conn, schema: str, tabla: str) -> set[str]:
    rows = conn.execute(text(
        "SELECT column_name FROM information_schema.columns "
        "WHERE table_schema=:s AND table_name=:t AND is_nullable='NO'"
    ), {"s": schema, "t": tabla}).all()
    return {r[0] for r in rows}


# ══════════════════════════════════════════════════════════════════════════════
# FASE 1 — EXPORTAR (SQL Server)
# ══════════════════════════════════════════════════════════════════════════════
def _leer_env(path: str) -> dict:
    data = {}
    for line in Path(path).read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, _, val = line.partition("=")
        data[k.strip()] = val.strip()
    return data


def exportar(source_env: str, out_dir: str):
    env = _leer_env(source_env)
    url = (
        f"mssql+pymssql://{env['DB_USER']}:{env['DB_PASSWORD']}"
        f"@{env['DB_SERVER']}:{env.get('DB_PORT', '1433')}/{env['DB_NAME']}"
    )
    print(f"[export] Conectando a SQL Server {env['DB_SERVER']}:{env.get('DB_PORT','1433')}/{env['DB_NAME']}")
    engine = create_engine(url)
    out = Path(out_dir)
    out.mkdir(parents=True, exist_ok=True)
    total_rows = 0
    with engine.connect() as conn:
        tablas = sorted(_tablas_base(conn))
        for schema, tabla in tablas:
            cols = _columnas(conn, schema, tabla)
            if not cols:
                continue
            cols_q = ", ".join(f'"{c}"' for c in cols)
            rows = conn.execute(text(f'SELECT {cols_q} FROM "{schema}"."{tabla}"')).all()
            fpath = out / f"{schema}__{tabla}.jsonl"
            with fpath.open("w", encoding="utf-8") as f:
                f.write(json.dumps({"schema": schema, "table": tabla, "columns": cols}) + "\n")
                for r in rows:
                    f.write(json.dumps([_enc(v) for v in r], ensure_ascii=False) + "\n")
            total_rows += len(rows)
            print(f"  ✓ {schema}.{tabla}: {len(rows)} filas")
    print(f"[export] Listo — {len(tablas)} tablas, {total_rows} filas → {out.resolve()}")


# ══════════════════════════════════════════════════════════════════════════════
# FASE 2 — IMPORTAR (PostgreSQL)
# ══════════════════════════════════════════════════════════════════════════════
def _orden_carga() -> list[tuple[str, str]]:
    """Orden FK-seguro (padres antes que hijos) desde el metadata ORM, más las 6
    tablas cat/stg sin modelo ORM al final (dependen de cat.Dim* que van antes)."""
    import app.models.usuario, app.models.dimensiones, app.models.hechos  # noqa: F401
    import app.models.visita, app.models.exam_models, app.models.cat_models  # noqa: F401
    from app.db.database import Base
    orm = [(t.schema, t.name) for t in Base.metadata.sorted_tables]
    raw = [("cat", "DimCentroMedico"), ("cat", "DimGeografia"), ("cat", "DimEquipo"),
           ("cat", "DimReglaCategoriaMedica"), ("cat", "FactMedicoCategoriaDetalle"),
           ("stg", "MedicoCategoriaInput")]
    orm_set = set(orm)
    return orm + [r for r in raw if r not in orm_set]


def importar(in_dir: str):
    from app.core.config import settings
    engine = create_engine(settings.DATABASE_URL)  # sin echo (el de la app usa echo=DEBUG)
    src = Path(in_dir)
    dumps = {tuple(p.stem.split("__", 1)): p for p in src.glob("*.jsonl")}
    orden = [t for t in _orden_carga() if t in dumps]
    # tablas presentes en el dump pero no en el orden ORM (por si acaso), al final
    orden += [t for t in dumps if t not in set(orden)]

    with engine.begin() as conn:
        # Filtrar a las tablas que EXISTEN en PostgreSQL (por si un esquema difiere)
        existentes = set(_tablas_base(conn))
        omitidas = [t for t in orden if t not in existentes]
        if omitidas:
            print("[import] Omitidas (no existen en PostgreSQL):",
                  ", ".join(f"{s}.{t}" for s, t in omitidas))
        orden = [t for t in orden if t in existentes]
        # 1) Vaciar todas las tablas destino (CASCADE resuelve dependencias)
        objetivo = ", ".join(f'"{s}"."{t}"' for s, t in orden)
        if objetivo:
            conn.execute(text(f"TRUNCATE {objetivo} RESTART IDENTITY CASCADE"))
        # 2) Cargar en orden FK
        resumen = []
        for schema, tabla in orden:
            lines = dumps[(schema, tabla)].read_text(encoding="utf-8").splitlines()
            header = json.loads(lines[0])
            src_cols = header["columns"]
            # Solo columnas presentes en AMBOS esquemas (resiliente a divergencias):
            # las que están en SQL Server pero no en PostgreSQL se omiten (el modelo
            # PG no las usa); las que están en PG pero no en el dump quedan con default.
            target_cols = set(_columnas(conn, schema, tabla))
            bool_cols = _columnas_boolean(conn, schema, tabla)
            use = [(i, c) for i, c in enumerate(src_cols) if c in target_cols]
            omit = [c for c in src_cols if c not in target_cols]
            if omit:
                print(f"    (columnas en SQL Server no presentes en PG, omitidas: {', '.join(omit)})")
            cols_q = ", ".join(f'"{c}"' for _, c in use)
            binds = ", ".join(f":b{j}" for j in range(len(use)))
            ins = text(f'INSERT INTO "{schema}"."{tabla}" ({cols_q}) VALUES ({binds})')
            params = []
            for ln in lines[1:]:
                if not ln.strip():
                    continue
                vals = [_dec(v) for v in json.loads(ln)]
                p = {}
                for j, (i, c) in enumerate(use):
                    v = vals[i]
                    if c in bool_cols and v is not None:
                        v = bool(v)  # BIT (int 0/1) → boolean
                    p[f"b{j}"] = v
                params.append(p)
            # Auto-sanado: si el dato real trae NULL en una columna que PG marcó
            # NOT NULL (los modelos PG quedaron más estrictos que el esquema real
            # de SQL Server), se relaja la restricción para alinear PG a la realidad.
            if params:
                not_null = _columnas_not_null(conn, schema, tabla)
                for j, (i, c) in enumerate(use):
                    if c in not_null and any(p[f"b{j}"] is None for p in params):
                        conn.execute(text(f'ALTER TABLE "{schema}"."{tabla}" ALTER COLUMN "{c}" DROP NOT NULL'))
                        print(f"    (NOT NULL relajado en {schema}.{tabla}.{c}: hay NULL en el dato real)")
                for k in range(0, len(params), 500):  # lotes
                    conn.execute(ins, params[k:k + 500])
            # 3) Resincronizar secuencias SERIAL de esta tabla
            for c in target_cols:
                seq = conn.execute(
                    text("SELECT pg_get_serial_sequence(:tab, :col)"),
                    {"tab": f'"{schema}"."{tabla}"', "col": c},
                ).scalar()
                if seq:
                    conn.execute(text(
                        f'SELECT setval(:seq, GREATEST(COALESCE((SELECT MAX("{c}") '
                        f'FROM "{schema}"."{tabla}"), 1), 1))'
                    ), {"seq": seq})
            resumen.append((f"{schema}.{tabla}", len(params)))
            print(f"  ✓ {schema}.{tabla}: {len(params)} filas")
    total = sum(n for _, n in resumen)
    print(f"[import] Listo — {len(resumen)} tablas, {total} filas cargadas en PostgreSQL")


# ── CLI ─────────────────────────────────────────────────────────────────────────
def main():
    ap = argparse.ArgumentParser(description="Migración de datos SQL Server → PostgreSQL")
    sub = ap.add_subparsers(dest="modo", required=True)
    pe = sub.add_parser("export", help="Volcar SQL Server → JSONL (venv SQL Server)")
    pe.add_argument("--source-env", required=True, help="Ruta al .env de la edición SQL Server")
    pe.add_argument("--out", default="dump", help="Directorio de salida (default: dump/)")
    pi = sub.add_parser("import", help="Cargar JSONL → PostgreSQL (venv PostgreSQL)")
    pi.add_argument("--in", dest="in_dir", default="dump", help="Directorio de dumps (default: dump/)")
    args = ap.parse_args()
    if args.modo == "export":
        exportar(args.source_env, args.out)
    else:
        importar(args.in_dir)


if __name__ == "__main__":
    main()
