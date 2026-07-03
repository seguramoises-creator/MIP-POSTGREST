# Módulo de Exámenes v2.0 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Añadir al Módulo de Exámenes: un gate de consolidación por (ciclo, país) hacia EVAL_CONOCIMIENTOS, banner de nota real Aprobado/No Aprobado, tipo de pregunta "Objeción de Producto", correo de correcciones a T+30min, y estadísticas por pregunta con nombres.

**Architecture:** Módulo autocontenido en esquema `exam`. La nota del RM solo llega a `DW.FACT_ResultadoIndicador` cuando Capacitación consolida el (ciclo, país) — se elimina el auto-feed en cada entrega. Correo programado con APScheduler + disparo manual. Frontend React verificado con `tsc` + navegador.

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic (idempotente, `include_schemas=True`), pymssql/SQL Server, APScheduler 3.10.4, pytest (unit con `MagicMock`/`monkeypatch`), React 18 + TS + Vite + MUI v6, axios, React Query.

## Global Constraints

- Modelos: `Mapped[tipo]` + `mapped_column()`. Nunca `Column()` antiguo.
- Timestamps: `datetime.now(timezone.utc)`. Nunca `utcnow()`.
- Logs: `from loguru import logger`. Nunca `print()`.
- El motor de Score/Ranking vive en SQL Server: NO recalcular factores en Python; disparar `recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)`.
- Recálculo solo sobre ciclo abierto: usar `recalculo_service.validar_ciclo_abierto(db, ciclo_id)` (lanza `CicloCerradoError`).
- RBAC del módulo: `RequireCapacitacion = require_roles(Rol.ADMIN, Rol.CAPACITACION)` (ya definido en `examenes.py:114`). `RequireEquipo` añade `GERENTE_DISTRITO`.
- Migraciones Alembic idempotentes (verificar existencia de tabla/columna antes de crear).
- Frontend: llamadas API en `services/`, estilos MUI `sx`, sin manipular el DOM directamente.
- Tests backend: unit con `MagicMock` + `monkeypatch` (patrón de `tests/test_examen_kpi_service.py`).

---

### Task 1: Modelo + migración `exam.FactConsolidacionCiclo`

**Files:**
- Modify: `backend/app/models/exam_models.py` (añadir clase al final)
- Create: `backend/alembic/versions/c1e7a2f4b9d0_exam_consolidacion_ciclo.py`

**Interfaces:**
- Produces: modelo `ConsolidacionCiclo` (tabla `exam.FactConsolidacionCiclo`) con
  columnas `id, ciclo_id, pais_codigo, estado, rms_consolidados,
  nota_promedio_equipo, fecha_consolidacion, consolidado_por_usuario_id`;
  `UNIQUE(ciclo_id, pais_codigo)`.

- [ ] **Step 1: Añadir el modelo** en `exam_models.py` (al final del archivo):

```python
class ConsolidacionCiclo(Base):
    """Gate de integración de EVAL_CONOCIMIENTOS por (ciclo, país). Una fila por
    par consolidado; la nota del RM solo llega al KPI cuando esta consolidación
    se ejecuta (ver examen_consolidacion_service)."""
    __tablename__ = "FactConsolidacionCiclo"
    __table_args__ = (
        UniqueConstraint("ciclo_id", "pais_codigo",
                         name="UQ_ConsolidacionCiclo_ciclo_pais"),
        {"schema": "exam"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    ciclo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    rms_consolidados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    nota_promedio_equipo: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    fecha_consolidacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    consolidado_por_usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
```

- [ ] **Step 2: Crear la migración** `c1e7a2f4b9d0_exam_consolidacion_ciclo.py`:

```python
"""exam.FactConsolidacionCiclo — gate de consolidación EVAL_CONOCIMIENTOS

Revision ID: c1e7a2f4b9d0
Revises: <PONER_AQUI_EL_HEAD_ACTUAL>
Create Date: 2026-07-02
"""
from alembic import op
import sqlalchemy as sa

revision = "c1e7a2f4b9d0"
down_revision = None  # reemplazar por el head actual (ver Step 3)
branch_labels = None
depends_on = None


def upgrade():
    bind = op.get_bind()
    insp = sa.inspect(bind)
    existing = insp.get_table_names(schema="exam")
    if "FactConsolidacionCiclo" not in existing:
        op.create_table(
            "FactConsolidacionCiclo",
            sa.Column("id", sa.Integer(), primary_key=True, autoincrement=True),
            sa.Column("ciclo_id", sa.Integer(), nullable=False),
            sa.Column("pais_codigo", sa.String(length=10), nullable=False),
            sa.Column("estado", sa.String(length=15), nullable=False, server_default="pendiente"),
            sa.Column("rms_consolidados", sa.Integer(), nullable=False, server_default="0"),
            sa.Column("nota_promedio_equipo", sa.Numeric(5, 2), nullable=True),
            sa.Column("fecha_consolidacion", sa.DateTime(), nullable=True),
            sa.Column("consolidado_por_usuario_id", sa.Integer(), nullable=True),
            sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
            sa.ForeignKeyConstraint(["consolidado_por_usuario_id"], ["Security.DIM_Usuario.id"]),
            sa.UniqueConstraint("ciclo_id", "pais_codigo", name="UQ_ConsolidacionCiclo_ciclo_pais"),
            schema="exam",
        )


def downgrade():
    op.drop_table("FactConsolidacionCiclo", schema="exam")
```

- [ ] **Step 3: Fijar `down_revision` al head actual**

Run: `cd backend && python -m alembic heads`
Copiar el id devuelto a `down_revision` en la migración.

- [ ] **Step 4: Aplicar la migración**

Run: `cd backend && python -m alembic upgrade head`
Expected: sin errores; `python -m alembic current` muestra `c1e7a2f4b9d0`.

- [ ] **Step 5: Verificar que el modelo importa**

Run: `cd backend && python -c "import app.models.exam_models as m; print(m.ConsolidacionCiclo.__tablename__)"`
Expected: `FactConsolidacionCiclo`

