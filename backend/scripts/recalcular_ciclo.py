"""
Recalcula Score Integral y Ranking de un ciclo (motor 100% Python). Úsalo después de
copiar insumos a un ciclo (copiar_datos_ciclo.py) para regenerar las salidas calculadas.
Solo opera sobre ciclos ABIERTOS (regla de negocio; los cerrados son inmutables).

Uso:
    python scripts/recalcular_ciclo.py --pais DO --num 7
    python scripts/recalcular_ciclo.py --ciclo 41
Docker:
    docker compose exec -e PYTHONPATH=/app backend python scripts/recalcular_ciclo.py --pais DO --num 7
"""
import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import app.models.dimensiones  # noqa: F401
import app.models.hechos       # noqa: F401
import app.models.usuario      # noqa: F401
from app.db.database import SessionLocal
from app.models.dimensiones import Ciclo
from app.services import recalculo_service


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ciclo", type=int, help="ID del ciclo")
    ap.add_argument("--num", type=int, help="Nº de ciclo (con --pais)")
    ap.add_argument("--pais", default=None, help="País (con --num)")
    args = ap.parse_args()

    db = SessionLocal()
    try:
        cid = args.ciclo
        if not cid and args.num and args.pais:
            c = (db.query(Ciclo).filter(Ciclo.pais_codigo == args.pais, Ciclo.numero == args.num)
                 .order_by(Ciclo.anio.desc()).first())
            cid = c.id if c else None
        if not cid:
            print("ERROR: indica --ciclo <id> o --pais --num <n>.")
            return
        c = db.query(Ciclo).filter(Ciclo.id == cid).first()
        if not c:
            print(f"ERROR: no existe el ciclo id={cid}.")
            return
        print(f"Recalculando ciclo id={c.id} {c.nombre} (país {c.pais_codigo})...")
        r = recalculo_service.recalcular_ciclo(db, c.id, c.pais_codigo)
        print("Resultado:", r)
    finally:
        db.close()


if __name__ == "__main__":
    main()
