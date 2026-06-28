# --- bootstrap: permite ejecutar este script desde backend/scripts/<bucket>/ ---
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
# ---------------------------------------------------------------------------
"""
Fix: corrige PuntajePct de UBICACION_TERRITORIAL_CM (tenía escala de 10% en vez de 30%)
y cierra el gap entre D (<=0.44) y C (>=0.46) ajustando D a <=0.4599.
Luego re-ejecuta el SP sobre todos los lotes existentes.
"""
import sys
sys.path.insert(0, ".")
from app.db.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # 1. Corregir PuntajePct de UBICACION_TERRITORIAL_CM
    print("Corrigiendo PuntajePct de UBICACION_TERRITORIAL_CM...")
    updates = [
        ("UBI_CM_05", 0.3000),  # Alta    → 30% × 100%
        ("UBI_CM_04", 0.2400),  # Buena   → 30% × 80%
        ("UBI_CM_03", 0.1800),  # Media   → 30% × 60%
        ("UBI_CM_02", 0.1200),  # Baja    → 30% × 40%
        ("UBI_CM_01", 0.0600),  # Mala    → 30% × 20%
    ]
    for codigo, puntaje in updates:
        n = db.execute(text("""
            UPDATE cat.DimReglaCategoriaMedica
            SET PuntajePct = :p
            WHERE CodigoRegla = :c
        """), {"c": codigo, "p": puntaje}).rowcount
        print(f"  {codigo}: PuntajePct = {puntaje}  ({n} filas actualizadas)")

    # 2. Cerrar gap entre D y C (D: 0.0000-0.4400 → 0.0000-0.4599)
    print("\nCerrando gap entre Clase D y C...")
    n = db.execute(text("""
        UPDATE cat.DimClasificacionMedica
        SET PuntajeMaxPct = 0.459900
        WHERE Clase = 'D' AND PuntajeMaxPct < 0.46
    """)).rowcount
    print(f"  Clase D PuntajeMaxPct → 0.4599 ({n} filas)")

    db.commit()
    print("\nCambios guardados.")

    # 3. Re-ejecutar el SP sobre cada lote existente
    lotes = db.execute(text("SELECT LoadBatchKey FROM cat.LoadBatch ORDER BY LoadBatchKey")).fetchall()
    if not lotes:
        print("No hay lotes para recalcular.")
    else:
        print(f"\nRe-calculando {len(lotes)} lote(s)...")
        for (key,) in lotes:
            # Borrar snapshot y detalle del lote para recalcular limpio
            db.execute(text("DELETE FROM cat.FactMedicoCategoriaDetalle WHERE MedicoCategoriaKey IN "
                           "(SELECT MedicoCategoriaKey FROM cat.FactMedicoCategoriaSnapshot WHERE LoadBatchKey=:k)"), {"k": key})
            db.execute(text("DELETE FROM cat.FactMedicoCategoriaSnapshot WHERE LoadBatchKey=:k"), {"k": key})
            db.execute(text("UPDATE cat.LoadBatch SET Estado='VALIDADO' WHERE LoadBatchKey=:k"), {"k": key})
            db.execute(text("EXEC cat.sp_CalcularCategoriaMedica @LoadBatchKey=:k"), {"k": key})
            db.commit()
            print(f"  Lote {key}: recalculado.")

    # 4. Mostrar resultado final
    print("\n=== Resultado final ===")
    row = db.execute(text("""
        SELECT COUNT(*),
               SUM(CASE WHEN CategoriaCalculada='A' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='B' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='C' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='D' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada IS NULL THEN 1 ELSE 0 END),
               MIN(PuntajeTotalPct), MAX(PuntajeTotalPct)
        FROM cat.FactMedicoCategoriaSnapshot
    """)).fetchone()
    print(f"  Total={row[0]}  A={row[1]}  B={row[2]}  C={row[3]}  D={row[4]}  Sin cat={row[5]}")
    print(f"  Puntaje MIN={float(row[6]):.4f}  MAX={float(row[7]):.4f}")

except Exception as e:
    db.rollback()
    print(f"ERROR: {e}")
    raise
finally:
    db.close()