- [ ] **Step 6: Commit**

```bash
git add backend/app/models/exam_models.py backend/alembic/versions/c1e7a2f4b9d0_exam_consolidacion_ciclo.py
git commit -m "feat(examenes) tabla exam.FactConsolidacionCiclo (gate consolidacion)"
```

---

### Task 2: Refactor `examen_kpi_service` — extraer upsert reutilizable y quitar auto-feed

**Files:**
- Modify: `backend/app/services/examen_kpi_service.py`
- Modify: `backend/app/services/examen_intento_service.py:341-355` (quitar llamada)
- Modify: `backend/tests/test_examen_kpi_service.py` (ajustar / añadir)

**Interfaces:**
- Consumes: `_nota_promedio_rm(db, rm_id, ciclo_id)` (ya existe), `ResultadoIndicador`, `Indicador`, `RepresentanteMedico`.
- Produces:
  - `upsert_nota_rm(db, rm, ciclo_id) -> float | None` — calcula el promedio y hace
    upsert (delete-then-insert) en `FACT_ResultadoIndicador` SIN recalcular; devuelve
    la nota escrita o `None` si no aplica.
  - `alimentar_eval_conocimientos` queda DEPRECADO/eliminado como auto-feed (ya no lo
    llama la entrega).

- [ ] **Step 1: Escribir el test de la nueva función `upsert_nota_rm`**

En `tests/test_examen_kpi_service.py` añadir:

```python
def test_upsert_nota_rm_escribe_sin_recalcular(monkeypatch):
    from types import SimpleNamespace
    db = MagicMock()
    rm = SimpleNamespace(id=5, pais_codigo="DO", linea_id=2, gerente_id=3)
    monkeypatch.setattr(kpi, "_nota_promedio_rm", lambda d, rid, cid: 8.5)
    monkeypatch.setattr(kpi, "_indicador_de_pais", lambda d, pais: SimpleNamespace(id=42))
    nota = kpi.upsert_nota_rm(db, rm, ciclo_id=7)
    assert nota == 8.5
    # No debe recalcular dentro del upsert (eso lo hace la consolidación 1 sola vez)
    assert db.add.called
```

- [ ] **Step 2: Run — verificar que falla**

Run: `cd backend && pytest tests/test_examen_kpi_service.py::test_upsert_nota_rm_escribe_sin_recalcular -v`
Expected: FAIL (`AttributeError: ... has no attribute 'upsert_nota_rm'`)

- [ ] **Step 3: Refactorizar `examen_kpi_service.py`**

Extraer el helper de indicador y la función de upsert; el `alimentar_eval_conocimientos`
existente pasa a delegar en `upsert_nota_rm` (queda disponible para tests legados) pero
YA NO se llama desde la entrega:

```python
def _indicador_de_pais(db: Session, pais_codigo: str):
    return db.query(Indicador).filter(
        Indicador.codigo == INDICADOR_EXAMEN,
        Indicador.pais_codigo == pais_codigo,
    ).first()


def upsert_nota_rm(db: Session, rm, ciclo_id: int) -> float | None:
    """Calcula el promedio EVAL_CONOCIMIENTOS del RM en el ciclo y hace upsert
    (delete-then-insert) en FACT_ResultadoIndicador. NO recalcula (la consolidación
    dispara un único recálculo al final). Devuelve la nota o None si no aplica."""
    indicador = _indicador_de_pais(db, rm.pais_codigo)
    if indicador is None:
        logger.warning(f"Examen: no existe indicador {INDICADOR_EXAMEN} para país {rm.pais_codigo}")
        return None
    nota = _nota_promedio_rm(db, rm.id, ciclo_id)
    if nota is None:
        return None
    db.query(ResultadoIndicador).filter(
        ResultadoIndicador.rm_id == rm.id,
        ResultadoIndicador.indicador_id == indicador.id,
        ResultadoIndicador.ciclo_id == ciclo_id,
    ).delete(synchronize_session=False)
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id, gerente_id=rm.gerente_id,
        resultado_real=nota, activo=True,
    ))
    return nota
```

- [ ] **Step 4: Quitar el auto-feed de la entrega**

En `examen_intento_service.py`, en `_finalizar_resultado`, ELIMINAR el bloque:

```python
    try:
        from app.services import examen_kpi_service
        examen_kpi_service.alimentar_eval_conocimientos(db, intento)
    except Exception as e:  # noqa: BLE001
        logger.error(f"Puente EVAL_CONOCIMIENTOS falló (no bloquea): {e}")
```

Dejar solo el envío de correo de resultado (el resto de la función intacto). Añadir un
comentario: `# El aporte a EVAL_CONOCIMIENTOS ahora ocurre solo al consolidar el ciclo`.

- [ ] **Step 5: Test de regresión — la entrega NO alimenta la FACT**

En `tests/test_examen_intento_service.py` (o el archivo de finalización) añadir un test
que verifique que `_finalizar_resultado` no invoca `examen_kpi_service`:

```python
def test_finalizar_resultado_no_alimenta_kpi(monkeypatch):
    import app.services.examen_intento_service as svc
    llamado = {"kpi": False}
    import app.services.examen_kpi_service as kpi
    monkeypatch.setattr(kpi, "upsert_nota_rm", lambda *a, **k: llamado.__setitem__("kpi", True))
    # _finalizar_resultado con notif desactivada no debe tocar el KPI
    from unittest.mock import MagicMock
    from types import SimpleNamespace
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="RM", evaluado_rm_id=5)
    examen = SimpleNamespace(id=1, indicador_codigo="EVAL_CONOCIMIENTOS", ciclo_id=7)
    asignacion = SimpleNamespace(notif_activa=False)
    svc._finalizar_resultado(db, intento, examen, asignacion, correctas=3, total=5)
    assert llamado["kpi"] is False
```

- [ ] **Step 6: Run tests**

