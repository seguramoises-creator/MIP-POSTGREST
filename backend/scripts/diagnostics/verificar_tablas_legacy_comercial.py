"""
Verificacion SOLO LECTURA: confirma si las tablas legacy que usa el motor de 5
componentes (FACT_Ventas, FACT_EVOIR, FACT_Coaching, FACT_Capacitacion) tienen
datos reales para un pais, o si estan vacias porque la carga real entra por el
Excel unificado KPI_RM (FACT_ResultadoIndicador).

Uso:
    docker compose exec backend python scripts/diagnostics/verificar_tablas_legacy_comercial.py DO
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from sqlalchemy import func

from app.db.database import SessionLocal
from app.models.hechos import Ventas, EvoIR, Coaching, CapacitacionFact, ResultadoIndicador
from app.models.dimensiones import Indicador


def main():
    pais_codigo = (sys.argv[1] if len(sys.argv) > 1 else "DO").upper()
    db = SessionLocal()
    try:
        print(f"=== Tablas legacy (motor de 5 componentes) — pais={pais_codigo} ===")
        print(f"  FACT_Ventas        : {db.query(func.count(Ventas.id)).filter(Ventas.pais_codigo == pais_codigo).scalar()} filas")
        print(f"  FACT_EVOIR         : {db.query(func.count(EvoIR.id)).filter(EvoIR.pais_codigo == pais_codigo).scalar()} filas")
        print(f"  FACT_Coaching      : {db.query(func.count(Coaching.id)).filter(Coaching.pais_codigo == pais_codigo).scalar()} filas")
        print(f"  FACT_Capacitacion  : {db.query(func.count(CapacitacionFact.id)).filter(CapacitacionFact.pais_codigo == pais_codigo).scalar()} filas")

        print()
        print(f"=== FACT_ResultadoIndicador (KPI_RM unificado) — pais={pais_codigo}, por indicador ===")
        rows = (
            db.query(Indicador.codigo, Indicador.modulo, func.count(ResultadoIndicador.id))
            .join(ResultadoIndicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(ResultadoIndicador.pais_codigo == pais_codigo)
            .group_by(Indicador.codigo, Indicador.modulo)
            .all()
        )
        if not rows:
            print("  (sin filas)")
        for codigo, modulo, n in rows:
            print(f"  {codigo:<20} modulo={modulo:<12} {n} filas")

    finally:
        db.close()


if __name__ == "__main__":
    main()
