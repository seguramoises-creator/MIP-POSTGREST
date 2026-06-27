# Módulo de Exámenes — Fase 1 (Fundación) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear la fundación backend del módulo de exámenes: el rol `CAPACITACION`, el esquema `exam` con sus 7 tablas, la limpieza del código muerto de Capacitación, y el CRUD de Examen/Preguntas/Opciones con publicación.

**Architecture:** Módulo autocontenido (esquema `exam`). Se sigue el patrón existente del proyecto: modelos SQLAlchemy 2.0 (`Mapped`/`mapped_column`), migraciones Alembic idempotentes, routers FastAPI con prefijo y constantes RBAC, servicios que reciben `db: Session`. Tests unitarios con dobles (`MagicMock`) para lógica de negocio; verificación de esquema contra la BD real para migraciones.

**Tech Stack:** Python 3.13, FastAPI, SQLAlchemy 2.0, Alembic, pymssql/SQL Server, Pydantic v2, pytest.

**Spec de referencia:** `docs/superpowers/specs/2026-06-26-modulo-examenes-design.md`

## Global Constraints

- Modelos: SQLAlchemy 2.0 `Mapped[tipo]` + `mapped_column()`. **Nunca** `Column()` antiguo.
- Base declarativa: `from app.db.database import Base`.
- Esquema BD: `exam` (minúscula), tablas PascalCase (ej. `DimExamen`), como el módulo `cat`.
- Migraciones: generar el stub con `./venv/Scripts/alembic.exe revision -m "..."` (id único + `down_revision` correcto). Cuerpo **idempotente** (crear esquema/tabla solo si no existe), estilo de las migraciones existentes.
- Migración head actual: `7fc6c15162a2`. Las migraciones de esta fase encadenan sobre el head vigente.
- Alembic se ejecuta con `./venv/Scripts/alembic.exe` (venv). El intérprete del proyecto es `./venv/Scripts/python.exe`.
- Routers: `APIRouter(prefix="/examenes", tags=["Exámenes"])`; constantes RBAC como `Depends(require_roles(...))` a nivel de módulo.
- Timestamps: `datetime.now(timezone.utc)`. Nunca `utcnow()`.
- Logs: `from loguru import logger`. Nunca `print()`.
- Tests corren con `./venv/Scripts/python.exe -m pytest -q` desde `backend/`. CI ya configurado en `.github/workflows/ci.yml`.
- Todos los comandos se ejecutan desde `C:\Users\Lenovo\Proyecto\MSM\backend` salvo que se indique la raíz.

## Estructura de archivos (Fase 1)

| Archivo | Responsabilidad |
|---------|-----------------|
| `app/models/usuario.py` (modificar) | Agregar `CAPACITACION` al enum `Rol` |
| `app/models/exam_models.py` (crear) | Modelos ORM del esquema `exam` |
| `app/api/v1/routers/capacitacion.py` (eliminar) | Código muerto |
| `frontend/src/pages/capacitacion/Capacitacion.tsx` (eliminar) | Código muerto |
| `app/schemas/examenes.py` (crear) | Schemas Pydantic del módulo |
| `app/services/examen_service.py` (crear) | CRUD + publicación |
| `app/api/v1/routers/examenes.py` (crear) | Endpoints `/examenes` |
| `app/api/v1/router.py` (modificar) | Registrar el router |
| `alembic/versions/*` (crear) | Migración del rol + migración del esquema `exam` |
| `tests/test_examen_service.py` (crear) | Tests de lógica de negocio |

---

### Task 1: Agregar rol `CAPACITACION`

**Files:**
- Modify: `app/models/usuario.py` (enum `Rol`)
- Create: `alembic/versions/<rev>_agregar_rol_capacitacion.py`
- Test: `tests/test_examen_service.py` (test del enum)

**Interfaces:**
- Produces: `Rol.CAPACITACION` (valor `"CAPACITACION"`), usable en `require_roles(...)`.

- [ ] **Step 1: Escribir el test que falla**

Crear `backend/tests/test_examen_service.py` con:

```python
from app.models.usuario import Rol


def test_rol_capacitacion_existe():
    assert Rol.CAPACITACION.value == "CAPACITACION"
```

- [ ] **Step 2: Correr el test y verificar que falla**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py::test_rol_capacitacion_existe -q`
Expected: FAIL con `AttributeError: CAPACITACION`.

- [ ] **Step 3: Agregar el valor al enum**

En `app/models/usuario.py`, dentro de `class Rol(str, PyEnum):`, agregar tras `GERENTE_MARCA`:

```python
    CAPACITACION           = "CAPACITACION"
```

- [ ] **Step 4: Correr el test y verificar que pasa**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py::test_rol_capacitacion_existe -q`
Expected: PASS.

