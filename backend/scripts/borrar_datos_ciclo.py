"""
Borra TODA la información ligada a un ciclo (por `ciclo_id`): insumos (planeación,
visitas, muestras, parrilla, costo, meta, KPI, evaluaciones) Y salidas calculadas
(score, ranking, reconocimiento, agregados). NO borra el ciclo en sí (DIM_Ciclo), solo
sus datos. Operación DESTRUCTIVA e irreversible — usa siempre --dry-run primero y ten
un respaldo de la base.

Uso (venv o dentro del contenedor backend):
    python scripts/borrar_datos_ciclo.py --listar --pais DO           # ver ciclos e ids
    python scripts/borrar_datos_ciclo.py --ciclo 71 --dry-run         # ver qué borraría
    python scripts/borrar_datos_ciclo.py --ciclo 71 --confirmar       # aplicar
Docker:
    docker compose exec -e PYTHONPATH=/app backend python scripts/borrar_datos_ciclo.py --ciclo 71 --dry-run
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models.dimensiones          # noqa: F401
import app.models.hechos               # noqa: F401
import app.models.usuario              # noqa: F401
import app.models.visita               # noqa: F401
import app.models.coaching_more_models  # noqa: F401
import app.models.exam_models          # noqa: F401
try:
    import app.models.cat_models       # noqa: F401
except Exception:
    pass
from app.db.database import SessionLocal, Base
from app.models.dimensiones import Ciclo


def _clases_ciclo():
    """Todas las clases mapeadas con `ciclo_id` FK a Config.DIM_Ciclo (insumos y calculadas)."""
    out = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if "ciclo_id" not in mapper.columns.keys():
            continue
        col = mapper.columns["ciclo_id"]
        if not any("DIM_Ciclo" in fk.target_fullname for fk in col.foreign_keys):
            continue
        out.append(cls)
    return out


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ciclo", type=int, help="ID del ciclo cuyos datos se borran")
    ap.add_argument("--pais", default=None, help="Para --listar")
    ap.add_argument("--listar", action="store_true", help="Lista los ciclos y sus IDs")
    ap.add_argument("--dry-run", action="store_true", help="No borra; solo muestra")
    ap.add_argument("--confirmar", action="store_true", help="Confirma el borrado real")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        if args.listar:
            q = db.query(Ciclo)
            if args.pais:
                q = q.filter(Ciclo.pais_codigo == args.pais)
            for c in q.order_by(Ciclo.pais_codigo, Ciclo.anio, Ciclo.numero).all():
                print(f"id={c.id:>3}  {c.pais_codigo}  {c.nombre:<12} {c.fecha_inicio}->{c.fecha_fin}  cerrado={c.cerrado}")
            return

        if not args.ciclo:
            print("ERROR: indica --ciclo <id> (usa --listar para ver los IDs).")
            return
        c = db.query(Ciclo).filter(Ciclo.id == args.ciclo).first()
        if not c:
            print(f"ERROR: no existe el ciclo id={args.ciclo}.")
            return
        aplicar = args.confirmar and not args.dry_run
        print(f"CICLO id={c.id} {c.nombre} {c.fecha_inicio}->{c.fecha_fin} cerrado={c.cerrado}")
        if c.cerrado:
            print("AVISO: el ciclo está CERRADO (histórico). Se borrarán sus datos igualmente.")
        print("-" * 60)

        from sqlalchemy.exc import DatabaseError
        total = 0
        omitidas = []
        for cls in _clases_ciclo():
            n = db.query(cls).filter(cls.ciclo_id == args.ciclo).count()
            if not n:
                continue
            tabla = f"{cls.__table__.schema}.{cls.__tablename__}"
            if not aplicar:
                print(f"  {'(borraría)':<11} {n:>5}  {tabla}")
                total += n
                continue
            # Savepoint por tabla: si una hoja es INMUTABLE (trigger append-only, p.ej.
            # coaching), se salta sin abortar el resto del borrado.
            try:
                sp = db.begin_nested()
                db.query(cls).filter(cls.ciclo_id == args.ciclo).delete(synchronize_session=False)
                sp.commit()
                total += n
                print(f"  {'borrado':<11} {n:>5}  {tabla}")
            except DatabaseError:
                sp.rollback()
                omitidas.append((tabla, n))
                print(f"  {'OMITIDA':<11} {n:>5}  {tabla}  (hoja inmutable — no se puede borrar)")

        if aplicar:
            db.commit()
            print(f"\nListo. {total} filas borradas del ciclo '{c.nombre}'.")
            if omitidas:
                print("Se omitieron hojas inmutables (append-only, se corrigen con registros "
                      "nuevos, no se borran):")
                for t, n in omitidas:
                    print(f"  - {t} ({n} filas)")
        else:
            print(f"\n{'(dry-run)' if args.dry_run else '(sin --confirmar)'} "
                  f"Se borrarían {total} filas. No se escribió nada. "
                  f"Para aplicar, añade --confirmar.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
