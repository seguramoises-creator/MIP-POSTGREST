# Fase 1 — Motor de cálculo a Python + core agnóstico — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reemplazar los 5 stored procedures T-SQL (motor Score/Ranking `DW.*` + `cat.*` Categorización/Cobertura) por servicios Python puros, verificados por caracterización (SP == Python), y dejar el core agnóstico de BD.

**Architecture:** Cada SP se reimplementa como función Python (SQLAlchemy + `decimal.Decimal` para aritmética exacta). Un *harness de caracterización* corre el SP actual y el Python sobre el mismo estado y exige salidas idénticas. Al final, una migración dropea los 5 SPs y una auditoría de portabilidad neutraliza el SQL crudo restante.

**Tech Stack:** FastAPI, SQLAlchemy 2.0, `decimal.Decimal`, SQL Server (pymssql), pytest (unit con `MagicMock`; caracterización contra la BD local marcada `@pytest.mark.dbtest`).

## Global Constraints

- Aritmética con `decimal.Decimal`, precisiones del SP: sumas `DECIMAL(18,6)`, score `DECIMAL(10,4)`; redondeo `ROUND_HALF_UP` salvo que la caracterización muestre otro.
- Timestamps `datetime.now(timezone.utc)`. Logs `loguru`. Nunca `print()`.
- Contrato de `recalcular_ciclo(db, ciclo_id, pais_codigo=None) -> dict`: `{ciclo_id, abortado, motivo?(solo si abortado), filas_kpi_actualizadas, rankings_generados}` — NO cambiar (lo consume `/etl/recalcular` y `ETL.tsx`).
- Guard de ciclo cerrado: reutilizar `recalculo_service.validar_ciclo_abierto` / `CicloCerradoError`.
- Columnas exactas (verificadas):
  - `DW.FACT_ResultadoIndicador`: `id, pais_codigo, linea_id, gerente_id, rm_id, indicador_id, ciclo_id, mes_id, resultado_real, resultado_porcentaje, factor_aplicado, puntos_obtenidos, puntos_maximos, porcentaje_logro, carga_excel_id, fecha_carga, fecha_calculo, activo`
  - `Config.DIM_Indicador`: `... ponderacion_pct, escala ...`
  - `Config.DIM_MetaIndicador`: `id, indicador_id, peso, minimo, objetivo, maximo, puntaje_maximo, meta_100, tipo_calculo, orden_dashboard, activo`
  - `DW.FACT_ScoreIntegralRM`: `pais_codigo, linea_id, gerente_id, rm_id, ciclo_id, score_total, categoria_id, elegible_reconocimiento, fecha_calculo`
  - `DW.FACT_RankingRM`: `pais_codigo, linea_id, gerente_id, rm_id, ciclo_id, tipo_ranking, score_total, categoria_id, posicion_global, posicion_linea, posicion_anterior, elegible, fecha_generacion`
  - `Config.DIM_CategoriaDesempeno`: `id, codigo, nombre, score_min, score_max, color_dashboard, activo`
- Tests de caracterización requieren BD local SQL Server; márcalos `@pytest.mark.dbtest` y `skip` si `check_db_connection()` es False, para que la suite corra sin BD.

---

### Task 1: `completar_puntajes` (motor DW, parte 1)

**Files:**
- Create: `backend/app/services/motor_calculo_service.py`
- Create: `backend/tests/test_motor_calculo_service.py`

**Interfaces:**
- Produces: `completar_puntajes(db, ciclo_id, pais_codigo=None) -> int` — actualiza
  `resultado_porcentaje`, `puntos_obtenidos`, `fecha_calculo` y (con `DIM_MetaIndicador`)
  `factor_aplicado`, `puntos_maximos`, `porcentaje_logro`. Devuelve nº de filas de la 1ª pasada.
- Helper `_clamp(v, lo, hi)`.

- [ ] **Step 1: Test unitario (casos calculados a mano)**

