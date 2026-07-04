"""
SCGCPR — Configuración SQLAlchemy + PostgreSQL (edición PostgreSQL)
"""
from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker, Session
from sqlalchemy.pool import QueuePool
from typing import Generator
from loguru import logger

from app.core.config import settings


# El timeout de conexión difiere por dialecto: pymssql usa 'timeout', psycopg2 'connect_timeout'.
_connect_args = {"connect_timeout": 30} if settings.DB_ENGINE == "postgres" else {"timeout": 30}

engine = create_engine(
    settings.DATABASE_URL,
    poolclass=QueuePool,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
    pool_recycle=1800,
    echo=settings.DEBUG,
    connect_args=_connect_args,
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
        logger.info("Conexión a SQL Server: OK")
        return True
    except Exception as e:
        logger.error(f"Error de conexión a SQL Server: {e}")
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
