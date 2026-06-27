# Módulo de Exámenes — Fase 2 (Tomar y Corregir) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** Backend del ciclo central: gestionar preguntas/opciones, asignar exámenes a evaluados (RM/Gerente), tomar un intento (aleatorización Fisher-Yates), responder, entregar y corregir automáticamente con reporte.

**Architecture:** Extiende el módulo `exam` de Fase 1 (esquema + modelos + `examen_service` + router `/examenes` ya existen). Añade lógica en servicios y endpoints siguiendo los patrones del proyecto. Pruebas unitarias con `MagicMock`/`monkeypatch`; lógica pura (shuffle, corrección) testeada de forma determinista.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, pymssql/SQL Server, Pydantic v2, pytest.

**Spec:** `docs/superpowers/specs/2026-06-26-modulo-examenes-design.md` (§3, §7 take-exam, §9 corrección, RN-01..RN-09)

## Global Constraints

- Modelos SQLAlchemy 2.0 `Mapped`/`mapped_column`. Migraciones idempotentes generadas con `./venv/Scripts/alembic.exe revision -m "..."`.
- Backend Python/Alembic vía `./venv/Scripts/python.exe` / `./venv/Scripts/alembic.exe` desde `backend/`.
- Router: constantes RBAC a nivel módulo como en `lsii.py`/`examenes.py`. `RequireCapacitacion = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION))` ya existe en `examenes.py`.
- Para endpoints de evaluado: el usuario logueado se resuelve a su evaluado vía `Usuario.rm_id` (tipo RM) o `Usuario.gerente_id` (tipo GERENTE). Un evaluado solo ve/usa SUS asignaciones (403 si no coincide).
- Timestamps `datetime.now(timezone.utc)`. Logs `loguru`. `== True` es la convención del proyecto en filtros.
- Aleatorización: algoritmo Fisher-Yates. La corrección compara contra `PreguntaOpcion.es_correcta` (verdad original), traduciendo con `mapa_opciones_json` (RN-05).
- Reglas: RN-01 (borrador no se toma), RN-02 (publicar ≥1 pregunta — ya implementado), RN-03 (corrección automática al entregar), RN-06 (al agotar intentos_max se bloquea), RN-07 (siempre hay retroalimentación), RN-09 (historial guarda todos los intentos; ranking usa el último).
- Migración head actual de Fase 1: la revisión `ab0868ac76db`. Las nuevas migraciones chain sobre el head vigente.
- Tests: `./venv/Scripts/python.exe -m pytest -q` desde `backend/`. Todos deben pasar antes de cada commit.

## Estructura de archivos (Fase 2)

| Archivo | Responsabilidad |
|---------|-----------------|
| `app/models/exam_models.py` (modificar) | Endurecer CHECK `evaluado_tipo`; agregar relationships en Fact tables |
| `alembic/versions/*` (crear) | Migración: re-crear CHECK con coherencia `evaluado_tipo` |
| `app/schemas/examenes.py` (modificar) | Schemas de Pregunta/Opcion/Asignacion/Intento/Respuesta/Reporte |
| `app/services/examen_service.py` (modificar) | CRUD preguntas/opciones, asignar |
| `app/services/examen_intento_service.py` (crear) | Fisher-Yates, preparar/responder/entregar/corregir, reporte |
| `app/api/v1/routers/examenes.py` (modificar) | Endpoints de preguntas, asignar, iniciar/responder/entregar/reporte/mis-pendientes |
| `tests/test_examen_service.py` (modificar) | Tests CRUD + asignar |
| `tests/test_examen_intento_service.py` (crear) | Tests shuffle/corrección/preparar |

---

### Task 1: Endurecer CHECK `evaluado_tipo` + relationships en Fact tables

**Files:**
- Modify: `app/models/exam_models.py` (CheckConstraint de `AsignacionExamen`; relationships)
- Create: `alembic/versions/<rev>_exam_check_evaluado_tipo.py`

**Interfaces:**
- Produces: invariante DB que `evaluado_tipo='RM'` ⇒ solo `evaluado_rm_id` set; `='GERENTE'` ⇒ solo `evaluado_gerente_id` set. Relationships: `AsignacionExamen.intentos`, `IntentoExamen.respuestas`.

- [ ] **Step 1: Endurecer el CheckConstraint en el modelo**

En `app/models/exam_models.py`, en `AsignacionExamen.__table_args__`, reemplazar la expresión del CheckConstraint (nombre `CK_AsignacionExamen_evaluado_unico`) por:

```python
        CheckConstraint(
            "(evaluado_tipo = 'RM' AND evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
            "(evaluado_tipo = 'GERENTE' AND evaluado_gerente_id IS NOT NULL AND evaluado_rm_id IS NULL)",
            name="CK_AsignacionExamen_evaluado_coherente",
        ),
```

