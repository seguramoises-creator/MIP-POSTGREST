# Fuente única de `EVAL_CONOCIMIENTOS` — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Declarar un dueño por país para `EVAL_CONOCIMIENTOS` y hacer que cada camino que lo escribe se niegue si no es el dueño, en vez de pisar en silencio; más la pantalla de captura que sustituye al Excel y el integrador de las notas de Mallén.

**Architecture:** Una tabla de configuración (`Config.FuenteIndicador`) y un servicio que concentra la regla (`fuente_indicador_service`). Tres caminos la consultan antes de escribir: la consolidación de exámenes, el integrador de `ext` y la nueva captura manual, que tiene su propia tabla de staging (`DW.FACT_NotaConocimiento`). El Excel queda fuera del indicador por completo.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, PostgreSQL, pytest contra PostgreSQL real, React 18 + TypeScript + MUI v6 + TanStack Query.

**Diseño:** `docs/superpowers/specs/2026-08-12-conocimientos-fuente-unica-design.md`

## Global Constraints

- **Tres fuentes, y solo tres**: `EXAMEN_VISTA`, `NOTA_EXTERNA`, `CAPTURA_MANUAL`. **`EXCEL` NO es una fuente** — decisión del cliente, "nunca más Excel para este proceso".
- **El dueño es por país**, no por ciclo: la decisión del §10 pendiente 2 es una política que Mallén toma una vez.
- **La regla vive en UN solo sitio**, `fuente_indicador_service`. Repartir la comprobación por los tres caminos es cómo se vuelven a desincronizar.
- **Cada camino se niega nombrando al dueño real**, no falla con un mensaje genérico.
- **Los tres escriben igual**: promedio de las notas del RM en el ciclo → `FACT_ResultadoIndicador`, `resultado_real` **0-100 directo** (`escala = 100`, sin conversión), guard de ciclo cerrado **ANTES** de cualquier borrado, delete-then-insert acotado a `(rm_id, indicador_id, ciclo_id)`.
- **Un RM sin notas NO genera fila.** Ausencia de dato no es un cero.
- **Las tres escrituras rellenan `pais_codigo`, `linea_id` y `gerente_id` desde el RM** — son `NOT NULL` en `FACT_ResultadoIndicador` y no vienen en la nota.
- **`DW.FACT_NotaConocimiento` NO lleva UNIQUE** (un RM puede tener varias notas por ciclo). Por eso **corregir EDITA la fila existente, nunca añade otra**: si corregir insertara, la nota vieja seguiría entrando al promedio.
- **PROHIBIDO tocar** `motor_calculo_service.py`, `recalculo_service.py`, `cobertura_predictiva_service.py`, `cobertura_farmacia_service.py`, `visita_costo_service.py`, ni el esquema `ext` (`app/models/integracion_ext.py`, migración `0030`).
- **El módulo de Exámenes solo recibe su puerta**, ningún otro cambio.
- Intérprete: `backend/venv/Scripts/python.exe`. Tests desde `backend/`. `Decimal` para notas, nunca `float`. `loguru`, nunca `print`. `datetime.now(timezone.utc)`.

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/alembic/versions/0035_fuente_conocimientos.py` (nuevo) | Las dos tablas + la semilla |
| `backend/app/models/dimensiones.py` | +`FuenteIndicador` (es un catálogo de `Config`) |
| `backend/app/models/hechos.py` | +`NotaConocimiento` (es un hecho de `DW`) |
| `backend/app/services/fuente_indicador_service.py` (nuevo) | La regla del dueño, en un solo sitio |
| `backend/app/services/conocimientos_service.py` (nuevo) | Captura, integración al ciclo y el integrador de `ext` |
| `backend/app/services/etl_service.py` | El Excel deja de tocar el indicador + borrado acotado |
| `backend/app/services/examen_consolidacion_service.py` | Su puerta |
| `backend/app/api/v1/routers/conocimientos.py` (nuevo) | Endpoints |
| `frontend/src/pages/conocimientos/Conocimientos.tsx` (nuevo) | Dueño + captura |

`Examenes.tsx` ya tiene 791 líneas: la captura va en página propia, no como pestaña suya.

---

### Task 1: La tabla del dueño y su regla

**Files:**
- Create: `backend/alembic/versions/0035_fuente_conocimientos.py`
- Modify: `backend/app/models/dimensiones.py`, `backend/app/models/hechos.py`
- Create: `backend/app/services/fuente_indicador_service.py`
- Test: `backend/tests/test_fuente_indicador.py`

**Interfaces:**
- Consumes: `Config.DIM_Pais.codigo`, `Config.DIM_RM.id`, `Config.DIM_Ciclo.id`, `Security.DIM_Usuario.id`.
- Produces: constantes `INDICADOR_CONOCIMIENTOS`, `FUENTE_EXAMEN_VISTA`, `FUENTE_NOTA_EXTERNA`, `FUENTE_CAPTURA_MANUAL`, `FUENTES`, `FUENTE_POR_DEFECTO`; `FuenteAjenaError`; `fuente_de(db, pais_codigo, indicador_codigo=INDICADOR_CONOCIMIENTOS) -> str`; `asegurar_duenio(db, pais_codigo, fuente_que_escribe, indicador_codigo=INDICADOR_CONOCIMIENTOS) -> None`; `fijar_fuente(db, pais_codigo, fuente, usuario_id, indicador_codigo=INDICADOR_CONOCIMIENTOS) -> FuenteIndicador`; modelos `FuenteIndicador` y `NotaConocimiento`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_fuente_indicador.py`:

```python
"""El dueño de EVAL_CONOCIMIENTOS, por país.

Tres caminos escriben ese indicador con delete-then-insert, así que sin un dueño
declarado gana el último en correr, sin error y sin rastro. Aquí se prueba la
regla; las puertas que la aplican se prueban en sus propios módulos.

Necesita PostgreSQL real.
"""
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
from app.models.dimensiones import FuenteIndicador, Pais
from app.services import fuente_indicador_service as fs

BD_PRUEBA = "vista_test_fuente"


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
    for tabla in ('"Config"."FuenteIndicador"', '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.commit()
    yield s
    s.close()


def test_pais_sin_fila_responde_el_default(db):
    """El default es CAPTURA_MANUAL, no un error: un país recién creado tiene
    que poder capturar sin que nadie configure nada primero."""
    assert fuente := fs.fuente_de(db, "DO")
    assert fuente == fs.FUENTE_CAPTURA_MANUAL


def test_fijar_fuente_deja_autor_y_fecha(db):
    fila = fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=7)
    db.commit()

    assert fila.fuente == fs.FUENTE_EXAMEN_VISTA
    assert fila.actualizado_por_usuario_id == 7
    assert fila.actualizado_en is not None
    assert fs.fuente_de(db, "DO") == fs.FUENTE_EXAMEN_VISTA


def test_fijar_fuente_dos_veces_actualiza_la_misma_fila(db):
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=7)
    db.commit()
    fs.fijar_fuente(db, "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=8)
    db.commit()

    filas = db.query(FuenteIndicador).filter(
        FuenteIndicador.pais_codigo == "DO").all()
    assert len(filas) == 1
    assert filas[0].fuente == fs.FUENTE_NOTA_EXTERNA


def test_una_fuente_inventada_se_rechaza(db):
    """EXCEL entre ellas: no es que no sea el dueño, es que dejó de ser una vía."""
    for invento in ("EXCEL", "excel", "", "OTRA_COSA"):
        with pytest.raises(ValueError):
            fs.fijar_fuente(db, "DO", invento, usuario_id=1)


def test_asegurar_duenio_pasa_cuando_coincide(db):
    fs.fijar_fuente(db, "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    db.commit()

    fs.asegurar_duenio(db, "DO", fs.FUENTE_NOTA_EXTERNA)   # no levanta


def test_asegurar_duenio_nombra_al_dueno_real(db):
    """El mensaje tiene que decir QUIÉN es el dueño: 'no tienes permiso' deja al
    operador sin saber qué cambiar."""
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    db.commit()

    with pytest.raises(fs.FuenteAjenaError) as exc:
        fs.asegurar_duenio(db, "DO", fs.FUENTE_CAPTURA_MANUAL)

    assert exc.value.duenio == fs.FUENTE_EXAMEN_VISTA
    assert exc.value.intento == fs.FUENTE_CAPTURA_MANUAL
    assert fs.FUENTE_EXAMEN_VISTA in str(exc.value)


def test_el_dueno_es_por_pais(db):
    db.add(Pais(codigo="PR", nombre="Puerto Rico"))
    db.commit()
    fs.fijar_fuente(db, "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    db.commit()

    assert fs.fuente_de(db, "DO") == fs.FUENTE_EXAMEN_VISTA
    assert fs.fuente_de(db, "PR") == fs.FUENTE_CAPTURA_MANUAL
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_fuente_indicador.py -q`
Expected: FAIL — `ImportError: cannot import name 'FuenteIndicador' from 'app.models.dimensiones'`

- [ ] **Step 3: Añadir los dos modelos**

Al final de `backend/app/models/dimensiones.py`:

```python
class FuenteIndicador(Base):
    """Quién alimenta un indicador en un país. Hoy solo se usa para
    EVAL_CONOCIMIENTOS, que tiene tres caminos posibles y hasta ahora se los
    disputaban en silencio: los tres hacen delete-then-insert, así que ganaba
    el último en correr.

    Es por PAÍS y no por ciclo a propósito: la elección entre exámenes de VISTA,
    notas de Mallén y captura manual es una política que se toma una vez, no
    algo que alterne entre ciclos.
    """
    __tablename__ = "FuenteIndicador"
    __table_args__ = (
        UniqueConstraint("pais_codigo", "indicador_codigo",
                         name="UQ_FuenteIndicador_clave"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False)
    indicador_codigo: Mapped[str] = mapped_column(String(50), nullable=False)
    #: EXAMEN_VISTA | NOTA_EXTERNA | CAPTURA_MANUAL — EXCEL no es una fuente
    fuente: Mapped[str] = mapped_column(String(20), nullable=False)
    actualizado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
    actualizado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
```