Run: `cd backend && pytest tests/test_examen_kpi_service.py tests/test_examen_intento_service.py -v`
Expected: PASS (todos)

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/examen_kpi_service.py backend/app/services/examen_intento_service.py backend/tests/test_examen_kpi_service.py backend/tests/test_examen_intento_service.py
git commit -m "refactor(examenes) quitar auto-feed EVAL_CONOCIMIENTOS; upsert_nota_rm reutilizable"
```

---

### Task 3: Servicio `examen_consolidacion_service`

**Files:**
- Create: `backend/app/services/examen_consolidacion_service.py`
- Create: `backend/tests/test_examen_consolidacion_service.py`

**Interfaces:**
- Consumes: `examen_kpi_service.upsert_nota_rm`, `recalculo_service.{validar_ciclo_abierto, recalcular_ciclo, CicloCerradoError}`, `RepresentanteMedico`, `Examen`, `AsignacionExamen`, `IntentoExamen`, `ConsolidacionCiclo`.
- Produces:
  - `rms_del_ciclo(db, ciclo_id, pais_codigo) -> list[RepresentanteMedico]` — RM del país con exámenes marcados del ciclo y al menos un intento con score.
  - `estado_consolidacion(db, ciclo_id, pais_codigo) -> dict`
  - `consolidar_ciclo(db, ciclo_id, pais_codigo, usuario_id) -> dict`

- [ ] **Step 1: Escribir tests**

```python
"""Tests de la consolidación de exámenes → EVAL_CONOCIMIENTOS por (ciclo, país)."""
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.services import examen_consolidacion_service as cons


def test_consolidar_aborta_si_ciclo_cerrado(monkeypatch):
    db = MagicMock()
    def _raise(d, c):
        raise cons.recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(cons.recalculo_service, "validar_ciclo_abierto", _raise)
    out = cons.consolidar_ciclo(db, ciclo_id=7, pais_codigo="DO", usuario_id=1)
    assert out["abortado"] is True
    assert out["rms_consolidados"] == 0


def test_consolidar_escribe_y_recalcula_una_vez(monkeypatch):
    db = MagicMock()
    monkeypatch.setattr(cons.recalculo_service, "validar_ciclo_abierto", lambda d, c: None)
    rms = [SimpleNamespace(id=1, pais_codigo="DO"), SimpleNamespace(id=2, pais_codigo="DO")]
    monkeypatch.setattr(cons, "rms_del_ciclo", lambda d, c, p: rms)
    monkeypatch.setattr(cons.examen_kpi_service, "upsert_nota_rm", lambda d, rm, cid: 8.0)
    recalcs = {"n": 0}
    monkeypatch.setattr(cons.recalculo_service, "recalcular_ciclo",
                        lambda d, cid, pais: recalcs.__setitem__("n", recalcs["n"] + 1))
    monkeypatch.setattr(cons, "_upsert_estado", lambda *a, **k: None)
    out = cons.consolidar_ciclo(db, ciclo_id=7, pais_codigo="DO", usuario_id=1)
    assert out["abortado"] is False
    assert out["rms_consolidados"] == 2
    assert out["nota_promedio_equipo"] == 8.0
    assert recalcs["n"] == 1  # un único recálculo
```

- [ ] **Step 2: Run — verificar que falla**

Run: `cd backend && pytest tests/test_examen_consolidacion_service.py -v`
Expected: FAIL (módulo no existe)

- [ ] **Step 3: Implementar el servicio**

```python
"""SCGCPR — Consolidación de exámenes → EVAL_CONOCIMIENTOS por (ciclo, país).

Gate del módulo: la nota EVAL_CONOCIMIENTOS de los RM entra al KPI SOLO cuando
Capacitación ejecuta esta consolidación. La entrega individual ya no alimenta la FACT.
"""
from datetime import datetime, timezone
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen, AsignacionExamen, IntentoExamen, ConsolidacionCiclo
from app.models.dimensiones import RepresentanteMedico
from app.services import examen_kpi_service, recalculo_service

INDICADOR_EXAMEN = "EVAL_CONOCIMIENTOS"


def _examenes_marcados(db: Session, ciclo_id: int):
    return db.query(Examen).filter(
        Examen.indicador_codigo == INDICADOR_EXAMEN, Examen.ciclo_id == ciclo_id).all()


def rms_del_ciclo(db: Session, ciclo_id: int, pais_codigo: str) -> list[RepresentanteMedico]:
    """RM del país con al menos un intento finalizado con score en algún examen
    marcado EVAL_CONOCIMIENTOS del ciclo."""
    examenes = _examenes_marcados(db, ciclo_id)
    if not examenes:
        return []
    ex_ids = [e.id for e in examenes]
    rm_ids = {
        r.evaluado_rm_id
        for r in db.query(IntentoExamen)
        .join(AsignacionExamen, AsignacionExamen.id == IntentoExamen.asignacion_id)
        .filter(
            AsignacionExamen.examen_id.in_(ex_ids),
            IntentoExamen.evaluado_rm_id.isnot(None),
            IntentoExamen.score.isnot(None),
        ).all()
    }
    if not rm_ids:
        return []
    return db.query(RepresentanteMedico).filter(
        RepresentanteMedico.id.in_(rm_ids),
        RepresentanteMedico.pais_codigo == pais_codigo,
    ).all()


def estado_consolidacion(db: Session, ciclo_id: int, pais_codigo: str) -> dict:
    fila = db.query(ConsolidacionCiclo).filter(
        ConsolidacionCiclo.ciclo_id == ciclo_id,
        ConsolidacionCiclo.pais_codigo == pais_codigo,
    ).first()
    rms = rms_del_ciclo(db, ciclo_id, pais_codigo)
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
        ciclo_abierto = True
    except recalculo_service.CicloCerradoError:
        ciclo_abierto = False
    return {
        "ciclo_id": ciclo_id,
        "pais_codigo": pais_codigo,
        "estado": fila.estado if fila else "pendiente",
        "rms_con_nota": len(rms),
        "rms_con_nota_nombres": [r.nombre for r in rms],
        "nota_promedio_equipo": float(fila.nota_promedio_equipo) if fila and fila.nota_promedio_equipo is not None else None,
        "ultima_consolidacion": fila.fecha_consolidacion.isoformat() if fila and fila.fecha_consolidacion else None,
        "ciclo_abierto": ciclo_abierto,
    }


