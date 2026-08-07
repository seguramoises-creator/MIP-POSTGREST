# Ranking de Formación — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar vida a `formacion.RankingFormacionPuntos` (hoy tabla fantasma): calcular y persistir los puntos de Formación de cada RM por ciclo desde sus 4 fuentes, llevar la racha de constancia, y mostrarlo con podio y desglose.

**Architecture:** Un servicio nuevo calcula los 4 componentes por (rm_id, ciclo_id) con pesos configurables por país (reutilizando `ParametroFormacion`), persiste con delete-then-insert y deriva la racha de los ciclos previos ya persistidos. Un router expone recálculo, ranking con auto-scope por rol, desglose propio y la config de pesos. El frontend añade una página con podio y tabla. **No se toca `motor_calculo_service.py` ni ningún cálculo del Score Integral.**

**Tech Stack:** Backend: Python 3.13, FastAPI, SQLAlchemy 2.0, pytest (PostgreSQL real). Frontend: React 18 + TypeScript, MUI v6, TanStack Query v5, axios, Zustand, react-router-dom v6 (`lazyWithReload`).

## Global Constraints

- **PROHIBIDO tocar `backend/app/services/motor_calculo_service.py`** ni ningún cálculo del Score Integral / ranking oficial / premios / elegibilidad. Este ranking es aditivo puro.
- **Sin migración**: `formacion.RankingFormacionPuntos` y `formacion.ParametroFormacion` ya existen.
- **La racha NO multiplica `puntos_total`** — se registra y se muestra, nada más.
- **El componente de Refuerzo no lleva peso propio**: se suma `RefuerzoRespuesta.puntos_obtenidos` tal cual (ya viene calculado por §10.6).
- **Campañas de refuerzo sin `ciclo_id` no suman** a ningún ciclo (la columna es nullable).
- Atribución por fecha (exámenes y onboarding no guardan `ciclo_id`): se usa el rango `Config.DIM_Ciclo.fecha_inicio … fecha_fin`. Para exámenes se usa `IntentoExamen.fecha_fin` (cuándo terminó), y los intentos sin `fecha_fin` no cuentan.
- `recalcular_ciclo` es **re-ejecutable** (delete-then-insert) y **no lleva guard de ciclo cerrado** (documentarlo en el docstring para que no parezca omisión).
- Pesos configurables siguiendo el patrón EXACTO de `formacion_brechas_service`: dict `PESOS_DEFECTO`, función `pesos(db, pais_codigo)` que superpone `ParametroFormacion`, y `fijar_peso(...)` que **rechaza claves desconocidas** con `ValueError`.
- Estilo backend: `Mapped`/`mapped_column` ya existentes (no se crean modelos), servicios reciben `db: Session` y no tocan HTTP, `from loguru import logger` si hace falta log, español en docstrings.
- Estilo frontend: MUI `sx`, React Query, español en el copy, `.then(r => r.data)` en el service. Referencias: `frontend/src/pages/formacion/refuerzo/KpiRefuerzo.tsx` (tarjetas + tablas) y `CampanasRefuerzo.tsx` (diálogos + `detalleError`).
- Tests automatizados SOLO en backend (Tasks 1-2). El frontend se verifica con `npm run build` + smoke.

---

### Task 1: Servicio — pesos configurables y cálculo de los 4 componentes

**Files:**
- Create: `backend/app/services/formacion_ranking_service.py`
- Test: `backend/tests/test_formacion_ranking.py`

**Interfaces:**
- Produce (para Tasks 2-3):
  - `PESOS_DEFECTO: dict[str, float]` con las claves `ranking_puntos_certificacion`, `ranking_puntos_examen`, `ranking_puntos_paso_onboarding`, `ranking_bono_ruta_completa`.
  - `pesos(db: Session, pais_codigo: str) -> dict[str, float]`
  - `fijar_peso(db: Session, pais_codigo: str, clave: str, valor: float, descripcion: str | None = None) -> ParametroFormacion` (lanza `ValueError` si la clave es desconocida)
  - `calcular_componentes(db: Session, rm_id: int, ciclo, pesos_pais: dict[str, float]) -> dict` → `{"puntos_certificacion", "puntos_examenes", "puntos_refuerzo", "puntos_onboarding", "puntos_total"}` (todos `int`). El parámetro `ciclo` es una instancia de `Config.DIM_Ciclo` (se usa `id`, `fecha_inicio`, `fecha_fin`).

- [ ] **Step 1: Escribir el archivo de tests con el escenario base**

Crear `backend/tests/test_formacion_ranking.py`. Sigue el patrón de fixtures de `backend/tests/test_formacion_onboarding_biblioteca.py` (base PostgreSQL desechable que se salta si no hay servidor):

