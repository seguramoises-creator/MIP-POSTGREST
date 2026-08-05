# Calendario de Coaching (Fase 4) — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Generar por Gerente de Distrito y ciclo un calendario sugerido de acompañamientos, donde cada RM recibe tantas visitas de coaching como indica su cuadrante LSII vigente, repartidas en el ciclo, editable y publicable.

**Architecture:** Servicio Python puro (`formacion_calendario_service`) que solo LEE de LSII (`FACT_EvaluacionReceptividad`) y del ROI de Visita, sobre las dos tablas ya creadas en `0031_formacion_ampliada` (`ParametroFrecuenciaLSII`, `CalendarioCoachingSugerido`). Router `/formacion/calendario-coaching` con auto-scope de GD. Frontend: página de cuadrícula + diálogo de frecuencias. **Sin migración.**

**Tech Stack:** FastAPI, SQLAlchemy 2.0 (`Mapped`), pytest (BD PostgreSQL real por módulo), React 18 + TS + MUI v6 + TanStack Query + Zustand.

## Global Constraints

- Solo edición **PostgreSQL** (`MSM-postgres`). No tocar ni nombrar la edición SQL Server.
- Modelos SQLAlchemy 2.0 `Mapped[..]` + `mapped_column()`. Timestamps `datetime.now(timezone.utc)`.
- Rutas frontend de Formación gatean por `allowedRoles` (NO por `recurso` de la matriz RBAC — un recurso inexistente denegaría a todos).
- Cuadrantes válidos: `D1, D2, D3, D4`. Frecuencia de arranque `D1=4, D2=3, D3=2, D4=1` (configurable por país en `ParametroFrecuenciaLSII`).
- El servicio **no recalcula LSII**: solo lee `FACT_EvaluacionReceptividad` (última por RM/ciclo, `activo=True`).
- Escrituras (generar/mover/publicar) solo sobre **ciclo abierto**: usar `recalculo_service.validar_ciclo_abierto` (levanta `CicloCerradoError` → 409).
- Commits en español, prefijo `feat(formacion)` / `test(formacion)`. Terminar mensajes con `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`.

---

## File Structure

- Create `backend/app/services/formacion_calendario_service.py` — motor y helpers.
- Create `backend/app/api/v1/routers/formacion_calendario.py` — router REST.
- Modify `backend/app/api/v1/router.py` — registrar el router.
- Create `backend/tests/test_formacion_calendario.py` — pruebas.
- Create `scripts/seed_frecuencia_lsii.py` — seed idempotente de frecuencias por país.
- Modify `frontend/src/services/formacion.service.ts` — funciones y tipos del calendario.
- Create `frontend/src/pages/formacion/CalendarioCoaching.tsx` — página + diálogo de frecuencias.
- Modify `frontend/src/App.tsx` — ruta lazy `/formacion/calendario`.
- Modify `frontend/src/components/layout/Sidebar.tsx` — ítem "Calendario de Coaching".

> **Nota de diseño respecto al spec §8:** la configuración de frecuencias se implementa como **diálogo dentro de la página** (mismo patrón que el diálogo "Umbrales" de la Fase 7 ya aprobado y desplegado), no como tab en `Admin.tsx`. Misma funcionalidad, menor acoplamiento con el mega-componente `Admin.tsx`.

---

### Task 1: Frecuencias por cuadrante (default + override + validación)

**Files:**
- Create: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `FRECUENCIA_DEFECTO: dict[str,int]`, `CUADRANTES: tuple[str,...]`, `frecuencias(db, pais_codigo) -> dict[str,int]`, `fijar_frecuencia(db, pais_codigo, cuadrante, visitas, descripcion=None) -> ParametroFrecuenciaLSII`.

- [ ] **Step 1: Write the failing test** (crea el archivo de test con la infraestructura de BD y las primeras pruebas)

```python
"""Calendario de Coaching (Fase 4) — motor de reglas sobre el cuadrante LSII."""
import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import Pais
from app.models.formacion import ParametroFrecuenciaLSII
from app.services import formacion_calendario_service as cal

BD_PRUEBA = "vista_test_calcoach"


def test_frecuencia_arranca_en_los_valores_por_defecto(db):
    f = cal.frecuencias(db, "DO")
    assert f == {"D1": 4, "D2": 3, "D3": 2, "D4": 1}


def test_un_pais_puede_sobrescribir_una_frecuencia(db):
    cal.fijar_frecuencia(db, "DO", "D1", 6)
    assert cal.frecuencias(db, "DO")["D1"] == 6
    # Override por país: otro país conserva el arranque.
    assert cal.frecuencias(db, "PA")["D1"] == 4


def test_fijar_un_cuadrante_invalido_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D9", 1)


def test_fijar_visitas_negativas_es_error(db):
    with pytest.raises(ValueError):
        cal.fijar_frecuencia(db, "DO", "D1", -1)


# --- infraestructura de BD (igual patrón que test_formacion_brechas) ---
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
    for t in ('formacion."CalendarioCoachingSugerido"', 'formacion."ParametroFrecuenciaLSII"',
              '"DW"."FACT_EvaluacionReceptividad"', '"Config"."DIM_RM"',
              '"Config"."DIM_Gerente"', '"Config"."DIM_Linea"', '"Config"."DIM_Ciclo"',
              '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {t}"))
    s.add_all([Pais(codigo="DO", nombre="República Dominicana"),
               Pais(codigo="PA", nombre="Panamá")])
    s.commit()
    yield s
    s.close()
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.formacion_calendario_service'`.

- [ ] **Step 3: Write minimal implementation** (crea el servicio con las frecuencias)

