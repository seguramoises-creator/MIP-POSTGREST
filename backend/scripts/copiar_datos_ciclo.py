"""
Copia (o mueve) TODA la información operativa de un ciclo ORIGEN a un ciclo DESTINO,
remapeando `ciclo_id`. Pensado para el caso "los datos quedaron en un ciclo con fechas
equivocadas y hay que llevarlos al ciclo del mes en curso".

Copia los INSUMOS (planeación, visitas, muestras, parrilla, costo, meta de cobertura,
KPI de resultados, evaluaciones LSII). NO copia las salidas CALCULADAS (score, ranking,
reconocimiento, agregados de dashboard, staging ETL): esas se regeneran con el recálculo.

Idempotente: en cada tabla borra primero las filas del DESTINO para ese ciclo y luego
inserta las copias del ORIGEN (con `ciclo_id` = destino y PK nueva autoincremental).

Uso (con el venv o dentro del contenedor backend):
    python scripts/copiar_datos_ciclo.py --listar --pais DO         # ver ciclos e ids
    python scripts/copiar_datos_ciclo.py --origen 17 --destino 41 --dry-run
    python scripts/copiar_datos_ciclo.py --origen 17 --destino 41   # aplicar
    python scripts/copiar_datos_ciclo.py --origen 17 --destino 41 --reabrir-destino
Docker:
    docker compose exec -e PYTHONPATH=/app backend python scripts/copiar_datos_ciclo.py --listar --pais DO
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Registrar TODOS los modelos (para que Base.registry conozca todas las tablas con ciclo_id).
import app.models.dimensiones      # noqa: F401
import app.models.hechos           # noqa: F401
import app.models.usuario          # noqa: F401
import app.models.visita           # noqa: F401
import app.models.coaching_more_models  # noqa: F401
import app.models.exam_models      # noqa: F401
try:
    import app.models.cat_models   # noqa: F401  (usa ciclo_key, no ciclo_id — se ignora)
except Exception:
    pass
from app.db.database import SessionLocal, Base
from app.models.dimensiones import Ciclo

# Tablas CALCULADAS/derivadas o staging: NO se copian (se regeneran con recálculo).
BLOCKLIST = {
    "FACT_ScoreIntegralRM", "FACT_RankingRM", "FACT_RankingGerente", "FACT_ReconocimientoRM",
    "FACT_ScorecardIndicador", "FACT_DistribucionEquipo", "FACT_DashboardEjecutivo",
    "FACT_TendenciaCiclo", "FACT_Visita", "FACT_Visita_V2", "FACT_KPI_RAW", "FACT_CargaExcel",
}


def _clases_ciclo():
    """Clases mapeadas con `ciclo_id` que apunta a Config.DIM_Ciclo (excluye cat.* con ciclo_key)."""
    out = []
    for mapper in Base.registry.mappers:
        cls = mapper.class_
        if "ciclo_id" not in mapper.columns.keys():
            continue
        col = mapper.columns["ciclo_id"]
        if not any("DIM_Ciclo" in fk.target_fullname for fk in col.foreign_keys):
            continue  # ciclo_id sin FK a Config.DIM_Ciclo (staging) — omitir
        if cls.__tablename__ in BLOCKLIST:
            continue
        out.append(cls)
    return out


def _copiar_tabla(db, cls, origen, destino, dry):
    mapper = cls.__mapper__
    pk = list(mapper.primary_key)
    autoinc = pk[0].name if (len(pk) == 1 and pk[0].autoincrement in (True, "auto")) else None
    filas = db.query(cls).filter(cls.ciclo_id == origen).all()
    if not filas:
        return 0
    if not dry:
        db.query(cls).filter(cls.ciclo_id == destino).delete(synchronize_session=False)
        for row in filas:
            data = {c: getattr(row, c) for c in mapper.columns.keys()}
            if autoinc:
                data.pop(autoinc, None)
            data["ciclo_id"] = destino
            db.add(cls(**data))
    return len(filas)


def _resolver_id(db, pais, num):
    c = (db.query(Ciclo).filter(Ciclo.pais_codigo == pais, Ciclo.numero == num)
         .order_by(Ciclo.anio.desc()).first())
    return c.id if c else None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--origen", type=int, help="ID del ciclo origen (con los datos)")
    ap.add_argument("--destino", type=int, help="ID del ciclo destino (mes en curso)")
    ap.add_argument("--origen-num", type=int, help="Nº de ciclo origen (con --pais), ej. 3")
    ap.add_argument("--destino-num", type=int, help="Nº de ciclo destino (con --pais), ej. 7")
    ap.add_argument("--pais", default=None, help="País (para --listar o --*-num)")
    ap.add_argument("--listar", action="store_true", help="Lista los ciclos y sus IDs")
    ap.add_argument("--dry-run", action="store_true", help="No escribe; solo muestra")
    ap.add_argument("--reabrir-destino", action="store_true", help="Marca el ciclo destino como abierto")
    ap.add_argument("--cerrar-origen", action="store_true", help="Cierra el ciclo origen tras copiar")
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

        # Resolver por país + número si no se dieron IDs directos.
        if not args.origen and args.origen_num and args.pais:
            args.origen = _resolver_id(db, args.pais, args.origen_num)
        if not args.destino and args.destino_num and args.pais:
            args.destino = _resolver_id(db, args.pais, args.destino_num)
        if not args.origen or not args.destino:
            print("ERROR: indica --origen/--destino (IDs) o --pais --origen-num --destino-num. "
                  "Usa --listar para ver los ciclos.")
            return
        if args.origen == args.destino:
            print("ERROR: origen y destino son el mismo ciclo.")
            return

        co = db.query(Ciclo).filter(Ciclo.id == args.origen).first()
        cd = db.query(Ciclo).filter(Ciclo.id == args.destino).first()
        if not co or not cd:
            print("ERROR: origen o destino no existe.")
            return
        print(f"ORIGEN  id={co.id} {co.nombre} {co.fecha_inicio}->{co.fecha_fin}")
        print(f"DESTINO id={cd.id} {cd.nombre} {cd.fecha_inicio}->{cd.fecha_fin}")
        print("-" * 60)

        total = 0
        for cls in _clases_ciclo():
            n = _copiar_tabla(db, cls, args.origen, args.destino, args.dry_run)
            if n:
                print(f"  {('(copiaría)' if args.dry_run else 'copiado'):<12} {n:>5}  {cls.__table__.schema}.{cls.__tablename__}")
                total += n

        if args.reabrir_destino and not args.dry_run:
            cd.cerrado = False
            print(f"  destino '{cd.nombre}' marcado como ABIERTO")
        if args.cerrar_origen and not args.dry_run:
            co.cerrado = True
            print(f"  origen '{co.nombre}' marcado como CERRADO")

        if args.dry_run:
            print(f"\n(dry-run) Total que se copiaría: {total} filas. No se escribió nada.")
        else:
            db.commit()
            print(f"\nListo. {total} filas copiadas de '{co.nombre}' a '{cd.nombre}'.")
            print("IMPORTANTE: ejecuta el recálculo del ciclo destino para regenerar "
                  "score/ranking:  POST /etl/recalcular/{ciclo_id}  (o desde la pantalla ETL).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
