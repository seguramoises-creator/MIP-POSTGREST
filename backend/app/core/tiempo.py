"""Utilidades de fecha/hora por país.

El sistema persiste SIEMPRE en UTC (`datetime.now(timezone.utc)`), pero el "día
operativo" del negocio es el día LOCAL del país. La diferencia importa: RD es UTC−4,
así que el día UTC va de las 8:00 p.m. a las 8:00 p.m. hora local. Un GD que hace
campo hasta las 5 p.m. y llena su hoja de coaching a las 8:30 p.m. sigue estando en
su mismo día laboral, aunque para el servidor ya sea mañana.

La zona horaria se lee de `Config.DIM_Pais.zona_horaria` (ej. "America/Santo_Domingo").
Sin configurar → UTC, que es el comportamiento histórico.
"""
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Pais

UTC = ZoneInfo("UTC")


def zona_horaria(db: Session, pais_codigo: str | None) -> ZoneInfo:
    """Zona horaria configurada del país; UTC si no está configurada o es inválida."""
    nombre = ""
    if pais_codigo:
        nombre = (db.query(Pais.zona_horaria)
                  .filter(Pais.codigo == pais_codigo).scalar() or "").strip()
    if not nombre:
        return UTC
    try:
        return ZoneInfo(nombre)
    except (ZoneInfoNotFoundError, ValueError):
        logger.warning(f"Zona horaria inválida '{nombre}' en DIM_Pais ({pais_codigo}); se usa UTC.")
        return UTC


def hoy_local(db: Session, pais_codigo: str | None) -> date:
    """Fecha de HOY en el país (no en UTC)."""
    return datetime.now(zona_horaria(db, pais_codigo)).date()


def ventana_dia_local(db: Session, pais_codigo: str | None,
                      dia: date | None = None) -> tuple[date, datetime, datetime]:
    """(día local, inicio, fin) del día local del país.

    `inicio`/`fin` vienen en UTC **naive**, listos para comparar contra las columnas
    `DateTime` que guardan UTC (ej. `Visita.FactVisita.fecha_hora`). Se devuelve un
    rango semiabierto [inicio, fin) en vez de `func.date(col) == dia` porque el rango
    sí puede usar el índice de la columna.
    """
    tz = zona_horaria(db, pais_codigo)
    d = dia or datetime.now(tz).date()
    inicio = datetime.combine(d, time.min, tzinfo=tz).astimezone(UTC).replace(tzinfo=None)
    fin = datetime.combine(d + timedelta(days=1), time.min, tzinfo=tz).astimezone(UTC).replace(tzinfo=None)
    return d, inicio, fin
