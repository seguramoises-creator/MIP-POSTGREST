"""
crear_admin_pg.py — Siembra el usuario admin (edición PostgreSQL).

A diferencia de crear_admin.py (SQL Server / pymssql + reinicio del servicio
Windows MSM-Backend), este script es portable: usa SQLAlchemy/ORM y no depende
del dialecto ni de servicios del SO. Pensado para correr dentro del contenedor:

    docker compose exec backend python scripts/setup/crear_admin_pg.py

Crea (o restablece) el usuario:  admin  /  Admin1234!  (rol ADMIN).
Cambia la contraseña tras el primer login.
"""
import sys
from pathlib import Path

# Permite ejecutar el script desde cualquier CWD (añade la raíz del backend al path).
sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Registrar todos los modelos para que los mappers resuelvan las FKs entre tablas.
import app.models.usuario  # noqa: F401
import app.models.dimensiones  # noqa: F401
import app.models.hechos  # noqa: F401
import app.models.visita  # noqa: F401
import app.models.exam_models  # noqa: F401
import app.models.cat_models  # noqa: F401

from passlib.context import CryptContext
from sqlalchemy import select

from app.db.database import SessionLocal
from app.models.usuario import Usuario, Rol

PASSWORD = "Admin1234!"


def main() -> None:
    hashed = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(PASSWORD)
    db = SessionLocal()
    try:
        u = db.execute(select(Usuario).where(Usuario.username == "admin")).scalar_one_or_none()
        if u:
            u.hashed_password = hashed
            u.activo = True
            u.debe_cambiar_password = False
            print("  ✓ Usuario admin actualizado (contraseña restablecida)")
        else:
            db.add(Usuario(
                username="admin",
                email="admin@vista-mip.com",
                hashed_password=hashed,
                nombre_completo="Administrador",
                rol=Rol.ADMIN,
                activo=True,
                debe_cambiar_password=False,
                intentos_fallidos=0,
            ))
            print("  ✓ Usuario admin creado")
        db.commit()
    finally:
        db.close()

    print(f"""
¡Listo!
  Usuario:    admin
  Contraseña: {PASSWORD}
  (Cambia la contraseña tras el primer login.)
""")


if __name__ == "__main__":
    main()
