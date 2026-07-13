# Maestro de Médicos — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Crear un Maestro de Médicos país-level (fuente única del dato general del médico) promoviendo `Config.DIM_Medico`, con dedup en cascada, CRUD, importación Excel y puente bidireccional con el Panel Médico — reorganizando la sección Médicos en dos subpestañas (Categorización | Maestro).

**Architecture:** Se promueve la tabla existente `Config.DIM_Medico` a Maestro canónico (país-level, 1 fila por médico físico), enriquecida con los campos generales que hoy viven duplicados en `Visita.DIM_MedicoVisita`. El Panel Médico (`DIM_MedicoVisita`) gana un FK `maestro_medico_id` y pasa a ser una **asignación** médico↔representante que referencia al maestro; sus campos generales se sincronizan hacia el maestro, nunca al revés. La Categorización (esquema `cat.*`, snapshot por período) no se toca — solo se cruza por referencia. Backend FastAPI + SQLAlchemy 2.0 + Alembic; frontend React + MUI Tabs.

**Tech Stack:** Python 3.13 / FastAPI / SQLAlchemy 2.0 (`Mapped`/`mapped_column`) / Alembic (`include_schemas=True`) / PostgreSQL 17 / React 18 + TS + Vite + MUI v6 + Zustand + TanStack Query + axios.

## Global Constraints

- **Maestro canónico = `Config.DIM_Medico`** (clase `Medico` en `backend/app/models/dimensiones.py`). NO crear tabla nueva `DIM_MedicoMaestro`.
- **Alcance país:** el maestro es país-level (`pais_codigo`). Un médico existe una sola vez por país.
- **Reglas de deduplicación (confirmadas):**
  - **Bloqueo duro (no permite crear):** coincidencia de **exequátur** *o* **documento/cédula** dentro del mismo país. Devuelve 409, no se crea.
  - **Advertencia blanda (permite crear con confirmación):** coincidencia por **nombre normalizado + centro/provincia**. Devuelve 409 con la lista de posibles duplicados; si el cliente reenvía con `confirmar_duplicado=true`, se crea igual.
  - Teléfono es solo señal informativa en la advertencia, nunca llave dura.
  - Normalización de nombre: `UPPER`, sin acentos, `trim`, colapsar espacios, antes de comparar.
- **Sincronización de campos (una sola dirección):** campos GENERALES editados en el Panel → se propagan al Maestro. Campos de ASIGNACIÓN (vm_id, ruta, frecuencia, observaciones del rep, última/próxima visita, estado_aprobacion) → solo la fila del Panel. La Categorización NUNCA escribe en el Maestro.
- **Reusar, no duplicar:** el workflow de aprobación de altas del Panel ya existe (`DIM_MedicoVisita.estado_aprobacion` ∈ APROBADO|PENDIENTE_ALTA|PENDIENTE_BAJA|RECHAZADO, `visita_aprobacion_service`). El detector de duplicados del Panel ya existe (`visita_service.detectar_duplicados` / `DuplicadoMedicoError` / flag `confirmar_duplicado`, respuesta 409). Extender esos patrones, no reinventarlos.
- **Convenciones backend:** `Mapped[tipo]`+`mapped_column()`; routers con `prefix=`; RBAC como constantes `Depends(require_roles(...))` por módulo; services reciben `db: Session` sin HTTP; `loguru.logger`, nunca `print`; `datetime.now(timezone.utc)`.
- **Convenciones frontend:** componentes funcionales TS estrictos; MUI `sx`; llamadas API en `frontend/src/services/*.ts` con axios; selectores relacionales con nombre visible (nunca texto libre para un ID); pantallas de carga Excel con patrón Stepper+FormData (ver `frontend/src/pages/etl/ETL.tsx`).
- **Migraciones:** una migración por cambio de esquema, `down_revision` encadenado desde `0011_rm_coaching_min_dia` (head actual). Columnas nuevas nullable o con `server_default`. NO tocar `env.py` (`include_schemas=True`).
- **RBAC del módulo Maestro:** ADMIN + GERENTE_PRODUCTIVIDAD = crear/editar/importar/exportar. GERENTE_DISTRITO/GERENTE_MARCA (supervisor) = leer + validar pendientes + editar generales. REPRESENTANTE_MEDICO = crea/edita solo desde su Panel (campos limitados) → queda PENDIENTE.

---

## Fase 1 — Maestro backend: modelo, dedup, CRUD

### Task 1.1: Enriquecer el modelo `Medico` con campos generales

**Files:**
- Modify: `backend/app/models/dimensiones.py:695-737` (clase `Medico`)

**Interfaces:**
- Produces: columnas nuevas en `Config.DIM_Medico`: `telefono, direccion, sector, exequatur, observaciones, estado_validacion, origen, created_at, updated_at`.

- [ ] **Step 1: Añadir columnas al modelo** — tras la línea `activo: Mapped[bool] = ...` (dimensiones.py:737) agregar:

