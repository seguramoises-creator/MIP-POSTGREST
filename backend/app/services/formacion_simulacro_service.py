"""Simulacro de Venta con IA (§9).

El RM practica contra un médico simulado por IA (estilo social asignado). Por
fase MORE (Apertura/Desarrollo/Cierre) una objeción hablada y respuesta de opción
múltiple, calificada D/P/A/E como Coaching MORE. El escenario lo genera la capa de
IA de la Fase 0 (una sola llamada de texto); aquí no se inventa teoría MORE.
"""
import random

from loguru import logger
from sqlalchemy.orm import Session

ESTILOS: tuple[str, ...] = ("Directivo", "Analitico", "Amistoso", "Expresivo")
FASES: tuple[str, ...] = ("Apertura", "Desarrollo", "Cierre")

#: Médicos simulados (nombre, género) — breve, solo para variar la práctica.
_MEDICOS: list[tuple[str, str]] = [
    ("Dra. Reyes", "F"), ("Dr. Peralta", "M"), ("Dra. Fermín", "F"),
    ("Dr. Guzmán", "M"), ("Dra. Objío", "F"),
]


class SimulacroIAError(RuntimeError):
    """La IA no devolvió un escenario válido tras el reintento."""


class PermisoError(RuntimeError):
    """La sesión/ronda no pertenece al RM que intenta operarla."""


def escala(ratio: float) -> int:
    """Ratio de aciertos → escala D/P/A/E (1-4), como Coaching MORE."""
    if ratio >= 0.90:
        return 4
    if ratio >= 0.70:
        return 3
    if ratio >= 0.50:
        return 2
    return 1
