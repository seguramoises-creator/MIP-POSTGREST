# Equivalencias de Prescripción IR y diagnóstico — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Resolver las tres equivalencias que la atribución del IR necesita (prescriptor, producto y período) y medir con un diagnóstico qué tan bien resuelven, antes de construir el indicador `EVO_IR`.

**Architecture:** Un servicio nuevo, `integracion_ir_service.py`, con tres sincronizadores que **enlazan sin crear** registros internos y un diagnóstico de solo lectura que clasifica cada receta de `ext.factprescripciondetalle` en cuatro baldes. Todo el estado vive en `Config.MapeoExterno` con tres entidades nuevas; no hay tablas nuevas ni migración. La cadena de atribución se define aquí y la reutilizará el indicador en el sub-proyecto siguiente.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, PostgreSQL, pytest contra PostgreSQL real, React 18 + TypeScript + MUI v6 + TanStack Query.

**Diseño:** `docs/superpowers/specs/2026-08-11-integracion-mallen-ir-equivalencias-design.md`

## Global Constraints

- **PROHIBIDO tocar el esquema `ext`**: `backend/app/models/integracion_ext.py`, la migración `0030` y el SQL entregado a Mallén. Es un contrato firmado con un tercero, de solo lectura.
- **PROHIBIDO modificar la ESTRUCTURA** de cualquier `Config.DIM_*` / `DW.FACT_*` / `Visita.*`. Escribir filas sí; cambiar columnas no.
- **PROHIBIDO tocar** `motor_calculo_service.py`, `recalculo_service.py`, `cobertura_predictiva_service.py`, `cobertura_farmacia_service.py`, `visita_costo_service.py`.
- **Este sub-proyecto NO lleva migración.** Las tres entidades nuevas de `MapeoExterno` son constantes de Python.
- **NO se construye el indicador `EVO_IR` ni se escribe en `DW.FACT_EVOIR`.** Es el sub-proyecto siguiente. Si un test o una función los menciona, está fuera de alcance.
- **El sincronizador de prescriptor NO crea médicos.** Enlaza contra `Config.DIM_Medico` o cuenta la fila como no enlazada. Crear un médico que ningún representante trabaja contaminaría los denominadores de cobertura y categorización.
- **El exequátur se compara EXACTO**, reutilizando `maestro_medico_service.detectar_duplicados`. No se inventa una normalización propia. Un exequátur que difiere solo en formato es un **casi-enlace**: se cuenta, no se enlaza.
- **Los prescriptores no enlazados se CUENTAN, no generan `Hallazgo`.** `dimmedicoir` trae todo el mercado (≈10.000 médicos, §9.1 del requerimiento); un hallazgo por fila enterraría los pocos que sí exigen acción. Los `Hallazgo` quedan para: producto propio sin equivalencia (**error**), período sin ciclo (**aviso**) y exequátur duplicado en el maestro (**error**).
- **La pertenencia al panel se evalúa con `visita_aprobacion_service.cuenta_en_ciclo`**, no con `estado_aprobacion == "APROBADO"`. Admite `PENDIENTE_BAJA` (una baja solicitada sigue contando el ciclo actual) y es sensible al ciclo. Los dos criterios existen a propósito y `visita_top_service` documenta que no deben unificarse.
- **El diagnóstico es de solo lectura**: no escribe en `FACT_*`, no cierra lotes, no hace `commit`. Correrlo dos veces devuelve lo mismo.
- Intérprete: `backend/venv/Scripts/python.exe`. Tests desde `backend/`. `Decimal` para aritmética, nunca `float`. `loguru`, nunca `print`. `datetime.now(timezone.utc)`, nunca `utcnow()`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/app/models/mapeo_externo.py` | +3 constantes de entidad. **No** se añaden a `ENTIDADES`, que es el orden de las nueve dimensiones que sincroniza `integracion_dimensiones_service` |
| `backend/app/services/integracion_ir_service.py` (nuevo) | Los tres puentes, la cadena de atribución y el diagnóstico |
| `backend/tests/test_integracion_ir.py` (nuevo) | Pruebas contra PostgreSQL real |
| `backend/app/api/v1/routers/integracion.py` | +2 endpoints |
| `frontend/src/services/integracion.service.ts` | +tipos y +2 llamadas |
| `frontend/src/pages/integracion/LotesIntegracion.tsx` | +`SeccionIR` |

El diagnóstico vive en el mismo servicio que los puentes porque comparte con ellos la cadena de atribución: separarlos obligaría a exportar esa función y a mantener dos módulos sincronizados sobre la misma regla.

---

### Task 1: Los tres puentes

**Files:**
- Modify: `backend/app/models/mapeo_externo.py`
- Create: `backend/app/services/integracion_ir_service.py`
- Test: `backend/tests/test_integracion_ir.py`

**Interfaces:**
- Consumes: `integracion_dimensiones_service.Hallazgo` / `SEVERIDAD_ERROR` / `SEVERIDAD_AVISO`; `maestro_medico_service.detectar_duplicados(db, pais_codigo, *, exequatur=...) -> {"duros": [...], "blandos": [...]}` (cada DTO trae `id`); `Config.MapeoExterno`.
- Produces: `ENT_MEDICO_IR = "medico_ir"`, `ENT_PRODUCTO_IR = "producto_ir"`, `ENT_PERIODO_IR = "periodo_ir"`; `ConteoIR` (dataclass); `sincronizar_ir(db, pais_codigo) -> dict`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_integracion_ir.py`:

```python
"""Equivalencias del módulo IR: prescriptor, producto y período.

Este sub-proyecto NO construye el indicador EVO_IR: construye los tres puentes
que la atribución necesita y mide qué tan bien resuelven. Ver el diseño en
`docs/superpowers/specs/2026-08-11-integracion-mallen-ir-equivalencias-design.md`.

Necesita PostgreSQL real: cruza tres esquemas con claves compuestas.
"""
from datetime import date, datetime
from decimal import Decimal

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
    Ciclo, Gerente, Linea, Medico, Pais, Producto, RepresentanteMedico,
)
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedicoIR, ExtDimPais, ExtDimPeriodoIR,
    ExtDimProducto, ExtDimProductoIR, ExtDimRepresentante, ExtFactPrescripcionDetalle,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno
from app.models.visita import MedicoVisita
from app.services import integracion_ir_service as ir

BD_PRUEBA = "vista_test_ir"


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
    for tabla in ("ext.factprescripciondetalle", "ext.dimmedicoir",
                  "ext.dimproductoir", "ext.dimperiodoir",
                  "ext.dimproducto", "ext.controlcarga",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais",
                  '"Visita"."DIM_MedicoVisita"',
                  '"Config"."MapeoExterno"', '"Config"."DIM_Medico"',
                  '"Config"."DIM_Producto"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def escenario(db):
    """País, línea, un representante, un ciclo y su equivalente en `ext`.

    Deja también el mapeo de ciclo y representante ya resuelto, como si el
    sub-proyecto 2 hubiera corrido: los puentes del IR se apoyan en él.
    """
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="gerente@ejemplo.com", tipo="DISTRITO")
    db.add(gerente)
    db.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             gerente_id=gerente.id, codigo="VM01",
                             nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    db.add_all([rm, ciclo])
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31), dias_laborables=20,
                       cerrado=False))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtControlCarga(
        lote_id=2001, sistema_origen="CLOSEUP", modulo="IR", pais_codigo="DO",
        ciclo_codigo="C01-2026", fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="VALIDADO"))
    db.flush()
    for entidad, codigo, interno in ((ENT_REPRESENTANTE, "VM01", rm.id),
                                     (ENT_CICLO, "C01-2026", ciclo.id)):
        db.add(MapeoExterno(entidad=entidad, pais_codigo="DO",
                            codigo_externo=codigo, id_interno=interno))
    db.commit()
    return {"db": db, "rm": rm, "ciclo": ciclo, "linea": linea}


def _medico_maestro(db, nombre="MEDICO UNO", exequatur="EX-100"):
    m = Medico(pais_codigo="DO", nombre=nombre, exequatur=exequatur, activo=True)
    db.add(m)
    db.flush()
    return m


def _medico_ir(db, medico_ir_codigo="MIR-1", exequatur="EX-100",
               nombre="MEDICO UNO"):
    db.add(ExtDimMedicoIR(pais_codigo="DO", medico_ir_codigo=medico_ir_codigo,
                          nombre=nombre, exequatur=exequatur, activo=True))
    db.flush()


def _producto_ir(db, producto_ir_codigo="PIR-1", producto_codigo="P1",
                 es_propio=True):
    db.add(ExtDimProductoIR(pais_codigo="DO", producto_ir_codigo=producto_ir_codigo,
                            nombre=f"Producto {producto_ir_codigo}",
                            producto_codigo=producto_codigo,
                            es_propio=es_propio, activo=True))
    db.flush()


def _periodo_ir(db, periodo_codigo="2026-01", ciclo_codigo="C01-2026"):
    db.add(ExtDimPeriodoIR(pais_codigo="DO", periodo_codigo=periodo_codigo,
                           anio=2026, mes=1, fecha_inicio=date(2026, 1, 1),
                           fecha_fin=date(2026, 1, 31),
                           ciclo_codigo=ciclo_codigo, cerrado=False))
    db.flush()


def _conteo(resultado, entidad):
    return next(c for c in resultado["entidades"] if c["entidad"] == entidad)


# ── Puente del prescriptor ───────────────────────────────────────────────

def test_prescriptor_con_exequatur_en_el_maestro_se_enlaza(escenario):
    db = escenario["db"]
    medico = _medico_maestro(db, exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_MEDICO_IR,
                 MapeoExterno.codigo_externo == "MIR-1").one())
    assert m.id_interno == medico.id
    assert _conteo(r, ir.ENT_MEDICO_IR)["enlazados"] == 1


def test_prescriptor_sin_contraparte_NO_crea_medico(escenario):
    """El test que protege los denominadores de cobertura y categorización:
    un prescriptor que ningún representante trabaja no debe entrar al maestro."""
    db = escenario["db"]
    _medico_ir(db, "MIR-9", exequatur="EX-999")
    db.commit()
    antes = db.query(Medico).count()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(Medico).count() == antes
    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    assert _conteo(r, ir.ENT_MEDICO_IR)["no_enlazados"] == 1


def test_exequatur_que_solo_difiere_en_formato_es_casi_enlace(escenario):
    """NO se enlaza: el maestro compara exacto y aquí no se inventa una
    normalización privada. Se cuenta aparte para que sea accionable."""
    db = escenario["db"]
    _medico_maestro(db, exequatur="12345")
    _medico_ir(db, "MIR-2", exequatur="12.345")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    c = _conteo(r, ir.ENT_MEDICO_IR)
    assert c["no_enlazados"] == 1
    assert c["casi_enlazados"] == 1


def test_cien_huerfanos_no_producen_hallazgos(escenario):
    """dimmedicoir trae TODO el mercado: un hallazgo por fila dejaría la
    pantalla inservible y enterraría los pocos que sí exigen acción."""
    db = escenario["db"]
    for i in range(100):
        _medico_ir(db, f"MIR-{i}", exequatur=f"EX-{i}", nombre=f"MEDICO {i}")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert _conteo(r, ir.ENT_MEDICO_IR)["no_enlazados"] == 100
    assert [h for h in r["hallazgos"] if h["entidad"] == ir.ENT_MEDICO_IR] == []


def test_exequatur_duplicado_en_el_maestro_no_enlaza_y_avisa(escenario):
    """Dos médicos con el mismo exequátur impiden decidir a cuál enlazar. Es un
    defecto del maestro, acotado, y por eso SÍ genera hallazgo."""
    db = escenario["db"]
    _medico_maestro(db, nombre="MEDICO UNO", exequatur="EX-100")
    _medico_maestro(db, nombre="MEDICO DOS", exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 0
    errores = [h for h in r["hallazgos"]
               if h["entidad"] == ir.ENT_MEDICO_IR and h["severidad"] == "error"]
    assert len(errores) == 1


# ── Puente del producto ──────────────────────────────────────────────────

def test_producto_propio_con_equivalencia_se_enlaza(escenario):
    db = escenario["db"]
    p = Producto(codigo="P1", nombre="Producto Uno",
                 linea_id=escenario["linea"].id, activo=True)
    db.add(p)
    db.flush()
    _producto_ir(db, "PIR-1", producto_codigo="P1", es_propio=True)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_PRODUCTO_IR,
                 MapeoExterno.codigo_externo == "PIR-1").one())
    assert m.id_interno == p.id
    assert _conteo(r, ir.ENT_PRODUCTO_IR)["enlazados"] == 1


def test_producto_de_competencia_se_omite_SIN_hallazgo(escenario):
    """Los productos de otros laboratorios existen a propósito (§11.8): hacen
    falta para medir participación de mercado. Que no mapeen es lo esperado."""
    db = escenario["db"]
    _producto_ir(db, "PIR-C", producto_codigo=None, es_propio=False)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    c = _conteo(r, ir.ENT_PRODUCTO_IR)
    assert c["omitidos"] == 1
    assert c["no_enlazados"] == 0
    assert [h for h in r["hallazgos"] if h["entidad"] == ir.ENT_PRODUCTO_IR] == []


def test_producto_propio_sin_equivalencia_es_error(escenario):
    """Un producto de Mallén cuyas recetas nadie va a poder contar."""
    db = escenario["db"]
    _producto_ir(db, "PIR-X", producto_codigo=None, es_propio=True)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    errores = [h for h in r["hallazgos"]
               if h["entidad"] == ir.ENT_PRODUCTO_IR and h["severidad"] == "error"]
    assert len(errores) == 1
    assert _conteo(r, ir.ENT_PRODUCTO_IR)["no_enlazados"] == 1


# ── Puente del período ───────────────────────────────────────────────────

def test_periodo_con_ciclo_se_enlaza(escenario):
    db = escenario["db"]
    _periodo_ir(db, "2026-01", ciclo_codigo="C01-2026")
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == ir.ENT_PERIODO_IR,
                 MapeoExterno.codigo_externo == "2026-01").one())
    assert m.id_interno == escenario["ciclo"].id
    assert _conteo(r, ir.ENT_PERIODO_IR)["enlazados"] == 1


def test_periodo_sin_ciclo_avisa_y_no_se_enlaza(escenario):
    db = escenario["db"]
    _periodo_ir(db, "2026-02", ciclo_codigo=None)
    db.commit()

    r = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_PERIODO_IR).count() == 0
    avisos = [h for h in r["hallazgos"]
              if h["entidad"] == ir.ENT_PERIODO_IR and h["severidad"] == "aviso"]
    assert len(avisos) == 1


def test_resincronizar_no_duplica_mapeos(escenario):
    db = escenario["db"]
    _medico_maestro(db, exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    _periodo_ir(db, "2026-01", ciclo_codigo="C01-2026")
    db.commit()

    ir.sincronizar_ir(db, "DO")
    r2 = ir.sincronizar_ir(db, "DO")

    assert db.query(MapeoExterno).filter(
        MapeoExterno.entidad == ir.ENT_MEDICO_IR).count() == 1
    # La segunda corrida ya no crea el mapeo: lo encuentra.
    assert _conteo(r2, ir.ENT_MEDICO_IR)["enlazados"] == 0
    assert _conteo(r2, ir.ENT_MEDICO_IR)["ya_enlazados"] == 1
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ir.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.integracion_ir_service'`

