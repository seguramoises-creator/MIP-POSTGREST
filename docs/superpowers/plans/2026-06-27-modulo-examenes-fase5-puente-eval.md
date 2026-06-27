# Módulo de Exámenes — Fase 5 (Puente EVAL_CONOCIMIENTOS) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development. Steps use checkbox (`- [ ]`).

**Goal:** Conectar la nota del examen con el motor de Score: sembrar la parametrización RESULTADO→FACTOR del indicador `EVAL_CONOCIMIENTOS` y alimentar ese indicador (solo para evaluados RM, ciclo abierto) al entregar un examen marcado, reusando el pipeline de KPI existente.

**Architecture:** Una migración siembra `Config.DIM_IndicadorTabla` para EVAL_CONOCIMIENTOS (escala 0–10). Un servicio puente, llamado al final de `entregar_intento`, calcula la nota (promedio de los exámenes marcados del RM en el ciclo), hace upsert de `DW.FACT_ResultadoIndicador.resultado_real`, y dispara `recalculo_service.recalcular_ciclo` (que aplica el factor desde `DIM_IndicadorTabla` dentro del SP y regenera ranking). El cálculo del factor NO se duplica en Python.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, SQL Server, pytest.

**Spec:** `docs/superpowers/specs/2026-06-26-modulo-examenes-design.md` (§7 detallado, §5 sección 5)

## Global Constraints

- Indicador `EVAL_CONOCIMIENTOS` ya existe (`Config.DIM_Indicador`, id=7 país DO, `peso_iup=0.10`, escala=100). NO crear otro.
- `Config.DIM_IndicadorTabla` columnas: `indicador_id, pais_codigo, codigo_indicador, nombre_indicador, rango_desde, rango_hasta, puntos, descripcion, activo`. Hoy tiene **0 filas** para EVAL_CONOCIMIENTOS.
- Parametrización (escala 0–10): `nota < 8 → factor 0`; `nota ≥ 8 → factor = nota/10` (8.0→0.80, 8.5→0.85, …, 10.0→1.00), en incrementos de 0.1, **rangos contiguos** (sin huecos). El SP usa la columna `puntos` como el factor.
- El examen aporta solo si `DimExamen.indicador_codigo == 'EVAL_CONOCIMIENTOS'` y `DimExamen.ciclo_id` no nulo. **Solo evaluados tipo RM.** **Solo ciclo abierto** (`recalculo_service.validar_ciclo_abierto`; capturar `CicloCerradoError` y omitir sin tocar el score). Nota = `score/10` del **último** intento; si hay varios exámenes marcados en el ciclo, **promediar**.
- Upsert en `DW.FACT_ResultadoIndicador` (modelo `ResultadoIndicador` en `app/models/hechos.py`): campos `rm_id, indicador_id, ciclo_id, pais_codigo, linea_id, gerente_id, resultado_real, activo` (resolver linea/gerente/pais desde `Config.DIM_RM`). Patrón delete-then-insert por `(rm_id, indicador_id, ciclo_id)`.
- Disparar `recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)` tras el upsert. El SP aplica internamente el guard de ciclo abierto y regenera todo.
- Backend Python/Alembic vía `./venv/Scripts/python.exe` / `./venv/Scripts/alembic.exe` desde `backend/`. Logs `loguru`. Timestamps UTC. Migración head actual de Fase 1-3: la última aplicada (`alembic.exe heads`). Tests verdes antes de cada commit.

## Estructura de archivos (Fase 5)

| Archivo | Responsabilidad |
|---------|-----------------|
| `alembic/versions/*` (crear) | Seed idempotente de `DIM_IndicadorTabla` para EVAL_CONOCIMIENTOS |
| `app/services/examen_kpi_service.py` (crear) | Puente: cálculo de nota + upsert ResultadoIndicador + disparo de recálculo |
| `app/services/examen_intento_service.py` (modificar) | Llamar al puente al final de `entregar_intento` |
| `tests/test_examen_kpi_service.py` (crear) | Tests del cálculo de nota/factor y de las guardas |

---