```python
    # --- Maestro de Médicos (jul-2026): datos generales que antes vivían
    #     duplicados en Visita.DIM_MedicoVisita. Ver plan maestro-medicos. ---
    telefono: Mapped[str | None]     = mapped_column(String(40),  nullable=True)
    direccion: Mapped[str | None]    = mapped_column(String(300), nullable=True)
    sector: Mapped[str | None]       = mapped_column(String(100), nullable=True)
    exequatur: Mapped[str | None]    = mapped_column(String(50),  nullable=True, index=True)
    observaciones: Mapped[str | None] = mapped_column(String(500), nullable=True)
    # APROBADO (creado/validado por Admin/Supervisor o Excel) | PENDIENTE (creado desde Panel por un rep)
    estado_validacion: Mapped[str]   = mapped_column(String(16), nullable=False, default="APROBADO", server_default="APROBADO")
    # MANUAL | EXCEL | PANEL | CATEGORIZACION | COBERTURA
    origen: Mapped[str]              = mapped_column(String(16), nullable=False, default="MANUAL", server_default="MANUAL")
    created_at: Mapped[datetime]     = mapped_column(DateTime, nullable=False, default=lambda: datetime.now(timezone.utc), server_default=func.now())
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, onupdate=lambda: datetime.now(timezone.utc))
```

- [ ] **Step 2: Verificar imports** — confirmar que al inicio de `dimensiones.py` estén `datetime, timezone` (from datetime) y `func` (from sqlalchemy) y `DateTime`. Si falta alguno, añadirlo al import existente.

Run: `cd backend && python -c "from app.models.dimensiones import Medico; print([c.name for c in Medico.__table__.columns])"`
Expected: la lista incluye `telefono, direccion, sector, exequatur, observaciones, estado_validacion, origen, created_at, updated_at`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/models/dimensiones.py
git commit -m "feat(maestro-medicos) DIM_Medico: campos generales del Maestro"
```

### Task 1.2: Migración Alembic 0012

**Files:**
- Create: `backend/alembic/versions/0012_maestro_medico_campos.py`

**Interfaces:**
- Consumes: head actual `0011_rm_coaching_min_dia`.
- Produces: columnas físicas en `Config.DIM_Medico`.

- [ ] **Step 1: Escribir la migración**

```python
"""DIM_Medico: campos generales del Maestro de Médicos

Revision ID: 0012_maestro_medico_campos
Revises: 0011_rm_coaching_min_dia
Create Date: 2026-07-13
"""
from alembic import op
import sqlalchemy as sa

revision = "0012_maestro_medico_campos"
down_revision = "0011_rm_coaching_min_dia"
branch_labels = None
depends_on = None

_COLS = [
    ("telefono", sa.String(40), True, None),
    ("direccion", sa.String(300), True, None),
    ("sector", sa.String(100), True, None),
    ("exequatur", sa.String(50), True, None),
    ("observaciones", sa.String(500), True, None),
    ("estado_validacion", sa.String(16), False, "APROBADO"),
    ("origen", sa.String(16), False, "MANUAL"),
]


def upgrade() -> None:
    for nombre, tipo, nullable, default in _COLS:
        op.add_column("DIM_Medico",
            sa.Column(nombre, tipo, nullable=nullable, server_default=default),
            schema="Config")
    op.add_column("DIM_Medico",
        sa.Column("created_at", sa.DateTime(), nullable=False, server_default=sa.func.now()),
        schema="Config")
    op.add_column("DIM_Medico",
        sa.Column("updated_at", sa.DateTime(), nullable=True), schema="Config")
    op.create_index("IX_Medico_exequatur", "DIM_Medico", ["exequatur"], schema="Config")


def downgrade() -> None:
    op.drop_index("IX_Medico_exequatur", table_name="DIM_Medico", schema="Config")
    for nombre in ("updated_at", "created_at", "observaciones", "exequatur",
                   "sector", "direccion", "telefono", "origen", "estado_validacion"):
        op.drop_column("DIM_Medico", nombre, schema="Config")
```

- [ ] **Step 2: Aplicar y verificar**

Run: `cd backend && python -m alembic upgrade head && python -m alembic current`
Expected: `0012_maestro_medico_campos (head)`.

- [ ] **Step 3: Commit**

```bash
git add backend/alembic/versions/0012_maestro_medico_campos.py
git commit -m "feat(maestro-medicos) migración 0012: campos del Maestro en DIM_Medico"
```

### Task 1.3: Servicio de deduplicación del Maestro

**Files:**
- Create: `backend/app/services/maestro_medico_service.py`
- Test: `backend/tests/test_maestro_medico_service.py`

**Interfaces:**
- Produces:
  - `normalizar_nombre(nombre: str) -> str`
  - `class DuplicadoDuroError(Exception)` con `.coincidencias: list[dict]`
  - `class PosibleDuplicadoError(Exception)` con `.coincidencias: list[dict]`
  - `detectar_duplicados(db, pais_codigo, *, exequatur, cedula, nombre, centro_medico_id, provincia_id, excluir_id=None) -> dict` → `{"duros": [...], "blandos": [...]}`
  - `crear_maestro(db, pais_codigo, datos: dict, *, origen="MANUAL", estado="APROBADO", confirmar_duplicado=False, usuario_id=None) -> Medico`
  - `actualizar_maestro(db, medico: Medico, cambios: dict, usuario_id=None) -> Medico`

- [ ] **Step 1: Escribir el test que falla**

```python
# backend/tests/test_maestro_medico_service.py
import pytest
from app.services import maestro_medico_service as svc

