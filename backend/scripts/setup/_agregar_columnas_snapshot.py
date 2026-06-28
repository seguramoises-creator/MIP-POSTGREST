# --- credenciales desde backend/.env (parametrizado, no hardcodear) ---
import os as _os, pathlib as _pl
try:
    from dotenv import load_dotenv as _ld
    _ld(_pl.Path(__file__).resolve().parents[2] / '.env')
except Exception:
    pass
os = _os
# ----------------------------------------------------------------------
# Script de un solo uso: agrega Provincia, Municipio y EstadoConciliacion
# a cat.FactMedicoCategoriaSnapshot si aun no existen.
# Correr desde el directorio backend con el venv activo:
#   python _agregar_columnas_snapshot.py
import sys
import pymssql

DB_SERVER   = "127.0.0.1"
DB_PORT     = 1433
DB_USER     = "segura"
DB_PASSWORD = os.environ.get('DB_PASSWORD', '')
DB_NAME     = "SCGCPR"

COLUMNAS = [
    ("Provincia",          "NVARCHAR(120) NULL"),
    ("Municipio",          "NVARCHAR(120) NULL"),
    ("EstadoConciliacion", "NVARCHAR(30)  NULL"),
]

def columna_existe(cur, tabla_schema, tabla_nombre, columna):
    cur.execute(
        "SELECT COUNT(*) FROM INFORMATION_SCHEMA.COLUMNS "
        "WHERE TABLE_SCHEMA=%s AND TABLE_NAME=%s AND COLUMN_NAME=%s",
        (tabla_schema, tabla_nombre, columna),
    )
    return cur.fetchone()[0] > 0

def main():
    print(f"Conectando a {DB_SERVER}:{DB_PORT}/{DB_NAME} ...")
    try:
        conn = pymssql.connect(DB_SERVER, DB_USER, DB_PASSWORD, DB_NAME, port=DB_PORT)
    except Exception as e:
        print(f"ERROR de conexión: {e}")
        sys.exit(1)

    cur = conn.cursor()
    cambios = 0

    for col, tipo in COLUMNAS:
        if columna_existe(cur, "cat", "FactMedicoCategoriaSnapshot", col):
            print(f"  ✓  {col} ya existe — omitiendo")
        else:
            sql = f"ALTER TABLE [cat].[FactMedicoCategoriaSnapshot] ADD [{col}] {tipo}"
            print(f"  +  Agregando {col} ...")
            cur.execute(sql)
            conn.commit()
            print(f"     OK")
            cambios += 1

    conn.close()

    if cambios == 0:
        print("\nNo se realizaron cambios (todas las columnas ya existían).")
    else:
        print(f"\n{cambios} columna(s) agregada(s) correctamente.")
        print("Reinicia uvicorn para que los cambios surtan efecto.")

if __name__ == "__main__":
    main()