### Task 1: Seed de la parametrización EVAL_CONOCIMIENTOS

**Files:**
- Create: `alembic/versions/<rev>_seed_eval_conocimientos_tabla.py`

**Interfaces:**
- Produces: filas en `Config.DIM_IndicadorTabla` para el indicador EVAL_CONOCIMIENTOS (todos los países que tengan ese indicador), escala 0–10.

- [ ] **Step 1: Generar el stub**

Run: `cd backend && ./venv/Scripts/alembic.exe revision -m "seed DIM_IndicadorTabla EVAL_CONOCIMIENTOS"`

- [ ] **Step 2: Escribir el cuerpo (idempotente, programático)**

Reemplazar `upgrade`/`downgrade`. Para cada indicador con `codigo='EVAL_CONOCIMIENTOS'` (puede haber uno por país), si NO tiene filas en `DIM_IndicadorTabla`, insertarlas. Generar los rangos en Python:
```python
from alembic import op
from sqlalchemy import text
# revision/down_revision generados

def _rangos():
    filas = []
    # nota < 8 -> factor 0
    filas.append((0.0, 7.999, 0.0))
    v = 8.0
    while v <= 10.0001:
        desde = round(v, 2)
        hasta = round(v + 0.099, 3) if v < 10.0 else 10.0
        factor = round(v / 10.0, 2)  # 8.0->0.80 ... 10.0->1.00
        filas.append((desde, hasta, factor))
        v = round(v + 0.1, 2)
    return filas

def upgrade() -> None:
    conn = op.get_bind()
    indicadores = conn.execute(text(
        "SELECT id, pais_codigo, codigo, nombre FROM Config.DIM_Indicador WHERE codigo='EVAL_CONOCIMIENTOS'"
    )).fetchall()
    for ind in indicadores:
        ya = conn.execute(text(
            "SELECT COUNT(*) FROM Config.DIM_IndicadorTabla WHERE indicador_id=:i"), {"i": ind[0]}).scalar()
        if ya and ya > 0:
            continue
        for desde, hasta, puntos in _rangos():
            conn.execute(text(
                "INSERT INTO Config.DIM_IndicadorTabla "
                "(indicador_id, pais_codigo, codigo_indicador, nombre_indicador, rango_desde, rango_hasta, puntos, descripcion, activo) "
                "VALUES (:i, :p, :c, :n, :d, :h, :pt, :ds, 1)"),
                {"i": ind[0], "p": ind[1], "c": ind[2], "n": ind[3],
                 "d": desde, "h": hasta, "pt": puntos,
                 "ds": f"nota {desde}-{hasta} -> factor {puntos}"})

def downgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "DELETE t FROM Config.DIM_IndicadorTabla t "
        "JOIN Config.DIM_Indicador i ON i.id=t.indicador_id WHERE i.codigo='EVAL_CONOCIMIENTOS'"))
```

> Nota: si la nota llega como 0–100 en vez de 0–10 en algún punto, NO es problema de esta tabla — el puente (Task 2) divide score/10 antes de escribir `resultado_real`. La tabla queda en escala 0–10.

- [ ] **Step 3: Aplicar y verificar**

Run: `cd backend && ./venv/Scripts/alembic.exe upgrade head`
Verificar:
```bash
cd backend && ./venv/Scripts/python.exe -c "from app.db.database import engine; from sqlalchemy import text; c=engine.connect(); rows=c.execute(text(\"SELECT rango_desde, rango_hasta, puntos FROM Config.DIM_IndicadorTabla t JOIN Config.DIM_Indicador i ON i.id=t.indicador_id WHERE i.codigo='EVAL_CONOCIMIENTOS' ORDER BY rango_desde\")).fetchall(); print('filas:', len(rows)); print('primeras:', rows[:3]); print('ultima:', rows[-1])"
```
Expected: ~22 filas; primera ≈ (0, 7.999, 0); última = (10.0, 10.0, 1.0). Verificar también que la fila de 8.0 da 0.80 y 9.0 da 0.90.