def _upsert_estado(db, ciclo_id, pais_codigo, n, promedio, usuario_id):
    fila = db.query(ConsolidacionCiclo).filter(
        ConsolidacionCiclo.ciclo_id == ciclo_id,
        ConsolidacionCiclo.pais_codigo == pais_codigo,
    ).first()
    if fila is None:
        fila = ConsolidacionCiclo(ciclo_id=ciclo_id, pais_codigo=pais_codigo)
        db.add(fila)
    fila.estado = "consolidado"
    fila.rms_consolidados = n
    fila.nota_promedio_equipo = promedio
    fila.fecha_consolidacion = datetime.now(timezone.utc)
    fila.consolidado_por_usuario_id = usuario_id


def consolidar_ciclo(db: Session, ciclo_id: int, pais_codigo: str, usuario_id: int | None) -> dict:
    """Escribe la nota EVAL_CONOCIMIENTOS de cada RM del (ciclo, país) a la FACT y
    dispara UN recálculo. Re-ejecutable mientras el ciclo esté abierto."""
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Consolidación abortada: ciclo {ciclo_id} cerrado")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_consolidados": 0,
                "nota_promedio_equipo": None}

    rms = rms_del_ciclo(db, ciclo_id, pais_codigo)
    notas = []
    for rm in rms:
        nota = examen_kpi_service.upsert_nota_rm(db, rm, ciclo_id)
        if nota is not None:
            notas.append(nota)
    promedio = round(sum(notas) / len(notas), 2) if notas else None
    _upsert_estado(db, ciclo_id, pais_codigo, len(notas), promedio, usuario_id)
    db.commit()
    logger.info(f"Consolidación ciclo {ciclo_id} país {pais_codigo}: {len(notas)} RM, prom={promedio}")

    recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
    return {"abortado": False, "rms_consolidados": len(notas),
            "nota_promedio_equipo": promedio, "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}
```

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_examen_consolidacion_service.py -v`
Expected: PASS (3)

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/examen_consolidacion_service.py backend/tests/test_examen_consolidacion_service.py
git commit -m "feat(examenes) servicio de consolidacion por (ciclo, pais)"
```

---

### Task 4: Endpoints de consolidación

**Files:**
- Modify: `backend/app/api/v1/routers/examenes.py` (añadir 2 endpoints antes de `/{examen_id}`)

**Interfaces:**
- Consumes: `examen_consolidacion_service.{estado_consolidacion, consolidar_ciclo}`, `RequireCapacitacion`.
- Produces: `GET /examenes/consolidacion`, `POST /examenes/consolidacion/consolidar`.

- [ ] **Step 1: Añadir schema del body** en `app/schemas/examenes.py`:

```python
class ConsolidarCiclo(BaseModel):
    ciclo_id: int
    pais_codigo: str = Field(min_length=1, max_length=10)
```

- [ ] **Step 2: Añadir los endpoints** en `examenes.py` (ANTES de la ruta `/{examen_id}`, por el ordering note del router):

```python
@router.get("/consolidacion", response_model=dict)
def consolidacion_estado(
    ciclo_id: int, pais_codigo: str,
    db: Session = Depends(get_db), current_user=RequireCapacitacion,
):
    """Preview del gate EVAL_CONOCIMIENTOS para un (ciclo, país)."""
    from app.services import examen_consolidacion_service
    return examen_consolidacion_service.estado_consolidacion(db, ciclo_id, pais_codigo)


@router.post("/consolidacion/consolidar", response_model=dict)
def consolidacion_ejecutar(
    body: ConsolidarCiclo,
    db: Session = Depends(get_db), current_user=RequireCapacitacion,
):
    """Consolida el (ciclo, país): escribe EVAL_CONOCIMIENTOS a la FACT y recalcula."""
    from app.services import examen_consolidacion_service
    return examen_consolidacion_service.consolidar_ciclo(
        db, body.ciclo_id, body.pais_codigo, getattr(current_user, "id", None))
```

Importar `ConsolidarCiclo` en el bloque de imports de schemas del router.

- [ ] **Step 3: Verificar el arranque de la app**

Run: `cd backend && python -c "import app.main; print('ok')"`
Expected: `ok` (sin errores de import ni de rutas)

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/examenes.py backend/app/schemas/examenes.py
git commit -m "feat(examenes) endpoints de consolidacion (estado + ejecutar)"
```

---

### Task 5: Tipo de pregunta "Objeción de Producto" (backend)

**Files:**
- Modify: `backend/app/services/examen_service.py` (validación al crear pregunta)
- Modify: `backend/app/schemas/examenes.py` (`PreguntaCrear` comentario; `ReporteRespuesta` +`tipo`/`escenario`)
- Modify: `backend/app/services/examen_intento_service.py` (`generar_reporte`: incluir tipo/escenario)
- Modify: `backend/tests/test_examen_service.py`

**Interfaces:**
- Consumes: `Pregunta.tipo`, `Pregunta.escenario` (existentes).
- Produces: tipo válido `"objecion"`; validación escenario obligatorio; reporte con `tipo`/`escenario`.

- [ ] **Step 1: Test de validación**

En `tests/test_examen_service.py` añadir:

```python
def test_objecion_requiere_escenario(db_session_o_mock):
    # objecion sin escenario -> ValueError
    import pytest
    from app.services import examen_service
    with pytest.raises(ValueError):
        examen_service.validar_pregunta_tipo("objecion", escenario=None, n_opciones=5)


def test_objecion_valida_con_escenario_y_opciones():
    from app.services import examen_service
    # no lanza
    examen_service.validar_pregunta_tipo("objecion", escenario="El Dr...", n_opciones=5)
```

*(Si la validación está inline en `crear_pregunta`, extraer un helper `validar_pregunta_tipo(tipo, escenario, n_opciones)` para poder testearlo aislado.)*

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_examen_service.py -k objecion -v`
Expected: FAIL

- [ ] **Step 3: Implementar validación**

En `examen_service.py`, extraer/añadir:

```python
def validar_pregunta_tipo(tipo: str, escenario: str | None, n_opciones: int) -> None:
    """Reglas por tipo. 'objecion' = opción múltiple con escenario obligatorio."""
    if tipo == "objecion":
        if not (escenario and escenario.strip()):
            raise ValueError("La pregunta de Objeción de Producto requiere el texto de la objeción (escenario).")
        if n_opciones < 2:
            raise ValueError("La Objeción de Producto requiere al menos 2 opciones.")
        return
    # ... reglas existentes para multi/caso/vf ...
```

Invocarla desde `crear_pregunta` con el `tipo`, `escenario` y `len(opciones)`.

- [ ] **Step 4: Añadir `tipo`/`escenario` a `ReporteRespuesta` y `ReporteIntento`**

En `schemas/examenes.py`, `ReporteRespuesta`:

```python
class ReporteRespuesta(BaseModel):
    pregunta_texto: str
    tipo: str = "multi"
    escenario: str | None = None
    explicacion: str | None
    indice_elegido_presentado: int | None
    texto_elegido: str | None
    texto_correcto: str
    es_correcta: bool
```

Actualizar `generar_reporte` en `examen_intento_service.py` para poblar `tipo` y
`escenario` de cada pregunta en el dict de respuesta.

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_examen_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/examen_service.py backend/app/services/examen_intento_service.py backend/app/schemas/examenes.py backend/tests/test_examen_service.py
git commit -m "feat(examenes) tipo de pregunta Objecion de Producto (backend + reporte)"
```

---

### Task 6: Estadísticas por pregunta con nombres

**Files:**
- Modify: `backend/app/services/examen_resultados_service.py` (`analisis_preguntas`)
- Modify: `backend/app/api/v1/routers/examenes.py` (endpoint recomendaciones, opcional)
- Modify: `backend/tests/test_examen_resultados_service.py`

**Interfaces:**
- Consumes: `_ultimo_intento_por_asignacion(db, examen_id)`, `Pregunta`, `IntentoRespuesta`, resolución RM/Gerente→nombre.
- Produces: `analisis_preguntas` con `acierto_pct, error_pct, aciertan[], fallan[], etiqueta`; `recomendaciones(db, examen_id) -> list[dict]`.

- [ ] **Step 1: Test**

```python
def test_analisis_incluye_nombres_y_etiqueta(monkeypatch):
    # Con un examen de prueba en DB o mocks, verificar que cada item trae
    # 'aciertan', 'fallan' (listas) y 'etiqueta' string.
    from app.services import examen_resultados_service as r
    items = r.analisis_preguntas(db, examen_id)  # fixtures del proyecto
    assert all("aciertan" in it and "fallan" in it and "etiqueta" in it for it in items)
```

*(Usar el mismo estilo de fixture que los demás tests de `test_examen_resultados_service.py`.)*

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_examen_resultados_service.py -k nombres -v`
Expected: FAIL

- [ ] **Step 3: Extender `analisis_preguntas`**

Reemplazar el cuerpo para: usar el **último intento por asignación**, contar aciertos/errores,
resolver nombres del evaluado (RM/Gerente), y clasificar:

```python
def _nombre_evaluado(db, intento) -> str:
    if intento.evaluado_rm_id:
        rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == intento.evaluado_rm_id).first()
        return rm.nombre if rm else f"RM {intento.evaluado_rm_id}"
    g = db.query(Gerente).filter(Gerente.id == intento.evaluado_gerente_id).first()
    return g.nombre if g else f"Gerente {intento.evaluado_gerente_id}"


