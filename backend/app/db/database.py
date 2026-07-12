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
    connect_args={"connect_timeout": 30},  # psycopg2
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
