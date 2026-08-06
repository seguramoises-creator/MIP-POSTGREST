# Simulacro de Venta con IA (Fase 8) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** El RM practica una venta contra un médico simulado por IA: por fase MORE (Apertura/Desarrollo/Cierre) una objeción hablada (TTS) y respuesta de opción múltiple, calificada D/P/A/E como Coaching MORE.

**Architecture:** Servicio Python (`formacion_simulacro_service`) que genera el escenario con la capa de IA de la Fase 0 (`conexion_service.adaptador_texto`), lo persiste en las tablas `Simulacro*` (Fase 1), y sintetiza la voz con `adaptador_voz` (degradando a Web Speech del navegador). Router `/formacion/simulacro` con auto-scope de RM. Frontend: sesión guiada por rondas. **Sin migración.**

**Tech Stack:** FastAPI, SQLAlchemy 2.0, pytest (PostgreSQL real por módulo), React 18 + TS + MUI v6 + TanStack Query + Zustand.

## Global Constraints

- Solo edición **PostgreSQL** (`MSM-postgres`). No tocar ni nombrar la edición SQL Server.
- Modelos SQLAlchemy 2.0 `Mapped`; timestamps `datetime.now(timezone.utc)`; logs con `from loguru import logger` (nunca `print`).
- La correcta y la retroalimentación de una ronda **NUNCA** viajan antes de responder (patrón `score_oculto`/Refuerzo §10.7).
- Generación IA: **todo el escenario en 1 llamada** de texto; parseo robusto reutilizando `examen_ia_service._extraer_json`. Sin conexión de texto → propagar `SinConexionIA` (router → 503). Sin fallback de contenido.
- Voz **degradable**: usa `adaptador_voz`; si no hay proveedor real, la Fase 0 devuelve `Audio(en_navegador=True)` y el frontend sintetiza con Web Speech API. La voz nunca bloquea la práctica.
- Escala por fase: `ratio ≥0.90→4, ≥0.70→3, ≥0.50→2, resto→1`; general = promedio de las 3, Numeric(4,2). Rondas sin responder = incorrectas.
- Fases calificadas: **Apertura, Desarrollo, Cierre** (las que tiene `SimulacroResultado`). `Planificacion` fuera de MVP.
- Rutas de Formación gatean por `allowedRoles`/`require_roles`, NO por la matriz RBAC.
- Commits en español, prefijo `feat(formacion)`/`fix(formacion)`, terminando con `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- Create `backend/app/services/formacion_simulacro_service.py` — motor.
- Create `backend/app/api/v1/routers/formacion_simulacro.py` — router REST.
- Modify `backend/app/api/v1/router.py` — registrar router.
- Create `backend/tests/test_formacion_simulacro.py` — pruebas (capa IA mockeada).
- Modify `frontend/src/services/formacion.service.ts` — funciones/tipos del simulacro.
- Create `frontend/src/pages/formacion/Simulacro.tsx` — página de sesión guiada.
- Modify `frontend/src/App.tsx` — ruta lazy `/formacion/simulacro`.
- Modify `frontend/src/components/layout/Sidebar.tsx` — ítem "Simulacro de Venta".

---

### Task 1: Escala D/P/A/E + constantes + excepciones

**Files:**
- Create: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `ESTILOS: tuple`, `FASES: tuple`, `class SimulacroIAError(RuntimeError)`, `class PermisoError(RuntimeError)`, `escala(ratio) -> int`.

- [ ] **Step 1: Write the failing test** (crea el archivo de test con infraestructura de BD + estas pruebas puras)

```python
"""Simulacro de Venta con IA (Fase 8) — motor sobre la capa de IA (mockeada)."""
import json

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Gerente, Linea, Pais, RepresentanteMedico
from app.services import formacion_simulacro_service as sim

BD_PRUEBA = "vista_test_simulacro"


@pytest.mark.parametrize("ratio, esperado", [
    (1.0, 4), (0.90, 4), (0.89, 3), (0.70, 3), (0.69, 2),
    (0.50, 2), (0.49, 1), (0.0, 1),
])
def test_la_escala_dpae_respeta_los_cortes(ratio, esperado):
    assert sim.escala(ratio) == esperado


def test_las_fases_calificadas_son_tres():
    assert sim.FASES == ("Apertura", "Desarrollo", "Cierre")


# --- infraestructura de BD (patrón de test_formacion_calendario) ---
def _url(nombre: str) -> str:
    return (f"postgresql+psycopg2://{settings.DB_USER}:{settings.DB_PASSWORD}"
            f"@{settings.DB_SERVER}:{settings.DB_PORT}/{nombre}")