Si `datetime`, `timezone`, `DateTime` o `UniqueConstraint` no están importados en ese archivo, añádelos a los imports existentes.

Al final de `backend/app/models/hechos.py`:

```python
class NotaConocimiento(Base):
    """Notas capturadas a mano por el responsable, antes de integrarse al ciclo.

    SIN UNIQUE a propósito: un RM puede tener varias notas en un ciclo (temas o
    fechas distintas), igual que en `ext` y que en los exámenes, y por eso al
    integrar se PROMEDIAN. La contrapartida es una regla que el servicio debe
    sostener: corregir una nota EDITA esta fila, nunca añade otra — si
    corrigiera insertando, la nota vieja seguiría entrando al promedio y el
    número saldría mal sin que nada lo delatara.
    """
    __tablename__ = "FACT_NotaConocimiento"
    __table_args__ = {"schema": "DW"}

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    pais_codigo: Mapped[str] = mapped_column(
        String(10), ForeignKey("Config.DIM_Pais.codigo"), nullable=False, index=True)
    ciclo_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=False, index=True)
    rm_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=False, index=True)
    fecha_evaluacion: Mapped[date] = mapped_column(Date, nullable=False)
    nota: Mapped[Decimal] = mapped_column(Numeric(10, 4), nullable=False)
    tema: Mapped[str | None] = mapped_column(String(200), nullable=True)
    capturado_por_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    capturado_en: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, default=lambda: datetime.now(timezone.utc))
```

Si `date` o `Date` no están importados en `hechos.py`, añádelos.

- [ ] **Step 4: Escribir el servicio de la regla**

Crear `backend/app/services/fuente_indicador_service.py`:

```python
"""Quién alimenta EVAL_CONOCIMIENTOS en cada país.

POR QUÉ EXISTE ESTE MÓDULO
--------------------------
Tres caminos escriben el mismo indicador —los exámenes de VISTA, las notas que
Mallén deja en `ext`, y la captura manual— y los tres hacen delete-then-insert
sobre `(rm_id, indicador_id, ciclo_id)`. Sin un dueño declarado gana el último
en correr: no hay error, no hay aviso, solo un número distinto según el orden en
que alguien pulse los botones.

La regla vive AQUÍ y en ningún otro sitio. Repartir la comprobación por los tres
caminos es exactamente cómo se vuelven a desincronizar.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.dimensiones import FuenteIndicador

INDICADOR_CONOCIMIENTOS = "EVAL_CONOCIMIENTOS"

FUENTE_EXAMEN_VISTA = "EXAMEN_VISTA"
FUENTE_NOTA_EXTERNA = "NOTA_EXTERNA"
FUENTE_CAPTURA_MANUAL = "CAPTURA_MANUAL"

#: Las tres, y solo las tres. `EXCEL` NO está: no es que hoy no sea el dueño, es
#: que dejó de ser una vía (decisión del cliente, 12-ago-2026).
FUENTES: tuple[str, ...] = (FUENTE_EXAMEN_VISTA, FUENTE_NOTA_EXTERNA,
                            FUENTE_CAPTURA_MANUAL)

#: Un país sin configurar captura a mano, que es lo más parecido a lo que hacía
#: el Excel. Devolver un error obligaría a configurar antes de poder trabajar.
FUENTE_POR_DEFECTO = FUENTE_CAPTURA_MANUAL


class FuenteAjenaError(Exception):
    """Alguien que no es el dueño intentó escribir el indicador."""

    def __init__(self, pais_codigo: str, indicador_codigo: str,
                 duenio: str, intento: str):
        self.pais_codigo = pais_codigo
        self.indicador_codigo = indicador_codigo
        self.duenio = duenio
        self.intento = intento
        super().__init__(
            f"En {pais_codigo}, {indicador_codigo} lo alimenta «{duenio}»; "
            f"«{intento}» no puede escribirlo. Si esa es la decisión, cambia la "
            f"fuente en la pantalla de Conocimientos.")


def fuente_de(db: Session, pais_codigo: str,
              indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> str:
    fila = (db.query(FuenteIndicador)
            .filter(FuenteIndicador.pais_codigo == pais_codigo,
                    FuenteIndicador.indicador_codigo == indicador_codigo).first())
    return fila.fuente if fila is not None else FUENTE_POR_DEFECTO


def asegurar_duenio(db: Session, pais_codigo: str, fuente_que_escribe: str,
                    indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> None:
    """Levanta `FuenteAjenaError` si quien va a escribir no es el dueño.

    El error NOMBRA al dueño real: un «no tienes permiso» deja al operador sin
    saber qué cambiar ni dónde.
    """
    actual = fuente_de(db, pais_codigo, indicador_codigo)
    if actual != fuente_que_escribe:
        raise FuenteAjenaError(pais_codigo, indicador_codigo, actual,
                               fuente_que_escribe)


def fijar_fuente(db: Session, pais_codigo: str, fuente: str,
                 usuario_id: int | None,
                 indicador_codigo: str = INDICADOR_CONOCIMIENTOS) -> FuenteIndicador:
    """Declara el dueño. No hace commit: lo decide el llamador."""
    if fuente not in FUENTES:
        raise ValueError(
            f"«{fuente}» no es una fuente válida. Las únicas son: "
            f"{', '.join(FUENTES)}.")
    fila = (db.query(FuenteIndicador)
            .filter(FuenteIndicador.pais_codigo == pais_codigo,
                    FuenteIndicador.indicador_codigo == indicador_codigo).first())
    if fila is None:
        fila = FuenteIndicador(pais_codigo=pais_codigo,
                               indicador_codigo=indicador_codigo)
        db.add(fila)
    fila.fuente = fuente
    fila.actualizado_en = datetime.now(timezone.utc)
    fila.actualizado_por_usuario_id = usuario_id
    db.flush()
    return fila
```

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_fuente_indicador.py -q`
Expected: PASS — 7 tests

- [ ] **Step 6: Escribir la migración**

Crear `backend/alembic/versions/0035_fuente_conocimientos.py`:

```python
"""Fuente única de EVAL_CONOCIMIENTOS: dueño por país + notas capturadas a mano.

Revision ID: 0035_fuente_conocimientos
Revises: 0034_medicos_top
Create Date: 2026-08-12
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0035_fuente_conocimientos"
down_revision: Union[str, Sequence[str], None] = "0034_medicos_top"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "FuenteIndicador",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("indicador_codigo", sa.String(length=50), nullable=False),
        sa.Column("fuente", sa.String(length=20), nullable=False),
        sa.Column("actualizado_en", sa.DateTime(), nullable=False),
        sa.Column("actualizado_por_usuario_id", sa.Integer(), nullable=True),
        sa.ForeignKeyConstraint(["pais_codigo"], ["Config.DIM_Pais.codigo"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("pais_codigo", "indicador_codigo",
                            name="UQ_FuenteIndicador_clave"),
        schema="Config",
    )

    # Semilla: cada país existente arranca en CAPTURA_MANUAL, que es lo más
    # parecido a lo que hace el Excel hoy. El servicio ya devolvería ese default
    # sin fila, pero sembrarla hace visible la decisión en la pantalla desde el
    # primer día — un país "sin configurar" invita a creer que nadie decidió.
    op.execute("""
        INSERT INTO "Config"."FuenteIndicador"
            (pais_codigo, indicador_codigo, fuente, actualizado_en)
        SELECT codigo, 'EVAL_CONOCIMIENTOS', 'CAPTURA_MANUAL', NOW()
          FROM "Config"."DIM_Pais"
    """)

    # SIN UNIQUE a proposito: un RM puede tener varias notas en un ciclo (temas
    # o fechas distintas) y al integrar se promedian. Ver el docstring del
    # modelo `NotaConocimiento` para la regla que eso obliga a sostener.
    op.create_table(
        "FACT_NotaConocimiento",
        sa.Column("id", sa.BigInteger(), autoincrement=True, nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("ciclo_id", sa.Integer(), nullable=False),
        sa.Column("rm_id", sa.Integer(), nullable=False),
        sa.Column("fecha_evaluacion", sa.Date(), nullable=False),
        sa.Column("nota", sa.Numeric(precision=10, scale=4), nullable=False),
        sa.Column("tema", sa.String(length=200), nullable=True),
        sa.Column("capturado_por_usuario_id", sa.Integer(), nullable=True),
        sa.Column("capturado_en", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["pais_codigo"], ["Config.DIM_Pais.codigo"]),
        sa.ForeignKeyConstraint(["ciclo_id"], ["Config.DIM_Ciclo.id"]),
        sa.ForeignKeyConstraint(["rm_id"], ["Config.DIM_RM.id"]),
        sa.PrimaryKeyConstraint("id"),
        schema="DW",
    )
    op.create_index("IX_NotaConocimiento_ciclo", "FACT_NotaConocimiento",
                    ["ciclo_id", "rm_id"], schema="DW")


def downgrade() -> None:
    op.drop_index("IX_NotaConocimiento_ciclo", table_name="FACT_NotaConocimiento",
                  schema="DW")
    op.drop_table("FACT_NotaConocimiento", schema="DW")
    op.drop_table("FuenteIndicador", schema="Config")
```

- [ ] **Step 7: Comprobar que la migración aplica y que Alembic queda en un solo head**

Run:
```bash
cd backend && ./venv/Scripts/python.exe -m alembic upgrade head && ./venv/Scripts/python.exe -m alembic heads
```
Expected: `0035_fuente_conocimientos (head)`, un solo head.

- [ ] **Step 8: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 9: Commit**

```bash
git add backend/alembic/versions/0035_fuente_conocimientos.py backend/app/models/dimensiones.py backend/app/models/hechos.py backend/app/services/fuente_indicador_service.py backend/tests/test_fuente_indicador.py
git commit -m "feat(conocimientos) dueno por pais de EVAL_CONOCIMIENTOS + tabla de notas capturadas"
```

---

### Task 2: El Excel sale del indicador — y deja de barrer el ciclo entero

**Files:**
- Modify: `backend/app/services/etl_service.py`
- Test: `backend/tests/test_etl_conocimientos.py`

**Interfaces:**
- Consumes: de la Tarea 1, nada directamente (la exclusión del Excel es incondicional: `EXCEL` no es una fuente).
- Produces: constante de módulo `INDICADORES_SIN_EXCEL: frozenset[str]`; `_cargar_datos` pasa a devolver `(exitosas, errores, advertencias_carga)`.

> **Este task arregla dos cosas, y la segunda es más grave que la primera.**
>
> `_cargar_datos`, para `KPI_RM`, borra los resultados previos del ciclo **sin filtrar por indicador**:
> ```python
> db.query(ResultadoIndicador).filter(ResultadoIndicador.ciclo_id.in_(...)).delete()
> ```
> Cuando todo venía del Excel eso era coherente: borraba lo suyo y lo reponía. Pero desde que existe la integración de Mallén (sub-proyectos 3 y 5), una carga de Excel **destruye en silencio los cuatro indicadores de visita y `VENTAS`**, que el Excel no repone. Omitir las filas de `EVAL_CONOCIMIENTOS` al insertar no bastaría: el borrado se las llevaría igual.
>
> La regla que arregla ambas: **un cargador solo puede reemplazar lo que él mismo repone.**

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_etl_conocimientos.py`:

```python
"""El Excel deja de alimentar EVAL_CONOCIMIENTOS, y deja de barrer el ciclo entero.

