"""SCGCPR — Servicio de generación de exámenes con IA (Claude)."""
from __future__ import annotations
import json
from loguru import logger
from app.core.config import settings

# ---------------------------------------------------------------------------
# NOTE ON n_multi / n_casos PERSISTENCE
# ---------------------------------------------------------------------------
# FuenteIA has no dedicated columns for n_multi / n_casos / texto_pegado.
# Rather than add a migration, we serialize those values as JSON into the
# `prompt_usado` field when the endpoint creates the FuenteIA row:
#   prompt_usado = json.dumps({"n_multi": n, "n_casos": m, "texto_pegado": t})
# procesar_generacion_ia reads and parses that JSON to recover the values.
# If `ruta_archivo` is present, text is extracted from disk; otherwise
# `texto_pegado` from the JSON is used directly.
# ---------------------------------------------------------------------------


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


def construir_prompt(texto: str, n_multi: int, n_casos: int) -> str:
    """Construye el prompt base para la generación de preguntas con Claude.

    El texto de entrada se trunca a _TEXTO_MAX_CHARS para acotar el tamaño del
    prompt y el costo de tokens, independientemente del tamaño del archivo fuente.
    """
    texto_acotado = texto[:_TEXTO_MAX_CHARS]
    total = n_multi + n_casos
    return (
        "Eres un experto en capacitación farmacéutica. Analiza el siguiente documento "
        f"y genera exactamente {total} preguntas de evaluación:\n"
        f"- {n_multi} de opción múltiple\n- {n_casos} casos clínicos\n\n"
        "Devuelve SOLO un arreglo JSON. Cada pregunta con este esquema:\n"
        "tipo: 'multi'|'caso'; escenario: string (solo caso); texto: string; "
        "opciones: [string,string,string,string] (exactamente 4); correcta: 0|1|2|3; "
        "explicacion: string.\n\nDOCUMENTO:\n" + texto_acotado)


# Maximum characters fed into the prompt to bound token cost.
_TEXTO_MAX_CHARS = 40_000


def _extraer_json(texto_respuesta: str):
    """Extrae y parsea JSON de la respuesta del modelo.

    Estrategia en orden de precedencia:
    1. Si hay un bloque ```json ... ``` o ``` ... ```, usa su contenido.
    2. De lo contrario busca el primer '[' o '{' y el último ']' o '}'
       correspondiente y parsea ese fragmento (tolerante a texto extra
       antes/después del JSON).
    3. Intenta parsear el texto completo como JSON.
    4. Lanza ValueError si todo falla.
    """
    t = texto_respuesta.strip()

    # Strategy 1: fenced code block
    if "```" in t:
        import re
        # Match ```json ... ``` or ``` ... ```
        m = re.search(r"```(?:json)?\s*([\s\S]*?)```", t)
        if m:
            candidate = m.group(1).strip()
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass  # fall through to other strategies

    # Strategy 2: first balanced JSON array or object
    for open_ch, close_ch in (("[", "]"), ("{", "}")):
        start = t.find(open_ch)
        end = t.rfind(close_ch)
        if start != -1 and end != -1 and end > start:
            candidate = t[start:end + 1]
            try:
                return json.loads(candidate)
            except json.JSONDecodeError:
                pass

    # Strategy 3: full text
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"La IA no devolvió JSON válido: {e}")


def _generar_demo(texto: str, n_multi: int, n_casos: int) -> list[dict]:
    """Genera preguntas localmente (MODO DEMO), sin llamar a Claude ni gastar API.

    Las preguntas referencian frases reales del documento subido y se marcan con
    el prefijo [DEMO] para que en la revisión sea obvio que no son salida de IA real.
    Pasan por validar_preguntas_generadas para garantizar el mismo esquema.
    """
    import re
    frases = [s.strip() for s in re.split(r"[.\n]", texto) if len(s.strip()) >= 25]
    if not frases:
        frases = ["el contenido del documento proporcionado"]
    preguntas: list[dict] = []
    for i in range(max(0, n_multi)):
        frase = frases[i % len(frases)][:160]
        preguntas.append({
            "tipo": "multi",
            "texto": f'[DEMO] Según el documento, ¿qué afirmación es correcta? (ref.: "{frase}")',
            "opciones": [
                frase,
                "Ninguna de las anteriores se menciona en el documento.",
                "El documento no aborda este tema.",
                "Es lo contrario de lo que indica el documento.",
            ],
            "correcta": 0,
            "explicacion": "Pregunta generada en MODO DEMO (sin IA real); la opción correcta proviene del texto del documento.",
        })
    for i in range(max(0, n_casos)):
        frase = frases[(n_multi + i) % len(frases)][:160]
        preguntas.append({
            "tipo": "caso",
            "escenario": f'[DEMO] Un representante médico consulta el material sobre: "{frase}".',
            "texto": "¿Cuál es la acción recomendada según el documento?",
            "opciones": [
                "Aplicar lo descrito en el documento.",
                "Ignorar la información del documento.",
                "Contradecir las indicaciones del documento.",
                "Posponer indefinidamente la decisión.",
            ],
            "correcta": 0,
            "explicacion": "Caso generado en MODO DEMO (sin IA real).",
        })
    return validar_preguntas_generadas(preguntas)