def test_normalizar_quita_acentos_y_espacios():
    assert svc.normalizar_nombre("  José   Peña ") == "JOSE PENA"

def test_dedup_duro_por_exequatur(db_session, medico_factory):
    medico_factory(pais_codigo="DO", exequatur="EXQ-100", nombre="A B")
    res = svc.detectar_duplicados(db_session, "DO", exequatur="EXQ-100",
                                  cedula=None, nombre="OTRO NOMBRE",
                                  centro_medico_id=None, provincia_id=None)
    assert len(res["duros"]) == 1 and res["blandos"] == []

def test_crear_bloquea_por_cedula(db_session, medico_factory):
    medico_factory(pais_codigo="DO", cedula="001-1", nombre="A B")
    with pytest.raises(svc.DuplicadoDuroError):
        svc.crear_maestro(db_session, "DO",
            {"nombre": "NUEVO", "cedula": "001-1"})

def test_crear_advierte_por_nombre_centro_y_permite_confirmar(db_session, medico_factory):
    medico_factory(pais_codigo="DO", nombre="JUAN PEREZ", centro_medico_id=5)
    with pytest.raises(svc.PosibleDuplicadoError):
        svc.crear_maestro(db_session, "DO",
            {"nombre": "Juan Perez", "centro_medico_id": 5})
    m = svc.crear_maestro(db_session, "DO",
            {"nombre": "Juan Perez", "centro_medico_id": 5},
            confirmar_duplicado=True)
    assert m.id is not None and m.estado_validacion == "APROBADO"
```

> Si no existen `db_session`/`medico_factory` en `backend/tests/conftest.py`, crearlos siguiendo el patrón de los fixtures ya usados por `test_visita_service.py` (sesión sobre la BD de test + factory que inserta un `Medico` con los kwargs dados y `pais_codigo` FK válido).

- [ ] **Step 2: Ejecutar el test (debe fallar)**

Run: `cd backend && python -m pytest tests/test_maestro_medico_service.py -v`
Expected: FAIL — `ModuleNotFoundError: maestro_medico_service`.

- [ ] **Step 3: Implementar el servicio**

```python
# backend/app/services/maestro_medico_service.py
"""Maestro de Médicos — dedup en cascada + alta/edición central.

Reglas de dedup (país-level):
  DURA  (bloquea): exequátur o cédula ya existentes → DuplicadoDuroError.
  BLANDA (advierte): mismo nombre normalizado + mismo centro/provincia →
         PosibleDuplicadoError, salvo confirmar_duplicado=True.
"""
import unicodedata
from datetime import datetime, timezone

from loguru import logger
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

from app.models.dimensiones import Medico


class DuplicadoDuroError(Exception):
    def __init__(self, coincidencias): self.coincidencias = coincidencias; super().__init__("Médico duplicado (exequátur/cédula)")

class PosibleDuplicadoError(Exception):
    def __init__(self, coincidencias): self.coincidencias = coincidencias; super().__init__("Posible médico duplicado")


def normalizar_nombre(nombre: str) -> str:
    if not nombre:
        return ""
    s = unicodedata.normalize("NFKD", nombre)
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.upper().split())


def _dto(m: Medico) -> dict:
    return {"id": m.id, "nombre": m.nombre, "codigo": m.codigo,
            "exequatur": m.exequatur, "cedula": m.cedula,
            "centro_medico_id": m.centro_medico_id, "telefono": m.telefono}


def detectar_duplicados(db: Session, pais_codigo: str, *, exequatur=None, cedula=None,
                        nombre=None, centro_medico_id=None, provincia_id=None,
                        excluir_id=None) -> dict:
    base = db.query(Medico).filter(Medico.pais_codigo == pais_codigo, Medico.activo == True)  # noqa: E712
    if excluir_id:
        base = base.filter(Medico.id != excluir_id)

    duros = []
    claves = [c for c in (exequatur, cedula) if c]
    if exequatur or cedula:
        conds = []
        if exequatur: conds.append(Medico.exequatur == exequatur)
        if cedula:    conds.append(Medico.cedula == cedula)
        duros = [_dto(m) for m in base.filter(or_(*conds)).all()]

    blandos = []
    if nombre:
        norm = normalizar_nombre(nombre)
        q = base.filter(func.upper(func.trim(Medico.nombre)) == norm)  # comparación básica; refinar acentos en Python
        for m in q.all():
            if normalizar_nombre(m.nombre) != norm:
                continue
            mismo_centro = centro_medico_id is not None and m.centro_medico_id == centro_medico_id
            mismo_prov = provincia_id is not None and m.provincia_id == provincia_id
            if mismo_centro or mismo_prov or (centro_medico_id is None and provincia_id is None):
                if m.id not in {d["id"] for d in duros}:
                    blandos.append(_dto(m))
    return {"duros": duros, "blandos": blandos}