- [ ] **Step 4: Suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q` → pasa.
```bash
git add backend/alembic/
git commit -m "feat(examenes): seed DIM_IndicadorTabla EVAL_CONOCIMIENTOS (escala 0-10)"
```

---

### Task 2: Servicio puente + integración en entregar

**Files:**
- Create: `app/services/examen_kpi_service.py`
- Modify: `app/services/examen_intento_service.py` (`entregar_intento`)
- Test: `tests/test_examen_kpi_service.py`

**Interfaces:**
- Produces:
  - `examen_kpi_service.nota_desde_score(score) -> float` — `round(score/10, 2)`.
  - `examen_kpi_service.alimentar_eval_conocimientos(db, intento) -> bool` — orquesta: valida que aplica (examen marcado + RM + ciclo); guard de ciclo abierto; calcula nota promedio; upsert ResultadoIndicador; dispara recálculo. Retorna True si alimentó, False si no aplicaba (no marcado / no RM / ciclo cerrado). NUNCA lanza por ciclo cerrado (lo captura y retorna False).

- [ ] **Step 1: Test de `nota_desde_score` + ramas de no-aplicación**

Crear `tests/test_examen_kpi_service.py`:
```python
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.services import examen_kpi_service as kpi

def test_nota_desde_score():
    assert kpi.nota_desde_score(85) == 8.5
    assert kpi.nota_desde_score(100) == 10.0
    assert kpi.nota_desde_score(73.4) == 7.34

def test_no_alimenta_si_evaluado_no_es_rm(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="GERENTE", evaluado_rm_id=None)
    # examen marcado pero evaluado GERENTE -> no alimenta
    monkeypatch.setattr(kpi, "_examen_de_intento", lambda d, i: SimpleNamespace(
        indicador_codigo="EVAL_CONOCIMIENTOS", ciclo_id=3))
    assert kpi.alimentar_eval_conocimientos(db, intento) is False

def test_no_alimenta_si_examen_no_marcado(monkeypatch):
    db = MagicMock()
    intento = SimpleNamespace(id=1, evaluado_tipo="RM", evaluado_rm_id=5)
    monkeypatch.setattr(kpi, "_examen_de_intento", lambda d, i: SimpleNamespace(
        indicador_codigo=None, ciclo_id=None))
    assert kpi.alimentar_eval_conocimientos(db, intento) is False
```

- [ ] **Step 2: Verificar falla, implementar, verificar pasa**

Crear `app/services/examen_kpi_service.py`:
```python
"""SCGCPR — Puente Exámenes → indicador EVAL_CONOCIMIENTOS del motor de Score."""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen, AsignacionExamen, IntentoExamen
from app.models.dimensiones import Indicador, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.services import recalculo_service

INDICADOR_EXAMEN = "EVAL_CONOCIMIENTOS"


def nota_desde_score(score) -> float:
    return round(float(score) / 10.0, 2)


def _examen_de_intento(db: Session, intento) -> Examen | None:
    asig = db.query(AsignacionExamen).filter(AsignacionExamen.id == intento.asignacion_id).first()
    if asig is None:
        return None
    return db.query(Examen).filter(Examen.id == asig.examen_id).first()


def _nota_promedio_rm(db: Session, rm_id: int, ciclo_id: int) -> float | None:
    """Promedio de score/10 del último intento de cada examen marcado del RM en el ciclo."""
    examenes = db.query(Examen).filter(
        Examen.indicador_codigo == INDICADOR_EXAMEN, Examen.ciclo_id == ciclo_id).all()
    notas = []
    for ex in examenes:
        ultimo = (db.query(IntentoExamen)
                  .join(AsignacionExamen, AsignacionExamen.id == IntentoExamen.asignacion_id)
                  .filter(AsignacionExamen.examen_id == ex.id,
                          IntentoExamen.evaluado_rm_id == rm_id,
                          IntentoExamen.fecha_fin.isnot(None))
                  .order_by(IntentoExamen.fecha_fin.desc()).first())
        if ultimo is not None and ultimo.score is not None:
            notas.append(nota_desde_score(ultimo.score))
    if not notas:
        return None
    return round(sum(notas) / len(notas), 2)