```python
"""Calendario de Coaching (§7).

Consume el cuadrante LSII vigente (FACT_EvaluacionReceptividad) — NO lo recalcula —
y sugiere una frecuencia de acompañamiento por RM, repartida en el ciclo. El GD
edita y publica. Es planeación; la ejecución del coaching vive en Coaching MORE.
"""
from math import ceil

from sqlalchemy.orm import Session

from app.models.formacion import ParametroFrecuenciaLSII

CUADRANTES: tuple[str, ...] = ("D1", "D2", "D3", "D4")

#: Arranque del §7.2 (ilustrativo, punto abierto 4): a menor desarrollo, más
#: acompañamiento. Editable por país en ParametroFrecuenciaLSII.
FRECUENCIA_DEFECTO: dict[str, int] = {"D1": 4, "D2": 3, "D3": 2, "D4": 1}


def frecuencias(db: Session, pais_codigo: str) -> dict[str, int]:
    """Los valores de arranque, con las sobrescrituras del país."""
    valores = dict(FRECUENCIA_DEFECTO)
    for p in (db.query(ParametroFrecuenciaLSII)
              .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo).all()):
        if p.cuadrante in valores:
            valores[p.cuadrante] = int(p.visitas_por_ciclo)
    return valores


def fijar_frecuencia(db: Session, pais_codigo: str, cuadrante: str, visitas: int,
                     descripcion: str | None = None) -> ParametroFrecuenciaLSII:
    if cuadrante not in CUADRANTES:
        raise ValueError(f"Cuadrante inválido: {cuadrante}. Válidos: {', '.join(CUADRANTES)}.")
    if visitas < 0:
        raise ValueError("visitas_por_ciclo no puede ser negativo.")
    p = (db.query(ParametroFrecuenciaLSII)
         .filter(ParametroFrecuenciaLSII.pais_codigo == pais_codigo,
                 ParametroFrecuenciaLSII.cuadrante == cuadrante).first())
    if p is None:
        p = ParametroFrecuenciaLSII(pais_codigo=pais_codigo, cuadrante=cuadrante,
                                    visitas_por_ciclo=visitas, descripcion=descripcion)
        db.add(p)
    else:
        p.visitas_por_ciclo = visitas
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: frecuencia por cuadrante configurable por pais"
```

---

### Task 2: Semanas del ciclo y reparto espaciado

**Files:**
- Modify: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `SEMANAS_DEFECTO: int`, `semanas_ciclo(ciclo) -> int`, `distribuir_semanas(n, semanas) -> list[int]`.

- [ ] **Step 1: Write the failing test** (agrega estas funciones puras al archivo de test, arriba de la infraestructura de BD)

```python
def test_reparto_de_una_visita_cae_a_mitad_del_ciclo():
    assert cal.distribuir_semanas(1, 8) == [4]


def test_reparto_de_cuatro_visitas_queda_espaciado():
    assert cal.distribuir_semanas(4, 8) == [1, 3, 5, 7]


def test_reparto_de_dos_visitas():
    assert cal.distribuir_semanas(2, 8) == [2, 6]


def test_cero_visitas_no_agenda_nada():
    assert cal.distribuir_semanas(0, 8) == []


def test_mas_visitas_que_semanas_se_acota_al_rango():
    # Nunca propone una semana fuera de [1, semanas]; puede repetir semana.
    r = cal.distribuir_semanas(10, 4)
    assert len(r) == 10
    assert all(1 <= s <= 4 for s in r)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "reparto or visitas or semanas" -q`
Expected: FAIL — `AttributeError: module ... has no attribute 'distribuir_semanas'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio, tras las constantes)

```python
SEMANAS_DEFECTO = 8  # biciclo típico si el ciclo no trae fechas


def semanas_ciclo(ciclo) -> int:
    """Semanas que abarca el ciclo, por sus fechas; fallback al biciclo típico."""
    ini = getattr(ciclo, "fecha_inicio", None)
    fin = getattr(ciclo, "fecha_fin", None)
    if ini and fin and fin >= ini:
        return max(1, ceil(((fin - ini).days + 1) / 7))
    return SEMANAS_DEFECTO


def distribuir_semanas(n: int, semanas: int) -> list[int]:
    """Reparte n visitas espaciadas entre 1..semanas.

    La i-ésima cae en round((i+0.5)*semanas/n), acotada a [1, semanas]. Para
    n=4, semanas=8 da [1,3,5,7]; para n=1 da la mitad del ciclo."""
    if n <= 0 or semanas <= 0:
        return []
    return [min(semanas, max(1, round((i + 0.5) * semanas / n))) for i in range(n)]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "reparto or visitas or semanas" -q`
Expected: PASS (5 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: semanas del ciclo y reparto espaciado"
```

---

### Task 3: Cuadrante LSII vigente por RM

**Files:**
- Modify: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `cuadrante_vigente(db, rm_id, ciclo_id) -> str | None`.
- Consumes: `app.models.hechos.EvaluacionReceptividad` (campos `rm_id, ciclo_id, nivel_lsii, activo, id`).

- [ ] **Step 1: Write the failing test** (agrega al archivo de test, y añade el import de `EvaluacionReceptividad` y `Gerente, Linea, RepresentanteMedico, Ciclo` arriba)

Añadir a los imports del test:
```python
from datetime import date
from app.models.dimensiones import Ciclo, Gerente, Linea, RepresentanteMedico
from app.models.hechos import EvaluacionReceptividad
```

Añadir un fixture de escenario y la prueba (tras el fixture `db`):
```python
@pytest.fixture
def equipo(db):
    """Un GD con dos RM y un ciclo con fechas de 8 semanas."""
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea); db.flush()
    gd = Gerente(pais_codigo="DO", codigo="GD-1", nombre="GD Uno", tipo="DISTRITO")
    db.add(gd); db.flush()
    rm_a = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM01", nombre="Ana")
    rm_b = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id, gerente_id=gd.id,
                               codigo="VM02", nombre="Beto")
    db.add_all([rm_a, rm_b])
    ciclo = Ciclo(pais_codigo="DO", nombre="C07-2026", anio=2026, numero=7,
                  cerrado=False, fecha_inicio=date(2026, 6, 1), fecha_fin=date(2026, 7, 26))
    db.add(ciclo); db.commit()
    return {"db": db, "gd": gd, "rm_a": rm_a, "rm_b": rm_b, "ciclo": ciclo, "linea": linea}


def _eval(db, rm_id, ciclo_id, nivel):
    e = EvaluacionReceptividad(pais_codigo="DO", rm_id=rm_id, ciclo_id=ciclo_id,
                               score_receptividad=50, nivel_lsii=nivel,
                               estilo_liderazgo="X", activo=True)
    db.add(e); db.commit(); return e


def test_cuadrante_vigente_toma_la_ultima_evaluacion(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, rm.id, ciclo.id, "D3")
    _eval(db, rm.id, ciclo.id, "D1")   # más reciente
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) == "D1"


def test_rm_sin_evaluacion_no_tiene_cuadrante(equipo):
    db, rm, ciclo = equipo["db"], equipo["rm_b"], equipo["ciclo"]
    assert cal.cuadrante_vigente(db, rm.id, ciclo.id) is None
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "cuadrante" -q`
Expected: FAIL — `AttributeError: ... 'cuadrante_vigente'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade el import arriba)

```python
from app.models.hechos import EvaluacionReceptividad
```
```python
def cuadrante_vigente(db: Session, rm_id: int, ciclo_id: int) -> str | None:
    """Cuadrante D1-D4 de la última evaluación LSII activa del RM en el ciclo.

    Solo lee: el cálculo del cuadrante es del módulo LSII, no de aquí."""
    e = (db.query(EvaluacionReceptividad)
         .filter(EvaluacionReceptividad.rm_id == rm_id,
                 EvaluacionReceptividad.ciclo_id == ciclo_id,
                 EvaluacionReceptividad.activo.is_(True))
         .order_by(EvaluacionReceptividad.id.desc())
         .first())
    return e.nivel_lsii if e else None
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "cuadrante" -q`
Expected: PASS (2 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: cuadrante LSII vigente por RM (solo lectura)"
```

