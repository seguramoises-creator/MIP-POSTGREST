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
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

# Registrar los modelos para que los mappers resuelvan las FKs.
import app.models.usuario  # noqa: F401
import app.models.dimensiones  # noqa: F401
import app.models.hechos  # noqa: F401
import app.models.visita  # noqa: F401
import app.models.exam_models  # noqa: F401
import app.models.cat_models  # noqa: F401

from sqlalchemy import select, func

from app.db.database import SessionLocal
from app.core.security import hash_password
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import Gerente, RepresentanteMedico

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
    # Coordinador Mercadeo Internacional (7º rol de la gerencia de Mallén): "acceso total,
    # países Guatemala y Honduras". Lleva rol GERENTE_MARKETING a propósito — su diferencia
    # con la Gerencia de Mercadeo NO es de rol sino de PAÍS, y el país es ortogonal a la
    # matriz (vive en Security.FACT_UsuarioPais, no en una celda). Acotarlo es asignarle
    # {GT, HN}; sin filas vería todos los países, como cualquier otro.
    ("qa_coordinador",  Rol.GERENTE_MARKETING,      "QA Coordinador Mercadeo Internacional"),
]


def main() -> None:
    hashed = hash_password(PASSWORD)
    ahora = datetime.now(timezone.utc)
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
                # Las cuentas creadas antes de la migración 0023 quedaron con fecha por el
                # backfill; una creada por este script después, no. Sin esto, re-ejecutarlo
                # no repara una cuenta que no puede entrar.
                if u.activado_en is None:
                    u.activado_en = ahora
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
                    # SIN esto la cuenta nace con `activado_en` NULL y auth.py corta el login
                    # con 403 ANTES de verificar la contraseña: la cuenta existe, la clave es
                    # correcta y aun así no se puede entrar. Mismo defecto que se corrigió en
                    # crear_admin_pg.py (e6315ca) y que aquí seguía vivo. Estas cuentas no se
                    # activan por enlace: el script ya les fija la clave.
                    activado_en=ahora,
                ))
                creados += 1
                print(f"  [OK] {username:16} creado       ({rol.value})")

        db.flush()
        # Vincular qa_gerprod a un distrito real con RMs para poder probar el alcance de EQUIPO
        # (sus celdas de coaching/exámenes son "equipo"). Se resuelve al gerente con más RMs
        # (INNER JOIN → solo gerentes con equipo; los MARCA quedan fuera). Agnóstico de IDs.
        # qa_producto (GERENTE_MARCA) NO se vincula: no tiene celdas de alcance "equipo".
        gd = (db.query(Gerente.id, func.count(RepresentanteMedico.id).label("n"))
                .join(RepresentanteMedico, RepresentanteMedico.gerente_id == Gerente.id)
                .group_by(Gerente.id)
                .order_by(func.count(RepresentanteMedico.id).desc()).first())
        u = db.execute(select(Usuario).where(Usuario.username == "qa_gerprod")).scalar_one_or_none()
        if u and gd:
            u.gerente_id = gd.id
            print(f"  [OK] qa_gerprod       vinculado a gerente id={gd.id} ({gd.n} RMs) — prueba de equipo")
        elif u:
            print("  [!]  qa_gerprod       sin gerente con RMs para vincular (no se probará equipo)")

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
