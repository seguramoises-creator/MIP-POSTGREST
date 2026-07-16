"""
Corrección de datos: normaliza el `ciclo_alta_id` de los médicos del Panel (Visita).

Problema: la carga masiva dejó a TODOS los médicos con ciclo_alta_id = el ciclo
más reciente al momento de importar (p. ej. C12-2026). Como el alta surte efecto
"el ciclo siguiente" (regla de `cuenta_en_ciclo`), ningún médico resulta VIGENTE
en los ciclos de trabajo (C01..C11), y el panel efectivo sale en 0 aunque haya
médicos y visitas registradas -> Dashboard de Cobertura en blanco.

Solución: fijar el alta de cada médico al PRIMER ciclo del año de su país
(C01), de modo que quede vigente en los ciclos siguientes. No toca médicos que
ya tienen un alta temprana ni cambia estado_aprobacion/activo.

Uso:
  cd backend && PYTHONPATH=. ./venv/Scripts/python scripts/fix_medico_alta.py           # aplica
  cd backend && PYTHONPATH=. ./venv/Scripts/python scripts/fix_medico_alta.py --dry-run  # solo reporta
"""
from __future__ import annotations
import sys
from sqlalchemy import text
from app.db.database import SessionLocal


def main() -> None:
    dry = "--dry-run" in sys.argv
    db = SessionLocal()
    try:
        # C01 (menor orden) por país.
        c01 = {r.pais_codigo: r.id for r in db.execute(text('''
            SELECT DISTINCT ON (pais_codigo) pais_codigo, id
            FROM "Config"."DIM_Ciclo" ORDER BY pais_codigo, anio ASC, numero ASC
        ''')).fetchall()}
        print("C01 por país:", c01)

        # Médicos cuyo alta NO es el C01 de su país (candidatos a corregir).
        filas = db.execute(text('''
            SELECT m.id, r.pais_codigo
            FROM "Visita"."DIM_MedicoVisita" m
            JOIN "Config"."DIM_RM" r ON r.id = m.vm_id
        ''')).fetchall()

        por_pais: dict[str, list[int]] = {}
        for f in filas:
            destino = c01.get(f.pais_codigo)
            if destino is not None:
                por_pais.setdefault(f.pais_codigo, []).append(f.id)

        total = 0
        for pais, ids in por_pais.items():
            destino = c01[pais]
            if dry:
                print(f"  {pais}: {len(ids)} médicos -> alta=C01 (id={destino})  [dry-run]")
                continue
            n = db.execute(text('''
                UPDATE "Visita"."DIM_MedicoVisita"
                SET ciclo_alta_id = :dest
                WHERE id = ANY(:ids) AND ciclo_alta_id IS DISTINCT FROM :dest
            '''), {"dest": destino, "ids": ids}).rowcount
            total += n
            print(f"  {pais}: {n} médicos actualizados -> alta=C01 (id={destino})")

        if not dry:
            db.commit()
            print(f"\nTotal corregidos: {total}")
        else:
            print("\n(dry-run: no se escribió nada)")
    finally:
        db.close()


if __name__ == "__main__":
    main()
