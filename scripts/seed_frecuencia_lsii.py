"""Seed idempotente de ParametroFrecuenciaLSII: carga la frecuencia de arranque
por país si aún no existe. Ejecutar: python scripts/seed_frecuencia_lsii.py"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.db.database import SessionLocal
from app.models.dimensiones import Pais
from app.models.formacion import ParametroFrecuenciaLSII
from app.services import formacion_calendario_service as cal


def main() -> None:
    db = SessionLocal()
    try:
        paises = [p.codigo for p in db.query(Pais).all()]
        creadas = 0
        for pais in paises:
            existentes = {r.cuadrante for r in db.query(ParametroFrecuenciaLSII)
                          .filter(ParametroFrecuenciaLSII.pais_codigo == pais).all()}
            for cuadrante, visitas in cal.FRECUENCIA_DEFECTO.items():
                if cuadrante not in existentes:
                    cal.fijar_frecuencia(db, pais, cuadrante, visitas,
                                         descripcion="Valor de arranque §7.2")
                    creadas += 1
        print(f"Seed de frecuencias LSII: {creadas} fila(s) creada(s) en {len(paises)} país(es).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