- [ ] **Step 3: Añadir las tres constantes de entidad**

En `backend/app/models/mapeo_externo.py`, después de `ENT_PRODUCTO = "producto"` (línea 35) y **antes** del bloque `ENTIDADES`:

```python
#: Módulo IR (Close-Up). NO entran en `ENTIDADES`: esa tupla es el orden de
#: sincronización de las nueve dimensiones de `integracion_dimensiones_service`,
#: que CREAN el registro interno cuando falta. Los puentes del IR solo enlazan
#: contra lo que ya existe (ver `integracion_ir_service`), así que meterlos ahí
#: los haría correr con una semántica que no es la suya.
ENT_MEDICO_IR = "medico_ir"
ENT_PRODUCTO_IR = "producto_ir"
ENT_PERIODO_IR = "periodo_ir"
```

- [ ] **Step 4: Crear el servicio con los tres puentes**

Crear `backend/app/services/integracion_ir_service.py`:

```python
"""Equivalencias del módulo de Prescripción IR (Close-Up) con VISTA.

QUÉ CONSTRUYE Y QUÉ NO
----------------------
Construye los tres puentes que la atribución de una receta necesita —
prescriptor, producto y período — y un diagnóstico que mide qué tan bien
resuelven. NO construye el indicador `EVO_IR`: el requerimiento reserva por
escrito la estructura del IR como la única que todavía puede cambiar
(pendiente 1 de §10) y manda verificar el exequátur con muestra real antes de
desarrollar (§11.9). Este módulo produce esa verificación.

POR QUÉ ENLAZA SIN CREAR
------------------------
Las nueve dimensiones de `integracion_dimensiones_service` crean el registro
interno cuando falta, y está bien: son el maestro de la operación. Aquí no.
`dimmedicoir` trae el universo de Close-Up, que es TODO el mercado (≈10.000
médicos, §9.1). Crear en `Config.DIM_Medico` a un prescriptor que ningún
representante trabaja lo metería en los denominadores de cobertura y
categorización, que es un daño silencioso: las cifras bajan y nada explica por
qué. Una receta cuyo prescriptor no se puede enlazar se cuenta para el mercado
y no se atribuye a nadie — literalmente lo que dice el §3.2 del contrato.
"""
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Medico, Producto
from app.models.integracion_ext import (
    ExtDimMedicoIR, ExtDimPeriodoIR, ExtDimProductoIR,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_MEDICO_IR, ENT_PERIODO_IR, ENT_PRODUCTO_IR, MapeoExterno,
)
from app.services import integracion_mapeo as mapeo
from app.services import maestro_medico_service
from app.services.integracion_dimensiones_service import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, Hallazgo,
)

#: Los tres códigos externos caben de sobra en `MapeoExterno.codigo_externo`
#: (60): `medico_ir_codigo` y `producto_ir_codigo` son String(50) y
#: `periodo_codigo` String(20). Por eso aquí no hay guarda de longitud, a
#: diferencia de los integradores que construyen claves compuestas.

RESULTADO_ENLAZADO = "enlazado"
RESULTADO_YA_ENLAZADO = "ya_enlazado"
RESULTADO_NO_ENLAZADO = "no_enlazado"


@dataclass
class ConteoIR:
    """Distinto de `Conteo` de dimensiones a propósito: aquí nada se CREA.

    `omitidos` es el no-enlace ESPERADO (un producto de la competencia);
    `no_enlazados` es el que puede doler. Separarlos es lo que permite leer el
    resultado de un vistazo.
    """
    entidad: str
    en_ext: int = 0
    enlazados: int = 0
    ya_enlazados: int = 0
    no_enlazados: int = 0
    casi_enlazados: int = 0
    omitidos: int = 0

    def anotar(self, resultado: str) -> None:
        if resultado == RESULTADO_ENLAZADO:
            self.enlazados += 1
        elif resultado == RESULTADO_YA_ENLAZADO:
            self.ya_enlazados += 1
        else:
            self.no_enlazados += 1

    def como_dict(self) -> dict:
        return {"entidad": self.entidad, "en_ext": self.en_ext,
                "enlazados": self.enlazados, "ya_enlazados": self.ya_enlazados,
                "no_enlazados": self.no_enlazados,
                "casi_enlazados": self.casi_enlazados,
                "omitidos": self.omitidos}


def _enlazar(db: Session, entidad: str, pais_codigo: str, codigo_externo: str,
             modelo, buscar) -> tuple[object | None, str]:
    """Enlaza contra lo que ya existe; si no hay contraparte, devuelve `None`.

    NO es `integracion_mapeo.resolver`: aquél CREA el registro interno cuando no
    lo encuentra, que es lo correcto para las nueve dimensiones y exactamente lo
    que aquí no se debe hacer. Sí comparte su manejo del mapeo huérfano: si el
    registro interno se borró a mano, el mapeo se descarta y se resuelve de nuevo
    en vez de quedar bloqueado para siempre.
    """
    m = (db.query(MapeoExterno)
         .filter(MapeoExterno.entidad == entidad,
                 MapeoExterno.pais_codigo == pais_codigo,
                 MapeoExterno.codigo_externo == codigo_externo).first())
    if m is not None:
        registro = db.get(modelo, m.id_interno)
        if registro is not None:
            return registro, RESULTADO_YA_ENLAZADO
        db.delete(m)
        db.flush()

    existente = buscar()
    if existente is None:
        return None, RESULTADO_NO_ENLAZADO
    db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                        codigo_externo=codigo_externo, id_interno=existente.id))
    db.flush()
    return existente, RESULTADO_ENLAZADO


def _solo_alfanumerico(valor: str | None) -> str:
    """Para detectar el CASI-enlace, nunca para enlazar."""
    return "".join(c for c in (valor or "") if c.isalnum()).upper()


def _indice_exequatur(db: Session, pais_codigo: str) -> dict[str, set[str]]:
    """Los exequátur del maestro, agrupados por su forma sin puntuación.

    Se construye UNA vez por corrida. La versión ingenua —consultar el maestro
    por cada prescriptor no enlazado— lo recorre entero miles de veces:
    `dimmedicoir` trae TODO el mercado (≈10.000 médicos, §9.1 del requerimiento),
    así que el coste sería el producto de los dos universos.
    """
    indice: dict[str, set[str]] = {}
    for (ex,) in (db.query(Medico.exequatur)
                  .filter(Medico.pais_codigo == pais_codigo,
                          Medico.activo == True,  # noqa: E712
                          Medico.exequatur.isnot(None)).all()):
        indice.setdefault(_solo_alfanumerico(ex), set()).add(ex)
    return indice


def _es_casi_enlace(indice: dict[str, set[str]], exequatur: str | None) -> bool:
    """¿Hay en el maestro un exequátur que solo difiere en formato?

    Es «casi» y no «enlace» a propósito: se cuenta y se muestra, nunca se
    enlaza. Si la única coincidencia es el propio valor, no hay casi-enlace —
    ese caso ya habría enlazado por la vía normal.
    """
    clave = _solo_alfanumerico(exequatur)
    if not clave:
        return False
    otros = indice.get(clave)
    return bool(otros) and otros != {exequatur}


def sincronizar_medico_ir(db: Session, pais_codigo: str,
                          hallazgos: list) -> ConteoIR:
    """`ext.dimmedicoir` → `Config.DIM_Medico`, por exequátur EXACTO.

    Reutiliza `maestro_medico_service.detectar_duplicados`, que es el criterio
    con el que el maestro decide si dos médicos son el mismo: compara el
    exequátur exacto, filtra por país y por activo. No se inventa aquí una
    normalización propia, aunque subiría la tasa de enlace — enlazaría como el
    mismo médico a dos que la deduplicación del maestro considera distintos, y
    el desacuerdo solo se descubriría cuando las cifras no cuadraran.

    NO emite hallazgo por prescriptor no enlazado: son miles y enterrarían los
    pocos que sí exigen acción. Se cuentan y el diagnóstico los muestra.
    """
    conteo = ConteoIR(ENT_MEDICO_IR)
    indice = _indice_exequatur(db, pais_codigo)
    filas = (db.query(ExtDimMedicoIR)
             .filter(ExtDimMedicoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        duros = maestro_medico_service.detectar_duplicados(
            db, pais_codigo, exequatur=fila.exequatur)["duros"]
        if len(duros) > 1:
            # Acotado y accionable: es un defecto del maestro, no de Close-Up.
            conteo.no_enlazados += 1
            hallazgos.append(Hallazgo(
                ENT_MEDICO_IR, fila.medico_ir_codigo,
                f"El exequátur «{fila.exequatur}» aparece en {len(duros)} médicos "
                f"del maestro; no se puede decidir a cuál enlazar. Deduplica el "
                f"maestro y vuelve a sincronizar.", SEVERIDAD_ERROR))
            continue

        def _buscar(ids=[d["id"] for d in duros]):
            return db.get(Medico, ids[0]) if ids else None

        registro, resultado = _enlazar(db, ENT_MEDICO_IR, pais_codigo,
                                       fila.medico_ir_codigo, Medico, _buscar)
        conteo.anotar(resultado)
        if registro is None and _es_casi_enlace(indice, fila.exequatur):
            conteo.casi_enlazados += 1
    return conteo


def sincronizar_producto_ir(db: Session, pais_codigo: str,
                            hallazgos: list) -> ConteoIR:
    """`ext.dimproductoir` → `Config.DIM_Producto`, por la equivalencia que la
    propia dimensión trae en `producto_codigo`.

    Los productos de la competencia llegan a propósito y sin equivalencia
    (§11.8): hacen falta para medir participación de mercado. Que no mapeen es
    lo ESPERADO y no genera hallazgo. Lo que sí es error es un producto marcado
    `es_propio` sin equivalencia: sus recetas no las va a poder contar nadie.
    """
    conteo = ConteoIR(ENT_PRODUCTO_IR)
    filas = (db.query(ExtDimProductoIR)
             .filter(ExtDimProductoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not fila.producto_codigo:
            if fila.es_propio:
                conteo.no_enlazados += 1
                hallazgos.append(Hallazgo(
                    ENT_PRODUCTO_IR, fila.producto_ir_codigo,
                    f"El producto «{fila.nombre}» está marcado como propio pero no "
                    f"trae equivalencia con el catálogo de Mallén; sus recetas no "
                    f"se podrán contar.", SEVERIDAD_ERROR))
            else:
                conteo.omitidos += 1
            continue

        def _buscar(f=fila):
            return db.query(Producto).filter(
                Producto.codigo == f.producto_codigo).first()

        registro, resultado = _enlazar(db, ENT_PRODUCTO_IR, pais_codigo,
                                       fila.producto_ir_codigo, Producto, _buscar)
        conteo.anotar(resultado)
        if registro is None and fila.es_propio:
            hallazgos.append(Hallazgo(
                ENT_PRODUCTO_IR, fila.producto_ir_codigo,
                f"El producto propio «{fila.nombre}» declara la equivalencia "
                f"«{fila.producto_codigo}», que no existe en el catálogo de VISTA.",
                SEVERIDAD_ERROR))
    return conteo


def sincronizar_periodo_ir(db: Session, pais_codigo: str,
                           hallazgos: list) -> ConteoIR:
    """`ext.dimperiodoir` → `Config.DIM_Ciclo`, por el `ciclo_codigo` que la
    dimensión declara.

    Si viene nulo, el mes de Close-Up no pertenece a ningún ciclo y sus recetas
    no se pueden ubicar en el tiempo de VISTA. NO se adivina por fechas: la
    dimensión trae `fecha_inicio`/`fecha_fin`, pero derivar de ahí sustituiría
    una decisión de Mallén por una inferencia nuestra, y un mes puede solapar
    dos ciclos.
    """
    conteo = ConteoIR(ENT_PERIODO_IR)
    filas = (db.query(ExtDimPeriodoIR)
             .filter(ExtDimPeriodoIR.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not fila.ciclo_codigo:
            conteo.no_enlazados += 1
            hallazgos.append(Hallazgo(
                ENT_PERIODO_IR, fila.periodo_codigo,
                f"El período «{fila.periodo_codigo}» no declara a qué ciclo "
                f"pertenece; sus recetas no se pueden ubicar en el tiempo.",
                SEVERIDAD_AVISO))
            continue

        def _buscar(f=fila):
            cid = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, f.ciclo_codigo)
            return db.get(Ciclo, cid) if cid else None

        registro, resultado = _enlazar(db, ENT_PERIODO_IR, pais_codigo,
                                       fila.periodo_codigo, Ciclo, _buscar)
        conteo.anotar(resultado)
        if registro is None:
            hallazgos.append(Hallazgo(
                ENT_PERIODO_IR, fila.periodo_codigo,
                f"El ciclo «{fila.ciclo_codigo}» del período no está sincronizado; "
                f"corre primero la sincronización de dimensiones.",
                SEVERIDAD_AVISO))
    return conteo


_PUENTES = (sincronizar_medico_ir, sincronizar_producto_ir, sincronizar_periodo_ir)


def sincronizar_ir(db: Session, pais_codigo: str) -> dict:
    """Los tres puentes, un solo commit al final.

    El orden no importa: a diferencia de las nueve dimensiones, ninguno de los
    tres resuelve claves contra los otros. Se mantiene fijo solo para que la
    salida sea estable.
    """
    hallazgos: list[Hallazgo] = []
    conteos = [puente(db, pais_codigo, hallazgos) for puente in _PUENTES]
    db.commit()

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    logger.info(f"Equivalencias IR de {pais_codigo}: "
                f"{sum(c.enlazados for c in conteos)} enlazadas, "
                f"{sum(c.no_enlazados for c in conteos)} sin enlazar, "
                f"{errores} con error")
    return {
        "pais_codigo": pais_codigo,
        "entidades": [c.como_dict() for c in conteos],
        "hallazgos": [{"entidad": h.entidad, "codigo_externo": h.codigo_externo,
                       "problema": h.problema, "severidad": h.severidad}
                      for h in hallazgos],
    }
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ir.py -q`
Expected: PASS — 11 tests

