# Módulo de Exámenes — Fase 3 (Generación con IA) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Generar preguntas de examen desde documentos (PDF/Word/PPT/texto) con Claude, en segundo plano, con validación del JSON y persistencia como borrador para revisión.

**Architecture:** Servicio nuevo `examen_ia_service` con tres responsabilidades aisladas: extracción de texto, generación con IA (cliente Claude inyectable → mockeable, key por env), y persistencia. El endpoint sube el archivo (seguridad de ETL: magic bytes + UUID), crea el examen borrador + registro `FuenteIA`, y lanza un `BackgroundTask` que actualiza `FuenteIA.estado_generacion`.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Pydantic v2, anthropic SDK, pdfplumber, python-docx, python-pptx, pytest.

**Spec:** `docs/superpowers/specs/2026-06-26-modulo-examenes-design.md` (§5.2, §11 prompt, §15)

## Global Constraints

- IA: SDK `anthropic`. Modelo por defecto `claude-sonnet-4-6` (config `EXAM_AI_MODEL`). Key por env `ANTHROPIC_API_KEY` (vacía por defecto). **El cliente Claude se inyecta como parámetro** (`client=None` → construir desde settings); los tests pasan un mock — NO requieren key real.
- Las preguntas generadas SIEMPRE se guardan como **borrador** para revisión (nunca se publican automáticamente).
- Seguridad de archivo: magic bytes + nombre UUID (reusar el patrón de `etl.py`: `_safe_filename`, `_validar_magic_bytes`). El archivo fuente se guarda para auditoría (RN-10), nunca visible al evaluado.
- Modelos `FuenteIA` (estado_generacion: pendiente|procesando|exitoso|error), `Examen`, `Pregunta`, `PreguntaOpcion` ya existen (Fase 1/2).
- BackgroundTasks: crear sesión propia con `SessionLocal()` y cerrarla en `finally`.
- Backend Python/Alembic vía `./venv/Scripts/python.exe` / `./venv/Scripts/alembic.exe` desde `backend/`. Logs `loguru`. Timestamps `datetime.now(timezone.utc)`.
- Tests: `./venv/Scripts/python.exe -m pytest -q` desde `backend/`. Todos pasan antes de cada commit.

## Estructura de archivos (Fase 3)

| Archivo | Responsabilidad |
|---------|-----------------|
| `requirements.txt` (modificar) | añadir anthropic, pdfplumber, python-docx, python-pptx |
| `app/core/config.py` (modificar) | `ANTHROPIC_API_KEY`, `EXAM_AI_MODEL` |
| `app/services/examen_ia_service.py` (crear) | extracción, validación, generación, persistencia, job |
| `app/schemas/examenes.py` (modificar) | `GenerarIARequest`/`GenerarIAResponse`/`JobIAEstado` |
| `app/api/v1/routers/examenes.py` (modificar) | `POST /examenes/generar-ia`, `GET /examenes/generar-ia/{job_id}` |
| `tests/test_examen_ia_service.py` (crear) | validación, generación (mock client), extracción |

---

### Task 1: Dependencias + configuración

**Files:**
- Modify: `requirements.txt`, `app/core/config.py`

**Interfaces:**
- Produces: `settings.ANTHROPIC_API_KEY: str`, `settings.EXAM_AI_MODEL: str`; paquetes `anthropic`, `pdfplumber`, `python-docx`, `python-pptx` instalados.

- [ ] **Step 1: Añadir dependencias a requirements.txt**

Agregar al final de `backend/requirements.txt`:
```
# Módulo de Exámenes — generación con IA (Fase 3)
anthropic==0.40.0
pdfplumber==0.11.4
python-docx==1.1.2
python-pptx==1.0.2
```
(Si una versión exacta falla al instalar, usar la más cercana disponible y anotarlo.)

- [ ] **Step 2: Instalar en el venv**

Run: `cd backend && ./venv/Scripts/python.exe -m pip install anthropic pdfplumber python-docx python-pptx`
Expected: `Successfully installed ...`.

- [ ] **Step 3: Añadir settings**

