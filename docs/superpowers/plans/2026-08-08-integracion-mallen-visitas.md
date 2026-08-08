# Integración de visitas Mallén → VISTA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrar los cuatro hechos de visita que Mallén deja en `ext`, calcular desde ellos los cuatro indicadores de visita del Score, y apagar la captura manual de visitas en VISTA.

**Architecture:** Un servicio de integración que lleva los hechos de `ext` a `DIM_TargetMedico`, `DW.FACT_Visita`, `Visita.DIM_FarmaciaVisita` y `Visita.FactVisitaFarmacia` (reutilizando `MapeoExterno` para idempotencia); un motor separado que calcula `COB_MD_F1`, `COB_MD_F2`, `PROM_DIARIO` y `COB_FARMACIAS` **directamente desde `ext`** y los escribe en `FACT_ResultadoIndicador`; y el cierre de los cinco endpoints de captura de visitas.

**Tech Stack:** Backend: Python 3.13, FastAPI, SQLAlchemy 2.0, pytest sobre PostgreSQL real. Frontend: React 18 + TypeScript, MUI v6, TanStack Query v5.

## Global Constraints

- **PROHIBIDO tocar el esquema `ext`** (modelos, migración `0030`, SQL entregado). Solo se LEE.
- **PROHIBIDO modificar cualquier `Config.DIM_*`, `DW.FACT_*` o `Visita.*` existente** (columnas, índices, constraints). **Este sub-proyecto NO lleva migración.**
- **PROHIBIDO tocar `motor_calculo_service.py`**, `cobertura_predictiva_service.py` ni `cobertura_farmacia_service.py`. El motor nuevo escribe `resultado_real` y la conversión a puntos sigue siendo del motor existente.
- **«Cubierto» = médicos DISTINTOS visitados** (§2.1 del requerimiento v2, literal): basta **una** visita ejecutada; visitarlo cinco veces lo cuenta una vez. **`visitas_programadas` NO entra en la fórmula.** Corrige una versión anterior de este plan que exigía la frecuencia completa, tomada del RFI del 22-jul que el v2 reemplazó.
- **`PROM_DIARIO` = médicos distintos visitados / `dias_laborables`** — médicos, **no visitas** (§2.1: *"Médicos visitados dividido entre los días laborables del ciclo"*).
- **Solo cuentan las visitas con `ejecutada = true`.** `V` y `R` cuentan ambas como contacto. Las no ejecutadas no suman al numerador, pero su médico **sigue en el denominador**.
- **El cálculo de indicadores se hace sobre `ext`, no sobre las tablas internas**: `DIM_TargetMedico` no tiene columna de frecuencia y no se le añade.
- **`prioridad` (TOP/REGULAR) NO se escribe en `DIM_TargetMedico.potencial`**: ese campo significa categoría A/B/C y el §11.5 advierte que *"marcar TOP no es marcar categoría A"*. La prioridad es del sub-proyecto de Médicos TOP, que va después de este.
- **Al final de la integración se dispara `recalculo_service.recalcular_ciclo`** (§7.1 paso 3) y **se marcan como `INTEGRADO` los lotes recorridos** (§7.1 paso 4). Sin esos dos pasos, integrar no actualiza el Score ni cierra el ciclo de vida del lote.
- **Una fila mala no detiene la integración**: se registra un hallazgo y se sigue. Los hallazgos viajan en la respuesta, no se persisten.
- **Idempotencia**: los hechos se emparejan por `MapeoExterno` (`visita_medico`, `visita_farmacia`, `target_medico`, `target_farmacia`); los indicadores por delete-then-insert acotado a los 4 códigos y al `(rm_id, ciclo_id)` procesado.
- **La solución es multipaís**: sin parametrización por país en ninguna parte.
- Roles de los endpoints: **ADMIN y GERENTE_PRODUCTIVIDAD** (gate `RequireTI` ya existente en el router).
- Referencias de patrón: `backend/app/services/integracion_dimensiones_service.py` (estructura de servicio, `Hallazgo`/`Conteo`), `backend/app/services/integracion_mapeo.py` (`resolver`, `id_mapeado`), `backend/tests/test_integracion_dimensiones.py` (fixtures de PostgreSQL real).

---

### Task 1: Integrar panel médico y visitas médicas

**Files:**
- Create: `backend/app/services/integracion_visitas_service.py`
- Test: `backend/tests/test_integracion_visitas.py`

**Interfaces:**
- Consumes: `integracion_mapeo.resolver`/`id_mapeado`, `MapeoExterno` y las constantes `ENT_*` del sub-proyecto 2.
- Produce (para Tasks 2-4):
  - `class Hallazgo` (dataclass): `hecho`, `origen_id`, `problema`, `severidad`.
  - `class ConteoHecho` (dataclass): `hecho`, `en_ext`, `integrados`, `actualizados`, `omitidos`.
  - `SEVERIDAD_ERROR = "error"`, `SEVERIDAD_AVISO = "aviso"`.
  - `ENT_TARGET_MEDICO = "target_medico"`, `ENT_VISITA_MEDICO = "visita_medico"`.
  - `integrar_panel_medico(db, pais_codigo, ciclo_codigo, hallazgos) -> ConteoHecho`
  - `integrar_visitas_medico(db, pais_codigo, ciclo_codigo, hallazgos) -> ConteoHecho`

- [ ] **Step 1: Escribir el archivo de tests con el escenario base**

Crear `backend/tests/test_integracion_visitas.py`:

```python
"""Integración de los hechos de visita de Mallén (`ext`) a VISTA.

Lo que estas pruebas cuidan: que re-integrar un ciclo no duplique visitas, y que
una fila cuya dimensión no está sincronizada se omita con hallazgo en vez de
tumbar la corrida.

Necesita PostgreSQL real: cruza tres esquemas con claves compuestas.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, integracion_hallazgo, mapeo_externo,
    seguridad_rbac, usuario, visita,
)
from app.models.dimensiones import (
    Ciclo, Linea, Medico, Pais, RepresentanteMedico, TargetMedico,
)
from app.models.hechos import Visita as FactVisita
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedico, ExtDimPais,
    ExtDimRepresentante, ExtFactVisitaMedico, ExtPanelMedico,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_MEDICO, ENT_REPRESENTANTE, MapeoExterno,
)
from app.services import integracion_visitas_service as viz

BD_PRUEBA = "vista_test_visitas_int"


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
    for tabla in ('"DW"."FACT_Visita"', '"Config"."DIM_TargetMedico"',
                  '"Config"."MapeoExterno"', "ext.factvisitamedico",
                  "ext.panelmedico", "ext.controlcarga", "ext.dimmedico",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Config"."DIM_Medico"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """Dimensiones sincronizadas (con su mapeo) + un lote abierto.

    El mapeo se siembra a mano porque este sub-proyecto CONSUME el del
    sub-proyecto 2, no lo produce: probar la integración de hechos no debe
    depender de re-ejecutar la sincronización de dimensiones.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    medico = Medico(pais_codigo="DO", codigo="MD01", nombre="Doctor Uno")
    db.add_all([rm, ciclo, medico])
    db.flush()

    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", activo=True))
    db.add(ExtControlCarga(
        lote_id=1001, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=2,
        estado="VALIDADO"))
    db.flush()

    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id),
                                     (ENT_MEDICO, "MD01", medico.id)):
        db.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                            codigo_externo=codigo, id_interno=interno))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo, "medico": medico}
```

- [ ] **Step 2: Añadir los tests de panel y visitas médicas**