---

### Task 4: Orden por ROI del ciclo anterior (desempate §7)

**Files:**
- Modify: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `ciclo_anterior_id(db, ciclo) -> int | None`, `orden_por_roi(db, rm_ids, ciclo_anterior_id) -> list[int]`.
- Consumes: `visita_costo_service.roi_ranking(db, ciclo_id) -> {"items": [{"vm_id": int, "valor": float}, ...]}` (menor ROI primero).

- [ ] **Step 1: Write the failing test** (monkeypatch de `roi_ranking` para no montar todo el módulo de Visita)

```python
def test_orden_por_roi_pone_primero_el_de_menor_roi(equipo, monkeypatch):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    monkeypatch.setattr(cal.visita_costo_service, "roi_ranking",
                        lambda _db, _c: {"items": [{"vm_id": b.id, "valor": -10.0},
                                                   {"vm_id": a.id, "valor": 30.0}]})
    assert cal.orden_por_roi(db, [a.id, b.id], 999) == [b.id, a.id]


def test_rm_sin_roi_previo_queda_al_final(equipo, monkeypatch):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    monkeypatch.setattr(cal.visita_costo_service, "roi_ranking",
                        lambda _db, _c: {"items": [{"vm_id": a.id, "valor": 5.0}]})
    # b no tiene ROI previo → al final; a primero.
    assert cal.orden_por_roi(db, [a.id, b.id], 999) == [a.id, b.id]


def test_sin_ciclo_anterior_conserva_orden_estable(equipo):
    db, a, b = equipo["db"], equipo["rm_a"], equipo["rm_b"]
    assert cal.orden_por_roi(db, [a.id, b.id], None) == [a.id, b.id]


def test_ciclo_anterior_es_el_previo_del_mismo_pais(equipo):
    db, ciclo = equipo["db"], equipo["ciclo"]
    # fecha_inicio/fecha_fin son NOT NULL en DIM_Ciclo — hay que darlas.
    prev = Ciclo(pais_codigo="DO", nombre="C06-2026", anio=2026, numero=6, cerrado=True,
                 fecha_inicio=date(2026, 4, 1), fecha_fin=date(2026, 5, 26))
    db.add(prev); db.commit()
    assert cal.ciclo_anterior_id(db, ciclo) == prev.id
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "roi or ciclo_anterior" -q`
Expected: FAIL — `AttributeError: ... 'orden_por_roi'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade imports arriba)

```python
from app.models.dimensiones import Ciclo
from app.services import visita_costo_service
```
```python
def ciclo_anterior_id(db: Session, ciclo) -> int | None:
    """El ciclo inmediatamente anterior del mismo país (por anio, numero)."""
    prev = (db.query(Ciclo)
            .filter(Ciclo.pais_codigo == ciclo.pais_codigo,
                    (Ciclo.anio < ciclo.anio) |
                    ((Ciclo.anio == ciclo.anio) & (Ciclo.numero < ciclo.numero)))
            .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
            .first())
    return prev.id if prev else None


def orden_por_roi(db: Session, rm_ids: list[int], ciclo_anterior_id: int | None) -> list[int]:
    """Ordena los RM por ROI ASCENDENTE del ciclo anterior (menor ROI = más
    atención = primero). RM sin ROI previo o sin ciclo anterior → al final,
    conservando el orden de entrada (estable)."""
    roi_map: dict[int, float] = {}
    if ciclo_anterior_id is not None:
        rk = visita_costo_service.roi_ranking(db, ciclo_anterior_id)
        roi_map = {it["vm_id"]: it["valor"] for it in rk.get("items", [])}
    orden_entrada = {rm: i for i, rm in enumerate(rm_ids)}
    return sorted(rm_ids, key=lambda rm: (roi_map.get(rm, float("inf")), orden_entrada[rm]))
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "roi or ciclo_anterior" -q`
Expected: PASS (4 passed).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: orden por ROI del ciclo anterior (desempate)"
```

---

### Task 5: `generar` — orquestación, sin_evaluar, día round-robin, persistencia selectiva

**Files:**
- Modify: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `DIAS: list[str]`, `generar(db, gd_id, ciclo_id, persistir=True) -> dict` con forma `{"semanas": int, "celdas": list[dict], "sin_evaluar": list[dict]}`. Cada celda: `{"id"?, "rm_id", "rm_nombre", "semana", "dia_semana", "cuadrante"}`.
- Consumes: `validar_ciclo_abierto`, `cuadrante_vigente`, `frecuencias`, `distribuir_semanas`, `semanas_ciclo`, `orden_por_roi`, `ciclo_anterior_id`, `CalendarioCoachingSugerido`, `RepresentanteMedico`.

- [ ] **Step 1: Write the failing test**