```python
"""Ranking de Formación (§8) — cálculo de puntos por ciclo.

Necesita PostgreSQL real: el cálculo cruza cuatro esquemas (formacion, exam, DW,
Config) con joins y rangos de fecha; probarlo con dobles verificaría los dobles.
Si no hay base alcanzable se salta, como el resto de pruebas del módulo.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import (
    CapacitacionDim, Ciclo, Linea, Pais, RepresentanteMedico,
)
from app.models.exam_models import AsignacionExamen, Examen, IntentoExamen
from app.models.formacion import (
    ParametroFormacion, RankingFormacionPuntos, RefuerzoCampana, RefuerzoCapsula,
    RefuerzoRespuesta, RefuerzoRondaProgramada,
)
from app.models.hechos import CapacitacionFact
from app.models.usuario import Rol, Usuario
from app.services import formacion_ranking_service as ranking

BD_PRUEBA = "vista_test_ranking_form"


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
        pytest.skip(f"sin PostgreSQL alcanzable para pruebas de integración: {exc}")
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
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Un RM con un punto de cada fuente, dentro del ciclo 1.

    El ciclo 2 existe para probar la atribución por fecha: lo que caiga en él no
    debe sumar al ciclo 1.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    db.add(rm)
    c1 = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
               fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31))
    c2 = Ciclo(pais_codigo="DO", anio=2026, numero=2, nombre="Ciclo 2",
               fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28))
    db.add_all([c1, c2])
    db.flush()

    # 1 certificación aprobada en el ciclo 1. Ojo: `CapacitacionDim` NO lleva
    # pais_codigo (es un catálogo global); el país vive en el hecho.
    cert = CapacitacionDim(codigo="CERT1", nombre="Certificación Cardio",
                           tipo="CERTIFICACION")
    db.add(cert)
    db.flush()
    db.add(CapacitacionFact(pais_codigo="DO", rm_id=rm.id, capacitacion_id=cert.id,
                            ciclo_id=c1.id, asistio=True, aprobado=True))

    # 1 examen aprobado terminado dentro del ciclo 1. `Examen` exige autor
    # (`creado_por_usuario_id` es NOT NULL), así que hace falta un usuario.
    autor = Usuario(username="capacitacion_test", hashed_password="x",
                    nombre_completo="Capacitación de Prueba", rol=Rol.CAPACITACION)
    db.add(autor)
    db.flush()
    examen = Examen(nombre="Examen Cardio", estado="publicado",
                    creado_por_usuario_id=autor.id)
    db.add(examen)
    db.flush()
    asig = AsignacionExamen(examen_id=examen.id, evaluado_tipo="RM",
                            evaluado_rm_id=rm.id, estado="entregado")
    db.add(asig)
    db.flush()
    db.add(IntentoExamen(asignacion_id=asig.id, evaluado_tipo="RM",
                         evaluado_rm_id=rm.id, fecha_inicio=datetime(2026, 1, 10, 9, 0),
                         fecha_fin=datetime(2026, 1, 10, 10, 0), score=90, aprobado=True))

    # Refuerzo: campaña del ciclo 1 con una respuesta de 8 puntos.
    campana = RefuerzoCampana(pais_codigo="DO", nombre="Campaña 1", ciclo_id=c1.id,
                             duracion_dias=30, modo_espaciado="creciente")
    db.add(campana)
    db.flush()
    ronda = RefuerzoRondaProgramada(campana_id=campana.id, numero_ronda=1,
                                    publicada=True)
    db.add(ronda)
    db.flush()
    capsula = RefuerzoCapsula(ronda_id=ronda.id, formato="microlectura",
                              enunciado="Lee esto", orden=1)
    db.add(capsula)
    db.flush()
    db.add(RefuerzoRespuesta(
        ronda_id=ronda.id, capsula_id=capsula.id, rm_id=rm.id,
        timestamp_recibido=datetime(2026, 1, 5, 9, 0),
        timestamp_respondido=datetime(2026, 1, 5, 9, 2),
        tiempo_respuesta_seg=120, puntos_obtenidos=8))
    db.commit()
    return {"db": db, "rm": rm, "c1": c1, "c2": c2, "linea": linea,
            "examen": examen, "asignacion": asig}
```

- [ ] **Step 2: Añadir el primer test (los 4 componentes) al final del archivo**

```python
def test_calcula_los_cuatro_componentes(escenario):
    """Certificación 50 + examen 30 + refuerzo 8 + onboarding 0 = 88."""
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    p = ranking.pesos(db, "DO")

    r = ranking.calcular_componentes(db, rm.id, c1, p)

    assert r["puntos_certificacion"] == 50
    assert r["puntos_examenes"] == 30
    assert r["puntos_refuerzo"] == 8
    assert r["puntos_onboarding"] == 0
    assert r["puntos_total"] == 88


def test_examen_fuera_del_ciclo_no_suma(escenario):
    """La atribución es por fecha: un intento terminado en el ciclo 2 no cuenta
    en el ciclo 1, aunque sea del mismo RM."""
    db, rm, c1, c2 = (escenario["db"], escenario["rm"],
                      escenario["c1"], escenario["c2"])
    db.add(IntentoExamen(asignacion_id=escenario["asignacion"].id, evaluado_tipo="RM",
                         evaluado_rm_id=rm.id,
                         fecha_inicio=datetime(2026, 2, 10, 9, 0),
                         fecha_fin=datetime(2026, 2, 10, 10, 0),
                         score=95, aprobado=True))
    db.commit()
    p = ranking.pesos(db, "DO")

    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_examenes"] == 30
    assert ranking.calcular_componentes(db, rm.id, c2, p)["puntos_examenes"] == 30


def test_campana_sin_ciclo_no_suma(escenario):
    """`RefuerzoCampana.ciclo_id` es nullable: sin ciclo no se atribuye a ninguno,
    en vez de repartirla por fecha y arriesgar contarla dos veces."""
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    huerfana = RefuerzoCampana(pais_codigo="DO", nombre="Sin ciclo", ciclo_id=None,
                               duracion_dias=30, modo_espaciado="creciente")
    db.add(huerfana)
    db.flush()
    ronda = RefuerzoRondaProgramada(campana_id=huerfana.id, numero_ronda=1,
                                    publicada=True)
    db.add(ronda)
    db.flush()
    capsula = RefuerzoCapsula(ronda_id=ronda.id, formato="microlectura",
                              enunciado="Huérfana", orden=1)
    db.add(capsula)
    db.flush()
    db.add(RefuerzoRespuesta(
        ronda_id=ronda.id, capsula_id=capsula.id, rm_id=rm.id,
        timestamp_recibido=datetime(2026, 1, 6, 9, 0),
        timestamp_respondido=datetime(2026, 1, 6, 9, 1),
        tiempo_respuesta_seg=60, puntos_obtenidos=99))
    db.commit()
    p = ranking.pesos(db, "DO")

    # Sigue siendo 8: los 99 de la campaña sin ciclo no entran.
    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_refuerzo"] == 8


def test_pesos_configurados_sobrescriben_los_de_defecto(escenario):
    db, rm, c1 = escenario["db"], escenario["rm"], escenario["c1"]
    ranking.fijar_peso(db, "DO", "ranking_puntos_certificacion", 100.0)

    p = ranking.pesos(db, "DO")
    assert p["ranking_puntos_certificacion"] == 100.0
    assert ranking.calcular_componentes(db, rm.id, c1, p)["puntos_certificacion"] == 100


def test_fijar_peso_rechaza_clave_desconocida(escenario):
    with pytest.raises(ValueError, match="Peso desconocido"):
        ranking.fijar_peso(escenario["db"], "DO", "peso_inventado", 1.0)
```

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `cd backend && python -m pytest tests/test_formacion_ranking.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.formacion_ranking_service'`.
(Si no hay PostgreSQL alcanzable se SALTAN — anótalo en el reporte y continúa.)