- [ ] **Step 6: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 7: Commit**

```bash
git add backend/app/models/mapeo_externo.py backend/app/services/integracion_ir_service.py backend/tests/test_integracion_ir.py
git commit -m "feat(integracion) los tres puentes de equivalencia del modulo IR"
```

---

### Task 2: La cadena de atribución y el diagnóstico

**Files:**
- Modify: `backend/app/services/integracion_ir_service.py`
- Test: `backend/tests/test_integracion_ir.py`

**Interfaces:**
- Consumes: de la Tarea 1, `ENT_MEDICO_IR` / `ENT_PRODUCTO_IR` / `ENT_PERIODO_IR` y `_enlazar`. De fuera: `visita_aprobacion_service.ordenes_ciclo(db) -> dict[int, int]` y `cuenta_en_ciclo(m, ciclo_orden, ordenes) -> bool`; `integracion_mapeo.id_mapeado(db, entidad, pais_codigo, codigo_externo) -> int | None`.
- Produces: `atribuir(db, fila, ctx) -> tuple[int | None, str]` donde el segundo valor es uno de `ATR_DIRECTA` / `ATR_CADENA` / `ATR_AMBIGUA` / `ATR_HUERFANA`; `diagnosticar_ir(db, pais_codigo) -> dict`.

- [ ] **Step 1: Escribir los tests**