def crear_maestro(db: Session, pais_codigo: str, datos: dict, *, origen="MANUAL",
                  estado="APROBADO", confirmar_duplicado=False, usuario_id=None) -> Medico:
    dups = detectar_duplicados(db, pais_codigo,
                               exequatur=datos.get("exequatur"), cedula=datos.get("cedula"),
                               nombre=datos.get("nombre"),
                               centro_medico_id=datos.get("centro_medico_id"),
                               provincia_id=datos.get("provincia_id"))
    if dups["duros"]:
        raise DuplicadoDuroError(dups["duros"])
    if dups["blandos"] and not confirmar_duplicado:
        raise PosibleDuplicadoError(dups["blandos"])

    m = Medico(pais_codigo=pais_codigo, origen=origen, estado_validacion=estado,
               activo=True, **{k: v for k, v in datos.items() if hasattr(Medico, k)})
    db.add(m); db.commit(); db.refresh(m)
    logger.info(f"Maestro médico creado id={m.id} '{m.nombre}' pais={pais_codigo} origen={origen}")
    return m


def actualizar_maestro(db: Session, medico: Medico, cambios: dict, usuario_id=None) -> Medico:
    for k, v in cambios.items():
        if hasattr(Medico, k) and k not in ("id", "pais_codigo", "created_at"):
            setattr(medico, k, v)
    medico.updated_at = datetime.now(timezone.utc)
    db.commit(); db.refresh(medico)
    logger.info(f"Maestro médico actualizado id={medico.id} campos={list(cambios)} por={usuario_id}")
    return medico
```

- [ ] **Step 4: Ejecutar el test (debe pasar)**

Run: `cd backend && python -m pytest tests/test_maestro_medico_service.py -v`
Expected: PASS (4 tests).

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/maestro_medico_service.py backend/tests/test_maestro_medico_service.py backend/tests/conftest.py
git commit -m "feat(maestro-medicos) servicio de dedup en cascada + alta/edición central"
```

### Task 1.4: Schemas Pydantic del Maestro

**Files:**
- Modify: `backend/app/schemas/schemas.py` (añadir al final del bloque de schemas)

**Interfaces:**
- Produces: `MaestroMedicoBase`, `MaestroMedicoCrear`, `MaestroMedicoActualizar`, `MaestroMedicoResponse`, `MaestroMedicoDuplicados`.

- [ ] **Step 1: Añadir los schemas**

```python
# --- Maestro de Médicos ---
class MaestroMedicoBase(BaseModel):
    nombre: str = Field(..., min_length=2, max_length=200)
    codigo: str | None = Field(None, max_length=50)
    cedula: str | None = Field(None, max_length=30)
    exequatur: str | None = Field(None, max_length=50)
    especialidad_id: int | None = None
    telefono: str | None = Field(None, max_length=40)
    email: str | None = Field(None, max_length=200)
    direccion: str | None = Field(None, max_length=300)
    provincia_id: int | None = None
    municipio_id: int | None = None
    centro_medico_id: int | None = None
    sector: str | None = Field(None, max_length=100)
    observaciones: str | None = Field(None, max_length=500)
    activo: bool = True

class MaestroMedicoCrear(MaestroMedicoBase):
    pais_codigo: str = Field(..., max_length=10)
    confirmar_duplicado: bool = False

class MaestroMedicoActualizar(BaseModel):
    # todos opcionales (patrón PATCH); mismos campos que Base menos pais
    nombre: str | None = Field(None, min_length=2, max_length=200)
    codigo: str | None = None
    cedula: str | None = None
    exequatur: str | None = None
    especialidad_id: int | None = None
    telefono: str | None = None
    email: str | None = None
    direccion: str | None = None
    provincia_id: int | None = None
    municipio_id: int | None = None
    centro_medico_id: int | None = None
    sector: str | None = None
    observaciones: str | None = None
    activo: bool | None = None

class MaestroMedicoResponse(MaestroMedicoBase):
    id: int
    pais_codigo: str
    estado_validacion: str
    origen: str
    model_config = ConfigDict(from_attributes=True)

class MaestroMedicoDuplicados(BaseModel):
    tipo: str  # "duro" | "blando"
    mensaje: str
    coincidencias: list[dict]
```

- [ ] **Step 2: Verificar import**

Run: `cd backend && python -c "from app.schemas.schemas import MaestroMedicoCrear, MaestroMedicoResponse; print('ok')"`
Expected: `ok`.

- [ ] **Step 3: Commit**

```bash
git add backend/app/schemas/schemas.py
git commit -m "feat(maestro-medicos) schemas Pydantic del Maestro"
```

### Task 1.5: Router `/medicos` (CRUD + KPIs)

**Files:**
- Create: `backend/app/api/v1/routers/maestro_medicos.py`
- Modify: `backend/app/api/v1/router.py` (registrar el router)

**Interfaces:**
- Consumes: `maestro_medico_service`, schemas de Task 1.4.
- Produces: endpoints bajo `prefix="/medicos"`:
  - `GET /medicos/maestro` (paginado, filtros: `q, especialidad_id, provincia_id, estado, activo`)
  - `GET /medicos/maestro/kpis` → `{total, activos, nuevos_mes, sin_asignacion, pendientes_validacion}`
  - `GET /medicos/maestro/{id}`
  - `POST /medicos/maestro` (crea; 409 con cuerpo `MaestroMedicoDuplicados` si dup duro/blando sin confirmar)
  - `PUT /medicos/maestro/{id}`

- [ ] **Step 1: Escribir el router**