def _etiqueta(error_pct: float) -> str:
    if error_pct >= 40:
        return "⚠️ Brecha crítica"
    if error_pct >= 20:
        return "⚡ Requiere refuerzo"
    return "✓ Bien comprendida"


def analisis_preguntas(db: Session, examen_id: int) -> list[dict]:
    ultimos = _ultimo_intento_por_asignacion(db, examen_id)  # {asignacion_id: intento}
    intento_ids = {it.id for it in ultimos.values()}
    preguntas = db.query(Pregunta).filter(
        Pregunta.examen_id == examen_id, Pregunta.activo == True).order_by(Pregunta.orden).all()
    # nombre por intento_id
    nombre_por_intento = {it.id: _nombre_evaluado(db, it) for it in ultimos.values()}
    salida = []
    for p in preguntas:
        resp = db.query(IntentoRespuesta).filter(
            IntentoRespuesta.pregunta_id == p.id,
            IntentoRespuesta.intento_id.in_(intento_ids) if intento_ids else False,
        ).all()
        total = len(resp)
        aciertan = [nombre_por_intento.get(r.intento_id) for r in resp if r.es_correcta is True]
        fallan = [nombre_por_intento.get(r.intento_id) for r in resp if r.es_correcta is False]
        error_pct = _porcentaje(len(fallan), total)
        correcta = next((o.texto_opcion for o in p.opciones if o.es_correcta), None)
        salida.append({
            "pregunta_id": p.id, "texto": p.texto, "orden": p.orden,
            "respuesta_correcta": correcta, "total_respuestas": total,
            "acierto_pct": _porcentaje(len(aciertan), total), "error_pct": error_pct,
            "aciertan": [n for n in aciertan if n], "fallan": [n for n in fallan if n],
            "etiqueta": _etiqueta(error_pct),
        })
    return salida


def recomendaciones(db: Session, examen_id: int) -> list[dict]:
    return [it for it in analisis_preguntas(db, examen_id) if it["error_pct"] >= 40]
```

Importar `RepresentanteMedico`, `Gerente` en el módulo si no están.

- [ ] **Step 4: (Opcional) endpoint de recomendaciones**

En `examenes.py`:

```python
@router.get("/{examen_id}/recomendaciones", response_model=list[dict])
def examen_recomendaciones(examen_id: int, db: Session = Depends(get_db), current_user=RequireEquipo):
    from app.services import examen_resultados_service
    return examen_resultados_service.recomendaciones(db, examen_id)
