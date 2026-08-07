# Recepción y validación de lotes de Mallén — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que VISTA pueda tomar un lote que Mallén dejó en `ext.controlcarga` con estado `RECIBIDO`, validarlo fila a fila, marcarlo `VALIDADO` o `RECHAZADO`, y mostrar un informe de qué corregir.

**Architecture:** Un modelo y migración para `Audit.IntegracionHallazgo` (la traza de lo que vino mal), un servicio de validación que recorre las 7 tablas de datos del contrato sin abortar por filas malas, un router `/integracion` para roles de TI, y una página que lista lotes y muestra sus hallazgos. **No integra nada a los esquemas internos de VISTA** — eso son los sub-proyectos siguientes.

**Tech Stack:** Backend: Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, pytest sobre PostgreSQL real. Frontend: React 18 + TypeScript, MUI v6, TanStack Query v5, axios, Zustand, react-router-dom v6 (`lazyWithReload`).

## Global Constraints

- **PROHIBIDO tocar el esquema `ext` de cualquier forma** (modelos, migración `0030`, o el SQL entregado). Es un contrato firmado con un tercero: cambiarlo obliga a reeditar lo entregado a Mallén y a repetir los permisos del usuario `mallen_etl`. La tabla de hallazgos va en `Audit`.
- **La validación NUNCA lanza excepción por datos malos** (§7.1 del contrato: *las inconsistencias se registran sin detener el lote completo*). Una fila mala se anota y se sigue con la siguiente.
- **La comparación de dominios es exacta y sensible a mayúsculas.** `"v"` en vez de `"V"` es un hallazgo, no una equivalencia: normalizarlo en silencio ocultaría que el origen de Mallén envía inconsistente.
- **Dos severidades con consecuencias distintas:** `error` (dominio inválido o conteo descuadrado) → el lote queda `RECHAZADO`. `aviso` (referencia aún no recibida) → el lote puede quedar `VALIDADO`. Un lote sin ningún `error` pasa a `VALIDADO`.
- **No se re-valida un lote `INTEGRADO`** — sus datos ya viven en los esquemas internos; re-marcarlo daría una foto falsa. Se levanta un error que el router traduce a 409.
- **Validar es re-ejecutable**: delete-then-insert de los hallazgos de ese lote.
- **No se valida duplicidad de `origen_id`**: los índices `ux_*_origen` del contrato ya lo garantizan a nivel de base. Documentarlo para que nadie lo agregue después creyendo que faltaba.
- Estados válidos de `controlcarga.estado`: `RECIBIDO`, `VALIDADO`, `INTEGRADO`, `RECHAZADO`.
- Roles del router: **ADMIN y GERENTE_PRODUCTIVIDAD** (operación de TI). Gate por `require_roles`, NO por la matriz RBAC (un recurso sin migrar denegaría a todos).
- Estilo backend: `Mapped[tipo]` + `mapped_column()`, servicios reciben `db: Session` y no tocan HTTP, español en docstrings. Estilo frontend: MUI `sx`, React Query, español en el copy, `.then(r => r.data)`.
- Referencias de patrón: `backend/app/services/formacion_ranking_service.py` (servicio + delete-then-insert), `backend/app/api/v1/routers/ia_conexiones.py` (router de sistema por rol), `frontend/src/pages/sistema/ConexionesIA.tsx` (página de TI con tabla + acciones).

---

### Task 1: Modelo `Audit.IntegracionHallazgo` + migración

**Files:**
- Create: `backend/app/models/integracion_hallazgo.py`
- Modify: `backend/app/models/__init__.py`
- Create: `backend/alembic/versions/0032_integracion_hallazgo.py`

**Interfaces:**
- Produce (para Tasks 2-4): la clase `IntegracionHallazgo` con los campos `id`, `lote_id`, `tabla`, `origen_id`, `campo`, `problema`, `severidad`, `detectado_en`.

- [ ] **Step 1: Crear el modelo**

Crear `backend/app/models/integracion_hallazgo.py`:

```python
"""Traza de validación de los lotes que envía Laboratorio Mallén.

POR QUÉ ESTA TABLA VIVE EN `Audit` Y NO EN `ext`
------------------------------------------------
`ext` es el contrato con un tercero: el SQL ya se le entregó a Mallén y su
usuario `mallen_etl` tiene permisos concedidos tabla por tabla. Agregarle una
tabla obligaría a reeditar lo entregado y a repetir la concesión de permisos,
para guardar un dato que además es NUESTRO (el resultado de nuestra validación,
no algo que ellos envíen). `Audit` es exactamente su sitio: la traza de qué vino
mal y cuándo.

`controlcarga.mensaje` es String(500) y solo lleva el resumen; el detalle fila a
fila vive aquí.
"""
from datetime import datetime, timezone

from sqlalchemy import BigInteger, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

#: Un dominio inválido o un conteo descuadrado RECHAZA el lote; una referencia
#: que todavía no llegó solo avisa (es normal que un hecho venga en un lote y su
#: dimensión en otro).
SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"


class IntegracionHallazgo(Base):
    """Una inconsistencia detectada al validar un lote de Mallén."""
    __tablename__ = "IntegracionHallazgo"
    __table_args__ = (
        Index("IX_IntegHallazgo_lote", "lote_id"),
        {"schema": "Audit"},
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    lote_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("ext.controlcarga.lote_id"), nullable=False)
    tabla: Mapped[str] = mapped_column(String(40), nullable=False)
    # Nulos a propósito: los hallazgos de lote (conteo descuadrado, lote vacío)
    # no pertenecen a ninguna fila ni a ningún campo.
    origen_id: Mapped[str | None] = mapped_column(String(60), nullable=True)
    campo: Mapped[str | None] = mapped_column(String(40), nullable=True)
    problema: Mapped[str] = mapped_column(String(300), nullable=False)
    severidad: Mapped[str] = mapped_column(String(10), nullable=False)
    detectado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 2: Registrar el modelo en el paquete**

En `backend/app/models/__init__.py`, añadir `integracion_hallazgo` a la lista de módulos importados, siguiendo exactamente el estilo de las entradas vecinas (el archivo importa los módulos para que `Base.metadata` los conozca). Inspecciona el archivo y añade la entrada en el mismo formato que `integracion_ext`.

- [ ] **Step 3: Crear la migración**

Crear `backend/alembic/versions/0032_integracion_hallazgo.py`:

```python
"""Audit.IntegracionHallazgo — traza de validacion de lotes de Mallen.

El detalle fila a fila de la validacion no cabe en controlcarga.mensaje
(String(500)) y no debe vivir en `ext`, que es contrato con un tercero.

Revision ID: 0032_integracion_hallazgo
Revises: 0031_formacion_ampliada
Create Date: 2026-08-06
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0032_integracion_hallazgo"
down_revision: Union[str, Sequence[str], None] = "0031_formacion_ampliada"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "IntegracionHallazgo",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("lote_id", sa.BigInteger(), nullable=False),
        sa.Column("tabla", sa.String(length=40), nullable=False),
        sa.Column("origen_id", sa.String(length=60), nullable=True),
        sa.Column("campo", sa.String(length=40), nullable=True),
        sa.Column("problema", sa.String(length=300), nullable=False),
        sa.Column("severidad", sa.String(length=10), nullable=False),
        sa.Column("detectado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["lote_id"], ["ext.controlcarga.lote_id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="Audit",
    )
    op.create_index("IX_IntegHallazgo_lote", "IntegracionHallazgo", ["lote_id"],
                    unique=False, schema="Audit")


def downgrade() -> None:
    op.drop_index("IX_IntegHallazgo_lote", table_name="IntegracionHallazgo",
                  schema="Audit")
    op.drop_table("IntegracionHallazgo", schema="Audit")
```

- [ ] **Step 4: Verificar que la migración aplica y que no rompe nada**

Run: `cd backend && python -m alembic upgrade head`
Expected: aplica `0032_integracion_hallazgo` sin error.

Run: `cd backend && python -m alembic check`
Expected: no detecta diferencias pendientes entre modelos y base (si reporta cambios ajenos a esta tabla, NO los incluyas: son ruido preexistente, mismo criterio que documentan las migraciones 0021, 0030 y 0031).

Run: `cd backend && python -m pytest tests/test_integracion_ext.py -v`
Expected: los tests del contrato `ext` siguen pasando (confirma que no se tocó el contrato).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/integracion_hallazgo.py backend/app/models/__init__.py backend/alembic/versions/0032_integracion_hallazgo.py
git commit -m "feat(integracion) Audit.IntegracionHallazgo: traza de validacion de lotes"
```

---

### Task 2: Servicio de validación — dominios y coherencia del lote

**Files:**
- Create: `backend/app/services/integracion_validacion_service.py`
- Test: `backend/tests/test_integracion_validacion.py`

**Interfaces:**
- Consumes: `IntegracionHallazgo`, `SEVERIDAD_ERROR`, `SEVERIDAD_AVISO` de Task 1.
- Produce (para Tasks 3-4):
  - `DOMINIOS: dict[tuple[str, str], set[str]]` — mapa `(tabla, campo) → valores válidos`.
  - `ESTADOS_LOTE: set[str]`
  - `validar_lote(db: Session, lote_id: int) -> dict` → `{"lote_id", "estado", "filas_declaradas", "filas_reales", "errores", "avisos", "mensaje"}`. Lanza `ValueError` si el lote no existe y `LoteYaIntegrado` si está `INTEGRADO`.
  - `class LoteYaIntegrado(RuntimeError)`

- [ ] **Step 1: Escribir el archivo de tests con el escenario base**

Crear `backend/tests/test_integracion_validacion.py`:

```python
"""Validación de los lotes que envía Mallén (esquema `ext`).