- [ ] **Step 2: Agregar relationships**

En `app/models/exam_models.py`:
- En `AsignacionExamen`, agregar:
```python
    intentos: Mapped[list["IntentoExamen"]] = relationship(
        "IntentoExamen", back_populates="asignacion", cascade="all, delete-orphan")
```
- En `IntentoExamen`, agregar `asignacion_id` ya existe; agregar:
```python
    asignacion: Mapped["AsignacionExamen"] = relationship("AsignacionExamen", back_populates="intentos")
    respuestas: Mapped[list["IntentoRespuesta"]] = relationship(
        "IntentoRespuesta", back_populates="intento", cascade="all, delete-orphan")
```
- En `IntentoRespuesta`, agregar:
```python
    intento: Mapped["IntentoExamen"] = relationship("IntentoExamen", back_populates="respuestas")
```

- [ ] **Step 3: Verificar import de modelos**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.models import exam_models; print('OK')"`
Expected: `OK`.

- [ ] **Step 4: Generar y escribir la migración**

Run: `cd backend && ./venv/Scripts/alembic.exe revision -m "exam check evaluado_tipo coherente"`
Escribir cuerpo (idempotente): dropear el CHECK viejo si existe y crear el nuevo, en `FactAsignacionExamen`. (Las tablas están vacías, sin riesgo de violar el nuevo CHECK.)

```python
from alembic import op
from sqlalchemy import text
# revision/down_revision generados por alembic

def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_AsignacionExamen_evaluado_unico' "
        "AND parent_object_id=OBJECT_ID('exam.FactAsignacionExamen')) "
        "ALTER TABLE [exam].[FactAsignacionExamen] DROP CONSTRAINT [CK_AsignacionExamen_evaluado_unico]"))
    conn.execute(text(
        "IF NOT EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_AsignacionExamen_evaluado_coherente' "
        "AND parent_object_id=OBJECT_ID('exam.FactAsignacionExamen')) "
        "ALTER TABLE [exam].[FactAsignacionExamen] ADD CONSTRAINT CK_AsignacionExamen_evaluado_coherente "
        "CHECK ((evaluado_tipo='RM' AND evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
        "(evaluado_tipo='GERENTE' AND evaluado_gerente_id IS NOT NULL AND evaluado_rm_id IS NULL))"))

def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "IF EXISTS (SELECT 1 FROM sys.check_constraints WHERE name='CK_AsignacionExamen_evaluado_coherente' "
        "AND parent_object_id=OBJECT_ID('exam.FactAsignacionExamen')) "
        "ALTER TABLE [exam].[FactAsignacionExamen] DROP CONSTRAINT [CK_AsignacionExamen_evaluado_coherente]"))
    conn.execute(text(
        "ALTER TABLE [exam].[FactAsignacionExamen] ADD CONSTRAINT CK_AsignacionExamen_evaluado_unico "
        "CHECK ((evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
        "(evaluado_rm_id IS NULL AND evaluado_gerente_id IS NOT NULL))"))
```

- [ ] **Step 5: Aplicar y verificar**

Run: `cd backend && ./venv/Scripts/alembic.exe upgrade head`
Verificar el constraint nuevo existe:
```bash
cd backend && ./venv/Scripts/python.exe -c "from app.db.database import engine; from sqlalchemy import text; c=engine.connect(); print(c.execute(text(\"SELECT name FROM sys.check_constraints WHERE parent_object_id=OBJECT_ID('exam.FactAsignacionExamen')\")).fetchall())"
```
Expected: incluye `CK_AsignacionExamen_evaluado_coherente`.

- [ ] **Step 6: Suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q` → todos pasan.
```bash
git add backend/app/models/exam_models.py backend/alembic/
git commit -m "feat(examenes): endurecer CHECK evaluado_tipo + relationships en fact tables"
```

---

### Task 2: Schemas de Fase 2

**Files:**
- Modify: `app/schemas/examenes.py`
- Test: (cubierto al usarlos en tasks siguientes)

**Interfaces:**
- Produces: `PreguntaOpcionCrear`, `PreguntaCrear`, `PreguntaResponse`, `OpcionPublica` (sin `es_correcta`), `PreguntaPublica` (sin marcar correcta), `AsignacionCrear`, `AsignacionResponse`, `RespuestaEnviar`, `IntentoResumen`, `ReporteRespuesta`, `ReporteIntento`.

- [ ] **Step 1: Agregar los schemas**

Agregar a `app/schemas/examenes.py`:

```python
from pydantic import BaseModel, ConfigDict, Field
from datetime import datetime, date