```python
"""SCGCPR — Router: Maestro de Médicos · prefix="/medicos".

Fuente única del dato general del médico (país-level). La categorización
(cat.*) y la asignación (Visita.DIM_MedicoVisita) referencian a este maestro.
"""
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.deps import get_db, get_current_active_user, require_roles
from app.models.usuario import Usuario, Rol
from app.models.dimensiones import Medico
from app.schemas.schemas import (MaestroMedicoCrear, MaestroMedicoActualizar,
                                 MaestroMedicoResponse)
from app.services import maestro_medico_service as svc

router = APIRouter(prefix="/medicos", tags=["Maestro de Médicos"])

RequireLectura = Depends(get_current_active_user)
RequireEscritura = Depends(require_roles(Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD))
RequireSupervisor = Depends(require_roles(
    Rol.ADMIN, Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA))


@router.get("/maestro", response_model=list[MaestroMedicoResponse])
def listar(q: str | None = None, especialidad_id: int | None = None,
           provincia_id: int | None = None, estado: str | None = None,
           activo: bool | None = None, skip: int = 0, limit: int = Query(100, le=500),
           db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    query = db.query(Medico)
    if q:
        like = f"%{q.upper()}%"
        query = query.filter(func.upper(Medico.nombre).like(like) |
                             func.upper(func.coalesce(Medico.codigo, "")).like(like) |
                             func.upper(func.coalesce(Medico.cedula, "")).like(like))
    if especialidad_id: query = query.filter(Medico.especialidad_id == especialidad_id)
    if provincia_id:    query = query.filter(Medico.provincia_id == provincia_id)
    if estado:          query = query.filter(Medico.estado_validacion == estado)
    if activo is not None: query = query.filter(Medico.activo == activo)
    return query.order_by(Medico.nombre).offset(skip).limit(limit).all()


@router.get("/maestro/kpis")
def kpis(db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    from app.models.visita import MedicoVisita
    total = db.query(func.count(Medico.id)).scalar() or 0
    activos = db.query(func.count(Medico.id)).filter(Medico.activo == True).scalar() or 0  # noqa: E712
    ini_mes = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    nuevos = db.query(func.count(Medico.id)).filter(Medico.created_at >= ini_mes).scalar() or 0
    pendientes = db.query(func.count(Medico.id)).filter(Medico.estado_validacion == "PENDIENTE").scalar() or 0
    asignados = {mid for (mid,) in db.query(MedicoVisita.maestro_medico_id)
                 .filter(MedicoVisita.maestro_medico_id.isnot(None)).distinct().all()}
    sin_asig = db.query(func.count(Medico.id)).filter(
        Medico.activo == True, ~Medico.id.in_(asignados or {-1})).scalar() or 0  # noqa: E712
    return {"total": total, "activos": activos, "nuevos_mes": nuevos,
            "sin_asignacion": sin_asig, "pendientes_validacion": pendientes}


@router.get("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def obtener(medico_id: int, db: Session = Depends(get_db), _u: Usuario = RequireLectura):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return m


@router.post("/maestro", response_model=MaestroMedicoResponse, status_code=201)
def crear(datos: MaestroMedicoCrear, db: Session = Depends(get_db),
          current_user: Usuario = RequireEscritura):
    payload = datos.model_dump(exclude={"pais_codigo", "confirmar_duplicado"})
    try:
        return svc.crear_maestro(db, datos.pais_codigo, payload, origen="MANUAL",
                                 confirmar_duplicado=datos.confirmar_duplicado,
                                 usuario_id=current_user.id)
    except svc.DuplicadoDuroError as e:
        raise HTTPException(409, detail={"tipo": "duro",
            "mensaje": "Ya existe un médico con ese exequátur o cédula. No se puede crear.",
            "coincidencias": e.coincidencias})
    except svc.PosibleDuplicadoError as e:
        raise HTTPException(409, detail={"tipo": "blando",
            "mensaje": "Posible médico duplicado (mismo nombre y ubicación). "
                       "Reenvíe con confirmar_duplicado=true para crear de todas formas.",
            "coincidencias": e.coincidencias})


@router.put("/maestro/{medico_id}", response_model=MaestroMedicoResponse)
def actualizar(medico_id: int, datos: MaestroMedicoActualizar,
               db: Session = Depends(get_db), current_user: Usuario = RequireSupervisor):
    m = db.query(Medico).filter(Medico.id == medico_id).first()
    if not m: raise HTTPException(404, "Médico no encontrado")
    return svc.actualizar_maestro(db, m, datos.model_dump(exclude_unset=True), current_user.id)
```

- [ ] **Step 2: Registrar el router** en `backend/app/api/v1/router.py` — importar y `api_router.include_router(maestro_medicos.router)` junto a los demás.

- [ ] **Step 3: Verificar arranque + rutas**

Run: `cd backend && python -c "from app.main import app; print([r.path for r in app.routes if '/medicos/maestro' in getattr(r,'path','')])"`
Expected: incluye `/api/v1/medicos/maestro`, `/api/v1/medicos/maestro/kpis`, `/api/v1/medicos/maestro/{medico_id}`.