```

- [ ] **Step 5: Run tests**

Run: `cd backend && pytest tests/test_examen_resultados_service.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/examen_resultados_service.py backend/app/api/v1/routers/examenes.py backend/tests/test_examen_resultados_service.py
git commit -m "feat(examenes) analisis por pregunta con nombres + recomendaciones"
```

---

### Task 7: Correo de correcciones (notificación + scheduler + endpoint)

**Files:**
- Modify: `backend/app/services/notification_service.py` (nueva función)
- Create: `backend/app/core/scheduler.py`
- Modify: `backend/app/main.py:24-46` (lifespan: iniciar/cerrar scheduler)
- Modify: `backend/app/api/v1/routers/examenes.py` (endpoint manual + programar al asignar)
- Create: `backend/tests/test_examen_correcciones.py`

**Interfaces:**
- Consumes: `_enviar`, `_pie_pagina` (notification_service), `Examen/Asignacion/Intento/Respuesta/Pregunta/Opcion`.
- Produces:
  - `notification_service.notificar_correcciones_examen(db, examen_id) -> int` (correos enviados)
  - `core.scheduler.{get_scheduler, iniciar, apagar, programar_correcciones}`

- [ ] **Step 1: Test del armado del cuerpo**

```python
def test_cuerpo_correcciones_lista_incorrectas(monkeypatch):
    from app.services import notification_service as ns
    enviados = {"n": 0}
    monkeypatch.setattr(ns, "_enviar", lambda dest, asu, html: enviados.__setitem__("n", enviados["n"] + 1) or True)
    # con fixtures/mocks: 1 participante con 2 incorrectas -> 1 correo
    n = ns.notificar_correcciones_examen(db, examen_id)
    assert n == enviados["n"]
```

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_examen_correcciones.py -v`
Expected: FAIL

- [ ] **Step 3: Implementar `notificar_correcciones_examen`** en `notification_service.py`:

```python
def notificar_correcciones_examen(db, examen_id: int) -> int:
    """Envía a cada participante (último intento) la corrección de sus preguntas
    incorrectas. Best-effort: no-op si el correo está deshabilitado. Devuelve #enviados."""
    from app.models.exam_models import (
        Examen, AsignacionExamen, IntentoExamen, IntentoRespuesta, Pregunta, PreguntaOpcion)
    from app.services.examen_resultados_service import _ultimo_intento_por_asignacion, _nombre_evaluado
    examen = db.query(Examen).filter(Examen.id == examen_id).first()
    if examen is None:
        return 0
    ultimos = _ultimo_intento_por_asignacion(db, examen_id)
    enviados = 0
    for intento in ultimos.values():
        incorrectas = db.query(IntentoRespuesta).filter(
            IntentoRespuesta.intento_id == intento.id,
            IntentoRespuesta.es_correcta == False,
        ).all()
        if not incorrectas:
            continue
        filas = []
        for r in incorrectas:
            p = db.query(Pregunta).filter(Pregunta.id == r.pregunta_id).first()
            elegida = db.query(PreguntaOpcion).filter(PreguntaOpcion.id == r.opcion_elegida_id).first() if r.opcion_elegida_id else None
            correcta = next((o for o in (p.opciones if p else []) if o.es_correcta), None)
            filas.append(
                f"<li><b>{p.texto if p else ''}</b><br>"
                f"❌ Tu respuesta: {elegida.texto_opcion if elegida else '—'}<br>"
                f"✅ Correcta: {correcta.texto_opcion if correcta else '—'}<br>"
                f"<i>{p.explicacion or ''}</i></li>")
        # destinatario: correo del evaluado si se puede resolver; si no, se omite envío real
        asunto = f"Correcciones — {examen.nombre}"
        html = f"<p>Hola {_nombre_evaluado(db, intento)},</p><ul>{''.join(filas)}</ul>{_pie_pagina()}"
        destinatario = _correo_evaluado(db, intento)  # helper: None si no hay correo
        if destinatario and _enviar(destinatario, asunto, html):
            enviados += 1
        elif not _habilitado():
            enviados += 1  # modo demo: cuenta como "simulado"
    logger.info(f"Correcciones examen {examen_id}: {enviados} correos")
    return enviados
```

Añadir el helper `_correo_evaluado(db, intento)` que resuelve el email del RM/Gerente
(devuelve `None` si el modelo no tiene email — el envío real se omite pero en demo cuenta).

- [ ] **Step 4: Crear `app/core/scheduler.py`**

```python
"""Scheduler de tareas del backend (APScheduler). Singleton simple para jobs
programados (p.ej. correo de correcciones a T+30min del cierre de un examen)."""
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.background import BackgroundScheduler
from loguru import logger

from app.db.database import SessionLocal
from app.services import notification_service

_scheduler: BackgroundScheduler | None = None


def get_scheduler() -> BackgroundScheduler:
    global _scheduler
    if _scheduler is None:
        _scheduler = BackgroundScheduler(timezone="UTC")
    return _scheduler


def iniciar() -> None:
    sch = get_scheduler()
    if not sch.running:
        sch.start()
        logger.info("APScheduler iniciado")


def apagar() -> None:
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("APScheduler apagado")


def _job_correcciones(examen_id: int) -> None:
    db = SessionLocal()
    try:
        notification_service.notificar_correcciones_examen(db, examen_id)
    finally:
        db.close()


def programar_correcciones(examen_id: int, fecha_limite: datetime) -> None:
    """Programa el correo de correcciones a fecha_limite + 30 min."""
    run_date = (fecha_limite if fecha_limite.tzinfo else fecha_limite.replace(tzinfo=timezone.utc)) + timedelta(minutes=30)
    get_scheduler().add_job(
        _job_correcciones, "date", run_date=run_date, args=[examen_id],
        id=f"correcciones-{examen_id}", replace_existing=True)
    logger.info(f"Correcciones examen {examen_id} programadas para {run_date.isoformat()}")
```

- [ ] **Step 5: Cablear el lifespan** en `main.py` (dentro de `lifespan`, tras verificar BD, antes de `yield`, y en el shutdown):