- [ ] **Step 5: Generar el stub de migración**

Run: `./venv/Scripts/alembic.exe revision -m "agregar rol CAPACITACION"`
Anotar el archivo generado (`alembic/versions/<rev>_agregar_rol_capacitacion.py`).

- [ ] **Step 6: Escribir el cuerpo de la migración**

La columna `Security.DIM_Usuario.rol` es un `Enum` de SQLAlchemy → en SQL Server es `VARCHAR` con un `CHECK`. Reemplazar el `CHECK` para admitir el nuevo valor. Reemplazar `upgrade`/`downgrade` del stub por:

```python
from alembic import op
from sqlalchemy import text

# (mantener las variables revision/down_revision que generó alembic)

_VALORES_NUEVOS = (
    "'ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD',"
    "'GERENTE_DISTRITO','GERENTE_MARCA','REPRESENTANTE_MEDICO','CONSULTA','CAPACITACION'"
)
_VALORES_VIEJOS = (
    "'ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD',"
    "'GERENTE_DISTRITO','GERENTE_MARCA','REPRESENTANTE_MEDICO','CONSULTA'"
)


def _nombre_check(conn):
    row = conn.execute(text(
        "SELECT cc.name FROM sys.check_constraints cc "
        "JOIN sys.columns c ON c.object_id=cc.parent_object_id AND c.column_id=cc.parent_column_id "
        "WHERE cc.parent_object_id=OBJECT_ID('Security.DIM_Usuario') AND c.name='rol'"
    )).fetchone()
    return row[0] if row else None


def upgrade() -> None:
    conn = op.get_bind()
    nombre = _nombre_check(conn)
    if nombre:
        conn.execute(text(f"ALTER TABLE [Security].[DIM_Usuario] DROP CONSTRAINT [{nombre}]"))
    conn.execute(text(
        f"ALTER TABLE [Security].[DIM_Usuario] ADD CONSTRAINT CK_DIM_Usuario_rol "
        f"CHECK (rol IN ({_VALORES_NUEVOS}))"
    ))


def downgrade() -> None:
    conn = op.get_bind()
    nombre = _nombre_check(conn)
    if nombre:
        conn.execute(text(f"ALTER TABLE [Security].[DIM_Usuario] DROP CONSTRAINT [{nombre}]"))
    conn.execute(text(
        f"ALTER TABLE [Security].[DIM_Usuario] ADD CONSTRAINT CK_DIM_Usuario_rol "
        f"CHECK (rol IN ({_VALORES_VIEJOS}))"
    ))
```

- [ ] **Step 7: Aplicar la migración y verificar**

Run: `./venv/Scripts/alembic.exe upgrade head`
Expected: log `Running upgrade 7fc6c15162a2 -> <rev>`.
Verificar el CHECK admite el valor:
```bash
./venv/Scripts/python.exe -c "from app.db.database import engine; from sqlalchemy import text; \
c=engine.connect(); \
print(c.execute(text(\"SELECT 1 WHERE 'CAPACITACION' IN (SELECT value FROM STRING_SPLIT(REPLACE(REPLACE((SELECT definition FROM sys.check_constraints WHERE name='CK_DIM_Usuario_rol'),'(',''),')',''),','))\")).fetchone())"
```
(Alternativa simple: confirmar que la migración aplicó sin error.)

- [ ] **Step 8: Commit**

```bash
git add app/models/usuario.py alembic/versions/ tests/test_examen_service.py
git commit -m "feat(examenes): agregar rol CAPACITACION"
```

---

### Task 2: Eliminar el código muerto de Capacitación

**Files:**
- Delete: `app/api/v1/routers/capacitacion.py`
- Delete: `frontend/src/pages/capacitacion/Capacitacion.tsx`

**Interfaces:** ninguna nueva. (Confirma que nada los importa.)

- [ ] **Step 1: Verificar que el router muerto no está registrado ni importado**

Run: `grep -rn "capacitacion" backend/app/api/v1/router.py backend/app/main.py`
Expected: sin coincidencias de import de `routers.capacitacion` (la línea de `categorizacion` con el comentario "sustituye a /capacitacion" es texto, no import — está OK).

- [ ] **Step 2: Verificar que la página muerta no tiene ruta**

Run: `grep -rn "Capacitacion" frontend/src/App.tsx`
Expected: sin ruta a `pages/capacitacion/Capacitacion`.

- [ ] **Step 3: Eliminar los archivos**

```bash
git rm backend/app/api/v1/routers/capacitacion.py
git rm frontend/src/pages/capacitacion/Capacitacion.tsx
```

- [ ] **Step 4: Verificar que el backend importa y el frontend compila**