- [ ] **Step 4: Crear el servicio con los pesos y el cálculo**

Crear `backend/app/services/formacion_ranking_service.py`:

```python
"""Ranking de Formación (§8).

Los puntos que un representante acumula por formarse: certificaciones, exámenes,
refuerzo de memoria y avance de su ruta de inducción. Se guardan los cuatro
componentes por separado (§8.2) para que el RM vea DE DÓNDE sale su posición.

QUÉ NO HACE ESTE MÓDULO
------------------------
No toca el Score Integral ni el ranking oficial (`motor_calculo_service`): este
ranking es motivacional y aditivo. Cambiar el Score redefiniría premios,
comisiones y la comparabilidad del histórico de todos los representantes, que es
justo lo que se decidió evitar.
"""
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.dimensiones import CapacitacionDim, Ciclo, RepresentanteMedico
from app.models.exam_models import IntentoExamen
from app.models.formacion import (
    OnboardingAsignacion, OnboardingPasoProgreso, ParametroFormacion,
    RankingFormacionPuntos, RefuerzoCampana, RefuerzoRespuesta,
    RefuerzoRondaProgramada,
)
from app.models.hechos import CapacitacionFact

#: Valores de arranque. Cualquiera se sobrescribe por país escribiendo una fila
#: en `formacion.ParametroFormacion`, sin tocar código.
PESOS_DEFECTO: dict[str, float] = {
    "ranking_puntos_certificacion": 50.0,
    "ranking_puntos_examen": 30.0,
    "ranking_puntos_paso_onboarding": 5.0,
    "ranking_bono_ruta_completa": 25.0,
}


def pesos(db: Session, pais_codigo: str) -> dict[str, float]:
    """Los de arranque, con las sobrescrituras que haya configurado el país."""
    valores = dict(PESOS_DEFECTO)
    for p in (db.query(ParametroFormacion)
              .filter(ParametroFormacion.pais_codigo == pais_codigo).all()):
        if p.clave in valores:
            valores[p.clave] = float(p.valor)
    return valores


def fijar_peso(db: Session, pais_codigo: str, clave: str, valor: float,
               descripcion: str | None = None) -> ParametroFormacion:
    if clave not in PESOS_DEFECTO:
        raise ValueError(
            f"Peso desconocido: {clave}. Válidos: {', '.join(sorted(PESOS_DEFECTO))}.")
    p = (db.query(ParametroFormacion)
         .filter(ParametroFormacion.pais_codigo == pais_codigo,
                 ParametroFormacion.clave == clave).first())
    if p is None:
        p = ParametroFormacion(pais_codigo=pais_codigo, clave=clave,
                               valor=Decimal(str(valor)), descripcion=descripcion)
        db.add(p)
    else:
        p.valor = Decimal(str(valor))
        if descripcion:
            p.descripcion = descripcion
    db.commit()
    db.refresh(p)
    return p


def _dia_siguiente(d: date) -> date:
    """`DIM_Ciclo.fecha_fin` es un DATE y los eventos son DATETIME: comparar con
    `<= fecha_fin` dejaría fuera todo lo ocurrido ese último día después de las
    00:00. Se compara contra el día siguiente en su lugar."""
    from datetime import timedelta
    return d + timedelta(days=1)


def _puntos_certificacion(db: Session, rm_id: int, ciclo: Ciclo, peso: float) -> int:
    n = (db.query(CapacitacionFact)
         .join(CapacitacionDim, CapacitacionFact.capacitacion_id == CapacitacionDim.id)
         .filter(CapacitacionFact.rm_id == rm_id,
                 CapacitacionFact.ciclo_id == ciclo.id,
                 CapacitacionFact.aprobado.is_(True),
                 CapacitacionDim.tipo == "CERTIFICACION")
         .count())
    return int(n * peso)


def _puntos_examenes(db: Session, rm_id: int, ciclo: Ciclo, peso: float) -> int:
    """Atribución por fecha: `IntentoExamen` no guarda ciclo.

    Se usa `fecha_fin` (cuándo terminó el intento) porque el mérito es haberlo
    aprobado; los intentos abandonados (sin `fecha_fin`) no cuentan.
    """
    n = (db.query(IntentoExamen)
         .filter(IntentoExamen.evaluado_rm_id == rm_id,
                 IntentoExamen.aprobado.is_(True),
                 IntentoExamen.fecha_fin.isnot(None),
                 IntentoExamen.fecha_fin >= ciclo.fecha_inicio,
                 IntentoExamen.fecha_fin < _dia_siguiente(ciclo.fecha_fin))
         .count())
    return int(n * peso)


def _puntos_refuerzo(db: Session, rm_id: int, ciclo: Ciclo) -> int:
    """Suma los puntos ya calculados por §10.6 — sin multiplicador propio.

    Solo cuentan las campañas atribuidas a este ciclo: `RefuerzoCampana.ciclo_id`
    es nullable y una campaña sin ciclo no pertenece a ninguno.
    """
    filas = (db.query(RefuerzoRespuesta)
             .join(RefuerzoRondaProgramada,
                   RefuerzoRespuesta.ronda_id == RefuerzoRondaProgramada.id)
             .join(RefuerzoCampana,
                   RefuerzoRondaProgramada.campana_id == RefuerzoCampana.id)
             .filter(RefuerzoRespuesta.rm_id == rm_id,
                     RefuerzoCampana.ciclo_id == ciclo.id)
             .all())
    return int(sum(f.puntos_obtenidos or 0 for f in filas))


def _puntos_onboarding(db: Session, rm_id: int, ciclo: Ciclo,
                       peso_paso: float, bono_ruta: float) -> int:
    """Pasos completados dentro del ciclo, más el bono si la ruta se cerró aquí."""
    limite = _dia_siguiente(ciclo.fecha_fin)
    pasos = (db.query(OnboardingPasoProgreso)
             .join(OnboardingAsignacion,
                   OnboardingPasoProgreso.asignacion_id == OnboardingAsignacion.id)
             .filter(OnboardingAsignacion.rm_id == rm_id,
                     OnboardingPasoProgreso.completado.is_(True),
                     OnboardingPasoProgreso.completado_en.isnot(None),
                     OnboardingPasoProgreso.completado_en >= ciclo.fecha_inicio,
                     OnboardingPasoProgreso.completado_en < limite)
             .count())
    rutas = (db.query(OnboardingAsignacion)
             .filter(OnboardingAsignacion.rm_id == rm_id,
                     OnboardingAsignacion.completada_en.isnot(None),
                     OnboardingAsignacion.completada_en >= ciclo.fecha_inicio,
                     OnboardingAsignacion.completada_en < limite)
             .count())
    return int(pasos * peso_paso + rutas * bono_ruta)


def calcular_componentes(db: Session, rm_id: int, ciclo: Ciclo,
                         pesos_pais: dict[str, float]) -> dict:
    """Los cuatro componentes del §8.2 y su total, para un RM en un ciclo."""
    cert = _puntos_certificacion(db, rm_id, ciclo,
                                 pesos_pais["ranking_puntos_certificacion"])
    exam = _puntos_examenes(db, rm_id, ciclo, pesos_pais["ranking_puntos_examen"])
    ref = _puntos_refuerzo(db, rm_id, ciclo)
    onb = _puntos_onboarding(db, rm_id, ciclo,
                             pesos_pais["ranking_puntos_paso_onboarding"],
                             pesos_pais["ranking_bono_ruta_completa"])
    return {"puntos_certificacion": cert, "puntos_examenes": exam,
            "puntos_refuerzo": ref, "puntos_onboarding": onb,
            "puntos_total": cert + exam + ref + onb}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `cd backend && python -m pytest tests/test_formacion_ranking.py -v`
Expected: 5 passed (o SKIPPED si no hay PostgreSQL).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/formacion_ranking_service.py backend/tests/test_formacion_ranking.py
git commit -m "feat(formacion) Ranking: pesos configurables y calculo de los 4 componentes"
```