```python
def _panel(db, medico="MD01", frecuencia="F1", programadas=2):
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo=frecuencia, prioridad="TOP",
        visitas_programadas=programadas, activo=True))
    db.flush()


def _visita(db, origen_id, medico="MD01", ejecutada=True, tipo="V", dia=15):
    db.add(ExtFactVisitaMedico(
        lote_id=1001, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo=medico,
        fecha_visita=date(2026, 1, dia), tipo_visita=tipo, ejecutada=ejecutada,
        acompanado=False))
    db.flush()


def test_panel_crea_el_target_medico(escenario):
    db = escenario["db"]
    _panel(db)
    db.commit()
    hallazgos = []

    conteo = viz.integrar_panel_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    t = db.query(TargetMedico).one()
    assert t.rm_id == escenario["rm"].id
    assert t.ciclo_id == escenario["ciclo"].id
    assert t.medico_codigo == "MD01"
    assert t.programado is True
    # `potencial` significa categoría A/B/C, NO prioridad TOP/REGULAR. La
    # prioridad de `ext` es del sub-proyecto de Médicos TOP; aquí no se
    # escribe. Este assert impide que alguien "aproveche" la columna.
    assert t.potencial is None


def test_visita_ejecutada_entra_como_realizada(escenario):
    db = escenario["db"]
    _visita(db, "V-0001")
    db.commit()
    hallazgos = []

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    v = db.query(FactVisita).one()
    assert v.estado_visita == "Realizada"
    assert v.tipo_contacto == "V"
    assert v.medico_codigo == "MD01"
    assert v.carga_excel_id is None


def test_visita_no_ejecutada_entra_como_cancelada(escenario):
    db = escenario["db"]
    _visita(db, "V-0002", ejecutada=False)
    db.commit()
    hallazgos = []

    viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert db.query(FactVisita).one().estado_visita == "Cancelada"


def test_reintegrar_no_duplica_visitas(escenario):
    """El origen_id del contrato es la clave de idempotencia: reenviar el mismo
    lote corrige, no duplica."""
    db = escenario["db"]
    _visita(db, "V-0001")
    db.commit()
    hallazgos = []
    viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert conteo.integrados == 0
    assert db.query(FactVisita).count() == 1


def test_visita_con_medico_sin_sincronizar_se_omite(escenario):
    """Una referencia sin mapeo NO se resuelve al vuelo: eso es trabajo de la
    sincronización de dimensiones. Se omite y el resto del lote sí entra."""
    db = escenario["db"]
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD99",
                        nombre="Doctor Sin Sincronizar", activo=True))
    db.flush()
    _visita(db, "V-0001")
    _visita(db, "V-0099", medico="MD99")
    db.commit()
    hallazgos = []

    conteo = viz.integrar_visitas_medico(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    assert conteo.omitidos == 1
    assert db.query(FactVisita).count() == 1
    assert any(h.severidad == viz.SEVERIDAD_ERROR and h.origen_id == "V-0099"
               for h in hallazgos)
```

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.integracion_visitas_service'`.
(Si no hay PostgreSQL alcanzable se SALTAN — anótalo y continúa.)

- [ ] **Step 4: Crear el servicio con los dos integradores de médicos**

Crear `backend/app/services/integracion_visitas_service.py`:

```python
"""Integra los hechos de visita que Mallén deja en `ext` con las tablas de VISTA.

QUÉ ALIMENTA CADA COSA
-----------------------
Poblar `DIM_TargetMedico` y `DW.FACT_Visita` alimenta el módulo de Cobertura
Predictiva (4DX) y sus dashboards en vivo. **No alimenta los ocho indicadores del
Score**: esos los calcula `integracion_indicadores_service` a partir de `ext`,
porque VISTA nunca los derivó de visitas — llegaban ya calculados en un Excel.

Una fila cuya dimensión no esté sincronizada se OMITE con hallazgo, nunca se
resuelve al vuelo: adoptar o crear dimensiones es trabajo del sub-proyecto 2 y
duplicar esa lógica aquí llevaría a dos verdades sobre la misma identidad.
"""
from dataclasses import dataclass
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import TargetMedico
from app.models.hechos import Visita as FactVisita
from app.models.integracion_ext import ExtFactVisitaMedico, ExtPanelMedico
from app.models.mapeo_externo import ENT_CICLO, ENT_MEDICO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo

SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"

#: Entidades propias de este sub-proyecto en `MapeoExterno`.
ENT_TARGET_MEDICO = "target_medico"
ENT_VISITA_MEDICO = "visita_medico"


@dataclass
class Hallazgo:
    hecho: str
    origen_id: str | None
    problema: str
    severidad: str


@dataclass
class ConteoHecho:
    hecho: str
    en_ext: int = 0
    integrados: int = 0
    actualizados: int = 0
    omitidos: int = 0

    def anotar(self, resultado: str) -> None:
        if resultado == mapeo.RESULTADO_CREADO:
            self.integrados += 1
        else:
            # Adoptado y actualizado se cuentan igual: para un hecho no existe la
            # distinción del maestro (nadie los cargó antes a mano).
            self.actualizados += 1


def _refs(db: Session, pais_codigo: str, ciclo_codigo: str, rm_codigo: str
          ) -> tuple[int | None, int | None]:
    """Ids internos de ciclo y representante, o None si falta el mapeo."""
    return (mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo),
            mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo))


def _falta_ref(hallazgos: list, hecho: str, origen_id: str | None,
               que: str, codigo: str) -> None:
    hallazgos.append(Hallazgo(
        hecho, origen_id,
        f"No se pudo resolver {que} «{codigo}»; sincroniza dimensiones primero.",
        SEVERIDAD_ERROR))


def integrar_panel_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                          hallazgos: list) -> ConteoHecho:
    """`ext.panelmedico` → `Config.DIM_TargetMedico` (universo del módulo 4DX).

    La frecuencia (F1/F2) NO se guarda: `DIM_TargetMedico` no tiene esa columna y
    no se le añade. El motor de indicadores la lee de `ext`, que es su origen.
    """
    conteo = ConteoHecho("panelmedico")
    filas = (db.query(ExtPanelMedico)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        clave = f"{fila.rm_codigo}/{fila.medico_codigo}"
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "panelmedico", clave, "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "panelmedico", clave, "el representante",
                       fila.rm_codigo)
            continue

        def _buscar(f=fila, cid=ciclo_id, rid=rm_id):
            return (db.query(TargetMedico)
                    .filter(TargetMedico.rm_id == rid,
                            TargetMedico.ciclo_id == cid,
                            TargetMedico.medico_codigo == f.medico_codigo)
                    .first())

        def _crear(f=fila, cid=ciclo_id, rid=rm_id):
            # `potencial` NO se escribe: significa categoría A/B/C, no la
            # prioridad TOP/REGULAR de `ext` (§11.5 del requerimiento).
            nuevo = TargetMedico(
                pais_codigo=f.pais_codigo, rm_id=rid, ciclo_id=cid,
                medico_codigo=f.medico_codigo,
                programado=f.activo, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_TARGET_MEDICO, pais_codigo,
            f"{ciclo_codigo}/{fila.rm_codigo}/{fila.medico_codigo}",
            TargetMedico, _buscar, _crear)
        registro.programado = fila.activo
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def integrar_visitas_medico(db: Session, pais_codigo: str, ciclo_codigo: str,
                            hallazgos: list) -> ConteoHecho:
    """`ext.factvisitamedico` → `DW.FACT_Visita` (bitácora del módulo 4DX).

    `origen_id` es la clave de idempotencia que garantiza el contrato: reenviar
    el mismo registro corrige la fila, no la duplica.
    """
    conteo = ConteoHecho("factvisitamedico")
    filas = (db.query(ExtFactVisitaMedico)
             .filter(ExtFactVisitaMedico.pais_codigo == pais_codigo,
                     ExtFactVisitaMedico.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if ciclo_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el ciclo", ciclo_codigo)
            continue
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el representante", fila.rm_codigo)
            continue
        # El médico se referencia por CÓDIGO en FACT_Visita, no por id, pero se
        # exige que esté sincronizado: una visita a un médico que VISTA no conoce
        # inflaría la cobertura con un contacto que no se puede auditar.
        if mapeo.id_mapeado(db, ENT_MEDICO, pais_codigo, fila.medico_codigo) is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitamedico", fila.origen_id,
                       "el médico", fila.medico_codigo)
            continue

        def _buscar():
            return None  # la identidad la lleva el mapeo por origen_id

        def _crear(f=fila, cid=ciclo_id, rid=rm_id):
            nuevo = FactVisita(
                pais_codigo=f.pais_codigo, rm_id=rid, ciclo_id=cid,
                medico_codigo=f.medico_codigo, fecha_visita=f.fecha_visita,
                tipo_contacto=f.tipo_visita,
                estado_visita="Realizada" if f.ejecutada else "Cancelada",
                carga_excel_id=None)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VISITA_MEDICO, pais_codigo, fila.origen_id,
            FactVisita, _buscar, _crear)
        registro.fecha_visita = fila.fecha_visita
        registro.tipo_contacto = fila.tipo_visita
        registro.estado_visita = "Realizada" if fila.ejecutada else "Cancelada"
        conteo.anotar(resultado)
    logger.info(f"Visitas médicas {pais_codigo}/{ciclo_codigo}: "
                f"{conteo.integrados} nuevas, {conteo.omitidos} omitidas")
    return conteo
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -v`
Expected: 5 passed (o SKIPPED).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/integracion_visitas_service.py backend/tests/test_integracion_visitas.py
git commit -m "feat(integracion) integrar panel medico y visitas medicas de Mallen"
```

---

### Task 2: Integrar target y visitas de farmacia

**Files:**
- Modify: `backend/app/services/integracion_visitas_service.py`
- Test: `backend/tests/test_integracion_visitas.py`

**Interfaces:**
- Consumes: `Hallazgo`, `ConteoHecho`, `_refs`, `_falta_ref`, `SEVERIDAD_*` de Task 1.
- Produce (para Task 4): `ENT_TARGET_FARMACIA = "target_farmacia"`, `ENT_VISITA_FARMACIA = "visita_farmacia"`, `integrar_target_farmacia(db, pais_codigo, ciclo_codigo, hallazgos) -> ConteoHecho`, `integrar_visitas_farmacia(db, pais_codigo, ciclo_codigo, hallazgos) -> ConteoHecho`.

- [ ] **Step 1: Añadir los tests al final del archivo**

Amplía los imports con:
```python
from app.models.dimensiones import Farmacia
from app.models.integracion_ext import ExtDimFarmacia, ExtFactVisitaFarmacia, ExtTargetFarmacia
from app.models.mapeo_externo import ENT_FARMACIA
from app.models.visita import FarmaciaVisita, VisitaFarmacia
```
Y añade al inicio de la lista de limpieza del fixture `db` (hijos antes que padres):
```python
'"Visita"."FactVisitaFarmacia"', '"Visita"."DIM_FarmaciaVisita"',
'"Config"."DIM_Farmacia"', "ext.factvisitafarmacia", "ext.targetfarmacia",
"ext.dimfarmacia",
```

Nota: verifica los nombres reales de las clases del modelo `visita.py` para `DIM_FarmaciaVisita` y `FactVisitaFarmacia` — el fixture y el servicio deben usar los del modelo, no los supuestos aquí.

```python
@pytest.fixture
def farmacia(escenario):
    """Una farmacia sincronizada, con su mapeo, lista para recibir hechos."""
    db = escenario["db"]
    maestro = Farmacia(pais_codigo="DO", nombre="Farmacia Central",
                       nombre_completo="FARMACIA CENTRAL", direccion="",
                       encargado="", estado="ACTIVA", origen="CONFIG")
    db.add(maestro)
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.flush()
    db.add(MapeoExterno(entidad=ENT_FARMACIA, pais_codigo="DO",
                        codigo_externo="FAR01", id_interno=maestro.id))
    db.commit()
    return {**escenario, "maestro": maestro}