Añadir a `backend/tests/test_integracion_ir.py`:

```python
# ── La cadena de atribución ──────────────────────────────────────────────

def _panel(db, rm_id, maestro_medico_id, estado="APROBADO", activo=True,
           ciclo_alta_id=None, ciclo_baja_id=None):
    m = MedicoVisita(vm_id=rm_id, maestro_medico_id=maestro_medico_id,
                     nombre_completo="MEDICO UNO", estado_aprobacion=estado,
                     activo=activo, ciclo_alta_id=ciclo_alta_id,
                     ciclo_baja_id=ciclo_baja_id)
    db.add(m)
    db.flush()
    return m


def _receta(db, origen_id="R-1", medico_ir="MIR-1", producto_ir="PIR-1",
            rm_codigo=None, periodo="2026-01", unidades=10):
    db.add(ExtFactPrescripcionDetalle(
        lote_id=2001, origen_id=origen_id, pais_codigo="DO",
        periodo_codigo=periodo, producto_ir_codigo=producto_ir,
        medico_ir_codigo=medico_ir, rm_codigo=rm_codigo,
        unidades=Decimal(str(unidades))))
    db.flush()


def _segundo_rm(db, escenario, codigo="VM02", linea_id=None):
    rm = RepresentanteMedico(
        pais_codigo="DO", linea_id=linea_id or escenario["linea"].id,
        gerente_id=escenario["rm"].gerente_id, codigo=codigo,
        nombre=f"Representante {codigo}")
    db.add(rm)
    db.flush()
    return rm


def _base_ir(db, escenario, *, producto_linea_id="misma"):
    """Maestro + panel + las tres equivalencias resueltas, listo para atribuir."""
    medico = _medico_maestro(db, exequatur="EX-100")
    _medico_ir(db, "MIR-1", exequatur="EX-100")
    linea_id = (escenario["linea"].id if producto_linea_id == "misma"
                else producto_linea_id)
    p = Producto(codigo="P1", nombre="Producto Uno", linea_id=linea_id, activo=True)
    db.add(p)
    db.flush()
    _producto_ir(db, "PIR-1", producto_codigo="P1", es_propio=True)
    _periodo_ir(db, "2026-01", ciclo_codigo="C01-2026")
    return medico


def test_receta_con_rm_codigo_se_atribuye_directo(escenario):
    """Mallén ya atribuyó: su decisión manda y no se consulta el panel."""
    db = escenario["db"]
    _base_ir(db, escenario)
    _receta(db, "R-1", rm_codigo="VM01")
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["directas"] == 1
    assert d["recetas"]["por_cadena"] == 0


def test_receta_sin_rm_se_atribuye_por_el_panel(escenario):
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    _panel(db, escenario["rm"].id, medico.id)
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["por_cadena"] == 1
    assert d["recetas"]["ambiguas"] == 0


def test_dos_representantes_de_lineas_distintas_desempata_el_producto(escenario):
    """El test que justifica el puente de producto: sin la línea, este caso
    sería ambiguo y la receta se perdería."""
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    otra_linea = Linea(pais_codigo="DO", codigo="DERM", nombre="Dermatología")
    db.add(otra_linea)
    db.flush()
    rm2 = _segundo_rm(db, escenario, "VM02", linea_id=otra_linea.id)
    _panel(db, escenario["rm"].id, medico.id)
    _panel(db, rm2.id, medico.id)
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["por_cadena"] == 1
    assert d["recetas"]["ambiguas"] == 0


def test_producto_sin_linea_no_puede_desempatar(escenario):
    db = escenario["db"]
    medico = _base_ir(db, escenario, producto_linea_id=None)
    rm2 = _segundo_rm(db, escenario, "VM02")
    _panel(db, escenario["rm"].id, medico.id)
    _panel(db, rm2.id, medico.id)
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["ambiguas"] == 1
    assert d["recetas"]["por_cadena"] == 0


def test_dos_representantes_de_la_MISMA_linea_es_ambigua(escenario):
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    rm2 = _segundo_rm(db, escenario, "VM02")
    _panel(db, escenario["rm"].id, medico.id)
    _panel(db, rm2.id, medico.id)
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["ambiguas"] == 1


def test_panel_pendiente_de_alta_no_es_candidato(escenario):
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    _panel(db, escenario["rm"].id, medico.id, estado="PENDIENTE_ALTA")
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["por_cadena"] == 0
    assert d["recetas"]["huerfanas"] == 1


def test_panel_pendiente_de_BAJA_si_es_candidato(escenario):
    """Una baja solicitada sigue contando el ciclo actual. Endurecer el
    criterio a APROBADO perdería las recetas de todo médico en proceso de baja
    — y el conteo simplemente saldría más bajo, sin que nada lo delatara."""
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    _panel(db, escenario["rm"].id, medico.id, estado="PENDIENTE_BAJA")
    _receta(db, "R-1", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["por_cadena"] == 1


def test_alta_en_un_ciclo_posterior_no_cuenta_para_la_receta(escenario):
    """La pertenencia se evalúa para el ciclo de la RECETA, no para hoy: si no,
    reprocesar un lote viejo daría una atribución distinta según el día."""
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    ciclo2 = Ciclo(pais_codigo="DO", anio=2026, numero=2, nombre="Ciclo 2",
                   fecha_inicio=date(2026, 2, 1), fecha_fin=date(2026, 2, 28),
                   dias_laborables=20, cerrado=False)
    db.add(ciclo2)
    db.flush()
    _panel(db, escenario["rm"].id, medico.id, ciclo_alta_id=ciclo2.id)
    _receta(db, "R-1", rm_codigo=None)   # receta del período del ciclo 1
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["por_cadena"] == 0
    assert d["recetas"]["huerfanas"] == 1


def test_prescriptor_huerfano_no_se_atribuye(escenario):
    db = escenario["db"]
    _base_ir(db, escenario)
    _medico_ir(db, "MIR-9", exequatur="EX-999")
    _receta(db, "R-1", medico_ir="MIR-9", rm_codigo=None)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["recetas"]["huerfanas"] == 1


def test_los_cuatro_baldes_suman_el_total(escenario):
    """Ninguna receta se pierde ni se cuenta dos veces."""
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    rm2 = _segundo_rm(db, escenario, "VM02")
    _panel(db, escenario["rm"].id, medico.id)
    _panel(db, rm2.id, medico.id)
    _medico_ir(db, "MIR-9", exequatur="EX-999")
    _receta(db, "R-1", rm_codigo="VM01")          # directa
    _receta(db, "R-2", medico_ir="MIR-9")         # huérfana
    _receta(db, "R-3")                            # ambigua (misma línea)
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")
    r = d["recetas"]

    assert r["directas"] + r["por_cadena"] + r["ambiguas"] + r["huerfanas"] == r["total"]
    assert r["total"] == 3


def test_el_diagnostico_no_escribe_nada_y_es_repetible(escenario):
    db = escenario["db"]
    medico = _base_ir(db, escenario)
    _panel(db, escenario["rm"].id, medico.id)
    _receta(db, "R-1")
    db.commit()
    ir.sincronizar_ir(db, "DO")
    mapeos_antes = db.query(MapeoExterno).count()

    d1 = ir.diagnosticar_ir(db, "DO")
    d2 = ir.diagnosticar_ir(db, "DO")

    assert d1 == d2
    assert db.query(MapeoExterno).count() == mapeos_antes


def test_el_diagnostico_separa_huerfanos_de_casi_enlaces(escenario):
    db = escenario["db"]
    _medico_maestro(db, exequatur="12345")
    _medico_ir(db, "MIR-2", exequatur="12.345")   # casi-enlace
    _medico_ir(db, "MIR-9", exequatur="EX-999")   # huérfano real
    db.commit()
    ir.sincronizar_ir(db, "DO")

    d = ir.diagnosticar_ir(db, "DO")

    assert d["prescriptores"]["casi_enlazados"] == 1
    assert d["prescriptores"]["huerfanos"] == 1
    assert len(d["prescriptores"]["ejemplos_huerfanos"]) == 1
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ir.py -q -k "atribu or diagnostico or baldes or panel or receta or producto_sin_linea or representantes or huerfano"`
Expected: FAIL — `AttributeError: module 'app.services.integracion_ir_service' has no attribute 'diagnosticar_ir'`