```python
from decimal import Decimal
from types import SimpleNamespace
from unittest.mock import MagicMock
from app.services import motor_calculo_service as mc


def test_clamp():
    assert mc._clamp(Decimal("-5"), Decimal(0), Decimal(100)) == Decimal(0)
    assert mc._clamp(Decimal("150"), Decimal(0), Decimal(100)) == Decimal(100)
    assert mc._clamp(Decimal("42.5"), Decimal(0), Decimal(100)) == Decimal("42.5")


def test_puntos_una_fila(monkeypatch):
    # escala=1 -> valor*100; ponderacion 15 -> puntos = (cumpl/100)*15
    ri = SimpleNamespace(id=1, resultado_real=Decimal("0.80"), resultado_porcentaje=None,
                         puntos_obtenidos=None, fecha_calculo=None, indicador_id=9)
    ind = SimpleNamespace(id=9, escala=1, ponderacion_pct=Decimal("15"))
    filas = mc._calc_puntajes_filas([(ri, ind)])
    assert ri.resultado_porcentaje == Decimal("80.0")
    assert ri.puntos_obtenidos == Decimal("12.0")   # 0.80*100=80 -> 80/100*15
    assert filas == 1
```

*(Extraer `_calc_puntajes_filas(pairs)` puro — recibe lista de `(ri, indicador)` y muta
los `ri` — para poder testear sin DB. `completar_puntajes` hace el query y llama a este.)*

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_motor_calculo_service.py -k "clamp or puntos_una_fila" -v`
Expected: FAIL (módulo/func no existe)

- [ ] **Step 3: Implementar** en `motor_calculo_service.py`:

```python
"""SCGCPR — Motor de cálculo Score/Ranking en Python (reemplaza los SPs DW.*).

Aritmética con Decimal para igualar exactamente al T-SQL original.
Verificado por caracterización (tests/test_caracterizacion_motor.py).
"""
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP

from loguru import logger
from sqlalchemy.orm import Session

from app.models.hechos import ResultadoIndicador, ScoreIntegralRM, RankingRM
from app.models.dimensiones import Indicador, MetaIndicador, RepresentanteMedico, CategoriaDesempeno
from app.services.recalculo_service import validar_ciclo_abierto, CicloCerradoError

D100 = Decimal("100")
Q6 = Decimal("0.000001")


def _clamp(v: Decimal, lo: Decimal, hi: Decimal) -> Decimal:
    return lo if v < lo else hi if v > hi else v


def _dec(v) -> Decimal:
    return v if isinstance(v, Decimal) else Decimal(str(v))


def _calc_puntajes_filas(pairs) -> int:
    ahora = datetime.now(timezone.utc)
    n = 0
    for ri, ind in pairs:
        real = _dec(ri.resultado_real)
        valor_pct = real * D100 if int(ind.escala) == 1 else real
        cumpl = _clamp(valor_pct, Decimal(0), D100)
        ri.resultado_porcentaje = cumpl
        ri.puntos_obtenidos = (cumpl / D100) * _dec(ind.ponderacion_pct)
        ri.fecha_calculo = ahora
        n += 1
    return n


def completar_puntajes(db: Session, ciclo_id: int, pais_codigo=None) -> int:
    q = (db.query(ResultadoIndicador, Indicador)
         .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
         .filter(ResultadoIndicador.ciclo_id == ciclo_id,
                 ResultadoIndicador.activo == True,  # noqa: E712
                 ResultadoIndicador.resultado_real.isnot(None)))
    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    pairs = q.all()
    n = _calc_puntajes_filas(pairs)

    # 2ª pasada: metas (factor, puntos_maximos, porcentaje_logro)
    metas = {m.indicador_id: m for m in db.query(MetaIndicador).filter(MetaIndicador.activo == True).all()}  # noqa: E712
    for ri, _ind in pairs:
        m = metas.get(ri.indicador_id)
        if m is None:
            continue
        ri.factor_aplicado = m.peso
        ri.puntos_maximos = m.puntaje_maximo
        real = _dec(ri.resultado_real)
        base = None
        if m.meta_100 is not None:
            base = _dec(m.meta_100)
        elif m.objetivo is not None:
            base = _dec(m.objetivo)
        if base is not None:
            ri.porcentaje_logro = Decimal(0) if base == 0 else _clamp((real / base) * D100, Decimal("-1e9"), D100)
    db.commit()
    logger.info(f"Motor: puntajes completados ciclo={ciclo_id} pais={pais_codigo} filas={n}")
    return n
