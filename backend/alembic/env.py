import sys
from pathlib import Path
from logging.config import fileConfig

from sqlalchemy import engine_from_config
from sqlalchemy import pool

from alembic import context

# Permite importar el paquete `app` cuando Alembic se ejecuta desde backend/
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# this is the Alembic Config object, which provides
# access to the values within the .ini file in use.
config = context.config

# Interpret the config file for Python logging.
# This line sets up loggers basically.
if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# --- Conexion: tomamos la URL real de la app (settings), no del .ini ---
from app.core.config import settings  # noqa: E402

config.set_main_option("sqlalchemy.url", settings.DATABASE_URL)

# --- Metadata de los modelos: se importan TODOS para que autogenerate los vea ---
from app.db.database import Base  # noqa: E402
from app.models import usuario, dimensiones, hechos  # noqa: F401,E402
from app.models import cat_models  # noqa: F401,E402  ← cat.* / stg.* (Categorización Médica jun-2026)
from app.models import exam_models  # noqa: F401,E402  ← esquema exam (Módulo de Exámenes)
from app.models import visita  # noqa: F401,E402  ← esquema Visita (Módulo de Visita Médica)
from app.models import coaching_more_models  # noqa: F401,E402  ← esquema coaching (Coaching MORE)
from app.models import seguridad_rbac  # noqa: F401,E402  ← RBAC Fase 1 (DIM_Recurso/FACT_RolPermiso/AuditoriaSeguridad)
from app.models import integracion_ext  # noqa: F401,E402  ← esquema ext (integracion Laboratorio Mallen)
from app.models import formacion  # noqa: F401,E402  ← esquema formacion (Ampliacion Modulo de Formacion)
from app.models import ia_conexion  # noqa: F401,E402  ← Security.DIM_IAConexion (proveedores de IA, seccion 20)
from app.models import integracion_hallazgo  # noqa: F401,E402  ← Audit.IntegracionHallazgo (traza de validacion de lotes de Mallen)
from app.models import mapeo_externo  # noqa: F401,E402  ← Config.MapeoExterno (equivalencias codigos Mallen <-> ids VISTA)
from app.models import alcance  # noqa: F401,E402  ← paises del usuario y lineas del gerente

target_metadata = Base.metadata


def include_object(object, name, type_, reflected, compare_to):
    """Ignora objetos fuera de los esquemas de la app (p.ej. del sistema)."""
    if type_ == "table" and object.schema not in (
        "Config", "Security", "DW", "Audit", "ETL", "exam", "ext", "formacion", "dbo", None
    ):
        return False
    return True

# other values from the config, defined by the needs of env.py,
# can be acquired:
# my_important_option = config.get_main_option("my_important_option")
# ... etc.


def run_migrations_offline() -> None:
    """Run migrations in 'offline' mode."""
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        include_object=include_object,
        include_schemas=True,
        compare_type=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Run migrations in 'online' mode."""
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            include_object=include_object,
            include_schemas=True,
            compare_type=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