```python
def test_generar_agenda_segun_frecuencia_y_separa_sin_evaluar(equipo):
    db, gd, a, b, ciclo = (equipo["db"], equipo["gd"], equipo["rm_a"],
                           equipo["rm_b"], equipo["ciclo"])
    _eval(db, a.id, ciclo.id, "D1")   # D1 → 4 visitas
    # b queda sin evaluación LSII
    r = cal.generar(db, gd.id, ciclo.id, persistir=False)
    assert r["semanas"] == 8
    celdas_a = [c for c in r["celdas"] if c["rm_id"] == a.id]
    assert len(celdas_a) == 4
    assert {c["semana"] for c in celdas_a} == {1, 3, 5, 7}
    assert all(c["cuadrante"] == "D1" for c in celdas_a)
    assert [s["rm_id"] for s in r["sin_evaluar"]] == [b.id]


def test_generar_persiste_y_regenerar_conserva_lo_publicado(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D4")   # D4 → 1 visita
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    from app.models.formacion import CalendarioCoachingSugerido as CC
    celda = db.query(CC).filter(CC.gd_id == gd.id).one()
    celda.publicado = True; db.commit()
    # Regenerar no debe borrar la celda publicada NI duplicar al RM ya agendado.
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    assert db.query(CC).filter(CC.gd_id == gd.id, CC.publicado.is_(True)).count() == 1
    assert db.query(CC).filter(CC.gd_id == gd.id).count() == 1, "no se duplica el RM preservado"


def test_generar_sobre_ciclo_cerrado_aborta(equipo):
    from app.services.recalculo_service import CicloCerradoError
    db, gd, ciclo = equipo["db"], equipo["gd"], equipo["ciclo"]
    ciclo.cerrado = True; db.commit()
    with pytest.raises(CicloCerradoError):
        cal.generar(db, gd.id, ciclo.id, persistir=True)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "generar" -q`
Expected: FAIL — `AttributeError: ... 'generar'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio; añade imports arriba)

```python
from app.models.dimensiones import RepresentanteMedico
from app.models.formacion import CalendarioCoachingSugerido
from app.services.recalculo_service import validar_ciclo_abierto
```
```python
DIAS: list[str] = ["lunes", "martes", "miercoles", "jueves", "viernes"]


def generar(db: Session, gd_id: int, ciclo_id: int, persistir: bool = True) -> dict:
    """Sugiere el calendario del GD para el ciclo. persistir=False = previa.

    Persistir hace delete-then-insert SELECTIVO: borra solo las celdas sugeridas
    (no publicadas ni editadas a mano) y reinserta; conserva el trabajo del GD."""
    ciclo = validar_ciclo_abierto(db, ciclo_id)   # levanta CicloCerradoError si está cerrado
    semanas = semanas_ciclo(ciclo)
    frec = frecuencias(db, ciclo.pais_codigo)
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.gerente_id == gd_id).all())
    nombre = {rm.id: rm.nombre for rm in rms}

    con_cuadrante: list[tuple[int, str]] = []
    sin_evaluar: list[dict] = []
    for rm in rms:
        q = cuadrante_vigente(db, rm.id, ciclo_id)
        if q is None:
            sin_evaluar.append({"rm_id": rm.id, "rm_nombre": rm.nombre})
        else:
            con_cuadrante.append((rm.id, q))

    orden = orden_por_roi(db, [rm_id for rm_id, _ in con_cuadrante],
                          ciclo_anterior_id(db, ciclo))
    quad = dict(con_cuadrante)

    celdas: list[dict] = []
    for idx, rm_id in enumerate(orden):
        q = quad[rm_id]
        dia = DIAS[idx % len(DIAS)]          # reparte los RM entre los días
        for semana in distribuir_semanas(frec.get(q, 0), semanas):
            celdas.append({"rm_id": rm_id, "rm_nombre": nombre[rm_id],
                           "semana": semana, "dia_semana": dia, "cuadrante": q})

    if persistir:
        # Borra solo lo sugerido (no publicado ni editado); conserva el trabajo del GD.
        (db.query(CalendarioCoachingSugerido)
         .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                 CalendarioCoachingSugerido.ciclo_id == ciclo_id,
                 CalendarioCoachingSugerido.publicado.is_(False),
                 CalendarioCoachingSugerido.editado_manualmente.is_(False))
         .delete(synchronize_session=False))
        db.flush()
        # RMs con celdas preservadas (publicadas/editadas): NO se re-agendan, o se
        # duplicarían con la nueva sugerencia.
        preservados = {rm_id for (rm_id,) in
                       db.query(CalendarioCoachingSugerido.rm_id)
                       .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                               CalendarioCoachingSugerido.ciclo_id == ciclo_id)
                       .distinct().all()}
        for c in celdas:
            if c["rm_id"] in preservados:
                continue
            db.add(CalendarioCoachingSugerido(
                gd_id=gd_id, ciclo_id=ciclo_id, rm_id=c["rm_id"], semana=c["semana"],
                dia_semana=c["dia_semana"], cuadrante_al_generar=c["cuadrante"]))
        db.commit()

    return {"semanas": semanas, "celdas": celdas, "sin_evaluar": sin_evaluar}
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -q`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: generar (frecuencia+ROI+reparto) con persistencia selectiva"
```

---

### Task 6: `listar`, `mover_celda`, `publicar`

**Files:**
- Modify: `backend/app/services/formacion_calendario_service.py`
- Test: `backend/tests/test_formacion_calendario.py`

**Interfaces:**
- Produces: `listar(db, gd_id, ciclo_id) -> list[CalendarioCoachingSugerido]`, `mover_celda(db, celda_id, semana, dia_semana) -> CalendarioCoachingSugerido`, `publicar(db, gd_id, ciclo_id) -> int`.

- [ ] **Step 1: Write the failing test**

```python
def test_mover_celda_la_marca_editada(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D4")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    celda = cal.listar(db, gd.id, ciclo.id)[0]
    m = cal.mover_celda(db, celda.id, semana=2, dia_semana="viernes")
    assert m.semana == 2 and m.dia_semana == "viernes" and m.editado_manualmente is True


def test_publicar_marca_todas_las_celdas(equipo):
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D1")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    n = cal.publicar(db, gd.id, ciclo.id)
    assert n == 4
    assert all(c.publicado for c in cal.listar(db, gd.id, ciclo.id))


def test_publicar_sobre_ciclo_cerrado_aborta(equipo):
    from app.services.recalculo_service import CicloCerradoError
    db, gd, a, ciclo = equipo["db"], equipo["gd"], equipo["rm_a"], equipo["ciclo"]
    _eval(db, a.id, ciclo.id, "D1")
    cal.generar(db, gd.id, ciclo.id, persistir=True)
    ciclo.cerrado = True; db.commit()
    with pytest.raises(CicloCerradoError):
        cal.publicar(db, gd.id, ciclo.id)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -k "mover or publicar" -q`