```

- [ ] **Step 4: Run — pasa**

Run: `cd backend && pytest tests/test_motor_calculo_service.py -k "clamp or puntos_una_fila" -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/motor_calculo_service.py backend/tests/test_motor_calculo_service.py
git commit -m "feat(motor) completar_puntajes en Python (Decimal exacto)"
```

---

### Task 2: `generar_ranking` (motor DW, parte 2)

**Files:**
- Modify: `backend/app/services/motor_calculo_service.py`
- Modify: `backend/tests/test_motor_calculo_service.py`

**Interfaces:**
- Consumes: `_clamp`, `_dec`.
- Produces: `generar_ranking(db, ciclo_id, pais_codigo=None) -> int` — delete-then-insert
  de `FACT_ScoreIntegralRM` y `FACT_RankingRM` (MENSUAL); devuelve nº de filas de ranking.
- Helper puro `_rankear(scores) -> list[dict]` (asigna posiciones + desempate).

- [ ] **Step 1: Test del cálculo puro de ranking**

```python
def test_rankear_desempate_por_rm():
    # dos RM con mismo score: gana el rm_id menor (posicion_global 1)
    rows = [
        {"rm_id": 5, "linea_id": 1, "gerente_id": 2, "pais_codigo": "DO", "score_total": Decimal("80.0"), "categoria_id": None},
        {"rm_id": 3, "linea_id": 1, "gerente_id": 2, "pais_codigo": "DO", "score_total": Decimal("80.0"), "categoria_id": None},
        {"rm_id": 9, "linea_id": 2, "gerente_id": 4, "pais_codigo": "DO", "score_total": Decimal("95.0"), "categoria_id": None},
    ]
    out = {r["rm_id"]: r for r in mc._rankear(rows)}
    assert out[9]["posicion_global"] == 1 and out[9]["elegible"] is True
    assert out[3]["posicion_global"] == 2   # empate: rm 3 antes que rm 5
    assert out[5]["posicion_global"] == 3
    assert out[3]["posicion_linea"] == 1 and out[5]["posicion_linea"] == 2
    assert out[9]["posicion_linea"] == 1    # otra línea
    assert out[3]["elegible"] is False
```

- [ ] **Step 2: Run — falla**

Run: `cd backend && pytest tests/test_motor_calculo_service.py -k rankear -v`
Expected: FAIL

- [ ] **Step 3: Implementar** (añadir a `motor_calculo_service.py`):

```python
def _rankear(rows: list[dict]) -> list[dict]:
    """Asigna posicion_global, posicion_linea (desempate score DESC, rm_id ASC) y elegible."""
    orden = sorted(rows, key=lambda r: (-r["score_total"], r["rm_id"]))
    por_linea: dict = {}
    for i, r in enumerate(orden, start=1):
        r["posicion_global"] = i
        k = r["linea_id"]
        por_linea[k] = por_linea.get(k, 0) + 1
        r["posicion_linea"] = por_linea[k]
        r["elegible"] = r["score_total"] >= Decimal("90")
    return orden


def _categoria_de(cats, score: Decimal):
    for c in cats:  # ordenadas por id ASC; TOP 1 que encaje
        lo = _dec(c.score_min) if c.score_min is not None else Decimal("-1")
        hi = _dec(c.score_max) if c.score_max is not None else Decimal("999999")
        if lo <= score <= hi:
            return c.id
    return None


