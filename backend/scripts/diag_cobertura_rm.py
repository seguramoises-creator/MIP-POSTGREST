"""
Diagnóstico (y corrección opcional) de Cobertura de Visita para UNA RM.

Explica por qué el Dashboard de Cobertura sale en "Panel de 0 médicos": la regla
`cuenta_en_ciclo` excluye a un médico si (a) estado_aprobacion ∈ {PENDIENTE_ALTA,
RECHAZADO} o (b) su ciclo_alta es >= el ciclo consultado (alta efectiva el ciclo
siguiente). Los médicos creados desde el Panel nacen PENDIENTE_ALTA con alta=ciclo
actual, así que no cuentan hasta ser aprobados Y hasta el ciclo siguiente.

Uso (en el servidor, dentro del contenedor):
  docker compose exec backend python scripts/diag_cobertura_rm.py "ADRIANA RODRIGUEZ"
  docker compose exec backend python scripts/diag_cobertura_rm.py "ADRIANA RODRIGUEZ" --fix

--fix: aprueba (estado_aprobacion=APROBADO) y fija el alta al C01 del país de la RM,
       de modo que sus médicos cuenten en el ciclo abierto actual. Solo esa RM.
"""
from __future__ import annotations
import sys
from sqlalchemy import text
from app.db.database import SessionLocal


def main() -> None:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    fix = "--fix" in sys.argv
    if not args:
        print('Falta el nombre o código de la RM. Ej: python scripts/diag_cobertura_rm.py "ADRIANA RODRIGUEZ"')
        return
    patron = args[0].upper()

    db = SessionLocal()
    try:
        rms = db.execute(text('''
            SELECT id, codigo, nombre, pais_codigo
            FROM "Config"."DIM_RM"
            WHERE UPPER(nombre) LIKE :p OR UPPER(codigo) = :c
            ORDER BY nombre
        '''), {"p": f"%{patron}%", "c": patron}).fetchall()
        if not rms:
            print(f"No se encontró RM con nombre/código que contenga '{patron}'.")
            return
        if len(rms) > 1:
            print("Varias RM coinciden — precisa el nombre/código:")
            for r in rms:
                print(f"  id={r.id}  {r.codigo}  {r.nombre}  ({r.pais_codigo})")
            return
        rm = rms[0]
        print(f"RM: id={rm.id}  {rm.codigo}  {rm.nombre}  pais={rm.pais_codigo}")

        # Ciclo abierto del país (el que muestra el dashboard) + su orden.
        ciclo = db.execute(text('''
            SELECT id, numero, anio FROM "Config"."DIM_Ciclo"
            WHERE pais_codigo = :p AND cerrado = false
            ORDER BY anio DESC, numero DESC LIMIT 1
        '''), {"p": rm.pais_codigo}).fetchone()
        print(f"Ciclo abierto: {('Ciclo '+str(ciclo.numero)+' '+str(ciclo.anio)+' (id='+str(ciclo.id)+')') if ciclo else 'NINGUNO'}")

        # Médicos del panel de esta RM.
        meds = db.execute(text('''
            SELECT id, nombre_completo, activo, estado_aprobacion, ciclo_alta_id, ciclo_baja_id
            FROM "Visita"."DIM_MedicoVisita" WHERE vm_id = :vm
        '''), {"vm": rm.id}).fetchall()
        print(f"\nMédicos en el panel: {len(meds)}")
        # Desglose por estado
        from collections import Counter
        print("  por estado_aprobacion:", dict(Counter(m.estado_aprobacion for m in meds)))
        print("  por ciclo_alta_id     :", dict(Counter(m.ciclo_alta_id for m in meds)))
        print("  activos               :", sum(1 for m in meds if m.activo))

        # Órdenes de ciclo del país (para simular cuenta_en_ciclo).
        ordenes = {r.id: i for i, r in enumerate(db.execute(text('''
            SELECT id FROM "Config"."DIM_Ciclo" WHERE pais_codigo = :p
            ORDER BY anio ASC, numero ASC
        '''), {"p": rm.pais_codigo}).fetchall())}
        co = ordenes.get(ciclo.id) if ciclo else None

        def cuenta(m) -> bool:
            if not m.activo: return False
            if m.estado_aprobacion in ("PENDIENTE_ALTA", "RECHAZADO"): return False
            if co is None: return True
            if m.ciclo_alta_id is not None:
                oa = ordenes.get(m.ciclo_alta_id)
                if oa is not None and co <= oa: return False
            if m.ciclo_baja_id is not None:
                ob = ordenes.get(m.ciclo_baja_id)
                if ob is not None and co > ob: return False
            return True

        cuentan = [m for m in meds if cuenta(m)]
        print(f"\n>>> Médicos que CUENTAN en el ciclo abierto: {len(cuentan)} de {len(meds)}")
        if meds and not cuentan:
            print("    (por eso el panel sale en 0). Razones vistas arriba:")
            print("    - PENDIENTE_ALTA/RECHAZADO → falta aprobar.")
            print("    - ciclo_alta = ciclo actual → alta efectiva el ciclo siguiente.")

        # Visitas registradas del ciclo.
        if ciclo:
            v = db.execute(text('''
                SELECT COUNT(*) n, COUNT(DISTINCT medico_id) md
                FROM "Visita"."FactVisita" WHERE vm_id = :vm AND ciclo_id = :c AND ejecutada = true
            '''), {"vm": rm.id, "c": ciclo.id}).fetchone()
            print(f"\nVisitas ejecutadas en el ciclo: {v.n} (a {v.md} médicos distintos)")

        if fix and ciclo:
            c01 = db.execute(text('''
                SELECT id FROM "Config"."DIM_Ciclo" WHERE pais_codigo = :p
                ORDER BY anio ASC, numero ASC LIMIT 1
            '''), {"p": rm.pais_codigo}).scalar()
            n = db.execute(text('''
                UPDATE "Visita"."DIM_MedicoVisita"
                SET estado_aprobacion = 'APROBADO', ciclo_alta_id = :c01
                WHERE vm_id = :vm AND activo = true
                  AND (estado_aprobacion IN ('PENDIENTE_ALTA','RECHAZADO')
                       OR ciclo_alta_id IS DISTINCT FROM :c01)
            '''), {"vm": rm.id, "c01": c01}).rowcount
            db.commit()
            print(f"\n[FIX] {n} médicos → APROBADO + alta=C01 (id={c01}). Recarga el dashboard.")
        elif fix:
            print("\n[FIX] No hay ciclo abierto para el país; no se aplicó nada.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
