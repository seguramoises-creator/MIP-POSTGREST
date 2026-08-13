"""
crear_admin_pg.py — Siembra el usuario admin (PostgreSQL).

Usa SQLAlchemy/ORM (no depende de servicios del SO). Pensado para correr
dentro del contenedor:

    docker compose exec backend python scripts/setup/crear_admin_pg.py

Crea (o restablece) el usuario:  admin  /  Admin1234!  (rol ADMIN).
Cambia la contraseña tras el primer login.
"""
import os
import sys
from datetime import datetime, timezone
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

"""Contraseña inicial.

Se puede fijar con la variable de entorno `ADMIN_PASSWORD`, y conviene hacerlo:
el repositorio es público, así que el valor por defecto lo conoce cualquiera.

    ADMIN_PASSWORD='...' python scripts/setup/crear_admin_pg.py
"""
PASSWORD = os.environ.get("ADMIN_PASSWORD") or "Admin1234!"


def main() -> None:
    hashed = CryptContext(schemes=["bcrypt"], deprecated="auto").hash(PASSWORD)
    ahora = datetime.now(timezone.utc)
    db = SessionLocal()
    try:
        u = db.execute(select(Usuario).where(Usuario.username == "admin")).scalar_one_or_none()
        if u:
            u.hashed_password = hashed
            u.activo = True
            # La fija un operador, no su dueño: el dueño debe cambiarla al entrar.
            u.debe_cambiar_password = True
            if u.activado_en is None:
                u.activado_en = ahora
            print("  ✓ Usuario admin actualizado (contraseña restablecida)")
        else:
            db.add(Usuario(
                username="admin",
                email="admin@vista-mip.com",
                hashed_password=hashed,
                nombre_completo="Administrador",
                rol=Rol.ADMIN,
                activo=True,
                debe_cambiar_password=True,
                # SIN ESTO NADIE PUEDE ENTRAR A UNA INSTALACIÓN NUEVA. El login
                # corta con 403 cuando `activado_en` es NULL (auth.py) y manda a
                # abrir el enlace de activación — que para este usuario no existe,
                # porque lo crea un script y no una invitación. La migración 0023
                # rellena el campo, pero solo a los usuarios que YA existían: en una
                # instalación desde cero las migraciones corren sobre una base vacía
                # y no hay nada que rellenar. Aquí el operador ya conoce la clave,
                # así que la cuenta nace activada; lo que se le exige es cambiarla.
                activado_en=ahora,
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