Run: `cd backend && ./venv/Scripts/python.exe -c "from app.main import app; print('OK', len(app.routes))"`
Expected: `OK <n>` sin errores.
Run: `cd frontend && ./node_modules/.bin/tsc -b`
Expected: exit 0.

- [ ] **Step 5: Commit**

```bash
git commit -m "chore(examenes): eliminar codigo muerto de Capacitacion (sustituido por Examenes)"
```

---

### Task 3: Modelos ORM del esquema `exam` + migración

**Files:**
- Create: `app/models/exam_models.py`
- Modify: `alembic/env.py` (importar el módulo de modelos)
- Create: `alembic/versions/<rev>_exam_schema.py`
- Test: verificación de esquema contra la BD real

**Interfaces:**
- Produces: clases `Examen`, `Pregunta`, `PreguntaOpcion`, `AsignacionExamen`, `IntentoExamen`, `IntentoRespuesta`, `FuenteIA` (esquema `exam`), importables desde `app.models.exam_models`.

- [ ] **Step 1: Crear el archivo de modelos**

Crear `app/models/exam_models.py`:

```python
"""
SCGCPR — Modelos del Módulo de Exámenes (esquema `exam`).
Módulo autocontenido. Evaluado polimórfico: RM (Config.DIM_RM) o Gerente
(Config.DIM_Gerente). Ver docs/superpowers/specs/2026-06-26-modulo-examenes-design.md
"""
from datetime import datetime, timezone

from sqlalchemy import (
    Integer, String, Boolean, DateTime, Numeric, Text, ForeignKey, CheckConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.database import Base


def _ahora() -> datetime:
    return datetime.now(timezone.utc)


class Examen(Base):
    __tablename__ = "DimExamen"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    nombre: Mapped[str] = mapped_column(String(200), nullable=False)
    producto: Mapped[str | None] = mapped_column(String(200), nullable=True)
    nota_minima: Mapped[int] = mapped_column(Integer, nullable=False, default=70)
    tiempo_limite_min: Mapped[int | None] = mapped_column(Integer, nullable=True)
    estado: Mapped[str] = mapped_column(String(20), nullable=False, default="borrador")
    fuente: Mapped[str] = mapped_column(String(10), nullable=False, default="manual")
    rand_preguntas: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    rand_opciones: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    creado_por_usuario_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=False)
    indicador_codigo: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ciclo_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Ciclo.id"), nullable=True)
    fecha_creacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_publicacion: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    preguntas: Mapped[list["Pregunta"]] = relationship(
        "Pregunta", back_populates="examen", cascade="all, delete-orphan")


class Pregunta(Base):
    __tablename__ = "DimPregunta"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=False)
    tipo: Mapped[str] = mapped_column(String(10), nullable=False, default="multi")
    escenario: Mapped[str | None] = mapped_column(Text, nullable=True)
    texto: Mapped[str] = mapped_column(Text, nullable=False)
    explicacion: Mapped[str | None] = mapped_column(Text, nullable=True)
    orden: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    examen: Mapped["Examen"] = relationship("Examen", back_populates="preguntas")
    opciones: Mapped[list["PreguntaOpcion"]] = relationship(
        "PreguntaOpcion", back_populates="pregunta", cascade="all, delete-orphan")


class PreguntaOpcion(Base):
    __tablename__ = "DimPreguntaOpcion"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pregunta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimPregunta.id"), nullable=False)
    texto_opcion: Mapped[str] = mapped_column(Text, nullable=False)
    indice_original: Mapped[int] = mapped_column(Integer, nullable=False)
    es_correcta: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    activo: Mapped[bool] = mapped_column(Boolean, default=True)

    pregunta: Mapped["Pregunta"] = relationship("Pregunta", back_populates="opciones")


class AsignacionExamen(Base):
    __tablename__ = "FactAsignacionExamen"
    __table_args__ = (
        CheckConstraint(
            "(evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
            "(evaluado_rm_id IS NULL AND evaluado_gerente_id IS NOT NULL)",
            name="CK_AsignacionExamen_evaluado_unico",
        ),
        {"schema": "exam"},
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=False)
    evaluado_tipo: Mapped[str] = mapped_column(String(10), nullable=False)  # RM | GERENTE
    evaluado_rm_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=True)
    evaluado_gerente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    fecha_asignacion: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_limite: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    intentos_max: Mapped[int | None] = mapped_column(Integer, nullable=True)
    intentos_usados: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    estado: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    notif_activa: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class IntentoExamen(Base):
    __tablename__ = "FactIntentoExamen"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    asignacion_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.FactAsignacionExamen.id"), nullable=False)
    evaluado_tipo: Mapped[str] = mapped_column(String(10), nullable=False)
    evaluado_rm_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_RM.id"), nullable=True)
    evaluado_gerente_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Config.DIM_Gerente.id"), nullable=True)
    fecha_inicio: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
    fecha_fin: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    score: Mapped[float | None] = mapped_column(Numeric(5, 2), nullable=True)
    aprobado: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    tiempo_usado_seg: Mapped[int | None] = mapped_column(Integer, nullable=True)
    orden_preguntas_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    user_agent: Mapped[str | None] = mapped_column(String(400), nullable=True)
    device_type: Mapped[str | None] = mapped_column(String(40), nullable=True)
    plataforma: Mapped[str | None] = mapped_column(String(40), nullable=True)
    ip_cliente: Mapped[str | None] = mapped_column(String(50), nullable=True)


class IntentoRespuesta(Base):
    __tablename__ = "FactIntentoRespuesta"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    intento_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.FactIntentoExamen.id"), nullable=False)
    pregunta_id: Mapped[int] = mapped_column(
        Integer, ForeignKey("exam.DimPregunta.id"), nullable=False)
    opcion_elegida_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam.DimPreguntaOpcion.id"), nullable=True)
    indice_opcion_presentada: Mapped[int | None] = mapped_column(Integer, nullable=True)
    indice_original_elegido: Mapped[int | None] = mapped_column(Integer, nullable=True)
    es_correcta: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    mapa_opciones_json: Mapped[str | None] = mapped_column(Text, nullable=True)
    fecha_respuesta: Mapped[datetime] = mapped_column(DateTime, default=_ahora)


class FuenteIA(Base):
    __tablename__ = "FactFuenteIA"
    __table_args__ = {"schema": "exam"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    examen_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("exam.DimExamen.id"), nullable=True)
    tipo_archivo: Mapped[str | None] = mapped_column(String(20), nullable=True)
    nombre_archivo: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ruta_archivo: Mapped[str | None] = mapped_column(String(400), nullable=True)
    texto_extraido_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    prompt_usado: Mapped[str | None] = mapped_column(Text, nullable=True)
    estado_generacion: Mapped[str] = mapped_column(String(15), nullable=False, default="pendiente")
    mensaje_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    cargado_por_usuario_id: Mapped[int | None] = mapped_column(
        Integer, ForeignKey("Security.DIM_Usuario.id"), nullable=True)
    fecha_carga: Mapped[datetime] = mapped_column(DateTime, default=_ahora)
```