Necesita PostgreSQL real: la validación recorre siete tablas con claves
compuestas y foráneas entre esquemas; probarlo con dobles verificaría los dobles.
Si no hay base alcanzable se salta, como el resto de pruebas de integración.
"""
from datetime import date, datetime

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

from app.core.config import settings
from app.db.database import Base
from app.models import (  # noqa: F401
    cat_models, coaching_more_models, dimensiones, exam_models, formacion,
    hechos, ia_conexion, integracion_ext, integracion_hallazgo,
    seguridad_rbac, usuario, visita,
)
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimMedico, ExtDimPais, ExtDimRepresentante,
    ExtFactVisitaMedico, ExtPanelMedico,
)
from app.models.integracion_hallazgo import IntegracionHallazgo
from app.services import integracion_validacion_service as validacion

BD_PRUEBA = "vista_test_integracion"


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
    # Hijos antes que padres: los hallazgos apuntan al lote y los hechos también.
    for tabla in ('"Audit"."IntegracionHallazgo"', "ext.factvisitamedico",
                  "ext.panelmedico", "ext.controlcarga", "ext.dimmedico",
                  "ext.dimrepresentante", "ext.dimciclo", "ext.dimpais"):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


def _lote(db, lote_id: int = 1001, filas: int = 2, estado: str = "RECIBIDO"):
    db.add(ExtControlCarga(
        lote_id=lote_id, sistema_origen="SFA", modulo="VISITAS", pais_codigo="DO",
        ciclo_codigo="C01-2026", periodo="2026-01",
        fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0),
        filas_enviadas=filas, estado=estado))
    db.flush()


@pytest.fixture
def escenario(db):
    """Un lote limpio: dimensiones completas, un panel y una visita válidos."""
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana"))
    db.flush()
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, fecha_inicio=date(2026, 1, 1),
                       fecha_fin=date(2026, 1, 31)))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               nombre="Representante Uno", activo=True))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", activo=True))
    db.flush()
    _lote(db)
    db.add(ExtPanelMedico(
        lote_id=1001, pais_codigo="DO", ciclo_codigo="C01-2026", rm_codigo="VM01",
        medico_codigo="MD01", frecuencia_objetivo="F1", prioridad="TOP",
        categoria="A", visitas_programadas=2, activo=True))
    db.add(ExtFactVisitaMedico(
        lote_id=1001, origen_id="V-0001", pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo="VM01", medico_codigo="MD01",
        fecha_visita=date(2026, 1, 15), tipo_visita="V", ejecutada=True,
        acompanado=False))
    db.commit()
    return {"db": db, "lote_id": 1001}
```

Nota: si algún campo obligatorio de `ExtDimCiclo`, `ExtDimRepresentante` o `ExtDimMedico` no coincide con el modelo real, **ajústalo leyendo `backend/app/models/integracion_ext.py`** — el fixture debe reflejar el modelo, no al revés.

- [ ] **Step 2: Añadir los tests de dominios y coherencia**

```python
def test_lote_limpio_queda_validado(escenario):
    r = validacion.validar_lote(escenario["db"], escenario["lote_id"])

    assert r["estado"] == "VALIDADO"
    assert r["errores"] == 0
    assert r["filas_declaradas"] == r["filas_reales"] == 2


def test_tipo_visita_invalido_rechaza_el_lote(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["errores"] == 1
    h = db.query(IntegracionHallazgo).one()
    assert h.tabla == "factvisitamedico"
    assert h.campo == "tipo_visita"
    assert h.origen_id == "V-0001"
    assert h.severidad == "error"


def test_minuscula_no_se_acepta_en_silencio(escenario):
    """La comparación es sensible a mayúsculas: normalizar ocultaría que el
    origen de Mallén envía inconsistente."""
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "v"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["errores"] == 1


def test_panel_con_frecuencia_y_prioridad_invalidas(escenario):
    db = escenario["db"]
    panel = db.query(ExtPanelMedico).one()
    panel.frecuencia_objetivo = "F3"
    panel.prioridad = "ALTA"
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["errores"] == 2
    campos = {h.campo for h in db.query(IntegracionHallazgo).all()}
    assert campos == {"frecuencia_objetivo", "prioridad"}


def test_conteo_descuadrado_es_error_de_lote(escenario):
    """Síntoma clásico de una carga cortada a la mitad. El hallazgo no pertenece
    a ninguna fila, así que va sin origen_id ni campo."""
    db = escenario["db"]
    db.get(ExtControlCarga, escenario["lote_id"]).filas_enviadas = 99
    db.commit()

    r = validacion.validar_lote(db, escenario["lote_id"])

    assert r["estado"] == "RECHAZADO"
    assert r["filas_declaradas"] == 99
    assert r["filas_reales"] == 2
    h = db.query(IntegracionHallazgo).one()
    assert h.origen_id is None and h.campo is None
    assert h.severidad == "error"


def test_revalidar_no_duplica_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()

    validacion.validar_lote(db, escenario["lote_id"])
    validacion.validar_lote(db, escenario["lote_id"])

    assert db.query(IntegracionHallazgo).count() == 1


def test_no_se_revalida_un_lote_integrado(escenario):
    db = escenario["db"]
    db.get(ExtControlCarga, escenario["lote_id"]).estado = "INTEGRADO"
    db.commit()

    with pytest.raises(validacion.LoteYaIntegrado):
        validacion.validar_lote(db, escenario["lote_id"])


def test_lote_inexistente(escenario):
    with pytest.raises(ValueError, match="no encontrado"):
        validacion.validar_lote(escenario["db"], 999999)
```

- [ ] **Step 3: Correr los tests para verificar que fallan**

Run: `cd backend && python -m pytest tests/test_integracion_validacion.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.integracion_validacion_service'`.
(Si no hay PostgreSQL alcanzable se SALTAN — anótalo en el reporte y continúa.)

- [ ] **Step 4: Crear el servicio**

Crear `backend/app/services/integracion_validacion_service.py`:

```python
"""Validación de los lotes que Laboratorio Mallén deja en el esquema `ext`.

LA REGLA QUE MANDA ESTE DISEÑO (§7.1 del Requerimiento de Datos)
-----------------------------------------------------------------
«Las inconsistencias se registran sin detener el lote completo.» Por eso el
contrato deliberadamente NO lleva CHECK en los campos acotados: un CHECK
rechazaría el INSERT de Mallén y abortaría su envío entero por una fila mala.
Al validar aquí, VISTA acepta el lote y devuelve un informe de qué corregir.

Consecuencia directa: ninguna función de este módulo levanta excepción por datos
malos. Anota el hallazgo y sigue con la fila siguiente. Las únicas excepciones
son de operación (lote inexistente, lote ya integrado), no de contenido.

LO QUE NO SE VALIDA AQUÍ
------------------------
- Duplicidad de `origen_id`: los índices `ux_*_origen` del contrato ya la
  impiden a nivel de base. Re-verificarla sería trabajo muerto.
- Que los códigos existan en los catálogos internos de VISTA (`Config.DIM_*`):
  eso pertenece a la sincronización de dimensiones, no al contrato.