def generar_ranking(db: Session, ciclo_id: int, pais_codigo=None) -> int:
    ahora = datetime.now(timezone.utc)
    q = (db.query(ResultadoIndicador, Indicador)
         .join(Indicador, Indicador.id == ResultadoIndicador.indicador_id)
         .filter(ResultadoIndicador.ciclo_id == ciclo_id,
                 ResultadoIndicador.activo == True,  # noqa: E712
                 ResultadoIndicador.puntos_obtenidos.isnot(None)))
    if pais_codigo:
        q = q.filter(ResultadoIndicador.pais_codigo == pais_codigo)
    filas = q.all()
    if not filas:
        return 0

    # score por RM = SUM(puntos)*100 / SUM(ponderacion), clamp 0..100 a 4 decimales
    acc: dict = {}
    for ri, ind in filas:
        a = acc.setdefault(ri.rm_id, {"pais_codigo": ri.pais_codigo, "puntos": Decimal(0), "pond": Decimal(0)})
        a["puntos"] += _dec(ri.puntos_obtenidos)
        a["pond"] += _dec(ind.ponderacion_pct)

    rms = {r.id: r for r in db.query(RepresentanteMedico).filter(RepresentanteMedico.id.in_(list(acc))).all()}
    cats = db.query(CategoriaDesempeno).filter(CategoriaDesempeno.activo == True).order_by(CategoriaDesempeno.id.asc()).all()  # noqa: E712
    rows = []
    for rm_id, a in acc.items():
        rm = rms.get(rm_id)
        score = Decimal(0) if a["pond"] == 0 else (a["puntos"] * D100 / a["pond"])
        score = _clamp(score, Decimal(0), D100).quantize(Decimal("0.0001"), rounding=ROUND_HALF_UP)
        rows.append({"rm_id": rm_id, "pais_codigo": a["pais_codigo"],
                     "linea_id": rm.linea_id if rm else None, "gerente_id": rm.gerente_id if rm else None,
                     "score_total": score, "categoria_id": _categoria_de(cats, score)})
    rankeados = _rankear(rows)

    # posicion_anterior del ranking previo (MENSUAL)
    prevq = db.query(RankingRM.rm_id, RankingRM.posicion_global).filter(
        RankingRM.ciclo_id == ciclo_id, RankingRM.tipo_ranking == "MENSUAL")
    if pais_codigo:
        prevq = prevq.filter(RankingRM.pais_codigo == pais_codigo)
    anterior = dict(prevq.all())

    # delete-then-insert
    dels = db.query(ScoreIntegralRM).filter(ScoreIntegralRM.ciclo_id == ciclo_id)
    delr = db.query(RankingRM).filter(RankingRM.ciclo_id == ciclo_id, RankingRM.tipo_ranking == "MENSUAL")
    if pais_codigo:
        dels = dels.filter(ScoreIntegralRM.pais_codigo == pais_codigo)
        delr = delr.filter(RankingRM.pais_codigo == pais_codigo)
    dels.delete(synchronize_session=False)
    delr.delete(synchronize_session=False)

    n = 0
    for r in rankeados:
        db.add(ScoreIntegralRM(pais_codigo=r["pais_codigo"], linea_id=r["linea_id"], gerente_id=r["gerente_id"],
            rm_id=r["rm_id"], ciclo_id=ciclo_id, score_total=r["score_total"], categoria_id=r["categoria_id"],
            elegible_reconocimiento=r["elegible"], fecha_calculo=ahora))
        db.add(RankingRM(pais_codigo=r["pais_codigo"], linea_id=r["linea_id"], gerente_id=r["gerente_id"],
            rm_id=r["rm_id"], ciclo_id=ciclo_id, tipo_ranking="MENSUAL", score_total=r["score_total"],
            categoria_id=r["categoria_id"], posicion_global=r["posicion_global"], posicion_linea=r["posicion_linea"],
            posicion_anterior=anterior.get(r["rm_id"]), elegible=r["elegible"], fecha_generacion=ahora))
        n += 1
    db.commit()
    logger.info(f"Motor: ranking generado ciclo={ciclo_id} pais={pais_codigo} filas={n}")
    return n
```

- [ ] **Step 4: Run — pasa** → `pytest tests/test_motor_calculo_service.py -k rankear -v`

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/motor_calculo_service.py backend/tests/test_motor_calculo_service.py
git commit -m "feat(motor) generar_ranking en Python (score, posiciones, delete-then-insert)"
```

---

### Task 3: `recalcular_ciclo_py` + cableado

**Files:**
- Modify: `backend/app/services/motor_calculo_service.py`
- Modify: `backend/app/services/recalculo_service.py` (reemplazar el `EXEC` por la llamada Python)
- Modify: `backend/tests/test_motor_calculo_service.py`

**Interfaces:**
- Produces: `recalcular_ciclo_py(db, ciclo_id, pais_codigo=None) -> dict` con el contrato exacto.

- [ ] **Step 1: Test del orquestador (ciclo cerrado aborta)**

```python
def test_recalcular_aborta_ciclo_cerrado(monkeypatch):
    db = MagicMock()
    from app.services import recalculo_service
    def _raise(d, c):
        raise recalculo_service.CicloCerradoError("cerrado")
    monkeypatch.setattr(mc, "validar_ciclo_abierto", _raise)
    out = mc.recalcular_ciclo_py(db, ciclo_id=7, pais_codigo="DO")
    assert out["abortado"] is True and out["filas_kpi_actualizadas"] == 0 and out["rankings_generados"] == 0
```

- [ ] **Step 2: Run — falla** → `pytest ... -k recalcular_aborta -v`