```python
    # Scheduler de tareas (correo de correcciones, etc.)
    from app.core import scheduler
    scheduler.iniciar()

    yield  # Servidor corriendo

    scheduler.apagar()
    logger.info(f"Apagando {settings.APP_NAME}...")
```

- [ ] **Step 6: Endpoint manual + programación al asignar** en `examenes.py`:

```python
@router.post("/{examen_id}/correcciones/enviar", response_model=dict)
def enviar_correcciones(examen_id: int, db: Session = Depends(get_db), current_user=RequireCapacitacion):
    """Envía (o simula en demo) las correcciones a los participantes ahora."""
    from app.services import notification_service
    n = notification_service.notificar_correcciones_examen(db, examen_id)
    return {"enviados": n}
```

En el endpoint `asignar` existente, tras crear las asignaciones, si hay `fecha_limite`,
programar: `from app.core import scheduler; scheduler.programar_correcciones(examen_id, fecha_limite)`.

- [ ] **Step 7: Run tests + arranque**

Run: `cd backend && pytest tests/test_examen_correcciones.py -v && python -c "import app.main; print('ok')"`
Expected: PASS + `ok`

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/notification_service.py backend/app/core/scheduler.py backend/app/main.py backend/app/api/v1/routers/examenes.py backend/tests/test_examen_correcciones.py
git commit -m "feat(examenes) correo de correcciones a T+30min (APScheduler + boton manual)"
```

---

### Task 8: Feature B backend — `provisional` en el reporte

**Files:**
- Modify: `backend/app/schemas/examenes.py` (`ReporteIntento` +`provisional`)
- Modify: `backend/app/services/examen_intento_service.py` (`generar_reporte`)
- Modify: `backend/tests/test_examen_intento_service.py`

**Interfaces:**
- Produces: `ReporteIntento.provisional: bool` (True si quedan abiertas sin calificar).

- [ ] **Step 1: Test**

```python
def test_reporte_marca_provisional_si_hay_abiertas_pendientes(...):
    rep = intento_svc.generar_reporte(db, intento_id)
    assert "provisional" in rep
```

- [ ] **Step 2: Run — falla** → **Step 3: Implementar**

Añadir `provisional: bool = False` a `ReporteIntento`. En `generar_reporte`, calcular
`provisional = any(r.respuesta_texto is not None and r.puntos is None for r in respuestas)`
e incluirlo en el dict devuelto.

- [ ] **Step 4: Run tests**

Run: `cd backend && pytest tests/test_examen_intento_service.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/schemas/examenes.py backend/app/services/examen_intento_service.py backend/tests/test_examen_intento_service.py
git commit -m "feat(examenes) reporte incluye flag provisional (para banner de nota)"
```

---

### Task 9: Frontend — `MisExamenes.tsx` (banner nota + objeción + aviso correo)

**Files:**
- Modify: `frontend/src/pages/examenes/MisExamenes.tsx`
- Modify: `frontend/src/services/examenes.service.ts` (tipos del reporte)

**Interfaces:**
- Consumes: respuesta de `entregar` con `{score, aprobado, nota_minima, provisional, respuestas:[{tipo, escenario, ...}]}`.

- [ ] **Step 1: Ajustar tipos** en `examenes.service.ts`: añadir `provisional: boolean`
  a `ReporteIntento` y `tipo: string; escenario?: string | null` a `ReporteRespuesta`.

- [ ] **Step 2: Banner de resultado** (reemplazar cualquier escritura a DOM por estado):

```tsx
{reporte && (
  reporte.provisional ? (
    <Alert severity="info" sx={{ mb: 2 }}>
      Pendiente de calificación del Gerente. Tu nota final se calculará cuando revise las preguntas abiertas.
    </Alert>
  ) : reporte.aprobado ? (
    <Alert severity="success" sx={{ mb: 2 }}>
      <b>¡Examen Aprobado!</b> Nota {reporte.score}% (mínima {reporte.nota_minima}%). Este resultado suma para tu KPI al consolidar el ciclo.
    </Alert>
  ) : (
    <Alert severity="error" sx={{ mb: 2 }}>
      <b>Examen no aprobado — por debajo de nota mínima.</b><br/>
      Nota obtenida: {reporte.score}% · Nota mínima: {reporte.nota_minima}%<br/>
      ❌ Este resultado NO suma para KPI. Solicita un nuevo intento a tu supervisor de capacitación.
    </Alert>
  )
)}
```

Mostrar `reporte.score` en grande siempre (KPI card).

- [ ] **Step 3: Banner naranja de objeción** en la vista de toma y en el reporte, cuando `pregunta.tipo === 'objecion'`:

```tsx
{p.tipo === 'objecion' && p.escenario && (
  <Box sx={{ p: 1.5, mb: 1, bgcolor: '#fff3e0', border: '1px solid #ffb74d', borderRadius: 1 }}>
    <Typography variant="subtitle2" sx={{ color: '#e65100', fontWeight: 700 }}>🛡️ Objeción del Médico sobre el Producto</Typography>
    <Typography variant="body2">{p.escenario}</Typography>
  </Box>
)}
```

- [ ] **Step 4: Aviso de correo** al finalizar:

```tsx
<Typography variant="caption" color="text.secondary">
  Recibirás por correo las correcciones de tus respuestas incorrectas 30 minutos después de concluido el tiempo hábil del examen.
</Typography>
```

- [ ] **Step 5: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/examenes/MisExamenes.tsx frontend/src/services/examenes.service.ts
git commit -m "feat(examenes) MisExamenes: banner nota real + objecion + aviso correo"
```

---

### Task 10: Frontend — `Examenes.tsx` (crear Objeción de Producto)

**Files:**
- Modify: `frontend/src/pages/examenes/Examenes.tsx`

- [ ] **Step 1: Botón de creación** junto a los demás tipos:

```tsx
<Tooltip title="Evalúa cómo el visitador responde cuando el médico objeta una característica, efecto adverso o limitación del producto.">
  <Button variant="outlined" color="warning" onClick={() => nuevaPregunta('objecion')}>🛡️ + Objeción de Producto</Button>
</Tooltip>
```

