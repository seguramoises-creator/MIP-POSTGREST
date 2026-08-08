# Sincronización de dimensiones Mallén → VISTA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Llevar las 9 dimensiones que Mallén deja en `ext` a los catálogos internos de VISTA, **adoptando** los registros que VISTA ya tiene en vez de duplicarlos.

**Architecture:** Una tabla de equivalencias `Config.MapeoExterno` como puente entre el código de Mallén y el id interno; una primitiva reutilizable de "buscar mapeo → adoptar por clave natural → crear" que usan los nueve sincronizadores; un orquestador que los corre en orden de dependencia; y dos endpoints en el router `/integracion` ya existente.

**Tech Stack:** Backend: Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, pytest sobre PostgreSQL real. Frontend: React 18 + TypeScript, MUI v6, TanStack Query v5.

## Global Constraints

- **PROHIBIDO tocar el esquema `ext`** (modelos `integracion_ext.py`, migración `0030`, SQL entregado a Mallén). Es contrato firmado con un tercero: solo se LEE de él.
- **PROHIBIDO modificar cualquier `Config.DIM_*` existente** (columnas, índices, constraints). La única tabla nueva es `Config.MapeoExterno`. El riesgo sobre datos reales de producción debe ser mínimo.
- **ADOPTAR antes que crear.** VISTA ya tiene datos cargados por Excel; una sincronización que solo cree duplicaría el maestro completo. El orden es: (1) ¿hay mapeo? actualizar; (2) ¿existe por clave natural? adoptar; (3) crear.
- **Nunca borra.** Un registro que desaparece de `ext` no se elimina ni se toca: hay hechos históricos apuntando a él. `activo` sí se sincroniza.
- **`DIM_Ciclo.cerrado` NUNCA se toca** (decisión del cliente). Si difiere del de `ext`, se emite hallazgo `aviso` y manda VISTA.
- **Los códigos que no caben se OMITEN, no se truncan** (`DIM_Gerente.codigo` y `DIM_RM.codigo` son `String(20)`; `ext` permite 30). Truncar crearía colisiones silenciosas.
- **Una fila mala no detiene la sincronización**: se registra un hallazgo y se sigue con la siguiente (mismo criterio que la validación del sub-proyecto 1).
- Los hallazgos de sincronización **NO se persisten**: se devuelven en la respuesta y se registran en el log. `Audit.IntegracionHallazgo` tiene `lote_id` NOT NULL con FK y una sincronización no pertenece a un lote.
- Orden de sincronización: `país → línea → gerente → representante → ciclo → especialidad → médico → farmacia → producto`.
- Roles del router: **ADMIN y GERENTE_PRODUCTIVIDAD** (gate por `require_roles`, NO por la matriz RBAC).
- Estilo backend: `Mapped[tipo]` + `mapped_column()`, servicios reciben `db: Session` y no tocan HTTP, `from loguru import logger`, español en docstrings.
- Referencias de patrón: `backend/app/services/integracion_validacion_service.py` (servicio del sub-proyecto 1), `backend/app/api/v1/routers/integracion.py` (router), `backend/tests/test_integracion_validacion.py` (fixtures de PostgreSQL real).

---

### Task 1: Modelo `Config.MapeoExterno` + migración

**Files:**
- Create: `backend/app/models/mapeo_externo.py`
- Modify: `backend/alembic/env.py`
- Create: `backend/alembic/versions/0033_mapeo_externo.py`

**Interfaces:**
- Produce (para Tasks 2-5): la clase `MapeoExterno` y las constantes de entidad `ENT_PAIS`, `ENT_LINEA`, `ENT_GERENTE`, `ENT_REPRESENTANTE`, `ENT_CICLO`, `ENT_ESPECIALIDAD`, `ENT_MEDICO`, `ENT_FARMACIA`, `ENT_PRODUCTO`, y la tupla `ENTIDADES` con las nueve en orden de sincronización.

- [ ] **Step 1: Crear el modelo**

Crear `backend/app/models/mapeo_externo.py`:

```python
"""Equivalencias entre los códigos de Laboratorio Mallén y los ids de VISTA.

POR QUÉ UNA TABLA Y NO UNA COLUMNA `codigo_externo` EN CADA DIM_*
------------------------------------------------------------------
1. No toca ninguna tabla interna existente. Producción es un piloto con datos
   reales; añadir columnas a nueve catálogos vivos es riesgo que no hace falta
   correr.
2. Funciona igual para las dimensiones que tienen código propio (DIM_RM) y para
   las que no (DIM_Especialidad se identifica por nombre, DIM_Ciclo por
   país+año+número, DIM_Farmacia no tiene código).
3. Deja el mapeo visible y corregible en UN solo sitio cuando algo se empareje
   mal, en vez de repartido por nueve tablas.
4. El identificador de un tercero no queda al alcance del resto del sistema,
   que podría acoplarse a él por accidente.

`id_interno` NO lleva clave foránea: apunta a nueve tablas distintas según
`entidad`. La integridad la mantiene el servicio, y un mapeo cuyo registro
interno fue borrado a mano se reconstruye solo (ver `integracion_mapeo`).
"""
from datetime import datetime, timezone

from sqlalchemy import DateTime, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base

ENT_PAIS = "pais"
ENT_LINEA = "linea"
ENT_GERENTE = "gerente"
ENT_REPRESENTANTE = "representante"
ENT_CICLO = "ciclo"
ENT_ESPECIALIDAD = "especialidad"
ENT_MEDICO = "medico"
ENT_FARMACIA = "farmacia"
ENT_PRODUCTO = "producto"

#: En orden de dependencia: cada una resuelve claves foráneas contra las
#: anteriores, así que sincronizarlas en otro orden dejaría referencias sueltas.
ENTIDADES: tuple[str, ...] = (
    ENT_PAIS, ENT_LINEA, ENT_GERENTE, ENT_REPRESENTANTE, ENT_CICLO,
    ENT_ESPECIALIDAD, ENT_MEDICO, ENT_FARMACIA, ENT_PRODUCTO,
)


class MapeoExterno(Base):
    """Un código de Mallén ↔ un id de VISTA, por entidad y país."""
    __tablename__ = "MapeoExterno"
    __table_args__ = (
        UniqueConstraint("entidad", "pais_codigo", "codigo_externo",
                         name="UQ_MapeoExterno_clave"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    entidad: Mapped[str] = mapped_column(String(30), nullable=False)
    # Cadena vacía —no NULL— para las entidades sin país (especialidad): en un
    # UNIQUE de PostgreSQL dos NULL se consideran distintos, así que permitiría
    # duplicar el mismo código.
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False, default="")
    codigo_externo: Mapped[str] = mapped_column(String(60), nullable=False)
    id_interno: Mapped[int] = mapped_column(Integer, nullable=False)
    sincronizado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), nullable=False)
```

- [ ] **Step 2: Registrar el modelo en Alembic**

`backend/app/models/__init__.py` está VACÍO en este repo; el registro real de modelos vive en `backend/alembic/env.py`, que importa un módulo por línea. Añade `mapeo_externo` a ese import siguiendo exactamente el patrón de la línea vecina de `integracion_hallazgo`.

- [ ] **Step 3: Crear la migración**

Crear `backend/alembic/versions/0033_mapeo_externo.py`:

```python
"""Config.MapeoExterno — equivalencias entre codigos de Mallen e ids de VISTA.

Ninguna DIM_* se modifica: el mapeo vive en su propia tabla para no tocar
catalogos con datos reales en produccion.

Revision ID: 0033_mapeo_externo
Revises: 0032_integracion_hallazgo
Create Date: 2026-08-08
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0033_mapeo_externo"
down_revision: Union[str, Sequence[str], None] = "0032_integracion_hallazgo"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "MapeoExterno",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("entidad", sa.String(length=30), nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.Column("codigo_externo", sa.String(length=60), nullable=False),
        sa.Column("id_interno", sa.Integer(), nullable=False),
        sa.Column("sincronizado_en", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("entidad", "pais_codigo", "codigo_externo",
                            name="UQ_MapeoExterno_clave"),
        schema="Config",
    )


def downgrade() -> None:
    op.drop_table("MapeoExterno", schema="Config")
```