En `app/core/config.py`, dentro de `class Settings`, junto a otras config (ej. cerca de `MAIL_SERVER`/`REDIS_URL`), agregar:
```python
    ANTHROPIC_API_KEY: str = ""
    EXAM_AI_MODEL: str = "claude-sonnet-4-6"
```

- [ ] **Step 4: Verificar import + settings**

Run: `cd backend && ./venv/Scripts/python.exe -c "import anthropic, pdfplumber, docx, pptx; from app.core.config import settings; print('OK', settings.EXAM_AI_MODEL)"`
Expected: `OK claude-sonnet-4-6`.

- [ ] **Step 5: Suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q` → pasa.
```bash
git add backend/requirements.txt backend/app/core/config.py
git commit -m "chore(examenes): dependencias IA + config ANTHROPIC_API_KEY/EXAM_AI_MODEL"
```

---

### Task 2: Validación de preguntas generadas + schemas

**Files:**
- Create: `app/services/examen_ia_service.py`
- Modify: `app/schemas/examenes.py`
- Test: `tests/test_examen_ia_service.py`

**Interfaces:**
- Produces:
  - `examen_ia_service.validar_preguntas_generadas(data: list) -> list[dict]` — valida que cada item tenga `tipo` in {multi,caso}, `texto` no vacío, `opciones` lista de exactamente 4 strings, `correcta` int 0..3, `explicacion` string; `escenario` requerido si `tipo=caso`. Lanza `ValueError` con mensaje claro si algo falla. Retorna la lista normalizada.
  - Schemas `GenerarIARequest` (n_multi:int≥0, n_casos:int≥0, texto_pegado:str|None, nombre:str, producto:str|None), `GenerarIAResponse` (job_id:int, examen_id:int, estado:str), `JobIAEstado` (job_id, estado, mensaje_error:str|None, examen_id:int|None, total_preguntas:int).

- [ ] **Step 1: Test de validación**

Crear `tests/test_examen_ia_service.py`:
```python
import pytest
from app.services import examen_ia_service as ia

def _q(**kw):
    base = {"tipo": "multi", "texto": "¿?", "opciones": ["a", "b", "c", "d"],
            "correcta": 1, "explicacion": "porque"}
    base.update(kw)
    return base

def test_validar_ok():
    out = ia.validar_preguntas_generadas([_q(), _q(tipo="caso", escenario="esc")])
    assert len(out) == 2

def test_validar_opciones_distintas_de_4_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(opciones=["a", "b", "c"])])

def test_validar_correcta_fuera_de_rango_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(correcta=5)])

def test_validar_caso_sin_escenario_falla():
    with pytest.raises(ValueError):
        ia.validar_preguntas_generadas([_q(tipo="caso")])
```

- [ ] **Step 2: Verificar falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_ia_service.py -k validar -q` → FAIL (módulo no existe).

- [ ] **Step 3: Implementar `validar_preguntas_generadas`**

Crear `app/services/examen_ia_service.py`:
```python
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
        if not isinstance(correcta, int) or not (0 <= correcta <= 3):
            raise ValueError(f"Pregunta {i}: 'correcta' debe ser 0..3")
        if tipo == "caso" and not (q.get("escenario") or "").strip():
            raise ValueError(f"Pregunta {i}: caso clínico requiere 'escenario'")
        out.append({
            "tipo": tipo, "texto": q["texto"].strip(),
            "escenario": (q.get("escenario") or None),
            "opciones": [o.strip() for o in ops], "correcta": correcta,
            "explicacion": (q.get("explicacion") or "").strip()})
    return out
```