def generar_preguntas_ia(texto: str, n_multi: int, n_casos: int,
                         client=None, model: str | None = None) -> list[dict]:
    """Genera preguntas llamando a Claude. El cliente se inyecta para testing.

    Si EXAMEN_IA_DEMO está activo y no se inyectó cliente, usa el generador local
    (sin consumir API) — permite probar el flujo completo sin créditos.
    """
    if client is None and settings.EXAMEN_IA_DEMO:
        logger.info("generar_preguntas_ia: MODO DEMO activo — generación local sin Claude")
        return _generar_demo(texto, n_multi, n_casos)
    if client is None:
        import anthropic
        client = anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)
    model = model or settings.EXAM_AI_MODEL
    prompt = construir_prompt(texto, n_multi, n_casos)
    respuesta = client.messages.create(
        model=model, max_tokens=4096,
        messages=[{"role": "user", "content": prompt}])
    texto_resp = "".join(getattr(b, "text", "") for b in respuesta.content)
    data = _extraer_json(texto_resp)
    return validar_preguntas_generadas(data)


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


# ---------------------------------------------------------------------------
# Persistence
# ---------------------------------------------------------------------------

def persistir_preguntas(db, examen_id: int, preguntas: list[dict]) -> int:
    """Inserta preguntas (con 4 opciones cada una) en el examen borrador.

    `indice_original` es 0..3 tal como las devolvió la IA.
    `es_correcta` se marca solo en la opción cuyo índice coincide con `correcta`.
    Retorna la cantidad de preguntas insertadas.
    """
    from app.models.exam_models import Pregunta, PreguntaOpcion

    base = db.query(Pregunta).filter(Pregunta.examen_id == examen_id).count()
    for offset, q in enumerate(preguntas):
        pregunta = Pregunta(
            examen_id=examen_id,
            tipo=q["tipo"],
            escenario=q.get("escenario"),
            texto=q["texto"],
            explicacion=q.get("explicacion"),
            orden=base + offset,
        )
        for idx, texto_op in enumerate(q["opciones"]):
            pregunta.opciones.append(
                PreguntaOpcion(
                    texto_opcion=texto_op,
                    indice_original=idx,
                    es_correcta=(idx == q["correcta"]),
                )
            )
        db.add(pregunta)
    db.commit()
    return len(preguntas)


# ---------------------------------------------------------------------------
# Background job
# ---------------------------------------------------------------------------

def procesar_generacion_ia(fuente_id: int) -> None:
    """Job en background: extrae texto, genera preguntas con IA y las persiste.

    Los parámetros n_multi / n_casos / texto_pegado se leen del JSON almacenado
    en FuenteIA.prompt_usado (no existe columna propia para ellos — decisión de
    diseño documentada en el módulo para evitar una migración adicional).
    """
    from app.db.database import SessionLocal
    from app.models.exam_models import FuenteIA

    db = SessionLocal()
    try:
        fuente = db.query(FuenteIA).filter(FuenteIA.id == fuente_id).first()
        if fuente is None:
            logger.warning(f"procesar_generacion_ia: FuenteIA id={fuente_id} no encontrada")
            return

        fuente.estado_generacion = "procesando"
        db.commit()

        try:
            # Recover parameters stored as JSON in prompt_usado
            params: dict = {}
            if fuente.prompt_usado:
                try:
                    params = json.loads(fuente.prompt_usado)
                except (json.JSONDecodeError, TypeError):
                    params = {}

            n_multi: int = int(params.get("n_multi", 5))
            n_casos: int = int(params.get("n_casos", 0))
            texto_pegado: str | None = params.get("texto_pegado") or None

            # Extract text: from file on disk, or from the pasted text
            if fuente.ruta_archivo:
                texto = extraer_texto_fuente(fuente.ruta_archivo, fuente.tipo_archivo or "texto")
            elif texto_pegado:
                texto = texto_pegado
            else:
                raise ValueError("No hay fuente de texto: ni archivo ni texto_pegado")

            preguntas = generar_preguntas_ia(texto, n_multi, n_casos)
            persistir_preguntas(db, fuente.examen_id, preguntas)

            fuente.estado_generacion = "exitoso"
            fuente.mensaje_error = None

        except Exception as exc:
            fuente.estado_generacion = "error"
            fuente.mensaje_error = str(exc)[:1000]
            logger.error(f"procesar_generacion_ia fuente={fuente_id} falló: {exc}")

        db.commit()
    finally:
        db.close()