- [ ] **Step 2: Registrar el módulo en alembic/env.py**

En `alembic/env.py`, junto a los otros imports de modelos (la línea `from app.models import usuario, dimensiones, hechos`), agregar:

```python
from app.models import exam_models  # noqa: F401,E402  ← esquema exam (Módulo de Exámenes)
```

- [ ] **Step 3: Verificar que los modelos importan**

Run: `./venv/Scripts/python.exe -c "from app.models import exam_models; print('OK', exam_models.Examen.__tablename__)"`
Expected: `OK DimExamen`.

- [ ] **Step 4: Generar el stub de migración**

Run: `./venv/Scripts/alembic.exe revision -m "crear esquema exam (modulo examenes)"`

- [ ] **Step 5: Escribir el cuerpo de la migración (idempotente)**

Reemplazar `upgrade`/`downgrade` del stub. Crea el esquema `exam` y las 7 tablas con `op.create_table` (schema="exam"), solo si no existen. Usar exactamente los nombres/columnas de los modelos. Patrón:

```python
from alembic import op
import sqlalchemy as sa
from sqlalchemy import text

# (mantener revision/down_revision generados)

def _tabla_existe(conn, tabla: str) -> bool:
    return conn.execute(text(
        "SELECT 1 FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='exam' AND TABLE_NAME=:t"
    ), {"t": tabla}).fetchone() is not None


def upgrade() -> None:
    conn = op.get_bind()
    conn.execute(text(
        "IF NOT EXISTS (SELECT 1 FROM sys.schemas WHERE name='exam') EXEC('CREATE SCHEMA [exam]')"
    ))

    if not _tabla_existe(conn, "DimExamen"):
        op.create_table(
            "DimExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("nombre", sa.String(200), nullable=False),
            sa.Column("producto", sa.String(200), nullable=True),
            sa.Column("nota_minima", sa.Integer, nullable=False, server_default="70"),
            sa.Column("tiempo_limite_min", sa.Integer, nullable=True),
            sa.Column("estado", sa.String(20), nullable=False, server_default="borrador"),
            sa.Column("fuente", sa.String(10), nullable=False, server_default="manual"),
            sa.Column("rand_preguntas", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("rand_opciones", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("creado_por_usuario_id", sa.Integer,
                      sa.ForeignKey("Security.DIM_Usuario.id"), nullable=False),
            sa.Column("indicador_codigo", sa.String(50), nullable=True),
            sa.Column("ciclo_id", sa.Integer, sa.ForeignKey("Config.DIM_Ciclo.id"), nullable=True),
            sa.Column("fecha_creacion", sa.DateTime, nullable=True),
            sa.Column("fecha_publicacion", sa.DateTime, nullable=True),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "DimPregunta"):
        op.create_table(
            "DimPregunta",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=False),
            sa.Column("tipo", sa.String(10), nullable=False, server_default="multi"),
            sa.Column("escenario", sa.Text, nullable=True),
            sa.Column("texto", sa.Text, nullable=False),
            sa.Column("explicacion", sa.Text, nullable=True),
            sa.Column("orden", sa.Integer, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "DimPreguntaOpcion"):
        op.create_table(
            "DimPreguntaOpcion",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("pregunta_id", sa.Integer, sa.ForeignKey("exam.DimPregunta.id"), nullable=False),
            sa.Column("texto_opcion", sa.Text, nullable=False),
            sa.Column("indice_original", sa.Integer, nullable=False),
            sa.Column("es_correcta", sa.Boolean, nullable=False, server_default="0"),
            sa.Column("activo", sa.Boolean, nullable=True, server_default="1"),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactAsignacionExamen"):
        op.create_table(
            "FactAsignacionExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=False),
            sa.Column("evaluado_tipo", sa.String(10), nullable=False),
            sa.Column("evaluado_rm_id", sa.Integer, sa.ForeignKey("Config.DIM_RM.id"), nullable=True),
            sa.Column("evaluado_gerente_id", sa.Integer,
                      sa.ForeignKey("Config.DIM_Gerente.id"), nullable=True),
            sa.Column("fecha_asignacion", sa.DateTime, nullable=True),
            sa.Column("fecha_limite", sa.DateTime, nullable=True),
            sa.Column("intentos_max", sa.Integer, nullable=True),
            sa.Column("intentos_usados", sa.Integer, nullable=False, server_default="0"),
            sa.Column("estado", sa.String(15), nullable=False, server_default="pendiente"),
            sa.Column("notif_activa", sa.Boolean, nullable=False, server_default="0"),
            sa.CheckConstraint(
                "(evaluado_rm_id IS NOT NULL AND evaluado_gerente_id IS NULL) OR "
                "(evaluado_rm_id IS NULL AND evaluado_gerente_id IS NOT NULL)",
                name="CK_AsignacionExamen_evaluado_unico"),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactIntentoExamen"):
        op.create_table(
            "FactIntentoExamen",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("asignacion_id", sa.Integer,
                      sa.ForeignKey("exam.FactAsignacionExamen.id"), nullable=False),
            sa.Column("evaluado_tipo", sa.String(10), nullable=False),
            sa.Column("evaluado_rm_id", sa.Integer, sa.ForeignKey("Config.DIM_RM.id"), nullable=True),
            sa.Column("evaluado_gerente_id", sa.Integer,
                      sa.ForeignKey("Config.DIM_Gerente.id"), nullable=True),
            sa.Column("fecha_inicio", sa.DateTime, nullable=True),
            sa.Column("fecha_fin", sa.DateTime, nullable=True),
            sa.Column("score", sa.Numeric(5, 2), nullable=True),
            sa.Column("aprobado", sa.Boolean, nullable=True),
            sa.Column("tiempo_usado_seg", sa.Integer, nullable=True),
            sa.Column("orden_preguntas_json", sa.Text, nullable=True),
            sa.Column("user_agent", sa.String(400), nullable=True),
            sa.Column("device_type", sa.String(40), nullable=True),
            sa.Column("plataforma", sa.String(40), nullable=True),
            sa.Column("ip_cliente", sa.String(50), nullable=True),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactIntentoRespuesta"):
        op.create_table(
            "FactIntentoRespuesta",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("intento_id", sa.Integer,
                      sa.ForeignKey("exam.FactIntentoExamen.id"), nullable=False),
            sa.Column("pregunta_id", sa.Integer, sa.ForeignKey("exam.DimPregunta.id"), nullable=False),
            sa.Column("opcion_elegida_id", sa.Integer,
                      sa.ForeignKey("exam.DimPreguntaOpcion.id"), nullable=True),
            sa.Column("indice_opcion_presentada", sa.Integer, nullable=True),
            sa.Column("indice_original_elegido", sa.Integer, nullable=True),
            sa.Column("es_correcta", sa.Boolean, nullable=True),
            sa.Column("mapa_opciones_json", sa.Text, nullable=True),
            sa.Column("fecha_respuesta", sa.DateTime, nullable=True),
            schema="exam",
        )

    if not _tabla_existe(conn, "FactFuenteIA"):
        op.create_table(
            "FactFuenteIA",
            sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
            sa.Column("examen_id", sa.Integer, sa.ForeignKey("exam.DimExamen.id"), nullable=True),
            sa.Column("tipo_archivo", sa.String(20), nullable=True),
            sa.Column("nombre_archivo", sa.String(300), nullable=True),
            sa.Column("ruta_archivo", sa.String(400), nullable=True),
            sa.Column("texto_extraido_hash", sa.String(64), nullable=True),
            sa.Column("prompt_usado", sa.Text, nullable=True),
            sa.Column("estado_generacion", sa.String(15), nullable=False, server_default="pendiente"),
            sa.Column("mensaje_error", sa.Text, nullable=True),
            sa.Column("cargado_por_usuario_id", sa.Integer,
                      sa.ForeignKey("Security.DIM_Usuario.id"), nullable=True),
            sa.Column("fecha_carga", sa.DateTime, nullable=True),
            schema="exam",
        )


def downgrade() -> None:
    for t in ("FactFuenteIA", "FactIntentoRespuesta", "FactIntentoExamen",
              "FactAsignacionExamen", "DimPreguntaOpcion", "DimPregunta", "DimExamen"):
        op.execute(f"IF OBJECT_ID('exam.{t}') IS NOT NULL DROP TABLE [exam].[{t}]")
```