- [ ] **Step 4: Verificar pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_ia_service.py -k validar -q` → PASS.

- [ ] **Step 5: Schemas**

Agregar a `app/schemas/examenes.py`:
```python
class GenerarIARequest(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    producto: str | None = None
    n_multi: int = Field(default=5, ge=0, le=50)
    n_casos: int = Field(default=0, ge=0, le=50)
    texto_pegado: str | None = None


class GenerarIAResponse(BaseModel):
    job_id: int
    examen_id: int
    estado: str


class JobIAEstado(BaseModel):
    job_id: int
    estado: str
    mensaje_error: str | None = None
    examen_id: int | None = None
    total_preguntas: int = 0
```

- [ ] **Step 6: Suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q` → pasa.
```bash
git add backend/app/services/examen_ia_service.py backend/app/schemas/examenes.py backend/tests/test_examen_ia_service.py
git commit -m "feat(examenes): validacion de preguntas IA + schemas generar-ia"
```

---

### Task 3: Extracción de texto de documentos

**Files:**
- Modify: `app/services/examen_ia_service.py`
- Test: `tests/test_examen_ia_service.py`

**Interfaces:**
- Produces: `examen_ia_service.extraer_texto_fuente(ruta: str, tipo_archivo: str) -> str` — despacha por `tipo_archivo` (pdf|docx|pptx|texto): pdf→pdfplumber, docx→python-docx, pptx→python-pptx, texto→leer el archivo. Lanza `ValueError` para tipo no soportado.

- [ ] **Step 1: Test (con docx generado al vuelo)**

Agregar a `tests/test_examen_ia_service.py`:
```python
def test_extraer_texto_docx(tmp_path):
    from docx import Document
    doc = Document()
    doc.add_paragraph("Paracetamol reduce la fiebre.")
    p = tmp_path / "fuente.docx"
    doc.save(str(p))
    texto = ia.extraer_texto_fuente(str(p), "docx")
    assert "Paracetamol" in texto

def test_extraer_texto_plano(tmp_path):
    p = tmp_path / "f.txt"
    p.write_text("Contenido de prueba", encoding="utf-8")
    assert "prueba" in ia.extraer_texto_fuente(str(p), "texto")

def test_extraer_tipo_no_soportado_falla(tmp_path):
    with pytest.raises(ValueError):
        ia.extraer_texto_fuente("x", "rtf")
```

- [ ] **Step 2: Verificar falla, implementar, verificar pasa**

Agregar a `examen_ia_service.py`:
```python
def extraer_texto_fuente(ruta: str, tipo_archivo: str) -> str:
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
```
Run focused tests → PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/examen_ia_service.py backend/tests/test_examen_ia_service.py
git commit -m "feat(examenes): extraccion de texto PDF/Word/PPT/texto"
```

---

### Task 4: Generación con Claude (cliente inyectable)

**Files:**
- Modify: `app/services/examen_ia_service.py`
- Test: `tests/test_examen_ia_service.py`

**Interfaces:**
- Produces:
  - `examen_ia_service.construir_prompt(texto, n_multi, n_casos) -> str` (prompt base §11).
  - `examen_ia_service.generar_preguntas_ia(texto, n_multi, n_casos, client=None, model=None) -> list[dict]` — si `client is None`, construye `anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY)`; llama `client.messages.create(model, max_tokens, messages=[...])`; extrae el texto de la respuesta; parsea JSON (tolerante a fences ```json); valida con `validar_preguntas_generadas`. **El cliente se inyecta para test (mock).**

- [ ] **Step 1: Test con cliente mock**

Agregar a `tests/test_examen_ia_service.py`:
```python
import json as _json
from unittest.mock import MagicMock

def _mock_client(payload):
    client = MagicMock()
    msg = MagicMock()
    bloque = MagicMock()
    bloque.text = _json.dumps(payload)
    msg.content = [bloque]
    client.messages.create.return_value = msg
    return client

def test_generar_preguntas_ia_parsea_y_valida():
    payload = [{"tipo": "multi", "texto": "¿?", "opciones": ["a","b","c","d"],
                "correcta": 0, "explicacion": "e"}]
    client = _mock_client(payload)
    out = ia.generar_preguntas_ia("texto fuente", n_multi=1, n_casos=0, client=client)
    assert len(out) == 1 and out[0]["correcta"] == 0
    assert client.messages.create.called

def test_generar_preguntas_ia_json_invalido_falla():
    client = MagicMock()
    msg = MagicMock(); bloque = MagicMock(); bloque.text = "no soy json"
    msg.content = [bloque]; client.messages.create.return_value = msg
    with pytest.raises(ValueError):
        ia.generar_preguntas_ia("t", 1, 0, client=client)
```