---

### Task 2: Servicio — persistencia, racha y lectura del ranking

**Files:**
- Modify: `backend/app/services/formacion_ranking_service.py`
- Test: `backend/tests/test_formacion_ranking.py`

**Interfaces:**
- Consumes: `pesos`, `calcular_componentes` de Task 1.
- Produce (para Task 3):
  - `recalcular_ciclo(db: Session, ciclo_id: int, pais_codigo: str) -> dict` → `{"ciclo_id", "rms_procesados", "puntos_totales"}`
  - `ranking(db: Session, ciclo_id: int, rm_ids: list[int] | None = None) -> list[dict]` → filas con `posicion`, `rm_id`, `rm_nombre`, los 4 componentes, `puntos_total`, `racha_ciclos`
  - `mis_puntos(db: Session, rm_id: int, ciclo_id: int) -> dict | None` → la fila del RM o `None` si no hay cálculo

- [ ] **Step 1: Añadir los tests de persistencia y racha al final del archivo de tests**

```python
def test_recalcular_es_reejecutable(escenario):
    """Delete-then-insert: correrlo dos veces no duplica ni acumula."""
    db, c1 = escenario["db"], escenario["c1"]

    r1 = ranking.recalcular_ciclo(db, c1.id, "DO")
    r2 = ranking.recalcular_ciclo(db, c1.id, "DO")

    assert r1["rms_procesados"] == 1
    assert r2["rms_procesados"] == 1
    filas = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c1.id).all()
    assert len(filas) == 1
    assert filas[0].puntos_total == 88


def test_racha_cuenta_ciclos_consecutivos_y_se_corta(escenario):
    """La racha mira hacia atrás y se detiene en el primer ciclo sin puntos.

    El ciclo 2 no tiene actividad, así que al calcularlo la racha vuelve a 0
    aunque el ciclo 1 sí tuviera puntos.
    """
    db, c1, c2 = escenario["db"], escenario["c1"], escenario["c2"]

    ranking.recalcular_ciclo(db, c1.id, "DO")
    ranking.recalcular_ciclo(db, c2.id, "DO")

    fila_c1 = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c1.id).one()
    fila_c2 = db.query(RankingFormacionPuntos).filter(
        RankingFormacionPuntos.ciclo_id == c2.id).one()
    assert fila_c1.racha_ciclos == 1      # su propio ciclo con puntos
    assert fila_c2.puntos_total == 0
    assert fila_c2.racha_ciclos == 0      # sin puntos, la racha se corta


def test_ranking_ordena_y_numera(escenario):
    """Un segundo RM sin actividad debe quedar detrás, con posición 2."""
    db, c1, linea = escenario["db"], escenario["c1"], escenario["linea"]
    otro = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                               codigo="VM02", nombre="Representante Dos")
    db.add(otro)
    db.commit()
    ranking.recalcular_ciclo(db, c1.id, "DO")

    filas = ranking.ranking(db, c1.id)

    assert [f["posicion"] for f in filas] == [1, 2]
    assert filas[0]["rm_nombre"] == "Representante Uno"
    assert filas[0]["puntos_total"] == 88
    assert filas[1]["puntos_total"] == 0


def test_ranking_filtra_por_rm_ids(escenario):
    """El auto-scope del GD se aplica en la lectura, no en el cálculo."""
    db, c1, rm = escenario["db"], escenario["c1"], escenario["rm"]
    ranking.recalcular_ciclo(db, c1.id, "DO")

    filas = ranking.ranking(db, c1.id, rm_ids=[rm.id])

    assert len(filas) == 1
    assert filas[0]["rm_id"] == rm.id
```