- [ ] **Step 6: Aplicar la migración**

Run: `./venv/Scripts/alembic.exe upgrade head`
Expected: `Running upgrade <rev_task1> -> <rev_task3>`.

- [ ] **Step 7: Verificar las 7 tablas en la BD**

Run:
```bash
./venv/Scripts/python.exe -c "from app.db.database import engine; from sqlalchemy import text; \
c=engine.connect(); \
print(sorted(r[0] for r in c.execute(text(\"SELECT TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA='exam'\")).fetchall()))"
```
Expected: las 7 tablas (`DimExamen`, `DimPregunta`, `DimPreguntaOpcion`, `FactAsignacionExamen`, `FactIntentoExamen`, `FactIntentoRespuesta`, `FactFuenteIA`).

- [ ] **Step 8: Commit**

```bash
git add app/models/exam_models.py alembic/
git commit -m "feat(examenes): esquema exam + 7 tablas (modelos y migracion)"
```

---

### Task 4: Schemas Pydantic + servicio de creación/lectura de Examen

**Files:**
- Create: `app/schemas/examenes.py`
- Create: `app/services/examen_service.py`
- Test: `tests/test_examen_service.py`

**Interfaces:**
- Produces:
  - `ExamenCrear` (Pydantic: `nombre: str`, `producto: str|None`, `nota_minima: int=70`, `tiempo_limite_min: int|None`, `rand_preguntas: bool=False`, `rand_opciones: bool=False`, `indicador_codigo: str|None`, `ciclo_id: int|None`).
  - `examen_service.crear_examen(db, datos: ExamenCrear, creado_por_usuario_id: int) -> Examen`
  - `examen_service.listar_examenes(db) -> list[Examen]`
  - `examen_service.obtener_examen(db, examen_id: int) -> Examen | None`