- [ ] **Step 4: Verificar que aplica y que nada se rompe**

Run: `cd backend && ./venv/Scripts/python.exe -m alembic upgrade head`
Expected: aplica `0033_mapeo_externo` sin error.

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_ext.py tests/test_integracion_validacion.py -v`
Expected: 41 passed (el contrato `ext` y la validación siguen intactos).

- [ ] **Step 5: Commit**

```bash
git add backend/app/models/mapeo_externo.py backend/alembic/env.py backend/alembic/versions/0033_mapeo_externo.py
git commit -m "feat(integracion) Config.MapeoExterno: equivalencias entre codigos de Mallen e ids de VISTA"
```

---

### Task 2: Primitiva de mapeo — buscar, adoptar, crear

El corazón del sub-proyecto: la función que evita duplicar el maestro.

**Files:**
- Create: `backend/app/services/integracion_mapeo.py`
- Test: `backend/tests/test_integracion_mapeo.py`

**Interfaces:**
- Consumes: `MapeoExterno` y las constantes de entidad de Task 1.
- Produce (para Tasks 3-4):
  - `RESULTADO_ACTUALIZADO`, `RESULTADO_ADOPTADO`, `RESULTADO_CREADO` (str)
  - `resolver(db, entidad, pais_codigo, codigo_externo, modelo, buscar_natural, crear) -> tuple[object, str]` — devuelve `(registro_interno, resultado)`. `buscar_natural` es un callable sin argumentos que devuelve el registro existente o `None`; `crear` es un callable sin argumentos que devuelve el registro nuevo ya añadido a la sesión y con `id` asignado (debe hacer `db.flush()`).
  - `id_mapeado(db, entidad, pais_codigo, codigo_externo) -> int | None` — para resolver FK entre dimensiones ya sincronizadas.

- [ ] **Step 1: Escribir el archivo de tests**

Crear `backend/tests/test_integracion_mapeo.py`:

```python
"""La primitiva de mapeo: buscar, ADOPTAR, crear.

El caso que estas pruebas cuidan es el de adopción: VISTA ya tiene su maestro
cargado por Excel, sin ningún identificador de Mallén. Si la sincronización solo
supiera crear, la primera corrida duplicaría cada representante y cada médico.

Necesita PostgreSQL real: se prueba contra las tablas y sus índices únicos.
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
from app.models.dimensiones import Linea, Pais
from app.models.mapeo_externo import ENT_LINEA, MapeoExterno
from app.services import integracion_mapeo as mapeo

BD_PRUEBA = "vista_test_mapeo"


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
    for tabla in ('"Config"."MapeoExterno"', '"Config"."DIM_Linea"',
                  '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def pais(db):
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.commit()
    return "DO"


def _crear_linea(db, codigo: str, nombre: str):
    """Callable de creación: añade, hace flush y devuelve el registro con id."""
    def _hacer():
        linea = Linea(pais_codigo="DO", codigo=codigo, nombre=nombre)
        db.add(linea)
        db.flush()
        return linea
    return _hacer


def _buscar_linea(db, codigo: str):
    def _hacer():
        return (db.query(Linea)
                .filter(Linea.pais_codigo == "DO", Linea.codigo == codigo)
                .first())
    return _hacer


def test_adopta_el_registro_que_ya_existe_en_vista(db, pais):
    """El caso que da sentido a todo: VISTA ya tenía la línea cargada por Excel.

    Sin adopción, la sincronización crearía una segunda línea con el mismo
    código y el maestro quedaría duplicado.
    """
    existente = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(existente)
    db.commit()

    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_ADOPTADO
    assert registro.id == existente.id
    assert db.query(Linea).count() == 1          # NO se duplicó
    assert db.query(MapeoExterno).count() == 1


def test_crea_cuando_no_existe(db, pais):
    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "DERM", Linea,
        _buscar_linea(db, "DERM"), _crear_linea(db, "DERM", "Dermatología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_CREADO
    assert registro.codigo == "DERM"
    assert db.query(Linea).count() == 1


def test_segunda_llamada_actualiza_por_el_mapeo(db, pais):
    """Idempotencia: la segunda vez ya hay mapeo, así que ni adopta ni crea."""
    mapeo.resolver(db, ENT_LINEA, "DO", "CARD", Linea,
                   _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    registro, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_ACTUALIZADO
    assert db.query(Linea).count() == 1
    assert db.query(MapeoExterno).count() == 1


def test_mapeo_huerfano_se_reconstruye(db, pais):
    """Si alguien borró el registro interno a mano, el mapeo apunta al vacío.

    Un mapeo es un dato derivado: se descarta y se vuelve a resolver, en vez de
    dejar la sincronización bloqueada para siempre.
    """
    registro, _ = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()
    db.query(Linea).filter(Linea.id == registro.id).delete()
    db.commit()

    nuevo, resultado = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert resultado == mapeo.RESULTADO_CREADO
    assert db.query(MapeoExterno).count() == 1
    assert db.query(MapeoExterno).one().id_interno == nuevo.id


def test_id_mapeado_devuelve_el_id_interno(db, pais):
    registro, _ = mapeo.resolver(
        db, ENT_LINEA, "DO", "CARD", Linea,
        _buscar_linea(db, "CARD"), _crear_linea(db, "CARD", "Cardiología"))
    db.commit()

    assert mapeo.id_mapeado(db, ENT_LINEA, "DO", "CARD") == registro.id
    assert mapeo.id_mapeado(db, ENT_LINEA, "DO", "NO-EXISTE") is None
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_mapeo.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.integracion_mapeo'`.
(Si no hay PostgreSQL alcanzable se SALTAN — anótalo y continúa.)

- [ ] **Step 3: Implementar la primitiva**

Crear `backend/app/services/integracion_mapeo.py`:

```python
"""Buscar, ADOPTAR o crear: la primitiva que usan los nueve sincronizadores.

EL PASO QUE IMPORTA ES LA ADOPCIÓN
-----------------------------------
VISTA lleva meses en piloto con su maestro cargado por Excel, y esos registros
no tienen ningún identificador de Mallén. Una sincronización que solo supiera
«buscar por código externo; si no está, crear» duplicaría cada representante,
cada médico y cada gerente en la primera corrida.