class PreguntaOpcionCrear(BaseModel):
    texto_opcion: str = Field(min_length=1)
    es_correcta: bool = False


class PreguntaCrear(BaseModel):
    tipo: str = Field(default="multi")  # multi | caso
    escenario: str | None = None
    texto: str = Field(min_length=1)
    explicacion: str | None = None
    opciones: list[PreguntaOpcionCrear] = Field(min_length=4, max_length=4)


class OpcionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    texto_opcion: str
    indice_original: int
    es_correcta: bool


class PreguntaResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    examen_id: int
    tipo: str
    escenario: str | None
    texto: str
    explicacion: str | None
    orden: int


class AsignacionCrear(BaseModel):
    examen_id: int
    evaluados: list["EvaluadoRef"] = Field(min_length=1)
    fecha_limite: date | None = None
    intentos_max: int | None = Field(default=None, ge=1)
    notif_activa: bool = False


class EvaluadoRef(BaseModel):
    tipo: str  # RM | GERENTE
    id: int


class AsignacionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    examen_id: int
    evaluado_tipo: str
    evaluado_rm_id: int | None
    evaluado_gerente_id: int | None
    fecha_limite: datetime | None
    intentos_max: int | None
    intentos_usados: int
    estado: str


class OpcionPresentada(BaseModel):
    indice_presentado: int
    texto_opcion: str


class PreguntaPresentada(BaseModel):
    pregunta_id: int
    tipo: str
    escenario: str | None
    texto: str
    opciones: list[OpcionPresentada]


class IntentoIniciado(BaseModel):
    intento_id: int
    examen_nombre: str
    tiempo_limite_min: int | None
    preguntas: list[PreguntaPresentada]


class RespuestaEnviar(BaseModel):
    pregunta_id: int
    indice_presentado: int


class ReporteRespuesta(BaseModel):
    pregunta_texto: str
    explicacion: str | None
    indice_elegido_presentado: int | None
    texto_elegido: str | None
    texto_correcto: str
    es_correcta: bool


class ReporteIntento(BaseModel):
    intento_id: int
    examen_nombre: str
    producto: str | None
    score: float
    aprobado: bool
    nota_minima: int
    correctas: int
    total: int
    fecha_fin: datetime | None
    respuestas: list[ReporteRespuesta]
```

- [ ] **Step 2: Verificar import**

Run: `cd backend && ./venv/Scripts/python.exe -c "import app.schemas.examenes as s; print('OK', hasattr(s,'ReporteIntento'))"`
Expected: `OK True`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/examenes.py
git commit -m "feat(examenes): schemas de preguntas, asignacion, intento y reporte"
```

---

### Task 3: CRUD de preguntas/opciones

**Files:**
- Modify: `app/services/examen_service.py`
- Modify: `app/api/v1/routers/examenes.py`
- Test: `tests/test_examen_service.py`

**Interfaces:**
- Produces:
  - `examen_service.agregar_pregunta(db, examen_id, datos: PreguntaCrear) -> Pregunta` — valida examen en `borrador` (RN-01) y exactamente 1 opción correcta; asigna `orden` consecutivo y `indice_original` 0..3.
  - `examen_service.eliminar_pregunta(db, pregunta_id) -> None`
  - `examen_service.reordenar_preguntas(db, examen_id, orden_ids: list[int]) -> None`
  - Endpoints: `POST /examenes/{id}/preguntas`, `DELETE /examenes/{id}/preguntas/{pid}`, `PUT /examenes/{id}/preguntas/orden`.

- [ ] **Step 1: Test (lógica de validación)**

Agregar a `tests/test_examen_service.py`:

```python
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.services import examen_service
from app.schemas.examenes import PreguntaCrear, PreguntaOpcionCrear


def _pcrear(n_correctas=1):
    ops = [PreguntaOpcionCrear(texto_opcion=f"o{i}", es_correcta=(i < n_correctas)) for i in range(4)]
    return PreguntaCrear(texto="¿?", opciones=ops)


def test_agregar_pregunta_requiere_examen_borrador(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo", preguntas=[])
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear())


def test_agregar_pregunta_exige_una_correcta(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador", preguntas=[])
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear(n_correctas=0))
    with pytest.raises(ValueError):
        examen_service.agregar_pregunta(db, 1, _pcrear(n_correctas=2))
```

- [ ] **Step 2: Verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k agregar_pregunta -q`
Expected: FAIL (`agregar_pregunta` no existe).

- [ ] **Step 3: Implementar en `examen_service.py`**

```python
from app.models.exam_models import Examen, Pregunta, PreguntaOpcion
from app.schemas.examenes import PreguntaCrear