- [ ] **Step 3: Implementar** (añadir a `motor_calculo_service.py`):

```python
def recalcular_ciclo_py(db: Session, ciclo_id: int, pais_codigo=None) -> dict:
    try:
        validar_ciclo_abierto(db, ciclo_id)
    except CicloCerradoError as e:
        logger.warning(f"RECALCULO abortado — {e}")
        return {"ciclo_id": ciclo_id, "abortado": True, "motivo": str(e),
                "filas_kpi_actualizadas": 0, "rankings_generados": 0}
    n_kpi = completar_puntajes(db, ciclo_id, pais_codigo)
    n_rank = generar_ranking(db, ciclo_id, pais_codigo)
    return {"ciclo_id": ciclo_id, "abortado": False,
            "filas_kpi_actualizadas": n_kpi, "rankings_generados": n_rank}
```

- [ ] **Step 4: Reemplazar el EXEC** en `recalculo_service.recalcular_ciclo` — sustituir el
cuerpo (el bloque `db.execute(text("EXEC DW.sp_RecalcularCiclo ..."))` … `return {...}`) por:

```python
    from app.services import motor_calculo_service
    return motor_calculo_service.recalcular_ciclo_py(db, ciclo_id, pais_codigo)
```

Conservar el docstring pero añadir nota: `# jul-2026: el cálculo se movió de DW.sp_RecalcularCiclo a Python (motor_calculo_service)`.

- [ ] **Step 5: Run** → `pytest tests/test_motor_calculo_service.py -v` (todos verdes) y
`python -c "import app.main; print('ok')"`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/motor_calculo_service.py backend/app/services/recalculo_service.py backend/tests/test_motor_calculo_service.py
git commit -m "feat(motor) recalcular_ciclo_py + recalculo_service llama al motor Python"
```

---

### Task 4: Caracterización del motor DW (SP == Python)

**Files:**
- Create: `backend/tests/test_caracterizacion_motor.py`

**Interfaces:**
- Consumes: `motor_calculo_service`, la BD local con los SPs aún presentes.

- [ ] **Step 1: Escribir el harness de caracterización**

```python
"""Caracterización: el motor Python produce EXACTAMENTE lo mismo que los SPs DW.*.
Requiere BD SQL Server local con datos sembrados y los SPs presentes."""
import pytest
from sqlalchemy import text
from app.db.database import SessionLocal, check_db_connection

pytestmark = pytest.mark.skipif(not check_db_connection(), reason="sin BD local")


def _snap_ranking(db, ciclo_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT rm_id, CAST(score_total AS DECIMAL(10,4)), posicion_global, posicion_linea, "
        "CAST(elegible AS INT), ISNULL(categoria_id,-1) FROM DW.FACT_RankingRM "
        "WHERE ciclo_id=:c AND tipo_ranking='MENSUAL' ORDER BY rm_id"), {"c": ciclo_id}).all()]


def _snap_puntos(db, ciclo_id):
    return [tuple(r) for r in db.execute(text(
        "SELECT id, CAST(resultado_porcentaje AS DECIMAL(18,6)), CAST(puntos_obtenidos AS DECIMAL(18,6)) "
        "FROM DW.FACT_ResultadoIndicador WHERE ciclo_id=:c AND activo=1 ORDER BY id"), {"c": ciclo_id}).all()]


def _ciclos_con_datos(db):
    return [r[0] for r in db.execute(text(
        "SELECT DISTINCT ciclo_id FROM DW.FACT_ResultadoIndicador WHERE activo=1 AND resultado_real IS NOT NULL")).all()]


def test_motor_dw_equivale_al_sp():
    from app.services import motor_calculo_service as mc
    db = SessionLocal()
    try:
        ciclos = _ciclos_con_datos(db)
        assert ciclos, "sembrar datos antes de caracterizar"
        for ciclo_id in ciclos[:5]:
            # ciclos cerrados: el SP aborta; saltar
            cerrado = db.execute(text("SELECT cerrado FROM Config.DIM_Ciclo WHERE id=:c"), {"c": ciclo_id}).scalar()
            if cerrado:
                continue
            # 1) SP -> golden
            db.execute(text("EXEC DW.sp_RecalcularCiclo @ciclo_id=:c, @pais_codigo=NULL"), {"c": ciclo_id}); db.commit()
            g_rank, g_pts = _snap_ranking(db, ciclo_id), _snap_puntos(db, ciclo_id)
            # 2) Python -> overwrite
            mc.recalcular_ciclo_py(db, ciclo_id, None)
            p_rank, p_pts = _snap_ranking(db, ciclo_id), _snap_puntos(db, ciclo_id)
            assert p_pts == g_pts, f"puntos difieren en ciclo {ciclo_id}"
            assert p_rank == g_rank, f"ranking difiere en ciclo {ciclo_id}"
    finally:
        db.close()