Por eso el orden es: (1) ¿ya hay mapeo? actualizar; (2) ¿existe por su clave
natural? adoptarlo creando el mapeo; (3) recién entonces, crear.
"""
from datetime import datetime, timezone

from sqlalchemy.orm import Session

from app.models.mapeo_externo import MapeoExterno

RESULTADO_ACTUALIZADO = "actualizado"
RESULTADO_ADOPTADO = "adoptado"
RESULTADO_CREADO = "creado"


def _buscar_mapeo(db: Session, entidad: str, pais_codigo: str,
                  codigo_externo: str) -> MapeoExterno | None:
    return (db.query(MapeoExterno)
            .filter(MapeoExterno.entidad == entidad,
                    MapeoExterno.pais_codigo == pais_codigo,
                    MapeoExterno.codigo_externo == codigo_externo)
            .first())


def id_mapeado(db: Session, entidad: str, pais_codigo: str,
               codigo_externo: str) -> int | None:
    """El id interno de un código externo ya sincronizado, o None.

    Es lo que usan las dimensiones para resolver sus claves foráneas contra las
    que se sincronizaron antes (un representante contra su gerente, por ejemplo).
    """
    m = _buscar_mapeo(db, entidad, pais_codigo, codigo_externo)
    return m.id_interno if m else None


def resolver(db: Session, entidad: str, pais_codigo: str, codigo_externo: str,
             modelo, buscar_natural, crear) -> tuple[object, str]:
    """Devuelve `(registro_interno, resultado)` y deja el mapeo al día.

    `buscar_natural` y `crear` son callables sin argumentos: cada dimensión sabe
    cuál es su clave natural y cómo construirse, y esta función no necesita
    saberlo. `crear` debe dejar el registro en la sesión con su `id` asignado
    (un `db.flush()` basta).

    No hace commit: el llamador decide la transacción, para que una dimensión
    entera se confirme junta.
    """
    m = _buscar_mapeo(db, entidad, pais_codigo, codigo_externo)
    if m is not None:
        registro = db.get(modelo, m.id_interno)
        if registro is not None:
            m.sincronizado_en = datetime.now(timezone.utc)
            return registro, RESULTADO_ACTUALIZADO
        # Mapeo huérfano: el registro interno se borró a mano. El mapeo es un
        # dato derivado, así que se descarta y se resuelve de nuevo en vez de
        # dejar esta fila bloqueada para siempre.
        db.delete(m)
        db.flush()

    existente = buscar_natural()
    if existente is not None:
        db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                            codigo_externo=codigo_externo,
                            id_interno=existente.id))
        db.flush()
        return existente, RESULTADO_ADOPTADO

    nuevo = crear()
    db.add(MapeoExterno(entidad=entidad, pais_codigo=pais_codigo,
                        codigo_externo=codigo_externo, id_interno=nuevo.id))
    db.flush()
    return nuevo, RESULTADO_CREADO
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_mapeo.py -v`
Expected: 5 passed (o SKIPPED si no hay PostgreSQL).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_mapeo.py backend/tests/test_integracion_mapeo.py
git commit -m "feat(integracion) primitiva de mapeo: buscar, adoptar o crear"
```

---

### Task 3: Sincronizadores troncales — país, línea, gerente, representante, ciclo

**Files:**
- Create: `backend/app/services/integracion_dimensiones_service.py`
- Test: `backend/tests/test_integracion_dimensiones.py`

**Interfaces:**
- Consumes: `resolver`, `id_mapeado`, los `RESULTADO_*` de Task 2; las constantes de entidad de Task 1.
- Produce (para Tasks 4-5):
  - `class Hallazgo` (dataclass): `entidad`, `codigo_externo`, `problema`, `severidad`.
  - `class Conteo` (dataclass): `entidad`, `en_ext`, `creados`, `adoptados`, `actualizados`, `omitidos`.
  - `sincronizar_pais(db, pais_codigo, hallazgos) -> Conteo` y sus equivalentes `sincronizar_linea`, `sincronizar_gerente`, `sincronizar_representante`, `sincronizar_ciclo` — todas con la misma firma: reciben la lista `hallazgos` y le añaden lo que encuentren.
  - `SEVERIDAD_ERROR = "error"`, `SEVERIDAD_AVISO = "aviso"`.

- [ ] **Step 1: Escribir el archivo de tests con el escenario base**

Crear `backend/tests/test_integracion_dimensiones.py`:

```python
"""Sincronización de dimensiones `ext` → catálogos internos de VISTA.

Lo que estas pruebas cuidan por encima de todo: que sincronizar NO duplique el
maestro que VISTA ya tiene cargado, y que no toque el estado `cerrado` de un
ciclo (del que dependen recálculos y premios).

Necesita PostgreSQL real: cruza dos esquemas con claves compuestas e índices
únicos.
"""
from datetime import date

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
from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.services import integracion_dimensiones_service as dim

BD_PRUEBA = "vista_test_dimensiones"


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
    # Hijos antes que padres.
    for tabla in ('"Config"."MapeoExterno"', '"Config"."DIM_RM"',
                  '"Config"."DIM_Gerente"', '"Config"."DIM_Ciclo"',
                  '"Config"."DIM_Linea"', "ext.dimrepresentante",
                  "ext.dimgerente", "ext.dimciclo", "ext.dimlinea",
                  "ext.dimpais", '"Config"."DIM_Pais"'):
        s.execute(text(f"DELETE FROM {tabla}"))
    s.commit()
    yield s
    s.close()


@pytest.fixture
def base(db):
    """País y línea en AMBOS lados: el punto de partida de todo el resto."""
    db.add(Pais(codigo="DO", nombre="República Dominicana"))
    db.add(ExtDimPais(pais_codigo="DO", nombre="República Dominicana", activo=True))
    db.flush()
    db.add(ExtDimLinea(pais_codigo="DO", linea_codigo="CARD",
                       nombre="Cardiología", activo=True))
    db.commit()
    return db


def test_adopta_el_representante_que_vista_ya_tenia(base):
    """El caso de la primera corrida en producción.

    VISTA lleva el piloto con 48 representantes cargados por Excel. Si la
    sincronización no los adoptara, quedarían 96.
    """
    db = base
    linea = Linea(pais_codigo="DO", codigo="CARD", nombre="Cardiología")
    db.add(linea)
    db.flush()
    db.add(RepresentanteMedico(pais_codigo="DO", linea_id=linea.id,
                               codigo="VM01", nombre="Representante Uno"))
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM01",
                               linea_codigo="CARD", nombre="Representante Uno",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1     # NO se duplicó


def test_crea_el_representante_que_no_existia(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo Representante",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    rm = db.query(RepresentanteMedico).one()
    assert rm.codigo == "VM99"
    assert rm.linea_id is not None      # resolvió la FK contra la línea mapeada


def test_no_toca_el_estado_cerrado_del_ciclo(base):
    """Decisión del cliente: el abrir/cerrar de un ciclo es de VISTA.

    De `cerrado` dependen los recálculos y los premios; que un envío externo
    reabra un ciclo cerrado dispararía cálculos sobre datos históricos.
    """
    db = base
    db.add(Ciclo(pais_codigo="DO", anio=2026, numero=1, nombre="Ciclo 1",
                 fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                 dias_laborables=22, cerrado=False))
    db.add(ExtDimCiclo(pais_codigo="DO", ciclo_codigo="C01-2026", anio=2026,
                       numero=1, nombre="Ciclo 1 Mallén",
                       fecha_inicio=date(2026, 1, 1), fecha_fin=date(2026, 1, 31),
                       dias_laborables=20, cerrado=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_ciclo(db, "DO", hallazgos)
    db.commit()

    ciclo = db.query(Ciclo).one()
    assert ciclo.cerrado is False                  # sigue abierto: manda VISTA
    assert ciclo.dias_laborables == 20             # lo demás sí se sincroniza
    assert conteo.adoptados == 1
    assert any(h.severidad == dim.SEVERIDAD_AVISO for h in hallazgos)


def test_codigo_demasiado_largo_se_omite_sin_truncar(base):
    """DIM_Gerente.codigo es String(20) y ext permite 30.

    Truncar juntaría dos códigos distintos que compartan los primeros 20
    caracteres, que es peor que no cargar la fila.
    """
    db = base
    db.add(ExtDimGerente(pais_codigo="DO",
                         gerente_codigo="GER-DISTRITO-NORTE-2026-A",
                         nombre="Gerente Norte", tipo="DISTRITO", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_gerente(db, "DO", hallazgos)
    db.commit()

    assert conteo.omitidos == 1
    assert conteo.creados == 0
    assert db.query(Gerente).count() == 0
    assert any(h.severidad == dim.SEVERIDAD_ERROR for h in hallazgos)


def test_sincronizar_dos_veces_no_duplica(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo",
                               activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_linea(db, "DO", hallazgos)
    dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    conteo = dim.sincronizar_representante(db, "DO", hallazgos)
    db.commit()

    assert conteo.actualizados == 1
    assert conteo.creados == 0
    assert db.query(RepresentanteMedico).count() == 1
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py -v`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.integracion_dimensiones_service'`.

- [ ] **Step 3: Implementar los cinco sincronizadores troncales**

Crear `backend/app/services/integracion_dimensiones_service.py`:

```python
"""Sincroniza las dimensiones que Mallén deja en `ext` con los catálogos de VISTA.

DOS REGLAS QUE NO SE NEGOCIAN
------------------------------
1. **Adoptar antes que crear.** VISTA lleva el piloto con su maestro cargado por
   Excel; sincronizar sin adoptar lo duplicaría entero. Lo resuelve
   `integracion_mapeo.resolver`.
2. **Nunca borrar.** Un registro que desaparece de `ext` conserva hechos
   históricos apuntándole. Se marca inactivo, no se elimina.