def agregar_pregunta(db: Session, examen_id: int, datos: PreguntaCrear) -> Pregunta:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "borrador":
        raise ValueError("Solo se editan preguntas de un examen en borrador")  # RN-01
    n_correctas = sum(1 for o in datos.opciones if o.es_correcta)
    if n_correctas != 1:
        raise ValueError("La pregunta debe tener exactamente 1 opción correcta")
    orden = len(examen.preguntas)
    pregunta = Pregunta(examen_id=examen_id, tipo=datos.tipo, escenario=datos.escenario,
                        texto=datos.texto, explicacion=datos.explicacion, orden=orden)
    for idx, op in enumerate(datos.opciones):
        pregunta.opciones.append(PreguntaOpcion(
            texto_opcion=op.texto_opcion, indice_original=idx, es_correcta=op.es_correcta))
    db.add(pregunta)
    db.commit()
    db.refresh(pregunta)
    return pregunta


def eliminar_pregunta(db: Session, pregunta_id: int) -> None:
    pregunta = db.query(Pregunta).filter(Pregunta.id == pregunta_id).first()
    if pregunta is None:
        raise ValueError("Pregunta no encontrada")
    db.delete(pregunta)
    db.commit()


def reordenar_preguntas(db: Session, examen_id: int, orden_ids: list[int]) -> None:
    for nuevo_orden, pid in enumerate(orden_ids):
        db.query(Pregunta).filter(
            Pregunta.id == pid, Pregunta.examen_id == examen_id
        ).update({"orden": nuevo_orden})
    db.commit()
```

- [ ] **Step 4: Verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k agregar_pregunta -q`
Expected: PASS.

- [ ] **Step 5: Endpoints**

En `app/api/v1/routers/examenes.py`, agregar (usar `RequireCapacitacion`, mapear `ValueError`→400):

```python
from app.schemas.examenes import PreguntaCrear, PreguntaResponse

@router.post("/{examen_id}/preguntas", response_model=PreguntaResponse, status_code=201)
def agregar_pregunta(examen_id: int, datos: PreguntaCrear, db: Session = Depends(get_db),
                     current_user=RequireCapacitacion):
    try:
        return examen_service.agregar_pregunta(db, examen_id, datos)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.delete("/{examen_id}/preguntas/{pregunta_id}", status_code=204)
def eliminar_pregunta(examen_id: int, pregunta_id: int, db: Session = Depends(get_db),
                      current_user=RequireCapacitacion):
    try:
        examen_service.eliminar_pregunta(db, pregunta_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.put("/{examen_id}/preguntas/orden", status_code=204)
def reordenar(examen_id: int, orden_ids: list[int], db: Session = Depends(get_db),
              current_user=RequireCapacitacion):
    examen_service.reordenar_preguntas(db, examen_id, orden_ids)
```

- [ ] **Step 6: Verificar app + suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print('OK')"` y `./venv/Scripts/python.exe -m pytest -q`.
```bash
git add backend/app/services/examen_service.py backend/app/api/v1/routers/examenes.py backend/tests/test_examen_service.py
git commit -m "feat(examenes): CRUD de preguntas/opciones (RN-01, 1 correcta, reorden)"
```

---

### Task 4: Asignar examen a evaluados

**Files:**
- Modify: `app/services/examen_service.py`, `app/api/v1/routers/examenes.py`
- Test: `tests/test_examen_service.py`

**Interfaces:**
- Produces: `examen_service.asignar_examen(db, examen_id, evaluados: list[EvaluadoRef], fecha_limite, intentos_max, notif_activa) -> list[AsignacionExamen]` — valida examen `activo`; crea una `AsignacionExamen` por evaluado con `evaluado_tipo` y el FK correspondiente. Endpoint `POST /examenes/{id}/asignar`.

- [ ] **Step 1: Test**

```python
from app.schemas.examenes import EvaluadoRef

def test_asignar_requiere_examen_activo(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.asignar_examen(db, 1, [EvaluadoRef(tipo="RM", id=5)], None, None, False)

def test_asignar_crea_una_por_evaluado(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="activo")
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    res = examen_service.asignar_examen(
        db, 1, [EvaluadoRef(tipo="RM", id=5), EvaluadoRef(tipo="GERENTE", id=9)], None, None, False)
    assert len(res) == 2
    assert res[0].evaluado_tipo == "RM" and res[0].evaluado_rm_id == 5
    assert res[1].evaluado_tipo == "GERENTE" and res[1].evaluado_gerente_id == 9
```

- [ ] **Step 2: Verificar falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k asignar -q` → FAIL.

- [ ] **Step 3: Implementar**

```python
from app.models.exam_models import AsignacionExamen
from app.schemas.examenes import EvaluadoRef

