# Alcances por línea y por país — Plan de implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Que VISTA sepa expresar los siete roles que definió la gerencia de Laboratorio Mallén, añadiendo alcance por línea y una frontera real por país.

**Architecture:** Dos ejes ortogonales. El alcance (`own`/`team`/`linea`/`all`) responde a "¿de cuáles representantes?" y vive en la matriz RBAC; el país responde a "¿de cuál operación?" y se aplica como filtro transversal por encima. Dos tablas nuevas —países del usuario y líneas del gerente— y ninguna fila significa "todos", para que los 37 usuarios existentes sigan funcionando sin migración manual.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0 (`Mapped`/`mapped_column`), Alembic, pytest contra PostgreSQL real, React 18 + TypeScript + MUI v6.

## Global Constraints

- Spec: `docs/superpowers/specs/2026-08-14-alcances-linea-pais-design.md`. Ante cualquier duda, manda el spec.
- **CERO roles nuevos.** El enum `Rol` no se toca. El Coordinador Mercadeo Internacional es `GERENTE_MARKETING` con países `{GT, HN}`.
- **`FACT_UsuarioPais` sin filas = todos los países.** Es lo que hace que los 37 usuarios existentes no requieran migración manual.
- **El país se evalúa ANTES que el alcance.** Un Gerente de Marca de RD no ve los RM de su línea en Guatemala.
- **`Usuario.pais_codigo` se conserva** como país preferido (default de la pantalla). Deja de ser la frontera; no se borra ni se renombra.
- **`DIM_Gerente.linea_id` se conserva.** Se migra su contenido a `DIM_GerenteLinea`; nada que lo lea hoy puede romperse.
- **No se cambia el modelo de la matriz** (una celda por `(recurso, rol)`). El alcance `linea` se asigna SOLO a recursos de lectura (spec §7).
- No se toca el esquema `ext`, ni `motor_calculo_service`, ni `recalculo_service`.
- Intérprete: `backend/venv/Scripts/python.exe`. Los tests de integración necesitan PostgreSQL real.
- Migraciones: encadenar desde `0035_fuente_conocimientos` (head actual).

---

## Estructura de archivos

| Archivo | Responsabilidad |
|---|---|
| `backend/app/models/alcance.py` (crear) | Los 2 modelos ORM nuevos: `UsuarioPais`, `GerenteLinea` |
| `backend/alembic/versions/0036_alcance_linea_pais.py` (crear) | Las 2 tablas + backfill de `linea_id` |
| `backend/app/core/authz/constantes.py` (modificar) | `Alcance.LINEA` + su orden |
| `backend/app/core/authz/scope.py` (modificar) | Resolución de `LINEA` y de países |
| `backend/app/core/authz/paises.py` (crear) | Dependency y guard de país — separado porque no es un alcance |
| `backend/app/core/authz/matrix.py` (modificar) | Celdas de `GERENTE_MARCA` y `GERENTE_DISTRITO` |
| `frontend/src/pages/admin/Usuarios.tsx` (modificar) | Asignar países a un usuario |
| `frontend/src/pages/admin/Admin.tsx` (modificar) | Asignar líneas a un gerente |

---

## Task 1: Modelos y migración

**Files:**
- Create: `backend/app/models/alcance.py`
- Create: `backend/alembic/versions/0036_alcance_linea_pais.py`
- Modify: `backend/alembic/env.py` (añadir el import del módulo nuevo)
- Test: `backend/tests/test_alcance_modelo.py`

**Interfaces:**
- Consumes: nada.
- Produces: `UsuarioPais(usuario_id: int, pais_codigo: str)` y `GerenteLinea(gerente_id: int, linea_id: int)`, ambos en `app.models.alcance`.

- [ ] **Step 1: Escribir el test que falla**

```python
# backend/tests/test_alcance_modelo.py
"""Modelos de alcance: países del usuario y líneas del gerente.

La regla que estos tests protegen es la del spec §3: SIN FILAS significa "todos
los países". Un modelo que exigiera al menos una fila obligaría a migrar a mano
los 37 usuarios existentes antes de activar la frontera — y ese es justo el paso
que se olvida y deja a todo el mundo sin acceso.
"""
from app.models.alcance import GerenteLinea, UsuarioPais


def test_usuario_pais_declara_su_tabla_y_esquema():
    assert UsuarioPais.__tablename__ == "FACT_UsuarioPais"
    assert UsuarioPais.__table__.schema == "Security"


def test_gerente_linea_declara_su_tabla_y_esquema():
    assert GerenteLinea.__tablename__ == "DIM_GerenteLinea"
    assert GerenteLinea.__table__.schema == "Config"


def test_la_pareja_usuario_pais_es_unica():
    """Sin el único, asignar dos veces el mismo país duplica filas y el conteo
    de 'cuántos países tiene' deja de ser fiable."""
    unicos = [set(c.columns.keys()) for c in UsuarioPais.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert {"usuario_id", "pais_codigo"} in unicos


def test_la_pareja_gerente_linea_es_unica():
    unicos = [set(c.columns.keys()) for c in GerenteLinea.__table__.constraints
              if c.__class__.__name__ == "UniqueConstraint"]
    assert {"gerente_id", "linea_id"} in unicos
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_modelo.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.models.alcance'`