```

- [ ] **Step 2: Correr y ajustar hasta igualdad exacta**

Run: `cd backend && pytest tests/test_caracterizacion_motor.py -v`
Expected: PASS. Si falla, **ajustar la aritmética del motor** (redondeo/precisión/orden de
operaciones) hasta que `p_pts==g_pts` y `p_rank==g_rank`. NO tocar el SP.

- [ ] **Step 3: Commit**

```bash
git add backend/tests/test_caracterizacion_motor.py backend/app/services/motor_calculo_service.py
git commit -m "test(motor) caracterizacion DW: motor Python == SP (igualdad exacta)"
```

---

### Task 5: Categorización a Python (`cat.sp_CalcularCategoriaMedica`)

**Files:**
- Modify: `backend/app/services/categorizacion_service.py`
- Create: `backend/tests/test_caracterizacion_categorizacion.py`

**Interfaces:**
- Reemplaza la llamada `db.execute(text("EXEC cat.sp_CalcularCategoriaMedica @LoadBatchKey=:key"))`
  por `categorizacion_service.calcular_categorias_py(db, load_batch_key)`.

- [ ] **Step 1: Volcar el SP vigente** para portarlo sección por sección:

Run: `cd backend && python -c "from app.db.database import SessionLocal; from sqlalchemy import text; db=SessionLocal(); print(db.execute(text(\"SELECT definition FROM sys.sql_modules WHERE object_id=OBJECT_ID('cat.sp_CalcularCategoriaMedica')\")).scalar())"`

Portar **cada bloque etiquetado** (`-- 1. Lookup Especialidades`, `-- 2. …`, snapshot/detalle)
a funciones Python en `categorizacion_service.py`, escribiendo con SQLAlchemy los mismos
`INSERT`/`UPDATE` sobre `cat.DimEspecialidad`, `DimGeografia`, `DimCentroMedico`, `DimMedico`,
`DimRepresentanteMedico`, y calculando la categoría con `cat.DimReglaCategoriaMedica` /
`DimComponenteCategoria`, escribiendo `cat.FactMedicoCategoriaSnapshot`/`FactMedicoCategoriaDetalle`.
Reemplazar el `EXEC` en el flujo (`categorizacion_service`) por `calcular_categorias_py`.

- [ ] **Step 2: Caracterización** (mismo patrón que Task 4): con un `LoadBatchKey` sembrado,
correr el SP → golden snapshot de `cat.FactMedicoCategoriaSnapshot`/`Detalle`; correr Python
sobre el mismo input → snapshot; **assert igualdad exacta**.

```python
import pytest
from sqlalchemy import text
from app.db.database import SessionLocal, check_db_connection
pytestmark = pytest.mark.skipif(not check_db_connection(), reason="sin BD local")

def _snap_cat(db, batch):
    return [tuple(r) for r in db.execute(text(
        "SELECT MedicoKey, CategoriaFinal, ISNULL(Puntaje,-1) FROM cat.FactMedicoCategoriaSnapshot "
        "WHERE LoadBatchKey=:b ORDER BY MedicoKey"), {"b": batch}).all()]