def asignar_examen(db: Session, examen_id: int, evaluados: list[EvaluadoRef],
                   fecha_limite, intentos_max, notif_activa) -> list[AsignacionExamen]:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "activo":
        raise ValueError("Solo se asigna un examen activo (publicado)")
    creadas = []
    for ev in evaluados:
        if ev.tipo not in ("RM", "GERENTE"):
            raise ValueError(f"Tipo de evaluado inválido: {ev.tipo}")
        asig = AsignacionExamen(
            examen_id=examen_id, evaluado_tipo=ev.tipo,
            evaluado_rm_id=ev.id if ev.tipo == "RM" else None,
            evaluado_gerente_id=ev.id if ev.tipo == "GERENTE" else None,
            fecha_limite=fecha_limite, intentos_max=intentos_max,
            intentos_usados=0, estado="pendiente", notif_activa=notif_activa)
        db.add(asig)
        creadas.append(asig)
    db.commit()
    for a in creadas:
        db.refresh(a)
    return creadas
```

- [ ] **Step 4: Verificar pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k asignar -q` → PASS.

- [ ] **Step 5: Endpoint**

```python
from app.schemas.examenes import AsignacionCrear, AsignacionResponse

@router.post("/{examen_id}/asignar", response_model=list[AsignacionResponse], status_code=201)
def asignar(examen_id: int, datos: AsignacionCrear, db: Session = Depends(get_db),
            current_user=RequireCapacitacion):
    try:
        return examen_service.asignar_examen(
            db, examen_id, datos.evaluados, datos.fecha_limite, datos.intentos_max, datos.notif_activa)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

- [ ] **Step 6: Suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`.
```bash
git add backend/app/services/examen_service.py backend/app/api/v1/routers/examenes.py backend/tests/test_examen_service.py
git commit -m "feat(examenes): asignar examen a evaluados RM/Gerente"
```

---

### Task 5: Fisher-Yates + preparar intento

**Files:**
- Create: `app/services/examen_intento_service.py`
- Test: `tests/test_examen_intento_service.py`

**Interfaces:**
- Produces:
  - `examen_intento_service.barajar(items: list, rng) -> list` — Fisher-Yates puro, determinista con `rng` inyectado.
  - `examen_intento_service.preparar_intento(db, asignacion, evaluado_tipo, evaluado_id, contexto: dict, rng=None) -> IntentoExamen` — valida asignación tomable (estado, fecha_limite, intentos_max RN-06); aplica barajado a preguntas (si `rand_preguntas`) y opciones (si `rand_opciones`); persiste `orden_preguntas_json` y crea `IntentoExamen`. Devuelve el intento con `_preguntas_presentadas` (estructura para el schema `PreguntaPresentada`) y guarda el mapa de opciones presentado→original por pregunta (en memoria del intento, se persiste al responder).

- [ ] **Step 1: Test del shuffle determinista**

Crear `tests/test_examen_intento_service.py`:

```python
import random
from app.services import examen_intento_service as svc

def test_barajar_es_permutacion_determinista():
    rng = random.Random(42)
    original = [1, 2, 3, 4, 5]
    barajado = svc.barajar(list(original), rng)
    assert sorted(barajado) == original   # es permutación
    rng2 = random.Random(42)
    assert svc.barajar(list(original), rng2) == barajado  # determinista con misma semilla

def test_barajar_sin_elementos():
    assert svc.barajar([], random.Random(1)) == []
```

- [ ] **Step 2: Verificar falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_intento_service.py -k barajar -q` → FAIL.

- [ ] **Step 3: Implementar `barajar` (Fisher-Yates)**

Crear `app/services/examen_intento_service.py`:

```python
"""SCGCPR — Servicio de intentos de examen: aleatorización, corrección, reporte."""
import json
import random
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import (
    Examen, Pregunta, AsignacionExamen, IntentoExamen, IntentoRespuesta,
)


def barajar(items: list, rng: random.Random) -> list:
    """Fisher-Yates in-place; retorna la misma lista barajada."""
    for i in range(len(items) - 1, 0, -1):
        j = rng.randint(0, i)
        items[i], items[j] = items[j], items[i]
    return items
```

- [ ] **Step 4: Verificar pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_intento_service.py -k barajar -q` → PASS.

- [ ] **Step 5: Test de `preparar_intento` (validaciones)**