Expected: FAIL — `AttributeError: ... 'mover_celda'`.

- [ ] **Step 3: Write minimal implementation** (agrega al servicio)

```python
from datetime import datetime, timezone


def listar(db: Session, gd_id: int, ciclo_id: int) -> list[CalendarioCoachingSugerido]:
    return (db.query(CalendarioCoachingSugerido)
            .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                    CalendarioCoachingSugerido.ciclo_id == ciclo_id)
            .order_by(CalendarioCoachingSugerido.rm_id, CalendarioCoachingSugerido.semana)
            .all())


def mover_celda(db: Session, celda_id: int, semana: int,
                dia_semana: str) -> CalendarioCoachingSugerido:
    c = db.get(CalendarioCoachingSugerido, celda_id)
    if c is None:
        raise ValueError("Celda no encontrada")
    validar_ciclo_abierto(db, c.ciclo_id)
    if dia_semana not in DIAS:
        raise ValueError(f"Día inválido: {dia_semana}. Válidos: {', '.join(DIAS)}.")
    c.semana = semana
    c.dia_semana = dia_semana
    c.editado_manualmente = True
    db.commit()
    db.refresh(c)
    return c


def publicar(db: Session, gd_id: int, ciclo_id: int) -> int:
    validar_ciclo_abierto(db, ciclo_id)
    ahora = datetime.now(timezone.utc)
    filas = (db.query(CalendarioCoachingSugerido)
             .filter(CalendarioCoachingSugerido.gd_id == gd_id,
                     CalendarioCoachingSugerido.ciclo_id == ciclo_id).all())
    for c in filas:
        c.publicado = True
        c.publicado_en = ahora
    db.commit()
    return len(filas)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd backend && venv/Scripts/python.exe -m pytest tests/test_formacion_calendario.py -q`
Expected: PASS (todas).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_calendario_service.py backend/tests/test_formacion_calendario.py
git commit -m "feat(formacion) Calendario: listar, mover_celda (editado) y publicar"
```

---

### Task 7: Router `/formacion/calendario-coaching` + registro + RBAC

**Files:**
- Create: `backend/app/api/v1/routers/formacion_calendario.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Consumes: todo el servicio de las tareas 1-6. Auto-scope de GD por `Usuario.gerente_id`.

- [ ] **Step 1: Write the router**

```python
"""Calendario de Coaching (§7). Consume el cuadrante LSII vigente; no lo recalcula."""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_calendario_service as cal
from app.services.recalculo_service import CicloCerradoError

router = APIRouter(prefix="/formacion/calendario-coaching",
                   tags=["Formación — Calendario de Coaching"])

RequireEscritura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO))
RequireLectura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO,
    Rol.PRESIDENCIA, Rol.GERENTE_MEDICO, Rol.CAPACITACION))
RequireConfig = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


def _gd_scope(usuario: Usuario, gd_id: int | None) -> int:
    """GERENTE_DISTRITO se fuerza a su propio equipo; el resto debe indicar gd_id."""
    if usuario.rol == Rol.GERENTE_DISTRITO:
        propio = getattr(usuario, "gerente_id", None)
        if propio is None:
            raise HTTPException(status.HTTP_403_FORBIDDEN,
                                "Tu usuario no está enlazado a un Gerente de Distrito.")
        if gd_id is not None and gd_id != propio:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Solo puedes ver tu propio equipo.")
        return propio
    if gd_id is None:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Falta gd_id.")
    return gd_id


class GenerarEntrada(BaseModel):
    ciclo_id: int
    gd_id: int | None = None
    persistir: bool = True


class MoverEntrada(BaseModel):
    semana: int = Field(ge=1)
    dia_semana: str


class FrecuenciaEntrada(BaseModel):
    pais_codigo: str
    cuadrante: str
    visitas_por_ciclo: int = Field(ge=0)
    descripcion: str | None = None


def _celda(c) -> dict:
    return {"id": c.id, "gd_id": c.gd_id, "ciclo_id": c.ciclo_id, "rm_id": c.rm_id,
            "semana": c.semana, "dia_semana": c.dia_semana,
            "cuadrante": c.cuadrante_al_generar,
            "editado_manualmente": c.editado_manualmente, "publicado": c.publicado}


@router.post("/generar", summary="Generar (o previsualizar) el calendario del GD")
def generar(datos: GenerarEntrada, db: Session = Depends(get_db),
            usuario: Usuario = RequireEscritura):
    gd = _gd_scope(usuario, datos.gd_id)
    try:
        return cal.generar(db, gd, datos.ciclo_id, persistir=datos.persistir)
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("", summary="Calendario del GD/ciclo")
def listar(ciclo_id: int, gd_id: int | None = None, db: Session = Depends(get_db),
           usuario: Usuario = RequireLectura):
    gd = _gd_scope(usuario, gd_id)
    return [_celda(c) for c in cal.listar(db, gd, ciclo_id)]


@router.put("/celda/{celda_id}", summary="Mover una celda (día/semana)")
def mover(celda_id: int, datos: MoverEntrada, db: Session = Depends(get_db),
          usuario: Usuario = RequireEscritura):
    c = db.get(cal.CalendarioCoachingSugerido, celda_id)
    if c is not None:
        _gd_scope(usuario, c.gd_id)   # valida scope del GD dueño de la celda
    try:
        return _celda(cal.mover_celda(db, celda_id, datos.semana, datos.dia_semana))
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/publicar", summary="Publicar el calendario del GD/ciclo")
def publicar(datos: GenerarEntrada, db: Session = Depends(get_db),
             usuario: Usuario = RequireEscritura):
    gd = _gd_scope(usuario, datos.gd_id)
    try:
        return {"publicadas": cal.publicar(db, gd, datos.ciclo_id)}
    except CicloCerradoError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc


@router.get("/frecuencias", summary="Tabla de frecuencia vigente del país")
def frecuencias(pais_codigo: str, db: Session = Depends(get_db), _: Usuario = RequireLectura):
    return {"pais_codigo": pais_codigo, "valores": cal.frecuencias(db, pais_codigo),
            "cuadrantes": list(cal.CUADRANTES)}


@router.put("/frecuencias", summary="Fijar la frecuencia de un cuadrante para el país")
def fijar_frecuencia(datos: FrecuenciaEntrada, db: Session = Depends(get_db),
                     _: Usuario = RequireConfig):
    try:
        p = cal.fijar_frecuencia(db, datos.pais_codigo, datos.cuadrante,
                                 datos.visitas_por_ciclo, datos.descripcion)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"pais_codigo": p.pais_codigo, "cuadrante": p.cuadrante,
            "visitas_por_ciclo": p.visitas_por_ciclo, "descripcion": p.descripcion}
```

