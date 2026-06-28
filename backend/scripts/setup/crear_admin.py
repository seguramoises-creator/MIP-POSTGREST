"""
crear_admin.py — Crea el usuario admin en la BD y reinicia el servicio MSM-Backend
"""
import os, sys, subprocess
from dotenv import load_dotenv
load_dotenv('.env')

import pymssql
from passlib.context import CryptContext

server   = os.getenv('DB_SERVER', '127.0.0.1')
port     = int(os.getenv('DB_PORT', 1433))
database = os.getenv('DB_NAME', 'SCGCPR')
user     = os.getenv('DB_USER', 'segura')
password = os.getenv('DB_PASSWORD', '')

# Generar hash de la contraseña
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
hashed  = pwd_ctx.hash("Admin1234!")

print("Conectando a la BD...")
conn = pymssql.connect(server=server, port=port, database=database,
                       user=user, password=password, as_dict=True)
cur = conn.cursor()

# Verificar si ya existe
cur.execute("SELECT COUNT(*) AS n FROM Security.DIM_Usuario WHERE username='admin'")
row = cur.fetchone()
if row['n'] > 0:
    # Actualizar contraseña
    cur.execute(
        "UPDATE Security.DIM_Usuario SET hashed_password=%s, activo=1, debe_cambiar_password=0 WHERE username='admin'",
        (hashed,)
    )
    conn.commit()
    print("  ✓ Usuario admin actualizado (contraseña restablecida)")
else:
    # Crear usuario
    cur.execute("""
        INSERT INTO Security.DIM_Usuario
            (username, email, hashed_password, nombre_completo, rol, activo, debe_cambiar_password, intentos_fallidos)
        VALUES
            ('admin', 'admin@sistemamip.com', %s, 'Administrador', 'ADMIN', 1, 0, 0)
    """, (hashed,))
    conn.commit()
    print("  ✓ Usuario admin creado")

cur.close()
conn.close()

print("\nReiniciando servicio MSM-Backend...")
r = subprocess.run(["net", "stop", "MSM-Backend"], capture_output=True, text=True)
print(" ", r.stdout.strip() or r.stderr.strip())
r = subprocess.run(["net", "start", "MSM-Backend"], capture_output=True, text=True)
print(" ", r.stdout.strip() or r.stderr.strip())

print("""
¡Listo!
  Usuario:    admin
  Contraseña: Admin1234!
  URL:        https://sistemamip.com
""")