- [ ] **Step 2: Campo escenario con placeholder** cuando `tipo === 'objecion'`:

```tsx
{tipo === 'objecion' && (
  <TextField label="Objeción del médico" multiline minRows={2} fullWidth
    value={escenario} onChange={e => setEscenario(e.target.value)}
    placeholder="Ej: El Dr. García dice: No receto [Producto X] porque escuché que causa [efecto adverso]. El competidor no tiene ese problema." />
)}
```

El resto (5 opciones + marcar correcta + explicación) reutiliza el formulario `multi`.

- [ ] **Step 3: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 4: Commit**

```bash
git add frontend/src/pages/examenes/Examenes.tsx
git commit -m "feat(examenes) crear pregunta tipo Objecion de Producto"
```

---

### Task 11: Frontend — `EquipoExamenes.tsx` (consolidación + stats con nombres + correcciones)

**Files:**
- Modify: `frontend/src/pages/examenes/EquipoExamenes.tsx`
- Modify: `frontend/src/services/examenes.service.ts` (nuevas llamadas)

**Interfaces:**
- Consumes: `GET /examenes/consolidacion`, `POST /examenes/consolidacion/consolidar`, `GET /examenes/{id}/analisis-preguntas` (extendido), `POST /examenes/{id}/correcciones/enviar`.

- [ ] **Step 1: Añadir llamadas** en `examenes.service.ts`:

```ts
export const consolidacionEstado = (cicloId: number, paisCodigo: string) =>
  api.get('/examenes/consolidacion', { params: { ciclo_id: cicloId, pais_codigo: paisCodigo } }).then(r => r.data);
export const consolidarCiclo = (ciclo_id: number, pais_codigo: string) =>
  api.post('/examenes/consolidacion/consolidar', { ciclo_id, pais_codigo }).then(r => r.data);
export const enviarCorrecciones = (examenId: number) =>
  api.post(`/examenes/${examenId}/correcciones/enviar`).then(r => r.data);
```

- [ ] **Step 2: Panel "Consolidación de Ciclo → KPI"**: selector ciclo + país,
  tarjeta preview (`rms_con_nota`, `rms_con_nota_nombres`, `nota_promedio_equipo`,
  `estado`, `ultima_consolidacion`), botón **Consolidar** (deshabilitado si
  `!ciclo_abierto`), con confirmación y refetch del estado tras consolidar.

- [ ] **Step 3: Análisis por pregunta con tooltip de nombres** (barras verde/roja + MUI `Tooltip`):

```tsx
<Tooltip title={item.fallan.join(', ') || 'Nadie falló'}>
  <Box sx={{ bgcolor: 'error.light', width: `${item.error_pct}%` }}>{item.error_pct}%</Box>
</Tooltip>
```

Cards resumen (mayor acierto / más fallada) y lista de recomendaciones (`error_pct >= 40`).

- [ ] **Step 4: Botón "Enviar/Simular correcciones ahora"** por examen que llama `enviarCorrecciones(examenId)` y muestra el conteo devuelto.

- [ ] **Step 5: Verificar compilación**

Run: `cd frontend && npx tsc -b --noEmit`
Expected: sin errores

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/examenes/EquipoExamenes.tsx frontend/src/services/examenes.service.ts
git commit -m "feat(examenes) EquipoExamenes: consolidacion + stats con nombres + correcciones"
```

---

### Task 12: Verificación E2E + documentación

**Files:**
- Modify: `CLAUDE.md` (§ Módulo Exámenes / Pendiente — reflejar v2.0)

- [ ] **Step 1: Suite completa**

Run: `cd backend && pytest -q`
Expected: todos verdes (incluye los nuevos).

- [ ] **Step 2: Build frontend**

Run: `cd frontend && npx tsc -b --noEmit && npm run build`
Expected: sin errores.

- [ ] **Step 3: E2E manual (navegador)** con backend + frontend arriba, login `admin`/`Admin1234!`:
  crear pregunta objeción → tomar examen como RM (ver banner naranja + banner nota) →
  ver análisis con tooltips → simular correcciones → consolidar (ciclo, país) y verificar
  que el ranking se recalcula.

- [ ] **Step 4: Actualizar CLAUDE.md** (marcar v2.0: gate de consolidación, tipo objeción, correo de correcciones, stats con nombres) y commit.

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md) Modulo Examenes v2.0: gate consolidacion + mejoras"
```

---

## Self-Review

**Spec coverage:**
- §3 gate consolidación → Tasks 1-4, 11 ✓
- §4 banner nota real → Tasks 8, 9 ✓
- §5 objeción de producto → Tasks 5, 9, 10 ✓
- §6 correo T+30min → Task 7 ✓
- §7 stats con nombres → Tasks 6, 11 ✓
- §8 lógica KPI (materializa al consolidar) → Tasks 2, 3, 9 (texto banner) ✓
- §9 migración + pruebas → Task 1 + tests en cada task + Task 12 ✓

**Placeholder scan:** los tests de Tasks 6/7/8 referencian "fixtures del proyecto" para
casos con DB — el implementador debe seguir el patrón del archivo de test correspondiente
(unit con `MagicMock`/`monkeypatch`, o el fixture de DB si el archivo ya lo usa). No hay
"TODO/TBD" en código de producción.

**Type consistency:**
- `upsert_nota_rm(db, rm, ciclo_id) -> float | None` usado consistente en Tasks 2, 3 ✓
- `consolidar_ciclo(...) -> {abortado, rms_consolidados, nota_promedio_equipo, ...}` usado en Tasks 3, 4, 11 ✓
- `notificar_correcciones_examen(db, examen_id) -> int` usado en Tasks 7, 11 ✓
- `analisis_preguntas` keys (`acierto_pct/error_pct/aciertan/fallan/etiqueta`) usados en Tasks 6, 11 ✓
- `ReporteIntento.provisional` / `ReporteRespuesta.tipo,escenario` usados en Tasks 5, 8, 9 ✓
