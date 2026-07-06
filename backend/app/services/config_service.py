"""SCGCPR — Parámetros de sistema clave-valor (runtime, sin reiniciar).

Lee/escribe en Config.DIM_Parametro. Útil para flags que el admin alterna en vivo,
como EXAMEN_IA_DEMO (generación de exámenes en modo DEMO vs IA real de Claude).
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.dimensiones import ParametroSistema

_VERDADERO = {"1", "true", "yes", "si", "sí", "on"}


def obtener(db: Session, clave: str) -> str | None:
    fila = db.query(ParametroSistema).filter(ParametroSistema.clave == clave).first()
    return fila.valor if fila else None


def obtener_bool(db: Session, clave: str, por_defecto: bool) -> bool:
    val = obtener(db, clave)
    if val is None:
        return por_defecto
    return val.strip().lower() in _VERDADERO


def obtener_int(db: Session, clave: str, por_defecto: int) -> int:
    val = obtener(db, clave)
    if val is None:
        return por_defecto
    try:
        return int(str(val).strip())
    except (ValueError, TypeError):
        return por_defecto


def fijar(db: Session, clave: str, valor: str) -> None:
    fila = db.query(ParametroSistema).filter(ParametroSistema.clave == clave).first()
    if fila is None:
        fila = ParametroSistema(clave=clave, valor=valor)
        db.add(fila)
    else:
        fila.valor = valor
    fila.actualizado = datetime.now(timezone.utc)
    db.commit()