- [ ] **Step 3: Añadir la cadena de atribución y el diagnóstico**

Añadir al final de `backend/app/services/integracion_ir_service.py`:

```python
# ===========================================================================
# La cadena de atribución
# ===========================================================================

ATR_DIRECTA = "directa"
ATR_CADENA = "por_cadena"
ATR_AMBIGUA = "ambigua"
ATR_HUERFANA = "huerfana"


@dataclass
class ContextoAtribucion:
    """Todo lo que la atribución necesita, resuelto UNA vez por corrida.

    Sin esto, cada receta dispararía media docena de consultas: `ext` puede
    traer cientos de miles de filas por período.
    """
    pais_codigo: str
    #: código externo → id interno, de los tres puentes
    medicos: dict = field(default_factory=dict)
    productos: dict = field(default_factory=dict)
    periodos: dict = field(default_factory=dict)
    #: rm_codigo de Mallén → id interno
    representantes: dict = field(default_factory=dict)
    #: id de DIM_Producto → linea_id (puede ser None)
    linea_de_producto: dict = field(default_factory=dict)
    #: id de DIM_Medico → [(vm_id, linea_id del vm, fila de panel)]
    paneles: dict = field(default_factory=dict)
    #: id de DIM_Ciclo → orden (anio*1000+numero), de `ordenes_ciclo`
    ordenes: dict = field(default_factory=dict)


def _mapa(db: Session, entidad: str, pais_codigo: str) -> dict:
    return {m.codigo_externo: m.id_interno
            for m in db.query(MapeoExterno).filter(
                MapeoExterno.entidad == entidad,
                MapeoExterno.pais_codigo == pais_codigo).all()}


def _contexto(db: Session, pais_codigo: str) -> ContextoAtribucion:
    from app.models.dimensiones import RepresentanteMedico
    from app.models.mapeo_externo import ENT_REPRESENTANTE
    from app.models.visita import MedicoVisita
    from app.services.visita_aprobacion_service import ordenes_ciclo

    ctx = ContextoAtribucion(pais_codigo=pais_codigo)
    ctx.medicos = _mapa(db, ENT_MEDICO_IR, pais_codigo)
    ctx.productos = _mapa(db, ENT_PRODUCTO_IR, pais_codigo)
    ctx.periodos = _mapa(db, ENT_PERIODO_IR, pais_codigo)
    ctx.representantes = _mapa(db, ENT_REPRESENTANTE, pais_codigo)
    ctx.ordenes = ordenes_ciclo(db)

    for p in db.query(Producto).all():
        ctx.linea_de_producto[p.id] = p.linea_id

    lineas_rm = {r.id: r.linea_id for r in
                 db.query(RepresentanteMedico).filter(
                     RepresentanteMedico.pais_codigo == pais_codigo).all()}
    for m in (db.query(MedicoVisita)
              .filter(MedicoVisita.maestro_medico_id.isnot(None)).all()):
        if m.vm_id not in lineas_rm:      # panel de otro país
            continue
        ctx.paneles.setdefault(m.maestro_medico_id, []).append(
            (m.vm_id, lineas_rm[m.vm_id], m))
    return ctx


def atribuir(db: Session, fila, ctx: ContextoAtribucion) -> tuple[int | None, str]:
    """¿De qué representante es esta receta?

    1. Si `rm_codigo` viene informado, Mallén ya atribuyó y su decisión manda.
    2. Si no, exequátur → maestro → filas de panel de ESE médico.
    3. Se filtran por pertenencia al panel EN EL CICLO de la receta, con
       `cuenta_en_ciclo` — el mismo criterio que usan la planeación y la
       cobertura. Admite `PENDIENTE_BAJA` a propósito: una baja solicitada
       sigue contando el ciclo actual. NO se usa
       `estado_aprobacion == "APROBADO"`, que responde otra pregunta
       («¿se le puede registrar una visita hoy?») y dejaría sin atribuir las
       recetas de todo médico en proceso de baja.
    4. Si el producto tiene línea, se desempata por ella.
    5. Un solo candidato → atribuida. Cero o varios → no se atribuye: cuenta
       para el mercado, que es lo que dice el §3.2 del contrato.
    """
    from app.services.visita_aprobacion_service import cuenta_en_ciclo

    if fila.rm_codigo:
        rm_id = ctx.representantes.get(fila.rm_codigo)
        if rm_id is not None:
            return rm_id, ATR_DIRECTA
        # Mallén atribuyó a un representante que VISTA no conoce: no se cae al
        # panel, porque contradecir la atribución de la fuente sería inventar.
        return None, ATR_HUERFANA

    medico_id = ctx.medicos.get(fila.medico_ir_codigo)
    if medico_id is None:
        return None, ATR_HUERFANA

    candidatos = ctx.paneles.get(medico_id, [])
    ciclo_id = ctx.periodos.get(fila.periodo_codigo)
    ciclo_orden = ctx.ordenes.get(ciclo_id) if ciclo_id is not None else None
    candidatos = [c for c in candidatos
                  if cuenta_en_ciclo(c[2], ciclo_orden, ctx.ordenes)]
    if not candidatos:
        return None, ATR_HUERFANA

    if len(candidatos) > 1:
        producto_id = ctx.productos.get(fila.producto_ir_codigo)
        linea = ctx.linea_de_producto.get(producto_id) if producto_id else None
        if linea is not None:
            candidatos = [c for c in candidatos if c[1] == linea]

    if len(candidatos) == 1:
        return candidatos[0][0], ATR_CADENA
    if not candidatos:
        return None, ATR_HUERFANA
    return None, ATR_AMBIGUA


# ===========================================================================
# El diagnóstico
# ===========================================================================

#: Cuántos ejemplos se muestran de cada clase. Una lista de miles no la lee
#: nadie; lo que el operador necesita es reconocer el patrón.
EJEMPLOS = 10


def diagnosticar_ir(db: Session, pais_codigo: str) -> dict:
    """Qué tan bien enlaza el IR, ANTES de construir el indicador.

    Es lo que el §11.9 del requerimiento manda comprobar con muestra real: si
    la mayoría de las recetas cae en huérfanas, el problema es del archivo de
    Close-Up y no se arregla con código.

    De SOLO LECTURA: no escribe, no hace commit, no cierra lotes. Correrlo dos
    veces devuelve lo mismo.
    """
    ctx = _contexto(db, pais_codigo)

    indice = _indice_exequatur(db, pais_codigo)
    prescriptores = (db.query(ExtDimMedicoIR)
                     .filter(ExtDimMedicoIR.pais_codigo == pais_codigo).all())
    enlazados, casi, huerfanos = [], [], []
    for p in prescriptores:
        if p.medico_ir_codigo in ctx.medicos:
            enlazados.append(p)
        elif _es_casi_enlace(indice, p.exequatur):
            casi.append(p)
        else:
            huerfanos.append(p)
    con_panel = sum(1 for p in enlazados
                    if ctx.paneles.get(ctx.medicos[p.medico_ir_codigo]))

    productos = (db.query(ExtDimProductoIR)
                 .filter(ExtDimProductoIR.pais_codigo == pais_codigo).all())
    propios = [p for p in productos if p.es_propio]
    propios_sin_equivalencia = [p for p in propios
                                if p.producto_ir_codigo not in ctx.productos]

    periodos = (db.query(ExtDimPeriodoIR)
                .filter(ExtDimPeriodoIR.pais_codigo == pais_codigo).all())

    baldes = {ATR_DIRECTA: 0, ATR_CADENA: 0, ATR_AMBIGUA: 0, ATR_HUERFANA: 0}
    recetas = (db.query(ExtFactPrescripcionDetalle)
               .filter(ExtFactPrescripcionDetalle.pais_codigo == pais_codigo).all())
    for fila in recetas:
        _, balde = atribuir(db, fila, ctx)
        baldes[balde] += 1

    return {
        "pais_codigo": pais_codigo,
        "prescriptores": {
            "en_ext": len(prescriptores),
            "enlazados": len(enlazados),
            "con_panel": con_panel,
            "casi_enlazados": len(casi),
            "huerfanos": len(huerfanos),
            "ejemplos_casi_enlazados": [
                {"codigo": p.medico_ir_codigo, "exequatur": p.exequatur,
                 "nombre": p.nombre} for p in casi[:EJEMPLOS]],
            "ejemplos_huerfanos": [
                {"codigo": p.medico_ir_codigo, "exequatur": p.exequatur,
                 "nombre": p.nombre} for p in huerfanos[:EJEMPLOS]],
        },
        "productos": {
            "en_ext": len(productos),
            "propios": len(propios),
            "enlazados": len(ctx.productos),
            "propios_sin_equivalencia": len(propios_sin_equivalencia),
            "ejemplos_propios_sin_equivalencia": [
                {"codigo": p.producto_ir_codigo, "nombre": p.nombre}
                for p in propios_sin_equivalencia[:EJEMPLOS]],
        },
        "periodos": {
            "en_ext": len(periodos),
            "con_ciclo": len(ctx.periodos),
            "sin_ciclo": len(periodos) - len(ctx.periodos),
        },
        "recetas": {
            "total": len(recetas),
            "directas": baldes[ATR_DIRECTA],
            "por_cadena": baldes[ATR_CADENA],
            "ambiguas": baldes[ATR_AMBIGUA],
            "huerfanas": baldes[ATR_HUERFANA],
        },
    }
```

