"""Seed idempotente de ParametroFrecuenciaLSII: carga la frecuencia de arranque
por país si aún no existe.

Uso local:      cd backend && python scripts/seed_frecuencia_lsii.py
Uso contenedor: docker compose exec backend python scripts/seed_frecuencia_lsii.py

Vive en backend/scripts/ (no en la raíz) porque el contenedor solo copia backend/
a /app — igual que los demás seeds ejecutables (p.ej. seed_costo_visita.py)."""
import sys
from pathlib import Path

# parents[1] = el directorio backend/ (en el contenedor, /app), como los seeds hermanos.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# Importar todos los modelos para resolver las relaciones ORM entre esquemas.
from app.models import usuario, dimensiones, hechos, formacion, visita  # noqa: F401
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
