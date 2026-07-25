"""
Diagnostico SOLO LECTURA: desglosa el calculo real de calcular_iup() (motor de 5
componentes usado por Ranking Regional/Anual) para uno o mas representantes, en un
pais/ciclo dado. Util para explicar de donde sale el score_total que se ve en la
pantalla de Ranking (Regional/Historico Anual).

No escribe nada en la base de datos.

Uso:
    docker compose exec backend python scripts/diagnostics/desglose_ranking_rm.py DO "Ciclo 7 2026"
    docker compose exec backend python scripts/diagnostics/desglose_ranking_rm.py DO "Ciclo 7 2026" "CARLOS MORENO" "KALAJAN FERRERAS"

Si no se pasan nombres, muestra el desglose de TODOS los representantes del
pais/ciclo indicado (puede ser una lista larga).
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from app.db.database import SessionLocal
from app.models.dimensiones import Ciclo, RepresentanteMedico
from app.services.iup_service import calcular_iup, _obtener_pesos


def main():
    if len(sys.argv) < 3:
        print("Uso: desglose_ranking_rm.py <PAIS_CODIGO> <NOMBRE_CICLO> [nombre_rm ...]")
        sys.exit(1)

    pais_codigo = sys.argv[1].upper()
    nombre_ciclo = sys.argv[2]
    nombres_buscados = [n.upper() for n in sys.argv[3:]]

    db = SessionLocal()
    try:
        ciclo = (
            db.query(Ciclo)
            .filter(Ciclo.pais_codigo == pais_codigo)
            .filter((Ciclo.nombre == nombre_ciclo) | (Ciclo.nombre_canonico == nombre_ciclo))
            .first()
        )
        if not ciclo:
            print(f"No se encontro un ciclo '{nombre_ciclo}' para {pais_codigo}.")
            print("Ciclos disponibles:")
            for c in db.query(Ciclo).filter(Ciclo.pais_codigo == pais_codigo).order_by(Ciclo.numero).all():
                print(f"  id={c.id}  nombre={c.nombre}  nombre_canonico={getattr(c, 'nombre_canonico', None)}")
            sys.exit(1)

        print(f"Ciclo encontrado: id={ciclo.id}  nombre={ciclo.nombre}  pais={pais_codigo}")
        pesos = _obtener_pesos(db)
        print(f"Pesos vigentes (leidos de DIM_Indicador.peso_iup, o default si no hay config): {pesos}")
        print()

        rms = db.query(RepresentanteMedico).filter(RepresentanteMedico.pais_codigo == pais_codigo).all()
        if nombres_buscados:
            rms = [r for r in rms if any(n in r.nombre.upper() for n in nombres_buscados)]

        if not rms:
            print("No se encontraron representantes que coincidan.")
            sys.exit(1)

        for rm in rms:
            r = calcular_iup(db, rm_id=rm.id, pais_codigo=pais_codigo, ciclo_id=ciclo.id)
            print(f"=== {rm.nombre}  (rm_id={rm.id}) ===")
            print(f"  Productividad  : {r['iup_productividad']:>8}  x peso {pesos.get('PRODUCTIVIDAD', 0):.4f}")
            print(f"  Comercial      : {r['iup_comercial']:>8}  x peso {pesos.get('COMERCIAL', 0):.4f}")
            print(f"  Coaching       : {r['iup_coaching']:>8}  x peso {pesos.get('COACHING', 0):.4f}")
            print(f"  Capacitacion   : {r['iup_capacitacion']:>8}  x peso {pesos.get('CAPACITACION', 0):.4f}")
            print(f"  Consistencia   : {r['iup_consistencia']:>8}  x peso {pesos.get('CONSISTENCIA', 0):.4f}")
            print(f"  SCORE TOTAL    : {r['score_total']}")
            print()

    finally:
        db.close()


if __name__ == "__main__":
    main()