Añade `CalendarioCoachingSugerido` al espacio de nombres del servicio para el router: al inicio de `formacion_calendario_service.py` ya está importado (`from app.models.formacion import CalendarioCoachingSugerido`), así `cal.CalendarioCoachingSugerido` resuelve.

- [ ] **Step 2: Register the router** (modificar `backend/app/api/v1/router.py`)

Tras la línea `from app.api.v1.routers.formacion_brechas import router as formacion_brechas_router` añadir:
```python
from app.api.v1.routers.formacion_calendario import router as formacion_calendario_router
```
Tras `api_router.include_router(formacion_brechas_router)  # Plan de Cierre de Brechas ...` añadir:
```python
api_router.include_router(formacion_calendario_router)  # Calendario de Coaching (7) — consume el cuadrante LSII
```

- [ ] **Step 3: Verify the app imports and exposes the routes**

Run: `cd backend && venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'calendario-coaching' in getattr(r,'path','')])"`
Expected: imprime las 5 rutas (`/generar`, `` , `/celda/{celda_id}`, `/publicar`, `/frecuencias` ×2).

- [ ] **Step 4: Full suite green**

Run: `cd backend && venv/Scripts/python.exe -m pytest -q --no-header 2>&1 | tail -3`
Expected: todos los tests pasan (los ~1239 previos + los nuevos del calendario).

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/formacion_calendario.py backend/app/api/v1/router.py
git commit -m "feat(formacion) Calendario: router /formacion/calendario-coaching con auto-scope de GD"
```

---

### Task 8: Seed idempotente de frecuencias por país

**Files:**
- Create: `scripts/seed_frecuencia_lsii.py`

**Interfaces:**
- Consumes: `formacion_calendario_service.fijar_frecuencia`, `FRECUENCIA_DEFECTO`.

- [ ] **Step 1: Write the script**

```python
"""Seed idempotente de ParametroFrecuenciaLSII: carga la frecuencia de arranque
por país si aún no existe. Ejecutar: python scripts/seed_frecuencia_lsii.py"""
from app.db.database import SessionLocal
from app.models.dimensiones import Pais
from app.models.formacion import ParametroFrecuenciaLSII
from app.services import formacion_calendario_service as cal


def main() -> None:
    db = SessionLocal()
    try:
        paises = [p.codigo for p in db.query(Pais).all()]
        creadas = 0
        for pais in paises:
            existentes = {r.cuadrante for r in db.query(ParametroFrecuenciaLSII)
                          .filter(ParametroFrecuenciaLSII.pais_codigo == pais).all()}
            for cuadrante, visitas in cal.FRECUENCIA_DEFECTO.items():
                if cuadrante not in existentes:
                    cal.fijar_frecuencia(db, pais, cuadrante, visitas,
                                         descripcion="Valor de arranque §7.2")
                    creadas += 1
        print(f"Seed de frecuencias LSII: {creadas} fila(s) creada(s) en {len(paises)} país(es).")
    finally:
        db.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 2: Run the seed against the dev DB**

Run: `cd backend && venv/Scripts/python.exe ../scripts/seed_frecuencia_lsii.py`
Expected: imprime "Seed de frecuencias LSII revisado para N país(es)." sin error. Correrlo dos veces no duplica (idempotente).

- [ ] **Step 3: Commit**

```bash
git add scripts/seed_frecuencia_lsii.py
git commit -m "feat(formacion) Calendario: seed idempotente de frecuencias por pais"
```

---

### Task 9: Servicio frontend — funciones y tipos del calendario

**Files:**
- Modify: `frontend/src/services/formacion.service.ts`

**Interfaces:**
- Produces: tipos `CeldaCalendario`, `GenerarCalendarioResp`, `FrecuenciasLSII`; funciones `generarCalendario`, `listarCalendario`, `moverCelda`, `publicarCalendario`, `obtenerFrecuenciasLSII`, `fijarFrecuenciaLSII`.

- [ ] **Step 1: Append to the service file**

```typescript
// ── Calendario de Coaching (§7) ───────────────────────────────────────────
export interface CeldaCalendario {
  id: number; gd_id: number; ciclo_id: number; rm_id: number;
  semana: number; dia_semana: string; cuadrante: string | null;
  editado_manualmente: boolean; publicado: boolean;
}
export interface SinEvaluar { rm_id: number; rm_nombre: string; }
export interface GenerarCalendarioResp {
  semanas: number;
  celdas: { rm_id: number; rm_nombre: string; semana: number; dia_semana: string; cuadrante: string }[];
  sin_evaluar: SinEvaluar[];
}
export interface FrecuenciasLSII {
  pais_codigo: string; valores: Record<string, number>; cuadrantes: string[];
}

export const generarCalendario = (p: { ciclo_id: number; gd_id?: number | null; persistir?: boolean }) =>
  api.post<GenerarCalendarioResp>('/formacion/calendario-coaching/generar', { persistir: true, ...p })
    .then((r) => r.data);

export const listarCalendario = (params: { ciclo_id: number; gd_id?: number | null }) =>
  api.get<CeldaCalendario[]>('/formacion/calendario-coaching', {
    params: { ciclo_id: params.ciclo_id, ...(params.gd_id != null ? { gd_id: params.gd_id } : {}) },
  }).then((r) => r.data);

export const moverCelda = (celdaId: number, semana: number, dia_semana: string) =>
  api.put<CeldaCalendario>(`/formacion/calendario-coaching/celda/${celdaId}`, { semana, dia_semana })
    .then((r) => r.data);

export const publicarCalendario = (p: { ciclo_id: number; gd_id?: number | null }) =>
  api.post<{ publicadas: number }>('/formacion/calendario-coaching/publicar', p).then((r) => r.data);

export const obtenerFrecuenciasLSII = (paisCodigo: string) =>
  api.get<FrecuenciasLSII>('/formacion/calendario-coaching/frecuencias', {
    params: { pais_codigo: paisCodigo },
  }).then((r) => r.data);

export const fijarFrecuenciaLSII = (p: {
  pais_codigo: string; cuadrante: string; visitas_por_ciclo: number; descripcion?: string | null;
}) => api.put('/formacion/calendario-coaching/frecuencias', p).then((r) => r.data);
```