# test: EXEC sp -> golden; borrar snapshot del batch; calcular_categorias_py -> snapshot; assert ==
```

*(Ajustar los nombres de columnas de `FactMedicoCategoriaSnapshot` a los reales leídos del modelo/SP en el Step 1.)*

- [ ] **Step 3: Run + ajustar hasta igualdad** → `pytest tests/test_caracterizacion_categorizacion.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/categorizacion_service.py backend/tests/test_caracterizacion_categorizacion.py
git commit -m "feat(categorizacion) motor a Python (== SP, caracterizado)"
```

---

### Task 6: Cobertura Predictiva a Python (`cat.sp_CalcularCoberturaPredictiva`)

**Files:**
- Modify: `backend/app/services/cobertura_predictiva_service.py`
- Create: `backend/tests/test_caracterizacion_cobertura.py`

- [ ] **Step 1: Volcar el SP** (query análoga a Task 5, con `OBJECT_ID('cat.sp_CalcularCoberturaPredictiva')`).
Portar a `cobertura_predictiva_service.calcular_cobertura_py(db, codigo_ciclo, codigo_pais, fecha_corte=None, representante_key=None, linea=None)`
replicando cada bloque; reemplazar el `EXEC` del servicio por esta función.

- [ ] **Step 2: Caracterización** (mismo patrón): SP → golden; Python → snapshot; assert
igualdad exacta de la salida (filas/columnas que produce el SP; leer el `INSERT`/`SELECT`
final del SP en el Step 1 para saber qué comparar).

- [ ] **Step 3: Run + ajustar** → `pytest tests/test_caracterizacion_cobertura.py -v`

- [ ] **Step 4: Commit**

```bash
git add backend/app/services/cobertura_predictiva_service.py backend/tests/test_caracterizacion_cobertura.py
git commit -m "feat(cobertura) motor a Python (== SP, caracterizado)"
```

---

### Task 7: `DB_ENGINE` en config + auditoría de portabilidad

**Files:**
- Modify: `backend/app/core/config.py` (derivar `DB_ENGINE`)
- Modify: `backend/app/api/v1/routers/admin.py` (`/admin/reset` neutral por dialecto)

**Interfaces:**
- Produces: `settings.DB_ENGINE` ∈ `{"mssql","postgres"}` derivado del `DATABASE_URL`.

- [ ] **Step 1: Añadir `DB_ENGINE`** a `config.py`:

```python
    @property
    def DB_ENGINE(self) -> str:
        url = (self.DATABASE_URL or "").lower()
        return "postgres" if ("postgres" in url or "psycopg" in url) else "mssql"
```

- [ ] **Step 2: Neutralizar `/admin/reset`** — el bloque que usa `pymssql`/`NOCHECK`/`[corchetes]`
se ramifica por `settings.DB_ENGINE`: rama `mssql` = la actual; rama `postgres` = `TRUNCATE ... RESTART IDENTITY CASCADE`
o `DELETE` con FKs diferidas (`SET CONSTRAINTS ALL DEFERRED`). Mantener el contrato del endpoint
(`tipo=facts|dims`). *(La rama postgres se ejercita en la Fase 2; aquí solo se deja escrita y no rompe mssql.)*

- [ ] **Step 3: Verificar** que la app arranca y `/admin/reset` sigue funcionando en mssql:

Run: `cd backend && python -c "from app.core.config import settings; print('DB_ENGINE=', settings.DB_ENGINE)" && pytest -q 2>&1 | tail -2`
Expected: `DB_ENGINE= mssql` y suite verde.

- [ ] **Step 4: Commit**

```bash
git add backend/app/core/config.py backend/app/api/v1/routers/admin.py
git commit -m "feat(core) DB_ENGINE + /admin/reset neutral por dialecto (portabilidad)"
```

---

### Task 8: Migración — drop de los 5 SPs

**Files:**
- Create: `backend/alembic/versions/e8f1a2c3d4b5_drop_stored_procedures_motor.py`

**Interfaces:**
- `upgrade`: `DROP PROCEDURE IF EXISTS` de los 5. `downgrade`: los recrea desde su definición vigente.

- [ ] **Step 1: Capturar las definiciones vigentes** (para el downgrade) con:

Run: `cd backend && python -c "from app.db.database import SessionLocal; from sqlalchemy import text; db=SessionLocal(); [print('-- '+n); print(db.execute(text('SELECT definition FROM sys.sql_modules WHERE object_id=OBJECT_ID(:n)'),{'n':n}).scalar()) for n in ['DW.sp_RecalcularCiclo','DW.sp_CompletarPuntajesCiclo','DW.sp_GenerarRankingCiclo','cat.sp_CalcularCategoriaMedica','cat.sp_CalcularCoberturaPredictiva']]"`

Pegar cada definición en el `downgrade` como `op.execute(<CREATE PROCEDURE ...>)`.

- [ ] **Step 2: Crear la migración** `e8f1a2c3d4b5_drop_stored_procedures_motor.py`:

```python
"""Drop de los 5 stored procedures del motor (movidos a Python)

Revision ID: e8f1a2c3d4b5
Revises: d4b8f1a6c290
Create Date: 2026-07-04
"""
from alembic import op