- [ ] **Step 1: Crear los schemas**

Crear `app/schemas/examenes.py`:

```python
from datetime import datetime
from pydantic import BaseModel, ConfigDict, Field


class ExamenCrear(BaseModel):
    nombre: str = Field(min_length=1, max_length=200)
    producto: str | None = None
    nota_minima: int = Field(default=70, ge=0, le=100)
    tiempo_limite_min: int | None = Field(default=None, ge=1)
    rand_preguntas: bool = False
    rand_opciones: bool = False
    indicador_codigo: str | None = None
    ciclo_id: int | None = None


class ExamenResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nombre: str
    producto: str | None
    nota_minima: int
    tiempo_limite_min: int | None
    estado: str
    fuente: str
    rand_preguntas: bool
    rand_opciones: bool
    indicador_codigo: str | None
    ciclo_id: int | None
    fecha_creacion: datetime
    fecha_publicacion: datetime | None
```

- [ ] **Step 2: Escribir el test de creación (lógica pura)**

Agregar a `tests/test_examen_service.py`:

```python
from unittest.mock import MagicMock
from app.services import examen_service
from app.schemas.examenes import ExamenCrear


def test_crear_examen_arranca_en_borrador_manual():
    db = MagicMock()
    datos = ExamenCrear(nombre="Producto X", producto="X")
    examen = examen_service.crear_examen(db, datos, creado_por_usuario_id=1)
    assert examen.estado == "borrador"
    assert examen.fuente == "manual"
    assert examen.nombre == "Producto X"
    assert db.add.called and db.commit.called
```

