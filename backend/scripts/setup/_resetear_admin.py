# --- bootstrap: permite ejecutar este script desde backend/scripts/<bucket>/ ---
import sys, pathlib as _pl
sys.path.insert(0, str(_pl.Path(__file__).resolve().parents[2]))
# ---------------------------------------------------------------------------
"""
Script de un solo uso: resetea (o crea) el usuario 'admin' con contraseña
conocida, usando hash_password() de la app — garantiza compatibilidad con
la version de bcrypt/passlib instalada (evita el problema de hashes
generados con otra version, ver CLAUDE.md seccion 17).

Uso:
    cd C:\\Users\\Lenovo\\Proyecto\\MSM\\backend
    python _resetear_admin.py
"""
from datetime import datetime, timezone

from app.db.database import SessionLocal
from app.core.security import hash_password
from app.models.usuario import Usuario, Rol
# IMPORTANTE: importar dimensiones registra Config.DIM_Pais (y demas DIM_*)
# en el Base.metadata — sin esto, SQLAlchemy no puede resolver el FK
# Usuario.pais_id -> Config.DIM_Pais.id al hacer flush/commit (aunque sea NULL).
import app.models.dimensiones  # noqa: F401

NUEVA_PASSWORD = "Admin1234!"

db = SessionLocal()
try:
    user = db.query(Usuario).filter(Usuario.username == "admin").first()

    if user is None:
        print("No existe el usuario 'admin' — creando uno nuevo...")
        user = Usuario(
            username="admin",
            email="admin@scgcpr.local",
            hashed_password=hash_password(NUEVA_PASSWORD),
            nombre_completo="Administrador",
            rol=Rol.ADMIN,
            activo=True,
            debe_cambiar_password=True,
            intentos_fallidos=0,
            bloqueado_hasta=None,
        )
        db.add(user)
    else:
        print(f"Usuario 'admin' encontrado (id={user.id}). Reseteando contraseña, "
              f"intentos fallidos y bloqueo...")
        user.hashed_password = hash_password(NUEVA_PASSWORD)
        user.activo = True
        user.intentos_fallidos = 0
        user.bloqueado_hasta = None
        user.updated_at = datetime.now(timezone.utc)

    db.commit()
    print(f"Listo. Usuario: admin / Contraseña: {NUEVA_PASSWORD}")
    print("Verificando hash recien guardado contra la contraseña...")

    from app.core.security import verify_password
    db.refresh(user)
    ok = verify_password(NUEVA_PASSWORD, user.hashed_password)
    print(f"verify_password() -> {ok}  {'(coincide, login deberia funcionar)' if ok else '(¡NO coincide! revisar bcrypt/passlib)'}")
finally:
    db.close()