Nota: `RepresentanteMedico` ya está importado en el archivo (Step 1 de Task 1).

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && python -m pytest tests/test_formacion_ranking.py -k "recalcular or racha or ordena or filtra" -v`
Expected: FAIL con `AttributeError: module 'app.services.formacion_ranking_service' has no attribute 'recalcular_ciclo'`.

- [ ] **Step 3: Añadir persistencia, racha y lectura al servicio**

Añadir al final de `backend/app/services/formacion_ranking_service.py`:

```python
def _racha(db: Session, rm_id: int, ciclo: Ciclo) -> int:
    """Ciclos consecutivos con actividad, contando hacia atrás desde `ciclo`.

    Se apoya en lo ya persistido: por eso `recalcular_ciclo` guarda primero los
    puntos y calcula la racha después. Si el ciclo actual no tiene puntos, la
    racha es 0 — la constancia se rompe, no se congela.
    """
    previos = (db.query(Ciclo)
               .filter(Ciclo.pais_codigo == ciclo.pais_codigo,
                       (Ciclo.anio < ciclo.anio) |
                       ((Ciclo.anio == ciclo.anio) & (Ciclo.numero <= ciclo.numero)))
               .order_by(Ciclo.anio.desc(), Ciclo.numero.desc())
               .all())
    racha = 0
    for c in previos:
        fila = (db.query(RankingFormacionPuntos)
                .filter(RankingFormacionPuntos.rm_id == rm_id,
                        RankingFormacionPuntos.ciclo_id == c.id).first())
        if fila is None or fila.puntos_total <= 0:
            break
        racha += 1
    return racha


def recalcular_ciclo(db: Session, ciclo_id: int, pais_codigo: str) -> dict:
    """Recalcula y persiste los puntos de todos los RM del país en un ciclo.

    Delete-then-insert, así que es re-ejecutable: correrlo dos veces da lo mismo.

    NO lleva guard de ciclo cerrado, a diferencia del motor de Score: aquí
    recalcular no mueve premios ni comisiones, y poder recomputar un ciclo ya
    cerrado es útil cuando las certificaciones se cargan con retraso.
    """
    ciclo = db.get(Ciclo, ciclo_id)
    if ciclo is None:
        raise ValueError("Ciclo no encontrado")
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.pais_codigo == pais_codigo).all())
    pesos_pais = pesos(db, pais_codigo)

    ids = [r.id for r in rms]
    if ids:
        (db.query(RankingFormacionPuntos)
         .filter(RankingFormacionPuntos.ciclo_id == ciclo_id,
                 RankingFormacionPuntos.rm_id.in_(ids))
         .delete(synchronize_session=False))
    total_general = 0
    for rm in rms:
        comp = calcular_componentes(db, rm.id, ciclo, pesos_pais)
        db.add(RankingFormacionPuntos(rm_id=rm.id, ciclo_id=ciclo_id, **comp))
        total_general += comp["puntos_total"]
    db.commit()

    # La racha se calcula DESPUÉS de persistir: lee los ciclos ya guardados,
    # incluido el actual.
    for rm in rms:
        fila = (db.query(RankingFormacionPuntos)
                .filter(RankingFormacionPuntos.rm_id == rm.id,
                        RankingFormacionPuntos.ciclo_id == ciclo_id).first())
        if fila is not None:
            fila.racha_ciclos = _racha(db, rm.id, ciclo)
    db.commit()

    return {"ciclo_id": ciclo_id, "rms_procesados": len(rms),
            "puntos_totales": total_general}


def ranking(db: Session, ciclo_id: int, rm_ids: list[int] | None = None) -> list[dict]:
    """Ranking del ciclo, ordenado. `posicion` se calcula al leer y no se
    persiste: así recalcular a un RM no obliga a reescribir filas ajenas."""
    q = (db.query(RankingFormacionPuntos, RepresentanteMedico)
         .join(RepresentanteMedico,
               RankingFormacionPuntos.rm_id == RepresentanteMedico.id)
         .filter(RankingFormacionPuntos.ciclo_id == ciclo_id))
    if rm_ids is not None:
        q = q.filter(RankingFormacionPuntos.rm_id.in_(rm_ids or [-1]))
    # Empates por rm_id ascendente para que el orden sea estable entre llamadas.
    filas = q.order_by(RankingFormacionPuntos.puntos_total.desc(),
                       RankingFormacionPuntos.rm_id.asc()).all()
    return [{
        "posicion": i + 1, "rm_id": p.rm_id, "rm_nombre": rm.nombre,
        "puntos_certificacion": p.puntos_certificacion,
        "puntos_examenes": p.puntos_examenes,
        "puntos_refuerzo": p.puntos_refuerzo,
        "puntos_onboarding": p.puntos_onboarding,
        "puntos_total": p.puntos_total, "racha_ciclos": p.racha_ciclos,
    } for i, (p, rm) in enumerate(filas)]


def mis_puntos(db: Session, rm_id: int, ciclo_id: int) -> dict | None:
    """El desglose propio del RM, o None si el ciclo no se ha calculado."""
    for fila in ranking(db, ciclo_id):
        if fila["rm_id"] == rm_id:
            return fila
    return None
```

- [ ] **Step 4: Correr toda la suite del archivo**

Run: `cd backend && python -m pytest tests/test_formacion_ranking.py -v`
Expected: 9 passed (o SKIPPED si no hay PostgreSQL).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/formacion_ranking_service.py backend/tests/test_formacion_ranking.py
git commit -m "feat(formacion) Ranking: persistencia re-ejecutable, racha y lectura ordenada"
```

---

### Task 3: Router `/formacion/ranking`