"""
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy.orm import Session

from app.models.integracion_ext import (
    ExtControlCarga, ExtFactEvaluacionConocimiento, ExtFactPrescripcionDetalle,
    ExtFactVenta, ExtFactVisitaFarmacia, ExtFactVisitaMedico, ExtPanelMedico,
    ExtTargetFarmacia,
)
from app.models.integracion_hallazgo import (
    SEVERIDAD_AVISO, SEVERIDAD_ERROR, IntegracionHallazgo,
)

ESTADOS_LOTE = {"RECIBIDO", "VALIDADO", "INTEGRADO", "RECHAZADO"}

#: Las 7 tablas de datos del contrato (las 8 «de hechos» menos `controlcarga`,
#: que es la cabecera). El orden es el del documento.
TABLAS_DATOS: list[tuple[str, type]] = [
    ("panelmedico", ExtPanelMedico),
    ("factvisitamedico", ExtFactVisitaMedico),
    ("targetfarmacia", ExtTargetFarmacia),
    ("factvisitafarmacia", ExtFactVisitaFarmacia),
    ("factventa", ExtFactVenta),
    ("factevaluacionconocimiento", ExtFactEvaluacionConocimiento),
    ("factprescripciondetalle", ExtFactPrescripcionDetalle),
]

#: Los campos que el contrato señala como «los que rompen indicadores en
#: silencio» (§11.6). La comparación es EXACTA: 'v' no es 'V'.
DOMINIOS: dict[tuple[str, str], set[str]] = {
    ("factvisitamedico", "tipo_visita"): {"V", "R"},
    ("panelmedico", "frecuencia_objetivo"): {"F1", "F2"},
    ("panelmedico", "prioridad"): {"TOP", "REGULAR"},
    ("panelmedico", "categoria"): {"A", "B", "C", "D"},
}


class LoteYaIntegrado(RuntimeError):
    """El lote ya se integró a los esquemas internos: re-validarlo daría una
    foto falsa de un dato que ya está en producción."""


def _hallazgo(lote_id: int, tabla: str, problema: str, severidad: str,
              origen_id: str | None = None,
              campo: str | None = None) -> IntegracionHallazgo:
    return IntegracionHallazgo(
        lote_id=lote_id, tabla=tabla, origen_id=origen_id, campo=campo,
        problema=problema, severidad=severidad,
        detectado_en=datetime.now(timezone.utc))


def _validar_dominios(filas: list, tabla: str, lote_id: int) -> list[IntegracionHallazgo]:
    """Revisa los campos acotados de una tabla. Un valor fuera de dominio es un
    hallazgo, nunca una excepción."""
    hallazgos = []
    for campo_tabla, validos in DOMINIOS.items():
        if campo_tabla[0] != tabla:
            continue
        campo = campo_tabla[1]
        for fila in filas:
            valor = getattr(fila, campo, None)
            # Un opcional ausente no es un problema de dominio; su obligatoriedad
            # ya la impone el NOT NULL del contrato.
            if valor is None:
                continue
            if valor not in validos:
                hallazgos.append(_hallazgo(
                    lote_id, tabla,
                    f"«{valor}» no es un valor válido de {campo}. "
                    f"Se esperaba uno de: {', '.join(sorted(validos))}.",
                    SEVERIDAD_ERROR,
                    origen_id=getattr(fila, "origen_id", None), campo=campo))
    return hallazgos


def _contar_filas(db: Session, lote_id: int) -> tuple[int, dict[str, list]]:
    """Trae las filas del lote de las 7 tablas. Se cargan en memoria porque hay
    que recorrerlas campo a campo de todas formas."""
    por_tabla: dict[str, list] = {}
    total = 0
    for tabla, modelo in TABLAS_DATOS:
        filas = db.query(modelo).filter(modelo.lote_id == lote_id).all()
        por_tabla[tabla] = filas
        total += len(filas)
    return total, por_tabla


def validar_lote(db: Session, lote_id: int) -> dict:
    """Valida (o re-valida) un lote y lo deja en VALIDADO o RECHAZADO.

    Re-ejecutable: borra los hallazgos previos del lote y los recalcula. Es lo
    que hace seguro el flujo real de corrección, en el que Mallén reenvía el
    registro con el mismo `origen_id` (nunca borra: no tiene ese permiso).
    """
    lote = db.get(ExtControlCarga, lote_id)
    if lote is None:
        raise ValueError(f"Lote {lote_id} no encontrado")
    if lote.estado == "INTEGRADO":
        raise LoteYaIntegrado(
            f"El lote {lote_id} ya fue integrado; no se re-valida.")

    (db.query(IntegracionHallazgo)
     .filter(IntegracionHallazgo.lote_id == lote_id)
     .delete(synchronize_session=False))

    filas_reales, por_tabla = _contar_filas(db, lote_id)
    hallazgos: list[IntegracionHallazgo] = []
    for tabla, filas in por_tabla.items():
        hallazgos.extend(_validar_dominios(filas, tabla, lote_id))

    if lote.filas_enviadas != filas_reales:
        hallazgos.append(_hallazgo(
            lote_id, "controlcarga",
            f"El lote declara {lote.filas_enviadas} fila(s) y se recibieron "
            f"{filas_reales}. Suele indicar una carga interrumpida.",
            SEVERIDAD_ERROR))
    elif filas_reales == 0:
        hallazgos.append(_hallazgo(
            lote_id, "controlcarga",
            "El lote no trae ninguna fila de datos.", SEVERIDAD_AVISO))

    for h in hallazgos:
        db.add(h)

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    avisos = len(hallazgos) - errores
    tablas_con_error = len({h.tabla for h in hallazgos
                            if h.severidad == SEVERIDAD_ERROR})
    lote.estado = "RECHAZADO" if errores else "VALIDADO"
    mensaje = (f"{filas_reales} fila(s), {errores} error(es) en "
               f"{tablas_con_error} tabla(s), {avisos} aviso(s)")
    lote.mensaje = mensaje[:500]
    db.commit()

    logger.info(f"Lote {lote_id} validado: {lote.estado} — {mensaje}")
    return {"lote_id": lote_id, "estado": lote.estado,
            "filas_declaradas": lote.filas_enviadas, "filas_reales": filas_reales,
            "errores": errores, "avisos": avisos, "mensaje": mensaje}
```

- [ ] **Step 5: Correr los tests para verificar que pasan**

Run: `cd backend && python -m pytest tests/test_integracion_validacion.py -v`
Expected: 8 passed (o SKIPPED si no hay PostgreSQL).

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/integracion_validacion_service.py backend/tests/test_integracion_validacion.py
git commit -m "feat(integracion) validacion de lotes: dominios acotados y coherencia del conteo"
```

---

### Task 3: Servicio — lectura de lotes y hallazgos

**Files:**
- Modify: `backend/app/services/integracion_validacion_service.py`
- Test: `backend/tests/test_integracion_validacion.py`

**Interfaces:**
- Consumes: `validar_lote` de Task 2.
- Produce (para Task 4):
  - `listar_lotes(db, pais_codigo=None, estado=None, limite=100) -> list[dict]`
  - `detalle_lote(db, lote_id) -> dict` (lanza `ValueError` si no existe)
  - `resumen(db, pais_codigo=None) -> dict[str, int]`

- [ ] **Step 1: Añadir los tests de lectura al final del archivo de tests**

```python
def test_listar_lotes_incluye_conteo_de_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtFactVisitaMedico).filter(
        ExtFactVisitaMedico.origen_id == "V-0001").one().tipo_visita = "X"
    db.commit()
    validacion.validar_lote(db, escenario["lote_id"])

    filas = validacion.listar_lotes(db)

    assert len(filas) == 1
    assert filas[0]["lote_id"] == 1001
    assert filas[0]["estado"] == "RECHAZADO"
    assert filas[0]["hallazgos"] == 1


def test_listar_lotes_filtra_por_estado(escenario):
    validacion.validar_lote(escenario["db"], escenario["lote_id"])

    assert len(validacion.listar_lotes(escenario["db"], estado="VALIDADO")) == 1
    assert validacion.listar_lotes(escenario["db"], estado="RECHAZADO") == []


def test_detalle_lote_trae_sus_hallazgos(escenario):
    db = escenario["db"]
    db.query(ExtPanelMedico).one().prioridad = "ALTA"
    db.commit()
    validacion.validar_lote(db, escenario["lote_id"])

    d = validacion.detalle_lote(db, escenario["lote_id"])

    assert d["lote"]["estado"] == "RECHAZADO"
    assert len(d["hallazgos"]) == 1
    assert d["hallazgos"][0]["campo"] == "prioridad"


def test_resumen_cuenta_por_estado(escenario):
    validacion.validar_lote(escenario["db"], escenario["lote_id"])

    r = validacion.resumen(escenario["db"])

    assert r["VALIDADO"] == 1
    assert r["RECIBIDO"] == 0
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && python -m pytest tests/test_integracion_validacion.py -k "listar or detalle or resumen" -v`
Expected: FAIL con `AttributeError: module 'app.services.integracion_validacion_service' has no attribute 'listar_lotes'`.

- [ ] **Step 3: Añadir las funciones de lectura al servicio**

Añadir al final de `backend/app/services/integracion_validacion_service.py`:

```python
def _lote_publico(lote: ExtControlCarga) -> dict:
    return {
        "lote_id": lote.lote_id, "sistema_origen": lote.sistema_origen,
        "modulo": lote.modulo, "pais_codigo": lote.pais_codigo,
        "ciclo_codigo": lote.ciclo_codigo, "periodo": lote.periodo,
        "fecha_extraccion": lote.fecha_extraccion,
        "fecha_recepcion": lote.fecha_recepcion,
        "filas_enviadas": lote.filas_enviadas, "estado": lote.estado,
        "mensaje": lote.mensaje,
    }


def listar_lotes(db: Session, pais_codigo: str | None = None,
                 estado: str | None = None, limite: int = 100) -> list[dict]:
    """Lotes más recientes primero, con su conteo de hallazgos."""
    q = db.query(ExtControlCarga)
    if pais_codigo:
        q = q.filter(ExtControlCarga.pais_codigo == pais_codigo)
    if estado:
        q = q.filter(ExtControlCarga.estado == estado)
    lotes = q.order_by(ExtControlCarga.fecha_recepcion.desc()).limit(limite).all()

    salida = []
    for lote in lotes:
        n = (db.query(IntegracionHallazgo)
             .filter(IntegracionHallazgo.lote_id == lote.lote_id).count())
        salida.append(_lote_publico(lote) | {"hallazgos": n})
    return salida


def detalle_lote(db: Session, lote_id: int) -> dict:
    """Cabecera del lote y sus hallazgos, los errores primero."""
    lote = db.get(ExtControlCarga, lote_id)
    if lote is None:
        raise ValueError(f"Lote {lote_id} no encontrado")
    # severidad DESC porque alfabéticamente 'error' > 'aviso': así los errores
    # (lo que rechaza el lote) salen primero, que es lo que hay que corregir.
    filas = (db.query(IntegracionHallazgo)
             .filter(IntegracionHallazgo.lote_id == lote_id)
             .order_by(IntegracionHallazgo.severidad.desc(),
                       IntegracionHallazgo.tabla.asc(),
                       IntegracionHallazgo.id.asc())
             .all())
    return {
        "lote": _lote_publico(lote),
        "hallazgos": [{
            "id": h.id, "tabla": h.tabla, "origen_id": h.origen_id,
            "campo": h.campo, "problema": h.problema, "severidad": h.severidad,
            "detectado_en": h.detectado_en,
        } for h in filas],
    }


def resumen(db: Session, pais_codigo: str | None = None) -> dict[str, int]:
    """Conteo de lotes por estado. Devuelve SIEMPRE los cuatro estados, aunque
    valgan cero: el tablero necesita las cuatro tarjetas siempre."""
    q = db.query(ExtControlCarga)
    if pais_codigo:
        q = q.filter(ExtControlCarga.pais_codigo == pais_codigo)
    conteo = {e: 0 for e in sorted(ESTADOS_LOTE)}
    for lote in q.all():
        if lote.estado in conteo:
            conteo[lote.estado] += 1
    return conteo
```


- [ ] **Step 4: Correr toda la suite del archivo**

Run: `cd backend && python -m pytest tests/test_integracion_validacion.py -v`
Expected: 12 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_validacion_service.py backend/tests/test_integracion_validacion.py
git commit -m "feat(integracion) lectura de lotes: listado, detalle con hallazgos y resumen"
```

---

### Task 4: Router `/integracion`

**Files:**
- Create: `backend/app/api/v1/routers/integracion.py`
- Modify: `backend/app/api/v1/router.py`

**Interfaces:**
- Consumes: `validar_lote`, `listar_lotes`, `detalle_lote`, `resumen`, `LoteYaIntegrado` del servicio (Tasks 2-3).
- Produce (para Tasks 5-6): los 4 endpoints de §6 del spec.

- [ ] **Step 1: Crear el router**

Crear `backend/app/api/v1/routers/integracion.py`:

```python
"""Integración con Laboratorio Mallén — recepción y validación de lotes.

