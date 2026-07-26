"""Inventario verificable del esquema de VISTA, derivado de los modelos ORM.

Entregables Mallén (jul-2026): es la base de evidencia del diccionario de datos y del contrato
de carga. Se genera del metadata de SQLAlchemy —no de leer los .py a ojo— para que el conteo de
tablas, columnas, llaves e índices sea reproducible y auditable.

Uso:
    python scripts/diagnostics/inventario_esquema.py            # resumen por consola
    python scripts/diagnostics/inventario_esquema.py --json RUTA # vuelca el detalle completo

No toca la base de datos: solo inspecciona el metadata declarativo.
"""
import argparse
import json
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

# Importar TODOS los modelos puebla Base.metadata (si falta uno, su tabla no aparece).
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models,
    hechos, seguridad_rbac, usuario, visita,
)
from app.db.database import Base


def _col(c):
    return {
        "posicion": c._creation_order,
        "nombre": c.name,
        "tipo": str(c.type),
        "nullable": c.nullable,
        "default": str(c.default.arg) if c.default is not None and hasattr(c.default, "arg") else None,
        "server_default": str(c.server_default.arg) if c.server_default is not None and hasattr(c.server_default, "arg") else None,
        "pk": c.primary_key,
        "autoincrement": bool(c.autoincrement is True),
        "fk": sorted(fk.target_fullname for fk in c.foreign_keys),
        "index": bool(c.index),
        "unique": bool(c.unique),
        "comentario": c.comment,
    }


def construir() -> dict:
    tablas = []
    for t in sorted(Base.metadata.tables.values(), key=lambda x: (x.schema or "", x.name)):
        uniques, checks = [], []
        for con in t.constraints:
            tipo = type(con).__name__
            if tipo == "UniqueConstraint":
                uniques.append({"nombre": con.name, "columnas": [c.name for c in con.columns]})
            elif tipo == "CheckConstraint":
                checks.append({"nombre": con.name, "expr": str(con.sqltext)})
        tablas.append({
            "esquema": t.schema,
            "tabla": t.name,
            "pk": [c.name for c in t.primary_key.columns],
            "columnas": [_col(c) for c in t.columns],
            "n_columnas": len(t.columns),
            "fks": sorted({fk.target_fullname.rsplit(".", 1)[0] for fk in t.foreign_keys}),
            "uniques": uniques,
            "checks": checks,
            "indices": [{"nombre": i.name, "columnas": [c.name for c in i.columns],
                         "unique": i.unique} for i in t.indexes],
            "docstring": (t.info or {}).get("doc"),
        })
    return {"tablas": tablas}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", help="ruta donde volcar el inventario completo")
    args = ap.parse_args()

    inv = construir()
    tablas = inv["tablas"]
    por_esquema = Counter(t["esquema"] for t in tablas)

    print("=" * 62)
    print("INVENTARIO DE ESQUEMA — VISTA (derivado de los modelos ORM)")
    print("=" * 62)
    print(f"Tablas totales : {len(tablas)}")
    print(f"Columnas totales: {sum(t['n_columnas'] for t in tablas)}")
    print(f"Esquemas       : {len(por_esquema)}")
    print()
    print(f"{'ESQUEMA':<12} {'TABLAS':>7} {'COLUMNAS':>9}")
    print("-" * 30)
    for esq, n in sorted(por_esquema.items(), key=lambda kv: -kv[1]):
        cols = sum(t["n_columnas"] for t in tablas if t["esquema"] == esq)
        print(f"{esq or '(sin esquema)':<12} {n:>7} {cols:>9}")
    print("-" * 30)
    print(f"{'TOTAL':<12} {len(tablas):>7} {sum(t['n_columnas'] for t in tablas):>9}")

    sin_pk = [f"{t['esquema']}.{t['tabla']}" for t in tablas if not t["pk"]]
    if sin_pk:
        print(f"\nAVISO — tablas sin clave primaria: {sin_pk}")

    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(inv, f, ensure_ascii=False, indent=2)
        print(f"\nDetalle completo volcado en: {args.json}")


if __name__ == "__main__":
    main()