Una fila mala no detiene la sincronización: se anota un `Hallazgo` y se sigue,
mismo criterio que la validación de lotes (§7.1 del contrato).
"""
from dataclasses import dataclass, field

from loguru import logger
from sqlalchemy.orm import Session

from app.models.dimensiones import Ciclo, Gerente, Linea, Pais, RepresentanteMedico
from app.models.integracion_ext import (
    ExtDimCiclo, ExtDimGerente, ExtDimLinea, ExtDimPais, ExtDimRepresentante,
)
from app.models.mapeo_externo import (
    ENT_CICLO, ENT_GERENTE, ENT_LINEA, ENT_PAIS, ENT_REPRESENTANTE,
)
from app.services import integracion_mapeo as mapeo

SEVERIDAD_ERROR = "error"
SEVERIDAD_AVISO = "aviso"


@dataclass
class Hallazgo:
    entidad: str
    codigo_externo: str
    problema: str
    severidad: str


@dataclass
class Conteo:
    entidad: str
    en_ext: int = 0
    creados: int = 0
    adoptados: int = 0
    actualizados: int = 0
    omitidos: int = 0

    def anotar(self, resultado: str) -> None:
        if resultado == mapeo.RESULTADO_CREADO:
            self.creados += 1
        elif resultado == mapeo.RESULTADO_ADOPTADO:
            self.adoptados += 1
        else:
            self.actualizados += 1


def _cabe(valor: str, largo: int) -> bool:
    return len(valor) <= largo


def _omitir_por_largo(conteo: Conteo, hallazgos: list, entidad: str,
                      codigo: str, columna: str, largo: int) -> None:
    """Un código que no cabe se omite, NO se trunca: dos códigos distintos que
    compartan los primeros N caracteres colapsarían en uno solo."""
    conteo.omitidos += 1
    hallazgos.append(Hallazgo(
        entidad, codigo,
        f"El código excede los {largo} caracteres de {columna}; la fila se omitió.",
        SEVERIDAD_ERROR))


def sincronizar_pais(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """El país es la raíz: sin él ninguna otra dimensión resuelve."""
    conteo = Conteo(ENT_PAIS)
    filas = (db.query(ExtDimPais)
             .filter(ExtDimPais.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            return db.query(Pais).filter(Pais.codigo == f.pais_codigo).first()

        def _crear(f=fila):
            nuevo = Pais(codigo=f.pais_codigo, nombre=f.nombre,
                         moneda=f.moneda, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_PAIS, pais_codigo, fila.pais_codigo, Pais, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.moneda = fila.moneda
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def sincronizar_linea(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    conteo = Conteo(ENT_LINEA)
    filas = (db.query(ExtDimLinea)
             .filter(ExtDimLinea.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.linea_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_LINEA, fila.linea_codigo,
                              "DIM_Linea.codigo", 20)
            continue

        def _buscar(f=fila):
            return (db.query(Linea)
                    .filter(Linea.pais_codigo == f.pais_codigo,
                            Linea.codigo == f.linea_codigo).first())

        def _crear(f=fila):
            nuevo = Linea(pais_codigo=f.pais_codigo, codigo=f.linea_codigo,
                          nombre=f.nombre, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_LINEA, pais_codigo, fila.linea_codigo, Linea, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def sincronizar_gerente(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`DIM_Gerente.codigo` es único GLOBAL, mientras que en `ext` lo es por
    país: dos países con el mismo código colisionan y el segundo se omite."""
    conteo = Conteo(ENT_GERENTE)
    filas = (db.query(ExtDimGerente)
             .filter(ExtDimGerente.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.gerente_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_GERENTE, fila.gerente_codigo,
                              "DIM_Gerente.codigo", 20)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)

        def _buscar(f=fila):
            return db.query(Gerente).filter(Gerente.codigo == f.gerente_codigo).first()

        def _crear(f=fila, lid=linea_id):
            nuevo = Gerente(pais_codigo=f.pais_codigo, codigo=f.gerente_codigo,
                            nombre=f.nombre, tipo=f.tipo, email=f.email,
                            linea_id=lid, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        existente = db.query(Gerente).filter(
            Gerente.codigo == fila.gerente_codigo).first()
        if existente is not None and existente.pais_codigo != pais_codigo:
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                ENT_GERENTE, fila.gerente_codigo,
                f"El código ya existe en el país {existente.pais_codigo} y "
                f"DIM_Gerente.codigo es único global; la fila se omitió.",
                SEVERIDAD_ERROR))
            continue

        registro, resultado = mapeo.resolver(
            db, ENT_GERENTE, pais_codigo, fila.gerente_codigo, Gerente,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.tipo = fila.tipo
        registro.email = fila.email
        registro.activo = fila.activo
        if linea_id is not None:
            registro.linea_id = linea_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_representante(db: Session, pais_codigo: str,
                              hallazgos: list) -> Conteo:
    """`DIM_RM.linea_id` es NOT NULL: sin línea resuelta la fila se omite."""
    conteo = Conteo(ENT_REPRESENTANTE)
    filas = (db.query(ExtDimRepresentante)
             .filter(ExtDimRepresentante.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.rm_codigo, 20):
            _omitir_por_largo(conteo, hallazgos, ENT_REPRESENTANTE, fila.rm_codigo,
                              "DIM_RM.codigo", 20)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)
        if linea_id is None:
            conteo.omitidos += 1
            hallazgos.append(Hallazgo(
                ENT_REPRESENTANTE, fila.rm_codigo,
                f"No se pudo resolver la línea «{fila.linea_codigo}», que es "
                f"obligatoria en DIM_RM; la fila se omitió.", SEVERIDAD_ERROR))
            continue
        gerente_id = (mapeo.id_mapeado(db, ENT_GERENTE, pais_codigo,
                                       fila.gerente_codigo)
                      if fila.gerente_codigo else None)

        def _buscar(f=fila):
            return (db.query(RepresentanteMedico)
                    .filter(RepresentanteMedico.codigo == f.rm_codigo).first())

        def _crear(f=fila, lid=linea_id, gid=gerente_id):
            nuevo = RepresentanteMedico(
                pais_codigo=f.pais_codigo, codigo=f.rm_codigo, nombre=f.nombre,
                linea_id=lid, gerente_id=gid, cedula=f.cedula, email=f.email,
                zona=f.zona, fecha_ingreso=f.fecha_ingreso, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_REPRESENTANTE, pais_codigo, fila.rm_codigo,
            RepresentanteMedico, _buscar, _crear)
        registro.nombre = fila.nombre
        registro.linea_id = linea_id
        registro.cedula = fila.cedula
        registro.email = fila.email
        registro.zona = fila.zona
        registro.fecha_ingreso = fila.fecha_ingreso
        registro.activo = fila.activo
        if gerente_id is not None:
            registro.gerente_id = gerente_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_ciclo(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """El ciclo se identifica por (país, año, número): `DIM_Ciclo` no tiene código.

    `cerrado` NO se sincroniza NUNCA (decisión del cliente): de él dependen los
    recálculos y los premios, y un envío externo no debe reabrir un ciclo cerrado
    ni cerrar el que está en curso. Si difiere, se avisa y manda VISTA.
    """
    conteo = Conteo(ENT_CICLO)
    filas = (db.query(ExtDimCiclo)
             .filter(ExtDimCiclo.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            return (db.query(Ciclo)
                    .filter(Ciclo.pais_codigo == f.pais_codigo,
                            Ciclo.anio == f.anio, Ciclo.numero == f.numero)
                    .first())

        def _crear(f=fila):
            nuevo = Ciclo(pais_codigo=f.pais_codigo, anio=f.anio, numero=f.numero,
                          nombre=f.nombre or f.ciclo_codigo,
                          nombre_canonico=f.ciclo_codigo,
                          fecha_inicio=f.fecha_inicio, fecha_fin=f.fecha_fin,
                          dias_laborables=f.dias_laborables, cerrado=False)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_CICLO, pais_codigo, fila.ciclo_codigo, Ciclo, _buscar, _crear)
        registro.nombre = fila.nombre or fila.ciclo_codigo
        registro.fecha_inicio = fila.fecha_inicio
        registro.fecha_fin = fila.fecha_fin
        registro.dias_laborables = fila.dias_laborables
        if not registro.nombre_canonico:
            registro.nombre_canonico = fila.ciclo_codigo
        if fila.cerrado != registro.cerrado:
            hallazgos.append(Hallazgo(
                ENT_CICLO, fila.ciclo_codigo,
                f"El ciclo viene como cerrado={fila.cerrado} y en VISTA está "
                f"cerrado={registro.cerrado}. El estado del ciclo lo decide "
                f"VISTA: no se modificó.", SEVERIDAD_AVISO))
        conteo.anotar(resultado)
    return conteo
```

- [ ] **Step 4: Correr los tests para verificar que pasan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py -v`
Expected: 5 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_dimensiones_service.py backend/tests/test_integracion_dimensiones.py
git commit -m "feat(integracion) sincronizar pais, linea, gerente, representante y ciclo"
```

---

### Task 4: Sincronizadores de maestros — especialidad, médico, farmacia, producto

**Files:**
- Modify: `backend/app/services/integracion_dimensiones_service.py`
- Test: `backend/tests/test_integracion_dimensiones.py`

**Interfaces:**
- Consumes: `Hallazgo`, `Conteo`, `SEVERIDAD_*`, `_cabe`, `_omitir_por_largo` de Task 3.
- Produce (para Task 5): `sincronizar_especialidad`, `sincronizar_medico`, `sincronizar_farmacia`, `sincronizar_producto`, todas con la firma `(db, pais_codigo, hallazgos) -> Conteo`.

- [ ] **Step 1: Añadir los tests al final del archivo de tests**

Añade primero estos imports a los que ya existen en el archivo:
```python
from app.models.dimensiones import (
    CentroMedico, Especialidad, Farmacia, Medico, Municipio, Producto, Provincia,
)
from app.models.integracion_ext import (
    ExtDimEspecialidad, ExtDimFarmacia, ExtDimMedico, ExtDimProducto,
)
```
Y añade estas tablas al inicio de la lista de limpieza del fixture `db` (hijos antes que padres):
```python
'"Config"."DIM_Medico"', '"Config"."DIM_CentroMedico"',
'"Config"."DIM_Municipio"', '"Config"."DIM_Provincia"',
'"Config"."DIM_Farmacia"', '"Config"."DIM_Producto"',
'"Config"."DIM_Especialidad"', "ext.dimmedico", "ext.dimfarmacia",
"ext.dimproducto", "ext.dimespecialidad",
```

Tests nuevos:

```python
def test_especialidad_se_adopta_por_nombre(base):
    """DIM_Especialidad no tiene código: su identidad es el nombre."""
    db = base
    db.add(Especialidad(nombre="Cardiología"))
    db.add(ExtDimEspecialidad(especialidad_codigo="CARD", nombre="cardiología",
                              activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_especialidad(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Especialidad).count() == 1     # no duplicó por may/minúsculas


def test_medico_crea_sus_catalogos_auxiliares(base):
    """`ext` trae centro, provincia y municipio como TEXTO; DIM_Medico los
    referencia por FK. Se crean al vuelo en vez de descartar el dato."""
    db = base
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", especialidad_codigo=None,
                        centro_trabajo="Clínica Central", provincia="Santo Domingo",
                        municipio="Distrito Nacional", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    medico = db.query(Medico).one()
    assert medico.provincia_id is not None
    assert medico.municipio_id is not None
    assert medico.centro_medico_id is not None
    assert db.query(Provincia).one().nombre == "Santo Domingo"
    assert db.query(Municipio).one().nombre == "Distrito Nacional"
    assert db.query(CentroMedico).one().nombre == "Clínica Central"


def test_medico_se_adopta_por_exequatur(base):
    """Si el código no coincide pero el exequátur sí, es la misma persona: el
    exequátur es el identificador profesional único."""
    db = base
    db.add(Medico(pais_codigo="DO", codigo="VIEJO-01", nombre="Doctor Uno",
                  exequatur="EX-123"))
    db.add(ExtDimMedico(pais_codigo="DO", medico_codigo="MD01",
                        nombre="Doctor Uno", exequatur="EX-123", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_medico(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    assert db.query(Medico).count() == 1


def test_farmacia_se_crea_como_maestro_oficial(base):
    """Viene del sistema oficial, no de un VM pidiendo alta: entra aprobada y
    con origen CONFIG. `direccion` y `encargado` son NOT NULL y `ext` no los
    envía, así que quedan vacíos para completarse en VISTA."""
    db = base
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    assert conteo.creados == 1
    f = db.query(Farmacia).one()
    assert f.origen == "CONFIG"
    assert f.estado == "APROBADA"
    assert f.nombre_completo == "Farmacia Central"


def test_farmacia_no_pisa_lo_que_vista_completo(base):
    """`direccion` y `encargado` los enriquece VISTA y `ext` no los conoce."""
    db = base
    db.add(ExtDimFarmacia(pais_codigo="DO", farmacia_codigo="FAR01",
                          nombre="Farmacia Central", activo=True))
    db.commit()
    hallazgos = []
    dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()
    f = db.query(Farmacia).one()
    f.direccion = "Av. Principal 100"
    f.encargado = "Ana Pérez"
    db.commit()

    dim.sincronizar_farmacia(db, "DO", hallazgos)
    db.commit()

    f = db.query(Farmacia).one()
    assert f.direccion == "Av. Principal 100"
    assert f.encargado == "Ana Pérez"


def test_producto_se_sincroniza_sin_pisar_campos_de_vista(base):
    """`area_terapeutica` y compañía son de VISTA; `ext` no los conoce."""
    db = base
    db.add(Producto(codigo="ONCX-301", nombre="Producto Viejo",
                    area_terapeutica="Oncología"))
    db.add(ExtDimProducto(pais_codigo="DO", producto_codigo="ONCX-301",
                          nombre="Producto Nuevo", activo=True))
    db.commit()
    hallazgos = []

    conteo = dim.sincronizar_producto(db, "DO", hallazgos)
    db.commit()

    assert conteo.adoptados == 1
    p = db.query(Producto).one()
    assert p.nombre == "Producto Nuevo"            # sí se sincroniza
    assert p.area_terapeutica == "Oncología"       # no se pisa
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py -k "especialidad or medico or farmacia or producto" -v`
Expected: FAIL con `AttributeError: module 'app.services.integracion_dimensiones_service' has no attribute 'sincronizar_especialidad'`.

- [ ] **Step 3: Implementar los cuatro sincronizadores**

Añade al final de `backend/app/services/integracion_dimensiones_service.py`. Amplía primero los imports del módulo con:
```python
from app.models.dimensiones import (
    CentroMedico, Especialidad, Farmacia, Medico, Municipio, Producto, Provincia,
)
from app.models.integracion_ext import (
    ExtDimEspecialidad, ExtDimFarmacia, ExtDimMedico, ExtDimProducto,
)
from app.models.mapeo_externo import (
    ENT_ESPECIALIDAD, ENT_FARMACIA, ENT_MEDICO, ENT_PRODUCTO,
)
```

```python
def _norm(texto: str | None) -> str:
    """Nombre normalizado para emparejar catálogos que se identifican por texto."""
    return (texto or "").strip().casefold()


def sincronizar_especialidad(db: Session, pais_codigo: str,
                             hallazgos: list) -> Conteo:
    """`DIM_Especialidad` no tiene código ni país: su identidad es el nombre.

    Por eso el mapeo se guarda con `pais_codigo=""` — es el único catálogo
    compartido entre países, igual que en el contrato.
    """
    conteo = Conteo(ENT_ESPECIALIDAD)
    filas = db.query(ExtDimEspecialidad).all()
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            objetivo = _norm(f.nombre)
            for e in db.query(Especialidad).all():
                if _norm(e.nombre) == objetivo:
                    return e
            return None

        def _crear(f=fila):
            nuevo = Especialidad(nombre=f.nombre.strip(), activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_ESPECIALIDAD, "", fila.especialidad_codigo, Especialidad,
            _buscar, _crear)
        registro.activo = fila.activo
        conteo.anotar(resultado)
    return conteo


def _provincia_id(db: Session, pais_codigo: str, nombre: str | None) -> int | None:
    if not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for p in db.query(Provincia).filter(Provincia.pais_codigo == pais_codigo).all():
        if _norm(p.nombre) == objetivo:
            return p.id
    nueva = Provincia(pais_codigo=pais_codigo, nombre=nombre.strip())
    db.add(nueva)
    db.flush()
    return nueva.id


def _municipio_id(db: Session, provincia_id: int | None,
                  nombre: str | None) -> int | None:
    """`DIM_Municipio` cuelga de la provincia, no del país: sin provincia
    resuelta no se puede crear el municipio."""
    if provincia_id is None or not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for m in db.query(Municipio).filter(Municipio.provincia_id == provincia_id).all():
        if _norm(m.nombre) == objetivo:
            return m.id
    nuevo = Municipio(provincia_id=provincia_id, nombre=nombre.strip())
    db.add(nuevo)
    db.flush()
    return nuevo.id


def _centro_medico_id(db: Session, pais_codigo: str, nombre: str | None,
                      provincia_id: int | None,
                      municipio_id: int | None) -> int | None:
    if not _norm(nombre):
        return None
    objetivo = _norm(nombre)
    for c in db.query(CentroMedico).filter(
            CentroMedico.pais_codigo == pais_codigo).all():
        if _norm(c.nombre) == objetivo:
            return c.id
    nuevo = CentroMedico(pais_codigo=pais_codigo, nombre=nombre.strip(),
                         provincia_id=provincia_id, municipio_id=municipio_id)
    db.add(nuevo)
    db.flush()
    return nuevo.id


def sincronizar_medico(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`ext` trae centro, provincia y municipio como texto; `DIM_Medico` los
    referencia por clave foránea. Se resuelven por nombre y se crean si faltan:
    son catálogos auxiliares sin identidad propia en el contrato, y descartar el
    dato sería peor que crearlos.

    La adopción por exequátur va después de la del código porque el exequátur es
    el identificador profesional: si el código de Mallén no coincide pero el
    exequátur sí, es la misma persona.
    """
    conteo = Conteo(ENT_MEDICO)
    filas = (db.query(ExtDimMedico)
             .filter(ExtDimMedico.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        provincia_id = _provincia_id(db, pais_codigo, fila.provincia)
        municipio_id = _municipio_id(db, provincia_id, fila.municipio)
        centro_id = _centro_medico_id(db, pais_codigo, fila.centro_trabajo,
                                      provincia_id, municipio_id)
        especialidad_id = (
            mapeo.id_mapeado(db, ENT_ESPECIALIDAD, "", fila.especialidad_codigo)
            if fila.especialidad_codigo else None)

        def _buscar(f=fila):
            por_codigo = (db.query(Medico)
                          .filter(Medico.pais_codigo == f.pais_codigo,
                                  Medico.codigo == f.medico_codigo).first())
            if por_codigo is not None:
                return por_codigo
            if f.exequatur:
                return (db.query(Medico)
                        .filter(Medico.pais_codigo == f.pais_codigo,
                                Medico.exequatur == f.exequatur).first())
            return None

        def _crear(f=fila, eid=especialidad_id, cid=centro_id,
                   pid=provincia_id, mid=municipio_id):
            nuevo = Medico(pais_codigo=f.pais_codigo, codigo=f.medico_codigo,
                           nombre=f.nombre, especialidad_id=eid,
                           centro_medico_id=cid, provincia_id=pid,
                           municipio_id=mid, exequatur=f.exequatur,
                           activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_MEDICO, pais_codigo, fila.medico_codigo, Medico,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        if fila.exequatur:
            registro.exequatur = fila.exequatur
        # El código de Mallén se adopta también en el registro interno cuando
        # este no tenía ninguno: así los dos universos de médicos convergen.
        if not registro.codigo:
            registro.codigo = fila.medico_codigo
        if especialidad_id is not None:
            registro.especialidad_id = especialidad_id
        if centro_id is not None:
            registro.centro_medico_id = centro_id
        if provincia_id is not None:
            registro.provincia_id = provincia_id
        if municipio_id is not None:
            registro.municipio_id = municipio_id
        conteo.anotar(resultado)
    return conteo


def sincronizar_farmacia(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """`DIM_Farmacia` exige `direccion` y `encargado` (NOT NULL) que `ext` no
    envía: se crean vacíos para completarse en VISTA, y al re-sincronizar NO se
    pisan — son datos que VISTA enriqueció y Mallén no conoce.

    Entra con `origen='CONFIG'` y `estado='APROBADA'`: viene del maestro oficial,
    no de un representante solicitando un alta que un gerente deba aprobar.
    """
    conteo = Conteo(ENT_FARMACIA)
    filas = (db.query(ExtDimFarmacia)
             .filter(ExtDimFarmacia.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        def _buscar(f=fila):
            objetivo = _norm(f.nombre)
            for far in db.query(Farmacia).filter(
                    Farmacia.pais_codigo == f.pais_codigo).all():
                if _norm(far.nombre_completo) == objetivo:
                    return far
            return None

        def _crear(f=fila):
            nueva = Farmacia(
                pais_codigo=f.pais_codigo, es_cadena=False, nombre=f.nombre,
                nombre_completo=f.nombre, direccion="", encargado="",
                provincia=f.provincia, municipio=f.municipio,
                estado="APROBADA", origen="CONFIG")
            db.add(nueva)
            db.flush()
            return nueva

        registro, resultado = mapeo.resolver(
            db, ENT_FARMACIA, pais_codigo, fila.farmacia_codigo, Farmacia,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.nombre_completo = fila.nombre
        if fila.provincia:
            registro.provincia = fila.provincia
        if fila.municipio:
            registro.municipio = fila.municipio
        conteo.anotar(resultado)
    return conteo


def sincronizar_producto(db: Session, pais_codigo: str, hallazgos: list) -> Conteo:
    """Los campos propios de VISTA (`area_terapeutica`, `segmento_target`,
    `meta_muestras_visita`, `gerente_producto`) NO se tocan: `ext` no los conoce
    y pisarlos borraría configuración hecha en VISTA."""
    conteo = Conteo(ENT_PRODUCTO)
    filas = (db.query(ExtDimProducto)
             .filter(ExtDimProducto.pais_codigo == pais_codigo).all())
    conteo.en_ext = len(filas)
    for fila in filas:
        if not _cabe(fila.producto_codigo, 40):
            _omitir_por_largo(conteo, hallazgos, ENT_PRODUCTO,
                              fila.producto_codigo, "DIM_Producto.codigo", 40)
            continue
        linea_id = (mapeo.id_mapeado(db, ENT_LINEA, pais_codigo, fila.linea_codigo)
                    if fila.linea_codigo else None)

        def _buscar(f=fila):
            return (db.query(Producto)
                    .filter(Producto.codigo == f.producto_codigo).first())

        def _crear(f=fila, lid=linea_id):
            nuevo = Producto(codigo=f.producto_codigo, nombre=f.nombre,
                             linea_id=lid, activo=f.activo)
            db.add(nuevo)
            db.flush()
            return nuevo

        registro, resultado = mapeo.resolver(
            db, ENT_PRODUCTO, pais_codigo, fila.producto_codigo, Producto,
            _buscar, _crear)
        registro.nombre = fila.nombre
        registro.activo = fila.activo
        if linea_id is not None:
            registro.linea_id = linea_id
        conteo.anotar(resultado)
    return conteo
```

- [ ] **Step 4: Correr toda la suite del archivo**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py -v`
Expected: 11 passed (o SKIPPED).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/integracion_dimensiones_service.py backend/tests/test_integracion_dimensiones.py
git commit -m "feat(integracion) sincronizar especialidad, medico, farmacia y producto"
```

---

### Task 5: Orquestador + endpoints

**Files:**
- Modify: `backend/app/services/integracion_dimensiones_service.py`
- Modify: `backend/app/api/v1/routers/integracion.py`
- Test: `backend/tests/test_integracion_dimensiones.py`

**Interfaces:**
- Consumes: los nueve `sincronizar_*` de Tasks 3-4.
- Produce (para Task 6): `sincronizar_todo(db, pais_codigo) -> dict` con las claves `pais_codigo`, `dimensiones` (lista de dicts con `entidad`, `en_ext`, `creados`, `adoptados`, `actualizados`, `omitidos`) y `hallazgos` (lista de dicts con `entidad`, `codigo_externo`, `problema`, `severidad`); y `resumen_dimensiones(db, pais_codigo) -> list[dict]` con `entidad`, `en_ext`, `mapeadas`.

- [ ] **Step 1: Añadir los tests al final del archivo de tests**

```python
def test_sincronizar_todo_devuelve_las_nueve_dimensiones(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()

    r = dim.sincronizar_todo(db, "DO")

    assert r["pais_codigo"] == "DO"
    assert len(r["dimensiones"]) == 9
    entidades = [d["entidad"] for d in r["dimensiones"]]
    assert entidades == list(dim.ENTIDADES)          # y en orden de dependencia
    rep = next(d for d in r["dimensiones"] if d["entidad"] == "representante")
    assert rep["creados"] == 1


def test_sincronizar_todo_es_idempotente(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()
    dim.sincronizar_todo(db, "DO")

    r = dim.sincronizar_todo(db, "DO")

    rep = next(d for d in r["dimensiones"] if d["entidad"] == "representante")
    assert rep["creados"] == 0
    assert rep["actualizados"] == 1
    assert db.query(RepresentanteMedico).count() == 1


def test_resumen_cuenta_ext_y_mapeadas(base):
    db = base
    db.add(ExtDimRepresentante(pais_codigo="DO", rm_codigo="VM99",
                               linea_codigo="CARD", nombre="Nuevo", activo=True))
    db.commit()
    dim.sincronizar_todo(db, "DO")

    filas = dim.resumen_dimensiones(db, "DO")

    rep = next(f for f in filas if f["entidad"] == "representante")
    assert rep["en_ext"] == 1
    assert rep["mapeadas"] == 1
```

- [ ] **Step 2: Correr los tests para verificar que fallan**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py -k "todo or resumen" -v`
Expected: FAIL con `AttributeError: ... has no attribute 'sincronizar_todo'`.

- [ ] **Step 3: Añadir el orquestador al servicio**

Añade al final de `backend/app/services/integracion_dimensiones_service.py`. Amplía el import de `mapeo_externo` con `ENTIDADES` y `MapeoExterno`:

```python
#: Cada dimensión en el orden en que debe correr: las posteriores resuelven sus
#: claves foráneas contra el mapeo que dejan las anteriores.
_SINCRONIZADORES = {
    ENT_PAIS: sincronizar_pais,
    ENT_LINEA: sincronizar_linea,
    ENT_GERENTE: sincronizar_gerente,
    ENT_REPRESENTANTE: sincronizar_representante,
    ENT_CICLO: sincronizar_ciclo,
    ENT_ESPECIALIDAD: sincronizar_especialidad,
    ENT_MEDICO: sincronizar_medico,
    ENT_FARMACIA: sincronizar_farmacia,
    ENT_PRODUCTO: sincronizar_producto,
}


def sincronizar_todo(db: Session, pais_codigo: str) -> dict:
    """Corre las nueve dimensiones en orden de dependencia.

    Un solo commit al final: o entra el maestro coherente o no entra nada. Las
    filas problemáticas no abortan —se omiten con su hallazgo—, así que el commit
    solo confirma lo que sí se pudo resolver.
    """
    hallazgos: list[Hallazgo] = []
    conteos: list[Conteo] = []
    for entidad in ENTIDADES:
        conteos.append(_SINCRONIZADORES[entidad](db, pais_codigo, hallazgos))
    db.commit()

    errores = sum(1 for h in hallazgos if h.severidad == SEVERIDAD_ERROR)
    logger.info(f"Dimensiones sincronizadas para {pais_codigo}: "
                f"{sum(c.creados for c in conteos)} creadas, "
                f"{sum(c.adoptados for c in conteos)} adoptadas, "
                f"{errores} con error")
    return {
        "pais_codigo": pais_codigo,
        "dimensiones": [{
            "entidad": c.entidad, "en_ext": c.en_ext, "creados": c.creados,
            "adoptados": c.adoptados, "actualizados": c.actualizados,
            "omitidos": c.omitidos,
        } for c in conteos],
        "hallazgos": [{
            "entidad": h.entidad, "codigo_externo": h.codigo_externo,
            "problema": h.problema, "severidad": h.severidad,
        } for h in hallazgos],
    }


#: Cuántas filas hay en `ext` por dimensión, para el tablero. La especialidad no
#: lleva país en el contrato, así que se cuenta entera.
_ORIGEN_CONTEO = {
    ENT_PAIS: (ExtDimPais, True),
    ENT_LINEA: (ExtDimLinea, True),
    ENT_GERENTE: (ExtDimGerente, True),
    ENT_REPRESENTANTE: (ExtDimRepresentante, True),
    ENT_CICLO: (ExtDimCiclo, True),
    ENT_ESPECIALIDAD: (ExtDimEspecialidad, False),
    ENT_MEDICO: (ExtDimMedico, True),
    ENT_FARMACIA: (ExtDimFarmacia, True),
    ENT_PRODUCTO: (ExtDimProducto, True),
}


def resumen_dimensiones(db: Session, pais_codigo: str) -> list[dict]:
    """Filas en `ext` frente a filas ya mapeadas, por dimensión."""
    salida = []
    for entidad in ENTIDADES:
        modelo, por_pais = _ORIGEN_CONTEO[entidad]
        q = db.query(modelo)
        if por_pais:
            q = q.filter(modelo.pais_codigo == pais_codigo)
        clave_pais = pais_codigo if entidad != ENT_ESPECIALIDAD else ""
        mapeadas = (db.query(MapeoExterno)
                    .filter(MapeoExterno.entidad == entidad,
                            MapeoExterno.pais_codigo == clave_pais).count())
        salida.append({"entidad": entidad, "en_ext": q.count(),
                       "mapeadas": mapeadas})
    return salida
```

- [ ] **Step 4: Añadir los endpoints al router**

En `backend/app/api/v1/routers/integracion.py`, añade el import del servicio nuevo junto al existente:
```python
from app.services import integracion_dimensiones_service as dimensiones
```
Y estos dos endpoints al final del archivo:

```python
@router.post("/dimensiones/sincronizar",
             summary="Sincronizar las 9 dimensiones de un país")
def sincronizar_dimensiones(pais_codigo: str, db: Session = Depends(get_db),
                            _: Usuario = RequireTI):
    """Adopta lo que VISTA ya tiene en vez de duplicarlo: mirar `adoptados` en la
    primera corrida es la forma de comprobar que el emparejamiento funcionó."""
    return dimensiones.sincronizar_todo(db, pais_codigo)


@router.get("/dimensiones/resumen", summary="Filas en ext frente a mapeadas")
def resumen_dimensiones(pais_codigo: str, db: Session = Depends(get_db),
                        _: Usuario = RequireTI):
    return dimensiones.resumen_dimensiones(db, pais_codigo)
```

- [ ] **Step 5: Verificar**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_integracion_dimensiones.py tests/test_integracion_mapeo.py tests/test_integracion_validacion.py tests/test_integracion_ext.py -v`
Expected: todos pasan (14 de dimensiones + 5 de mapeo + 16 de validación + 25 de contrato).

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print([r.path for r in app.routes if 'dimensiones' in r.path])"`
Expected: imprime las 2 rutas nuevas.

- [ ] **Step 6: Commit**

```bash
git add backend/app/services/integracion_dimensiones_service.py backend/app/api/v1/routers/integracion.py backend/tests/test_integracion_dimensiones.py
git commit -m "feat(integracion) orquestador de las 9 dimensiones + endpoints"
```

---

### Task 6: Frontend — sección "Dimensiones" en la pantalla de lotes

**Files:**
- Modify: `frontend/src/services/integracion.service.ts`
- Modify: `frontend/src/pages/integracion/LotesIntegracion.tsx`

**Interfaces:**
- Consumes: los endpoints de Task 5.

- [ ] **Step 1: Añadir tipos y funciones al service**

Añade al final de `frontend/src/services/integracion.service.ts`:

```ts
// ── Dimensiones (sub-proyecto 2) ─────────────────────────────────────────
export interface ConteoDimension {
  entidad: string; en_ext: number; creados: number;
  adoptados: number; actualizados: number; omitidos: number;
}

export interface HallazgoDimension {
  entidad: string; codigo_externo: string; problema: string;
  severidad: SeveridadHallazgo;
}

export interface ResultadoSincronizacion {
  pais_codigo: string;
  dimensiones: ConteoDimension[];
  hallazgos: HallazgoDimension[];
}

export interface FilaResumenDimension {
  entidad: string; en_ext: number; mapeadas: number;
}

export const sincronizarDimensiones = (paisCodigo: string) =>
  api.post<ResultadoSincronizacion>('/integracion/dimensiones/sincronizar', null,
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const resumenDimensiones = (paisCodigo: string) =>
  api.get<FilaResumenDimension[]>('/integracion/dimensiones/resumen',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);
```

- [ ] **Step 2: Añadir la sección a la página**

En `frontend/src/pages/integracion/LotesIntegracion.tsx`, amplía el import del service con `sincronizarDimensiones`, `resumenDimensiones` y los tipos `ConteoDimension`, `ResultadoSincronizacion`. Añade el componente al final del archivo:

```tsx
function SeccionDimensiones({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [resultado, setResultado] = useState<ResultadoSincronizacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resumen = useQuery({
    queryKey: ['integracion-dimensiones', paisCodigo],
    queryFn: () => resumenDimensiones(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const sincronizar = useMutation({
    mutationFn: () => sincronizarDimensiones(paisCodigo as string),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-dimensiones'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron sincronizar las dimensiones.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para ver las dimensiones.
    </Alert>;
  }

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>Dimensiones</Typography>
        <Button variant="contained" startIcon={<Sync />}
          disabled={sincronizar.isPending} onClick={() => sincronizar.mutate()}>
          {sincronizar.isPending ? 'Sincronizando…' : 'Sincronizar dimensiones'}
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Dimensión</TableCell>
              <TableCell align="right">En Mallén</TableCell>
              <TableCell align="right">Mapeadas</TableCell>
              <TableCell align="right">Pendientes</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(resumen.data || []).map((f) => (
              <TableRow key={f.entidad}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{f.entidad}</TableCell>
                <TableCell align="right">{f.en_ext}</TableCell>
                <TableCell align="right">{f.mapeadas}</TableCell>
                <TableCell align="right">{Math.max(0, f.en_ext - f.mapeadas) || '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      {resultado && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>
            Sincronización completada. «Adoptados» son los registros que ya existían
            en VISTA y se emparejaron en vez de duplicarse.
          </Alert>
          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Dimensión</TableCell>
                  <TableCell align="right">Creados</TableCell>
                  <TableCell align="right">Adoptados</TableCell>
                  <TableCell align="right">Actualizados</TableCell>
                  <TableCell align="right">Omitidos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultado.dimensiones.map((d: ConteoDimension) => (
                  <TableRow key={d.entidad}>
                    <TableCell sx={{ textTransform: 'capitalize' }}>{d.entidad}</TableCell>
                    <TableCell align="right">{d.creados}</TableCell>
                    <TableCell align="right"><strong>{d.adoptados}</strong></TableCell>
                    <TableCell align="right">{d.actualizados}</TableCell>
                    <TableCell align="right">{d.omitidos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {resultado.hallazgos.length > 0 && (
            <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <Box sx={{ p: 2 }}>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Esto es lo que hay que enviarle al equipo técnico de Mallén para corregir.
                </Alert>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Dimensión</TableCell><TableCell>Código</TableCell>
                      <TableCell>Problema</TableCell><TableCell>Severidad</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.hallazgos.map((h, i) => (
                      <TableRow key={`${h.entidad}-${h.codigo_externo}-${i}`}>
                        <TableCell sx={{ textTransform: 'capitalize' }}>{h.entidad}</TableCell>
                        <TableCell>{h.codigo_externo}</TableCell>
                        <TableCell>{h.problema}</TableCell>
                        <TableCell>
                          <Chip size="small" label={h.severidad}
                            color={h.severidad === 'error' ? 'error' : 'warning'} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}
```

Monta la sección al final del JSX del componente `LotesIntegracion`, justo antes del `<Snackbar>`:
```tsx
      <SeccionDimensiones paisCodigo={paisCodigo} />
```
Y añade `Sync` al import de `@mui/icons-material`.

- [ ] **Step 3: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 4: Commit**

```bash
git add frontend/src/services/integracion.service.ts frontend/src/pages/integracion/LotesIntegracion.tsx
git commit -m "feat(integracion) seccion Dimensiones: sincronizar y ver adoptados vs creados"
```

---

## Verificación en vivo (tras Task 6, no es un commit)

Como Mallén todavía no envía nada, hay que **sembrar dimensiones en `ext` a mano** en la base local. Con JWT de ADMIN:

1. Sembrar `ext.dimpais`, `ext.dimlinea` y dos `ext.dimrepresentante`, uno con un `rm_codigo` que YA exista en `Config.DIM_RM` y otro nuevo.
2. Pulsar «Sincronizar dimensiones» → el existente debe salir en **adoptados**, el nuevo en **creados**, y `DIM_RM` no debe tener duplicados.
3. Sincronizar otra vez → todo en **actualizados**, cero creados.
4. Sembrar un `ext.dimgerente` con código de 25 caracteres → sale en **omitidos** con su hallazgo, y no se crea el gerente.
5. Sembrar un `ext.dimciclo` con `cerrado=true` sobre un ciclo abierto en VISTA → el ciclo sigue abierto y aparece el hallazgo `aviso`.
6. Un rol no-TI no ve la sección ni puede llamar los endpoints.

---

## Self-Review

- **Cobertura del spec:**
  - §3 tabla de equivalencias + migración → Task 1.
  - §4 algoritmo buscar/adoptar/crear + claves naturales → Task 2 (primitiva) y Tasks 3-4 (cada clave natural).
  - §5 nunca borra → ningún sincronizador emite `delete` sobre una `DIM_*`; `activo` se sincroniza.
  - §6 mapeos huérfanos → Task 2 (`resolver`) + test dedicado.
  - §7.1 ciclo sin tocar `cerrado` → Task 3 + test.
  - §7.2 farmacia (origen/estado/no pisar) → Task 4 + 2 tests.
  - §7.3 médico y catálogos auxiliares → Task 4 + 2 tests.
  - §7.4 códigos largos y colisión global → Task 3 (`_omitir_por_largo`, colisión de gerente) + test.
  - §7.5 producto sin pisar campos de VISTA → Task 4 + test.
  - §8 orden → `ENTIDADES` (Task 1) y `_SINCRONIZADORES` (Task 5).
  - §9 errores sin persistir → `Hallazgo` es un dataclass que viaja en la respuesta; no se toca `Audit.IntegracionHallazgo`.
  - §10 los 2 endpoints → Task 5.
  - §11 idempotencia → Task 5 + test.
  - §12 frontend → Task 6.
  - §13 fuera de alcance → respetado (sin hechos, sin dimensiones IR, sin scheduler, sin editor de mapeo, sin borrado).
  - §14 verificación → tests de Tasks 2-5 (10 de los 10 casos del spec) + sección en vivo.
- **Placeholder scan:** sin TBD/TODO; código completo en cada paso.
- **Consistencia de tipos:** `resolver` devuelve `(registro, resultado)` y los nueve sincronizadores lo consumen igual; `Conteo.anotar` traduce los `RESULTADO_*` de Task 2; `sincronizar_todo` devuelve las claves que declara `ResultadoSincronizacion` en el frontend; `resumen_dimensiones` devuelve las de `FilaResumenDimension`.
- **Riesgo conocido, mitigado:** los closures dentro de los bucles capturan `fila` por argumento por defecto (`def _buscar(f=fila)`), no por referencia. Sin eso, todas las filas compartirían la última iteración — el error clásico de closures en bucles de Python.