@pytest.fixture(scope="module")
def motor():
    try:
        admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
        with admin.connect() as cx:
            cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
            cx.execute(text(f"CREATE DATABASE {BD_PRUEBA}"))
        admin.dispose()
    except Exception as exc:  # noqa: BLE001
        pytest.skip(f"sin PostgreSQL alcanzable: {exc}")
    eng = create_engine(_url(BD_PRUEBA))
    with eng.begin() as cx:
        for esquema in ("Config", "Security", "DW", "Audit", "ETL", "exam",
                        "Visita", "coaching", "cat", "stg", "formacion", "ext"):
            cx.execute(text(f'CREATE SCHEMA IF NOT EXISTS "{esquema}"'))
    Base.metadata.create_all(eng)
    yield eng
    eng.dispose()
    admin = create_engine(_url("postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as cx:
        cx.execute(text(f"DROP DATABASE IF EXISTS {BD_PRUEBA} WITH (FORCE)"))
    admin.dispose()


@pytest.fixture
def db(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for t in ('formacion."SimulacroResultado"', 'formacion."SimulacroRonda"',
              'formacion."SimulacroSesion"', '"Config"."DIM_RM"',
              '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.add(Pais(codigo="DO", nombre="República Dominicana")); s.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología"); s.add(linea); s.flush()
    gd = Gerente(pais_codigo="DO", codigo="GD-1", nombre="GD Uno", tipo="DISTRITO"); s.add(gd); s.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                             codigo="VM01", nombre="Ana"); s.add(rm); s.commit()
    yield s, rm, gd
    s.close()


# Escenario canónico que devuelve la IA mockeada (reutilizado por varias pruebas).
ESCENARIO_OK = {
    "rondas": [
        {"fase_more": "Apertura", "objecion_texto": "No tengo tiempo hoy.",
         "opciones": {"A": "Insistir", "B": "Acordar 2 minutos y ser concreto", "C": "Irse"},
         "opcion_correcta": "B", "retroalimentacion": "Respetar el tiempo abre la puerta."},
        {"fase_more": "Desarrollo", "tecnica_objecion": "Sentir-Sintió-Descubrió",
         "objecion_texto": "Su producto es caro.",
         "opciones": {"A": "Bajar el precio", "B": "Reconocer y mostrar valor clínico", "C": "Callar"},
         "opcion_correcta": "B", "retroalimentacion": "El valor se argumenta, no se descuenta."},
        {"fase_more": "Cierre", "objecion_texto": "Lo pensaré.",
         "opciones": {"A": "Cerrar con un compromiso concreto", "B": "Despedirse sin más"},
         "opcion_correcta": "A", "retroalimentacion": "Un cierre pide un siguiente paso claro."},
    ]
}


class _TextoStub:
    """Adaptador de texto de prueba: devuelve el JSON que se le configure."""
    def __init__(self, payload): self._payload = payload
    def generar_texto(self, prompt, max_tokens=4000): return self._payload


class _VozStub:
    def sintetizar(self, texto, voz=None):
        from app.services.ia.base import Audio
        return Audio(en_navegador=True, aviso="prueba")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "escala or fases" -q`
Expected: FAIL — `ModuleNotFoundError: ... formacion_simulacro_service`.

- [ ] **Step 3: Write minimal implementation** (crea el servicio)

```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "escala or fases" -q`
Expected: PASS (9 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: escala D/P/A/E, constantes y excepciones"
```

---

### Task 2: Prompt + parseo/validación del escenario IA

**Files:**
- Modify: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `construir_prompt(estilo, medico, genero) -> str`, `parsear_escenario(texto) -> list[dict]`.
- Consumes: `examen_ia_service._extraer_json` (parser robusto de JSON con fences).

- [ ] **Step 1: Write the failing test**

```python
def test_parsea_escenario_con_fences_markdown():
    crudo = "```json\n" + json.dumps(ESCENARIO_OK) + "\n```"
    rondas = sim.parsear_escenario(crudo)
    assert [r["fase_more"] for r in rondas] == ["Apertura", "Desarrollo", "Cierre"]
    assert rondas[1]["tecnica_objecion"] == "Sentir-Sintió-Descubrió"


def test_rechaza_escenario_sin_opcion_correcta_valida():
    malo = {"rondas": [{"fase_more": "Apertura", "objecion_texto": "x",
                        "opciones": {"A": "s"}, "opcion_correcta": "Z",
                        "retroalimentacion": "r"}]}
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario(json.dumps(malo))


def test_rechaza_desarrollo_sin_tecnica():
    malo = {"rondas": [{"fase_more": "Desarrollo", "objecion_texto": "x",
                        "opciones": {"A": "s", "B": "t"}, "opcion_correcta": "A",
                        "retroalimentacion": "r"}]}
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario(json.dumps(malo))


def test_rechaza_json_no_json():
    with pytest.raises(sim.SimulacroIAError):
        sim.parsear_escenario("esto no es json")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "parsea or rechaza" -q`
Expected: FAIL — `AttributeError: ... 'parsear_escenario'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade el import arriba)

```python
from app.services.examen_ia_service import _extraer_json
```
```python
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
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "parsea or rechaza" -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: prompt y parseo/validacion del escenario IA"
```

---

### Task 3: `iniciar` — genera (IA mockeada), persiste sesión + rondas, no filtra la correcta

**Files:**
- Modify: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `ronda_publica(r) -> dict`, `iniciar(db, rm_id, estilo=None, medico=None, genero=None) -> dict` con forma `{"sesion":{"id","rm_id","estilo","medico","genero","finalizada"}, "rondas":[ronda_publica...]}`.
- Consumes: `conexion_service.adaptador_texto(db).generar_texto(...)`; modelos `SimulacroSesion`, `SimulacroRonda`.

- [ ] **Step 1: Write the failing test**

```python
def test_iniciar_persiste_las_tres_rondas_sin_filtrar_la_correcta(db, monkeypatch):
    s, rm, _ = db
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub(json.dumps(ESCENARIO_OK)))
    r = sim.iniciar(s, rm.id, estilo="Analitico", medico="Dr. Peralta", genero="M")
    assert r["sesion"]["estilo"] == "Analitico"
    assert len(r["rondas"]) == 3
    serial = json.dumps(r["rondas"])
    assert "opcion_correcta" not in serial and "retroalimentacion" not in serial
    # Las opciones sí viajan (sin ellas no hay nada que elegir).
    assert set(r["rondas"][0]["opciones"]) >= {"A", "B"}


def test_iniciar_reintenta_una_vez_y_luego_falla(db, monkeypatch):
    s, rm, _ = db
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub("basura no json"))
    with pytest.raises(sim.SimulacroIAError):
        sim.iniciar(s, rm.id, estilo="Directivo", medico="Dra. Reyes", genero="F")
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "iniciar" -q`
Expected: FAIL — `AttributeError: ... 'iniciar'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade imports)

