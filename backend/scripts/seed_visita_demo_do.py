"""
Siembra de datos DEMO para el módulo Visita — ciclo 17 (C03-2026, país DO).

Objetivo: poblar Planeación + Visitas registradas para que Cobertura Predictiva /
Cobertura Diaria muestren números en la demo (el dashboard vivo se alimenta de
Visita.PlaneacionCiclo = programado y Visita.FactVisita = realizado).

Características:
  - Idempotente: borra su propia siembra previa (FactVisita con comentario
    '[SEED-DEMO]' y PlaneacionCiclo de los VM sembrados en el ciclo objetivo).
  - No toca filas reales existentes (p. ej. vm_id=26).
  - Genera un espectro Verde/Amarillo/Rojo variando la fracción visitada por VM.
  - Deja médicos planeados sin visitar (→ "no visitado") y un par de NO-Visita.

Uso:
  cd backend && ./venv/Scripts/python scripts/seed_visita_demo_do.py
  # limpiar sin sembrar:
  ./venv/Scripts/python scripts/seed_visita_demo_do.py --limpiar
"""
from __future__ import annotations
import sys
from datetime import datetime, timedelta

from sqlalchemy import text
from app.db.database import SessionLocal

CICLO_ID = 17               # C03-2026 (DO)
MARCA = "[SEED-DEMO]"
PLAN_POR_VM = 25            # médicos planeados por VM (tipo_visita='V')
NO_VISITA_POR_VM = 2        # médicos planeados marcados como NO-Visita (ejecutada=False)

# (vm_id, visitados_ejecutados) → produce un espectro de estados de cobertura.
# Incluye a Carlos Moreno (vm_id=11).
PLAN_VMS = [
    (6, 24), (2, 23),           # Verde  (96% / 92%)
    (5, 22), (9, 22),           # Amarillo (88%)
    (11, 20), (12, 16),         # Rojo (80% / 64%) — vm 11 = Carlos Moreno
    (4, 12), (13, 8),           # Rojo (48% / 32%)
]
DIAS = ["Lunes", "Martes", "Miércoles", "Jueves", "Viernes"]
PRODUCTOS_DEMO = "AMOXIDAL:2|BROMICEL:1"


def _medicos_de_vm(db, vm_id: int, limite: int) -> list[int]:
    rows = db.execute(text('''
        SELECT id FROM "Visita"."DIM_MedicoVisita"
        WHERE vm_id = :vm AND activo = true AND estado_aprobacion = 'APROBADO'
        ORDER BY id
        LIMIT :lim
    '''), {"vm": vm_id, "lim": limite}).fetchall()
    return [r.id for r in rows]


def limpiar(db) -> None:
    vm_ids = tuple(vm for vm, _ in PLAN_VMS)
    d1 = db.execute(text('''
        DELETE FROM "Visita"."FactVisita"
        WHERE ciclo_id = :c AND comentario = :m AND vm_id = ANY(:vms)
    '''), {"c": CICLO_ID, "m": MARCA, "vms": list(vm_ids)}).rowcount
    d2 = db.execute(text('''
        DELETE FROM "Visita"."PlaneacionCiclo"
        WHERE ciclo_id = :c AND vm_id = ANY(:vms)
    '''), {"c": CICLO_ID, "vms": list(vm_ids)}).rowcount
    db.commit()
    print(f"  Limpieza: {d1} visitas + {d2} planeaciones demo eliminadas.")