Dos reglas:
  1. Las filas de EVAL_CONOCIMIENTOS del archivo se omiten SIEMPRE (decisión del
     cliente: "nunca más Excel para este proceso") y se reportan como
     advertencia, sin tumbar el resto del archivo.
  2. El borrado previo se acota a los indicadores que ESE archivo trae. Antes
     barría el ciclo completo, lo que desde la integración de Mallén destruía
     indicadores que el Excel no repone.

Necesita PostgreSQL real.
"""
from datetime import date
from decimal import Decimal

import pandas as pd
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
from app.models.dimensiones import Ciclo, Gerente, Indicador, Linea, Pais, RepresentanteMedico
from app.models.hechos import ResultadoIndicador
from app.services import etl_service

BD_PRUEBA = "vista_test_etl_conoc"


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
def escenario(motor):
    Sesion = sessionmaker(bind=motor)
    s = Sesion()
    for tabla in ('"DW"."FACT_ResultadoIndicador"', '"Config"."DIM_Indicador"',
                  '"Config"."DIM_RM"', '"Config"."DIM_Gerente"',
                  '"Config"."DIM_Ciclo"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()

    s.add(Pais(codigo="DO", nombre="República Dominicana"))
    s.flush()
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    s.add(linea)
    s.flush()
    gerente = Gerente(pais_codigo="DO", codigo="GD01", nombre="Gerente Uno",
                      email="g@ejemplo.com", tipo="DISTRITO")
    s.add(gerente)
    s.flush()
    rm = RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                             gerente_id=gerente.id, codigo="VM01",
                             nombre="Representante Uno")
    ciclo = Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                  fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                  dias_laborables=20, cerrado=False)
    s.add_all([rm, ciclo])
    s.flush()
    indicadores = {}
    for codigo, escala in (("EVAL_CONOCIMIENTOS", 100), ("COB_MD_F1", 1),
                           ("VENTAS", 1)):
        i = Indicador(pais_codigo="DO", codigo=codigo, nombre=codigo,
                      modulo="RESULTADOS", tipo_periodo="CICLO", escala=escala,
                      ponderacion_pct=10, activo=True)
        s.add(i)
        s.flush()
        indicadores[codigo] = i
    s.commit()
    yield {"db": s, "rm": rm, "ciclo": ciclo, "linea": linea,
           "gerente": gerente, "ind": indicadores}
    s.close()


def _mapas(e):
    ind = {("DO", c): i.id for c, i in e["ind"].items()}
    return {
        "rm": {"VM01": {"id": e["rm"].id, "linea_id": e["linea"].id,
                        "gerente_id": e["gerente"].id, "pais_codigo": "DO"}},
        "gerente": {}, "cap": {}, "ind": ind,
        "ciclo": {("DO", 2026, 1): e["ciclo"].id},
        "pais": {"DO": "DO"},
    }


def _df(filas):
    return pd.DataFrame(filas)


def _resultado(e, codigo):
    return (e["db"].query(ResultadoIndicador)
            .filter(ResultadoIndicador.indicador_id == e["ind"][codigo].id,
                    ResultadoIndicador.ciclo_id == e["ciclo"].id).first())


def test_las_filas_de_conocimientos_se_omiten_y_las_demas_cargan(escenario):
    e = escenario
    df = _df([
        {"rm_codigo": "VM01", "indicador_codigo": "EVAL_CONOCIMIENTOS",
         "valor_real": 88, "pais_codigo": "DO", "anio": 2026, "ciclo_id": 1},
        {"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
         "valor_real": 0.9, "pais_codigo": "DO", "anio": 2026, "ciclo_id": 1},
    ])

    exitosas, errores, advertencias = etl_service._cargar_datos(
        e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert exitosas == 1
    assert errores == []
    assert _resultado(e, "COB_MD_F1") is not None
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
    assert any("EVAL_CONOCIMIENTOS" in a for a in advertencias)


def test_el_excel_no_borra_lo_que_no_repone(escenario):
    """El defecto de fondo: el borrado previo barría el ciclo ENTERO. Desde la
    integración de Mallén eso destruye VENTAS y los indicadores de visita, que
    el Excel no repone."""
    e = escenario
    for codigo, valor in (("VENTAS", Decimal("0.9")),
                          ("EVAL_CONOCIMIENTOS", Decimal("77"))):
        e["db"].add(ResultadoIndicador(
            rm_id=e["rm"].id, indicador_id=e["ind"][codigo].id,
            ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
            gerente_id=e["gerente"].id, resultado_real=valor, activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
               "valor_real": 0.5, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    etl_service._cargar_datos(e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert _resultado(e, "VENTAS").resultado_real == Decimal("0.9000")
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("77.0000")
    assert _resultado(e, "COB_MD_F1") is not None


def test_el_excel_si_reemplaza_lo_suyo(escenario):
    """La otra mitad de la regla: acotar el borrado no puede volverlo inútil —
    un indicador que el archivo SÍ trae se reemplaza, no se duplica."""
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["COB_MD_F1"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("0.1"), activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "COB_MD_F1",
               "valor_real": 0.5, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    etl_service._cargar_datos(e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["COB_MD_F1"].id).all())
    assert len(filas) == 1
    assert filas[0].resultado_real == Decimal("0.5000")


def test_un_archivo_solo_de_conocimientos_no_borra_nada(escenario):
    """Caso límite del acotado: si tras excluir no queda ningún indicador que
    reponer, no debe borrarse nada en absoluto."""
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("77"), activo=True))
    e["db"].commit()

    df = _df([{"rm_codigo": "VM01", "indicador_codigo": "EVAL_CONOCIMIENTOS",
               "valor_real": 88, "pais_codigo": "DO", "anio": 2026,
               "ciclo_id": 1}])
    exitosas, _, _ = etl_service._cargar_datos(
        e["db"], df, "KPI_RM", "DO", e["ciclo"].id, _mapas(e))
    e["db"].commit()

    assert exitosas == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("77.0000")
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_etl_conocimientos.py -q`
Expected: FAIL — `ValueError: too many values to unpack` (hoy `_cargar_datos` devuelve 2 elementos), y los de borrado en rojo porque el ciclo se barre entero.

- [ ] **Step 3: Excluir el indicador y acotar el borrado**

En `backend/app/services/etl_service.py`, junto a las constantes de módulo del principio:

```python
#: Indicadores que el Excel YA NO alimenta. Decisión del cliente (12-ago-2026):
#: "nunca más Excel para este proceso". EVAL_CONOCIMIENTOS se captura en la
#: pantalla de Conocimientos, o llega por exámenes, o lo envía Mallén — las tres
#: dejan autoría y fecha, cosa que una hoja de cálculo no hace.
INDICADORES_SIN_EXCEL: frozenset[str] = frozenset({"EVAL_CONOCIMIENTOS"})
```

En `_cargar_datos`, junto a `errores = []`:

```python
    advertencias_carga: list[str] = []
```

Reemplazar el bloque del borrado previo (`if ciclos_a_limpiar:`) por:

```python
        if ciclos_a_limpiar:
            # El borrado se acota a los indicadores que ESTE archivo trae. Antes
            # barría el ciclo entero: cuando todo venía del Excel era coherente
            # —borraba lo suyo y lo reponía—, pero desde la integración de Mallén
            # destruía en silencio los cuatro indicadores de visita y VENTAS, que
            # el Excel no repone. La regla es: un cargador solo puede reemplazar
            # lo que él mismo vuelve a escribir.
            codigos_archivo = {
                str(c).strip().upper()
                for c in df.get("indicador_codigo", pd.Series(dtype=str)).dropna()
            } - INDICADORES_SIN_EXCEL
            ids_a_limpiar = [i for (_p, c), i in mapa_ind.items()
                             if isinstance(c, str) and c in codigos_archivo]
            if ids_a_limpiar:
                deleted = (
                    db.query(ResultadoIndicador)
                      .filter(ResultadoIndicador.ciclo_id.in_(list(ciclos_a_limpiar)),
                              ResultadoIndicador.indicador_id.in_(ids_a_limpiar))
                      .delete(synchronize_session=False)
                )
                db.flush()
                logger.info(f"ETL: eliminados {deleted} registros previos de "
                            f"FACT_ResultadoIndicador (ciclos {ciclos_a_limpiar}, "
                            f"{len(ids_a_limpiar)} indicadores del archivo)")
            else:
                logger.info("ETL: el archivo no trae indicadores que el Excel "
                            "pueda reponer — no se borra nada")
        else:
            logger.warning("ETL: no se pudo determinar ciclos_a_limpiar — se omite borrado previo")
```

En el bucle de filas, justo después de `ind_codigo = str(row.get("indicador_codigo", "")).strip().upper()`:

```python
                if ind_codigo in INDICADORES_SIN_EXCEL:
                    advertencias_carga.append(
                        f"Fila {idx+2}: {ind_codigo} ya no se carga por Excel; "
                        f"se captura en la pantalla de Conocimientos, llega por "
                        f"exámenes o la envía Mallén, según la fuente del país.")
                    continue
```

Y cambiar el `return` final de `_cargar_datos`:

```python
    return exitosas, errores, advertencias_carga
```

- [ ] **Step 4: Ajustar el llamador**

En `backend/app/services/etl_service.py`, dentro de `procesar_excel_task`, donde hoy dice `exitosas, errores = _cargar_datos(...)`:

```python
            exitosas, errores, advertencias_carga = _cargar_datos(
                db, df, tipo_archivo, pais_codigo, ciclo_id, mapas
            )
            advertencias.extend(advertencias_carga)
```

`advertencias` ya existe en ese ámbito (viene de `_validar_y_enriquecer`) y ya se persiste en `job.filas_advertencia` / `job.log_advertencias`: la omisión viaja al historial de cargas sin inventar un canal nuevo.

Comprobar que la inicialización de la línea anterior (`exitosas, errores = 0, []`) sigue siendo válida — si el modo es `SIMULACION` no se llama a `_cargar_datos`.

- [ ] **Step 5: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_etl_conocimientos.py -q`
Expected: PASS — 4 tests

- [ ] **Step 6: Comprobar por mutación que el test del borrado protege algo**

Quitar temporalmente `ResultadoIndicador.indicador_id.in_(ids_a_limpiar)` del filtro.
Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_etl_conocimientos.py -q -k no_borra_lo_que_no_repone`
Expected: FAIL. Revertir y volver a correr: PASS.

- [ ] **Step 7: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 8: Commit**

```bash
git add backend/app/services/etl_service.py backend/tests/test_etl_conocimientos.py
git commit -m "fix(etl) el Excel deja de alimentar EVAL_CONOCIMIENTOS y de barrer el ciclo entero"
```

---

### Task 3: La captura manual y su puerta

**Files:**
- Create: `backend/app/services/conocimientos_service.py`
- Test: `backend/tests/test_conocimientos_captura.py`

**Interfaces:**
- Consumes: de la Tarea 1, `fuente_indicador_service` completo y el modelo `NotaConocimiento`.
- Produces: `capturar_nota(db, pais_codigo, ciclo_id, rm_id, nota, fecha_evaluacion, tema, usuario_id) -> NotaConocimiento`; `corregir_nota(db, nota_id, nota, tema, usuario_id) -> NotaConocimiento`; `notas_del_ciclo(db, pais_codigo, ciclo_id) -> list[dict]`; `integrar_captura(db, pais_codigo, ciclo_id) -> dict`; `_upsert_resultado(db, rm, ciclo_id, nota)`.

- [ ] **Step 1: Escribir los tests**

Crear `backend/tests/test_conocimientos_captura.py`. **Copia** de `tests/test_etl_conocimientos.py` el encabezado de imports, `_url`, la fixture `motor`, la fixture `escenario` y el helper `_resultado` — son módulos distintos, así que se copian, no se importan. Cambia `BD_PRUEBA` a `"vista_test_conoc_captura"` y añade `'"DW"."FACT_NotaConocimiento"'` al **principio** de la lista de tablas que se limpian (antes que `DIM_RM` y `DIM_Ciclo`, por las claves foráneas). Añade después:

```python
from app.models.hechos import NotaConocimiento
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fs
from app.services import motor_calculo_service


def test_capturar_y_listar_marca_quien_falta(escenario):
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), "Cardio", usuario_id=3)
    e["db"].commit()

    filas = cs.notas_del_ciclo(e["db"], "DO", e["ciclo"].id)

    assert len(filas) == 1
    assert filas[0]["rm_id"] == e["rm"].id
    assert filas[0]["notas"][0]["nota"] == Decimal("80.0000")


def test_una_nota_fuera_de_rango_se_rechaza_en_el_servicio(escenario):
    """En el servicio, no solo en el formulario: la API la puede llamar
    cualquiera."""
    e = escenario
    for mala in (Decimal("-1"), Decimal("101")):
        with pytest.raises(ValueError):
            cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, mala,
                             date(2026, 1, 15), None, usuario_id=3)


def test_corregir_EDITA_la_fila_no_anade_otra(escenario):
    """La tabla no lleva UNIQUE, así que si corregir insertara, la nota vieja
    seguiría entrando al promedio y el número saldría mal sin que nada lo
    delatara."""
    e = escenario
    fila = cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id,
                            Decimal("60"), date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    cs.corregir_nota(e["db"], fila.id, Decimal("90"), "Corregida", usuario_id=4)
    e["db"].commit()

    todas = e["db"].query(NotaConocimiento).all()
    assert len(todas) == 1
    assert todas[0].nota == Decimal("90.0000")
    # Queda quién la tocó por última vez y cuándo: es lo que hace auditable la
    # corrección, y es justo lo que una hoja de cálculo no deja.
    assert todas[0].capturado_por_usuario_id == 4
    assert todas[0].capturado_en is not None

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("90.0000")


def test_capturar_una_segunda_nota_SI_anade_fila_y_promedia(escenario):
    """La frontera con el test anterior: corregir edita, capturar añade."""
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("60"),
                     date(2026, 1, 15), "Tema A", usuario_id=3)
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("100"),
                     date(2026, 1, 20), "Tema B", usuario_id=3)
    e["db"].commit()

    assert e["db"].query(NotaConocimiento).count() == 2

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")


def test_un_rm_sin_notas_no_genera_fila(escenario):
    e = escenario
    out = cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_integrar_atraviesa_el_motor_y_puntua(escenario):
    """Afirmar solo sobre `resultado_real` es comparar el valor consigo mismo.
    EVAL_CONOCIMIENTOS tiene escala=100 y ponderación 10: una nota de 80 debe
    dar 8 puntos."""
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()
    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()

    fila = _resultado(e, "EVAL_CONOCIMIENTOS")
    assert fila.resultado_porcentaje == Decimal("80.0000")
    assert fila.puntos_obtenidos == Decimal("8.0000")
    # `pais_codigo`, `linea_id` y `gerente_id` son NOT NULL y NO vienen en la
    # nota: salen del RM. Sin esto el INSERT ni siquiera llegaría a la BD.
    assert fila.pais_codigo == "DO"
    assert fila.linea_id == e["linea"].id
    assert fila.gerente_id == e["gerente"].id


def test_integrar_dos_veces_no_duplica(escenario):
    e = escenario
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()
    cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["EVAL_CONOCIMIENTOS"].id).all())
    assert len(filas) == 1


def test_ciclo_cerrado_no_escribe_ni_borra(escenario):
    e = escenario
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("55"), activo=True))
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["ciclo"].cerrado = True
    e["db"].commit()

    out = cs.integrar_captura(e["db"], "DO", e["ciclo"].id)
    e["db"].commit()

    assert out["abortado"] is True
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("55.0000")


def test_integrar_se_niega_si_el_pais_no_es_de_captura(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_EXAMEN_VISTA, usuario_id=1)
    cs.capturar_nota(e["db"], "DO", e["ciclo"].id, e["rm"].id, Decimal("80"),
                     date(2026, 1, 15), None, usuario_id=3)
    e["db"].commit()

    with pytest.raises(fs.FuenteAjenaError):
        cs.integrar_captura(e["db"], "DO", e["ciclo"].id)

    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None
```

- [ ] **Step 2: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_conocimientos_captura.py -q`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.services.conocimientos_service'`

- [ ] **Step 3: Escribir el servicio**

Crear `backend/app/services/conocimientos_service.py`:

```python
"""Captura manual de notas de conocimiento y su integración al ciclo.