- [ ] **Step 3: Escribir los modelos**

```python
# backend/app/models/alcance.py
"""Asignaciones de alcance: países de un usuario y líneas de un gerente.

Viven aparte de `usuario.py` y `dimensiones.py` a propósito: son la unión entre el
motor de autorización y las dimensiones del negocio, y no pertenecen del todo a
ninguno de los dos.
"""
from sqlalchemy import ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


class UsuarioPais(Base):
    """Países que un usuario puede ver.

    SIN FILAS = TODOS LOS PAÍSES. No es un descuido: es lo que permite activar la
    frontera sin tocar a los usuarios que ya existen. Con filas, el usuario queda
    limitado exactamente a esos países.
    """
    __tablename__ = "FACT_UsuarioPais"
    __table_args__ = (
        UniqueConstraint("usuario_id", "pais_codigo", name="UQ_UsuarioPais"),
        {"schema": "Security"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id", ondelete="CASCADE"), nullable=False, index=True)
    pais_codigo: Mapped[str] = mapped_column(String(10), nullable=False)


class GerenteLinea(Base):
    """Líneas a cargo de un gerente. Sustituye funcionalmente a `DIM_Gerente.linea_id`,
    que se conserva para no romper lo que ya lo lee."""
    __tablename__ = "DIM_GerenteLinea"
    __table_args__ = (
        UniqueConstraint("gerente_id", "linea_id", name="UQ_GerenteLinea"),
        {"schema": "Config"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    gerente_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id", ondelete="CASCADE"), nullable=False, index=True)
    linea_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Config.DIM_Linea.id"), nullable=False, index=True)
```

- [ ] **Step 4: Registrar el módulo en env.py**

En `backend/alembic/env.py`, junto a los otros imports de modelos (alrededor de la línea 39), añadir:

```python
from app.models import alcance  # noqa: F401,E402  ← países del usuario y líneas del gerente
```

- [ ] **Step 5: Correr el test y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_modelo.py -q`
Expected: PASS (4 tests)

- [ ] **Step 6: Escribir la migración con backfill**

```python
# backend/alembic/versions/0036_alcance_linea_pais.py
"""Alcances por línea y por país: FACT_UsuarioPais + DIM_GerenteLinea.

El backfill copia `DIM_Gerente.linea_id` a `DIM_GerenteLinea` para que ningún
gerente pierda su línea al cambiar la fuente de verdad. `DIM_Gerente.linea_id`
NO se borra: sigue habiendo código que lo lee.

`FACT_UsuarioPais` nace VACÍA a propósito — sin filas significa "todos los
países", así que los usuarios existentes conservan su acceso actual.

Revision ID: 0036_alcance_linea_pais
Revises: 0035_fuente_conocimientos
"""
import sqlalchemy as sa
from alembic import op