> Nota: el endpoint `kpis` referencia `MedicoVisita.maestro_medico_id`, que se crea en Fase 4 (Task 4.1). Hasta entonces, el server no arranca si esa columna no existe en el modelo. **Ordenar la ejecución: hacer Task 4.1 (añadir el atributo al modelo `MedicoVisita`) antes de arrancar el server con este router**, o dejar `sin_asignacion=0` provisional. Recomendado: ejecutar Task 4.1 inmediatamente después de 1.1 para que el modelo tenga el atributo desde el inicio (la migración de datos puede ir en Fase 4).

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/maestro_medicos.py backend/app/api/v1/router.py
git commit -m "feat(maestro-medicos) router /medicos: CRUD + KPIs"
```

---

## Fase 2 — Frontend: sección Médicos con dos subpestañas

### Task 2.1: Servicio API del Maestro

**Files:**
- Create: `frontend/src/services/maestroMedicos.service.ts`

**Interfaces:**
- Produces: tipos `MaestroMedico`, `MaestroMedicoKpis`, `Duplicados`; funciones `mmListar(params)`, `mmKpis()`, `mmObtener(id)`, `mmCrear(payload)`, `mmActualizar(id, payload)`.

- [ ] **Step 1: Escribir el servicio** (patrón de `frontend/src/services/coachingMore.service.ts`)

```typescript
import { api } from './api';

export interface MaestroMedico {
  id: number; pais_codigo: string; nombre: string; codigo: string | null;
  cedula: string | null; exequatur: string | null; especialidad_id: number | null;
  telefono: string | null; email: string | null; direccion: string | null;
  provincia_id: number | null; municipio_id: number | null; centro_medico_id: number | null;
  sector: string | null; observaciones: string | null; activo: boolean;
  estado_validacion: string; origen: string;
}
export interface MaestroMedicoKpis {
  total: number; activos: number; nuevos_mes: number;
  sin_asignacion: number; pendientes_validacion: number;
}
export interface DuplicadoDetalle { tipo: 'duro' | 'blando'; mensaje: string; coincidencias: any[]; }

export const mmListar = (params: Record<string, any> = {}) =>
  api.get<MaestroMedico[]>('/medicos/maestro', { params }).then(r => r.data);
export const mmKpis = () => api.get<MaestroMedicoKpis>('/medicos/maestro/kpis').then(r => r.data);
export const mmObtener = (id: number) => api.get<MaestroMedico>(`/medicos/maestro/${id}`).then(r => r.data);
export const mmCrear = (p: Partial<MaestroMedico> & { pais_codigo: string; confirmar_duplicado?: boolean }) =>
  api.post<MaestroMedico>('/medicos/maestro', p).then(r => r.data);
export const mmActualizar = (id: number, p: Partial<MaestroMedico>) =>
  api.put<MaestroMedico>(`/medicos/maestro/${id}`, p).then(r => r.data);
```

- [ ] **Step 2: Type-check** — `cd frontend && npx tsc --noEmit` → sin errores nuevos.
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) servicio API frontend del Maestro"`

### Task 2.2: Página Maestro de Médicos (tabla + KPIs + crear/editar + dedup)

**Files:**
- Create: `frontend/src/pages/medicos/MaestroMedicos.tsx`

**Interfaces:**
- Consumes: `maestroMedicos.service.ts`, `useCicloStore` (país activo), catálogos de especialidad/provincia (patrón de selectores relacionales existentes).
- Produces: componente `MaestroMedicos` exportado por defecto.

- [ ] **Step 1: Implementar** — tabla MUI con búsqueda/filtros, fila de 5 KPI cards (Total/Activos/Nuevos mes/Sin asignación/Pendientes), diálogo Crear/Editar con selectores relacionales de especialidad/provincia/municipio/centro. Al recibir 409:
  - `detail.tipo === "duro"` → mostrar `Alert` de error con las coincidencias y **no** reintentar.
  - `detail.tipo === "blando"` → `Dialog` de confirmación listando las coincidencias, con botón "El médico ya existe (cancelar)" y "Crear de todas formas" → reenvía `mmCrear({...payload, confirmar_duplicado: true})`.
  - Botones Importar/Exportar como placeholders enlazados a Fase 3/5.

- [ ] **Step 2: Type-check + build** — `cd frontend && npx tsc --noEmit && npm run build` → OK.
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) página Maestro: tabla, KPIs, crear/editar con dedup"`

### Task 2.3: Página contenedora Médicos con Tabs + ruta + menú

**Files:**
- Create: `frontend/src/pages/medicos/Medicos.tsx`
- Modify: `frontend/src/App.tsx` (ruta `/medicos`)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (ítem de menú)

**Interfaces:**
- Consumes: `Categorizacion.tsx` existente, `MaestroMedicos.tsx`.

- [ ] **Step 1: `Medicos.tsx`** — MUI `Tabs` con dos pestañas: **Categorización** (renderiza `<Categorizacion />`) y **Maestro de Médicos** (renderiza `<MaestroMedicos />`). Pestaña por defecto = Categorización. Persistir la pestaña activa en el estado local.

- [ ] **Step 2: Ruta** en `App.tsx` — añadir `const Medicos = lazy(() => import('./pages/medicos/Medicos'));` y `<Route path="medicos" element={<ProtectedRoute allowedRoles={['ADMIN','PRESIDENCIA','DIR_COMERCIAL','GERENTE_PRODUCTIVIDAD','GERENTE_MARCA','GERENTE_DISTRITO','REPRESENTANTE_MEDICO','CONSULTA']}><Medicos /></ProtectedRoute>} />`. Mantener `categorizacion` como ruta existente (compatibilidad) o redirigir a `/medicos`.

