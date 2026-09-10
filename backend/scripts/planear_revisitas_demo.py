"""Programa la REVISITA de los médicos a los que el representante ya hizo la Vista.

Sin esto no hay ciclo completo que enseñar: la planeación traía 25 Vistas y ninguna
Revisita, así que el botón «Revisita» salía bloqueado en todas las fichas — que es lo
correcto (la agenda manda), pero deja fuera medio flujo en una demostración.

Se programa la Revisita SOLO de quien ya tiene la Vista registrada: es el orden real
del ciclo, y así la agenda la muestra como pendiente en cuanto se abre la pantalla.

    python scripts/planear_revisitas_demo.py --vm VM-4
    python scripts/planear_revisitas_demo.py --vm VM-4 --aplicar
"""
import argparse
import sys
from datetime import datetime, timezone

sys.path.insert(0, ".")

from sqlalchemy import text  # noqa: E402

from app.db.database import SessionLocal  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--vm", required=True)
    ap.add_argument("--aplicar", action="store_true")
    args = ap.parse_args()

    db = SessionLocal()
    rm = db.execute(text('SELECT id, codigo, nombre, pais_codigo FROM "Config"."DIM_RM" '
                         'WHERE codigo = :c'), {"c": args.vm}).first()
    if rm is None:
        print(f"No existe {args.vm}.")
        return 2
    ciclo = db.execute(text('SELECT id, nombre FROM "Config"."DIM_Ciclo" '
                            'WHERE pais_codigo = :p AND cerrado = false '
                            'ORDER BY anio DESC, numero DESC LIMIT 1'),
                       {"p": rm.pais_codigo}).first()

    # Quien ya tiene la Vista hecha y NO tiene la Revisita planeada.
    faltan = db.execute(text('''
        SELECT DISTINCT v.medico_id, m.nombre_completo,
               p.semana, p.dia_semana, p.hora_estimada
        FROM "Visita"."FactVisita" v
        JOIN "Visita"."DIM_MedicoVisita" m ON m.id = v.medico_id
        JOIN "Visita"."PlaneacionCiclo" p
          ON p.vm_id = v.vm_id AND p.ciclo_id = v.ciclo_id
         AND p.medico_id = v.medico_id AND p.tipo_visita = 'V'
        WHERE v.vm_id = :vm AND v.ciclo_id = :c AND v.ejecutada
          AND NOT EXISTS (SELECT 1 FROM "Visita"."PlaneacionCiclo" r
                          WHERE r.vm_id = v.vm_id AND r.ciclo_id = v.ciclo_id
                            AND r.medico_id = v.medico_id AND r.tipo_visita = 'R')
        ORDER BY v.medico_id'''), {"vm": rm.id, "c": ciclo.id}).all()

    print(f"{rm.codigo} · {rm.nombre} · ciclo {ciclo.nombre}")
    print(f"Revisitas por programar: {len(faltan)}")
    for f in faltan:
        print(f"  {f.nombre_completo[:34]:<34} semana {f.semana} · {f.dia_semana} {f.hora_estimada or ''}")

    if not args.aplicar:
        print("\n(simulación) No se escribió nada. Añade --aplicar.")
        return 0

    ahora = datetime.now(timezone.utc).replace(tzinfo=None)
    for f in faltan:
        db.execute(text(
            'INSERT INTO "Visita"."PlaneacionCiclo" '
            '(vm_id, ciclo_id, medico_id, tipo_visita, semana, dia_semana, hora_estimada, '
            ' fecha_creacion) '
            "VALUES (:vm, :c, :m, 'R', :s, :d, :h, :ts)"),
            {"vm": rm.id, "c": ciclo.id, "m": f.medico_id, "s": f.semana,
             "d": f.dia_semana, "h": f.hora_estimada, "ts": ahora})
    db.commit()
    print(f"\nProgramadas {len(faltan)} revisitas.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
