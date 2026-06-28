# --- bootstrap: permite ejecutar este script desde backend/scripts/<bucket>/ ---
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
# ---------------------------------------------------------------------------
"""
Diagnóstico de diferencias Sistema vs Excel en categorización.
Busca: médicos que difieren de categoría + textos que no hacen match.
"""
import sys
sys.path.insert(0, ".")
from app.db.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    # 1. Médicos que difieren + sus puntajes
    print("=== Médicos con categoría diferente (muestra 20) ===")
    rows = db.execute(text("""
        SELECT TOP 20
            m.NombreMedico,
            f.PuntajeTotalPct,
            f.CategoriaCalculada AS Sistema,
            f.CategoriaExcel    AS Excel,
            f.MensajeCalculo
        FROM cat.FactMedicoCategoriaSnapshot f
        JOIN cat.DimMedico m ON m.MedicoKey = f.MedicoKey
        WHERE f.CategoriaCalculada <> f.CategoriaExcel
          AND f.CategoriaExcel IS NOT NULL
        ORDER BY f.PuntajeTotalPct DESC
    """)).fetchall()
    for r in rows:
        print(f"  [{r[2]}→{r[3]}] Puntaje={float(r[1]):.4f}  {r[0]}  Msg={r[4]}")

    # 2. Distribución de puntajes de los que difieren
    print("\n=== Distribución puntaje de médicos que difieren ===")
    rows = db.execute(text("""
        SELECT
            CASE
                WHEN f.PuntajeTotalPct >= 0.86 THEN '>=0.86 (A)'
                WHEN f.PuntajeTotalPct >= 0.66 THEN '0.66-0.85 (B)'
                WHEN f.PuntajeTotalPct >= 0.46 THEN '0.46-0.65 (C)'
                WHEN f.PuntajeTotalPct >= 0.00 THEN '0.00-0.45 (D)'
            END AS Rango,
            f.CategoriaCalculada AS Sistema,
            f.CategoriaExcel AS Excel,
            COUNT(*) AS Cantidad
        FROM cat.FactMedicoCategoriaSnapshot f
        WHERE f.CategoriaCalculada <> f.CategoriaExcel
          AND f.CategoriaExcel IS NOT NULL
        GROUP BY
            CASE
                WHEN f.PuntajeTotalPct >= 0.86 THEN '>=0.86 (A)'
                WHEN f.PuntajeTotalPct >= 0.66 THEN '0.66-0.85 (B)'
                WHEN f.PuntajeTotalPct >= 0.46 THEN '0.46-0.65 (C)'
                WHEN f.PuntajeTotalPct >= 0.00 THEN '0.00-0.45 (D)'
            END,
            f.CategoriaCalculada, f.CategoriaExcel
        ORDER BY Sistema, Excel
    """)).fetchall()
    for r in rows:
        print(f"  Puntaje {r[0]}  Sistema={r[1]} Excel={r[2]}  N={r[3]}")

    # 3. Valores de texto únicos en staging para los componentes de texto
    print("\n=== Valores únicos en stg: KOL ===")
    rows = db.execute(text("""
        SELECT DISTINCT KOL, COUNT(*) AS N
        FROM stg.MedicoCategoriaInput
        GROUP BY KOL ORDER BY N DESC
    """)).fetchall()
    for r in rows:
        print(f"  '{r[0]}' → {r[1]}")

    print("\n=== Valores únicos en stg: RecetasSemana (POTENCIAL_PRESCRIPCION) ===")
    rows = db.execute(text("""
        SELECT DISTINCT RecetasSemana, COUNT(*) AS N
        FROM stg.MedicoCategoriaInput
        GROUP BY RecetasSemana ORDER BY N DESC
    """)).fetchall()
    for r in rows:
        print(f"  '{r[0]}' → {r[1]}")

    print("\n=== Valores únicos en stg: UbicacionTerritorialCM ===")
    rows = db.execute(text("""
        SELECT DISTINCT UbicacionTerritorialCM, COUNT(*) AS N
        FROM stg.MedicoCategoriaInput
        GROUP BY UbicacionTerritorialCM ORDER BY N DESC
    """)).fetchall()
    for r in rows:
        print(f"  '{r[0]}' → {r[1]}")

    print("\n=== Valores de reglas configurados (texto) ===")
    rows = db.execute(text("""
        SELECT co.CodigoComponente, r.CodigoRegla, r.ValorTexto
        FROM cat.DimReglaCategoriaMedica r
        JOIN cat.DimComponenteCategoria co ON co.ComponenteKey = r.ComponenteKey
        WHERE r.ValorTexto IS NOT NULL AND r.Activo = 1
        ORDER BY co.CodigoComponente, r.Criterio DESC
    """)).fetchall()
    for r in rows:
        print(f"  [{r[0]}] {r[1]}: '{r[2]}'")

finally:
    db.close()
