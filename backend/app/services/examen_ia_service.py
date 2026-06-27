"""SCGCPR — Servicio de generación de exámenes con IA (Claude)."""
from __future__ import annotations
import json
from loguru import logger


def validar_preguntas_generadas(data: list) -> list[dict]:
    if not isinstance(data, list) or not data:
        raise ValueError("La IA no devolvió una lista de preguntas")
    out = []
    for i, q in enumerate(data):
        if not isinstance(q, dict):
            raise ValueError(f"Pregunta {i}: formato inválido")
        tipo = q.get("tipo")
        if tipo not in ("multi", "caso"):
            raise ValueError(f"Pregunta {i}: tipo inválido {tipo!r}")
        if not (q.get("texto") or "").strip():
            raise ValueError(f"Pregunta {i}: texto vacío")
        ops = q.get("opciones")
        if not isinstance(ops, list) or len(ops) != 4 or not all(isinstance(o, str) and o.strip() for o in ops):
            raise ValueError(f"Pregunta {i}: debe tener exactamente 4 opciones no vacías")
        correcta = q.get("correcta")
        if not isinstance(correcta, int) or isinstance(correcta, bool) or not (0 <= correcta <= 3):
            raise ValueError(f"Pregunta {i}: 'correcta' debe ser 0..3")
        if tipo == "caso" and not (q.get("escenario") or "").strip():
            raise ValueError(f"Pregunta {i}: caso clínico requiere 'escenario'")
        out.append({
            "tipo": tipo, "texto": q["texto"].strip(),
            "escenario": (q.get("escenario") or None),
            "opciones": [o.strip() for o in ops], "correcta": correcta,
            "explicacion": (q.get("explicacion") or "").strip()})
    return out
