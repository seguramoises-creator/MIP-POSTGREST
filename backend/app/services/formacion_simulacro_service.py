"""Simulacro de Venta con IA (§9).

El RM practica contra un médico simulado por IA (estilo social asignado). Por
fase MORE (Apertura/Desarrollo/Cierre) una objeción hablada y respuesta de opción
múltiple, calificada D/P/A/E como Coaching MORE. El escenario lo genera la capa de
IA de la Fase 0 (una sola llamada de texto); aquí no se inventa teoría MORE.
"""
import random

from loguru import logger
from sqlalchemy.orm import Session

from app.services.examen_ia_service import _extraer_json

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


def construir_prompt(estilo: str, medico: str, genero: str | None) -> str:
    gen = {"F": "femenino", "M": "masculino"}.get(genero or "", "no especificado")
    return (
        "Eres un generador de simulacros de venta farmacéutica para entrenar a un "
        "Representante Médico con el modelo MORE.\n"
        f"El médico simulado es {medico} (género {gen}) y su estilo social es "
        f"{estilo}. Genera un escenario con EXACTAMENTE una ronda por cada fase: "
        "Apertura, Desarrollo y Cierre.\n"
        "En cada ronda el médico plantea una OBJECIÓN realista acorde a su estilo, "
        "y ofreces de 3 a 4 opciones de respuesta para el representante, UNA sola "
        "correcta según MORE, con una retroalimentación breve del porqué.\n"
        "La ronda de Desarrollo DEBE nombrar la técnica de manejo de objeciones "
        "empleada (campo tecnica_objecion).\n"
        "Responde SOLO con JSON válido, sin texto adicional, con esta forma:\n"
        '{"rondas":[{"fase_more":"Apertura","objecion_texto":"...",'
        '"opciones":{"A":"...","B":"...","C":"..."},"opcion_correcta":"B",'
        '"retroalimentacion":"..."},'
        '{"fase_more":"Desarrollo","tecnica_objecion":"...","objecion_texto":"...",'
        '"opciones":{"A":"...","B":"..."},"opcion_correcta":"A","retroalimentacion":"..."},'
        '{"fase_more":"Cierre","objecion_texto":"...","opciones":{"A":"...","B":"..."},'
        '"opcion_correcta":"A","retroalimentacion":"..."}]}'
    )


def parsear_escenario(texto: str) -> list[dict]:
    """Extrae y valida las rondas del JSON que devolvió la IA."""
    try:
        datos = _extraer_json(texto)
    except Exception as exc:  # noqa: BLE001 — cualquier fallo de parseo es IA inválida
        raise SimulacroIAError(f"La IA no devolvió JSON válido: {exc}") from exc
    rondas = datos.get("rondas") if isinstance(datos, dict) else datos
    if not isinstance(rondas, list) or not rondas:
        raise SimulacroIAError("El escenario no trae una lista de rondas.")
    for r in rondas:
        fase = r.get("fase_more")
        opciones = r.get("opciones")
        correcta = r.get("opcion_correcta")
        if fase not in FASES:
            raise SimulacroIAError(f"Fase inválida: {fase!r}.")
        if not isinstance(opciones, dict) or not opciones:
            raise SimulacroIAError("Una ronda no trae opciones.")
        if correcta not in opciones:
            raise SimulacroIAError("La opción correcta no está entre las opciones.")
        if not r.get("objecion_texto"):
            raise SimulacroIAError("Una ronda no trae objeción.")
        if fase == "Desarrollo" and not r.get("tecnica_objecion"):
            raise SimulacroIAError("La ronda de Desarrollo no nombra la técnica.")
    return rondas
