"""
SCGCPR — Configuración SQLAlchemy + PostgreSQL (edición PostgreSQL)
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from typing import Generator
from loguru import logger

from app.core.config import settings


engine = create_engine(
    settings.DATABASE_URL,
    connect_args={
        "connect_timeout": 30,  # psycopg2
        # ── Toda conexión habla UTC. NO es cosmético. ────────────────────────
        # Las columnas de fecha son `TIMESTAMP WITHOUT TIME ZONE` y el código
        # guarda `datetime.now(timezone.utc)`, que es un valor CONSCIENTE. Al
        # entrar en una columna sin zona, PostgreSQL lo convierte a la zona de
        # la SESIÓN y descarta el huso — así que lo que queda almacenado no lo
        # decide el código, lo decide la configuración de la máquina.
        #
        # Medido el 2026-09-09: en el portátil (sesión `America/La_Paz`) una
        # visita capturada a las 23:49 hora local quedó guardada como
        # `23:49`, es decir hora LOCAL; en producción (sesión `Etc/UTC`) el
        # mismo código guarda UTC. Dos instalaciones, dos significados para la
        # misma columna, y nada que lo delate: la fila siempre se ve razonable.
        #
        # Con `timezone=UTC` la conversión es la identidad y lo que dice el
        # código —UTC— es de verdad lo que queda escrito. El "día del
        # visitador" se resuelve aparte, en `app/core/tiempo.py`, que para eso
        # lee la zona de su país.
        "options": "-c timezone=UTC",
    },
    poolclass=QueuePool,
    pool_size=settings.DB_POOL_SIZE,
    max_overflow=settings.DB_MAX_OVERFLOW,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=settings.DB_ECHO,
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


def get_db() -> Generator[Session, None, None]:
    db = SessionLocal()
    try:
        yield db
    except Exception as e:
        logger.error(f"Error en sesión de BD: {e}")
        db.rollback()
        raise
    finally:
        db.close()


def check_db_connection() -> bool:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        logger.info("Conexión a PostgreSQL: OK")
        return True
    except Exception as e:
        logger.error(f"Error de conexión a PostgreSQL: {e}")
        return False


def init_db() -> None:
    """Registra los modelos e intenta crear tablas (solo para desarrollo)."""
    # Importar los módulos correctos — dimensiones.py y hechos.py
    from app.models import usuario, dimensiones, hechos  # noqa: F401
    try:
        Base.metadata.create_all(bind=engine)
        logger.info("Base de datos inicializada.")
    except Exception as e:
        logger.warning(f"init_db: {e} — las tablas pueden ya existir con esquemas.")
