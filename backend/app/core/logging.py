"""
SCGCPR — Configuración de Logging con Loguru
"""
import sys
from loguru import logger
from app.core.config import settings


def setup_logging() -> None:
    logger.remove()  # quitar handler por defecto

    fmt = (
        "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
        "<level>{level: <8}</level> | "
        "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> | "
        "<level>{message}</level>"
    )

    # Consola
    logger.add(sys.stdout, format=fmt, level=settings.LOG_LEVEL, colorize=True)

    # Archivo rotativo
    logger.add(
        settings.LOG_FILE,
        format=fmt,
        level=settings.LOG_LEVEL,
        rotation="10 MB",
        retention="30 days",
        compression="zip",
        enqueue=True,
    )

    logger.info(f"Logging configurado — nivel: {settings.LOG_LEVEL}")