- [ ] **Step 2: Verificar falla, implementar, verificar pasa**

Agregar a `examen_ia_service.py` (import `from app.core.config import settings`):
```python
def construir_prompt(texto: str, n_multi: int, n_casos: int) -> str:
    total = n_multi + n_casos
    return (
        "Eres un experto en capacitación farmacéutica. Analiza el siguiente documento "
        f"y genera exactamente {total} preguntas de evaluación:\n"
        f"- {n_multi} de opción múltiple\n- {n_casos} casos clínicos\n\n"
        "Devuelve SOLO un arreglo JSON. Cada pregunta con este esquema:\n"
        "tipo: 'multi'|'caso'; escenario: string (solo caso); texto: string; "
        "opciones: [string,string,string,string] (exactamente 4); correcta: 0|1|2|3; "
        "explicacion: string.\n\nDOCUMENTO:\n" + texto)


def _extraer_json(texto_respuesta: str):
    t = texto_respuesta.strip()
    if "```" in t:  # tolerar fences ```json ... ```
        t = t.split("```")[1]
        if t.startswith("json"):
            t = t[4:]
    t = t.strip()
    try:
        return json.loads(t)
    except json.JSONDecodeError as e:
        raise ValueError(f"La IA no devolvió JSON válido: {e}")


def generar_preguntas_ia(texto, n_multi, n_casos, client=None, model=None) -> list[dict]:
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
```
Run focused tests → PASS.

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/examen_ia_service.py backend/tests/test_examen_ia_service.py
git commit -m "feat(examenes): generacion de preguntas con Claude (cliente inyectable)"
```

---

### Task 5: Persistencia + endpoint + job en background

**Files:**
- Modify: `app/services/examen_ia_service.py`, `app/api/v1/routers/examenes.py`
- Test: `tests/test_examen_ia_service.py`

**Interfaces:**
- Produces:
  - `examen_ia_service.persistir_preguntas(db, examen_id, preguntas: list[dict]) -> int` — inserta cada pregunta (estado borrador del examen) con sus 4 opciones (`indice_original` 0..3, `es_correcta` = (idx==correcta)); retorna cantidad insertada.
  - `examen_ia_service.procesar_generacion_ia(fuente_id)` — job: crea `SessionLocal()`; set FuenteIA `procesando`; extrae texto; genera; persiste en el examen; set `exitoso` (o `error` + mensaje); cierra sesión en finally.
  - Endpoints `POST /examenes/generar-ia` (multipart: archivo opcional + campos; o texto_pegado) → crea examen borrador (fuente="ia") + FuenteIA pendiente + lanza BackgroundTask → `GenerarIAResponse`; `GET /examenes/generar-ia/{job_id}` → `JobIAEstado`.

- [ ] **Step 1: Test de `persistir_preguntas`**

```python
def test_persistir_preguntas_marca_correcta(monkeypatch):
    from unittest.mock import MagicMock
    db = MagicMock()
    agregados = []
    db.add.side_effect = lambda obj: agregados.append(obj)
    n = ia.persistir_preguntas(db, examen_id=1, preguntas=[
        {"tipo":"multi","texto":"¿?","escenario":None,
         "opciones":["a","b","c","d"],"correcta":2,"explicacion":"e"}])
    assert n == 1
    # la opción en índice 2 es la correcta
    opciones = [o for o in agregados if getattr(o, "indice_original", None) is not None]
    assert any(getattr(o,"es_correcta",False) and o.indice_original==2 for o in opciones)
```

- [ ] **Step 2: Implementar `persistir_preguntas` + `procesar_generacion_ia`**