revision = "e8f1a2c3d4b5"
down_revision = "d4b8f1a6c290"
branch_labels = None
depends_on = None

_SPS = ["DW.sp_RecalcularCiclo", "DW.sp_CompletarPuntajesCiclo", "DW.sp_GenerarRankingCiclo",
        "cat.sp_CalcularCategoriaMedica", "cat.sp_CalcularCoberturaPredictiva"]


def upgrade():
    for sp in _SPS:
        op.execute(f"DROP PROCEDURE IF EXISTS {sp}")


def downgrade():
    # Recrea los SPs desde su definición vigente (pegadas del Step 1).
    op.execute(r'''<CREATE PROCEDURE DW.sp_RecalcularCiclo ...>''')
    # ... los otros 4 ...
```

- [ ] **Step 3: Aplicar y verificar** que el recálculo sigue funcionando (ya vía Python):

Run: `cd backend && python -m alembic upgrade head && python -c "from app.db.database import SessionLocal; from sqlalchemy import text; db=SessionLocal(); print('SPs restantes:', db.execute(text(\"SELECT COUNT(*) FROM sys.sql_modules WHERE OBJECT_NAME(object_id) LIKE 'sp_%'\")).scalar())"`
Expected: `SPs restantes: 0`. Un recálculo por API/servicio debe seguir devolviendo el dict correcto.

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/e8f1a2c3d4b5_drop_stored_procedures_motor.py
git commit -m "feat(motor) migracion: drop de los 5 SPs (motor ya vive en Python)"
```

---

### Task 9: Verificación integral + documentación

**Files:**
- Modify: `CLAUDE.md` (§8 y §22 — el motor ya no vive en SQL Server)

- [ ] **Step 1: Suite completa (con y sin caracterización)**

Run: `cd backend && pytest -q`
Expected: todos verdes (los `@pytest.mark.dbtest` corren si hay BD; si no, `skip`).

- [ ] **Step 2: E2E de recálculo** (backend arriba): `POST /etl/recalcular/{ciclo_id}` sobre un
ciclo abierto → devuelve `{abortado:false, filas_kpi_actualizadas, rankings_generados}`; sobre un
ciclo cerrado → `{abortado:true}`. Verificar que el ranking se generó (consultar `/ranking`).

- [ ] **Step 3: Actualizar CLAUDE.md** — §8 (el motor de Score/Ranking **ya no** está en SQL Server;
vive en `motor_calculo_service.py`; los SPs fueron dropeados), §7 (fuente de productividad),
§22 fila de Categorización/Cobertura (motor en Python). Commit:

```bash
git add CLAUDE.md
git commit -m "docs(CLAUDE.md) motor de calculo movido de SQL Server a Python (core agnostico)"
```

---

## Self-Review

**Spec coverage:**
- §3 motor DW → Tasks 1, 2, 3, 4 ✓
- §4 cat.* (categorización + cobertura) → Tasks 5, 6 ✓
- §5 caracterización → Tasks 4, 5(Step 2), 6(Step 2) ✓
- §6 portabilidad (DB_ENGINE, /admin/reset) → Task 7 ✓
- §7 migración drop SPs → Task 8 ✓
- §8 verificación + docs → Task 9 ✓

**Placeholder scan:** Tasks 5 y 6 usan un patrón "volcar el SP vigente → portar sección por
sección → caracterizar" en vez de inlinear 12k/19k chars de T-SQL: es deliberado (el harness de
caracterización es la especificación de correctitud) y cada paso trae el comando exacto para volcar
el SP y el patrón de assert. No hay "TODO" en código de producción. El Task 8 downgrade se rellena
en el Step 1 con las definiciones reales (comando dado).

**Type consistency:**
- `completar_puntajes(db, ciclo_id, pais_codigo=None) -> int`, `generar_ranking(...) -> int`,
  `recalcular_ciclo_py(...) -> dict` consistentes en Tasks 1-4 y en `recalculo_service` ✓
- `_clamp/_dec/_rankear/_categoria_de` definidos en Tasks 1-2, usados coherentemente ✓
- Contrato de dict `{ciclo_id, abortado, motivo?, filas_kpi_actualizadas, rankings_generados}`
  idéntico al de `recalculo_service` original ✓
- `settings.DB_ENGINE` (Task 7) usado por la rama de `/admin/reset` y por la Fase 2 ✓