- [ ] **Step 3: Correr el test y verificar que falla**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py::test_crear_examen_arranca_en_borrador_manual -q`
Expected: FAIL (`examen_service` no tiene `crear_examen`).

- [ ] **Step 4: Implementar el servicio**

Crear `app/services/examen_service.py`:

```python
"""SCGCPR — Servicio del Módulo de Exámenes: CRUD y ciclo de vida."""
from loguru import logger
from sqlalchemy.orm import Session

from app.models.exam_models import Examen
from app.schemas.examenes import ExamenCrear


def crear_examen(db: Session, datos: ExamenCrear, creado_por_usuario_id: int) -> Examen:
    examen = Examen(
        nombre=datos.nombre,
        producto=datos.producto,
        nota_minima=datos.nota_minima,
        tiempo_limite_min=datos.tiempo_limite_min,
        rand_preguntas=datos.rand_preguntas,
        rand_opciones=datos.rand_opciones,
        indicador_codigo=datos.indicador_codigo,
        ciclo_id=datos.ciclo_id,
        creado_por_usuario_id=creado_por_usuario_id,
        estado="borrador",
        fuente="manual",
    )
    db.add(examen)
    db.commit()
    db.refresh(examen)
    logger.info(f"Examen creado id={examen.id} '{examen.nombre}'")
    return examen


def listar_examenes(db: Session) -> list[Examen]:
    return db.query(Examen).filter(Examen.activo == True).order_by(Examen.id.desc()).all()


def obtener_examen(db: Session, examen_id: int) -> Examen | None:
    return db.query(Examen).filter(Examen.id == examen_id).first()
```

- [ ] **Step 5: Correr el test y verificar que pasa**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py::test_crear_examen_arranca_en_borrador_manual -q`
Expected: PASS.

- [ ] **Step 6: Commit**

```bash
git add app/schemas/examenes.py app/services/examen_service.py tests/test_examen_service.py
git commit -m "feat(examenes): schemas + servicio crear/listar/obtener examen"
```

---

### Task 5: Publicar examen (regla RN-02)

**Files:**
- Modify: `app/services/examen_service.py`
- Test: `tests/test_examen_service.py`

**Interfaces:**
- Produces: `examen_service.publicar_examen(db, examen_id: int) -> Examen` — lanza `ValueError` si el examen no tiene preguntas (RN-02) o no está en `borrador`.

- [ ] **Step 1: Escribir los tests**

Agregar a `tests/test_examen_service.py`:

```python
import pytest
from types import SimpleNamespace
from datetime import datetime, timezone


def test_publicar_sin_preguntas_falla(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador", preguntas=[], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    with pytest.raises(ValueError):
        examen_service.publicar_examen(db, 1)


def test_publicar_con_preguntas_activa(monkeypatch):
    db = MagicMock()
    examen = SimpleNamespace(id=1, estado="borrador",
                             preguntas=[SimpleNamespace(id=9)], fecha_publicacion=None)
    monkeypatch.setattr(examen_service, "obtener_examen", lambda d, i: examen)
    resultado = examen_service.publicar_examen(db, 1)
    assert resultado.estado == "activo"
    assert resultado.fecha_publicacion is not None
    assert db.commit.called
```

- [ ] **Step 2: Correr los tests y verificar que fallan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k publicar -q`
Expected: FAIL (`publicar_examen` no existe).

- [ ] **Step 3: Implementar `publicar_examen`**

Agregar a `app/services/examen_service.py` (imports arriba: `from datetime import datetime, timezone`):

```python
def publicar_examen(db: Session, examen_id: int) -> Examen:
    examen = obtener_examen(db, examen_id)
    if examen is None:
        raise ValueError("Examen no encontrado")
    if examen.estado != "borrador":
        raise ValueError(f"Solo se publica un examen en borrador (estado actual: {examen.estado})")
    if not examen.preguntas:  # RN-02
        raise ValueError("El examen debe tener al menos 1 pregunta para publicarse")
    examen.estado = "activo"
    examen.fecha_publicacion = datetime.now(timezone.utc)
    db.commit()
    db.refresh(examen)
    logger.info(f"Examen id={examen.id} publicado")
    return examen