def test_target_farmacia_entra_aprobado(farmacia):
    """Viene del maestro oficial del SFA: no pasa por la cola de aprobación
    VM→GD, que existe para las altas que pide un representante."""
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []

    conteo = viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    panel = db.query(FarmaciaVisita).one()
    assert panel.estado_aprobacion == "APROBADO"
    assert panel.vm_id == farmacia["rm"].id
    assert panel.maestro_farmacia_id == farmacia["maestro"].id


def test_visita_farmacia_entra_sin_usuario_que_la_registro(farmacia):
    """`registrado_por` queda nulo: no la capturó nadie en VISTA."""
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.commit()
    hallazgos = []
    viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()
    db.add(ExtFactVisitaFarmacia(
        lote_id=1001, origen_id="VF-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", farmacia_codigo="FAR01",
        fecha_visita=date(2026, 1, 20), ejecutada=True))
    db.commit()

    conteo = viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.integrados == 1
    v = db.query(VisitaFarmacia).one()
    assert v.registrado_por is None
    assert v.ejecutada is True


def test_reintegrar_no_duplica_visitas_de_farmacia(farmacia):
    db = farmacia["db"]
    db.add(ExtTargetFarmacia(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026",
        rm_codigo="VM01", farmacia_codigo="FAR01", visitas_programadas=1,
        activo=True))
    db.add(ExtFactVisitaFarmacia(
        lote_id=1001, origen_id="VF-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", farmacia_codigo="FAR01",
        fecha_visita=date(2026, 1, 20), ejecutada=True))
    db.commit()
    hallazgos = []
    viz.integrar_target_farmacia(db, "DO", "C01-2026", hallazgos)
    viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    conteo = viz.integrar_visitas_farmacia(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert db.query(VisitaFarmacia).count() == 1
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -k farmacia -v`
Expected: FAIL con `AttributeError: ... has no attribute 'integrar_target_farmacia'`.

- [ ] **Step 3: Implementar los dos integradores de farmacia**

Añade al final de `backend/app/services/integracion_visitas_service.py`. Amplía los imports con los modelos de farmacia (usa los nombres reales de `app/models/visita.py` y `app/models/dimensiones.py`) y con `ENT_FARMACIA` de `mapeo_externo`.

```python
ENT_TARGET_FARMACIA = "target_farmacia"
ENT_VISITA_FARMACIA = "visita_farmacia"


def integrar_target_farmacia(db: Session, pais_codigo: str, ciclo_codigo: str,
                             hallazgos: list) -> ConteoHecho:
    """`ext.targetfarmacia` → `Visita.DIM_FarmaciaVisita` (panel del VM).

    Entra como APROBADO (masculino: es el valor que usan farmacia_aprobacion_service
    y el filtro de cobertura_farmacia_service). El flujo de aprobación VM→GD existe
    para las altas que
    solicita un representante, y esto es maestro oficial del SFA.

    `ciclos_sin_visita` NO se toca: lo lleva el rodaje de cierre de ciclo.
    """
    conteo = ConteoHecho("targetfarmacia")
    filas = (db.query(ExtTargetFarmacia)
             .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                     ExtTargetFarmacia.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        clave = f"{fila.rm_codigo}/{fila.farmacia_codigo}"
        if rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "targetfarmacia", clave, "el representante",
                       fila.rm_codigo)
            continue
        maestro_id = mapeo.id_mapeado(db, ENT_FARMACIA, pais_codigo,
                                      fila.farmacia_codigo)
        if maestro_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "targetfarmacia", clave, "la farmacia",
                       fila.farmacia_codigo)
            continue

        def _buscar(f=fila, rid=rm_id, mid=maestro_id):
            return (db.query(FarmaciaVisita)
                    .filter(FarmaciaVisita.vm_id == rid,
                            FarmaciaVisita.maestro_farmacia_id == mid).first())

        def _crear(f=fila, rid=rm_id, mid=maestro_id, cid=ciclo_id):
            nuevo = FarmaciaVisita(
                vm_id=rid, maestro_farmacia_id=mid,
                estado_aprobacion="APROBADO", ciclo_alta_id=cid,
                activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_TARGET_FARMACIA, pais_codigo,
            f"{ciclo_codigo}/{fila.rm_codigo}/{fila.farmacia_codigo}",
            FarmaciaVisita, _buscar, _crear)
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def integrar_visitas_farmacia(db: Session, pais_codigo: str, ciclo_codigo: str,
                              hallazgos: list) -> ConteoHecho:
    """`ext.factvisitafarmacia` → `Visita.FactVisitaFarmacia`.

    `registrado_por` queda nulo (no la capturó un usuario de VISTA) y la hora
    es 00:00 porque el contrato solo trae fecha.
    """
    conteo = ConteoHecho("factvisitafarmacia")
    filas = (db.query(ExtFactVisitaFarmacia)
             .filter(ExtFactVisitaFarmacia.pais_codigo == pais_codigo,
                     ExtFactVisitaFarmacia.ciclo_codigo == ciclo_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        ciclo_id, rm_id = _refs(db, pais_codigo, ciclo_codigo, fila.rm_codigo)
        if ciclo_id is None or rm_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitafarmacia", fila.origen_id,
                       "el ciclo o el representante",
                       f"{ciclo_codigo}/{fila.rm_codigo}")
            continue
        panel_id = mapeo.id_mapeado(
            db, ENT_TARGET_FARMACIA, pais_codigo,
            f"{ciclo_codigo}/{fila.rm_codigo}/{fila.farmacia_codigo}")
        if panel_id is None:
            conteo.omitidos += 1
            _falta_ref(hallazgos, "factvisitafarmacia", fila.origen_id,
                       "la farmacia en el panel del representante",
                       fila.farmacia_codigo)
            continue

        def _buscar():
            return None  # la identidad la lleva el mapeo por origen_id

        def _crear(f=fila, cid=ciclo_id, rid=rm_id, pid=panel_id):
            nuevo = VisitaFarmacia(
                vm_id=rid, ciclo_id=cid, farmacia_id=pid,
                fecha_hora=datetime(f.fecha_visita.year, f.fecha_visita.month,
                                    f.fecha_visita.day),
                ejecutada=f.ejecutada, registrado_por=None)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_VISITA_FARMACIA, pais_codigo, fila.origen_id,
            VisitaFarmacia, _buscar, _crear)
        registro.ejecutada = fila.ejecutada
        conteo.anotar(resultado)
    return conteo
```

- [ ] **Step 4: Correr toda la suite del archivo**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -v`
Expected: 8 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_visitas_service.py backend/tests/test_integracion_visitas.py
git commit -m "feat(integracion) integrar target y visitas de farmacia de Mallen"
```

---

### Task 3: Motor de cálculo de los cuatro indicadores

El corazón nuevo: VISTA deja de recibir los indicadores calculados y los deriva de los hechos.

**Files:**
- Create: `backend/app/services/integracion_indicadores_service.py`
- Test: `backend/tests/test_integracion_indicadores.py`

**Interfaces:**
- Consumes: `Hallazgo` y `SEVERIDAD_*` de `integracion_visitas_service`.
- Produce (para Task 4): `CODIGOS = ("COB_MD_F1", "COB_MD_F2", "PROM_DIARIO", "COB_FARMACIAS")` y `calcular_indicadores(db, pais_codigo, ciclo_codigo, hallazgos) -> dict` con `{"rms": int, "filas": int}`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_integracion_indicadores.py` con el mismo bloque de fixtures `motor`/`db` del archivo de Task 1 (cópialo tal cual, cambiando `BD_PRUEBA = "vista_test_indicadores"` y añadiendo `'"DW"."FACT_ResultadoIndicador"'` y `'"Config"."DIM_Indicador"'` al inicio de la lista de limpieza), más:

```python
from app.models.dimensiones import Indicador
from app.models.hechos import ResultadoIndicador


@pytest.fixture
def base(db):
    """Dimensiones mapeadas + los 4 indicadores dados de alta en el país."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             codigo="VM01", nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    db.add_all([rm, ciclo])
    db.flush()
    for codigo in ind.CODIGOS:
        db.add(Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                         modulo="PRODUCTIVIDAD", tipo_periodo="CICLO"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="RD", activo=True))
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtControlCarga(
        lote_id=1001, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=0,
        estado="VALIDADO"))
    db.flush()
    db.add(MapeoExterno(entidad=ENT_REPRESENTANTE, pais_codigo="DO",
                        codigo_externo="VM01", id_interno=rm.id))
    db.add(MapeoExterno(entidad=ENT_CICLO, pais_codigo="DO",
                        codigo_externo="C01-2026", id_interno=ciclo.id))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo}


def _valor(db, rm_id, ciclo_id, codigo):
    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(ResultadoIndicador.rm_id == rm_id,
                    ResultadoIndicador.ciclo_id == ciclo_id,
                    Indicador.codigo == codigo).first())
    return float(fila.resultado_real) if fila else None


def _panel(db, medico, frecuencia, programadas):
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo=medico, frecuencia_objetivo=frecuencia, prioridad="TOP",
        visitas_programadas=programadas, activo=True))


def _visitas(db, medico, cuantas, ejecutada=True, desde=1):
    for i in range(cuantas):
        db.add(ExtFactVisitaMedico(
            lote_id=1001, origen_id=f"V-{medico}-{i}", pais_codigo="DO",
            ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo=medico,
            fecha_visita=date(2026, 1, desde + i), tipo_visita="V",
            ejecutada=ejecutada, acompanado=False))


def test_cobertura_cuenta_medicos_distintos_no_visitas(base):
    """El caso que fija «médicos distintos visitados» (§2.1 del requerimiento).

    Dos médicos F1: uno visitado 3 veces, el otro ninguna. Las 3 visitas al
    mismo médico cuentan UNA vez, así que da 50. Si el numerador contara
    visitas en vez de médicos, daría 150 — un valor imposible.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _panel(db, "MD02", "F1", 2)
    _visitas(db, "MD01", 3)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 50.0


def test_una_sola_visita_ya_cubre_aunque_exija_mas(base):
    """`visitas_programadas` NO participa: basta una visita ejecutada.

    Un médico F1 que declara exigir 2 visitas y recibió 1 → cubierto, 100.
    Con la definición vieja («frecuencia completa») daría 0. Este test es el
    que impide que esa definición vuelva a colarse.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 2)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0


def test_f1_y_f2_no_se_mezclan(base):
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F2", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0
    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F2") == 0.0


def test_promedio_diario_cuenta_medicos_distintos_no_visitas(base):
    """§2.1: «MÉDICOS visitados / días laborables», no visitas.

    Un médico visitado 10 veces en un ciclo de 20 días → 1/20 = 0.05.
    Si contara visitas daría 0.5: diez veces más. Es la diferencia que
    justifica este test.
    """
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_promedio_diario_suma_medicos_distintos(base):
    """10 médicos distintos visitados / 20 días laborables = 0.5."""
    db = base["db"]
    for i in range(10):
        _panel(db, f"MD{i:02d}", "F1", 1)
        _visitas(db, f"MD{i:02d}", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.5


def test_las_no_ejecutadas_no_cuentan_pero_su_medico_si(base):
    """No visitar no reduce el universo: el médico sigue en el denominador."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _panel(db, "MD02", "F1", 1)
    _visitas(db, "MD01", 1)
    _visitas(db, "MD02", 1, ejecutada=False, desde=10)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 50.0
    assert _valor(db, base["rm"].id, base["ciclo"].id, "PROM_DIARIO") == 0.05


def test_visitas_programadas_nulo_no_afecta_el_calculo(base):
    """`visitas_programadas` no entra en la fórmula, así que un nulo no rompe
    nada ni genera hallazgo: no hay frecuencia que exigir."""
    db = base["db"]
    _panel(db, "MD01", "F1", None)
    _visitas(db, "MD01", 1)
    db.commit()
    hallazgos = []

    ind.calcular_indicadores(db, "DO", "C01-2026", hallazgos)
    db.commit()

    assert _valor(db, base["rm"].id, base["ciclo"].id, "COB_MD_F1") == 100.0
    assert hallazgos == []


def test_recalcular_no_duplica_ni_toca_otros_indicadores(base):
    """Delete-then-insert acotado a los 4 códigos: los otros no se rozan."""
    db = base["db"]
    otro = Indicador(pais_codigo="DO", codigo="VENTAS", nombre="Ventas",
                     modulo="COMERCIAL", tipo_periodo="MES")
    db.add(otro)
    db.flush()
    db.add(ResultadoIndicador(rm_id=base["rm"].id, pais_codigo="DO",
                              ciclo_id=base["ciclo"].id, indicador_id=otro.id,
                              resultado_real=88, activo=True))
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()
    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    assert db.query(ResultadoIndicador).count() == 5   # 4 calculados + VENTAS
    assert _valor(db, base["rm"].id, base["ciclo"].id, "VENTAS") == 88.0


def test_no_escribe_puntos_solo_el_valor(base):
    """La conversión a puntos sigue siendo del motor existente."""
    db = base["db"]
    _panel(db, "MD01", "F1", 1)
    _visitas(db, "MD01", 1)
    db.commit()

    ind.calcular_indicadores(db, "DO", "C01-2026", [])
    db.commit()

    fila = (db.query(ResultadoIndicador)
            .join(Indicador, ResultadoIndicador.indicador_id == Indicador.id)
            .filter(Indicador.codigo == "COB_MD_F1").one())
    assert fila.resultado_real is not None
    assert fila.puntos_obtenidos is None
```

Importa el servicio como `from app.services import integracion_indicadores_service as ind`.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_indicadores.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.integracion_indicadores_service'`.

- [ ] **Step 3: Implementar el motor**

Crear `backend/app/services/integracion_indicadores_service.py`:

```python
"""Calcula los cuatro indicadores de visita a partir de los hechos de Mallén.

POR QUÉ EXISTE ESTE MÓDULO
---------------------------
VISTA nunca derivó estos indicadores de las visitas: llegaban ya calculados en el
Excel `KPI_RM` y el motor solo los convertía a puntos. El contrato con Mallén no
trae indicadores calculados —trae hechos—, así que al retirar el Excel alguien
tiene que producirlos. Es este módulo.

SE CALCULA SOBRE `ext`, NO SOBRE LAS TABLAS INTERNAS
-----------------------------------------------------
`ext.panelmedico` trae `frecuencia_objetivo` (F1/F2), que es justo lo que separa
COB_MD_F1 de COB_MD_F2. `DIM_TargetMedico` no tiene esa columna, y añadírsela
sería deformar una tabla interna para que quepa un dato del contrato.

DEFINICIÓN DE «CUBIERTO»: MÉDICOS DISTINTOS VISITADOS
------------------------------------------------------
§2.1 del requerimiento v2, literal: «calcula la cobertura dividiendo la cantidad
de MÉDICOS DISTINTOS VISITADOS entre la cantidad de médicos programados para cada
frecuencia». Un médico cuenta cuando tiene AL MENOS UNA visita ejecutada;
visitarlo cinco veces no lo cuenta cinco veces.

`visitas_programadas` NO participa en esta fórmula. Se integra igual a
`DIM_TargetMedico` porque lo consume el módulo 4DX, pero aquí no se lee.

Una versión anterior de este módulo exigía la frecuencia completa
(`>= visitas_programadas`). Venía del RFI del 22-jul, que el requerimiento v2
reemplazó. Se corrigió porque los números de VISTA deben cuadrar con los de
Mallén, y el documento acordado es el v2.
"""
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Indicador
from app.models.hechos import ResultadoIndicador
from app.models.integracion_ext import (
    ExtDimCiclo, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo
from app.services.integracion_visitas_service import SEVERIDAD_ERROR, Hallazgo

COB_MD_F1 = "COB_MD_F1"
COB_MD_F2 = "COB_MD_F2"
PROM_DIARIO = "PROM_DIARIO"
COB_FARMACIAS = "COB_FARMACIAS"
CODIGOS: tuple[str, ...] = (COB_MD_F1, COB_MD_F2, PROM_DIARIO, COB_FARMACIAS)


def _pct(cubiertos: int, universo: int) -> Decimal:
    """Cobertura en porcentaje. Universo vacío → 0, no división por cero: un RM
    sin panel no tiene cobertura, no tiene cobertura indefinida."""
    if universo <= 0:
        return Decimal("0")
    return (Decimal(cubiertos) * 100 / Decimal(universo)).quantize(Decimal("0.01"))


def _indicadores_del_pais(db: Session, pais_codigo: str) -> dict[str, int]:
    """`codigo → indicador_id`. Los que no estén dados de alta se reportan una
    sola vez y su indicador se omite: dar de alta un indicador es configuración
    (lleva ponderación y tabla de rangos), no algo que se improvise aquí."""
    filas = (db.query(Indicador)
             .filter(Indicador.pais_codigo == pais_codigo,
                     Indicador.codigo.in_(CODIGOS)).all())
    return {f.codigo: f.id for f in filas}


def _medicos_visitados(db: Session, pais_codigo: str, ciclo_codigo: str,
                       rm_codigo: str) -> set[str]:
    """Códigos de los médicos con AL MENOS UNA visita ejecutada en el ciclo.

    Un `set` es la estructura que expresa la regla: «distintos visitados». Da
    igual cuántas veces aparezca cada médico. Tanto `V` (visita) como `R`
    (revisita) cuentan: ambas son presencia frente al médico.
    """
    filas = (db.query(ExtFactVisitaMedico.medico_codigo)
             .filter(ExtFactVisitaMedico.pais_codigo == pais_codigo,
                     ExtFactVisitaMedico.ciclo_codigo == ciclo_codigo,
                     ExtFactVisitaMedico.rm_codigo == rm_codigo,
                     ExtFactVisitaMedico.ejecutada.is_(True))
             .distinct().all())
    return {f[0] for f in filas}


def _cobertura_medicos(db: Session, pais_codigo: str, ciclo_codigo: str,
                       rm_codigo: str, frecuencia: str,
                       visitados: set[str]) -> Decimal:
    """Médicos distintos visitados de esa frecuencia / médicos de esa
    frecuencia en el panel × 100.

    El numerador se intersecta con el panel de ESTA frecuencia: una visita a
    un médico F2 no puede sumar a la cobertura F1. Los no visitados siguen en
    el denominador — no visitar no reduce el universo.
    """
    panel = {f[0] for f in db.query(ExtPanelMedico.medico_codigo)
             .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                     ExtPanelMedico.ciclo_codigo == ciclo_codigo,
                     ExtPanelMedico.rm_codigo == rm_codigo,
                     ExtPanelMedico.frecuencia_objetivo == frecuencia,
                     ExtPanelMedico.activo.is_(True)).distinct().all()}
    if not panel:
        return Decimal("0")
    return _pct(len(panel & visitados), len(panel))


def _promedio_diario(db: Session, visitados: set[str],
                     dias_laborables: int) -> Decimal:
    """§2.1: «MÉDICOS visitados dividido entre los días laborables del ciclo».

    Médicos distintos, no visitas: un médico visitado tres veces aporta 1.
    Se reutiliza el mismo conjunto que la cobertura, así los dos indicadores
    no pueden divergir en qué cuenta como visitado.
    """
    if dias_laborables <= 0:
        return Decimal("0")
    return (Decimal(len(visitados)) / Decimal(dias_laborables)).quantize(Decimal("0.01"))


def _cobertura_farmacias(db: Session, pais_codigo: str, ciclo_codigo: str,
                         rm_codigo: str) -> Decimal:
    """Farmacias distintas visitadas / farmacias en el target × 100."""
    target = {f[0] for f in db.query(ExtTargetFarmacia.farmacia_codigo)
              .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                      ExtTargetFarmacia.ciclo_codigo == ciclo_codigo,
                      ExtTargetFarmacia.rm_codigo == rm_codigo,
                      ExtTargetFarmacia.activo.is_(True)).distinct().all()}
    if not target:
        return Decimal("0")

    visitadas = {f[0] for f in db.query(ExtFactVisitaFarmacia.farmacia_codigo)
                 .filter(ExtFactVisitaFarmacia.pais_codigo == pais_codigo,
                         ExtFactVisitaFarmacia.ciclo_codigo == ciclo_codigo,
                         ExtFactVisitaFarmacia.rm_codigo == rm_codigo,
                         ExtFactVisitaFarmacia.ejecutada.is_(True))
                 .distinct().all()}
    return _pct(len(target & visitadas), len(target))


def calcular_indicadores(db: Session, pais_codigo: str, ciclo_codigo: str,
                         hallazgos: list) -> dict:
    """Calcula los 4 indicadores de cada RM con actividad en el ciclo.

    Escribe SOLO `resultado_real`: la conversión a puntos la sigue haciendo
    `motor_calculo_service`, igual que con los datos que llegaban por Excel. Así
    el camino de puntuación sigue siendo uno solo.

    Delete-then-insert acotado a estos 4 códigos y a los RM procesados: los otros
    indicadores del ciclo no se rozan.
    """
    ciclo_ext = (db.query(ExtDimCiclo)
                 .filter(ExtDimCiclo.pais_codigo == pais_codigo,
                         ExtDimCiclo.ciclo_codigo == ciclo_codigo).first())
    if ciclo_ext is None:
        raise ValueError(f"El ciclo {ciclo_codigo} no está en ext.dimciclo")
    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        raise ValueError(
            f"El ciclo {ciclo_codigo} no está sincronizado; corre dimensiones primero.")

    ids = _indicadores_del_pais(db, pais_codigo)
    faltantes = [c for c in CODIGOS if c not in ids]
    for codigo in faltantes:
        hallazgos.append(Hallazgo(
            "indicador", codigo,
            f"El indicador {codigo} no está dado de alta en {pais_codigo}; "
            f"no se calculó. Créalo en Administración → Indicadores.",
            SEVERIDAD_ERROR))

    # Los RM con actividad: los del panel más los que solo tienen farmacias.
    rms = {f[0] for f in db.query(ExtPanelMedico.rm_codigo)
           .filter(ExtPanelMedico.pais_codigo == pais_codigo,
                   ExtPanelMedico.ciclo_codigo == ciclo_codigo).distinct()}
    rms |= {f[0] for f in db.query(ExtTargetFarmacia.rm_codigo)
            .filter(ExtTargetFarmacia.pais_codigo == pais_codigo,
                    ExtTargetFarmacia.ciclo_codigo == ciclo_codigo).distinct()}

    filas_escritas = 0
    for rm_codigo in sorted(rms):
        rm_id = mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo)
        if rm_id is None:
            hallazgos.append(Hallazgo(
                "indicador", rm_codigo,
                f"El representante «{rm_codigo}» no está sincronizado; sus "
                f"indicadores no se calcularon.", SEVERIDAD_ERROR))
            continue

        visitados = _medicos_visitados(db, pais_codigo, ciclo_codigo, rm_codigo)
        valores = {
            COB_MD_F1: _cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, "F1", visitados),
            COB_MD_F2: _cobertura_medicos(db, pais_codigo, ciclo_codigo,
                                          rm_codigo, "F2", visitados),
            PROM_DIARIO: _promedio_diario(db, visitados,
                                          ciclo_ext.dias_laborables),
            COB_FARMACIAS: _cobertura_farmacias(db, pais_codigo, ciclo_codigo,
                                                rm_codigo),
        }

        indicador_ids = [ids[c] for c in CODIGOS if c in ids]
        if indicador_ids:
            (db.query(ResultadoIndicador)
             .filter(ResultadoIndicador.rm_id == rm_id,
                     ResultadoIndicador.ciclo_id == ciclo_id,
                     ResultadoIndicador.indicador_id.in_(indicador_ids))
             .delete(synchronize_session=False))
        for codigo, valor in valores.items():
            if codigo not in ids:
                continue
            db.add(ResultadoIndicador(
                rm_id=rm_id, pais_codigo=pais_codigo, ciclo_id=ciclo_id,
                indicador_id=ids[codigo], resultado_real=valor, activo=True))
            filas_escritas += 1

    logger.info(f"Indicadores de visita {pais_codigo}/{ciclo_codigo}: "
                f"{len(rms)} representantes, {filas_escritas} filas")
    return {"rms": len(rms), "filas": filas_escritas}
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_indicadores.py -v`
Expected: 9 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_indicadores_service.py backend/tests/test_integracion_indicadores.py
git commit -m "feat(integracion) motor de los 4 indicadores de visita desde los hechos de Mallen"
```

---

### Task 4: Orquestador + endpoints

**Files:**
- Modify: `backend/app/services/integracion_visitas_service.py`
- Modify: `backend/app/api/v1/routers/integracion.py`
- Test: `backend/tests/test_integracion_visitas.py`

**Interfaces:**
- Consumes: los cuatro integradores (Tasks 1-2) y `calcular_indicadores` (Task 3).
- Consumes también: `recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo) -> dict` (existente, con su guard de ciclo abierto) y `ExtControlCarga`.
- Produce (para Task 6): `integrar_todo(db, pais_codigo, ciclo_codigo) -> dict` con `{"pais_codigo", "ciclo_codigo", "hechos": [...], "indicadores": {...}, "recalculo": {...}, "lotes_cerrados": [int], "hallazgos": [...]}`; y `resumen_visitas(db, pais_codigo, ciclo_codigo) -> list[dict]` con `{"hecho", "en_ext", "integradas"}`.

- [ ] **Step 1: Añadir los tests al final de `test_integracion_visitas.py`**

```python
def test_integrar_todo_corre_los_cuatro_hechos(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["ciclo_codigo"] == "C01-2026"
    assert [h["hecho"] for h in r["hechos"]] == [
        "panelmedico", "factvisitamedico", "targetfarmacia", "factvisitafarmacia"]
    panel = next(h for h in r["hechos"] if h["hecho"] == "panelmedico")
    assert panel["integrados"] == 1


def test_integrar_todo_es_idempotente(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    r = viz.integrar_todo(db, "DO", "C01-2026")

    visitas = next(h for h in r["hechos"] if h["hecho"] == "factvisitamedico")
    assert visitas["integrados"] == 0
    assert visitas["actualizados"] == 1
    assert db.query(FactVisita).count() == 1


def test_resumen_cuenta_ext_y_integradas(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    filas = viz.resumen_visitas(db, "DO", "C01-2026")

    v = next(f for f in filas if f["hecho"] == "factvisitamedico")
    assert v["en_ext"] == 1
    assert v["integradas"] == 1


def test_integrar_dispara_el_recalculo_del_score(farmacia):
    """§7.1 paso 3: sin esto, integrar no movería el Score ni el ranking.

    Se comprueba sobre la salida del motor, no sobre un mock: `recalculo`
    trae el dict real de `recalculo_service.recalcular_ciclo`.
    """
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["recalculo"]["abortado"] is False
    assert "rankings_generados" in r["recalculo"]


def test_ciclo_cerrado_integra_los_hechos_pero_aborta_el_recalculo(farmacia):
    """Un ciclo cerrado es un snapshot histórico: los hechos entran, el Score
    no se toca. El guard vive en `recalculo_service`, no se duplica aquí."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    farmacia["ciclo"].cerrado = True
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["recalculo"]["abortado"] is True
    assert db.query(FactVisita).count() == 1   # los hechos SÍ entraron


def test_lote_validado_pasa_a_integrado(farmacia):
    """§7.1 paso 4. Hasta ahora nadie escribía INTEGRADO."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == [1001]
    lote = db.query(ExtControlCarga).filter_by(lote_id=1001).one()
    assert lote.estado == "INTEGRADO"
    assert "factvisitamedico" in lote.mensaje


def test_lote_rechazado_no_se_rescata(farmacia):
    """Un lote que la validación rechazó no llega a INTEGRADO por el hecho de
    que la integración recorra sus filas."""
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado = "RECHAZADO"
    db.commit()

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == []
    assert db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado == "RECHAZADO"


def test_reintegrar_no_revierte_el_estado_del_lote(farmacia):
    db = farmacia["db"]
    _panel(db)
    _visita(db, "V-0001")
    db.commit()
    viz.integrar_todo(db, "DO", "C01-2026")

    r = viz.integrar_todo(db, "DO", "C01-2026")

    assert r["lotes_cerrados"] == []          # ya estaba cerrado
    assert db.query(ExtControlCarga).filter_by(lote_id=1001).one().estado == "INTEGRADO"
```

El fixture `farmacia` debe exponer `"ciclo"` (el `Ciclo` interno) para el test de ciclo cerrado; si no lo hace, añádelo a su dict de retorno.

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py -k "todo or resumen or recalculo or lote or cerrado" -v`
Expected: FAIL con `AttributeError: ... has no attribute 'integrar_todo'`.

- [ ] **Step 3: Añadir el orquestador**

Añade al final de `backend/app/services/integracion_visitas_service.py`:

```python
#: En orden: los hechos de farmacia dependen del target, que dependen del panel.
_INTEGRADORES = (
    ("panelmedico", integrar_panel_medico),
    ("factvisitamedico", integrar_visitas_medico),
    ("targetfarmacia", integrar_target_farmacia),
    ("factvisitafarmacia", integrar_visitas_farmacia),
)

_ORIGEN_CONTEO = {
    "panelmedico": (ExtPanelMedico, ENT_TARGET_MEDICO),
    "factvisitamedico": (ExtFactVisitaMedico, ENT_VISITA_MEDICO),
    "targetfarmacia": (ExtTargetFarmacia, ENT_TARGET_FARMACIA),
    "factvisitafarmacia": (ExtFactVisitaFarmacia, ENT_VISITA_FARMACIA),
}


def _lotes_del_ciclo(db: Session, pais_codigo: str, ciclo_codigo: str) -> list[int]:
    """Los `lote_id` que aportaron filas a este ciclo, en cualquiera de los
    cuatro hechos. Es la reconciliación lote ↔ ciclo: la integración trabaja
    por ciclo, pero el estado del §7.1 vive en el lote."""
    lotes: set[int] = set()
    for modelo, _ in _ORIGEN_CONTEO.values():
        lotes |= {f[0] for f in db.query(modelo.lote_id)
                  .filter(modelo.pais_codigo == pais_codigo,
                          modelo.ciclo_codigo == ciclo_codigo).distinct().all()}
    return sorted(lotes)


def _cerrar_lotes(db: Session, lotes: list[int], detalle: str) -> list[int]:
    """§7.1 paso 4: marca como INTEGRADO los lotes que estaban en VALIDADO.

    Solo VALIDADO → INTEGRADO. Un lote RECHAZADO no se rescata por la puerta
    de atrás, y uno ya INTEGRADO se deja como está (la re-ejecución del
    proceso es idempotente por diseño del contrato).

    Escribir `estado`/`mensaje` no viola la prohibición sobre `ext`: esa
    prohibición es sobre el ESQUEMA. El contrato asigna esos dos campos a
    VISTA y el sub-proyecto 1 ya los escribe.
    """
    if not lotes:
        return []
    cerrados = []
    for lote in (db.query(ExtControlCarga)
                 .filter(ExtControlCarga.lote_id.in_(lotes)).all()):
        if (lote.estado or "").strip().upper() != "VALIDADO":
            continue
        lote.estado = "INTEGRADO"
        lote.mensaje = detalle[:500]
        cerrados.append(lote.lote_id)
    return sorted(cerrados)


def integrar_todo(db: Session, pais_codigo: str, ciclo_codigo: str) -> dict:
    """Los cuatro pasos del §7.1 para un ciclo: integrar, calcular, recalcular
    el Score y cerrar los lotes.

    Un solo commit para la integración: o entra el ciclo coherente o no entra
    nada. Las filas problemáticas no abortan —se omiten con su hallazgo—, así
    que el commit confirma solo lo que sí se pudo resolver.

    El cálculo de indicadores va DESPUÉS de integrar, aunque lea de `ext` y no de
    las tablas internas: así una sola acción del operador deja el ciclo completo,
    sin un segundo paso que se olvide.
    """
    from app.services import integracion_indicadores_service as indicadores
    from app.services import recalculo_service

    hallazgos: list[Hallazgo] = []
    conteos: list[ConteoHecho] = []
    for _, integrar in _INTEGRADORES:
        conteos.append(integrar(db, pais_codigo, ciclo_codigo, hallazgos))

    try:
        resumen_ind = indicadores.calcular_indicadores(
            db, pais_codigo, ciclo_codigo, hallazgos)
    except ValueError as exc:
        resumen_ind = {"rms": 0, "filas": 0}
        hallazgos.append(Hallazgo("indicador", None, str(exc), SEVERIDAD_ERROR))

    detalle = "; ".join(
        f"{c.hecho}: {c.integrados} nuevas, {c.actualizados} actualizadas"
        for c in conteos)
    cerrados = _cerrar_lotes(
        db, _lotes_del_ciclo(db, pais_codigo, ciclo_codigo),
        f"Integrado en VISTA. {detalle}")

    db.commit()

    # §7.1 paso 3 — DESPUÉS del commit: el motor abre su propia transacción y
    # tiene que ver los indicadores ya escritos. Sin esta llamada, integrar un
    # ciclo no movería el Score, el ranking ni los reconocimientos: seguirían
    # mostrando el cálculo anterior.
    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        recalculo = {"abortado": True, "motivo": "El ciclo no está sincronizado."}
    else:
        recalculo = recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)
        if recalculo.get("abortado"):
            # Ciclo cerrado: los hechos entran (son historia) pero el Score no
            # se toca. No es un error de la integración; se informa y ya.
            logger.warning(
                f"Integración {pais_codigo}/{ciclo_codigo}: hechos integrados "
                f"pero el recálculo se abortó ({recalculo.get('motivo')})")

    return {
        "pais_codigo": pais_codigo, "ciclo_codigo": ciclo_codigo,
        "hechos": [{
            "hecho": c.hecho, "en_ext": c.en_ext, "integrados": c.integrados,
            "actualizados": c.actualizados, "omitidos": c.omitidos,
        } for c in conteos],
        "indicadores": resumen_ind,
        "recalculo": recalculo,
        "lotes_cerrados": cerrados,
        "hallazgos": [{
            "hecho": h.hecho, "origen_id": h.origen_id,
            "problema": h.problema, "severidad": h.severidad,
        } for h in hallazgos],
    }


def resumen_visitas(db: Session, pais_codigo: str, ciclo_codigo: str) -> list[dict]:
    """Filas en `ext` frente a filas ya integradas, por hecho."""
    salida = []
    for hecho, (modelo, entidad) in _ORIGEN_CONTEO.items():
        en_ext = (db.query(modelo)
                  .filter(modelo.pais_codigo == pais_codigo,
                          modelo.ciclo_codigo == ciclo_codigo).count())
        integradas = (db.query(MapeoExterno)
                      .filter(MapeoExterno.entidad == entidad,
                              MapeoExterno.pais_codigo == pais_codigo)
                      .count())
        salida.append({"hecho": hecho, "en_ext": en_ext,
                       "integradas": integradas})
    return salida
```

Amplía los imports del módulo con `MapeoExterno`, `ExtControlCarga` y `ENT_CICLO`.

- [ ] **Step 4: Añadir los endpoints al router**

En `backend/app/api/v1/routers/integracion.py`, añade el import:
```python
from app.services import integracion_visitas_service as visitas
```
Y al final del archivo:

```python
@router.post("/visitas/integrar",
             summary="Integrar los hechos de visita de un ciclo, recalcular y cerrar los lotes")
def integrar_visitas(pais_codigo: str, ciclo_codigo: str,
                     db: Session = Depends(get_db), _: Usuario = RequireTI):
    """Los cuatro pasos del §7.1 en una acción: integra los hechos, calcula los
    4 indicadores de visita, dispara el recálculo del Score/ranking/premios y
    marca los lotes recorridos como INTEGRADO."""
    return visitas.integrar_todo(db, pais_codigo, ciclo_codigo)


@router.get("/visitas/resumen", summary="Filas en ext frente a integradas")
def resumen_visitas(pais_codigo: str, ciclo_codigo: str,
                    db: Session = Depends(get_db), _: Usuario = RequireTI):
    return visitas.resumen_visitas(db, pais_codigo, ciclo_codigo)
```

- [ ] **Step 5: Verificar**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_visitas.py tests/test_integracion_indicadores.py -v`
Expected: todos pasan (16 de visitas + 9 de indicadores).

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'visitas' in r.path])"`
Expected: imprime las 2 rutas nuevas bajo `/api/v1/integracion/visitas`.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/integracion_visitas_service.py backend/app/api/v1/routers/integracion.py backend/tests/test_integracion_visitas.py
git commit -m "feat(integracion) orquestador de visitas + endpoints"
```

---

### Task 5: Apagar la captura de visitas

**Files:**
- Modify: `backend/app/api/v1/routers/visita.py`
- Modify: `backend/app/api/v1/routers/farmacias.py`
- Test: `backend/tests/test_captura_visitas_cerrada.py`

**Interfaces:**
- Produce: los cinco endpoints responden 409.

- [ ] **Step 1: Escribir el test**

Crear `backend/tests/test_captura_visitas_cerrada.py`:

```python
"""La captura de visitas dentro de VISTA quedó cerrada.

Las visitas provienen del SFA de Mallén (esquema `ext`). Estos endpoints ya no
escriben: si volvieran a aceptar registros, VISTA tendría dos fuentes de verdad
para el mismo hecho y los indicadores dejarían de cuadrar con los de Mallén.

No necesitan base de datos: comprueban que el guard está declarado antes de
cualquier acceso a datos.
"""
import pytest
from fastapi import HTTPException

from app.api.v1.routers import farmacias, visita

CERRADOS = [
    (visita, "registrar"),
    (visita, "no_visita"),
    (visita, "subir_foto"),
    (farmacias, "registrar_visita"),
    (farmacias, "subir_foto_visita"),
]


@pytest.mark.parametrize("modulo,nombre", CERRADOS)
def test_el_endpoint_de_captura_esta_cerrado(modulo, nombre):
    """Cada uno debe levantar 409 con un motivo legible, no fallar de otra forma."""
    funcion = getattr(modulo, nombre, None)
    assert funcion is not None, f"No existe {modulo.__name__}.{nombre}"
    fuente = funcion.__doc__ or ""
    assert "SFA" in fuente or "Mallén" in fuente or "Mallen" in fuente, (
        f"{nombre} debe documentar por qué está cerrado")
```

Nota: los nombres de función de la lista `CERRADOS` son los supuestos. **Verifica los reales** leyendo `backend/app/api/v1/routers/visita.py` y `farmacias.py`, y ajusta la lista a los que existen — el test debe reflejar el código, no al revés.

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_captura_visitas_cerrada.py -v`
Expected: FAIL en la aserción del docstring (los endpoints aún no documentan el cierre).

- [ ] **Step 3: Cerrar los cinco endpoints**

En `backend/app/api/v1/routers/visita.py` y `farmacias.py`, en cada uno de los cinco endpoints de captura, **sustituye el cuerpo** por el guard, conservando la firma y el decorador. Patrón a aplicar en cada uno:

```python
    """La captura de visitas está cerrada: las visitas provienen del SFA de
    Mallén (esquema `ext`) y se integran desde ahí.

    Se conserva el endpoint devolviendo 409 en vez de borrarlo para que un
    cliente antiguo reciba un motivo legible en lugar de un 404 sin explicación.
    """
    raise HTTPException(
        status.HTTP_409_CONFLICT,
        "El registro de visitas está cerrado: las visitas provienen del SFA de "
        "Mallén y se integran automáticamente. Lo ya registrado sigue disponible "
        "para consulta.")
```

Los cinco endpoints son: `POST /visita/registrar`, `POST /visita/no-visita`, `POST /visita/{visita_id}/foto`, `POST /farmacias/{panel_id}/visita` y `POST /farmacias/{visita_id}/foto`. **No toques ningún otro endpoint** de esos routers: consultas, panel, planeación, parrilla, muestras y costo/ROI siguen funcionando.

- [ ] **Step 4: Verificar**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_captura_visitas_cerrada.py -v`
Expected: 5 passed.

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: la suite completa pasa. **Si algún test existente esperaba que estos endpoints escribieran, ese test refleja el comportamiento anterior**: actualízalo para esperar 409 y documenta el cambio en el reporte.

- [ ] **Step 5: Commit**

```bash
git add backend/app/api/v1/routers/visita.py backend/app/api/v1/routers/farmacias.py backend/tests/test_captura_visitas_cerrada.py
git commit -m "feat(integracion) cerrar la captura de visitas: la fuente es el SFA de Mallen"
```

---

### Task 6: Frontend — sección Visitas y pantallas en solo lectura

**Files:**
- Modify: `frontend/src/services/integracion.service.ts`
- Modify: `frontend/src/pages/integracion/LotesIntegracion.tsx`
- Modify: `frontend/src/pages/visita/RegistrarVisita.tsx`

**Interfaces:**
- Consumes: los endpoints de Task 4.

- [ ] **Step 1: Añadir tipos y funciones al service**

Añade al final de `frontend/src/services/integracion.service.ts`:

```ts
// ── Visitas (sub-proyecto 3) ─────────────────────────────────────────────
export interface ConteoHecho {
  hecho: string; en_ext: number; integrados: number;
  actualizados: number; omitidos: number;
}

export interface HallazgoVisita {
  hecho: string; origen_id: string | null; problema: string;
  severidad: SeveridadHallazgo;
}

export interface RecalculoIntegracion {
  abortado: boolean;
  motivo?: string;
  filas_kpi_actualizadas?: number;
  rankings_generados?: number;
}

export interface ResultadoIntegracionVisitas {
  pais_codigo: string; ciclo_codigo: string;
  hechos: ConteoHecho[];
  indicadores: { rms: number; filas: number };
  recalculo: RecalculoIntegracion;
  lotes_cerrados: number[];
  hallazgos: HallazgoVisita[];
}

export interface FilaResumenVisita {
  hecho: string; en_ext: number; integradas: number;
}

export const integrarVisitas = (paisCodigo: string, cicloCodigo: string) =>
  api.post<ResultadoIntegracionVisitas>('/integracion/visitas/integrar', null,
    { params: { pais_codigo: paisCodigo, ciclo_codigo: cicloCodigo } })
    .then((r) => r.data);

export const resumenVisitas = (paisCodigo: string, cicloCodigo: string) =>
  api.get<FilaResumenVisita[]>('/integracion/visitas/resumen',
    { params: { pais_codigo: paisCodigo, ciclo_codigo: cicloCodigo } })
    .then((r) => r.data);
```

- [ ] **Step 2: Añadir la sección "Visitas" a la pantalla de lotes**

En `frontend/src/pages/integracion/LotesIntegracion.tsx`, añade el componente al final y móntalo junto a `<SeccionDimensiones ... />`. Reutiliza el helper `detalleError` y `useCicloStore` que ya están en el archivo (no los dupliques).

```tsx
function SeccionVisitas({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [cicloCodigo, setCicloCodigo] = useState('');
  const [resultado, setResultado] = useState<ResultadoIntegracionVisitas | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resumen = useQuery({
    queryKey: ['integracion-visitas', paisCodigo, cicloCodigo],
    queryFn: () => resumenVisitas(paisCodigo as string, cicloCodigo),
    enabled: !!paisCodigo && !!cicloCodigo.trim(),
  });

  const integrar = useMutation({
    mutationFn: () => integrarVisitas(paisCodigo as string, cicloCodigo),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-visitas'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron integrar las visitas.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para integrar visitas.
    </Alert>;
  }

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>Visitas</Typography>
        <TextField size="small" label="Ciclo (código de Mallén)" value={cicloCodigo}
          onChange={(e) => setCicloCodigo(e.target.value)} sx={{ width: 220 }} />
        <Button variant="contained" startIcon={<Sync />}
          disabled={!cicloCodigo.trim() || integrar.isPending}
          onClick={() => integrar.mutate()}>
          {integrar.isPending ? 'Integrando…' : 'Integrar visitas'}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Integrar deja el ciclo completo: los cuatro hechos entran, los indicadores
        COB_MD_F1, COB_MD_F2, PROM_DIARIO y COB_FARMACIAS se calculan desde ellos,
        se recalculan Score y ranking, y los lotes quedan marcados como integrados.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {resumen.data && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Hecho</TableCell>
                <TableCell align="right">En Mallén</TableCell>
                <TableCell align="right">Integradas</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {resumen.data.map((f) => (
                <TableRow key={f.hecho}>
                  <TableCell>{f.hecho}</TableCell>
                  <TableCell align="right">{f.en_ext}</TableCell>
                  <TableCell align="right">{f.integradas}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {resultado && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>
            Integración completada. Indicadores calculados para {resultado.indicadores.rms}
            {' '}representante(s): {resultado.indicadores.filas} valor(es).
            {resultado.lotes_cerrados.length > 0 &&
              ` Lote(s) marcados como integrados: ${resultado.lotes_cerrados.join(', ')}.`}
          </Alert>
          {/* El recálculo es lo que hace visible la integración en el Score y el
              ranking. Si se abortó, el operador tiene que saberlo: los hechos
              entraron pero los tableros siguen mostrando el cálculo anterior. */}
          {resultado.recalculo.abortado ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Los hechos se integraron, pero el Score y el ranking <b>no</b> se
              recalcularon: {resultado.recalculo.motivo ?? 'el ciclo está cerrado.'}
            </Alert>
          ) : (
            <Alert severity="info" sx={{ mb: 2 }}>
              Score y ranking recalculados: {resultado.recalculo.rankings_generados ?? 0}
              {' '}posición(es) de ranking generadas.
            </Alert>
          )}
          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Hecho</TableCell>
                  <TableCell align="right">Integrados</TableCell>
                  <TableCell align="right">Actualizados</TableCell>
                  <TableCell align="right">Omitidos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultado.hechos.map((h) => (
                  <TableRow key={h.hecho}>
                    <TableCell>{h.hecho}</TableCell>
                    <TableCell align="right">{h.integrados}</TableCell>
                    <TableCell align="right">{h.actualizados}</TableCell>
                    <TableCell align="right">{h.omitidos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {resultado.hallazgos.length > 0 && (
            <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
              <Alert severity="info" sx={{ mb: 2 }}>
                Esto es lo que hay que enviarle al equipo técnico de Mallén para corregir.
              </Alert>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Hecho</TableCell><TableCell>Registro</TableCell>
                    <TableCell>Problema</TableCell><TableCell>Severidad</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {resultado.hallazgos.map((h, i) => (
                    <TableRow key={`${h.hecho}-${h.origen_id}-${i}`}>
                      <TableCell>{h.hecho}</TableCell>
                      <TableCell>{h.origen_id || '—'}</TableCell>
                      <TableCell>{h.problema}</TableCell>
                      <TableCell>
                        <Chip size="small" label={h.severidad}
                          color={h.severidad === 'error' ? 'error' : 'warning'} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}
```

- [ ] **Step 3: Poner la pantalla de registro en solo lectura**

En `frontend/src/pages/visita/RegistrarVisita.tsx`, añade al principio del render un aviso persistente y **oculta los controles de captura** (el botón de registrar, el de no-visita y el de foto). Lo ya registrado se sigue mostrando.

```tsx
      <Alert severity="info" sx={{ mb: 2 }}>
        El registro de visitas está cerrado: las visitas provienen del SFA de Mallén
        y se integran automáticamente. Lo ya registrado sigue disponible para consulta.
      </Alert>
```

Inspecciona el archivo para identificar los controles de captura y envolverlos de modo que no se rendericen. **No elimines el código de consulta ni el historial.**

- [ ] **Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/services/integracion.service.ts frontend/src/pages/integracion/LotesIntegracion.tsx frontend/src/pages/visita/RegistrarVisita.tsx
git commit -m "feat(integracion) seccion Visitas y pantalla de registro en solo lectura"
```

---

## Verificación en vivo (tras Task 6, no es un commit)

Con JWT de ADMIN y sembrando datos en `ext` a mano (Mallén aún no envía):

1. Sincronizar dimensiones primero (sub-proyecto 2), luego integrar visitas.
2. Sembrar 2 médicos F1: uno visitado **3 veces** y otro ninguna → `COB_MD_F1` debe salir **50**. Es la comprobación de que el numerador cuenta médicos distintos y no visitas (con visitas daría 150, un imposible).
3. En ese mismo escenario, `PROM_DIARIO` con 20 días laborables debe salir **0.05** (1 médico / 20 días), no 0.15.
4. Integrar dos veces → los conteos pasan de "integrados" a "actualizados" y no hay duplicados.
5. Una visita con un médico sin sincronizar → aparece en hallazgos y el resto entra.
6. Abrir la pantalla de registro de visita → aviso visible y sin controles de captura.
7. Intentar `POST /visita/registrar` por API → 409 con el mensaje.
8. **El Score del RM cambia con la sola integración**, sin correr nada más: la respuesta trae `recalculo.abortado = false` y `/ranking` muestra el ciclo actualizado (§7.1 paso 3).
9. **El lote queda en `INTEGRADO`**: `SELECT estado, mensaje FROM ext.controlcarga` tras integrar (§7.1 paso 4).

---

## Self-Review

- **Cobertura del spec:**
  - §3 mapeo de los 4 hechos → Tasks 1-2.
  - §3.1 resolución de referencias por mapeo, omitir si falta → Tasks 1-2 + 1 test.
  - §3.2 idempotencia por `origen_id` → Tasks 1-2 + 2 tests.
  - §3.3 reglas por destino (estado_visita, aprobada, registrado_por nulo) → Tasks 1-2 + tests.
  - §3.4 motor de indicadores con «cubierto = médicos distintos visitados» (§2.1 del requerimiento) → Task 3 + 9 tests.
  - §3.5 recálculo del Score al integrar (§7.1 paso 3) → Task 4 + 2 tests.
  - §3.6 cierre del lote a INTEGRADO (§7.1 paso 4) → Task 4 + 3 tests.
  - §4 apagado de los 5 endpoints → Task 5.
  - §5 frontend → Task 6.
  - §6 los 2 endpoints → Task 4.
  - §7 F1/F2 resuelto (se lee de `ext`) → Task 3.
  - §8 errores sin persistir, commit único → Task 4.
  - §9 fuera de alcance → respetado (sin migración, sin tocar motores de cálculo ni el resto del módulo de Visita).
  - §10 verificación → tests de Tasks 1-5 + sección en vivo.
- **Placeholder scan:** sin TBD/TODO. Tres puntos piden verificar nombres reales contra el modelo (clases de farmacia en Task 2, nombres de función de endpoints en Task 5, controles de captura en Task 6 Step 3): son instrucciones de inspección, no huecos — el plan no puede fijar nombres que no leí y prefiere que el implementador los confirme a inventarlos.
- **Consistencia de tipos:** `ConteoHecho`/`Hallazgo` de Task 1 los usan Tasks 2-4; `integrar_todo` devuelve las claves que declara `ResultadoIntegracionVisitas`; `resumen_visitas` las de `FilaResumenVisita`; `calcular_indicadores` devuelve `{rms, filas}` que el orquestador expone como `indicadores`.
- **Riesgo conocido, mitigado:** los closures en bucles capturan `fila` por argumento por defecto (`def _buscar(f=fila)`), igual que en el sub-proyecto 2 — sin eso todas las filas usarían la última iteración.