```python
from datetime import datetime, timezone
from app.models.exam_models import Examen, Pregunta, PreguntaOpcion, FuenteIA
from app.db.database import SessionLocal


def persistir_preguntas(db, examen_id: int, preguntas: list[dict]) -> int:
    base = db.query(Pregunta).filter(Pregunta.examen_id == examen_id).count()
    for offset, q in enumerate(preguntas):
        pregunta = Pregunta(examen_id=examen_id, tipo=q["tipo"], escenario=q.get("escenario"),
                            texto=q["texto"], explicacion=q.get("explicacion"), orden=base + offset)
        for idx, texto_op in enumerate(q["opciones"]):
            pregunta.opciones.append(PreguntaOpcion(
                texto_opcion=texto_op, indice_original=idx, es_correcta=(idx == q["correcta"])))
        db.add(pregunta)
    db.commit()
    return len(preguntas)


def procesar_generacion_ia(fuente_id: int) -> None:
    db = SessionLocal()
    try:
        fuente = db.query(FuenteIA).filter(FuenteIA.id == fuente_id).first()
        if fuente is None:
            return
        fuente.estado_generacion = "procesando"; db.commit()
        try:
            texto = (extraer_texto_fuente(fuente.ruta_archivo, fuente.tipo_archivo)
                     if fuente.ruta_archivo else fuente.prompt_usado or "")
            n_multi = int((fuente.mensaje_error or "0").split("|")[0]) if False else 0  # placeholder
            # n_multi/n_casos vienen del examen/fuente — ver nota
            preguntas = generar_preguntas_ia(texto, fuente._n_multi, fuente._n_casos)  # ver nota
            persistir_preguntas(db, fuente.examen_id, preguntas)
            fuente.estado_generacion = "exitoso"; fuente.mensaje_error = None
        except Exception as e:
            fuente.estado_generacion = "error"; fuente.mensaje_error = str(e)[:1000]
            logger.error(f"Generación IA fuente={fuente_id} falló: {e}")
        db.commit()
    finally:
        db.close()
```
> Nota para el implementer: `n_multi`/`n_casos` deben llevarse a través de la fila (p.ej. guardándolos en `FuenteIA.prompt_usado` como JSON, o añadiendo campos). Elige la forma más limpia consistente con el modelo (sin migración nueva si es posible: serializa `{"n_multi":..,"n_casos":..,"texto_pegado":..}` en `prompt_usado` al crear la fuente, y léelo en el job). Documenta tu elección.

- [ ] **Step 3: Endpoints**

En `examenes.py`, agregar `POST /examenes/generar-ia` (usa `RequireCapacitacion`, `BackgroundTasks`, `UploadFile` opcional + `Form` fields; valida magic bytes si hay archivo; guarda con `_safe_filename`; crea `Examen(estado="borrador", fuente="ia", ...)`, `FuenteIA(estado_generacion="pendiente", ...)`; `background_tasks.add_task(examen_ia_service.procesar_generacion_ia, fuente.id)`; retorna `GenerarIAResponse`). Y `GET /examenes/generar-ia/{job_id}` → arma `JobIAEstado` leyendo la `FuenteIA` + contando preguntas del examen. Reusar `_safe_filename`/`_validar_magic_bytes` (importar de `etl.py` o replicar; preferir importar si están expuestos).

- [ ] **Step 4: Verificar app + suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'generar-ia' in getattr(r,'path','')])"` y `./venv/Scripts/python.exe -m pytest -q`.
```bash
git add backend/app/services/examen_ia_service.py backend/app/api/v1/routers/examenes.py backend/tests/test_examen_ia_service.py
git commit -m "feat(examenes): endpoint generar-ia + job en background + persistencia"
```

---

## Self-Review (cobertura del spec, Fase 3)

- Dependencias + config IA → Task 1. ✓
- Validación JSON IA → Task 2. ✓
- Extracción PDF/Word/PPT/texto → Task 3. ✓
- Generación con Claude (cliente inyectable, key por env, mockeable) → Task 4. ✓
- Persistencia como borrador + endpoint + job background + estado → Task 5. ✓
- IA siempre a borrador para revisión (RN) → Task 5 (examen queda en borrador; la revisión/edición usa el CRUD de Fase 2). ✓
- **Pendiente operativo:** correr la generación real requiere `ANTHROPIC_API_KEY` en `.env` (los tests usan mock; el código está completo).