Y ampliar el import de la cabecera del archivo, que pasa a ser exactamente:

```python
from app.models.integracion_ext import (
    ExtDimMedicoIR, ExtDimPeriodoIR, ExtDimProductoIR, ExtFactPrescripcionDetalle,
)
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ir.py -q`
Expected: PASS — 23 tests

- [ ] **Step 5: Comprobar por mutación que el test de `PENDIENTE_BAJA` protege algo**

Cambiar temporalmente en `atribuir` el filtro por `[c for c in candidatos if c[2].estado_aprobacion == "APROBADO"]`.
Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ir.py -q -k pendiente_de_BAJA`
Expected: FAIL. Revertir el cambio y volver a correr: PASS.

- [ ] **Step 6: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/integracion_ir_service.py backend/tests/test_integracion_ir.py
git commit -m "feat(integracion) cadena de atribucion del IR y diagnostico de enlazabilidad"
```

---

### Task 3: Endpoints y pantalla

**Files:**
- Modify: `backend/app/api/v1/routers/integracion.py`
- Modify: `frontend/src/services/integracion.service.ts`
- Modify: `frontend/src/pages/integracion/LotesIntegracion.tsx:142`

**Interfaces:**
- Consumes: `integracion_ir_service.sincronizar_ir(db, pais_codigo) -> dict` y `diagnosticar_ir(db, pais_codigo) -> dict` (Tareas 1 y 2).
- Produces: `POST /integracion/ir/sincronizar?pais_codigo=` y `GET /integracion/ir/diagnostico?pais_codigo=`.

- [ ] **Step 1: Añadir los endpoints**

En `backend/app/api/v1/routers/integracion.py`, añadir al import de servicios:

```python
from app.services import integracion_ir_service as ir
```

y al final del archivo:

```python
@router.post("/ir/sincronizar",
             summary="Resolver las equivalencias del módulo IR de un país")
def sincronizar_ir(pais_codigo: str, db: Session = Depends(get_db),
                   _: Usuario = RequireTI):
    """Enlaza prescriptor, producto y período con los catálogos de VISTA.

    A diferencia de las dimensiones, este paso NO crea registros internos: un
    prescriptor de Close-Up que ningún representante trabaja no debe entrar al
    maestro de médicos. Lo que no enlaza se cuenta y se ve en el diagnóstico.
    """
    return ir.sincronizar_ir(db, pais_codigo)


@router.get("/ir/diagnostico",
            summary="Qué tan bien enlaza el IR y qué recetas serían atribuibles")
def diagnostico_ir(pais_codigo: str, db: Session = Depends(get_db),
                   _: Usuario = RequireTI):
    """Solo lectura. Es la comprobación que el requerimiento manda hacer con
    muestra real antes de construir el indicador EVO_IR (§11.9)."""
    return ir.diagnosticar_ir(db, pais_codigo)
```

- [ ] **Step 2: Comprobar que el backend arranca y las rutas quedan registradas**

Run:
```bash
cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if '/ir/' in r.path])"
```
Expected: `['/api/v1/integracion/ir/sincronizar', '/api/v1/integracion/ir/diagnostico']`

- [ ] **Step 3: Añadir tipos y llamadas al servicio del frontend**

Al final de `frontend/src/services/integracion.service.ts`:

```typescript
// ── Prescripción IR (sub-proyecto 6) ─────────────────────────────────────
export interface ConteoIR {
  entidad: string; en_ext: number; enlazados: number; ya_enlazados: number;
  no_enlazados: number; casi_enlazados: number; omitidos: number;
}

export interface ResultadoSincronizacionIR {
  pais_codigo: string;
  entidades: ConteoIR[];
  hallazgos: HallazgoDimension[];
}

export interface EjemploPrescriptor {
  codigo: string; exequatur: string; nombre: string;
}

export interface DiagnosticoIR {
  pais_codigo: string;
  prescriptores: {
    en_ext: number; enlazados: number; con_panel: number;
    casi_enlazados: number; huerfanos: number;
    ejemplos_casi_enlazados: EjemploPrescriptor[];
    ejemplos_huerfanos: EjemploPrescriptor[];
  };
  productos: {
    en_ext: number; propios: number; enlazados: number;
    propios_sin_equivalencia: number;
    ejemplos_propios_sin_equivalencia: { codigo: string; nombre: string }[];
  };
  periodos: { en_ext: number; con_ciclo: number; sin_ciclo: number };
  recetas: {
    total: number; directas: number; por_cadena: number;
    ambiguas: number; huerfanas: number;
  };
}

export const sincronizarIR = (paisCodigo: string) =>
  api.post<ResultadoSincronizacionIR>('/integracion/ir/sincronizar', null,
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const diagnosticoIR = (paisCodigo: string) =>
  api.get<DiagnosticoIR>('/integracion/ir/diagnostico',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);
```

- [ ] **Step 4: Añadir la sección a la pantalla**

En `frontend/src/pages/integracion/LotesIntegracion.tsx`, añadir a los imports del servicio (bloque de las líneas 15-22):

```typescript
  sincronizarIR, diagnosticoIR,
  type DiagnosticoIR, type ResultadoSincronizacionIR,
```

Montar la sección justo después de `<SeccionVisitas ... />` (línea 142):

```tsx
      <SeccionIR paisCodigo={paisCodigo} />
```

Y añadir el componente al final del archivo:

```tsx
function SeccionIR({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [resultado, setResultado] = useState<ResultadoSincronizacionIR | null>(null);
  const [error, setError] = useState<string | null>(null);

  const diag = useQuery<DiagnosticoIR>({
    queryKey: ['integracion-ir', paisCodigo],
    queryFn: () => diagnosticoIR(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const sincronizar = useMutation({
    mutationFn: () => sincronizarIR(paisCodigo as string),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-ir'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron resolver las equivalencias.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para revisar el módulo IR.
    </Alert>;
  }

  const d = diag.data;

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>
          Prescripción IR
        </Typography>
        <Button variant="contained" startIcon={<Sync />}
          disabled={sincronizar.isPending}
          onClick={() => sincronizar.mutate()}>
          {sincronizar.isPending ? 'Resolviendo…' : 'Resolver equivalencias'}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Enlaza el prescriptor (por exequátur), el producto y el período de
        Close-Up con los catálogos de VISTA. No crea médicos: un prescriptor
        que ningún representante trabaja se cuenta para el mercado y no se
        atribuye a nadie. El indicador EVO_IR todavía no se calcula.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {d && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Qué</TableCell>
                <TableCell align="right">En Mallén</TableCell>
                <TableCell align="right">Enlazados</TableCell>
                <TableCell align="right">Sin enlazar</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>Prescriptores (con panel: {d.prescriptores.con_panel})</TableCell>
                <TableCell align="right">{d.prescriptores.en_ext}</TableCell>
                <TableCell align="right">{d.prescriptores.enlazados}</TableCell>
                <TableCell align="right">
                  {d.prescriptores.huerfanos}
                  {d.prescriptores.casi_enlazados > 0 &&
                    ` (+${d.prescriptores.casi_enlazados} mal escritos)`}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Productos (propios: {d.productos.propios})</TableCell>
                <TableCell align="right">{d.productos.en_ext}</TableCell>
                <TableCell align="right">{d.productos.enlazados}</TableCell>
                <TableCell align="right">{d.productos.propios_sin_equivalencia}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Períodos</TableCell>
                <TableCell align="right">{d.periodos.en_ext}</TableCell>
                <TableCell align="right">{d.periodos.con_ciclo}</TableCell>
                <TableCell align="right">{d.periodos.sin_ciclo}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Paper>
      )}

      {d && d.recetas.total > 0 && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
            Recetas atribuibles ({d.recetas.total} en total)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {d.recetas.directas} traen representante de Mallén ·{' '}
            {d.recetas.por_cadena} se atribuyen por el panel ·{' '}
            {d.recetas.ambiguas} ambiguas ·{' '}
            {d.recetas.huerfanas} sin dueño (cuentan para el mercado)
          </Typography>
        </Paper>
      )}

      {resultado && resultado.hallazgos.length > 0 && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Entidad</TableCell>
                <TableCell>Código</TableCell>
                <TableCell>Problema</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {resultado.hallazgos.map((h, i) => (
                <TableRow key={i}>
                  <TableCell>{h.entidad}</TableCell>
                  <TableCell>{h.codigo_externo}</TableCell>
                  <TableCell>{h.problema}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  );
}
```

> `detalleError` ya existe en ese archivo (línea 25) y lo usan `SeccionDimensiones` y `SeccionVisitas`. Reutilizarlo tal cual; no escribir otro.

- [ ] **Step 5: Comprobar que el frontend compila**

Run: `cd frontend && npm run build`
Expected: build sin errores de TypeScript

- [ ] **Step 6: Correr la suite completa del backend**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/routers/integracion.py frontend/src/services/integracion.service.ts frontend/src/pages/integracion/LotesIntegracion.tsx
git commit -m "feat(integracion) endpoints y pantalla de equivalencias IR"
```
