"""SCGCPR — Servicio de generación de exámenes con IA (Claude)."""
from __future__ import annotations
import json
from loguru import logger


def extraer_texto_fuente(ruta: str, tipo_archivo: str) -> str:
    """Extrae texto de un archivo según su tipo (pdf|docx|pptx|texto)."""
    tipo = (tipo_archivo or "").lower()
    if tipo == "pdf":
        import pdfplumber
        with pdfplumber.open(ruta) as pdf:
            return "\n".join((page.extract_text() or "") for page in pdf.pages)
    if tipo == "docx":
        import docx
        d = docx.Document(ruta)
        return "\n".join(p.text for p in d.paragraphs)
    if tipo == "pptx":
        import pptx
        prs = pptx.Presentation(ruta)
        partes = []
        for slide in prs.slides:
            for shape in slide.shapes:
                if shape.has_text_frame:
                    partes.append(shape.text_frame.text)
        return "\n".join(partes)
    if tipo == "texto":
        with open(ruta, "r", encoding="utf-8", errors="ignore") as f:
            return f.read()
    raise ValueError(f"Tipo de archivo no soportado: {tipo_archivo}")


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