Sustituye al Excel para EVAL_CONOCIMIENTOS. La captura pasa por una tabla propia
—`DW.FACT_NotaConocimiento`— y se integra en un paso explícito, igual que los
otros dos caminos: el examen tiene intentos → consolidación, Mallén tiene `ext` →
integración. De ahí salen tres propiedades que escribir directo no da: la nota se
corrige antes de entrar, queda auditada con autor y fecha, y el reproceso es
idempotente.
"""
from datetime import date, datetime, timezone
from decimal import Decimal

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Indicador, RepresentanteMedico
from app.models.hechos import NotaConocimiento, ResultadoIndicador
from app.services import fuente_indicador_service as fuentes
from app.services import recalculo_service

NOTA_MIN = Decimal("0")
NOTA_MAX = Decimal("100")


def _validar_nota(nota: Decimal) -> Decimal:
    """En el servicio y no solo en el formulario: la API la llama cualquiera."""
    valor = Decimal(str(nota))
    if valor < NOTA_MIN or valor > NOTA_MAX:
        raise ValueError(
            f"La nota debe estar entre {NOTA_MIN} y {NOTA_MAX}; llegó {valor}.")
    return valor


def capturar_nota(db: Session, pais_codigo: str, ciclo_id: int, rm_id: int,
                  nota: Decimal, fecha_evaluacion: date, tema: str | None,
                  usuario_id: int | None) -> NotaConocimiento:
    """Añade una nota. Para CORREGIR una existente se usa `corregir_nota`.

    La distinción importa: la tabla no lleva UNIQUE porque un RM puede tener
    varias notas en un ciclo, así que corregir insertando dejaría la nota vieja
    entrando al promedio.
    """
    fila = NotaConocimiento(
        pais_codigo=pais_codigo, ciclo_id=ciclo_id, rm_id=rm_id,
        nota=_validar_nota(nota), fecha_evaluacion=fecha_evaluacion, tema=tema,
        capturado_por_usuario_id=usuario_id,
        capturado_en=datetime.now(timezone.utc))
    db.add(fila)
    db.flush()
    return fila


def corregir_nota(db: Session, nota_id: int, nota: Decimal, tema: str | None,
                  usuario_id: int | None) -> NotaConocimiento:
    """Corrige una nota ya capturada EDITANDO su fila."""
    fila = db.get(NotaConocimiento, nota_id)
    if fila is None:
        raise ValueError(f"No existe la nota {nota_id}.")
    fila.nota = _validar_nota(nota)
    fila.tema = tema
    fila.capturado_por_usuario_id = usuario_id
    fila.capturado_en = datetime.now(timezone.utc)
    db.flush()
    return fila


def notas_del_ciclo(db: Session, pais_codigo: str, ciclo_id: int) -> list[dict]:
    """Los RM del país con sus notas del ciclo — incluidos los que no tienen
    ninguna, que es lo que le dice al responsable cuánto le falta."""
    rms = (db.query(RepresentanteMedico)
           .filter(RepresentanteMedico.pais_codigo == pais_codigo)
           .order_by(RepresentanteMedico.codigo).all())
    por_rm: dict[int, list] = {}
    for n in (db.query(NotaConocimiento)
              .filter(NotaConocimiento.ciclo_id == ciclo_id,
                      NotaConocimiento.pais_codigo == pais_codigo)
              .order_by(NotaConocimiento.fecha_evaluacion).all()):
        por_rm.setdefault(n.rm_id, []).append(n)
    salida = []
    for rm in rms:
        notas = por_rm.get(rm.id, [])
        salida.append({
            "rm_id": rm.id, "rm_codigo": rm.codigo, "rm_nombre": rm.nombre,
            "notas": [{"id": n.id, "nota": n.nota, "tema": n.tema,
                       "fecha_evaluacion": n.fecha_evaluacion,
                       "capturado_en": n.capturado_en} for n in notas],
            "promedio": (sum((n.nota for n in notas), Decimal(0)) / len(notas)
                         if notas else None),
        })
    return salida


def _upsert_resultado(db: Session, rm, ciclo_id: int, nota: Decimal) -> bool:
    """Escribe la nota del RM en `FACT_ResultadoIndicador`, reemplazando la
    anterior. `pais_codigo`/`linea_id`/`gerente_id` salen del RM: son NOT NULL y
    no vienen en la nota. Devuelve False si el país no tiene el indicador.
    """
    indicador = (db.query(Indicador)
                 .filter(Indicador.codigo == fuentes.INDICADOR_CONOCIMIENTOS,
                         Indicador.pais_codigo == rm.pais_codigo).first())
    if indicador is None:
        logger.warning(f"Conocimientos: {rm.pais_codigo} no tiene el indicador "
                       f"{fuentes.INDICADOR_CONOCIMIENTOS}")
        return False
    (db.query(ResultadoIndicador)
     .filter(ResultadoIndicador.rm_id == rm.id,
             ResultadoIndicador.indicador_id == indicador.id,
             ResultadoIndicador.ciclo_id == ciclo_id)
     .delete(synchronize_session=False))
    db.add(ResultadoIndicador(
        rm_id=rm.id, indicador_id=indicador.id, ciclo_id=ciclo_id,
        pais_codigo=rm.pais_codigo, linea_id=rm.linea_id,
        gerente_id=rm.gerente_id, resultado_real=nota, activo=True))
    return True


def integrar_captura(db: Session, pais_codigo: str, ciclo_id: int) -> dict:
    """Promedia las notas capturadas de cada RM y las escribe al indicador.

    El guard de ciclo cerrado va ANTES de cualquier borrado: un
    delete-then-insert que luego aborta borra `puntos_obtenidos` para siempre.
    """
    fuentes.asegurar_duenio(db, pais_codigo, fuentes.FUENTE_CAPTURA_MANUAL)
    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Conocimientos: ciclo {ciclo_id} cerrado — no se integra")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_integrados": 0}

    filas = (db.query(NotaConocimiento)
             .filter(NotaConocimiento.ciclo_id == ciclo_id,
                     NotaConocimiento.pais_codigo == pais_codigo).all())
    por_rm: dict[int, list] = {}
    for n in filas:
        por_rm.setdefault(n.rm_id, []).append(n.nota)

    integrados = 0
    for rm_id, notas in por_rm.items():
        rm = db.get(RepresentanteMedico, rm_id)
        if rm is None:
            continue
        promedio = sum(notas, Decimal(0)) / len(notas)
        if _upsert_resultado(db, rm, ciclo_id, promedio):
            integrados += 1

    logger.info(f"Conocimientos: {integrados} RM integrados en el ciclo {ciclo_id} "
                f"de {pais_codigo}")
    return {"abortado": False, "rms_integrados": integrados,
            "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}
```

- [ ] **Step 4: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_conocimientos_captura.py -q`
Expected: PASS — 9 tests

- [ ] **Step 5: Comprobar por mutación que el test de corrección protege algo**

Cambiar temporalmente `corregir_nota` para que haga `db.add(NotaConocimiento(...))` en vez de editar.
Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_conocimientos_captura.py -q -k corregir_EDITA`
Expected: FAIL. Revertir y volver a correr: PASS.

- [ ] **Step 6: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/conocimientos_service.py backend/tests/test_conocimientos_captura.py
git commit -m "feat(conocimientos) captura manual de notas e integracion al ciclo"
```

---

### Task 4: El integrador de Mallén y la puerta de los exámenes

**Files:**
- Modify: `backend/app/services/conocimientos_service.py`, `backend/app/services/examen_consolidacion_service.py`
- Test: `backend/tests/test_conocimientos_integracion.py`, `backend/tests/test_examen_consolidacion_service.py`

**Interfaces:**
- Consumes: de la Tarea 3, `_upsert_resultado(db, rm, ciclo_id, nota) -> bool`; de la Tarea 1, `fuente_indicador_service`. De fuera: `integracion_mapeo.id_mapeado(db, entidad, pais_codigo, codigo_externo) -> int | None`, `ENT_REPRESENTANTE`, `ENT_CICLO`.
- Produces: `integrar_conocimientos(db, pais_codigo, ciclo_codigo, hallazgos) -> dict`.

- [ ] **Step 1: Escribir el test de la puerta de exámenes**

Añadir a `backend/tests/test_examen_consolidacion_service.py` (ese archivo usa `MagicMock` y `monkeypatch`; respeta su estilo):

```python
def test_consolidar_se_niega_si_el_pais_no_es_de_examenes(monkeypatch):
    """Con otro dueño, consolidar no debe escribir NADA: los tres caminos hacen
    delete-then-insert, así que dejarlo pasar sobrescribiría la nota buena."""
    db = MagicMock()
    monkeypatch.setattr(cons.fuentes, "fuente_de",
                        lambda d, p, *a, **k: cons.fuentes.FUENTE_CAPTURA_MANUAL)
    escrituras = {"n": 0}
    monkeypatch.setattr(cons.examen_kpi_service, "upsert_nota_rm",
                        lambda *a, **k: escrituras.__setitem__("n", escrituras["n"] + 1))

    with pytest.raises(cons.fuentes.FuenteAjenaError):
        cons.consolidar_ciclo(db, ciclo_id=7, pais_codigo="DO", usuario_id=1)

    assert escrituras["n"] == 0
```

Añadir `import pytest` al principio del archivo si no está.

- [ ] **Step 2: Correr ese test y confirmar que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_consolidacion_service.py -q -k se_niega`
Expected: FAIL — `AttributeError: module 'app.services.examen_consolidacion_service' has no attribute 'fuentes'`

- [ ] **Step 3: Añadir la puerta a la consolidación de exámenes**

En `backend/app/services/examen_consolidacion_service.py`, añadir al import:

```python
from app.services import fuente_indicador_service as fuentes
```

y como PRIMERA línea del cuerpo de `consolidar_ciclo`, antes del guard de ciclo cerrado:

```python
    # Antes que nada: ¿es este país de exámenes? Los tres caminos hacen
    # delete-then-insert sobre el mismo indicador, así que consolidar en un país
    # que se alimenta de otra fuente borraría la nota buena sin dejar rastro.
    fuentes.asegurar_duenio(db, pais_codigo, fuentes.FUENTE_EXAMEN_VISTA)
```

- [ ] **Step 4: Correr los tests de exámenes**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_examen_consolidacion_service.py -q`
Expected: PASS. Los tests preexistentes que llaman `consolidar_ciclo` con un `MagicMock` ahora atraviesan `fuente_de`, que sobre un mock devuelve otro mock y no coincidiría con `EXAMEN_VISTA`: añádeles `monkeypatch.setattr(cons.fuentes, "fuente_de", lambda d, p, *a, **k: cons.fuentes.FUENTE_EXAMEN_VISTA)`. Es hacer explícito un prerequisito real, no debilitar la aserción — cada test conserva intactas las suyas.

- [ ] **Step 5: Escribir los tests del integrador**

Crear `backend/tests/test_conocimientos_integracion.py`. **Copia** de `tests/test_conocimientos_captura.py` el encabezado, `_url`, `motor`, `escenario` y `_resultado`; cambia `BD_PRUEBA` a `"vista_test_conoc_ext"` y añade a la limpieza, **antes** de las tablas de `Config`: `"ext.factevaluacionconocimiento"`, `"ext.controlcarga"`, `"ext.dimrepresentante"`, `"ext.dimciclo"`, `"ext.dimpais"` y `'"Config"."MapeoExterno"'`.

Amplía además la fixture `escenario` para sembrar el equivalente en `ext` y los mapeos que el integrador necesita, igual que hace el escenario de `tests/test_integracion_ventas.py` — `ExtDimPais("DO")`, `ExtDimCiclo("C01-2026")`, `ExtDimRepresentante("VM01")`, un `ExtControlCarga(lote_id=3001, estado="VALIDADO")`, y las dos filas de `MapeoExterno` (`ENT_REPRESENTANTE`/`VM01` y `ENT_CICLO`/`C01-2026`) apuntando al `rm.id` y al `ciclo.id` internos. Sin esas cinco filas las claves foráneas de `ext.factevaluacionconocimiento` rechazan la inserción.

Luego añade:

```python
from app.models.integracion_ext import (
    ExtControlCarga, ExtDimCiclo, ExtDimPais, ExtDimRepresentante,
    ExtFactEvaluacionConocimiento,
)
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE, MapeoExterno


def _nota_ext(db, origen_id, nota, rm="VM01", lote_id=3001, tema=None):
    db.add(ExtFactEvaluacionConocimiento(
        lote_id=lote_id, origen_id=origen_id, pais_codigo="DO",
        ciclo_codigo="C01-2026", rm_codigo=rm,
        fecha_evaluacion=date(2026, 1, 15), nota=Decimal(str(nota)), tema=tema))
    db.flush()


def test_promedia_las_notas_del_rm(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 60)
    _nota_ext(e["db"], "N-2", 100)
    e["db"].commit()

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    assert out["rms_integrados"] == 1
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")


def test_atraviesa_el_motor_y_puntua(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()
    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    motor_calculo_service.completar_puntajes(e["db"], e["ciclo"].id, "DO")
    e["db"].commit()

    fila = _resultado(e, "EVAL_CONOCIMIENTOS")
    assert fila.resultado_porcentaje == Decimal("80.0000")
    assert fila.puntos_obtenidos == Decimal("8.0000")


def test_se_niega_si_el_pais_no_es_de_notas_externas(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_CAPTURA_MANUAL, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert any(h.severidad == "error" for h in hallazgos)
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_filas_de_un_lote_no_validado_se_omiten(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ExtControlCarga(
        lote_id=3002, sistema_origen="LMS", modulo="CONOCIMIENTOS",
        pais_codigo="DO", ciclo_codigo="C01-2026",
        fecha_extraccion=datetime(2026, 1, 31, 20, 0),
        fecha_recepcion=datetime(2026, 1, 31, 21, 0), filas_enviadas=1,
        estado="RECHAZADO"))
    e["db"].flush()
    _nota_ext(e["db"], "N-9", 99, lote_id=3002)
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 0
    assert _resultado(e, "EVAL_CONOCIMIENTOS") is None


def test_ciclo_cerrado_no_escribe_ni_borra(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ResultadoIndicador(
        rm_id=e["rm"].id, indicador_id=e["ind"]["EVAL_CONOCIMIENTOS"].id,
        ciclo_id=e["ciclo"].id, pais_codigo="DO", linea_id=e["linea"].id,
        gerente_id=e["gerente"].id, resultado_real=Decimal("55"), activo=True))
    _nota_ext(e["db"], "N-1", 90)
    e["ciclo"].cerrado = True
    e["db"].commit()

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    assert out["abortado"] is True
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("55.0000")


def test_reintegrar_no_duplica(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    _nota_ext(e["db"], "N-1", 80)
    e["db"].commit()

    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()
    cs.integrar_conocimientos(e["db"], "DO", "C01-2026", [])
    e["db"].commit()

    filas = (e["db"].query(ResultadoIndicador)
             .filter(ResultadoIndicador.indicador_id == e["ind"]["EVAL_CONOCIMIENTOS"].id).all())
    assert len(filas) == 1


def test_rm_sin_mapeo_se_omite_con_hallazgo_y_el_resto_entra(escenario):
    e = escenario
    fs.fijar_fuente(e["db"], "DO", fs.FUENTE_NOTA_EXTERNA, usuario_id=1)
    e["db"].add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                                    nombre="Sin mapear", activo=True))
    e["db"].flush()
    _nota_ext(e["db"], "N-1", 80)
    _nota_ext(e["db"], "N-9", 10, rm="VM99")
    e["db"].commit()
    hallazgos = []

    out = cs.integrar_conocimientos(e["db"], "DO", "C01-2026", hallazgos)
    e["db"].commit()

    assert out["rms_integrados"] == 1
    assert any(h.severidad == "error" for h in hallazgos)
    assert _resultado(e, "EVAL_CONOCIMIENTOS").resultado_real == Decimal("80.0000")
```

- [ ] **Step 6: Correr los tests y confirmar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_conocimientos_integracion.py -q`
Expected: FAIL — `AttributeError: module 'app.services.conocimientos_service' has no attribute 'integrar_conocimientos'`

- [ ] **Step 7: Escribir el integrador**

Añadir a `backend/app/services/conocimientos_service.py`:

```python
from app.models.integracion_ext import ExtControlCarga, ExtFactEvaluacionConocimiento
from app.models.mapeo_externo import ENT_CICLO, ENT_REPRESENTANTE
from app.services import integracion_mapeo as mapeo
from app.services.integracion_dimensiones_service import SEVERIDAD_ERROR, Hallazgo

#: Un lote ya INTEGRADO se vuelve a leer sin problema: la escritura es
#: idempotente y reprocesar debe poder repetirse.
_ESTADOS_INTEGRABLES = ("VALIDADO", "INTEGRADO")


def integrar_conocimientos(db: Session, pais_codigo: str, ciclo_codigo: str,
                           hallazgos: list) -> dict:
    """`ext.factevaluacionconocimiento` → `EVAL_CONOCIMIENTOS`, promediando por RM.

    Un RM puede traer varias notas (temas o fechas distintas): se promedian,
    igual que en los otros dos caminos.
    """
    fuente = fuentes.fuente_de(db, pais_codigo)
    if fuente != fuentes.FUENTE_NOTA_EXTERNA:
        hallazgos.append(Hallazgo(
            "factevaluacionconocimiento", ciclo_codigo,
            f"En {pais_codigo}, {fuentes.INDICADOR_CONOCIMIENTOS} lo alimenta "
            f"«{fuente}»; las notas de Mallén no se integraron. Cambia la fuente "
            f"en Conocimientos si esa es la decisión.", SEVERIDAD_ERROR))
        return {"abortado": True, "motivo": "fuente_ajena", "rms_integrados": 0}

    ciclo_id = mapeo.id_mapeado(db, ENT_CICLO, pais_codigo, ciclo_codigo)
    if ciclo_id is None:
        hallazgos.append(Hallazgo(
            "factevaluacionconocimiento", ciclo_codigo,
            f"No se pudo resolver el ciclo «{ciclo_codigo}»; sincroniza "
            f"dimensiones primero.", SEVERIDAD_ERROR))
        return {"abortado": True, "motivo": "ciclo_no_mapeado", "rms_integrados": 0}

    try:
        recalculo_service.validar_ciclo_abierto(db, ciclo_id)
    except recalculo_service.CicloCerradoError:
        logger.info(f"Conocimientos: ciclo {ciclo_id} cerrado — no se integra")
        return {"abortado": True, "motivo": "ciclo_cerrado", "rms_integrados": 0}

    filas = (db.query(ExtFactEvaluacionConocimiento)
             .filter(ExtFactEvaluacionConocimiento.pais_codigo == pais_codigo,
                     ExtFactEvaluacionConocimiento.ciclo_codigo == ciclo_codigo).all())
    estados = {l.lote_id: l.estado for l in db.query(ExtControlCarga).filter(
        ExtControlCarga.lote_id.in_({f.lote_id for f in filas} or {0})).all()}

    por_rm: dict[str, list] = {}
    for fila in filas:
        if estados.get(fila.lote_id) not in _ESTADOS_INTEGRABLES:
            continue
        por_rm.setdefault(fila.rm_codigo, []).append(fila.nota)

    integrados = 0
    for rm_codigo, notas in sorted(por_rm.items()):
        rm_id = mapeo.id_mapeado(db, ENT_REPRESENTANTE, pais_codigo, rm_codigo)
        rm = db.get(RepresentanteMedico, rm_id) if rm_id else None
        if rm is None:
            hallazgos.append(Hallazgo(
                "factevaluacionconocimiento", rm_codigo,
                f"El representante «{rm_codigo}» no está sincronizado; su nota "
                f"no se integró.", SEVERIDAD_ERROR))
            continue
        promedio = sum(notas, Decimal(0)) / len(notas)
        if _upsert_resultado(db, rm, ciclo_id, promedio):
            integrados += 1

    logger.info(f"Conocimientos (Mallén): {integrados} RM integrados en "
                f"{pais_codigo}/{ciclo_codigo}")
    return {"abortado": False, "rms_integrados": integrados,
            "ciclo_id": ciclo_id, "pais_codigo": pais_codigo}
```

- [ ] **Step 8: Correr los tests y confirmar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_conocimientos_integracion.py tests/test_examen_consolidacion_service.py -q`
Expected: PASS

- [ ] **Step 9: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/conocimientos_service.py backend/app/services/examen_consolidacion_service.py backend/tests/test_conocimientos_integracion.py backend/tests/test_examen_consolidacion_service.py
git commit -m "feat(conocimientos) integrador de notas de Mallen + puerta en la consolidacion de examenes"
```

---

### Task 5: Endpoints y pantalla

**Files:**
- Create: `backend/app/api/v1/routers/conocimientos.py`, `frontend/src/pages/conocimientos/Conocimientos.tsx`, `frontend/src/services/conocimientos.service.ts`
- Modify: `backend/app/api/v1/router.py`, `frontend/src/App.tsx`

**Interfaces:**
- Consumes: `fuente_indicador_service.{fuente_de, fijar_fuente, FUENTES, FuenteAjenaError}`; `conocimientos_service.{capturar_nota, corregir_nota, notas_del_ciclo, integrar_captura, integrar_conocimientos}`.
- Produces: `GET/PUT /conocimientos/fuente`, `GET /conocimientos/notas`, `POST /conocimientos/notas`, `PUT /conocimientos/notas/{nota_id}`, `POST /conocimientos/integrar`.

- [ ] **Step 1: Escribir el router**

Crear `backend/app/api/v1/routers/conocimientos.py`:

```python
"""Conocimientos: quién alimenta EVAL_CONOCIMIENTOS y la captura manual de notas.