```python
import pytest
from types import SimpleNamespace
from unittest.mock import MagicMock

def _asig(estado="pendiente", intentos_max=None, intentos_usados=0, fecha_limite=None):
    return SimpleNamespace(id=1, estado=estado, intentos_max=intentos_max,
                           intentos_usados=intentos_usados, fecha_limite=fecha_limite,
                           examen_id=7, evaluado_tipo="RM", evaluado_rm_id=5, evaluado_gerente_id=None)

def test_preparar_intento_bloquea_si_agoto_intentos(monkeypatch):
    db = MagicMock()
    asig = _asig(intentos_max=2, intentos_usados=2)
    with pytest.raises(ValueError):
        svc.preparar_intento(db, asig, "RM", 5, {})
```

- [ ] **Step 6: Verificar falla, implementar `preparar_intento`, verificar pasa**

Agregar a `examen_intento_service.py`:

```python
def preparar_intento(db, asignacion, evaluado_tipo, evaluado_id, contexto, rng=None):
    if asignacion.estado not in ("pendiente",):
        raise ValueError("La asignación no está disponible para un nuevo intento")  # RN-06
    if asignacion.intentos_max is not None and asignacion.intentos_usados >= asignacion.intentos_max:
        raise ValueError("Se agotaron los intentos permitidos")  # RN-06
    if asignacion.fecha_limite is not None and datetime.now(timezone.utc).date() > asignacion.fecha_limite:
        raise ValueError("La asignación está vencida")
    rng = rng or random.Random()
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    if examen is None or examen.estado != "activo":
        raise ValueError("El examen no está disponible")  # RN-01
    preguntas = list(db.query(Pregunta).filter(
        Pregunta.examen_id == examen.id, Pregunta.activo == True).order_by(Pregunta.orden).all())
    if examen.rand_preguntas:
        barajar(preguntas, rng)
    orden_ids = [p.id for p in preguntas]
    intento = IntentoExamen(
        asignacion_id=asignacion.id, evaluado_tipo=evaluado_tipo,
        evaluado_rm_id=evaluado_id if evaluado_tipo == "RM" else None,
        evaluado_gerente_id=evaluado_id if evaluado_tipo == "GERENTE" else None,
        fecha_inicio=datetime.now(timezone.utc), orden_preguntas_json=json.dumps(orden_ids),
        user_agent=contexto.get("user_agent"), device_type=contexto.get("device_type"),
        plataforma=contexto.get("plataforma"), ip_cliente=contexto.get("ip_cliente"))
    db.add(intento)
    db.commit()
    db.refresh(intento)
    # Estructura presentada (opciones barajadas si aplica) — el mapa se reconstruye al entregar
    presentadas = []
    for p in preguntas:
        ops = list(p.opciones)
        if examen.rand_opciones:
            barajar(ops, rng)
        presentadas.append({
            "pregunta_id": p.id, "tipo": p.tipo, "escenario": p.escenario, "texto": p.texto,
            "opciones": [{"indice_presentado": i, "texto_opcion": o.texto_opcion,
                          "_opcion_id": o.id, "_indice_original": o.indice_original}
                         for i, o in enumerate(ops)]})
    intento._preguntas_presentadas = presentadas  # transitorio para el router
    return intento
```

Run focused tests → PASS.

- [ ] **Step 7: Suite + commit**

```bash
git add backend/app/services/examen_intento_service.py backend/tests/test_examen_intento_service.py
git commit -m "feat(examenes): Fisher-Yates + preparar intento (validaciones RN-06/RN-01)"
```

---

### Task 6: Responder + entregar + corregir

**Files:**
- Modify: `app/services/examen_intento_service.py`
- Test: `tests/test_examen_intento_service.py`

**Interfaces:**
- Produces:
  - `registrar_respuesta(db, intento_id, pregunta_id, opcion_id, indice_presentado, indice_original, mapa: dict) -> IntentoRespuesta`
  - `calcular_score(correctas: int, total: int) -> float` — `round(correctas/total*100, 2)`; `0` si total 0.
  - `entregar_intento(db, intento_id) -> IntentoExamen` — anti-doble-entrega (si `fecha_fin` ya set → ValueError); corrige cada `IntentoRespuesta` (es_correcta = la opción elegida es la correcta original); calcula `score`/`aprobado` (vs `examen.nota_minima`); set `fecha_fin`, `tiempo_usado_seg`; ++`intentos_usados`; cierra asignación si aprobó o agotó intentos (RN-06); commit.

- [ ] **Step 1: Test de `calcular_score`**

```python
def test_calcular_score():
    assert svc.calcular_score(8, 10) == 80.0
    assert svc.calcular_score(0, 0) == 0.0
    assert svc.calcular_score(1, 3) == 33.33
```

- [ ] **Step 2: Verificar falla, implementar, verificar pasa**

```python
def calcular_score(correctas: int, total: int) -> float:
    if total <= 0:
        return 0.0
    return round(correctas / total * 100, 2)
```

