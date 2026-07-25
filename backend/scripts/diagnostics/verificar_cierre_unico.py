"""
Verificacion SOLO LECTURA, directa y simple: dado que solo existe UN cierre real en
todo el historial (CR, C12-2026), responde dos preguntas concretas:

1. Ese cierre, ¿corrio ANTES o DESPUES del fix de aislamiento por pais (commit
   8427bb0, 2026-07-23 21:27:28 -0400)? Si corrio antes, el bug viejo habria tocado
   por error a TODOS los medicos del sistema (no solo a los de CR).
2. ¿Algun medico que NO es de CR tiene hoy ciclos_sin_visita > 0? Si el bug de verdad
   contamino y nada lo reseteo despues, deberian aparecer con al menos 1.

No escribe nada en la base de datos.

Uso:
    docker compose exec backend python scripts/diagnostics/verificar_cierre_unico.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from datetime import datetime, timezone

from app.db.database import SessionLocal
from app.models.visita import MedicoVisita, CierreCicloVisita
from app.models.dimensiones import Ciclo, RepresentanteMedico

FIX_DEPLOY_UTC = datetime(2026, 7, 24, 1, 27, 28, tzinfo=timezone.utc)  # 2026-07-23 21:27:28 -0400


def main():
    db = SessionLocal()
    try:
        cierres = db.query(CierreCicloVisita).all()
        print(f"Total de cierres reales en el historial: {len(cierres)}")
        for c in cierres:
            ciclo = db.query(Ciclo).filter(Ciclo.id == c.ciclo_id).first()
            fecha = c.fecha_cierre
            if fecha and fecha.tzinfo is None:
                fecha = fecha.replace(tzinfo=timezone.utc)
            antes_o_despues = "ANTES del fix (riesgo real)" if fecha and fecha < FIX_DEPLOY_UTC else "DESPUES del fix (sin riesgo)"
            print(f"  cierre_id={c.id}  ciclo={ciclo.nombre if ciclo else c.ciclo_id}  "
                  f"pais={ciclo.pais_codigo if ciclo else '?'}  fecha_cierre={c.fecha_cierre}  -> {antes_o_despues}")

        print()
        rms_pais = dict(db.query(RepresentanteMedico.id, RepresentanteMedico.pais_codigo).all())
        medicos = db.query(MedicoVisita).all()

        por_pais_mayor_cero: dict[str, int] = {}
        por_pais_total: dict[str, int] = {}
        for m in medicos:
            pais = rms_pais.get(m.vm_id, "?")
            por_pais_total[pais] = por_pais_total.get(pais, 0) + 1
            if m.ciclos_sin_visita and m.ciclos_sin_visita > 0:
                por_pais_mayor_cero[pais] = por_pais_mayor_cero.get(pais, 0) + 1

        print("Medicos con ciclos_sin_visita > 0 HOY, por pais:")
        for pais in sorted(por_pais_total):
            n = por_pais_mayor_cero.get(pais, 0)
            print(f"  {pais}: {n} de {por_pais_total[pais]} medicos con ciclos_sin_visita > 0")

    finally:
        db.close()


if __name__ == "__main__":
    main()
