# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
"""
_reset_datos.py
===============
Borra TODA la información de tablas DIM y FACT y deja la BD lista
para una carga desde cero.

Conserva:
  - Security.DIM_Usuario (usuarios del sistema, incluyendo admin)

Orden de borrado:
  1. FACT_* (dependen de DIM_*)
  2. DIM_* en orden inverso de dependencias FK

    cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
    .\\venv\\Scripts\\activate
    python _reset_datos.py
"""

import sys

DB_SERVER   = "127.0.0.1"
DB_PORT     = 1433
DB_NAME     = "SCGCPR"
DB_USER     = "segura"
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')

# ── Tablas en orden de borrado (las primeras dependen de las últimas) ──
TABLAS = [
    # ── FACT / ETL / Audit ──────────────────────────────────────────
    ("DW",    "FACT_ResultadoIndicador"),
    ("DW",    "FACT_ScoreIntegralRM"),
    ("DW",    "FACT_RankingRM"),
    ("DW",    "FACT_Ranking"),          # tabla anterior (puede no existir)
    ("DW",    "FACT_RendimientoComercial"),   # legacy (puede no existir)
    ("DW",    "FACT_Ventas"),           # legacy
    ("DW",    "FACT_EVOIR"),            # legacy
    ("DW",    "FACT_Coaching"),         # legacy
    ("DW",    "FACT_Capacitacion"),     # legacy
    ("DW",    "FACT_Reconocimiento"),
    ("ETL",   "FACT_CargaExcel"),
    ("Audit", "FACT_Auditoria"),

    # ── DIM dependientes (hijos primero) ────────────────────────────
    ("Config", "DIM_IndicadorTabla"),
    ("Config", "DIM_MetaIndicador"),
    ("Config", "DIM_ReglaElegibilidad"),
    ("Config", "DIM_RM"),
    ("Config", "DIM_Gerente"),
    ("Config", "DIM_Indicador"),
    ("Config", "DIM_Ciclo"),
    ("Config", "DIM_Linea"),
    ("Config", "DIM_Mes"),
    ("Config", "DIM_Premio"),
    ("Config", "DIM_CategoriaDesempeno"),
    ("Config", "DIM_KpiDashboard"),
    ("Config", "DIM_Pais"),             # base: va al final
]


def main():
    import pymssql

    print("=" * 60)
    print("RESET DATOS — borra DIM y FACT, conserva usuarios")
    print("=" * 60)
    print()
    print("ADVERTENCIA: esta operación es IRREVERSIBLE.")
    print("Se borrarán TODOS los catálogos, KPIs y rankings.")
    print("Los usuarios del sistema (admin, etc.) se conservan.")
    print()
    resp = input("Escribe  SI  para confirmar: ").strip()
    if resp != "SI":
        print("Cancelado.")
        sys.exit(0)

    print()
    print("Conectando ...")
    conn = pymssql.connect(
        server=DB_SERVER, port=DB_PORT,
        database=DB_NAME, user=DB_USER, password=DB_PASSWORD,
        as_dict=True,
    )
    cur = conn.cursor()
    print("OK\n")

    # Deshabilitar FK checks no está disponible en SQL Server de forma global,
    # pero podemos usar NOCHECK / DELETE en orden correcto.

    total_borradas = 0
    skipped = 0

    for schema, tabla in TABLAS:
        full = f"[{schema}].[{tabla}]"
        # Verificar si la tabla existe antes de borrar
        cur.execute(f"""
            SELECT COUNT(*) AS existe
            FROM INFORMATION_SCHEMA.TABLES
            WHERE TABLE_SCHEMA = '{schema}' AND TABLE_NAME = '{tabla}'
        """)
        row = cur.fetchone()
        if not row or not row["existe"]:
            print(f"  SKIP {full} (no existe)")
            skipped += 1
            continue

        try:
            cur.execute(f"DELETE FROM {full}")
            n = cur.rowcount if cur.rowcount >= 0 else 0
            conn.commit()
            print(f"  ✓ {full:<45}  {n:>6} filas borradas")
            total_borradas += n
        except Exception as e:
            conn.rollback()
            print(f"  ERR {full}: {e}")

    cur.close()
    conn.close()

    print()
    print("=" * 60)
    print(f"COMPLETADO — {total_borradas} filas borradas en total")
    print(f"Tablas inexistentes (ignoradas): {skipped}")
    print()
    print("Pasos siguientes:")
    print("  1. Admin → Importar DIMs → subir DIM_MIP_FINAL.xlsx")
    print("     Seleccionar TODAS las hojas → Importar")
    print("  2. ETL → Cargar → subir FACT_MIP_FINAL.xlsx")
    print("     tipo_archivo=KPI_RM, modo=PRODUCCION → Cargar")
    print("  3. Admin → Ciclos → verificar que los ciclos con")
    print("     datos están en estado Abierto")
    print("  4. Configuración → Recálculo → recalcular cada ciclo")
    print("     (o se dispara automáticamente tras el ETL)")
    print("=" * 60)


if __name__ == "__main__":
    main()