Se gatea por rol —ADMIN, GERENTE_PRODUCTIVIDAD y CAPACITACION—, el mismo criterio
que `/integracion`: dar de alta un recurso en la matriz RBAC exigiría una
migración y, sin ella, quedaría denegado para todos.
"""
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.core.deps import get_current_active_user, require_roles
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.services import conocimientos_service as cs
from app.services import fuente_indicador_service as fuentes

router = APIRouter(prefix="/conocimientos", tags=["Conocimientos"])

RequireCaptura = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION))


class FuenteIn(BaseModel):
    pais_codigo: str
    fuente: str


class NotaIn(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    pais_codigo: str
    ciclo_id: int
    rm_id: int
    nota: Decimal
    fecha_evaluacion: date
    tema: str | None = None


class NotaEdit(BaseModel):
    nota: Decimal
    tema: str | None = None


@router.get("/fuente", summary="Quién alimenta EVAL_CONOCIMIENTOS en un país")
def ver_fuente(pais_codigo: str, db: Session = Depends(get_db),
               _: Usuario = RequireCaptura):
    return {"pais_codigo": pais_codigo,
            "fuente": fuentes.fuente_de(db, pais_codigo),
            "fuentes": list(fuentes.FUENTES)}


@router.put("/fuente", summary="Declarar quién alimenta EVAL_CONOCIMIENTOS")
def cambiar_fuente(datos: FuenteIn, db: Session = Depends(get_db),
                   usuario: Usuario = Depends(get_current_active_user)):
    """Los otros caminos consultan esto antes de escribir: cambiarlo decide cuál
    de los tres puede alimentar el indicador en ese país."""
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    try:
        fila = fuentes.fijar_fuente(db, datos.pais_codigo, datos.fuente, usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"pais_codigo": fila.pais_codigo, "fuente": fila.fuente}


@router.get("/notas", summary="Notas capturadas del ciclo, y a quién le faltan")
def listar_notas(pais_codigo: str, ciclo_id: int, db: Session = Depends(get_db),
                 _: Usuario = RequireCaptura):
    return cs.notas_del_ciclo(db, pais_codigo, ciclo_id)


@router.post("/notas", summary="Capturar una nota")
def crear_nota(datos: NotaIn, db: Session = Depends(get_db),
               usuario: Usuario = Depends(get_current_active_user)):
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    try:
        fila = cs.capturar_nota(db, datos.pais_codigo, datos.ciclo_id, datos.rm_id,
                                datos.nota, datos.fecha_evaluacion, datos.tema,
                                usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"id": fila.id}


@router.put("/notas/{nota_id}", summary="Corregir una nota capturada")
def editar_nota(nota_id: int, datos: NotaEdit, db: Session = Depends(get_db),
                usuario: Usuario = Depends(get_current_active_user)):
    """Corrige EDITANDO la fila. Para añadir otra nota del mismo RM se usa POST:
    la tabla no lleva UNIQUE y corregir insertando dejaría la nota vieja
    entrando al promedio."""
    if usuario.rol not in (Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.CAPACITACION):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Sin permiso.")
    try:
        cs.corregir_nota(db, nota_id, datos.nota, datos.tema, usuario.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc))
    db.commit()
    return {"ok": True}


@router.post("/integrar", summary="Integrar las notas capturadas al ciclo")
def integrar(pais_codigo: str, ciclo_id: int, db: Session = Depends(get_db),
             _: Usuario = RequireCaptura):
    try:
        return cs.integrar_captura(db, pais_codigo, ciclo_id)
    except fuentes.FuenteAjenaError as exc:
        raise HTTPException(status.HTTP_409_CONFLICT, str(exc))
```

En `backend/app/api/v1/router.py`, importar el router nuevo junto a los demás y registrarlo al final:

```python
api_router.include_router(conocimientos_router)  # Fuente unica de EVAL_CONOCIMIENTOS + captura manual
```

- [ ] **Step 2: Comprobar que las rutas quedan registradas**

Run:
```bash
cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print(sorted(r.path for r in app.routes if '/conocimientos' in r.path))"
```
Expected: las cinco rutas bajo `/api/v1/conocimientos`.

- [ ] **Step 3: Escribir el servicio del frontend**

Crear `frontend/src/services/conocimientos.service.ts`:

```typescript
/**
 * conocimientos.service.ts — Fuente de EVAL_CONOCIMIENTOS y captura de notas.
 * Rutas exactas del router `/conocimientos` (ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION).
 */
import { api } from './api';

export type FuenteConocimientos = 'EXAMEN_VISTA' | 'NOTA_EXTERNA' | 'CAPTURA_MANUAL';

export interface FuenteActual {
  pais_codigo: string;
  fuente: FuenteConocimientos;
  fuentes: FuenteConocimientos[];
}

export interface NotaCapturada {
  id: number; nota: string; tema: string | null;
  fecha_evaluacion: string; capturado_en: string;
}

export interface FilaNotas {
  rm_id: number; rm_codigo: string; rm_nombre: string;
  notas: NotaCapturada[]; promedio: string | null;
}

export interface ResultadoIntegracion {
  abortado: boolean; motivo?: string; rms_integrados: number;
}

export const verFuente = (paisCodigo: string) =>
  api.get<FuenteActual>('/conocimientos/fuente',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const cambiarFuente = (paisCodigo: string, fuente: FuenteConocimientos) =>
  api.put<{ pais_codigo: string; fuente: FuenteConocimientos }>(
    '/conocimientos/fuente', { pais_codigo: paisCodigo, fuente }).then((r) => r.data);

export const listarNotas = (paisCodigo: string, cicloId: number) =>
  api.get<FilaNotas[]>('/conocimientos/notas',
    { params: { pais_codigo: paisCodigo, ciclo_id: cicloId } }).then((r) => r.data);

export const capturarNota = (datos: {
  pais_codigo: string; ciclo_id: number; rm_id: number;
  nota: number; fecha_evaluacion: string; tema?: string | null;
}) => api.post<{ id: number }>('/conocimientos/notas', datos).then((r) => r.data);

export const corregirNota = (notaId: number, nota: number, tema: string | null) =>
  api.put<{ ok: boolean }>(`/conocimientos/notas/${notaId}`, { nota, tema })
    .then((r) => r.data);

export const integrarCaptura = (paisCodigo: string, cicloId: number) =>
  api.post<ResultadoIntegracion>('/conocimientos/integrar', null,
    { params: { pais_codigo: paisCodigo, ciclo_id: cicloId } }).then((r) => r.data);
```

- [ ] **Step 4: Escribir la pantalla**

Crear `frontend/src/pages/conocimientos/Conocimientos.tsx`:

```tsx
/**
 * Conocimientos — quién alimenta EVAL_CONOCIMIENTOS y captura manual de notas.
 *
 * Sustituye al Excel para este indicador. Los controles de captura se apagan
 * cuando el país no se alimenta de esta vía: la puerta que manda es la del
 * backend, pero descubrir el 409 DESPUÉS de teclear veinte notas es una forma
 * cara de enterarse.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Chip, MenuItem, Paper, Select, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { Edit, PlaylistAddCheck, Save } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  cambiarFuente, capturarNota, corregirNota, integrarCaptura, listarNotas,
  verFuente, type FuenteConocimientos,
} from '../../services/conocimientos.service';

const EXPLICACION: Record<FuenteConocimientos, string> = {
  EXAMEN_VISTA: 'Las notas salen de los exámenes de VISTA; Capacitación las consolida por ciclo. Esta pantalla queda de solo lectura.',
  NOTA_EXTERNA: 'Las notas las envía Laboratorio Mallén y entran por la integración. Esta pantalla queda de solo lectura.',
  CAPTURA_MANUAL: 'Las notas se capturan aquí y entran al ciclo con el botón "Integrar al ciclo".',
};

function mensajeError(e: unknown, respaldo: string): string {
  const det = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof det === 'string' && det ? det : respaldo;
}

export default function Conocimientos() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState<{ rm_id: number; nota: string; fecha: string; tema: string } | null>(null);
  const [editando, setEditando] = useState<{ id: number; nota: string; tema: string } | null>(null);

  const fuente = useQuery({
    queryKey: ['conocimientos-fuente', paisCodigo],
    queryFn: () => verFuente(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const notas = useQuery({
    queryKey: ['conocimientos-notas', paisCodigo, cicloId],
    queryFn: () => listarNotas(paisCodigo as string, cicloId as number),
    enabled: !!paisCodigo && !!cicloId,
  });

  const refrescar = () => qc.invalidateQueries({ queryKey: ['conocimientos-notas'] });

  const mutFuente = useMutation({
    mutationFn: (f: FuenteConocimientos) => cambiarFuente(paisCodigo as string, f),
    onSuccess: () => { setError(null); qc.invalidateQueries({ queryKey: ['conocimientos-fuente'] }); },
    onError: (e) => setError(mensajeError(e, 'No se pudo cambiar la fuente.')),
  });

  const mutCapturar = useMutation({
    mutationFn: () => capturarNota({
      pais_codigo: paisCodigo as string, ciclo_id: cicloId as number,
      rm_id: nuevo!.rm_id, nota: Number(nuevo!.nota),
      fecha_evaluacion: nuevo!.fecha, tema: nuevo!.tema || null,
    }),
    onSuccess: () => { setNuevo(null); setError(null); refrescar(); },
    onError: (e) => setError(mensajeError(e, 'No se pudo capturar la nota.')),
  });

  const mutCorregir = useMutation({
    mutationFn: () => corregirNota(editando!.id, Number(editando!.nota), editando!.tema || null),
    onSuccess: () => { setEditando(null); setError(null); refrescar(); },
    onError: (e) => setError(mensajeError(e, 'No se pudo corregir la nota.')),
  });

  const mutIntegrar = useMutation({
    mutationFn: () => integrarCaptura(paisCodigo as string, cicloId as number),
    onSuccess: (r) => {
      setError(null);
      setAviso(r.abortado
        ? `No se integró: ${r.motivo}.`
        : `${r.rms_integrados} representante(s) integrados al ciclo.`);
      refrescar();
    },
    onError: (e) => setError(mensajeError(e, 'No se pudo integrar.')),
  });

  if (!paisCodigo || !cicloId) {
    return <Alert severity="info" sx={{ m: 3 }}>
      Selecciona país y ciclo en el encabezado.
    </Alert>;
  }

  const esCaptura = fuente.data?.fuente === 'CAPTURA_MANUAL';

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 2 }}>Conocimientos</Typography>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="subtitle2" fontWeight={700}>
            Quién alimenta EVAL_CONOCIMIENTOS en {paisCodigo}
          </Typography>
          <Select size="small" sx={{ minWidth: 220 }}
            value={fuente.data?.fuente ?? ''}
            onChange={(e) => mutFuente.mutate(e.target.value as FuenteConocimientos)}>
            {(fuente.data?.fuentes ?? []).map((f) => (
              <MenuItem key={f} value={f}>{f}</MenuItem>
            ))}
          </Select>
        </Box>
        {fuente.data && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {EXPLICACION[fuente.data.fuente]}
          </Typography>
        )}
      </Paper>

      {fuente.data && !esCaptura && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          En {paisCodigo} el indicador lo alimenta «{fuente.data.fuente}»: aquí no
          se puede capturar ni integrar. Cambia la fuente arriba si esa es la decisión.
        </Alert>
      )}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {aviso && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setAviso(null)}>{aviso}</Alert>}

      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <Button variant="contained" startIcon={<PlaylistAddCheck />}
          disabled={!esCaptura || mutIntegrar.isPending}
          onClick={() => mutIntegrar.mutate()}>
          {mutIntegrar.isPending ? 'Integrando…' : 'Integrar al ciclo'}
        </Button>
      </Box>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Representante</TableCell>
              <TableCell>Notas del ciclo</TableCell>
              <TableCell align="right">Promedio</TableCell>
              <TableCell align="right">Capturar</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(notas.data ?? []).map((f) => (
              <TableRow key={f.rm_id} sx={{ opacity: f.notas.length ? 1 : 0.55 }}>
                <TableCell>
                  {f.rm_codigo} — {f.rm_nombre}
                  {!f.notas.length && <Chip size="small" label="falta" color="warning" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>
                  {f.notas.map((n) => (
                    <Box key={n.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {editando?.id === n.id ? (
                        <>
                          <TextField size="small" type="number" sx={{ width: 90 }}
                            value={editando.nota}
                            onChange={(e) => setEditando({ ...editando, nota: e.target.value })} />
                          <TextField size="small" sx={{ width: 140 }} placeholder="Tema"
                            value={editando.tema}
                            onChange={(e) => setEditando({ ...editando, tema: e.target.value })} />
                          <Button size="small" startIcon={<Save />}
                            disabled={mutCorregir.isPending}
                            onClick={() => mutCorregir.mutate()}>Guardar</Button>
                          <Button size="small" onClick={() => setEditando(null)}>Cancelar</Button>
                        </>
                      ) : (
                        <>
                          <Typography variant="body2">
                            {n.nota}{n.tema ? ` · ${n.tema}` : ''} · {n.fecha_evaluacion}
                          </Typography>
                          <Button size="small" startIcon={<Edit />} disabled={!esCaptura}
                            onClick={() => setEditando({ id: n.id, nota: String(n.nota), tema: n.tema ?? '' })}>
                            Corregir
                          </Button>
                        </>
                      )}
                    </Box>
                  ))}
                  {nuevo?.rm_id === f.rm_id && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                      <TextField size="small" type="number" sx={{ width: 90 }} label="Nota"
                        value={nuevo.nota} onChange={(e) => setNuevo({ ...nuevo, nota: e.target.value })} />
                      <TextField size="small" type="date" sx={{ width: 160 }}
                        value={nuevo.fecha} onChange={(e) => setNuevo({ ...nuevo, fecha: e.target.value })} />
                      <TextField size="small" sx={{ width: 140 }} label="Tema"
                        value={nuevo.tema} onChange={(e) => setNuevo({ ...nuevo, tema: e.target.value })} />
                      <Button size="small" variant="contained"
                        disabled={!nuevo.nota || mutCapturar.isPending}
                        onClick={() => mutCapturar.mutate()}>Añadir</Button>
                      <Button size="small" onClick={() => setNuevo(null)}>Cancelar</Button>
                    </Box>
                  )}
                </TableCell>
                <TableCell align="right">{f.promedio ?? '—'}</TableCell>
                <TableCell align="right">
                  <Button size="small" disabled={!esCaptura}
                    onClick={() => setNuevo({
                      rm_id: f.rm_id, nota: '', tema: '',
                      fecha: new Date().toISOString().slice(0, 10),
                    })}>
                    Añadir nota
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  );
}
```

Tres cosas de esta pantalla no son cosméticas y no deben "simplificarse":

- Los RM **sin nota** salen atenuados y con el `Chip` "falta". Sin eso el responsable no sabe cuándo terminó, que es la mitad de *"todo lo necesario para integrarlo al ciclo"*.
- **Corregir y añadir son botones distintos.** "Corregir" sale de una nota existente y llama al `PUT`; "Añadir nota" abre el formulario y llama al `POST`. Fusionarlos haría que una corrección insertara una fila y la nota vieja seguiría entrando al promedio.
- Los controles se apagan cuando la fuente no es `CAPTURA_MANUAL`, pero **la puerta que manda es la del backend**: esto solo evita que el usuario descubra el 409 después de teclear.

**Falta una cosa en ese código y hay que añadirla:** la tienda expone también `esSoloLectura` (`frontend/src/store/ciclo.store.ts:31`), que vale `true` cuando el ciclo en consulta no es el abierto. La convención del proyecto es que **los módulos de captura apagan sus controles cuando `esSoloLectura`** — ver §23 de `CLAUDE.md`. Añádelo:

```tsx
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);
  ...
  const puedeCapturar = esCaptura && !esSoloLectura;
```

y usa `puedeCapturar` en lugar de `esCaptura` en los tres `disabled` de los botones (integrar, corregir, añadir nota), con un `Alert` propio cuando `esSoloLectura` explique que se está mirando un ciclo que no es el de trabajo. Son dos motivos distintos para apagar lo mismo —fuente ajena y ciclo en consulta— y el operador necesita saber cuál de los dos le aplica.

En `frontend/src/App.tsx`, añadir el import perezoso junto a los demás y la ruta antes del catch-all:

```tsx
const Conocimientos = lazyWithReload(() => import('./pages/conocimientos/Conocimientos'));
```
```tsx
        <Route path="conocimientos" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','CAPACITACION']}><Conocimientos /></ProtectedRoute>} />
```

Añadir el ítem al `Sidebar` con los mismos roles.

- [ ] **Step 5: Comprobar que el frontend compila**

Run: `cd frontend && npm run build`
Expected: build sin errores de TypeScript

- [ ] **Step 6: Correr la suite completa del backend**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: PASS, sin regresiones

- [ ] **Step 7: Commit**

```bash
git add backend/app/api/v1/routers/conocimientos.py backend/app/api/v1/router.py frontend/src/services/conocimientos.service.ts frontend/src/pages/conocimientos/Conocimientos.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(conocimientos) endpoints y pantalla de fuente y captura de notas"
```