- [ ] **Step 3: Test de anti-doble-entrega**

```python
def test_entregar_dos_veces_falla(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, fecha_fin=datetime.now(timezone.utc))
    db.query.return_value.filter.return_value.first.return_value = intento
    with pytest.raises(ValueError):
        svc.entregar_intento(db, 1)
```
(import `from datetime import datetime, timezone`)

- [ ] **Step 4: Implementar `registrar_respuesta` y `entregar_intento`**

```python
def registrar_respuesta(db, intento_id, pregunta_id, opcion_id, indice_presentado,
                        indice_original, mapa):
    resp = IntentoRespuesta(
        intento_id=intento_id, pregunta_id=pregunta_id, opcion_elegida_id=opcion_id,
        indice_opcion_presentada=indice_presentado, indice_original_elegido=indice_original,
        mapa_opciones_json=json.dumps(mapa), fecha_respuesta=datetime.now(timezone.utc))
    db.add(resp)
    db.commit()
    db.refresh(resp)
    return resp


def entregar_intento(db, intento_id):
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    if intento.fecha_fin is not None:
        raise ValueError("El intento ya fue entregado")  # anti-doble-entrega
    asignacion = db.query(AsignacionExamen).filter(
        AsignacionExamen.id == intento.asignacion_id).first()
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    respuestas = list(db.query(IntentoRespuesta).filter(
        IntentoRespuesta.intento_id == intento_id).all())
    total = db.query(Pregunta).filter(Pregunta.examen_id == examen.id,
                                      Pregunta.activo == True).count()
    correctas = 0
    for r in respuestas:
        opcion = db.query(PreguntaOpcion).filter(PreguntaOpcion.id == r.opcion_elegida_id).first()
        r.es_correcta = bool(opcion and opcion.es_correcta)
        if r.es_correcta:
            correctas += 1
    intento.score = calcular_score(correctas, total)
    intento.aprobado = intento.score >= examen.nota_minima
    intento.fecha_fin = datetime.now(timezone.utc)
    if intento.fecha_inicio is not None:
        intento.tiempo_usado_seg = int((intento.fecha_fin - intento.fecha_inicio).total_seconds())
    asignacion.intentos_usados += 1
    if intento.aprobado or (asignacion.intentos_max is not None
                            and asignacion.intentos_usados >= asignacion.intentos_max):
        asignacion.estado = "completado"  # RN-06
    db.commit()
    db.refresh(intento)
    return intento
```
(import `from app.models.exam_models import PreguntaOpcion`)

Run focused tests → PASS.

- [ ] **Step 5: Suite + commit**

```bash
git add backend/app/services/examen_intento_service.py backend/tests/test_examen_intento_service.py
git commit -m "feat(examenes): responder + entregar + correccion automatica (RN-03/RN-06)"
```

---

### Task 7: Endpoints de evaluado (iniciar/responder/entregar/reporte/pendientes)

**Files:**
- Modify: `app/api/v1/routers/examenes.py`, `app/services/examen_intento_service.py`
- Test: smoke de arranque

**Interfaces:**
- Consumes: `examen_intento_service.preparar_intento/registrar_respuesta/entregar_intento`; resolución del evaluado desde `current_user` (`Usuario.rm_id`/`Usuario.gerente_id`).
- Produces: `examen_intento_service.generar_reporte(db, intento_id) -> dict` (estructura `ReporteIntento`); helper `_resolver_evaluado(current_user) -> tuple[str,int]`; endpoints `GET /examenes/mis-pendientes`, `POST /examenes/{id}/iniciar`, `POST /intentos/{id}/responder`, `POST /intentos/{id}/entregar`, `GET /intentos/{id}/reporte`, `GET /examenes/mi-historial`.

- [ ] **Step 1: Helper de resolución de evaluado + reporte**

En `examen_intento_service.py`:

```python
def generar_reporte(db, intento_id) -> dict:
    intento = db.query(IntentoExamen).filter(IntentoExamen.id == intento_id).first()
    if intento is None:
        raise ValueError("Intento no encontrado")
    asignacion = db.query(AsignacionExamen).filter(AsignacionExamen.id == intento.asignacion_id).first()
    examen = db.query(Examen).filter(Examen.id == asignacion.examen_id).first()
    respuestas = list(db.query(IntentoRespuesta).filter(
        IntentoRespuesta.intento_id == intento_id).all())
    total = db.query(Pregunta).filter(Pregunta.examen_id == examen.id, Pregunta.activo == True).count()
    detalle = []
    correctas = 0
    for r in respuestas:
        pregunta = db.query(Pregunta).filter(Pregunta.id == r.pregunta_id).first()
        elegida = db.query(PreguntaOpcion).filter(PreguntaOpcion.id == r.opcion_elegida_id).first() if r.opcion_elegida_id else None
        correcta = db.query(PreguntaOpcion).filter(
            PreguntaOpcion.pregunta_id == r.pregunta_id, PreguntaOpcion.es_correcta == True).first()
        if r.es_correcta:
            correctas += 1
        detalle.append({
            "pregunta_texto": pregunta.texto, "explicacion": pregunta.explicacion,
            "indice_elegido_presentado": r.indice_opcion_presentada,
            "texto_elegido": elegida.texto_opcion if elegida else None,
            "texto_correcto": correcta.texto_opcion if correcta else "",
            "es_correcta": bool(r.es_correcta)})
    return {"intento_id": intento.id, "examen_nombre": examen.nombre, "producto": examen.producto,
            "score": float(intento.score or 0), "aprobado": bool(intento.aprobado),
            "nota_minima": examen.nota_minima, "correctas": correctas, "total": total,
            "fecha_fin": intento.fecha_fin, "respuestas": detalle}
```

En `examenes.py`, helper (usa el usuario logueado):

```python
def _resolver_evaluado(current_user):
    if getattr(current_user, "rm_id", None):
        return ("RM", current_user.rm_id)
    if getattr(current_user, "gerente_id", None):
        return ("GERENTE", current_user.gerente_id)
    raise HTTPException(status_code=403, detail="El usuario no es un evaluado (RM/Gerente)")
```

- [ ] **Step 2: Endpoints de evaluado**

En `examenes.py` (auth: `RequireAnyAuth = Depends(get_current_active_user)` — verificar el nombre real en `deps.py`/`lsii.py`):

```python
from fastapi import Request
from app.schemas.examenes import IntentoIniciado, RespuestaEnviar, ReporteIntento, AsignacionResponse
from app.services import examen_intento_service as intento_svc

@router.get("/mis-pendientes", response_model=list[AsignacionResponse])
def mis_pendientes(db: Session = Depends(get_db), current_user=Depends(get_current_active_user)):
    tipo, eid = _resolver_evaluado(current_user)
    return intento_svc.listar_pendientes(db, tipo, eid)

@router.post("/{examen_id}/iniciar", response_model=IntentoIniciado)
def iniciar(examen_id: int, request: Request, db: Session = Depends(get_db),
            current_user=Depends(get_current_active_user)):
    tipo, eid = _resolver_evaluado(current_user)
    try:
        return intento_svc.iniciar_para_evaluado(db, examen_id, tipo, eid, _contexto(request))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

Donde `_contexto(request)` arma `{"user_agent","device_type","plataforma","ip_cliente"}` desde headers. Definir `listar_pendientes` e `iniciar_para_evaluado` en el service (resuelven la asignación pendiente del evaluado, validan scope 403, y construyen el `IntentoIniciado` a partir de `preparar_intento`, mapeando `_preguntas_presentadas` a `PreguntaPresentada` sin exponer `_opcion_id`/`_indice_original`). Análogamente `responder` (llama `registrar_respuesta` reconstruyendo el mapa desde el intento), `entregar` (llama `entregar_intento` + `generar_reporte`), `reporte` (`generar_reporte`, con verificación de que el intento pertenece al evaluado), `mi-historial`.

> Nota para el implementer: este task tiene varias piezas. Implementa cada endpoint con su función de service, verifica el arranque de la app y que el evaluado solo accede a lo suyo (scope 403). Si una pieza crece, divide en sub-commits. Mantén la regla de no exponer la opción correcta en `iniciar` (solo en el reporte tras entregar).

- [ ] **Step 3: Verificar app + suite**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if '/examenes' in getattr(r,'path','') or '/intentos' in getattr(r,'path','')])"` y `./venv/Scripts/python.exe -m pytest -q`.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/examenes.py backend/app/services/examen_intento_service.py
git commit -m "feat(examenes): endpoints de evaluado (iniciar/responder/entregar/reporte/pendientes)"
```

---

## Self-Review (cobertura del spec, Fase 2)

- CHECK evaluado_tipo coherente (prereq) → Task 1. ✓
- CRUD preguntas/opciones + reorden (RN-01, 1 correcta) → Task 3. ✓
- Asignación RM/Gerente → Task 4. ✓
- Fisher-Yates + preparar intento (RN-06, RN-01) → Task 5. ✓
- Responder + entregar + corrección (RN-03, RN-05, RN-06) → Task 6. ✓
- Endpoints de evaluado + reporte + scope (RN-07, RN-09) → Task 7. ✓
- Correo al entregar (notif_activa) y KPIs → diferidos a Fase 4. Frontend → Fase 4.