revision = "0036_alcance_linea_pais"
down_revision = "0035_fuente_conocimientos"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "FACT_UsuarioPais",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("usuario_id", sa.Integer(), nullable=False),
        sa.Column("pais_codigo", sa.String(length=10), nullable=False),
        sa.ForeignKeyConstraint(["usuario_id"], ["Security.DIM_Usuario.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("usuario_id", "pais_codigo", name="UQ_UsuarioPais"),
        schema="Security",
    )
    op.create_index("IX_UsuarioPais_usuario", "FACT_UsuarioPais", ["usuario_id"], schema="Security")

    op.create_table(
        "DIM_GerenteLinea",
        sa.Column("id", sa.Integer(), autoincrement=True, nullable=False),
        sa.Column("gerente_id", sa.Integer(), nullable=False),
        sa.Column("linea_id", sa.Integer(), nullable=False),
        sa.ForeignKeyConstraint(["gerente_id"], ["Config.DIM_Gerente.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["linea_id"], ["Config.DIM_Linea.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("gerente_id", "linea_id", name="UQ_GerenteLinea"),
        schema="Config",
    )
    op.create_index("IX_GerenteLinea_gerente", "DIM_GerenteLinea", ["gerente_id"], schema="Config")
    op.create_index("IX_GerenteLinea_linea", "DIM_GerenteLinea", ["linea_id"], schema="Config")

    # Backfill: la línea que cada gerente ya tenía.
    op.execute("""
        INSERT INTO "Config"."DIM_GerenteLinea" (gerente_id, linea_id)
        SELECT id, linea_id FROM "Config"."DIM_Gerente" WHERE linea_id IS NOT NULL
    """)


def downgrade() -> None:
    op.drop_index("IX_GerenteLinea_linea", table_name="DIM_GerenteLinea", schema="Config")
    op.drop_index("IX_GerenteLinea_gerente", table_name="DIM_GerenteLinea", schema="Config")
    op.drop_table("DIM_GerenteLinea", schema="Config")
    op.drop_index("IX_UsuarioPais_usuario", table_name="FACT_UsuarioPais", schema="Security")
    op.drop_table("FACT_UsuarioPais", schema="Security")
```

- [ ] **Step 7: Aplicar la migración y comprobar el backfill**

```bash
cd backend && ./venv/Scripts/python.exe -m alembic upgrade head
./venv/Scripts/python.exe -c "
from app.db.database import SessionLocal
from app.models.alcance import GerenteLinea
from app.models.dimensiones import Gerente
db = SessionLocal()
con_linea = db.query(Gerente).filter(Gerente.linea_id.isnot(None)).count()
migrados = db.query(GerenteLinea).count()
print(f'gerentes con linea: {con_linea}  filas migradas: {migrados}')
assert con_linea == migrados, 'el backfill no cubrio a todos'
db.close(); print('backfill correcto')"
```

Expected: los dos números coinciden.

- [ ] **Step 8: Comprobar que `alembic check` no ve diferencias en las tablas nuevas**

Run: `cd backend && ./venv/Scripts/python.exe -m alembic check`
Expected: no aparecen `FACT_UsuarioPais` ni `DIM_GerenteLinea` entre las diferencias. (Hay deuda previa en otras 8 tablas ajenas a este trabajo — ignorarla.)

- [ ] **Step 9: Commit**

```bash
git add backend/app/models/alcance.py backend/alembic/versions/0036_alcance_linea_pais.py backend/alembic/env.py backend/tests/test_alcance_modelo.py
git commit -m "feat(alcance) modelos y migracion: paises del usuario y lineas del gerente"
```

---

## Task 2: El motor — alcance por línea y países visibles

**Files:**
- Modify: `backend/app/core/authz/constantes.py`
- Modify: `backend/app/core/authz/scope.py`
- Test: `backend/tests/test_alcance_scope.py`

**Interfaces:**
- Consumes: `UsuarioPais`, `GerenteLinea` (Task 1).
- Produces:
  - `Alcance.LINEA` (valor `"linea"`), ordenado entre `TEAM` y `ALL`.
  - `scope.lineas_de_usuario(db, user) -> set[int]`
  - `scope.paises_visibles(db, user) -> set[str] | None` (`None` = todos)
  - `scope.rm_ids_visibles(db, user, alcance)` acepta `LINEA` y **siempre** acota por país.

- [ ] **Step 1: Escribir el test que falla**

```python
# backend/tests/test_alcance_scope.py
"""Resolución de alcance por línea y de países visibles.

El orden importa y es lo que estos tests fijan: el país se evalúa ANTES que el
alcance. Un Gerente de Marca de RD con alcance de línea ve su línea EN RD, no esa
línea en todos los países. Al revés, un usuario podría alcanzar operaciones de
países que no le corresponden con solo pertenecer a una línea homónima.
"""
import pytest
from types import SimpleNamespace

from app.core.authz.constantes import Alcance, alcance_min
from app.core.authz import scope


def test_linea_es_mas_amplio_que_equipo_y_menos_que_todo():
    """`alcance_min` capa el export por la lectura; si LINEA quedara fuera del
    orden, la comparación daría KeyError en tiempo de ejecución."""
    assert alcance_min(Alcance.LINEA, Alcance.ALL) == Alcance.LINEA
    assert alcance_min(Alcance.LINEA, Alcance.TEAM) == Alcance.TEAM


def test_sin_filas_de_pais_el_usuario_ve_todos(db, escenario):
    u = escenario["usuario_sin_paises"]
    assert scope.paises_visibles(db, u) is None


def test_con_filas_el_usuario_ve_solo_esos(db, escenario):
    u = escenario["usuario_gt_hn"]
    assert scope.paises_visibles(db, u) == {"GT", "HN"}


def test_alcance_linea_ve_los_rm_de_su_linea_en_todos_los_distritos(db, escenario):
    """El Gerente de Marca ve su línea completa, no solo el equipo de un gerente."""
    u = escenario["gerente_marca_do"]
    ids = scope.rm_ids_visibles(db, u, Alcance.LINEA)
    assert escenario["rm_linea_a_distrito_1"].id in ids
    assert escenario["rm_linea_a_distrito_2"].id in ids
    assert escenario["rm_linea_b"].id not in ids


def test_el_pais_se_aplica_antes_que_la_linea(db, escenario):
    """EL TEST QUE DEFINE EL DISEÑO: el Gerente de Marca de RD NO ve al RM de su
    misma línea en Guatemala."""
    u = escenario["gerente_marca_do"]
    ids = scope.rm_ids_visibles(db, u, Alcance.LINEA)
    assert escenario["rm_linea_a_guatemala"].id not in ids


def test_el_pais_tambien_acota_el_alcance_total(db, escenario):
    """ALL ya no significa 'sin filtro' para quien tiene países asignados."""
    u = escenario["usuario_gt_hn"]
    ids = scope.rm_ids_visibles(db, u, Alcance.ALL)
    assert ids is not None, "con países asignados, ALL debe filtrar"
    assert escenario["rm_linea_a_guatemala"].id in ids
    assert escenario["rm_linea_a_distrito_1"].id not in ids   # es de RD


def test_sin_paises_asignados_todo_sigue_igual(db, escenario):
    """Compatibilidad: quien no tiene países conserva el comportamiento de hoy."""
    u = escenario["usuario_sin_paises"]
    assert scope.rm_ids_visibles(db, u, Alcance.ALL) is None
```

La fixture `escenario` crea: país DO y GT; líneas A y B en DO, línea A en GT; dos gerentes de distrito en DO sobre la línea A; un gerente de marca de DO con la línea A asignada en `DIM_GerenteLinea`; RM en cada combinación; y dos usuarios — uno sin filas en `FACT_UsuarioPais` y otro con `{GT, HN}`. Seguir el patrón de fixtures de `tests/test_medicos_top.py`.

- [ ] **Step 2: Correr el test y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_scope.py -q`
Expected: FAIL con `AttributeError: LINEA`

- [ ] **Step 3: Añadir `Alcance.LINEA`**

En `backend/app/core/authz/constantes.py`, reemplazar la clase y el orden:

```python
class Alcance(str, Enum):
    NONE = "none"
    OWN = "own"
    TEAM = "team"
    LINEA = "linea"
    ALL = "all"


# LINEA va entre TEAM y ALL: un Gerente de Marca ve más que un equipo (su línea
# en todos los distritos) y menos que todo (solo su línea). El orden lo usa
# `alcance_min` para capar el export por la lectura del módulo.
_ORDEN = {Alcance.NONE: 0, Alcance.OWN: 1, Alcance.TEAM: 2, Alcance.LINEA: 3, Alcance.ALL: 4}
```

- [ ] **Step 4: Implementar la resolución en `scope.py`**

Añadir a `backend/app/core/authz/scope.py`:

```python
def lineas_de_usuario(db: Session, user) -> set[int]:
    """Líneas a cargo del gerente al que pertenece el usuario. Vacío si no tiene gerente."""
    gerente_id = getattr(user, "gerente_id", None)
    if not gerente_id:
        return set()
    return {r[0] for r in db.query(GerenteLinea.linea_id)
            .filter(GerenteLinea.gerente_id == gerente_id).all()}


def paises_visibles(db: Session, user) -> set[str] | None:
    """Países que el usuario puede ver. `None` = todos.

    SIN FILAS significa TODOS a propósito (spec §3): es lo que deja intacto el
    acceso de los usuarios que ya existían el día que se activa la frontera.
    """
    usuario_id = getattr(user, "id", None)
    if not usuario_id:
        return None
    filas = {r[0] for r in db.query(UsuarioPais.pais_codigo)
             .filter(UsuarioPais.usuario_id == usuario_id).all()}
    return filas or None


def rm_ids_visibles(db: Session, user, alcance: Alcance) -> set[int] | None:
    """Conjunto de `rm_id` que el usuario puede ver. `None` = sin filtro (todos).

    El país se aplica SIEMPRE y ANTES que el alcance: un Gerente de Marca de RD
    ve su línea EN RD, no esa línea en todos los países.
    """
    paises = paises_visibles(db, user)

    if alcance == Alcance.ALL:
        if paises is None:
            return None                      # todo, sin filtro — comportamiento histórico
        return {r[0] for r in db.query(RepresentanteMedico.id)
                .filter(RepresentanteMedico.pais_codigo.in_(paises)).all()}

    if alcance == Alcance.OWN:
        rm_id = getattr(user, "rm_id", None)
        return {rm_id} if rm_id else set()

    if alcance == Alcance.LINEA:
        lineas = lineas_de_usuario(db, user)
        if not lineas:
            return set()
        q = db.query(RepresentanteMedico.id).filter(RepresentanteMedico.linea_id.in_(lineas))
        if paises is not None:
            q = q.filter(RepresentanteMedico.pais_codigo.in_(paises))
        return {r[0] for r in q.all()}

    if alcance == Alcance.TEAM:
        return rm_ids_de_equipo(db, getattr(user, "gerente_id", None))

    return set()
```

Y añadir el import arriba del archivo:

```python
from app.models.alcance import GerenteLinea, UsuarioPais
```

- [ ] **Step 5: Extender el guard por registro**

En la misma `scope.py`, `assert_ve_rm` debe aceptar `LINEA`. Reemplazar la función:

```python
def assert_ve_rm(user, rm_id: int, alcance: Alcance, ids_equipo: set[int] | None = None) -> None:
    """Guard por registro (anti-IDOR/BOLA): 403 si el usuario no puede ver ese `rm_id`.

    Para TEAM y LINEA el caller precomputa el conjunto con `rm_ids_visibles` y lo
    pasa en `ids_equipo`, para no consultar por cada registro de una lista.
    """
    if alcance == Alcance.ALL:
        return
    if alcance == Alcance.OWN and getattr(user, "rm_id", None) == rm_id:
        return
    if alcance in (Alcance.TEAM, Alcance.LINEA) and ids_equipo is not None and rm_id in ids_equipo:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="No autorizado sobre ese registro")
```

- [ ] **Step 6: Correr el test y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_scope.py -q`
Expected: PASS (7 tests)

- [ ] **Step 7: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: todo verde. Si algún test de `test_authz_*.py` falla por el `_ORDEN` nuevo, es un test que dependía de que `ALL` valiera 3 — corregir el valor esperado, no el orden.

- [ ] **Step 8: Commit**

```bash
git add backend/app/core/authz/constantes.py backend/app/core/authz/scope.py backend/tests/test_alcance_scope.py
git commit -m "feat(alcance) Alcance.LINEA y frontera de pais en el resolvedor de alcance"
```

---

## Task 3: La frontera de país en los endpoints

**Files:**
- Create: `backend/app/core/authz/paises.py`
- Modify: `backend/app/api/v1/routers/ranking.py`, `productividad.py`, `cobertura_predictiva.py`, `visita.py`, `exportacion.py`
- Test: `backend/tests/test_alcance_frontera_pais.py`

**Interfaces:**
- Consumes: `scope.paises_visibles` (Task 2).
- Produces: `paises.exigir_pais(db, user, pais_codigo) -> None` (lanza 403) y la dependency `PaisPermitido`.

- [ ] **Step 1: Escribir el test que falla**

```python
# backend/tests/test_alcance_frontera_pais.py
"""La frontera de país, de filtro a límite real.

El test `test_hoy_un_gerente_de_rd_puede_ver_guatemala` documenta el agujero que
este trabajo cierra: ANTES del cambio pasa, porque el backend nunca imponía el
país. Que falle tras implementar es la señal de que la frontera existe.
"""
import pytest
from fastapi import HTTPException

from app.core.authz import paises


def test_sin_paises_asignados_se_permite_cualquiera(db, escenario):
    """Compatibilidad: los 37 usuarios existentes no tienen filas y deben seguir igual."""
    paises.exigir_pais(db, escenario["usuario_sin_paises"], "DO")   # no lanza


def test_con_paises_asignados_se_permite_uno_de_ellos(db, escenario):
    paises.exigir_pais(db, escenario["usuario_gt_hn"], "GT")        # no lanza


def test_con_paises_asignados_se_rechaza_otro(db, escenario):
    """EL TEST QUE CONVIERTE EL FILTRO EN FRONTERA."""
    with pytest.raises(HTTPException) as e:
        paises.exigir_pais(db, escenario["usuario_gt_hn"], "DO")
    assert e.value.status_code == 403


def test_pais_none_no_se_valida(db, escenario):
    """Un endpoint sin `pais_codigo` consulta todos los países que le permita su
    alcance; la restricción la aplica `rm_ids_visibles`, no este guard."""
    paises.exigir_pais(db, escenario["usuario_gt_hn"], None)        # no lanza


def test_el_rechazo_no_revela_que_paises_existen(db, escenario):
    """El mensaje no debe enumerar los países del usuario ni decir si 'XX' existe:
    sería un canal para mapear la operación desde fuera."""
    with pytest.raises(HTTPException) as e:
        paises.exigir_pais(db, escenario["usuario_gt_hn"], "XX")
    assert "GT" not in e.value.detail and "HN" not in e.value.detail
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_frontera_pais.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.core.authz.paises'`

- [ ] **Step 3: Implementar el guard**

```python
# backend/app/core/authz/paises.py
"""Frontera por país.

Vive aparte de `scope.py` porque NO es un alcance. Los alcances responden a "¿de
cuáles representantes?"; el país a "¿de cuál operación?". Son ortogonales, y
meterlo dentro de `Alcance` obligaría a multiplicar cada celda de la matriz por
cada país (spec §2).
"""
from fastapi import Depends, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.core.authz.scope import paises_visibles
from app.core.deps import get_current_active_user
from app.db.database import get_db
from app.models.usuario import Usuario


def exigir_pais(db: Session, user, pais_codigo: str | None) -> None:
    """403 si el usuario no puede operar sobre ese país. `None` no se valida.

    El mensaje NO enumera los países permitidos ni distingue "no autorizado" de
    "no existe": ambas cosas dejarían mapear la operación desde fuera.
    """
    if not pais_codigo:
        return
    permitidos = paises_visibles(db, user)
    if permitidos is None or pais_codigo in permitidos:
        return
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="No autorizado sobre ese país")


def PaisPermitido(
    pais_codigo: str | None = Query(None),
    user: Usuario = Depends(get_current_active_user),
    db: Session = Depends(get_db),
) -> str | None:
    """Dependency que sustituye a `pais_codigo: str | None = Query(None)` en un
    endpoint: lee el parámetro, lo valida contra los países del usuario y lo
    devuelve. Migrar un endpoint es cambiar la declaración de su parámetro."""
    exigir_pais(db, user, pais_codigo)
    return pais_codigo
```

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_frontera_pais.py -q`
Expected: PASS (5 tests)

- [ ] **Step 5: Cablear los cinco módulos con datos de operación**

En cada router, sustituir la declaración del parámetro. Ejemplo en `ranking.py`:

```python
# ANTES
def get_ranking(pais_codigo: Optional[str] = Query(None), ...):

# DESPUÉS
from app.core.authz.paises import PaisPermitido
def get_ranking(pais_codigo: Optional[str] = Depends(PaisPermitido), ...):
```

Aplicar en los endpoints de: `ranking.py`, `productividad.py`, `cobertura_predictiva.py`, `visita.py` y `exportacion.py`.

**Por qué solo estos cinco de los 105 sitios que reciben `pais_codigo`:** son los que devuelven datos de la operación (desempeño, visitas, cobertura, exportaciones). Los demás son catálogos y pantallas de administración, ya restringidas por rol. Cablear los 105 de golpe multiplicaría el riesgo de romper algo sin cerrar nada que no cierren estos cinco. El resto queda como seguimiento explícito, no como olvido.

- [ ] **Step 6: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: todo verde.

- [ ] **Step 7: Commit**

```bash
git add backend/app/core/authz/paises.py backend/app/api/v1/routers/ backend/tests/test_alcance_frontera_pais.py
git commit -m "feat(alcance) frontera de pais en ranking, productividad, cobertura, visita y exportacion"
```

---

## Task 4: La matriz — asignar el alcance de línea

**Files:**
- Modify: `backend/app/core/authz/matrix.py`
- Test: `backend/tests/test_authz_matriz.py` (extender)

**Interfaces:**
- Consumes: `Alcance.LINEA` (Task 2).
- Produces: la matriz de fábrica con `GERENTE_MARCA` y `GERENTE_DISTRITO` en alcance de línea sobre los tres recursos de lectura.

- [ ] **Step 1: Escribir el test que falla**

```python
# añadir a backend/tests/test_authz_matriz.py
"""El alcance de línea SOLO va en recursos de lectura.

La matriz guarda una celda por (recurso, rol) y una acción de escritura implica
lectura al MISMO alcance. Si a `medico.panel` —donde el GD aprueba— se le pusiera
alcance de línea, el GD podría aprobar médicos de representantes ajenos. La regla
del spec §7 es que `linea` solo se asigna a recursos que se leen.
"""
from app.core.authz.constantes import Accion, Alcance, Recurso
from app.core.authz.matrix import MATRIZ
from app.models.usuario import Rol

RECURSOS_DE_LINEA = [Recurso.RANKING_RKT, Recurso.PRODUCTIVIDAD_COMERCIAL,
                     Recurso.COBERTURA_PREDICTIVA]


def test_el_gerente_de_marca_lee_su_linea():
    for r in RECURSOS_DE_LINEA:
        assert MATRIZ[r][Rol.GERENTE_MARCA] == (Accion.READ, Alcance.LINEA), r


def test_el_gerente_de_distrito_lee_su_linea():
    for r in RECURSOS_DE_LINEA:
        assert MATRIZ[r][Rol.GERENTE_DISTRITO] == (Accion.READ, Alcance.LINEA), r


def test_el_gerente_de_distrito_sigue_actuando_solo_sobre_su_equipo():
    """La otra mitad del acuerdo: lee su línea, escribe sobre su equipo."""
    accion, alcance = MATRIZ[Recurso.MEDICO_PANEL][Rol.GERENTE_DISTRITO]
    assert alcance == Alcance.TEAM, "aprobar médicos no puede alcanzar toda la línea"


def test_ningun_recurso_de_escritura_tiene_alcance_de_linea():
    """Barrido: si alguien añade `linea` a una celda de escritura, esto lo caza."""
    escrituras = {Accion.REGISTER, Accion.CONFIGURE, Accion.APPROVE}
    culpables = [(r, rol) for r, fila in MATRIZ.items() for rol, celda in fila.items()
                 if celda and celda[0] in escrituras and celda[1] == Alcance.LINEA]
    assert not culpables, culpables
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_authz_matriz.py -q -k linea`
Expected: FAIL — hoy esas celdas son `R_ALL` o `R_TEAM`.

- [ ] **Step 3: Ajustar las celdas**

En `backend/app/core/authz/matrix.py`, añadir la constante junto a las otras (`R_OWN`, `R_TEAM`, `R_ALL`):

```python
R_LINEA = (Accion.READ, Alcance.LINEA)
```

Y en las filas de `Recurso.RANKING_RKT`, `Recurso.PRODUCTIVIDAD_COMERCIAL` y `Recurso.COBERTURA_PREDICTIVA`, poner `R_LINEA` en las columnas de `GERENTE_DISTRITO` y `GERENTE_MARCA`. El resto de la fila no se toca.

- [ ] **Step 4: Correr el test y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_authz_matriz.py -q`
Expected: PASS.

- [ ] **Step 5: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: todo verde.

- [ ] **Step 6: Commit**

```bash
git add backend/app/core/authz/matrix.py backend/tests/test_authz_matriz.py
git commit -m "feat(alcance) matriz: el GD y el Gerente de Marca leen su linea completa"
```

---

## Task 5: Asignar países y líneas desde la interfaz

**Files:**
- Modify: `backend/app/api/v1/routers/admin.py` (endpoints de asignación)
- Modify: `frontend/src/pages/admin/Usuarios.tsx` (países del usuario)
- Modify: `frontend/src/pages/admin/Admin.tsx` (líneas del gerente)
- Test: `backend/tests/test_alcance_asignacion.py`

**Interfaces:**
- Consumes: `UsuarioPais`, `GerenteLinea` (Task 1).
- Produces: `GET/PUT /admin/usuarios/{id}/paises` y `GET/PUT /admin/gerentes/{id}/lineas`, ambos solo ADMIN.

- [ ] **Step 1: Escribir el test que falla**

```python
# backend/tests/test_alcance_asignacion.py
"""Asignación de países y líneas. Solo ADMIN.

`PUT` reemplaza el conjunto completo en vez de añadir: es lo que permite quitar un
país. Con un endpoint que solo agrega, revocar acceso exigiría un DELETE aparte
que se olvida — y el permiso de más no da ningún error.
"""
from app.services import alcance_service


def test_asignar_paises_reemplaza_el_conjunto(db, escenario):
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, ["DO"])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == {"DO"}


def test_dejar_la_lista_vacia_devuelve_el_acceso_total(db, escenario):
    """Vaciar = "todos los países", según el spec §3. Es la forma de revertir."""
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, [])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == set()


def test_asignar_dos_veces_el_mismo_pais_no_duplica(db, escenario):
    u = escenario["usuario_gt_hn"]
    alcance_service.fijar_paises(db, u.id, ["GT", "GT", "HN"])
    db.commit()
    assert alcance_service.paises_de(db, u.id) == {"GT", "HN"}


def test_asignar_lineas_reemplaza_el_conjunto(db, escenario):
    g = escenario["gerente_marca"]
    alcance_service.fijar_lineas(db, g.id, [escenario["linea_b"].id])
    db.commit()
    assert alcance_service.lineas_de(db, g.id) == {escenario["linea_b"].id}
```

- [ ] **Step 2: Correr el test y ver que falla**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_asignacion.py -q`
Expected: FAIL con `ModuleNotFoundError: No module named 'app.services.alcance_service'`

- [ ] **Step 3: Implementar el servicio**

```python
# backend/app/services/alcance_service.py
"""Asignación de países a usuarios y de líneas a gerentes.

`fijar_*` REEMPLAZA el conjunto completo, no añade. Con un endpoint que solo
agrega, revocar un acceso exigiría un DELETE aparte — y un permiso de más nunca
se manifiesta como error: simplemente funciona, hasta que alguien ve lo que no
debía.
"""
from sqlalchemy.orm import Session

from app.models.alcance import GerenteLinea, UsuarioPais


def paises_de(db: Session, usuario_id: int) -> set[str]:
    return {r[0] for r in db.query(UsuarioPais.pais_codigo)
            .filter(UsuarioPais.usuario_id == usuario_id).all()}


def fijar_paises(db: Session, usuario_id: int, codigos: list[str]) -> set[str]:
    db.query(UsuarioPais).filter(UsuarioPais.usuario_id == usuario_id).delete()
    for c in sorted(set(codigos)):
        db.add(UsuarioPais(usuario_id=usuario_id, pais_codigo=c))
    db.flush()
    return set(codigos)


def lineas_de(db: Session, gerente_id: int) -> set[int]:
    return {r[0] for r in db.query(GerenteLinea.linea_id)
            .filter(GerenteLinea.gerente_id == gerente_id).all()}


def fijar_lineas(db: Session, gerente_id: int, linea_ids: list[int]) -> set[int]:
    db.query(GerenteLinea).filter(GerenteLinea.gerente_id == gerente_id).delete()
    for lid in sorted(set(linea_ids)):
        db.add(GerenteLinea(gerente_id=gerente_id, linea_id=lid))
    db.flush()
    return set(linea_ids)
```

- [ ] **Step 4: Añadir los endpoints**

En `backend/app/api/v1/routers/admin.py`, junto a los demás de usuarios y gerentes:

```python
@router.get("/usuarios/{usuario_id}/paises", dependencies=[RequireAdmin])
def get_paises_usuario(usuario_id: int, db: Session = Depends(get_db)):
    return {"paises": sorted(alcance_service.paises_de(db, usuario_id))}


@router.put("/usuarios/{usuario_id}/paises", dependencies=[RequireAdmin])
def put_paises_usuario(usuario_id: int, payload: dict, db: Session = Depends(get_db)):
    """Lista vacía = todos los países (spec §3)."""
    alcance_service.fijar_paises(db, usuario_id, payload.get("paises", []))
    db.commit()
    return {"paises": sorted(alcance_service.paises_de(db, usuario_id))}


@router.get("/gerentes/{gerente_id}/lineas", dependencies=[RequireAdmin])
def get_lineas_gerente(gerente_id: int, db: Session = Depends(get_db)):
    return {"lineas": sorted(alcance_service.lineas_de(db, gerente_id))}


@router.put("/gerentes/{gerente_id}/lineas", dependencies=[RequireAdmin])
def put_lineas_gerente(gerente_id: int, payload: dict, db: Session = Depends(get_db)):
    alcance_service.fijar_lineas(db, gerente_id, payload.get("lineas", []))
    db.commit()
    return {"lineas": sorted(alcance_service.lineas_de(db, gerente_id))}
```

- [ ] **Step 5: Correr el test y ver que pasa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest tests/test_alcance_asignacion.py -q`
Expected: PASS (4 tests)

- [ ] **Step 6: Interfaz — países en Usuarios**

En `frontend/src/pages/admin/Usuarios.tsx`, dentro del diálogo de editar usuario, añadir un selector múltiple de países alimentado por el catálogo existente, con esta ayuda literal debajo:

```tsx
<FormHelperText>
  Sin países seleccionados, el usuario ve todos. Con países, solo esos.
</FormHelperText>
```

Ese texto no es decorativo: una lista vacía que significa "todo" es contraintuitiva, y sin decirlo un administrador puede creer que está restringiendo cuando está abriendo.

- [ ] **Step 7: Interfaz — líneas en Gerentes**

En la pestaña de Gerentes de `frontend/src/pages/admin/Admin.tsx`, añadir un selector múltiple de líneas que lea y escriba `/admin/gerentes/{id}/lineas`. Mantener el campo `linea_id` actual visible y en solo lectura, con la etiqueta "Línea principal (heredada)".

- [ ] **Step 8: Compilar el frontend**

Run: `cd frontend && npm run build`
Expected: build limpio.

- [ ] **Step 9: Correr la suite completa**

Run: `cd backend && ./venv/Scripts/python.exe -m pytest -q`
Expected: todo verde.

- [ ] **Step 10: Commit**

```bash
git add backend/app/services/alcance_service.py backend/app/api/v1/routers/admin.py backend/tests/test_alcance_asignacion.py frontend/src/pages/admin/
git commit -m "feat(alcance) asignacion de paises y lineas desde Administracion"
```

---

## Verificación final del plan contra el spec

| Spec | Tarea |
|---|---|
| §3 Modelo de datos, sin filas = todos | 1 |
| §4 `Alcance.LINEA` y `paises_visibles` | 2 |
| §4 El país antes que el alcance | 2 (test `test_el_pais_se_aplica_antes_que_la_linea`) |
| §5 Cero roles nuevos | — (no se toca el enum `Rol`) |
| §6 "Acceso total" no incluye configurar | — (la matriz ya lo cumple; el test de barrido de la Tarea 4 lo protege) |
| §7 `linea` solo en recursos de lectura | 4 (test `test_ningun_recurso_de_escritura_tiene_alcance_de_linea`) |
| §9.1–9.4 Frontera de país | 3 |
| §9.5–9.8 Alcance por línea | 2 |
| §9.9–9.10 GD lee línea, actúa sobre equipo | 4 |
| §9.11–9.12 Compatibilidad | 1 (backfill) y 2 (test `test_sin_paises_asignados_todo_sigue_igual`) |

**Seguimiento explícito, no olvido:** quedan ~100 endpoints que reciben `pais_codigo` sin la dependency `PaisPermitido` (Tarea 3, paso 5). Son catálogos y administración, ya restringidos por rol. Migrarlos es mecánico y debería hacerse antes de que Mallén opere en más de un país a la vez.