**Files:**
- Create: `backend/app/api/v1/routers/formacion_ranking.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Consumes: `pesos`, `fijar_peso`, `recalcular_ciclo`, `ranking`, `mis_puntos` del servicio (Tasks 1-2).
- Produce (para Task 4): los 5 endpoints de §5 del spec.

- [ ] **Step 1: Crear el router**

Crear `backend/app/api/v1/routers/formacion_ranking.py`:

```python
"""Ranking de Formación (§8) — el podio del módulo.

Es un ranking PROPIO: no alimenta el Score Integral ni los premios (ver el
docstring de `formacion_ranking_service`). Por eso su recálculo es una acción
manual de Capacitación y no un paso del ETL.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.authz import scope
from app.core.authz.constantes import Alcance
from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import formacion_ranking_service as ranking_srv

router = APIRouter(prefix="/formacion/ranking", tags=["Formación — Ranking"])

RequireCapacitacion = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))
RequireAnyAuth = Depends(get_current_active_user)

#: Quién ve el ranking completo del país. El representante TAMBIÉN lo ve entero:
#: un podio en el que cada quien solo se ve a sí mismo no es un podio.
_VEN_TODO = {Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION,
             Rol.PRESIDENCIA, Rol.GERENTE_MEDICO, Rol.REPRESENTANTE_MEDICO}


class PesoEntrada(BaseModel):
    pais_codigo: str
    clave: str
    valor: float
    descripcion: str | None = None


def _rm_propio(usuario: Usuario) -> int:
    rm_id = getattr(usuario, "rm_id", None)
    if rm_id is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu usuario no está enlazado a un representante.")
    return rm_id


@router.post("/recalcular", summary="Recalcular los puntos del ciclo")
def recalcular(ciclo_id: int, pais_codigo: str, db: Session = Depends(get_db),
               _: Usuario = RequireCapacitacion):
    try:
        return ranking_srv.recalcular_ciclo(db, ciclo_id, pais_codigo)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("", summary="Ranking de Formación del ciclo")
def listar(ciclo_id: int, db: Session = Depends(get_db),
           usuario: Usuario = RequireAnyAuth):
    """El Gerente de Distrito ve solo su equipo; los demás roles, todo el país."""
    if usuario.rol in _VEN_TODO:
        rm_ids = None
    elif usuario.rol == Rol.GERENTE_DISTRITO:
        visibles = scope.rm_ids_visibles(db, usuario, Alcance.TEAM)
        rm_ids = sorted(visibles) if visibles is not None else None
    else:
        raise HTTPException(status.HTTP_403_FORBIDDEN,
                            "Tu rol no tiene acceso al Ranking de Formación.")
    return ranking_srv.ranking(db, ciclo_id, rm_ids)


@router.get("/mis-puntos", summary="Mi desglose de puntos del ciclo")
def mis_puntos(ciclo_id: int, db: Session = Depends(get_db),
               usuario: Usuario = RequireAnyAuth):
    return ranking_srv.mis_puntos(db, _rm_propio(usuario), ciclo_id)


@router.get("/pesos", summary="Pesos vigentes del país")
def ver_pesos(pais_codigo: str, db: Session = Depends(get_db),
              _: Usuario = RequireAnyAuth):
    return ranking_srv.pesos(db, pais_codigo)


@router.put("/pesos", summary="Fijar un peso")
def fijar_peso(datos: PesoEntrada, db: Session = Depends(get_db),
               _: Usuario = RequireCapacitacion):
    try:
        p = ranking_srv.fijar_peso(db, datos.pais_codigo, datos.clave,
                                   datos.valor, datos.descripcion)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    return {"clave": p.clave, "valor": float(p.valor)}
```

- [ ] **Step 2: Registrar el router**

En `backend/app/api/v1/router.py`, junto a los otros imports de formación:
```python
from app.api.v1.routers.formacion_ranking import router as formacion_ranking_router
```
Y junto a los otros `include_router` de formación:
```python
api_router.include_router(formacion_ranking_router)  # Ranking de Formacion (8) — no toca el Score Integral
```

- [ ] **Step 3: Verificar que la app carga y la suite sigue verde**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'ranking' in r.path])"`
Expected: imprime las 5 rutas nuevas bajo `/api/v1/formacion/ranking`.

Run: `cd backend && python -m pytest tests/test_formacion_ranking.py -v`
Expected: 9 passed (o SKIPPED).

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/formacion_ranking.py backend/app/api/v1/router.py
git commit -m "feat(formacion) Ranking: router /formacion/ranking con auto-scope por rol"
```

---

### Task 4: Service frontend `rankingFormacion.service.ts`

**Files:**
- Create: `frontend/src/services/rankingFormacion.service.ts`

**Interfaces:**
- Produce (para Task 5): tipos `FilaRankingFormacion`, `PesosRanking`; funciones `listarRankingFormacion`, `misPuntosFormacion`, `recalcularRankingFormacion`, `pesosRankingFormacion`, `fijarPesoRankingFormacion`.

- [ ] **Step 1: Crear el archivo completo**

```ts
/**
 * rankingFormacion.service.ts — Ranking de Formación (§8).
 * Rutas exactas del router backend `/formacion/ranking`.
 *
 * Es un ranking PROPIO del módulo: no alimenta el Score Integral ni los premios.
 */
import { api } from './api';

export interface FilaRankingFormacion {
  posicion: number; rm_id: number; rm_nombre: string;
  puntos_certificacion: number; puntos_examenes: number;
  puntos_refuerzo: number; puntos_onboarding: number;
  puntos_total: number; racha_ciclos: number;
}

export interface PesosRanking {
  ranking_puntos_certificacion: number;
  ranking_puntos_examen: number;
  ranking_puntos_paso_onboarding: number;
  ranking_bono_ruta_completa: number;
}

export const listarRankingFormacion = (cicloId: number) =>
  api.get<FilaRankingFormacion[]>('/formacion/ranking', { params: { ciclo_id: cicloId } })
    .then((r) => r.data);

export const misPuntosFormacion = (cicloId: number) =>
  api.get<FilaRankingFormacion | null>('/formacion/ranking/mis-puntos',
    { params: { ciclo_id: cicloId } }).then((r) => r.data);

export const recalcularRankingFormacion = (cicloId: number, paisCodigo: string) =>
  api.post<{ ciclo_id: number; rms_procesados: number; puntos_totales: number }>(
    '/formacion/ranking/recalcular', null,
    { params: { ciclo_id: cicloId, pais_codigo: paisCodigo } }).then((r) => r.data);

export const pesosRankingFormacion = (paisCodigo: string) =>
  api.get<PesosRanking>('/formacion/ranking/pesos', { params: { pais_codigo: paisCodigo } })
    .then((r) => r.data);

export const fijarPesoRankingFormacion = (body: {
  pais_codigo: string; clave: string; valor: number; descripcion?: string | null;
}) => api.put<{ clave: string; valor: number }>('/formacion/ranking/pesos', body)
  .then((r) => r.data);
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/rankingFormacion.service.ts
git commit -m "feat(formacion) Ranking: capa de servicio frontend"
```

---

### Task 5: Página `RankingFormacion.tsx` + ruta + sidebar

**Files:**
- Create: `frontend/src/pages/formacion/RankingFormacion.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: todo el service de Task 4; `useCicloStore` (`paisCodigo`, `cicloId`), `useAuthStore` (`rol`).

- [ ] **Step 1: Crear la página**

```tsx
/**
 * RankingFormacion.tsx — El podio del módulo de Formación (§8).
 * Muestra de dónde salen los puntos (los 4 componentes por separado) para que la
 * posición sea explicable, no un número opaco.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Card, CardContent, Grid, CircularProgress, Snackbar,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
} from '@mui/material';
import { Refresh, Tune, EmojiEvents, LocalFireDepartment } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import {
  listarRankingFormacion, misPuntosFormacion, recalcularRankingFormacion,
  pesosRankingFormacion, fijarPesoRankingFormacion,
  type FilaRankingFormacion, type PesosRanking,
} from '../../services/rankingFormacion.service';

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o string.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

const ROLES_GESTION = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION'];
const MEDALLA = ['🥇', '🥈', '🥉'];

export default function RankingFormacion() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const rol = useAuthStore((s) => s.rol);
  const puedeGestionar = !!rol && ROLES_GESTION.includes(rol);
  const [pesos, setPesos] = useState(false);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const tabla = useQuery({
    queryKey: ['ranking-formacion', cicloId],
    queryFn: () => listarRankingFormacion(cicloId as number),
    enabled: cicloId != null,
  });
  // Si el usuario no está enlazado a un representante el backend da 403: la
  // tarjeta simplemente no se muestra, no es un error que interrumpa la pantalla.
  const mios = useQuery({
    queryKey: ['ranking-formacion-mis-puntos', cicloId],
    queryFn: () => misPuntosFormacion(cicloId as number),
    enabled: cicloId != null,
    retry: false,
  });

  const recalcular = useMutation({
    mutationFn: () => recalcularRankingFormacion(cicloId as number, paisCodigo as string),
    onSuccess: (r) => {
      setAviso({ sev: 'success', msg: `Recalculado: ${r.rms_procesados} representante(s), ${r.puntos_totales} puntos.` });
      qc.invalidateQueries({ queryKey: ['ranking-formacion'] });
      qc.invalidateQueries({ queryKey: ['ranking-formacion-mis-puntos'] });
    },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo recalcular.') }),
  });

  if (!paisCodigo || cicloId == null) {
    return <Box sx={{ p: 3 }}><Alert severity="info">Selecciona país y ciclo en el encabezado.</Alert></Box>;
  }

  const filas = tabla.data || [];
  const podio = filas.slice(0, 3);

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" mb={2}>
        <Typography variant="h5" fontWeight={800} sx={{ flex: 1 }}>Ranking de Formación</Typography>
        {puedeGestionar && (
          <>
            <Button startIcon={<Tune />} onClick={() => setPesos(true)} sx={{ mr: 1 }}>Pesos</Button>
            <Button variant="contained" startIcon={<Refresh />}
              disabled={recalcular.isPending} onClick={() => recalcular.mutate()}>
              {recalcular.isPending ? 'Recalculando…' : 'Recalcular'}
            </Button>
          </>
        )}
      </Stack>

      {mios.data && (
        <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} mb={1}>
              <EmojiEvents color="warning" />
              <Typography fontWeight={700}>Mis puntos: {mios.data.puntos_total}</Typography>
              <Chip size="small" label={`Posición ${mios.data.posicion}`} />
              {mios.data.racha_ciclos > 0 && (
                <Chip size="small" color="warning" icon={<LocalFireDepartment />}
                  label={`${mios.data.racha_ciclos} ciclo(s) seguidos`} />
              )}
            </Stack>
            <Grid container spacing={1}>
              <Componente titulo="Certificaciones" valor={mios.data.puntos_certificacion} />
              <Componente titulo="Exámenes" valor={mios.data.puntos_examenes} />
              <Componente titulo="Refuerzo" valor={mios.data.puntos_refuerzo} />
              <Componente titulo="Onboarding" valor={mios.data.puntos_onboarding} />
            </Grid>
          </CardContent>
        </Card>
      )}

      {tabla.isLoading ? <CircularProgress /> : tabla.isError ? (
        <Alert severity="warning">No se pudo cargar el ranking.</Alert>
      ) : filas.length === 0 ? (
        <Alert severity="info">
          Este ciclo aún no tiene puntos calculados.{puedeGestionar ? ' Pulsa «Recalcular».' : ''}
        </Alert>
      ) : (
        <>
          <Grid container spacing={2} mb={3}>
            {podio.map((f, i) => (
              <Grid item xs={12} md={4} key={f.rm_id}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4">{MEDALLA[i]}</Typography>
                    <Typography fontWeight={700}>{f.rm_nombre}</Typography>
                    <Typography variant="h5" fontWeight={800}>{f.puntos_total}</Typography>
                    <Typography variant="caption" color="text.secondary">puntos</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell><TableCell>Representante</TableCell>
                  <TableCell align="right">Certif.</TableCell>
                  <TableCell align="right">Exám.</TableCell>
                  <TableCell align="right">Refuerzo</TableCell>
                  <TableCell align="right">Onboard.</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell align="right">Racha</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filas.map((f) => (
                  <TableRow key={f.rm_id}>
                    <TableCell>{f.posicion}</TableCell>
                    <TableCell>{f.rm_nombre}</TableCell>
                    <TableCell align="right">{f.puntos_certificacion}</TableCell>
                    <TableCell align="right">{f.puntos_examenes}</TableCell>
                    <TableCell align="right">{f.puntos_refuerzo}</TableCell>
                    <TableCell align="right">{f.puntos_onboarding}</TableCell>
                    <TableCell align="right"><strong>{f.puntos_total}</strong></TableCell>
                    <TableCell align="right">{f.racha_ciclos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </>
      )}

      <DialogoPesos abierto={pesos} paisCodigo={paisCodigo}
        onClose={() => setPesos(false)}
        onGuardado={() => setAviso({ sev: 'success', msg: 'Peso actualizado. Recalcula para aplicarlo.' })} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function Componente({ titulo, valor }: { titulo: string; valor: number }) {
  return (
    <Grid item xs={6} md={3}>
      <Typography variant="caption" color="text.secondary">{titulo}</Typography>
      <Typography variant="h6" fontWeight={700}>{valor}</Typography>
    </Grid>
  );
}

const ETIQUETA_PESO: Record<keyof PesosRanking, string> = {
  ranking_puntos_certificacion: 'Puntos por certificación aprobada',
  ranking_puntos_examen: 'Puntos por examen aprobado',
  ranking_puntos_paso_onboarding: 'Puntos por paso de ruta completado',
  ranking_bono_ruta_completa: 'Bono por completar la ruta',
};

function DialogoPesos({ abierto, paisCodigo, onClose, onGuardado }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onGuardado: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const datos = useQuery({
    queryKey: ['ranking-formacion-pesos', paisCodigo],
    queryFn: () => pesosRankingFormacion(paisCodigo),
    enabled: abierto,
  });
  const [borrador, setBorrador] = useState<Record<string, string>>({});

  const guardar = useMutation({
    mutationFn: async () => {
      for (const [clave, valor] of Object.entries(borrador)) {
        if (valor.trim() && !Number.isNaN(Number(valor))) {
          await fijarPesoRankingFormacion({ pais_codigo: paisCodigo, clave, valor: Number(valor) });
        }
      }
    },
    onSuccess: () => {
      setBorrador({}); setError(null);
      qc.invalidateQueries({ queryKey: ['ranking-formacion-pesos', paisCodigo] });
      onGuardado(); onClose();
    },
    onError: (e) => setError(detalleError(e, 'No se pudo guardar el peso.')),
  });

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Pesos del Ranking de Formación</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info">
            Los puntos de Refuerzo no llevan peso: ya vienen calculados por la participación
            en las cápsulas. Tras cambiar un peso hay que recalcular el ciclo.
          </Alert>
          {datos.isLoading ? <CircularProgress /> : (Object.keys(ETIQUETA_PESO) as (keyof PesosRanking)[]).map((k) => (
            <TextField key={k} label={ETIQUETA_PESO[k]} type="number"
              value={borrador[k] ?? String(datos.data?.[k] ?? '')}
              onChange={(e) => setBorrador((p) => ({ ...p, [k]: e.target.value }))}
              fullWidth />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={guardar.isPending}
          onClick={() => guardar.mutate()}>{guardar.isPending ? 'Guardando…' : 'Guardar'}</Button>
      </DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 2: Registrar la ruta lazy en `App.tsx`**

Junto a los otros `lazyWithReload` de formación:
```tsx
const RankingFormacion = lazyWithReload(() => import('./pages/formacion/RankingFormacion'));
```
Y junto a las rutas `formacion/*` (usa el patrón de `formacion/refuerzo` como referencia):
```tsx
<Route path="formacion/ranking" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','CAPACITACION','PRESIDENCIA','GERENTE_MEDICO','GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><RankingFormacion /></ProtectedRoute>} />
```

- [ ] **Step 3: Agregar el ítem al Sidebar**

En el mismo grupo de Formación (donde están 'Plan de Brechas', 'Refuerzo de Memoria', 'Formación inicial'):
```tsx
{ label: 'Ranking de Formación', path: '/formacion/ranking', icon: <EmojiEvents />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'PRESIDENCIA', 'GERENTE_MEDICO', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
```
Verifica que `EmojiEvents` esté importado desde `@mui/icons-material`; agrégalo al import existente si falta.

- [ ] **Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/formacion/RankingFormacion.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(formacion) Ranking: pagina con podio, desglose y pesos configurables"
```

---

## Verificación en vivo (tras Task 5, no es un commit)

Con JWT minteado (sin escribir contraseña):

1. Capacitación: entrar a `/formacion/ranking` con un ciclo con actividad → «Recalcular» → aparecen podio y tabla.
2. Comprobar que la tarjeta «Mis puntos» de un RM **cuadra exactamente** con su fila en la tabla.
3. Cambiar un peso en el diálogo → recalcular → los puntos de ese componente cambian en consecuencia.
4. Un GD: solo debe ver a los RM de su equipo en la tabla.
5. Un RM: ve el ranking completo del país (es un podio) y su propia tarjeta.
6. Un ciclo sin actividad: mensaje de estado vacío, sin error.
7. **Comprobar que el Score Integral no cambió:** abrir el Ranking oficial (`/ranking`) antes y después de recalcular — las posiciones deben ser idénticas.

---

## Self-Review

- **Cobertura del spec:**
  - §2 decisiones (ranking propio, racha por actividad) → Global Constraints + Tasks 2-3.
  - §3 modelo existente → se usa tal cual, sin migración.
  - §4.1 pesos configurables → Task 1 (`PESOS_DEFECTO`/`pesos`/`fijar_peso`).
  - §4.2 los 4 componentes → Task 1 (`calcular_componentes` + los 4 privados).
  - §4.3 racha sin multiplicar → Task 2 (`_racha`, y `puntos_total` no la incluye).
  - §4.4 recálculo delete-then-insert re-ejecutable, sin guard de ciclo cerrado → Task 2.
  - §5 los 5 endpoints + auto-scope → Task 3.
  - §6 frontend (podio, tabla, mis puntos, recalcular, pesos) → Tasks 4-5.
  - §7 fuera de alcance → respetado (no se toca el motor, sin automatización, sin insignias, sin histórico).
  - §8 verificación → tests de Tasks 1-2 (los 6 casos del spec) + sección en vivo.
- **Placeholder scan:** sin TBD/TODO; todo el código está completo en cada paso.
- **Consistencia de tipos:** `calcular_componentes` devuelve exactamente las 5 claves que consume `RankingFormacionPuntos(**comp)`; `ranking()` devuelve las 9 claves que declara `FilaRankingFormacion` en el frontend; `pesos()` devuelve las 4 claves de `PesosRanking`; `mis_puntos` reutiliza `ranking()` para que el desglose propio y la fila de la tabla **no puedan divergir**.