```python
from app.models.formacion import SimulacroRonda, SimulacroSesion
from app.services.ia import conexion_service
```
```python
def ronda_publica(r: SimulacroRonda) -> dict:
    """Lo que ve el RM. La correcta y la retro SOLO tras responder (§10.7)."""
    d = {"id": r.id, "fase_more": r.fase_more, "tecnica_objecion": r.tecnica_objecion,
         "objecion_texto": r.objecion_texto, "opciones": r.opciones,
         "opcion_seleccionada": r.opcion_seleccionada, "es_correcta": r.es_correcta}
    if r.opcion_seleccionada is not None:
        d["opcion_correcta"] = r.opcion_correcta
        d["retroalimentacion"] = r.retroalimentacion
    return d


def _sesion_publica(s: SimulacroSesion) -> dict:
    return {"id": s.id, "rm_id": s.rm_id, "estilo": s.estilo_social_asignado,
            "medico": s.medico_simulado, "genero": s.genero_simulado,
            "finalizada": s.finalizada}


def iniciar(db: Session, rm_id: int, estilo: str | None = None,
            medico: str | None = None, genero: str | None = None) -> dict:
    """Genera el escenario con IA y arranca la sesión. 1 reintento si la IA
    devuelve algo inválido; luego SimulacroIAError. SinConexionIA se propaga."""
    if estilo is None:
        estilo = random.choice(ESTILOS)
    if medico is None:
        medico, genero = random.choice(_MEDICOS)
    prompt = construir_prompt(estilo, medico, genero)

    rondas_datos = None
    for intento in (1, 2):
        texto = conexion_service.adaptador_texto(db).generar_texto(prompt)
        try:
            rondas_datos = parsear_escenario(texto)
            break
        except SimulacroIAError:
            logger.warning(f"Simulacro: escenario IA inválido (intento {intento}).")
    if rondas_datos is None:
        raise SimulacroIAError("La IA no produjo un escenario válido tras el reintento.")

    sesion = SimulacroSesion(rm_id=rm_id, estilo_social_asignado=estilo,
                             medico_simulado=medico, genero_simulado=genero)
    db.add(sesion)
    db.flush()
    for r in rondas_datos:
        db.add(SimulacroRonda(
            sesion_id=sesion.id, fase_more=r["fase_more"],
            tecnica_objecion=r.get("tecnica_objecion"),
            objecion_texto=r["objecion_texto"], opciones=r["opciones"],
            opcion_correcta=r["opcion_correcta"],
            retroalimentacion=r.get("retroalimentacion")))
    db.commit()
    filas = (db.query(SimulacroRonda)
             .filter(SimulacroRonda.sesion_id == sesion.id)
             .order_by(SimulacroRonda.id).all())
    return {"sesion": _sesion_publica(sesion), "rondas": [ronda_publica(x) for x in filas]}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "iniciar" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: iniciar (genera con IA, persiste, oculta la correcta)"
```

---

### Task 4: `responder` — califica, revela, rechaza doble respuesta, valida dueño

**Files:**
- Modify: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `responder(db, ronda_id, opcion, rm_id_scope=None) -> dict` con forma `{"es_correcta","opcion_correcta","retroalimentacion"}`.

- [ ] **Step 1: Write the failing test**

```python
def _iniciar_ok(s, rm, monkeypatch):
    monkeypatch.setattr(sim.conexion_service, "adaptador_texto",
                        lambda _db=None: _TextoStub(json.dumps(ESCENARIO_OK)))
    return sim.iniciar(s, rm.id, estilo="Amistoso", medico="Dra. Fermín", genero="F")


def test_responder_correcto_revela_correcta_y_retro(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    ronda_id = r["rondas"][0]["id"]      # Apertura, correcta = B
    res = sim.responder(s, ronda_id, "B")
    assert res["es_correcta"] is True
    assert res["opcion_correcta"] == "B"
    assert "puerta" in res["retroalimentacion"]


def test_responder_incorrecto_tambien_revela(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    res = sim.responder(s, r["rondas"][0]["id"], "A")
    assert res["es_correcta"] is False
    assert res["opcion_correcta"] == "B"


def test_no_se_responde_dos_veces(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    rid = r["rondas"][0]["id"]
    sim.responder(s, rid, "A")
    with pytest.raises(ValueError):
        sim.responder(s, rid, "B")


def test_un_rm_ajeno_no_puede_responder(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    with pytest.raises(sim.PermisoError):
        sim.responder(s, r["rondas"][0]["id"], "B", rm_id_scope=rm.id + 999)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "responder or dos_veces or ajeno" -q`