- [ ] **Step 3: Menú** en `Sidebar.tsx` — reemplazar el ítem `{ label: 'Categorización Médica', path: '/categorizacion', ... }` (línea ~64) por `{ label: 'Médicos', path: '/medicos', icon: <LocalHospital />, roles: [...mismos roles...] }`. Panel Médico (`/visita/panel-medico`) permanece como ítem separado.

- [ ] **Step 4: Verificación en navegador** — `preview_start` del frontend, navegar a `/medicos`, confirmar las dos subpestañas y que Maestro carga la tabla + KPIs. Screenshot.
- [ ] **Step 5: Commit** — `git commit -m "feat(maestro-medicos) sección Médicos con subpestañas Categorización | Maestro"`

---

## Fase 3 — Importación Excel del Maestro

### Task 3.1: Backend importación (preview + upsert)

**Files:**
- Modify: `backend/app/services/maestro_medico_service.py` (añadir `preview_excel`, `importar_excel`)
- Modify: `backend/app/api/v1/routers/maestro_medicos.py` (endpoints `POST /medicos/maestro/preview`, `POST /medicos/maestro/importar`)
- Test: `backend/tests/test_maestro_medico_service.py` (casos de upsert)

**Interfaces:**
- Produces: `importar_excel(db, pais_codigo, filas: list[dict], usuario_id) -> dict` → `{creados, actualizados, duplicados_marcados, errores}`.

- [ ] **Step 1: Test de upsert** — crear un médico por exequátur; reimportar la misma fila con teléfono nuevo → `actualizados==1`, teléfono sincronizado, sin duplicar. Fila con exequátur distinto → `creados==1`.
- [ ] **Step 2: Ejecutar (falla).**
- [ ] **Step 3: Implementar** — `pandas.read_excel`; por fila, resolver por llave dura (exequátur→cédula→código); si existe → `actualizar_maestro` (solo campos generales presentes, no pisa con vacío); si no → `crear_maestro(origen="EXCEL")`; nombre+centro coincidente sin llave dura → contar en `duplicados_marcados` y crear igual (Excel es fuente autorizada). Validar magic bytes como en `etl_service._safe_filename`.
- [ ] **Step 4: Ejecutar (pasa).**
- [ ] **Step 5: Commit** — `git commit -m "feat(maestro-medicos) importación Excel: preview + upsert idempotente"`

### Task 3.2: Frontend Stepper de importación

**Files:**
- Modify: `frontend/src/pages/medicos/MaestroMedicos.tsx` (diálogo Importar con Stepper)
- Modify: `frontend/src/services/maestroMedicos.service.ts` (`mmPreview(file)`, `mmImportar(file)`)

- [ ] **Step 1: Implementar** el diálogo Stepper+FormData replicando `frontend/src/pages/etl/ETL.tsx` (subir → preview con conteo/duplicados → confirmar import → resumen `creados/actualizados/duplicados`).
- [ ] **Step 2: Type-check + build.**
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) UI importación Excel (Stepper)"`

---

## Fase 4 — Puente Panel ↔ Maestro

### Task 4.1: FK `maestro_medico_id` en `DIM_MedicoVisita` + modelo

**Files:**
- Modify: `backend/app/models/visita.py:36-91` (clase `MedicoVisita`)
- Create: `backend/alembic/versions/0013_medicovisita_maestro_fk.py`

**Interfaces:**
- Produces: `MedicoVisita.maestro_medico_id: Mapped[int | None]` FK → `Config.DIM_Medico.id`.

- [ ] **Step 1: Añadir el atributo** al modelo (tras `vm_id`): `maestro_medico_id: Mapped[int | None] = mapped_column(Integer, ForeignKey("Config.DIM_Medico.id"), nullable=True, index=True)`.
- [ ] **Step 2: Migración 0013** (`down_revision = "0012_maestro_medico_campos"`) — `op.add_column` nullable + `op.create_index` + `op.create_foreign_key`.
- [ ] **Step 3: Aplicar + verificar** `alembic upgrade head`.
- [ ] **Step 4: Commit** — `git commit -m "feat(maestro-medicos) DIM_MedicoVisita.maestro_medico_id (FK al Maestro)"`

### Task 4.2: Backfill Panel → Maestro (script idempotente)

**Files:**
- Create: `backend/scripts/backfill_maestro_medicos.py`

**Interfaces:**
- Consumes: `maestro_medico_service`, modelos `MedicoVisita`, `Medico`.

- [ ] **Step 1: Implementar** — por cada `MedicoVisita` con `maestro_medico_id IS NULL`: derivar `pais_codigo` vía su `vm_id`→`DIM_RM.pais_id`→`DIM_Pais.codigo`; buscar match duro (exequátur/cédula) en el Maestro; si existe → linkear; si no → crear maestro (origen="PANEL", estado="APROBADO" para datos históricos ya validados) con los campos generales del panel y linkear. Idempotente (reejecutable). Loggear resumen `{linkeados, creados}`.
- [ ] **Step 2: Ejecutar contra la BD local** y verificar que todos los `MedicoVisita` quedan con `maestro_medico_id`.
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) script de backfill Panel→Maestro"`