```

- [ ] **Step 4: Correr los tests y verificar que pasan**

Run: `./venv/Scripts/python.exe -m pytest tests/test_examen_service.py -k publicar -q`
Expected: PASS (2 tests).

- [ ] **Step 5: Commit**

```bash
git add app/services/examen_service.py tests/test_examen_service.py
git commit -m "feat(examenes): publicar examen con validacion RN-02"
```

---

### Task 6: Router `/examenes` + RBAC + registro

**Files:**
- Create: `app/api/v1/routers/examenes.py`
- Modify: `app/api/v1/router.py`
- Test: smoke de arranque de la app

**Interfaces:**
- Consumes: `examen_service.crear_examen/listar_examenes/obtener_examen/publicar_examen`; `require_roles` de `app.core.deps`; `Rol` de `app.models.usuario`; `get_db` de `app.db.database`; `get_current_active_user` de `app.core.deps`.
- Produces: router `examenes_router` registrado en `api_router`. Endpoints: `POST /examenes`, `GET /examenes`, `GET /examenes/{id}`, `POST /examenes/{id}/publicar`.

- [ ] **Step 1: Crear el router**

Crear `app/api/v1/routers/examenes.py`:

```python
"""SCGCPR — Router del Módulo de Exámenes."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.core.deps import require_roles, get_current_active_user
from app.db.database import get_db
from app.models.usuario import Rol, Usuario
from app.schemas.examenes import ExamenCrear, ExamenResponse
from app.services import examen_service

router = APIRouter(prefix="/examenes", tags=["Exámenes"])

RequireCapacitacion = Depends(require_roles(Rol.ADMIN, Rol.CAPACITACION))


@router.post("", response_model=ExamenResponse, status_code=status.HTTP_201_CREATED)
def crear(
    datos: ExamenCrear,
    db: Session = Depends(get_db),
    usuario: Usuario = RequireCapacitacion,
):
    return examen_service.crear_examen(db, datos, creado_por_usuario_id=usuario.id)


@router.get("", response_model=list[ExamenResponse])
def listar(db: Session = Depends(get_db), usuario: Usuario = RequireCapacitacion):
    return examen_service.listar_examenes(db)


@router.get("/{examen_id}", response_model=ExamenResponse)
def obtener(examen_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireCapacitacion):
    examen = examen_service.obtener_examen(db, examen_id)
    if examen is None:
        raise HTTPException(status_code=404, detail="Examen no encontrado")
    return examen


@router.post("/{examen_id}/publicar", response_model=ExamenResponse)
def publicar(examen_id: int, db: Session = Depends(get_db), usuario: Usuario = RequireCapacitacion):
    try:
        return examen_service.publicar_examen(db, examen_id)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
```

> Nota: verificar la firma real de `require_roles` y `get_current_active_user` en `app/core/deps.py` antes de implementar; ajustar el patrón de la constante `RequireCapacitacion` para que coincida con cómo lo hacen los otros routers (ej. `lsii.py`).

- [ ] **Step 2: Registrar el router**

En `app/api/v1/router.py`, agregar el import junto a los demás:

```python
from app.api.v1.routers.examenes import router as examenes_router
```

y el registro junto a los otros `include_router`:

```python
api_router.include_router(examenes_router)
```

- [ ] **Step 3: Verificar que la app arranca y expone las rutas**

Run:
```bash
./venv/Scripts/python.exe -c "from app.main import app; \
print([r.path for r in app.routes if '/examenes' in getattr(r,'path','')])"
```
Expected: lista con `/api/v1/examenes`, `/api/v1/examenes/{examen_id}`, `/api/v1/examenes/{examen_id}/publicar`.

- [ ] **Step 4: Correr toda la suite**

Run: `./venv/Scripts/python.exe -m pytest -q`
Expected: todos los tests pasan (incluye los nuevos de examen).

- [ ] **Step 5: Commit**

```bash
git add app/api/v1/routers/examenes.py app/api/v1/router.py
git commit -m "feat(examenes): router /examenes (CRUD + publicar) con RBAC CAPACITACION"
```

---

## Self-Review (cobertura del spec, Fase 1)

- **Rol CAPACITACION (§1):** Task 1. ✓
- **Esquema exam + 7 tablas (§2):** Task 3. ✓
- **Tomador polimórfico + CHECK (§2):** Task 3 (CheckConstraint en `FactAsignacionExamen`/modelo + migración). ✓
- **Limpieza código muerto (§1):** Task 2. ✓
- **CRUD examen + publicar RN-02 (§3, §13.1, §13.3):** Tasks 4–6. ✓
- **RBAC (§1, §9):** Task 6 (`RequireCapacitacion`). ✓
- Pendiente de fases siguientes (fuera de Fase 1): CRUD de preguntas/opciones con reorder, asignación, tomar/corregir, IA, KPIs, frontend, puente EVAL_CONOCIMIENTOS. Cada uno tendrá su plan.

> Nota de fase: el CRUD de **preguntas/opciones** (agregar/editar/eliminar/reordenar) es necesario para que "publicar con ≥1 pregunta" sea útil de punta a punta. Está planificado como primer bloque de la **Fase 2**, antes de asignación/tomar. Si se prefiere, puede adelantarse a Fase 1 como Task 7 siguiendo el mismo patrón TDD de Tasks 4–5.