Operación de TI, no de negocio: se gatea por rol (ADMIN, GERENTE_PRODUCTIVIDAD)
igual que `/admin` y `/ia/conexiones`, y no por la matriz RBAC, que exigiría una
migración para dar de alta el recurso —y sin ella quedaría denegado para todos.

Este router NO integra datos a los esquemas internos de VISTA: solo valida lo que
Mallén dejó en `ext` y reporta qué corregir.
"""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import integracion_validacion_service as validacion

router = APIRouter(prefix="/integracion", tags=["Integración — Mallén"])

RequireTI = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))


@router.get("/lotes", summary="Lotes recibidos de Mallén")
def listar(pais_codigo: str | None = None, estado: str | None = None,
           limite: int = 100, db: Session = Depends(get_db),
           _: Usuario = RequireTI):
    return validacion.listar_lotes(db, pais_codigo, estado, limite)


@router.get("/lotes/{lote_id}", summary="Detalle del lote y sus hallazgos")
def detalle(lote_id: int, db: Session = Depends(get_db), _: Usuario = RequireTI):
    try:
        return validacion.detalle_lote(db, lote_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.post("/lotes/{lote_id}/validar", summary="Validar (o re-validar) un lote")
def validar(lote_id: int, db: Session = Depends(get_db), _: Usuario = RequireTI):
    try:
        return validacion.validar_lote(db, lote_id)
    except validacion.LoteYaIntegrado as exc:
        # 409 y no 422: la petición es válida, lo que pasa es que el lote ya
        # está en un estado que no admite esta operación.
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc


@router.get("/resumen", summary="Conteo de lotes por estado")
def ver_resumen(pais_codigo: str | None = None, db: Session = Depends(get_db),
                _: Usuario = RequireTI):
    return validacion.resumen(db, pais_codigo)
```

- [ ] **Step 2: Registrar el router**

En `backend/app/api/v1/router.py`, junto a los otros imports:
```python
from app.api.v1.routers.integracion import router as integracion_router
```
Y junto a los otros `include_router`:
```python
api_router.include_router(integracion_router)  # Integracion Mallen: recepcion y validacion de lotes
```

- [ ] **Step 3: Verificar que la app carga y la suite sigue verde**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if 'integracion' in r.path])"`
Expected: imprime las 4 rutas bajo `/api/v1/integracion`.

Run: `cd backend && python -m pytest tests/test_integracion_validacion.py tests/test_integracion_ext.py -v`
Expected: todos pasan.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/integracion.py backend/app/api/v1/router.py
git commit -m "feat(integracion) router /integracion con gate de TI"
```

---

### Task 5: Service frontend `integracion.service.ts`

**Files:**
- Create: `frontend/src/services/integracion.service.ts`

**Interfaces:**
- Produce (para Task 6): tipos `LoteIntegracion`, `HallazgoIntegracion`, `DetalleLote`, `ResultadoValidacion`, `ResumenLotes`; funciones `listarLotes`, `detalleLote`, `validarLote`, `resumenLotes`.

- [ ] **Step 1: Crear el archivo completo**

```ts
/**
 * integracion.service.ts — Integración con Laboratorio Mallén.
 * Rutas exactas del router backend `/integracion` (solo ADMIN y GERENTE_PRODUCTIVIDAD).
 *
 * Este sub-proyecto solo valida lo que Mallén dejó en el esquema `ext`; no
 * integra nada a los esquemas internos de VISTA.
 */
import { api } from './api';

export type EstadoLote = 'RECIBIDO' | 'VALIDADO' | 'INTEGRADO' | 'RECHAZADO';
export type SeveridadHallazgo = 'error' | 'aviso';

export interface LoteIntegracion {
  lote_id: number; sistema_origen: string; modulo: string;
  pais_codigo: string; ciclo_codigo: string | null; periodo: string | null;
  fecha_extraccion: string; fecha_recepcion: string;
  filas_enviadas: number; estado: EstadoLote; mensaje: string | null;
  hallazgos: number;
}

export interface HallazgoIntegracion {
  id: number; tabla: string; origen_id: string | null; campo: string | null;
  problema: string; severidad: SeveridadHallazgo; detectado_en: string;
}

export interface DetalleLote {
  lote: Omit<LoteIntegracion, 'hallazgos'>;
  hallazgos: HallazgoIntegracion[];
}

export interface ResultadoValidacion {
  lote_id: number; estado: EstadoLote;
  filas_declaradas: number; filas_reales: number;
  errores: number; avisos: number; mensaje: string;
}

export type ResumenLotes = Record<EstadoLote, number>;

export const listarLotes = (params: {
  pais_codigo?: string; estado?: EstadoLote; limite?: number;
} = {}) => api.get<LoteIntegracion[]>('/integracion/lotes', { params })
  .then((r) => r.data);

export const detalleLote = (loteId: number) =>
  api.get<DetalleLote>(`/integracion/lotes/${loteId}`).then((r) => r.data);

export const validarLote = (loteId: number) =>
  api.post<ResultadoValidacion>(`/integracion/lotes/${loteId}/validar`)
    .then((r) => r.data);

export const resumenLotes = (paisCodigo?: string) =>
  api.get<ResumenLotes>('/integracion/resumen',
    { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then((r) => r.data);
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/integracion.service.ts
git commit -m "feat(integracion) capa de servicio frontend"
```

---

### Task 6: Página `LotesIntegracion.tsx` + ruta + sidebar

**Files:**
- Create: `frontend/src/pages/integracion/LotesIntegracion.tsx`
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: todo el service de Task 5; `useCicloStore` (`paisCodigo`).

- [ ] **Step 1: Crear la página**

```tsx
/**
 * LotesIntegracion.tsx — Lotes que Mallén deja en el esquema `ext`.
 * Pantalla de TI: ver qué llegó, validarlo y obtener el informe de qué corregir
 * para mandárselo al integrador.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Card, CardContent, Grid, CircularProgress, Snackbar,
  Dialog, DialogTitle, DialogContent, DialogActions, Tooltip,
} from '@mui/material';
import { FactCheck, Visibility } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  listarLotes, detalleLote, validarLote, resumenLotes,
  type EstadoLote, type LoteIntegracion,
} from '../../services/integracion.service';

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

const COLOR_ESTADO: Record<EstadoLote, 'default' | 'primary' | 'success' | 'error'> = {
  RECIBIDO: 'default', VALIDADO: 'primary', INTEGRADO: 'success', RECHAZADO: 'error',
};
const ESTADOS: EstadoLote[] = ['RECIBIDO', 'VALIDADO', 'INTEGRADO', 'RECHAZADO'];

export default function LotesIntegracion() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const [verLote, setVerLote] = useState<number | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const lotes = useQuery({
    queryKey: ['integracion-lotes', paisCodigo],
    queryFn: () => listarLotes(paisCodigo ? { pais_codigo: paisCodigo } : {}),
  });
  const resumen = useQuery({
    queryKey: ['integracion-resumen', paisCodigo],
    queryFn: () => resumenLotes(paisCodigo || undefined),
  });

  const validar = useMutation({
    mutationFn: (loteId: number) => validarLote(loteId),
    onSuccess: (r) => setAviso({
      sev: r.errores > 0 ? 'warning' : 'success',
      msg: `Lote ${r.lote_id}: ${r.estado}. ${r.mensaje}`,
    }),
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo validar el lote.') }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['integracion-lotes'] });
      qc.invalidateQueries({ queryKey: ['integracion-resumen'] });
    },
  });

  const filas = lotes.data || [];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Lotes de Mallén</Typography>

      <Grid container spacing={2} mb={3}>
        {ESTADOS.map((e) => (
          <Grid item xs={6} md={3} key={e}>
            <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <CardContent>
                <Typography variant="caption" color="text.secondary">{e}</Typography>
                <Typography variant="h5" fontWeight={800}>{resumen.data?.[e] ?? 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {lotes.isLoading ? <CircularProgress /> : lotes.isError ? (
        <Alert severity="warning">No se pudieron cargar los lotes.</Alert>
      ) : filas.length === 0 ? (
        <Alert severity="info">Aún no se ha recibido ningún lote de Mallén.</Alert>
      ) : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Lote</TableCell><TableCell>Origen</TableCell>
                <TableCell>Módulo</TableCell><TableCell>País</TableCell>
                <TableCell>Ciclo / Período</TableCell><TableCell>Recibido</TableCell>
                <TableCell align="right">Filas</TableCell>
                <TableCell>Estado</TableCell>
                <TableCell align="right">Hallazgos</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filas.map((l: LoteIntegracion) => (
                <TableRow key={l.lote_id}>
                  <TableCell>{l.lote_id}</TableCell>
                  <TableCell>{l.sistema_origen}</TableCell>
                  <TableCell>{l.modulo}</TableCell>
                  <TableCell>{l.pais_codigo}</TableCell>
                  <TableCell>{l.ciclo_codigo || l.periodo || '—'}</TableCell>
                  <TableCell>{new Date(l.fecha_recepcion).toLocaleString()}</TableCell>
                  <TableCell align="right">{l.filas_enviadas}</TableCell>
                  <TableCell><Chip size="small" color={COLOR_ESTADO[l.estado]} label={l.estado} /></TableCell>
                  <TableCell align="right">{l.hallazgos || '—'}</TableCell>
                  <TableCell align="right">
                    <Tooltip title={l.estado === 'INTEGRADO'
                      ? 'Un lote ya integrado no se re-valida: sus datos ya están en VISTA'
                      : 'Validar el lote'}>
                      <span>
                        <Button size="small" startIcon={<FactCheck />}
                          disabled={l.estado === 'INTEGRADO' ||
                            (validar.isPending && validar.variables === l.lote_id)}
                          onClick={() => validar.mutate(l.lote_id)}>Validar</Button>
                      </span>
                    </Tooltip>
                    <Button size="small" startIcon={<Visibility />}
                      onClick={() => setVerLote(l.lote_id)}>Hallazgos</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <DialogoHallazgos loteId={verLote} onClose={() => setVerLote(null)} />

      <Snackbar open={!!aviso} autoHideDuration={8000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoHallazgos({ loteId, onClose }: { loteId: number | null; onClose: () => void }) {
  const datos = useQuery({
    queryKey: ['integracion-detalle', loteId],
    queryFn: () => detalleLote(loteId as number),
    enabled: loteId != null,
  });

  return (
    <Dialog open={loteId != null} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Hallazgos del lote {loteId}</DialogTitle>
      <DialogContent>
        {datos.isLoading ? <CircularProgress /> : (datos.data?.hallazgos || []).length === 0 ? (
          <Alert severity="success">Sin hallazgos: el lote está limpio.</Alert>
        ) : (
          <>
            <Alert severity="info" sx={{ mb: 2 }}>
              Este detalle es lo que hay que enviarle al equipo técnico de Mallén para corregir.
            </Alert>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Tabla</TableCell><TableCell>Registro</TableCell>
                  <TableCell>Campo</TableCell><TableCell>Problema</TableCell>
                  <TableCell>Severidad</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(datos.data?.hallazgos || []).map((h) => (
                  <TableRow key={h.id}>
                    <TableCell>{h.tabla}</TableCell>
                    <TableCell>{h.origen_id || '—'}</TableCell>
                    <TableCell>{h.campo || '—'}</TableCell>
                    <TableCell>{h.problema}</TableCell>
                    <TableCell>
                      <Chip size="small" color={h.severidad === 'error' ? 'error' : 'warning'}
                        label={h.severidad} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 2: Registrar la ruta lazy en `App.tsx`**

Junto a los otros `lazyWithReload`:
```tsx
const LotesIntegracion = lazyWithReload(() => import('./pages/integracion/LotesIntegracion'));
```
Y en el árbol de rutas protegidas (usa el patrón de `conexiones-ia` como referencia):
```tsx
<Route path="integracion/lotes" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD']}><LotesIntegracion /></ProtectedRoute>} />
```

- [ ] **Step 3: Agregar el ítem al Sidebar**

En el grupo de sistema (el que contiene 'Conexiones de IA', '/admin' y '/usuarios'):
```tsx
{ label: 'Lotes de Mallén', path: '/integracion/lotes', icon: <CloudSync />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD'] },
```
Verifica que `CloudSync` esté importado desde `@mui/icons-material`; agrégalo al import existente si falta.

- [ ] **Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/integracion/LotesIntegracion.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(integracion) pantalla de lotes con validacion y detalle de hallazgos"
```

---

## Verificación en vivo (tras Task 6, no es un commit)

Como Mallén todavía no envía nada, el smoke exige **sembrar un lote de prueba a mano** en la base local (INSERT directo en `ext.controlcarga` + unas filas de `ext.panelmedico`/`ext.factvisitamedico`, con una fila deliberadamente mala). Con JWT de ADMIN minteado:

1. `/integracion/lotes` muestra el lote sembrado en estado RECIBIDO.
2. «Validar» → el estado pasa a RECHAZADO y el snackbar trae el resumen.
3. «Hallazgos» → la tabla muestra la fila mala con su tabla, `origen_id`, campo y problema.
4. Corregir la fila mala en la base y volver a «Validar» → pasa a VALIDADO y los hallazgos desaparecen (no se acumulan).
5. Poner el lote en INTEGRADO a mano → el botón «Validar» queda deshabilitado con su tooltip.
6. Un rol no-TI (p. ej. REPRESENTANTE_MEDICO) no ve el ítem del sidebar ni puede entrar a la ruta.

---

## Self-Review

- **Cobertura del spec:**
  - §1 contexto y §2 regla de no-abortar → Global Constraints + docstring del servicio (Task 2).
  - §3.1 dominios → `DOMINIOS` + `_validar_dominios` (Task 2) + 3 tests.
  - §3.2 integridad referencial blanda → **no implementada como validación activa**; ver nota de gap abajo.
  - §3.3 coherencia del lote (conteo, lote vacío) → Task 2 + 2 tests. Duplicados de `origen_id`: documentado como garantizado por la base, no re-verificado.
  - §3.4 obligatoriedad de `prioridad` → cubierto por el dominio (el `NOT NULL` ya está en el contrato).
  - §4 tabla de hallazgos en `Audit` + severidades + migración → Task 1.
  - §5 re-validación y guard de `INTEGRADO` → Task 2 + 2 tests.
  - §6 los 4 endpoints y el gate de TI → Task 4.
  - §7 frontend → Tasks 5-6.
  - §8 fuera de alcance → respetado (no se integra nada, no se toca `ext`, sin scheduler, sin correo).
  - §9 verificación → tests de Tasks 2-3 (8 de los 8 casos del spec, salvo el de referencia faltante) + sección en vivo.
- **Gap consciente y su motivo:** el spec (§3.2) pedía reportar como `aviso` las referencias que aún no han llegado. **No se implementa en este plan** porque las FK del contrato ya impiden insertar un hecho cuya dimensión no exista: la fila simplemente no entraría, así que no hay nada que detectar leyendo `ext`. El caso que el spec imaginaba (dimensión en un lote posterior) no puede ocurrir con el esquema tal como está declarado. Se deja `SEVERIDAD_AVISO` en uso para el lote vacío, que sí es un aviso real. **Esto debe confirmarse con el usuario**: si Mallén cargara con las FK deshabilitadas, el caso volvería a ser posible y habría que añadir la comprobación.
- **Placeholder scan:** sin TBD/TODO; código completo en cada paso.
- **Consistencia de tipos:** `validar_lote` devuelve las 7 claves que declara `ResultadoValidacion`; `listar_lotes` devuelve `_lote_publico` + `hallazgos`, que es exactamente `LoteIntegracion`; `detalle_lote` devuelve `{lote, hallazgos}` = `DetalleLote` con `Omit<LoteIntegracion,'hallazgos'>`; `resumen` devuelve los 4 estados = `ResumenLotes`.