Expected: FAIL — `AttributeError: ... 'responder'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio)

```python
def responder(db: Session, ronda_id: int, opcion: str,
              rm_id_scope: int | None = None) -> dict:
    """Registra la elección y revela la correcta + retro. `rm_id_scope`, si se da,
    debe coincidir con el dueño de la sesión (None = privilegiado/ADMIN)."""
    r = db.get(SimulacroRonda, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    sesion = db.get(SimulacroSesion, r.sesion_id)
    if rm_id_scope is not None and sesion.rm_id != rm_id_scope:
        raise PermisoError("Esta ronda no es de tu sesión.")
    if r.opcion_seleccionada is not None:
        raise ValueError("Esta ronda ya fue respondida.")
    r.opcion_seleccionada = opcion
    r.es_correcta = (opcion == r.opcion_correcta)
    db.commit()
    return {"es_correcta": r.es_correcta, "opcion_correcta": r.opcion_correcta,
            "retroalimentacion": r.retroalimentacion}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "responder or dos_veces or ajeno" -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: responder (califica, revela, guarda dueño)"
```

---

### Task 5: `finalizar` — D/P/A/E por fase + general, re-ejecutable

**Files:**
- Modify: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `finalizar(db, sesion_id, rm_id_scope=None) -> dict` con forma `{"apertura","desarrollo","cierre","general"}`.

- [ ] **Step 1: Write the failing test**

```python
def test_finalizar_calcula_dpae_por_fase_y_general(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    by_fase = {x["fase_more"]: x["id"] for x in r["rondas"]}
    sim.responder(s, by_fase["Apertura"], "B")    # correcto → 1.0 → 4
    sim.responder(s, by_fase["Desarrollo"], "A")  # incorrecto → 0.0 → 1
    # Cierre queda SIN responder → cuenta como incorrecto → 0.0 → 1
    res = sim.finalizar(s, r["sesion"]["id"])
    assert res["apertura"] == 4
    assert res["desarrollo"] == 1
    assert res["cierre"] == 1
    assert res["general"] == 2.0   # (4+1+1)/3 = 2.0
    # La sesión queda finalizada y es re-ejecutable sin duplicar.
    from app.models.formacion import SimulacroResultado, SimulacroSesion
    assert s.get(SimulacroSesion, r["sesion"]["id"]).finalizada is True
    sim.finalizar(s, r["sesion"]["id"])
    assert s.query(SimulacroResultado).filter(
        SimulacroResultado.sesion_id == r["sesion"]["id"]).count() == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "finalizar" -q`
Expected: FAIL — `AttributeError: ... 'finalizar'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade imports)

```python
from decimal import Decimal
from app.models.formacion import SimulacroResultado
```
```python
def _fase_escala(rondas: list[SimulacroRonda], fase: str) -> int:
    """Escala D/P/A/E de una fase: aciertos / total (sin responder = incorrecto)."""
    de_fase = [r for r in rondas if r.fase_more == fase]
    if not de_fase:
        return 1
    aciertos = sum(1 for r in de_fase if r.es_correcta)
    return escala(aciertos / len(de_fase))


def finalizar(db: Session, sesion_id: int, rm_id_scope: int | None = None) -> dict:
    sesion = db.get(SimulacroSesion, sesion_id)
    if sesion is None:
        raise ValueError("Sesión no encontrada")
    if rm_id_scope is not None and sesion.rm_id != rm_id_scope:
        raise PermisoError("Esta sesión no es tuya.")
    rondas = (db.query(SimulacroRonda)
              .filter(SimulacroRonda.sesion_id == sesion_id).all())
    ap = _fase_escala(rondas, "Apertura")
    de = _fase_escala(rondas, "Desarrollo")
    ci = _fase_escala(rondas, "Cierre")
    general = round((ap + de + ci) / 3, 2)

    db.query(SimulacroResultado).filter(
        SimulacroResultado.sesion_id == sesion_id).delete(synchronize_session=False)
    db.add(SimulacroResultado(
        sesion_id=sesion_id, calificacion_apertura=ap, calificacion_desarrollo=de,
        calificacion_cierre=ci, calificacion_general=Decimal(str(general))))
    sesion.finalizada = True
    db.commit()
    return {"apertura": ap, "desarrollo": de, "cierre": ci, "general": general}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "finalizar" -q`
Expected: PASS (1 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: finalizar (D/P/A/E por fase + general, re-ejecutable)"
```

---

### Task 6: Lectura — `voz_ronda`, `detalle`, `mis_sesiones`, `resumen`

**Files:**
- Modify: `backend/app/services/formacion_simulacro_service.py`
- Test: `backend/tests/test_formacion_simulacro.py`

**Interfaces:**
- Produces: `voz_ronda(db, ronda_id) -> Audio`, `detalle(db, sesion_id) -> dict`, `mis_sesiones(db, rm_id) -> list[dict]`, `resumen(db, rm_ids=None) -> list[dict]`.

- [ ] **Step 1: Write the failing test**

```python
def test_voz_ronda_usa_el_adaptador_de_voz(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    monkeypatch.setattr(sim.conexion_service, "adaptador_voz", lambda _db=None: _VozStub())
    audio = sim.voz_ronda(s, r["rondas"][0]["id"])
    assert audio.en_navegador is True


def test_detalle_no_filtra_correctas_no_respondidas(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    d = sim.detalle(s, r["sesion"]["id"])
    assert "opcion_correcta" not in json.dumps(d["rondas"])


def test_mis_sesiones_y_resumen(db, monkeypatch):
    s, rm, _ = db
    r = _iniciar_ok(s, rm, monkeypatch)
    sim.finalizar(s, r["sesion"]["id"])
    assert len(sim.mis_sesiones(s, rm.id)) == 1
    fila = next(f for f in sim.resumen(s) if f["rm_id"] == rm.id)
    assert fila["practicas"] == 1
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -k "voz or detalle or mis_sesiones" -q`
Expected: FAIL — `AttributeError: ... 'voz_ronda'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio)

```python
def voz_ronda(db: Session, ronda_id: int):
    """Audio de la objeción: bytes si hay proveedor real, o Audio(en_navegador)."""
    r = db.get(SimulacroRonda, ronda_id)
    if r is None:
        raise ValueError("Ronda no encontrada")
    return conexion_service.adaptador_voz(db).sintetizar(r.objecion_texto)


def detalle(db: Session, sesion_id: int) -> dict:
    sesion = db.get(SimulacroSesion, sesion_id)
    if sesion is None:
        raise ValueError("Sesión no encontrada")
    rondas = (db.query(SimulacroRonda)
              .filter(SimulacroRonda.sesion_id == sesion_id)
              .order_by(SimulacroRonda.id).all())
    res = db.get(SimulacroResultado, sesion_id)
    resultado = None
    if res is not None:
        resultado = {"apertura": res.calificacion_apertura,
                     "desarrollo": res.calificacion_desarrollo,
                     "cierre": res.calificacion_cierre,
                     "general": float(res.calificacion_general) if res.calificacion_general is not None else None}
    return {"sesion": _sesion_publica(sesion),
            "rondas": [ronda_publica(x) for x in rondas], "resultado": resultado}


def mis_sesiones(db: Session, rm_id: int) -> list[dict]:
    filas = (db.query(SimulacroSesion)
             .filter(SimulacroSesion.rm_id == rm_id)
             .order_by(SimulacroSesion.fecha.desc()).all())
    return [_sesion_publica(s) | {"fecha": s.fecha} for s in filas]


def resumen(db: Session, rm_ids: list[int] | None = None) -> list[dict]:
    """Agregado por RM: nº de prácticas finalizadas y última general."""
    q = db.query(SimulacroSesion)
    if rm_ids is not None:
        q = q.filter(SimulacroSesion.rm_id.in_(rm_ids or [-1]))
    por_rm: dict[int, list[SimulacroSesion]] = {}
    for s in q.all():
        por_rm.setdefault(s.rm_id, []).append(s)
    salida = []
    for rm_id, sesiones in por_rm.items():
        finalizadas = [s for s in sesiones if s.finalizada]
        ultima = None
        if finalizadas:
            reciente = max(finalizadas, key=lambda s: s.fecha)
            res = db.get(SimulacroResultado, reciente.id)
            ultima = float(res.calificacion_general) if res and res.calificacion_general is not None else None
        salida.append({"rm_id": rm_id, "practicas": len(finalizadas), "ultima_general": ultima})
    return sorted(salida, key=lambda x: x["rm_id"])
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_simulacro.py -q`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_simulacro_service.py backend/tests/test_formacion_simulacro.py
git commit -m "feat(formacion) Simulacro: lectura (voz_ronda, detalle, mis_sesiones, resumen)"
```

---

### Task 7: Router `/formacion/simulacro` + registro + RBAC

**Files:**
- Create: `backend/app/api/v1/routers/formacion_simulacro.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Consumes: todo el servicio (Tasks 1-6). Auto-scope de RM por `Usuario.rm_id`.

- [ ] **Step 1: Write the router**

```python
"""Simulacro de Venta con IA (§9). Genera el escenario con la capa IA de la Fase 0."""
import io

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_simulacro_service as sim
from app.services.ia.conexion_service import SinConexionIA

router = APIRouter(prefix="/formacion/simulacro", tags=["Formación — Simulacro IA"])

RequirePractica = Depends(require_roles(Rol.ADMIN, Rol.REPRESENTANTE_MEDICO))
RequireLectura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
    Rol.GERENTE_DISTRITO, Rol.PRESIDENCIA, Rol.GERENTE_MEDICO,
    Rol.REPRESENTANTE_MEDICO))


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu usuario no está enlazado a un representante.")
    return rm_id


def _scope(usuario: Usuario) -> int | None:
    """rm_id a exigir como dueño; None para ADMIN (sin restricción)."""
    return None if usuario.rol == Rol.ADMIN else _rm_propio(usuario)


class IniciarEntrada(BaseModel):
    rm_id: int | None = None       # solo ADMIN puede indicar otro RM
    estilo: str | None = None
    medico: str | None = None
    genero: str | None = None


class ResponderEntrada(BaseModel):
    opcion: str


@router.post("/iniciar", summary="Generar un escenario y arrancar la sesión")
def iniciar(datos: IniciarEntrada, db: Session = Depends(get_db),
            usuario: Usuario = RequirePractica):
    rm_id = datos.rm_id if (usuario.rol == Rol.ADMIN and datos.rm_id) else _rm_propio(usuario)
    try:
        return sim.iniciar(db, rm_id, estilo=datos.estilo, medico=datos.medico,
                           genero=datos.genero)
    except SinConexionIA as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, str(exc)) from exc
    except sim.SimulacroIAError as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc


@router.get("/mis-sesiones", summary="Historial de prácticas del RM")
def mis_sesiones(db: Session = Depends(get_db), usuario: Usuario = RequirePractica):
    return sim.mis_sesiones(db, _rm_propio(usuario))


@router.get("/sesion/{sesion_id}", summary="Detalle de una sesión")
def sesion(sesion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireLectura):
    try:
        d = sim.detalle(db, sesion_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    scope = _scope(usuario)
    if scope is not None and d["sesion"]["rm_id"] != scope:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "No es tu sesión.")
    return d


@router.get("/ronda/{ronda_id}/voz", summary="Audio de la objeción (o señal Web Speech)")
def voz(ronda_id: int, db: Session = Depends(get_db), _: Usuario = RequireLectura):
    try:
        audio = sim.voz_ronda(db, ronda_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    if audio.en_navegador:
        r = db.get(sim.SimulacroRonda, ronda_id)
        return {"en_navegador": True, "texto": r.objecion_texto, "aviso": audio.aviso}
    return StreamingResponse(io.BytesIO(audio.contenido or b""),
                             media_type=audio.mime or "audio/mpeg")


@router.post("/ronda/{ronda_id}/responder", summary="Responder — revela la correcta")
def responder(ronda_id: int, datos: ResponderEntrada, db: Session = Depends(get_db),
              usuario: Usuario = RequirePractica):
    try:
        return sim.responder(db, ronda_id, datos.opcion, rm_id_scope=_scope(usuario))
    except sim.PermisoError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.post("/sesion/{sesion_id}/finalizar", summary="Calcular el resultado D/P/A/E")
def finalizar(sesion_id: int, db: Session = Depends(get_db), usuario: Usuario = RequirePractica):
    try:
        return sim.finalizar(db, sesion_id, rm_id_scope=_scope(usuario))
    except sim.PermisoError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/resumen", summary="Agregado de prácticas (GD/Capacitación)")
def resumen(db: Session = Depends(get_db), usuario: Usuario = RequireLectura):
    if usuario.rol == Rol.REPRESENTANTE_MEDICO:
        return sim.resumen(db, [_rm_propio(usuario)])
    return sim.resumen(db)
```

- [ ] **Step 2: Register the router** (modificar `backend/app/api/v1/router.py`)

Tras `from app.api.v1.routers.formacion_calendario import router as formacion_calendario_router` añadir:
```python
from app.api.v1.routers.formacion_simulacro import router as formacion_simulacro_router
```
Tras `api_router.include_router(formacion_calendario_router)  # Calendario de Coaching ...` añadir:
```python
api_router.include_router(formacion_simulacro_router)  # Simulacro de Venta con IA (9)
```

- [ ] **Step 3: Verify import + routes**

Run: `cd backend && venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'simulacro' in getattr(r,'path','')])"`
Expected: imprime las 7 rutas del simulacro.

- [ ] **Step 4: Full suite green**

Run: `cd backend && venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -3`
Expected: todos pasan (previos + nuevos del simulacro).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/formacion_simulacro.py backend/app/api/v1/router.py
git commit -m "feat(formacion) Simulacro: router /formacion/simulacro con auto-scope de RM"
```

---

### Task 8: Servicio frontend — tipos y funciones del simulacro

**Files:**
- Modify: `frontend/src/services/formacion.service.ts`

**Interfaces:**
- Produces: tipos `RondaSimulacro`, `SesionSimulacro`, `SimulacroIniciado`, `ResultadoSimulacro`, `VozRonda`; funciones `iniciarSimulacro`, `detalleSimulacro`, `vozRonda`, `responderRonda`, `finalizarSimulacro`, `misSesionesSimulacro`, `resumenSimulacro`.

- [ ] **Step 1: Append to the service file**

```typescript
// ── Simulacro de Venta con IA (§9) ────────────────────────────────────────
export interface RondaSimulacro {
  id: number; fase_more: string; tecnica_objecion: string | null;
  objecion_texto: string; opciones: Record<string, string>;
  opcion_seleccionada: string | null; es_correcta: boolean | null;
  opcion_correcta?: string; retroalimentacion?: string;
}
export interface SesionSimulacro {
  id: number; rm_id: number; estilo: string; medico: string;
  genero: string | null; finalizada: boolean;
}
export interface SimulacroIniciado { sesion: SesionSimulacro; rondas: RondaSimulacro[]; }
export interface ResultadoSimulacro {
  apertura: number; desarrollo: number; cierre: number; general: number;
}
export interface VozRonda { en_navegador: boolean; texto?: string; aviso?: string; }

export const iniciarSimulacro = (p: { estilo?: string; medico?: string; genero?: string; rm_id?: number } = {}) =>
  api.post<SimulacroIniciado>('/formacion/simulacro/iniciar', p).then((r) => r.data);

export const detalleSimulacro = (sesionId: number) =>
  api.get<{ sesion: SesionSimulacro; rondas: RondaSimulacro[]; resultado: ResultadoSimulacro | null }>(
    `/formacion/simulacro/sesion/${sesionId}`).then((r) => r.data);

export const responderRonda = (rondaId: number, opcion: string) =>
  api.post<{ es_correcta: boolean; opcion_correcta: string; retroalimentacion: string }>(
    `/formacion/simulacro/ronda/${rondaId}/responder`, { opcion }).then((r) => r.data);

export const finalizarSimulacro = (sesionId: number) =>
  api.post<ResultadoSimulacro>(`/formacion/simulacro/sesion/${sesionId}/finalizar`).then((r) => r.data);

export const misSesionesSimulacro = () =>
  api.get<(SesionSimulacro & { fecha: string })[]>('/formacion/simulacro/mis-sesiones').then((r) => r.data);

export const resumenSimulacro = () =>
  api.get<{ rm_id: number; practicas: number; ultima_general: number | null }[]>(
    '/formacion/simulacro/resumen').then((r) => r.data);

/** Voz de una ronda: si el backend devuelve JSON `en_navegador`, sintetizar con
 *  Web Speech; si devuelve audio (blob), reproducirlo. Se resuelve con la señal. */
export const vozRonda = async (rondaId: number): Promise<VozRonda> => {
  const r = await api.get(`/formacion/simulacro/ronda/${rondaId}/voz`, { responseType: 'blob' });
  const tipo = r.headers['content-type'] || '';
  if (tipo.includes('application/json')) {
    const txt = await (r.data as Blob).text();
    return JSON.parse(txt) as VozRonda;
  }
  const url = URL.createObjectURL(r.data as Blob);
  new Audio(url).play().catch(() => {/* autoplay bloqueado: el botón lo reintenta */});
  return { en_navegador: false };
};
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/formacion.service.ts
git commit -m "feat(formacion) Simulacro: capa de servicio frontend (tipos + endpoints)"
```

---

### Task 9: Página `Simulacro.tsx` + ruta + ítem de menú

**Files:**
- Create: `frontend/src/pages/formacion/Simulacro.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: las funciones del servicio de la Task 8; `useAuthStore` (`rol`).

- [ ] **Step 1: Create the page** (sesión guiada; usa Web Speech cuando `en_navegador`)

```tsx
/**
 * Simulacro.tsx — Simulacro de Venta con IA (§9).
 * Sesión guiada por rondas: el médico simulado plantea una objeción (hablada por
 * TTS del backend o Web Speech del navegador), el RM elige la respuesta, se revela
 * correcto/incorrecto + retro, y al final el resultado D/P/A/E por fase.
 */
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Button, Stack, Alert, Chip, Divider,
  CircularProgress, LinearProgress, Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material';
import { RecordVoiceOver, VolumeUp } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  iniciarSimulacro, responderRonda, finalizarSimulacro, vozRonda,
  misSesionesSimulacro, resumenSimulacro,
  type SimulacroIniciado, type RondaSimulacro, type ResultadoSimulacro,
} from '../../services/formacion.service';

const DPAE: Record<number, { label: string; color: string }> = {
  4: { label: 'Excelente (E)', color: '#2e7d32' }, 3: { label: 'Adecuado (A)', color: '#1565c0' },
  2: { label: 'En proceso (P)', color: '#e65100' }, 1: { label: 'Deficiente (D)', color: '#c62828' },
};

function hablarNavegador(texto: string) {
  try {
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-DO';
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { /* sin Web Speech: el texto igual se ve en pantalla */ }
}

export default function Simulacro() {
  const [sesion, setSesion] = useState<SimulacroIniciado | null>(null);
  const [idx, setIdx] = useState(0);
  const [feedback, setFeedback] = useState<{ correcta: string; retro: string; acerto: boolean } | null>(null);
  const [resultado, setResultado] = useState<ResultadoSimulacro | null>(null);

  const iniciar = useMutation({
    mutationFn: () => iniciarSimulacro(),
    onSuccess: (d) => { setSesion(d); setIdx(0); setFeedback(null); setResultado(null); reproducir(d.rondas[0]); },
  });
  const responder = useMutation({
    mutationFn: (v: { rondaId: number; opcion: string }) => responderRonda(v.rondaId, v.opcion),
    onSuccess: (r) => setFeedback({ correcta: r.opcion_correcta, retro: r.retroalimentacion, acerto: r.es_correcta }),
  });
  const finalizar = useMutation({
    mutationFn: (sid: number) => finalizarSimulacro(sid),
    onSuccess: (r) => setResultado(r),
  });

  async function reproducir(ronda: RondaSimulacro) {
    try {
      const v = await vozRonda(ronda.id);
      if (v.en_navegador && v.texto) hablarNavegador(v.texto);
    } catch { hablarNavegador(ronda.objecion_texto); }
  }

  const ronda = sesion?.rondas[idx];
  const esUltima = sesion ? idx === sesion.rondas.length - 1 : false;

  function siguiente() {
    if (!sesion) return;
    if (esUltima) { finalizar.mutate(sesion.sesion.id); return; }
    const n = idx + 1;
    setIdx(n); setFeedback(null); reproducir(sesion.rondas[n]);
  }

  // --- Pantalla de resultado ---
  if (resultado) {
    return (
      <Box sx={{ p: 3, maxWidth: 640, mx: 'auto' }}>
        <Typography variant="h5" fontWeight={800} mb={2}>Resultado de la práctica</Typography>
        {(['apertura', 'desarrollo', 'cierre'] as const).map((f) => {
          const v = resultado[f]; const info = DPAE[v];
          return (
            <Card key={f} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1 }}>
              <CardContent sx={{ py: 1.25, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ textTransform: 'capitalize' }}>{f}</Typography>
                <Chip label={info.label} sx={{ bgcolor: info.color, color: '#fff', fontWeight: 700 }} />
              </CardContent>
            </Card>
          );
        })}
        <Alert severity="info" sx={{ my: 2 }}>Calificación general: <strong>{resultado.general}</strong> / 4</Alert>
        <Button variant="contained" startIcon={<RecordVoiceOver />} onClick={() => iniciar.mutate()}>
          Nueva práctica
        </Button>
      </Box>
    );
  }

  // --- Pantalla de inicio (con historial del RM / resumen del equipo) ---
  if (!sesion) {
    return <PantallaInicio iniciar={iniciar} />;
  }

  // --- Pantalla de ronda ---
  return (
    <Box sx={{ p: 3, maxWidth: 640, mx: 'auto' }}>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <Chip color="primary" label={ronda!.fase_more} />
        {ronda!.tecnica_objecion && <Chip variant="outlined" label={ronda!.tecnica_objecion} />}
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" color="text.secondary">
          {sesion.sesion.medico} · {sesion.sesion.estilo}
        </Typography>
      </Stack>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body1" sx={{ flex: 1 }}>«{ronda!.objecion_texto}»</Typography>
            <Button size="small" startIcon={<VolumeUp />} onClick={() => reproducir(ronda!)}>Escuchar</Button>
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={1}>
        {Object.entries(ronda!.opciones).map(([k, v]) => {
          const elegido = feedback && k === ronda!.opcion_seleccionada;
          const esCorrecta = feedback && k === feedback.correcta;
          const color = feedback
            ? (esCorrecta ? 'success' : (elegido ? 'error' : 'inherit'))
            : 'primary';
          return (
            <Button key={k} fullWidth variant={feedback ? 'outlined' : 'contained'} color={color as any}
              disabled={!!feedback || responder.isPending}
              onClick={() => { ronda!.opcion_seleccionada = k; responder.mutate({ rondaId: ronda!.id, opcion: k }); }}
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}>
              <strong style={{ marginRight: 8 }}>{k}.</strong> {v}
            </Button>
          );
        })}
      </Stack>

      {feedback && (
        <>
          <Alert severity={feedback.acerto ? 'success' : 'error'} sx={{ mt: 2 }}>
            {feedback.acerto ? '¡Correcto!' : `La mejor opción era la ${feedback.correcta}.`} {feedback.retro}
          </Alert>
          <Divider sx={{ my: 2 }} />
          <Button variant="contained" onClick={siguiente} disabled={finalizar.isPending}>
            {esUltima ? 'Ver resultado' : 'Siguiente'}
          </Button>
        </>
      )}
      {responder.isPending && <CircularProgress size={20} sx={{ mt: 2 }} />}
    </Box>
  );
}

// Pantalla de arranque: botón "Nueva práctica" + historial (RM) o resumen (roles
// gerenciales). Reutiliza los endpoints /mis-sesiones y /resumen ya existentes.
function PantallaInicio({ iniciar }: {
  iniciar: { isPending: boolean; isError: boolean; mutate: () => void };
}) {
  const rol = useAuthStore((s) => s.rol);
  const esRM = rol === 'REPRESENTANTE_MEDICO';
  const historial = useQuery({ queryKey: ['sim-mis-sesiones'], queryFn: misSesionesSimulacro, enabled: esRM });
  const resumen = useQuery({ queryKey: ['sim-resumen'], queryFn: resumenSimulacro, enabled: !esRM });

  return (
    <Box sx={{ p: 3, maxWidth: 720, mx: 'auto' }}>
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h5" fontWeight={800}>Simulacro de Venta</Typography>
        <Typography color="text.secondary" mb={3}>
          Practica el manejo de objeciones contra un médico simulado por IA, con el modelo MORE.
        </Typography>
        {iniciar.isError && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            No se pudo iniciar. Verifica que haya una conexión de IA de texto activa en Conexiones de IA.
          </Alert>
        )}
        <Button variant="contained" size="large" startIcon={<RecordVoiceOver />}
          disabled={iniciar.isPending} onClick={() => iniciar.mutate()}>
          {iniciar.isPending ? 'Generando escenario…' : 'Nueva práctica'}
        </Button>
        {iniciar.isPending && <LinearProgress sx={{ mt: 2 }} />}
      </Box>

      {esRM ? (
        <Box sx={{ mt: 4 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Mis prácticas</Typography>
          {(historial.data || []).length === 0 ? (
            <Typography color="text.secondary" variant="body2">Aún no has practicado.</Typography>
          ) : (historial.data || []).map((s) => (
            <Card key={s.id} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1 }}>
              <CardContent sx={{ py: 1, display: 'flex', justifyContent: 'space-between' }}>
                <span>{s.medico} · {s.estilo}</span>
                <Chip size="small" label={s.finalizada ? 'Finalizada' : 'En curso'}
                  color={s.finalizada ? 'success' : 'default'} />
              </CardContent>
            </Card>
          ))}
        </Box>
      ) : (
        <Box sx={{ mt: 4 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Resumen del equipo</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>RM</TableCell>
                <TableCell align="right">Prácticas</TableCell>
                <TableCell align="right">Última general</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(resumen.data || []).map((r) => (
                <TableRow key={r.rm_id}>
                  <TableCell>RM #{r.rm_id}</TableCell>
                  <TableCell align="right">{r.practicas}</TableCell>
                  <TableCell align="right">{r.ultima_general ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Box>
  );
}
```

- [ ] **Step 2: Register the route** (`frontend/src/App.tsx`)

Tras `const CalendarioCoaching = lazyWithReload(() => import('./pages/formacion/CalendarioCoaching'));` añadir:
```tsx
const Simulacro = lazyWithReload(() => import('./pages/formacion/Simulacro'));
```
Tras la `<Route path="formacion/calendario" ... />` añadir:
```tsx
<Route path="formacion/simulacro" element={<ProtectedRoute allowedRoles={['ADMIN','REPRESENTANTE_MEDICO','GERENTE_PRODUCTIVIDAD','CAPACITACION','GERENTE_DISTRITO','PRESIDENCIA','GERENTE_MEDICO']}><Simulacro /></ProtectedRoute>} />
```

- [ ] **Step 3: Add the nav item** (`frontend/src/components/layout/Sidebar.tsx`, sección "Formación", tras "Calendario de Coaching")

Importar un ícono en el bloque `@mui/icons-material` (añadir `RecordVoiceOver,`). Luego el ítem:
```tsx
{ label: 'Simulacro de Venta', path: '/formacion/simulacro', icon: <RecordVoiceOver />, roles: ['ADMIN', 'REPRESENTANTE_MEDICO', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_DISTRITO', 'PRESIDENCIA', 'GERENTE_MEDICO'] },
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vite build 2>&1 | tail -3`
Expected: sin errores; build OK; se emite el chunk `Simulacro-*.js`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formacion/Simulacro.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(formacion) Simulacro: vista frontend (sesion guiada por rondas + voz)"
```

---

### Task 10: Verificación en vivo y cierre

**Files:** ninguno (verificación).

- [ ] **Step 1:** Backend arriba (`run_in_background`) + frontend `npm run dev`; JWT ADMIN/RM inyectado en `localStorage` (ver `[[preview-levanta-edicion-sqlserver]]`). Requiere una **conexión de IA de texto activa** (Anthropic) para `iniciar` — si en dev no la hay, probar `iniciar` con la capa mockeada NO aplica en vivo; documentar que en prod la conexión ya existe.

- [ ] **Step 2: Smoke por API** con token: `POST /formacion/simulacro/iniciar {}` como RM → 200 con `sesion`+`rondas` (o 503 si no hay conexión IA en dev — esperado, no es bug); `POST /ronda/{id}/responder {opcion}` → revela correcta; `POST /sesion/{id}/finalizar` → D/P/A/E. Un token de otro RM sobre la sesión → 403.

- [ ] **Step 3: Navegador** (edición postgres): abrir `/formacion/simulacro`, "Nueva práctica", escuchar la objeción (Web Speech si no hay ElevenLabs), responder las 3 rondas, ver el resultado. Sin errores de consola nuevos.

- [ ] **Step 4:** Suite completa verde (`pytest -q`) y `git status` limpio.

- [ ] **Step 5:** Handoff de deploy al usuario (push + `git pull && docker compose --profile with-db up -d --build`). **No** auto-push sin confirmación. Nota: sin seed nuevo; requiere conexión de IA de texto activa en prod (ya configurada para Exámenes).