def alimentar_eval_conocimientos(db: Session, intento) -> bool:
    if intento.evaluado_tipo != "RM" or not intento.evaluado_rm_id:
        return False
    examen = _examen_de_intento(db, intento)
    if examen is None or examen.indicador_codigo != INDICADOR_EXAMEN or not examen.ciclo_id:
        return False
    ciclo_id = examen.ciclo_id
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Examen: ciclo {ciclo_id} cerrado — no se alimenta EVAL_CONOCIMIENTOS")
        return False
    rm = db.query(RepresentanteMedico).filter(RepresentanteMedico.id == intento.evaluado_rm_id).first()
    if rm is None:
        return False
    indicador = db.query(Indicador).filter(
        Indicador.codigo == INDICADOR_EXAMEN, Indicador.pais_codigo == rm.pais_codigo).first()
    if indicador is None:
        logger.warning(f"Examen: no existe indicador {INDICADOR_EXAMEN} para país {rm.pais_codigo}")
        return False
    nota = _nota_promedio_rm(db, rm.id, ciclo_id)
    if nota is None:
        return False
    # Upsert delete-then-insert por (rm, indicador, ciclo)
    db.query(ResultadoIndicador).filter(
        ResultadoIndicador.rm_id == rm.id,
        ResultadoIndicador.indicador_id == indicador.id,
        ResultadoIndicador.ciclo_id == ciclo_id).delete(synchronize_session=False)
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id, gerente_id=rm.gerente_id,
        resultado_real=nota, activo=True))
    db.commit()
    logger.info(f"Examen→EVAL_CONOCIMIENTOS: RM {rm.id} ciclo {ciclo_id} nota={nota}")
    recalculo_service.recalcular_ciclo(db, ciclo_id, rm.pais_codigo)
    return True
```
> Nota para el implementer: verificar los nombres reales de los campos de `ResultadoIndicador` en `app/models/hechos.py` (esp. `resultado_real`, `linea_id`, `gerente_id`, `mes_id`). Si `mes_id` es NOT NULL, resolver un mes válido o permitir null según el modelo. Ajusta el insert a los campos reales. Verifica también los nombres de import de `Indicador`/`RepresentanteMedico` en `app/models/dimensiones.py`.

- [ ] **Step 3: Integrar en `entregar_intento`**

En `app/services/examen_intento_service.py`, al final de `entregar_intento` (después del `db.commit()` que persiste el score, antes del `return intento`), agregar — envuelto para que un fallo del puente NO rompa la entrega del examen:
```python
    try:
        from app.services import examen_kpi_service
        examen_kpi_service.alimentar_eval_conocimientos(db, intento)
    except Exception as e:
        logger.error(f"Puente EVAL_CONOCIMIENTOS falló (no bloquea entrega): {e}")
    return intento
```

- [ ] **Step 4: Verificar + suite + commit**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print('OK')"` y `./venv/Scripts/python.exe -m pytest -q`.
```bash
git add backend/app/services/examen_kpi_service.py backend/app/services/examen_intento_service.py backend/tests/test_examen_kpi_service.py
git commit -m "feat(examenes): puente nota -> EVAL_CONOCIMIENTOS (RM, ciclo abierto, promedio) + disparo recalculo"
```

---

## Self-Review (cobertura del spec, Fase 5)

- Seed parametrización RESULTADO→FACTOR (escala 0–10) → Task 1. ✓
- Cálculo nota = score/10, promedio de exámenes marcados del RM en el ciclo → Task 2 (`_nota_promedio_rm`). ✓
- Solo RM, solo ciclo abierto (guard) → Task 2 (`alimentar_eval_conocimientos`). ✓
- Upsert resultado_real + disparo de recálculo (reusa el motor, no recalcula factor en Python) → Task 2. ✓
- El puente no bloquea la entrega si falla → Task 2 Step 3 (try/except). ✓
- **Operativo:** requiere un ciclo abierto y un examen con `indicador_codigo='EVAL_CONOCIMIENTOS'` + `ciclo_id` para activarse en producción.
