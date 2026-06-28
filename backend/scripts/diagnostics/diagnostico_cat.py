# --- bootstrap: permite ejecutar este script desde backend/scripts/<bucket>/ ---
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
# ---------------------------------------------------------------------------
"""
Diagnóstico del módulo de Categorización Médica.
Muestra: clasificaciones configuradas, muestra de reglas y scores calculados.
"""
import sys
sys.path.insert(0, ".")
from app.db.database import SessionLocal
from sqlalchemy import text

db = SessionLocal()
try:
    print("\n=== DimClasificacionMedica (rangos A/B/C/D) ===")
    rows = db.execute(text("""
        SELECT p.CodigoPais, c.Clase, c.PuntajeMinPct, c.PuntajeMaxPct, c.Activo,
               c.VigenteDesde, c.VigenteHasta
        FROM cat.DimClasificacionMedica c
        JOIN cat.DimPais p ON p.PaisKey = c.PaisKey
        ORDER BY c.Clase, p.CodigoPais
    """)).fetchall()
    if not rows:
        print("  [VACÍO] No hay clasificaciones cargadas — los médicos no pueden ser asignados a A/B/C/D")
    for r in rows:
        print(f"  País={r[0]} Clase={r[1]} Min={float(r[2]):.4f} Max={float(r[3]):.4f} Activo={r[4]} Desde={r[5]} Hasta={r[6]}")

    print("\n=== DimReglaCategoriaMedica — muestra por componente (primeras 5 reglas cada uno) ===")
    rows = db.execute(text("""
        SELECT TOP 30 p.CodigoPais, co.CodigoComponente, r.CodigoRegla,
               r.PuntajePct, r.PesoComponentePct,
               r.ValorMinimo, r.ValorMaximo, r.ValorTexto, r.Criterio, r.Activo
        FROM cat.DimReglaCategoriaMedica r
        JOIN cat.DimPais p ON p.PaisKey = r.PaisKey
        JOIN cat.DimComponenteCategoria co ON co.ComponenteKey = r.ComponenteKey
        WHERE r.Activo = 1
        ORDER BY co.CodigoComponente, r.Criterio DESC
    """)).fetchall()
    if not rows:
        print("  [VACÍO] No hay reglas cargadas — el SP no puede calcular puntajes")
    for r in rows:
        print(f"  [{r[1]}] Regla={r[2]} PuntajePct={float(r[3]):.4f} PesoPct={float(r[4]):.4f} "
              f"Min={r[5]} Max={r[6]} Texto={r[7]} Criterio={r[8]}")

    print("\n=== FactMedicoCategoriaSnapshot — distribución de puntajes ===")
    row = db.execute(text("""
        SELECT COUNT(*),
               MIN(PuntajeTotalPct), MAX(PuntajeTotalPct), AVG(PuntajeTotalPct),
               SUM(CASE WHEN CategoriaCalculada='A' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='B' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='C' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada='D' THEN 1 ELSE 0 END),
               SUM(CASE WHEN CategoriaCalculada IS NULL THEN 1 ELSE 0 END)
        FROM cat.FactMedicoCategoriaSnapshot
    """)).fetchone()
    if row and row[0]:
        print(f"  Total={row[0]}  Min={float(row[1]):.4f}  Max={float(row[2]):.4f}  Avg={float(row[3]):.4f}")
        print(f"  A={row[4]}  B={row[5]}  C={row[6]}  D={row[7]}  Sin categoría={row[8]}")
    else:
        print("  [VACÍO]")

    print("\n=== Muestra de puntajes individuales (10 primeras filas) ===")
    rows = db.execute(text("""
        SELECT TOP 10 f.PuntajeTotalPct, f.CategoriaCalculada, f.CategoriaExcel,
               f.EstadoCalculo, f.MensajeCalculo
        FROM cat.FactMedicoCategoriaSnapshot f
        ORDER BY f.MedicoCategoriaKey
    """)).fetchall()
    for r in rows:
        puntaje = f"{float(r[0]):.4f}" if r[0] is not None else "NULL"
        print(f"  Puntaje={puntaje} CalcCat={r[1]} ExcelCat={r[2]} Estado={r[3]} Msg={r[4]}")

    print("\n=== Componentes cargados ===")
    rows = db.execute(text("""
        SELECT CodigoComponente, NombreComponente, PesoComponentePct, Requerido, Activo
        FROM cat.DimComponenteCategoria ORDER BY CodigoComponente
    """)).fetchall()
    for r in rows:
        print(f"  {r[0]} | {r[1]} | Peso={float(r[2]):.4f} | Req={r[3]} | Activo={r[4]}")

finally:
    db.close()

print("\nDiagnóstico completo.\n")