- [ ] **Step 2: Typecheck**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json`
Expected: sin errores.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/formacion.service.ts
git commit -m "feat(formacion) Calendario: capa de servicio frontend (tipos + endpoints)"
```

---

### Task 10: Página `CalendarioCoaching.tsx` + ruta + ítem de menú

**Files:**
- Create: `frontend/src/pages/formacion/CalendarioCoaching.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: las funciones del servicio de la Task 9; `useCicloStore` (`paisCodigo`, `cicloId`, `esSoloLectura`), `useAuthStore` (`rol`).

- [ ] **Step 1: Create the page** (cuadrícula RM×semanas, diálogo de frecuencias, patrón de la Fase 7 `PlanBrechas.tsx`)

```tsx
/**
 * CalendarioCoaching.tsx — Calendario de Coaching (§7).
 * Cuadrícula RM × semanas alimentada por el cuadrante LSII vigente. El GD ve su
 * equipo; ADMIN/GERPROD eligen GD. Editable y publicable; solo-lectura si el
 * ciclo está cerrado. La config de frecuencias va en un diálogo (patrón Umbrales
 * de la Fase 7).
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Chip, Button, Stack, Alert, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, MenuItem,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider,
} from '@mui/material';
import { AutoAwesome, Tune, PublishedWithChanges } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import {
  generarCalendario, listarCalendario, moverCelda, publicarCalendario,
  obtenerFrecuenciasLSII, fijarFrecuenciaLSII,
  type CeldaCalendario, type GenerarCalendarioResp,
} from '../../services/formacion.service';
import { api } from '../../services/api';

const DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'];
const ROLES_ESCRITURA = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'];
const CUAD_COLOR: Record<string, string> = {
  D1: '#c62828', D2: '#e65100', D3: '#1565c0', D4: '#2e7d32',
};

export default function CalendarioCoaching() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const soloLectura = useCicloStore((s) => s.esSoloLectura);
  const rol = useAuthStore((s) => s.rol);
  const esGD = rol === 'GERENTE_DISTRITO';
  const puedeEscribir = !!rol && ROLES_ESCRITURA.includes(rol) && !soloLectura;
  const qc = useQueryClient();

  const [gdId, setGdId] = useState<number | ''>('');
  const [frecAbierto, setFrecAbierto] = useState(false);
  const [previa, setPrevia] = useState<GenerarCalendarioResp | null>(null);

  // ADMIN/GERPROD eligen GD; el GD no ve el selector.
  const { data: gerentes } = useQuery({
    queryKey: ['gerentes', paisCodigo],
    queryFn: () => api.get('/admin/gerentes', { params: { pais_codigo: paisCodigo } }).then((r) => r.data),
    enabled: !!paisCodigo && !esGD,
  });

  const gdParam = esGD ? undefined : (gdId === '' ? undefined : Number(gdId));
  const listo = !!cicloId && (esGD || gdParam != null);

  const { data: celdas, isLoading } = useQuery({
    queryKey: ['calendario', cicloId, gdParam],
    queryFn: () => listarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    enabled: listo,
  });

  const generar = useMutation({
    mutationFn: () => generarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    onSuccess: (r) => { setPrevia(r); qc.invalidateQueries({ queryKey: ['calendario', cicloId] }); },
  });
  const publicar = useMutation({
    mutationFn: () => publicarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendario', cicloId] }),
  });
  const mover = useMutation({
    mutationFn: (v: { id: number; semana: number; dia: string }) => moverCelda(v.id, v.semana, v.dia),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendario', cicloId] }),
  });

  const semanas = previa?.semanas ?? Math.max(8, ...(celdas || []).map((c) => c.semana));
  const porRm = useMemo(() => {
    const m = new Map<number, CeldaCalendario[]>();
    for (const c of celdas || []) { if (!m.has(c.rm_id)) m.set(c.rm_id, []); m.get(c.rm_id)!.push(c); }
    return m;
  }, [celdas]);

  if (!paisCodigo) return <Alert severity="info" sx={{ m: 3 }}>Selecciona un país en el encabezado.</Alert>;

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={1}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Calendario de Coaching</Typography>
          <Typography variant="body2" color="text.secondary">
            Acompañamientos sugeridos por cuadrante LSII, repartidos en el ciclo.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          {!esGD && (
            <TextField select size="small" label="Gerente de Distrito" value={gdId}
              onChange={(e) => setGdId(e.target.value === '' ? '' : Number(e.target.value))} sx={{ minWidth: 200 }}>
              <MenuItem value="">—</MenuItem>
              {(gerentes || []).filter((g: any) => g.tipo === 'DISTRITO').map((g: any) => (
                <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>
              ))}
            </TextField>
          )}
          {puedeEscribir && (
            <>
              <Button variant="outlined" startIcon={<Tune />} onClick={() => setFrecAbierto(true)}>Frecuencias</Button>
              <Button variant="contained" startIcon={<AutoAwesome />} disabled={!listo || generar.isPending}
                onClick={() => generar.mutate()}>{generar.isPending ? 'Generando…' : 'Generar'}</Button>
              <Button variant="outlined" startIcon={<PublishedWithChanges />} disabled={!listo || publicar.isPending}
                onClick={() => publicar.mutate()}>Publicar</Button>
            </>
          )}
        </Stack>
      </Stack>

      {generar.isSuccess && previa && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => generar.reset()}>
          Calendario generado sobre {previa.semanas} semanas.
          {previa.sin_evaluar.length > 0 &&
            ` ${previa.sin_evaluar.length} RM sin evaluación LSII no se agendaron.`}
        </Alert>
      )}

      {!listo ? (
        <Alert severity="info">{esGD ? 'Selecciona un ciclo.' : 'Elige un Gerente de Distrito y un ciclo.'}</Alert>
      ) : isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : (celdas || []).length === 0 ? (
        <Alert severity="info">Sin calendario para este GD y ciclo. {puedeEscribir && 'Genera uno.'}</Alert>
      ) : (
        <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, overflowX: 'auto' }}>
          <CardContent>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>RM</TableCell>
                  {Array.from({ length: semanas }, (_, i) => (
                    <TableCell key={i} align="center">Sem {i + 1}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {[...porRm.entries()].map(([rmId, cs]) => {
                  const cuad = cs[0]?.cuadrante ?? '';
                  return (
                    <TableRow key={rmId}>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip size="small" label={cuad}
                            sx={{ bgcolor: CUAD_COLOR[cuad] || '#777', color: '#fff', fontWeight: 700 }} />
                          <span>RM #{rmId}</span>
                        </Stack>
                      </TableCell>
                      {Array.from({ length: semanas }, (_, i) => {
                        const c = cs.find((x) => x.semana === i + 1);
                        return (
                          <TableCell key={i} align="center">
                            {c ? (
                              <TextField select size="small" variant="standard" value={c.dia_semana}
                                disabled={!puedeEscribir || c.publicado}
                                onChange={(e) => mover.mutate({ id: c.id, semana: c.semana, dia: e.target.value })}>
                                {DIAS.map((d) => <MenuItem key={d} value={d}>{d.slice(0, 3)}</MenuItem>)}
                              </TextField>
                            ) : '·'}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {frecAbierto && paisCodigo && (
        <DialogoFrecuencias paisCodigo={paisCodigo} puedeEscribir={puedeEscribir}
          onCerrar={() => setFrecAbierto(false)} />
      )}
    </Box>
  );
}

function DialogoFrecuencias({ paisCodigo, puedeEscribir, onCerrar }: {
  paisCodigo: string; puedeEscribir: boolean; onCerrar: () => void;
}) {
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['frecuencias-lsii', paisCodigo],
    queryFn: () => obtenerFrecuenciasLSII(paisCodigo),
  });
  const [cuadrante, setCuadrante] = useState('');
  const [valor, setValor] = useState('');
  const fijar = useMutation({
    mutationFn: () => fijarFrecuenciaLSII({ pais_codigo: paisCodigo, cuadrante, visitas_por_ciclo: Number(valor) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['frecuencias-lsii', paisCodigo] }); setCuadrante(''); setValor(''); },
  });
  return (
    <Dialog open onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle>Frecuencia por cuadrante — {paisCodigo}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={0.5} sx={{ mb: 2 }}>
          {Object.entries(data?.valores || {}).map(([k, v]) => (
            <Stack key={k} direction="row" justifyContent="space-between">
              <Typography variant="body2" fontWeight={700}>{k}</Typography>
              <Typography variant="body2">{v} visita(s)/ciclo</Typography>
            </Stack>
          ))}
        </Stack>
        {puedeEscribir && (
          <>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" spacing={1}>
              <TextField select size="small" label="Cuadrante" value={cuadrante}
                onChange={(e) => setCuadrante(e.target.value)} sx={{ flex: 1 }}>
                {(data?.cuadrantes || []).map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
              <TextField size="small" type="number" label="Visitas" value={valor}
                onChange={(e) => setValor(e.target.value)} sx={{ width: 100 }} />
              <Button variant="contained" disabled={!cuadrante || valor === '' || fijar.isPending}
                onClick={() => fijar.mutate()}>Fijar</Button>
            </Stack>
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onCerrar}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 2: Register the route** (`frontend/src/App.tsx`)

Tras `const PlanBrechas = lazyWithReload(() => import('./pages/formacion/PlanBrechas'));` añadir:
```tsx
const CalendarioCoaching = lazyWithReload(() => import('./pages/formacion/CalendarioCoaching'));
```
Tras la `<Route path="formacion/brechas" ... />` añadir:
```tsx
<Route path="formacion/calendario" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','GERENTE_DISTRITO','PRESIDENCIA','GERENTE_MEDICO','CAPACITACION']}><CalendarioCoaching /></ProtectedRoute>} />
```

- [ ] **Step 3: Add the nav item** (`frontend/src/components/layout/Sidebar.tsx`, sección "Formación", tras "Plan de Brechas")

Importar un ícono en el bloque de `@mui/icons-material` (añadir `CalendarMonth,`). Luego el ítem:
```tsx
{ label: 'Calendario de Coaching', path: '/formacion/calendario', icon: <CalendarMonth />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'PRESIDENCIA', 'GERENTE_MEDICO', 'CAPACITACION'] },
```

- [ ] **Step 4: Typecheck + build**

Run: `cd frontend && npx tsc --noEmit -p tsconfig.json && npx vite build 2>&1 | tail -3`
Expected: sin errores de tipos; build OK; se emite el chunk `CalendarioCoaching-*.js`.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formacion/CalendarioCoaching.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(formacion) Calendario: vista frontend (cuadricula RM x semanas + frecuencias)"
```

---

### Task 11: Verificación en vivo y cierre

**Files:** ninguno (verificación).

- [ ] **Step 1: Backend + frontend arriba** (backend con `run_in_background`, frontend `npm run dev`); mintear JWT ADMIN e inyectar en `localStorage` (ver `[[preview-levanta-edicion-sqlserver]]` en memoria). Correr el seed de la Task 8 antes.

- [ ] **Step 2: Smoke por API** (token ADMIN): `GET /formacion/calendario-coaching/frecuencias?pais_codigo=DO` → 200 con `{D1:4,D2:3,D3:2,D4:1}`; `POST /generar {gd_id, ciclo_id, persistir:false}` → 200 con `celdas`/`sin_evaluar`. Con token REPRESENTANTE_MEDICO: cualquiera → 403.

- [ ] **Step 3: Navegador** (edición postgres): abrir `/formacion/calendario`, elegir un GD, Generar, verificar la cuadrícula, mover un día, Publicar. Sin errores de consola nuevos.

- [ ] **Step 4: Suite completa verde** (`pytest -q`) y `git status` limpio.

- [ ] **Step 5:** Handoff de deploy al usuario (push + comandos `git pull && docker compose --profile with-db up -d --build`). **No** auto-push sin confirmación.