### Task 4.3: Sincronización en crear/editar del Panel

**Files:**
- Modify: `backend/app/services/visita_service.py` (`crear_medico`, `actualizar_medico`)

**Interfaces:**
- Consumes: `maestro_medico_service`.

- [ ] **Step 1: Test** — crear médico desde panel sin match → crea maestro PENDIENTE + linkea; editar teléfono del médico del panel → el teléfono del maestro cambia; editar `frecuencia_visita` → el maestro NO cambia.
- [ ] **Step 2: Ejecutar (falla).**
- [ ] **Step 3: Implementar:**
  - En `crear_medico`: antes de crear el `MedicoVisita`, resolver/crear el maestro (`maestro_medico_service`): match duro → linkea; sin match → `crear_maestro(origen="PANEL", estado="PENDIENTE", confirmar_duplicado=datos.confirmar_duplicado)`; propagar `PosibleDuplicadoError`/`DuplicadoDuroError` al endpoint (mapear a 409, reusando el manejo de `DuplicadoMedicoError` ya existente). Guardar `maestro_medico_id` en el panel.
  - En `actualizar_medico`: tras aplicar cambios al panel, si algún campo GENERAL (`nombre_completo→nombre, telefono, email, direccion, exequatur, especialidad_id, provincia/municipio, sector, centro`) cambió y hay `maestro_medico_id`, llamar `actualizar_maestro` con solo esos campos. Los de asignación se ignoran.
  - Definir la lista blanca de campos generales sincronizables como constante del módulo.
- [ ] **Step 4: Ejecutar (pasa).**
- [ ] **Step 5: Commit** — `git commit -m "feat(maestro-medicos) sincronización Panel→Maestro (solo campos generales)"`

### Task 4.4: Búsqueda-primero en alta desde el Panel (frontend)

**Files:**
- Modify: `frontend/src/pages/visita/PanelMedico.tsx`

- [ ] **Step 1: Implementar** — en el diálogo de alta del panel, autocomplete que consulta `mmListar({q})` del maestro; si el rep elige uno existente, prellenar los campos generales (solo lectura) y crear únicamente la asignación; si no existe, flujo actual (crea maestro PENDIENTE + panel). Respetar el 409 blando con confirmación.
- [ ] **Step 2: Type-check + build + verificación en navegador.**
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) Panel: buscar en el Maestro antes de crear"`

---

## Fase 5 — Exportar, historial y cierre

### Task 5.1: Exportar Excel del Maestro

**Files:**
- Modify: `backend/app/api/v1/routers/maestro_medicos.py` (`GET /medicos/maestro/exportar`)
- Modify: `frontend/src/pages/medicos/MaestroMedicos.tsx` (botón Exportar)

- [ ] **Step 1: Implementar** exportación in-memory `BytesIO`+`StreamingResponse` (patrón `exportacion_service.py`), respetando los filtros activos. Botón frontend que descarga.
- [ ] **Step 2: Verificar** descarga válida.
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) exportación Excel del Maestro"`

### Task 5.2: Historial de cambios (auditoría)

**Files:**
- Modify: `backend/app/api/v1/routers/maestro_medicos.py` (`GET /medicos/maestro/{id}/historial`)

- [ ] **Step 1: Implementar** — leer de `Audit.FACT_Auditoria` las acciones sobre la entidad médico (el `audit_middleware` ya registra POST/PUT). Si el middleware no captura el `entidad_id`, añadir el registro explícito en `crear`/`actualizar`. Exponer la lista al frontend en un diálogo "Historial".
- [ ] **Step 2: Verificar** que crear/editar deja rastro consultable.
- [ ] **Step 3: Commit** — `git commit -m "feat(maestro-medicos) historial de cambios del médico"`

### Task 5.3: Docs + verificación final

**Files:**
- Modify: `C:\Users\Lenovo\Proyecto\MSM-postgres\CLAUDE.md` (nueva sección "Maestro de Médicos" + actualizar §3/§4/§14)

- [ ] **Step 1: Documentar** el módulo (tablas, endpoints, reglas de dedup, sincronización, subpestañas).
- [ ] **Step 2: Suite completa** — `cd backend && python -m pytest -q` (verde) + `cd frontend && npx tsc --noEmit && npm run build`.
- [ ] **Step 3: Commit** — `git commit -m "docs(maestro-medicos) documentación del módulo Maestro de Médicos"`

---

## Notas de ejecución

- **Orden crítico:** ejecutar **Task 4.1 (atributo `maestro_medico_id` en el modelo) inmediatamente después de Task 1.1**, para que el router de la Fase 1 (que lo referencia en `kpis`) arranque. La migración de datos (backfill, Task 4.2) puede quedarse en Fase 4.
- **Ciclos cerrados:** el Maestro es país-level y NO es ciclo-dependiente, así que el guard de ciclo abierto no aplica al maestro. Sí aplica a la asignación del Panel (que ya lo tiene).
- **`cat.*` intacto:** no se modifica ninguna tabla del esquema `cat` — la subpestaña Categorización renderiza el componente existente sin cambios.