def sembrar(db) -> None:
    ciclo = db.execute(text(
        'SELECT fecha_inicio, fecha_fin, nombre FROM "Config"."DIM_Ciclo" WHERE id = :c'
    ), {"c": CICLO_ID}).fetchone()
    if not ciclo:
        print(f"  ERROR: ciclo_id={CICLO_ID} no existe."); return
    inicio = ciclo.fecha_inicio
    print(f"  Ciclo {ciclo.nombre} ({inicio} .. {ciclo.fecha_fin})")

    # El panel de "Cobertura Visita" solo cuenta médicos VIGENTES para el ciclo
    # (regla de alta/baja: el alta surte efecto el ciclo siguiente). La importación
    # masiva dejó a todos los médicos con ciclo_alta_id = C12-2026, así que ninguno
    # es vigente en C03. Normalizamos el alta de los médicos sembrados al primer ciclo
    # del año (C01) para que cuenten en C03 y el dashboard no salga en blanco.
    alta = db.execute(text('''
        SELECT id FROM "Config"."DIM_Ciclo"
        WHERE pais_codigo = 'DO' AND anio = 2026 AND numero = 1 LIMIT 1
    ''')).scalar()

    total_plan = total_vis = total_nov = 0
    usados: set[int] = set()
    for vm_id, n_visit in PLAN_VMS:
        medicos = _medicos_de_vm(db, vm_id, PLAN_POR_VM)
        if not medicos:
            print(f"  VM {vm_id}: sin médicos aprobados, se omite."); continue
        usados.update(medicos)

        # 1) Planeación (todos, tipo 'V')
        for i, med in enumerate(medicos):
            db.execute(text('''
                INSERT INTO "Visita"."PlaneacionCiclo"
                    (vm_id, ciclo_id, medico_id, tipo_visita, semana, dia_semana, hora_estimada, fecha_creacion)
                VALUES (:vm, :c, :med, 'V', :sem, :dia, :hora, :fc)
            '''), {
                "vm": vm_id, "c": CICLO_ID, "med": med,
                "sem": (i % 4) + 1, "dia": DIAS[i % 5],
                "hora": f"{8 + (i % 8):02d}:00",
                "fc": datetime.combine(inicio, datetime.min.time()),
            })
        total_plan += len(medicos)

        # 2) Visitas ejecutadas (los primeros n_visit médicos planeados)
        for i, med in enumerate(medicos[:n_visit]):
            fh = datetime.combine(inicio, datetime.min.time()) + timedelta(days=(i % 20), hours=9 + (i % 6))
            db.execute(text('''
                INSERT INTO "Visita"."FactVisita"
                    (vm_id, ciclo_id, medico_id, tipo_visita, fecha_hora, comentario, productos, ejecutada,
                     latitud, longitud)
                VALUES (:vm, :c, :med, 'V', :fh, :com, :prod, true, 18.4861, -69.9312)
            '''), {"vm": vm_id, "c": CICLO_ID, "med": med, "fh": fh, "com": MARCA, "prod": PRODUCTOS_DEMO})
        total_vis += n_visit

        # 3) NO-Visita (médicos planeados no cubiertos, ejecutada=False)
        no_vis = medicos[n_visit:n_visit + NO_VISITA_POR_VM]
        for i, med in enumerate(no_vis):
            fh = datetime.combine(inicio, datetime.min.time()) + timedelta(days=10 + i, hours=11)
            db.execute(text('''
                INSERT INTO "Visita"."FactVisita"
                    (vm_id, ciclo_id, medico_id, tipo_visita, fecha_hora, comentario, ejecutada, causa_no_visita)
                VALUES (:vm, :c, :med, 'V', :fh, :com, false, 'Médico no disponible')
            '''), {"vm": vm_id, "c": CICLO_ID, "med": med, "fh": fh, "com": MARCA})
        total_nov += len(no_vis)

        print(f"  VM {vm_id:>3}: {len(medicos)} planeados · {n_visit} visitados · {len(no_vis)} NO-Visita")

    # Normaliza vigencia de los médicos sembrados (alta C01, sin baja, aprobados/activos).
    if usados and alta:
        n = db.execute(text('''
            UPDATE "Visita"."DIM_MedicoVisita"
            SET ciclo_alta_id = :alta, ciclo_baja_id = NULL,
                estado_aprobacion = 'APROBADO', activo = true
            WHERE id = ANY(:ids)
        '''), {"alta": alta, "ids": list(usados)}).rowcount
        print(f"  Vigencia normalizada (alta=C01-2026) en {n} médicos.")

    db.commit()
    print(f"\n  TOTAL: {total_plan} planeaciones · {total_vis} visitas ejecutadas · {total_nov} NO-Visita")


def main() -> None:
    db = SessionLocal()
    try:
        print("== Siembra demo Visita — ciclo 17 (DO) ==")
        limpiar(db)
        if "--limpiar" in sys.argv:
            print("  Solo limpieza (--limpiar). Listo."); return
        sembrar(db)
        print("== Hecho ==")
    finally:
        db.close()


if __name__ == "__main__":
    main()
