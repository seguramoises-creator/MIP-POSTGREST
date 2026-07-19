"""
crear_usuarios_prueba.py — Crea un usuario QA por cada rol (idempotente).

Pensado para validar la matriz de Roles y Permisos: deja una cuenta lista por cada rol
que hoy no tiene usuario. Namespaced `qa_*` para no confundirse con cuentas reales.

    docker compose exec backend python scripts/setup/crear_usuarios_prueba.py

Re-ejecutable: si el usuario ya existe, le restablece el rol, la contraseña y lo activa.
Todos comparten la misma contraseña de prueba (abajo). NO son cuentas de producción:
bórralas cuando termines de validar.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Registrar los modelos para que los mappers resuelvan las FKs.
import app.models.usuario  # noqa: F401
import app.models.dimensiones  # noqa: F401
import app.models.hechos  # noqa: F401
import app.models.visita  # noqa: F401
import app.models.exam_models  # noqa: F401
import app.models.cat_models  # noqa: F401

from sqlalchemy import select

from app.db.database import SessionLocal
from app.core.security import hash_password
from app.models.usuario import Usuario, Rol

PASSWORD = "PruebaVista2026!"

# username -> (rol, nombre visible). Solo roles que hoy no tienen cuenta;
# puedes agregar/quitar filas sin problema (el script es idempotente).
USUARIOS = [
    ("qa_presidencia",  Rol.PRESIDENCIA,           "QA Dirección General"),
    ("qa_dircomercial", Rol.DIR_COMERCIAL,          "QA Director Comercial"),
    ("qa_gerprod",      Rol.GERENTE_PRODUCTIVIDAD,  "QA Capacitación y Productividad"),
    ("qa_marketing",    Rol.GERENTE_MARKETING,      "QA Gerente de Marketing"),
    ("qa_germedico",    Rol.GERENTE_MEDICO,         "QA Gerente Médico"),
    ("qa_analista",     Rol.ANALISTA_DATOS,         "QA Analista de Datos"),
    ("qa_finanzas",     Rol.FINANZAS,               "QA Finanzas"),
    ("qa_producto",     Rol.GERENTE_MARCA,          "QA Gerente de Producto"),
]


def main() -> None:
    hashed = hash_password(PASSWORD)
    db = SessionLocal()
    creados, actualizados = 0, 0
    try:
        for username, rol, nombre in USUARIOS:
            u = db.execute(select(Usuario).where(Usuario.username == username)).scalar_one_or_none()
            if u:
                u.rol = rol
                u.hashed_password = hashed
                u.activo = True
                u.debe_cambiar_password = False
                u.bloqueado_hasta = None
                u.intentos_fallidos = 0
                actualizados += 1
                print(f"  [OK] {username:16} actualizado  ({rol.value})")
            else:
                db.add(Usuario(
                    username=username,
                    email=f"{username}@vista-mip.com",
                    hashed_password=hashed,
                    nombre_completo=nombre,
                    rol=rol,
                    activo=True,
                    debe_cambiar_password=False,
                    intentos_fallidos=0,
                ))
                creados += 1
                print(f"  [OK] {username:16} creado       ({rol.value})")
        db.commit()
    finally:
        db.close()

    print(f"""
¡Listo!  creados={creados}  actualizados={actualizados}
  Contraseña de todas las cuentas QA: {PASSWORD}
  (Cuentas de prueba — bórralas al terminar la validación.)
""")


if __name__ == "__main__":
    main()
