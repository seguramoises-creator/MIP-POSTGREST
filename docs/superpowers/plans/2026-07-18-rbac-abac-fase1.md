# RBAC/ABAC Fase 1 (motor + seed, NO destructivo) — Plan de Implementación

> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development (recomendado)
> o superpowers:executing-plans. Pasos con checkbox (`- [ ]`).

**Goal:** Construir el motor de autorización RBAC/ABAC de VISTA (recurso × acción × alcance),
sembrar la matriz 28×10 como dato, exponerla al frontend y auditarla — **sin cambiar el acceso
efectivo de ningún usuario actual** (no se rewirean endpoints existentes).

**Architecture:** Motor Python declarativo (`app/core/authz/`) como fuente de verdad; seed idempotente
a `Security.DIM_Recurso`/`FACT_RolPermiso`; endpoint `GET /authz/me/permisos` como contrato frontend;
auditoría en `Security.FACT_AuditoriaSeguridad`; revocación por `roles_actualizado_en` + `iat` del token.

**Tech Stack:** FastAPI 0.115, SQLAlchemy 2.0 (Mapped), Alembic (include_schemas=True), PostgreSQL 14,
python-jose, pytest.

**Spec:** `docs/superpowers/specs/2026-07-18-rbac-abac-seguridad-design.md` (§5 = matriz canónica).

## Global Constraints

- **NO destructivo:** ningún `require_roles` existente cambia; ningún endpoint actual altera su RBAC.
  Todo es aditivo (tablas nuevas, módulo nuevo, endpoint nuevo, 4 valores de enum nuevos).
- **Denegación por defecto:** ausencia de celda en la matriz = deny (`None`).
- **`own` desde la sesión** (`user.rm_id`), nunca desde un id del cliente.
- **`export` independiente de `read`**; el alcance efectivo de export por módulo =
  `min(export_grant, read_scope(módulo))`, nunca mayor que la lectura.
- **`admin` (Superadmin=ADMIN) concede todo.**
- Enum PG se llama `rol` (nombre default de SQLAlchemy); nuevos valores vía `ALTER TYPE rol ADD VALUE`.
- Migraciones y seed **idempotentes** (re-ejecutables).
- Timestamps `datetime.now(timezone.utc)`. Modelos `Mapped[...]`. Logs con `loguru`.
- La matriz codificada en `matrix.py` debe ser **idéntica** a la tabla del spec §5 (test-oracle lo verifica).

---

### Task 1: Roles nuevos + modelos de seguridad + migración

**Files:**
- Modify: `backend/app/models/usuario.py` (4 valores de enum + columna `roles_actualizado_en`)
- Create: `backend/app/models/seguridad_rbac.py` (`Recurso`, `RolPermiso`, `AuditoriaSeguridad`)
- Modify: `backend/app/models/__init__.py` o donde se importan modelos para metadata (verificar)
- Create: `backend/alembic/versions/0017_rbac_fase1.py`
- Test: `backend/tests/test_rbac_migracion.py`

**Interfaces:**
- Produces: `Rol.GERENTE_MARKETING/GERENTE_MEDICO/ANALISTA_DATOS/FINANZAS`;
  `Usuario.roles_actualizado_en: datetime|None`; ORM `Recurso`, `RolPermiso`, `AuditoriaSeguridad`
  (esquema `Security`).

- [ ] **Step 1: Añadir los 4 roles al enum** en `usuario.py` (después de `CAPACITACION`):

```python
class Rol(str, PyEnum):
    ADMIN                  = "ADMIN"
    PRESIDENCIA            = "PRESIDENCIA"
    DIR_COMERCIAL          = "DIR_COMERCIAL"
    GERENTE_PRODUCTIVIDAD  = "GERENTE_PRODUCTIVIDAD"
    GERENTE_DISTRITO       = "GERENTE_DISTRITO"
    GERENTE_MARCA          = "GERENTE_MARCA"
    REPRESENTANTE_MEDICO   = "REPRESENTANTE_MEDICO"
    CONSULTA               = "CONSULTA"
    CAPACITACION           = "CAPACITACION"
    # RBAC Fase 1 (jul-2026): roles canónicos de la matriz de seguridad
    GERENTE_MARKETING      = "GERENTE_MARKETING"
    GERENTE_MEDICO         = "GERENTE_MEDICO"
    ANALISTA_DATOS         = "ANALISTA_DATOS"
    FINANZAS               = "FINANZAS"
```

- [ ] **Step 2: Añadir columna a `Usuario`** (después de `password_actualizado_en`):

```python
    # RBAC Fase 1: al cambiar el rol se fija a now(); los access tokens con iat anterior
    # se rechazan (revocación de permisos, ver deps.get_current_user).
    roles_actualizado_en: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
```

- [ ] **Step 3: Crear `seguridad_rbac.py`** con los 3 modelos:

```python
"""RBAC Fase 1 — catálogo de recursos, matriz rol→permiso y auditoría de seguridad."""
from datetime import datetime, timezone
from sqlalchemy import String, Integer, DateTime, UniqueConstraint, Index
from sqlalchemy.orm import Mapped, mapped_column
from app.db.database import Base


class Recurso(Base):
    __tablename__ = "DIM_Recurso"
    __table_args__ = {"schema": "Security"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    slug: Mapped[str] = mapped_column(String(80), unique=True, nullable=False, index=True)
    nombre: Mapped[str] = mapped_column(String(160), nullable=False)
    modulo: Mapped[str] = mapped_column(String(60), nullable=False)


class RolPermiso(Base):
    __tablename__ = "FACT_RolPermiso"
    __table_args__ = (
        UniqueConstraint("rol", "recurso", "accion", name="UQ_RolPermiso"),
        {"schema": "Security"},
    )
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    rol: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recurso: Mapped[str] = mapped_column(String(80), nullable=False, index=True)
    accion: Mapped[str] = mapped_column(String(20), nullable=False)
    alcance: Mapped[str] = mapped_column(String(10), nullable=False)


class AuditoriaSeguridad(Base):
    """Log append-only de acciones sensibles (asignación de rol, configure/approve,
    export, excepción Superadmin). Sin datos personales sensibles."""
    __tablename__ = "FACT_AuditoriaSeguridad"
    __table_args__ = {"schema": "Security"}
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    actor_usuario_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    actor_rol: Mapped[str | None] = mapped_column(String(40), nullable=True)
    evento: Mapped[str] = mapped_column(String(40), nullable=False, index=True)
    recurso: Mapped[str | None] = mapped_column(String(80), nullable=True)
    accion: Mapped[str | None] = mapped_column(String(20), nullable=True)
    alcance: Mapped[str | None] = mapped_column(String(10), nullable=True)
    objetivo: Mapped[str | None] = mapped_column(String(160), nullable=True)  # p.ej. usuario afectado
    detalle: Mapped[str | None] = mapped_column(String(500), nullable=True)   # JSON corto, sin PII
    resultado: Mapped[str | None] = mapped_column(String(20), nullable=True)  # OK|DENEGADO|ERROR
    creado_en: Mapped[datetime] = mapped_column(
        DateTime, default=lambda: datetime.now(timezone.utc), index=True)
```

- [ ] **Step 4: Asegurar import del modelo para `Base.metadata`.** Verificar cómo el baseline/otros
  importan modelos (baseline hace `import app.models.usuario` etc. antes de `create_all`). Añadir
  `import app.models.seguridad_rbac` allí donde se listan los modelos para metadata (revisar
  `app/models/__init__.py` y el `env.py` de alembic; seguir el patrón existente de `hechos.py`).

- [ ] **Step 5: Escribir la migración** `0017_rbac_fase1.py`. `down_revision` = la cabeza actual
  (obtener con `python -m alembic heads`). Los `ADD VALUE` van en AUTOCOMMIT (no dentro de la tx):

```python
"""RBAC Fase 1 — enum roles nuevos, DIM_Recurso, FACT_RolPermiso, FACT_AuditoriaSeguridad,
Usuario.roles_actualizado_en.

Revision ID: 0017_rbac_fase1
Revises: <CABEZA_ACTUAL>
"""
from alembic import op
import sqlalchemy as sa

revision = "0017_rbac_fase1"
down_revision = "<CABEZA_ACTUAL>"   # sustituir por `alembic heads`
branch_labels = None
depends_on = None

_NUEVOS_ROLES = ["GERENTE_MARKETING", "GERENTE_MEDICO", "ANALISTA_DATOS", "FINANZAS"]


def upgrade():
    # 1) Nuevos valores del enum PG `rol` — ADD VALUE no puede usarse en la misma tx en que
    #    se USA el valor, pero aquí solo lo añadimos. Se ejecuta en AUTOCOMMIT por robustez.
    conn = op.get_bind()
    conn = conn.execution_options(isolation_level="AUTOCOMMIT")
    for r in _NUEVOS_ROLES:
        conn.execute(sa.text(f"ALTER TYPE rol ADD VALUE IF NOT EXISTS '{r}'"))

    # 2) Columna de revocación
    op.add_column("DIM_Usuario",
                  sa.Column("roles_actualizado_en", sa.DateTime(), nullable=True),
                  schema="Security")

    # 3) Catálogo de recursos
    op.create_table(
        "DIM_Recurso",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("slug", sa.String(80), nullable=False, unique=True),
        sa.Column("nombre", sa.String(160), nullable=False),
        sa.Column("modulo", sa.String(60), nullable=False),
        schema="Security",
    )
    op.create_index("IX_Recurso_slug", "DIM_Recurso", ["slug"], schema="Security")

    # 4) Matriz rol→permiso
    op.create_table(
        "FACT_RolPermiso",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("rol", sa.String(40), nullable=False),
        sa.Column("recurso", sa.String(80), nullable=False),
        sa.Column("accion", sa.String(20), nullable=False),
        sa.Column("alcance", sa.String(10), nullable=False),
        sa.UniqueConstraint("rol", "recurso", "accion", name="UQ_RolPermiso"),
        schema="Security",
    )
    op.create_index("IX_RolPermiso_rol", "FACT_RolPermiso", ["rol"], schema="Security")

    # 5) Auditoría de seguridad
    op.create_table(
        "FACT_AuditoriaSeguridad",
        sa.Column("id", sa.Integer, primary_key=True, autoincrement=True),
        sa.Column("actor_usuario_id", sa.Integer, nullable=True),
        sa.Column("actor_rol", sa.String(40), nullable=True),
        sa.Column("evento", sa.String(40), nullable=False),
        sa.Column("recurso", sa.String(80), nullable=True),
        sa.Column("accion", sa.String(20), nullable=True),
        sa.Column("alcance", sa.String(10), nullable=True),
        sa.Column("objetivo", sa.String(160), nullable=True),
        sa.Column("detalle", sa.String(500), nullable=True),
        sa.Column("resultado", sa.String(20), nullable=True),
        sa.Column("creado_en", sa.DateTime(), nullable=False, server_default=sa.text("now()")),
        schema="Security",
    )
    op.create_index("IX_AudSeg_evento", "FACT_AuditoriaSeguridad", ["evento"], schema="Security")


def downgrade():
    op.drop_table("FACT_AuditoriaSeguridad", schema="Security")
    op.drop_table("FACT_RolPermiso", schema="Security")
    op.drop_table("DIM_Recurso", schema="Security")
    op.drop_column("DIM_Usuario", "roles_actualizado_en", schema="Security")
    # Nota: PostgreSQL no soporta DROP VALUE en un enum; los valores nuevos quedan (inofensivo).
```

- [ ] **Step 6: Aplicar y verificar** contra la BD local de trabajo (`scgcpr`, NUNCA `scgcpr_prod`):

Run: `cd backend && python -m alembic upgrade head`
Expected: sin error; `\dt "Security".*` muestra las 3 tablas nuevas.

- [ ] **Step 7: Test de migración** `test_rbac_migracion.py` — importa los modelos y el enum, asegura
  que los 4 roles existen y que `Usuario` tiene el atributo:

```python
from app.models.usuario import Rol, Usuario
from app.models.seguridad_rbac import Recurso, RolPermiso, AuditoriaSeguridad

def test_roles_nuevos_en_enum():
    for r in ("GERENTE_MARKETING", "GERENTE_MEDICO", "ANALISTA_DATOS", "FINANZAS"):
        assert hasattr(Rol, r)

def test_usuario_tiene_roles_actualizado_en():
    assert "roles_actualizado_en" in Usuario.__table__.columns

def test_modelos_seguridad_en_esquema_security():
    assert Recurso.__table__.schema == "Security"
    assert RolPermiso.__table__.schema == "Security"
    assert AuditoriaSeguridad.__table__.schema == "Security"
```

Run: `cd backend && python -m pytest tests/test_rbac_migracion.py -v` → PASS

- [ ] **Step 8: Commit** — `git add` modelos + migración + test; mensaje
  `feat(seguridad) RBAC Fase 1 T1: roles nuevos + modelos DIM_Recurso/FACT_RolPermiso/auditoria + migracion 0017`.

---

### Task 2: Constantes canónicas + matriz declarativa

**Files:**
- Create: `backend/app/core/authz/__init__.py`
- Create: `backend/app/core/authz/constantes.py`
- Create: `backend/app/core/authz/matrix.py`
- Test: `backend/tests/test_authz_matriz.py`

**Interfaces:**
- Produces: `Accion`, `Alcance`, `alcance_min`, `Recurso` (slugs), `RECURSOS: list[str]`,
  `RECURSOS_META: dict[str, tuple[str,str]]`, `MATRIZ: dict[str, dict[Rol, tuple|None]]`, y las
  constantes de celda (`R_OWN`, `R_TEAM`, `R_ALL`, `REG_OWN`, `REG_TEAM`, `CFG`, `APR`, `EXP_TEAM`,
  `EXP_ALL`, `ADMIN_CELL`).

- [ ] **Step 1: `constantes.py`**:

```python
from enum import Enum

class Accion(str, Enum):
    READ = "read"; REGISTER = "register"; CONFIGURE = "configure"
    APPROVE = "approve"; EXPORT = "export"; ADMIN = "admin"

class Alcance(str, Enum):
    NONE = "none"; OWN = "own"; TEAM = "team"; ALL = "all"

_ORDEN = {Alcance.NONE: 0, Alcance.OWN: 1, Alcance.TEAM: 2, Alcance.ALL: 3}

def alcance_min(a: Alcance, b: Alcance) -> Alcance:
    return a if _ORDEN[a] <= _ORDEN[b] else b

class Recurso:
    DASHBOARD_EJECUTIVO = "dashboard.ejecutivo"
    VISITA_REGISTRAR = "visita.registrar"
    MEDICO_PANEL = "medico.panel"
    CATEGORIZACION_BASICA = "categorizacion.basica"
    CATEGORIZACION_DETALLE = "categorizacion.detalle"
    PLANEACION_CICLO = "planeacion.ciclo"
    COBERTURA_DIARIA = "cobertura.diaria"
    COBERTURA_PREDICTIVA = "cobertura.predictiva"
    PARRILLA_CONFIGURAR = "parrilla.configurar"
    PARRILLA_CONSULTA = "parrilla.consulta"
    PRODUCTIVIDAD_COMERCIAL = "productividad.comercial"
    RANKING_RKT = "ranking.rkt"
    FARMACIA_CONFIGURACION = "farmacia.configuracion"
    FARMACIA_VISITA = "farmacia.visita"
    FARMACIA_COBERTURA = "farmacia.cobertura"
    COACHING_HOJA = "coaching.hoja"
    COACHING_KPI = "coaching.kpi"
    EXAMEN_RENDIR = "examen.rendir"
    EXAMEN_CONFIGURAR = "examen.configurar"
    INTELIGENCIA_MATRIZ = "inteligencia.matriz"
    ENCUESTA_CONFIGURAR = "inteligencia.encuesta.configurar"
    ENCUESTA_APLICAR = "inteligencia.encuesta.aplicar"
    COSTOROI_VER = "costoroi.ver"
    COSTOROI_CONFIGURAR = "costoroi.configurar"
    CONFIG_PRODUCTOS = "config.productos"
    CONFIG_USUARIOS = "config.usuarios"
    CONFIG_PARAMETROS = "config.parametros"
    EXPORTACION = "exportacion"

# (slug, nombre legible, módulo) — orden = filas del spec §5
RECURSOS_META: dict[str, tuple[str, str]] = {
    Recurso.DASHBOARD_EJECUTIVO: ("Dashboard Ejecutivo", "Visión general"),
    Recurso.VISITA_REGISTRAR: ("Registrar visita médica", "Registro de visita"),
    Recurso.MEDICO_PANEL: ("Catálogo de médicos y contacto", "Panel médico"),
    Recurso.CATEGORIZACION_BASICA: ("Categorización básica (A/B/C)", "Panel médico"),
    Recurso.CATEGORIZACION_DETALLE: ("Categorización detalle y pesos", "Panel médico"),
    Recurso.PLANEACION_CICLO: ("Planeación del ciclo", "Planeación y cobertura"),
    Recurso.COBERTURA_DIARIA: ("Cobertura diaria / Ruptura", "Planeación y cobertura"),
    Recurso.COBERTURA_PREDICTIVA: ("Cobertura predictiva", "Planeación y cobertura"),
    Recurso.PARRILLA_CONFIGURAR: ("Parrilla de muestras: configurar", "Comercial"),
    Recurso.PARRILLA_CONSULTA: ("Parrilla de muestras: consulta", "Comercial"),
    Recurso.PRODUCTIVIDAD_COMERCIAL: ("Productividad comercial", "Comercial"),
    Recurso.RANKING_RKT: ("Ranking general (RKT)", "Comercial"),
    Recurso.FARMACIA_CONFIGURACION: ("Configuración de farmacias", "Farmacias"),
    Recurso.FARMACIA_VISITA: ("Registro de visita a farmacia", "Farmacias"),
    Recurso.FARMACIA_COBERTURA: ("Cobertura de farmacias", "Farmacias"),
    Recurso.COACHING_HOJA: ("Hoja de acompañamiento GD→RM", "Coaching (MORE)"),
    Recurso.COACHING_KPI: ("KPI Coaching de equipo", "Coaching (MORE)"),
    Recurso.EXAMEN_RENDIR: ("Rendir examen de producto", "Formación / Exámenes"),
    Recurso.EXAMEN_CONFIGURAR: ("Configurar/publicar exámenes", "Formación / Exámenes"),
    Recurso.INTELIGENCIA_MATRIZ: ("Matriz de Potencial y Adopción", "Inteligencia de mercado"),
    Recurso.ENCUESTA_CONFIGURAR: ("Encuestas: crear y publicar", "Inteligencia de mercado"),
    Recurso.ENCUESTA_APLICAR: ("Encuestas: aplicar en visita", "Inteligencia de mercado"),
    Recurso.COSTOROI_VER: ("Ver Costo por Visita y ROI", "Costo y ROI"),
    Recurso.COSTOROI_CONFIGURAR: ("Configurar costos/pool/presupuesto", "Costo y ROI"),
    Recurso.CONFIG_PRODUCTOS: ("Catálogo de productos y precios", "Configuración del sistema"),
    Recurso.CONFIG_USUARIOS: ("Usuarios y asignación de roles", "Configuración del sistema"),
    Recurso.CONFIG_PARAMETROS: ("Parámetros generales", "Configuración del sistema"),
    Recurso.EXPORTACION: ("Exportar datos y reportes", "Exportación"),
}
RECURSOS: list[str] = list(RECURSOS_META.keys())
```

- [ ] **Step 2: `matrix.py`** — celdas + la matriz completa (transcripción exacta del spec §5):

```python
from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso

R_OWN  = (Accion.READ, Alcance.OWN)
R_TEAM = (Accion.READ, Alcance.TEAM)
R_ALL  = (Accion.READ, Alcance.ALL)
REG_OWN  = (Accion.REGISTER, Alcance.OWN)
REG_TEAM = (Accion.REGISTER, Alcance.TEAM)
CFG = (Accion.CONFIGURE, Alcance.ALL)
APR = (Accion.APPROVE, Alcance.ALL)
EXP_TEAM = (Accion.EXPORT, Alcance.TEAM)
EXP_ALL  = (Accion.EXPORT, Alcance.ALL)
ADMIN_CELL = (Accion.ADMIN, Alcance.ALL)

# Orden de roles (columnas del spec §5)
_ROLES = [
    Rol.REPRESENTANTE_MEDICO, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA, Rol.GERENTE_MARKETING,
    Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MEDICO, Rol.PRESIDENCIA, Rol.ANALISTA_DATOS,
    Rol.FINANZAS, Rol.ADMIN,
]

def _fila(*celdas):
    assert len(celdas) == len(_ROLES), "la fila debe tener 10 celdas"
    return {rol: c for rol, c in zip(_ROLES, celdas)}

_N = None  # sin acceso

# MATRIZ[recurso][rol] = (accion, alcance) | None. Columnas en orden _ROLES.
MATRIZ: dict[str, dict] = {
    #                            RM        GD        MARCA   MKT     PROD     MED     PRES    ANAL    FIN     ADMIN
    Recurso.DASHBOARD_EJECUTIVO: _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   R_ALL,  R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.VISITA_REGISTRAR:    _fila(REG_OWN,_N,      _N,     _N,     _N,      _N,     _N,     _N,     _N,     ADMIN_CELL),
    Recurso.MEDICO_PANEL:        _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  _N,      R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.CATEGORIZACION_BASICA:_fila(R_OWN, R_TEAM,  R_ALL,  R_ALL,  _N,      R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.CATEGORIZACION_DETALLE:_fila(_N,   _N,      CFG,    R_ALL,  _N,      R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.PLANEACION_CICLO:    _fila(REG_OWN,R_TEAM,  _N,     _N,     _N,      _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.COBERTURA_DIARIA:    _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   R_ALL,  R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.COBERTURA_PREDICTIVA:_fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.PARRILLA_CONFIGURAR: _fila(_N,     CFG,     _N,     _N,     _N,      _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.PARRILLA_CONSULTA:   _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   R_ALL,  R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.PRODUCTIVIDAD_COMERCIAL:_fila(R_OWN,R_TEAM, R_ALL,  R_ALL,  R_ALL,   _N,     R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.RANKING_RKT:         _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   _N,     R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.FARMACIA_CONFIGURACION:_fila(_N,   CFG,     _N,     R_ALL,  _N,      _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.FARMACIA_VISITA:     _fila(REG_OWN,_N,      _N,     _N,     _N,      _N,     _N,     _N,     _N,     ADMIN_CELL),
    Recurso.FARMACIA_COBERTURA:  _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  R_ALL,   _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.COACHING_HOJA:       _fila(R_OWN,  REG_TEAM,_N,     _N,     R_TEAM,  R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.COACHING_KPI:        _fila(_N,     R_TEAM,  _N,     _N,     R_ALL,   R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.EXAMEN_RENDIR:       _fila(REG_OWN,_N,      _N,     _N,     R_TEAM,  R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.EXAMEN_CONFIGURAR:   _fila(_N,     R_TEAM,  _N,     _N,     CFG,     CFG,    R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.INTELIGENCIA_MATRIZ: _fila(R_OWN,  R_TEAM,  CFG,    CFG,    _N,      R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.ENCUESTA_CONFIGURAR: _fila(_N,     _N,      CFG,    CFG,    _N,      R_ALL,  R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.ENCUESTA_APLICAR:    _fila(REG_OWN,_N,      R_ALL,  R_ALL,  _N,      _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.COSTOROI_VER:        _fila(R_OWN,  R_TEAM,  R_ALL,  R_ALL,  _N,      _N,     R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.COSTOROI_CONFIGURAR: _fila(_N,     _N,      _N,     _N,     _N,      _N,     APR,    _N,     CFG,    ADMIN_CELL),
    Recurso.CONFIG_PRODUCTOS:    _fila(_N,     _N,      R_ALL,  R_ALL,  _N,      R_ALL,  R_ALL,  R_ALL,  R_ALL,  ADMIN_CELL),
    Recurso.CONFIG_USUARIOS:     _fila(_N,     _N,      _N,     _N,     _N,      _N,     _N,     _N,     _N,     ADMIN_CELL),
    Recurso.CONFIG_PARAMETROS:   _fila(_N,     _N,      _N,     _N,     _N,      _N,     R_ALL,  R_ALL,  _N,     ADMIN_CELL),
    Recurso.EXPORTACION:         _fila(_N,     EXP_TEAM,EXP_ALL,EXP_ALL,EXP_ALL, EXP_ALL,EXP_ALL,EXP_ALL,EXP_ALL,ADMIN_CELL),
}
```

- [ ] **Step 2b: `__init__.py`** re-exporta lo público:

```python
from app.core.authz.constantes import Accion, Alcance, Recurso, RECURSOS, RECURSOS_META, alcance_min
from app.core.authz.matrix import MATRIZ
```

- [ ] **Step 3: Test-oracle** `test_authz_matriz.py` — **transcripción INDEPENDIENTE** de la tabla del
  spec como oráculo, para atrapar errores de transcripción en `matrix.py`:

```python
from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso, RECURSOS
from app.core.authz.matrix import MATRIZ

# Oráculo: (accion, alcance) o None, en el orden de columnas del spec §5.
COLS = [Rol.REPRESENTANTE_MEDICO, Rol.GERENTE_DISTRITO, Rol.GERENTE_MARCA, Rol.GERENTE_MARKETING,
        Rol.GERENTE_PRODUCTIVIDAD, Rol.GERENTE_MEDICO, Rol.PRESIDENCIA, Rol.ANALISTA_DATOS,
        Rol.FINANZAS, Rol.ADMIN]
RO=(Accion.READ,Alcance.OWN); RT=(Accion.READ,Alcance.TEAM); RA=(Accion.READ,Alcance.ALL)
GO=(Accion.REGISTER,Alcance.OWN); GT=(Accion.REGISTER,Alcance.TEAM)
CF=(Accion.CONFIGURE,Alcance.ALL); AP=(Accion.APPROVE,Alcance.ALL)
ET=(Accion.EXPORT,Alcance.TEAM); EA=(Accion.EXPORT,Alcance.ALL); AD=(Accion.ADMIN,Alcance.ALL); _=None

ORACULO = {
 Recurso.DASHBOARD_EJECUTIVO:[RO,RT,RA,RA,RA,RA,RA,RA,RA,AD],
 Recurso.VISITA_REGISTRAR:[GO,_,_,_,_,_,_,_,_,AD],
 Recurso.MEDICO_PANEL:[RO,RT,RA,RA,_,RA,RA,RA,_,AD],
 Recurso.CATEGORIZACION_BASICA:[RO,RT,RA,RA,_,RA,RA,RA,_,AD],
 Recurso.CATEGORIZACION_DETALLE:[_,_,CF,RA,_,RA,RA,RA,_,AD],
 Recurso.PLANEACION_CICLO:[GO,RT,_,_,_,_,RA,RA,_,AD],
 Recurso.COBERTURA_DIARIA:[RO,RT,RA,RA,RA,RA,RA,RA,RA,AD],
 Recurso.COBERTURA_PREDICTIVA:[RO,RT,RA,RA,RA,RA,RA,RA,_,AD],
 Recurso.PARRILLA_CONFIGURAR:[_,CF,_,_,_,_,RA,RA,_,AD],
 Recurso.PARRILLA_CONSULTA:[RO,RT,RA,RA,RA,RA,RA,RA,RA,AD],
 Recurso.PRODUCTIVIDAD_COMERCIAL:[RO,RT,RA,RA,RA,_,RA,RA,RA,AD],
 Recurso.RANKING_RKT:[RO,RT,RA,RA,RA,_,RA,RA,RA,AD],
 Recurso.FARMACIA_CONFIGURACION:[_,CF,_,RA,_,_,RA,RA,_,AD],
 Recurso.FARMACIA_VISITA:[GO,_,_,_,_,_,_,_,_,AD],
 Recurso.FARMACIA_COBERTURA:[RO,RT,RA,RA,RA,_,RA,RA,_,AD],
 Recurso.COACHING_HOJA:[RO,GT,_,_,RT,RA,RA,RA,_,AD],
 Recurso.COACHING_KPI:[_,RT,_,_,RA,RA,RA,RA,_,AD],
 Recurso.EXAMEN_RENDIR:[GO,_,_,_,RT,RA,RA,RA,_,AD],
 Recurso.EXAMEN_CONFIGURAR:[_,RT,_,_,CF,CF,RA,RA,_,AD],
 Recurso.INTELIGENCIA_MATRIZ:[RO,RT,CF,CF,_,RA,RA,RA,_,AD],
 Recurso.ENCUESTA_CONFIGURAR:[_,_,CF,CF,_,RA,RA,RA,_,AD],
 Recurso.ENCUESTA_APLICAR:[GO,_,RA,RA,_,_,RA,RA,_,AD],
 Recurso.COSTOROI_VER:[RO,RT,RA,RA,_,_,RA,RA,RA,AD],
 Recurso.COSTOROI_CONFIGURAR:[_,_,_,_,_,_,AP,_,CF,AD],
 Recurso.CONFIG_PRODUCTOS:[_,_,RA,RA,_,RA,RA,RA,RA,AD],
 Recurso.CONFIG_USUARIOS:[_,_,_,_,_,_,_,_,_,AD],
 Recurso.CONFIG_PARAMETROS:[_,_,_,_,_,_,RA,RA,_,AD],
 Recurso.EXPORTACION:[_,ET,EA,EA,EA,EA,EA,EA,EA,AD],
}

def test_matriz_tiene_28_recursos():
    assert len(RECURSOS) == 28 and set(MATRIZ) == set(RECURSOS)

def test_matriz_coincide_con_oraculo_del_spec():
    for recurso, fila in ORACULO.items():
        for rol, esperado in zip(COLS, fila):
            assert MATRIZ[recurso][rol] == esperado, f"{recurso} / {rol}: {MATRIZ[recurso][rol]} != {esperado}"
```

Run: `cd backend && python -m pytest tests/test_authz_matriz.py -v` → PASS

- [ ] **Step 4: Commit** — `feat(seguridad) RBAC Fase 1 T2: constantes canonicas + matriz declarativa 28x10 + test-oraculo`.

---

### Task 3: Motor `can()` + implicación + tope de export

**Files:**
- Create: `backend/app/core/authz/engine.py`
- Test: `backend/tests/test_authz_engine.py`

**Interfaces:**
- Consumes: `MATRIZ`, `Accion`, `Alcance`, `alcance_min` (Task 2); `Rol` (Task 1).
- Produces: `can(user, accion, recurso) -> Alcance | None`; `alcance_export_modulo(user, recurso) -> Alcance | None`;
  `puede(user, accion, recurso) -> bool`. `user` es cualquier objeto con `.rol` (Usuario o stub).

- [ ] **Step 1: Test primero** `test_authz_engine.py` (rojo). Incluye la **parametrizada 28×10**
  reusando el ORÁCULO de Task 2 y verificando `can()` para la acción propia de cada celda + reglas:

```python
import pytest
from types import SimpleNamespace
from app.models.usuario import Rol
from app.core.authz.constantes import Accion, Alcance, Recurso, RECURSOS
from app.core.authz import engine
from tests.test_authz_matriz import ORACULO, COLS

def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id)

@pytest.mark.parametrize("recurso", list(ORACULO.keys()))
@pytest.mark.parametrize("idx", range(10))
def test_can_para_cada_celda(recurso, idx):
    rol = COLS[idx]; celda = ORACULO[recurso][idx]
    u = U(rol)
    if celda is None:
        # ninguna acción concede nada (salvo que sea ADMIN, que no es None)
        for a in Accion:
            assert engine.can(u, a, recurso) is None
    else:
        accion, alcance = celda
        if accion == Accion.ADMIN:
            for a in (Accion.READ, Accion.REGISTER, Accion.CONFIGURE, Accion.APPROVE, Accion.EXPORT, Accion.ADMIN):
                assert engine.can(u, a, recurso) == Alcance.ALL
        else:
            assert engine.can(u, accion, recurso) == alcance

def test_configure_implica_read():
    # GERENTE_MARCA configura categorizacion.detalle → puede leerla
    u = U(Rol.GERENTE_MARCA)
    assert engine.can(u, Accion.READ, Recurso.CATEGORIZACION_DETALLE) == Alcance.ALL
    assert engine.can(u, Accion.CONFIGURE, Recurso.CATEGORIZACION_DETALLE) == Alcance.ALL

def test_approve_implica_read_pero_no_configure():
    u = U(Rol.PRESIDENCIA)  # Director aprueba costoroi.configurar
    assert engine.can(u, Accion.READ, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(u, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(u, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) is None

def test_register_implica_read_mismo_alcance():
    u = U(Rol.REPRESENTANTE_MEDICO)
    assert engine.can(u, Accion.READ, Recurso.VISITA_REGISTRAR) == Alcance.OWN

def test_export_no_deriva_de_read():
    # ANALISTA lee dashboard (all) pero eso no le da export sobre el recurso dashboard
    u = U(Rol.ANALISTA_DATOS)
    assert engine.can(u, Accion.EXPORT, Recurso.DASHBOARD_EJECUTIVO) is None

def test_alcance_export_modulo_capa_por_lectura():
    gd = U(Rol.GERENTE_DISTRITO)  # export team, read dashboard team → team
    assert engine.alcance_export_modulo(gd, Recurso.DASHBOARD_EJECUTIVO) == Alcance.TEAM
    # GD no lee parrilla.configurar → export sobre ese módulo = None
    assert engine.alcance_export_modulo(gd, Recurso.PARRILLA_CONFIGURAR) is None
    rm = U(Rol.REPRESENTANTE_MEDICO)  # RM no exporta nada
    assert engine.alcance_export_modulo(rm, Recurso.DASHBOARD_EJECUTIVO) is None
    ana = U(Rol.ANALISTA_DATOS)  # export all, read medico.panel all → all
    assert engine.alcance_export_modulo(ana, Recurso.MEDICO_PANEL) == Alcance.ALL

def test_admin_concede_todo():
    a = U(Rol.ADMIN)
    for recurso in RECURSOS:
        assert engine.can(a, Accion.ADMIN, recurso) == Alcance.ALL

def test_firewall_medico():
    med = U(Rol.GERENTE_MEDICO)
    for recurso in (Recurso.PRODUCTIVIDAD_COMERCIAL, Recurso.RANKING_RKT,
                    Recurso.COSTOROI_VER, Recurso.COSTOROI_CONFIGURAR):
        for a in Accion:
            assert engine.can(med, a, recurso) is None

def test_solo_admin_gestiona_usuarios():
    for rol in Rol:
        u = U(rol)
        esperado = Alcance.ALL if rol == Rol.ADMIN else None
        assert engine.can(u, Accion.ADMIN, Recurso.CONFIG_USUARIOS) == esperado
        # ni Presidencia (Director General) tiene lectura
        if rol == Rol.PRESIDENCIA:
            assert engine.can(u, Accion.READ, Recurso.CONFIG_USUARIOS) is None

def test_analista_no_escribe():
    ana = U(Rol.ANALISTA_DATOS)
    for recurso in RECURSOS:
        for a in (Accion.REGISTER, Accion.CONFIGURE, Accion.APPROVE, Accion.ADMIN):
            assert engine.can(ana, a, recurso) is None

def test_finanzas_configura_director_aprueba():
    fin = U(Rol.FINANZAS); dire = U(Rol.PRESIDENCIA)
    assert engine.can(fin, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(fin, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) is None
    assert engine.can(dire, Accion.APPROVE, Recurso.COSTOROI_CONFIGURAR) == Alcance.ALL
    assert engine.can(dire, Accion.CONFIGURE, Recurso.COSTOROI_CONFIGURAR) is None
```

Run: `python -m pytest tests/test_authz_engine.py -v` → FAIL (engine no existe).

- [ ] **Step 2: Implementar `engine.py`**:

```python
"""Motor de autorización: evalúa la matriz canónica (app/core/authz/matrix.MATRIZ).
`user` es cualquier objeto con `.rol` (y `.rm_id`/`.gerente_id` para los filtros de scope)."""
from app.core.authz.constantes import Accion, Alcance, Recurso, alcance_min
from app.core.authz.matrix import MATRIZ

# Acciones cuya concesión implica READ al mismo alcance (export NO se incluye: es independiente)
_IMPLICAN_READ = (Accion.CONFIGURE, Accion.APPROVE, Accion.REGISTER)


def _celda(rol, recurso):
    return MATRIZ.get(recurso, {}).get(rol)


def _read_scope(rol, recurso):
    """Alcance de READ para (rol, recurso), incluyendo la implicación de configure/approve/register
    y admin. None si no hay lectura."""
    celda = _celda(rol, recurso)
    if celda is None:
        return None
    accion, alcance = celda
    if accion == Accion.ADMIN:
        return Alcance.ALL
    if accion == Accion.READ or accion in _IMPLICAN_READ:
        return alcance
    return None  # export puro no da lectura


def can(user, accion: Accion, recurso: str):
    """Alcance concedido para (accion, recurso) o None (deny)."""
    celda = _celda(user.rol, recurso)
    if celda is None:
        return None
    g_accion, g_alcance = celda
    if g_accion == Accion.ADMIN:
        return Alcance.ALL
    if g_accion == accion:
        return g_alcance
    if accion == Accion.READ and g_accion in _IMPLICAN_READ:
        return g_alcance
    return None


def puede(user, accion: Accion, recurso: str) -> bool:
    return can(user, accion, recurso) is not None


def alcance_export_modulo(user, recurso: str):
    """Alcance efectivo de EXPORT sobre un módulo concreto: capado por la lectura del usuario en
    ese módulo. None si el usuario no tiene capacidad de export o no lee el módulo.
    (El recurso EXPORTACION lleva la capacidad; el tope viene de la lectura del módulo)."""
    cap = can(user, Accion.EXPORT, Recurso.EXPORTACION)
    if cap is None:
        return None
    # ADMIN cae aquí con cap=ALL y lectura=ALL → min = ALL (sin caso especial).
    lectura = _read_scope(user.rol, recurso)
    if lectura is None:
        return None
    return alcance_min(cap, lectura)
```

Run: `python -m pytest tests/test_authz_engine.py -v` → PASS (280 casos parametrizados + reglas).

- [ ] **Step 3: Commit** — `feat(seguridad) RBAC Fase 1 T3: motor can() con implicacion de acciones y tope de export por lectura`.

---

### Task 4: Filtros de scope (own/team/all) + guard anti-IDOR

**Files:**
- Create: `backend/app/core/authz/scope.py`
- Test: `backend/tests/test_authz_scope.py`

**Interfaces:**
- Consumes: `Alcance` (Task 2); `RepresentanteMedico` (`app.models.dimensiones`); `Rol`.
- Produces: `rm_ids_visibles(db, user, alcance) -> set[int] | None` (None = sin filtro / todos);
  `assert_ve_rm(user, rm_id, alcance) -> None` (lanza 403 si no puede); `anonimizar_para_scope(...)`
  (reubicación de `scope_gd.anonimizar_para_gd`, generalizada por alcance `team`).

- [ ] **Step 1: Test** `test_authz_scope.py` con un fake de `db.query(...)` (patrón usado en la suite
  existente de scope) o una sesión de test:

```python
import pytest
from types import SimpleNamespace
from fastapi import HTTPException
from app.core.authz.constantes import Alcance
from app.core.authz import scope

class FakeQuery:
    def __init__(self, ids): self._ids = ids
    def filter(self, *a, **k): return self
    def all(self): return [(i,) for i in self._ids]
class FakeDB:
    def __init__(self, ids): self._ids = ids
    def query(self, *a, **k): return FakeQuery(self._ids)

def U(rol, rm_id=None, gerente_id=None):
    return SimpleNamespace(rol=rol, rm_id=rm_id, gerente_id=gerente_id)

def test_all_no_filtra():
    assert scope.rm_ids_visibles(FakeDB([1,2,3]), U("X"), Alcance.ALL) is None

def test_own_solo_su_rm():
    assert scope.rm_ids_visibles(FakeDB([]), U("X", rm_id=7), Alcance.OWN) == {7}

def test_own_sin_rm_id_conjunto_vacio():
    assert scope.rm_ids_visibles(FakeDB([]), U("X", rm_id=None), Alcance.OWN) == set()

def test_team_usa_equipo_del_gd():
    assert scope.rm_ids_visibles(FakeDB([4,5]), U("GERENTE_DISTRITO", gerente_id=9), Alcance.TEAM) == {4,5}

def test_assert_ve_rm_bloquea_ajeno():
    with pytest.raises(HTTPException) as e:
        scope.assert_ve_rm(U("REPRESENTANTE_MEDICO", rm_id=7), 8, Alcance.OWN)
    assert e.value.status_code == 403

def test_assert_ve_rm_permite_propio():
    scope.assert_ve_rm(U("REPRESENTANTE_MEDICO", rm_id=7), 7, Alcance.OWN)  # no lanza

def test_assert_ve_rm_all_permite_todo():
    scope.assert_ve_rm(U("PRESIDENCIA"), 999, Alcance.ALL)  # no lanza
```

- [ ] **Step 2: Implementar `scope.py`** (reusa la lógica de `scope_gd.rm_ids_de_gd`):

```python
"""Filtros de alcance de datos (ABAC own/team/all) y guard anti-IDOR por registro."""
from fastapi import HTTPException, status
from sqlalchemy.orm import Session
from app.core.authz.constantes import Alcance
from app.models.dimensiones import RepresentanteMedico


def rm_ids_de_equipo(db: Session, gerente_id) -> set[int]:
    if not gerente_id:
        return set()
    return {r[0] for r in db.query(RepresentanteMedico.id)
            .filter(RepresentanteMedico.gerente_id == gerente_id).all()}


def rm_ids_visibles(db: Session, user, alcance: Alcance) -> set[int] | None:
    """Conjunto de rm_id que el usuario puede ver con este alcance. None = sin filtro (todos)."""
    if alcance == Alcance.ALL:
        return None
    if alcance == Alcance.OWN:
        return {user.rm_id} if getattr(user, "rm_id", None) else set()
    if alcance == Alcance.TEAM:
        return rm_ids_de_equipo(db, getattr(user, "gerente_id", None))
    return set()  # NONE u otro → nada


def assert_ve_rm(user, rm_id: int, alcance: Alcance) -> None:
    """Guard por registro: 403 si el usuario no puede ver ese rm_id bajo el alcance dado."""
    if alcance == Alcance.ALL:
        return
    if alcance == Alcance.OWN:
        if getattr(user, "rm_id", None) == rm_id:
            return
    elif alcance == Alcance.TEAM:
        # la verificación de equipo requiere db; el caller que ya cargó rm_ids_visibles debe
        # usar ese conjunto. Este guard cubre own/all; para team, ver rm_ids_visibles.
        pass
    raise HTTPException(status_code=status.HTTP_403_FORBIDDEN,
                        detail="No autorizado sobre ese registro")
```

> Nota de diseño: `assert_ve_rm` cubre `own`/`all` sin `db`. Para `team` el caller debe verificar
> `rm_id in rm_ids_visibles(db, user, TEAM)` (evita una query por registro). Documentarlo en el
> docstring y añadir un test que muestre el patrón team con el conjunto precomputado.

- [ ] **Step 3: Verificar que `scope_gd.py` sigue intacto** (no se toca en Fase 1; su reemplazo por
  `scope.py` es de Fase 2). Solo se añade `scope.py` nuevo.

Run: `python -m pytest tests/test_authz_scope.py -v` → PASS

- [ ] **Step 4: Commit** — `feat(seguridad) RBAC Fase 1 T4: filtros de scope own/team/all + guard anti-IDOR`.

---

### Task 5: Seed idempotente de la matriz + auditoría helper

**Files:**
- Create: `backend/app/core/authz/seed.py`
- Create: `backend/app/core/authz/audit.py`
- Create: `backend/scripts/seed_authz.py`
- Test: `backend/tests/test_authz_seed.py`, `backend/tests/test_authz_audit.py`

**Interfaces:**
- Consumes: `RECURSOS_META`, `MATRIZ` (Task 2); `Recurso`, `RolPermiso`, `AuditoriaSeguridad` (Task 1).
- Produces: `seed_recursos(db)`, `seed_permisos(db)`, `sembrar_todo(db) -> dict` (conteos);
  `registrar_evento_seguridad(db, actor, evento, **campos)`.

- [ ] **Step 1: Test seed** `test_authz_seed.py` (usa la sesión de test de la suite; DB de test):

```python
from app.core.authz import seed
from app.models.seguridad_rbac import Recurso, RolPermiso

def test_seed_idempotente(db_session):
    r1 = seed.sembrar_todo(db_session)
    n_rec = db_session.query(Recurso).count()
    n_perm = db_session.query(RolPermiso).count()
    assert n_rec == 28
    assert n_perm > 0
    # segunda pasada: no duplica ni cambia conteos
    r2 = seed.sembrar_todo(db_session)
    assert db_session.query(Recurso).count() == n_rec
    assert db_session.query(RolPermiso).count() == n_perm

def test_seed_permisos_reflejan_matriz(db_session):
    seed.sembrar_todo(db_session)
    # config.usuarios solo ADMIN admin
    filas = db_session.query(RolPermiso).filter_by(recurso="config.usuarios").all()
    assert {(f.rol, f.accion, f.alcance) for f in filas} == {("ADMIN", "admin", "all")}
```

- [ ] **Step 2: Implementar `seed.py`** (upsert por llave natural, idempotente):

```python
"""Siembra idempotente de la matriz canónica (matrix.MATRIZ) a Security.DIM_Recurso /
FACT_RolPermiso. Re-ejecutable: inserta lo faltante, actualiza el alcance si cambió, borra
las filas de permiso que ya no estén en la matriz (para que la BD refleje exactamente el código)."""
from loguru import logger
from sqlalchemy.orm import Session
from app.core.authz.constantes import Accion, RECURSOS_META
from app.core.authz.matrix import MATRIZ
from app.models.seguridad_rbac import Recurso, RolPermiso

_IMPLICAN_READ = (Accion.CONFIGURE, Accion.APPROVE, Accion.REGISTER)


def seed_recursos(db: Session) -> int:
    existentes = {r.slug: r for r in db.query(Recurso).all()}
    n = 0
    for slug, (nombre, modulo) in RECURSOS_META.items():
        r = existentes.get(slug)
        if r is None:
            db.add(Recurso(slug=slug, nombre=nombre, modulo=modulo)); n += 1
        elif (r.nombre, r.modulo) != (nombre, modulo):
            r.nombre, r.modulo = nombre, modulo
    db.flush()
    return n


def _grants_de_celda(celda):
    """Expande una celda (accion, alcance) al conjunto de (accion, alcance) que persiste:
    la propia + admin=todo. Se persiste SOLO la celda base (no la implicación read), porque el
    motor deriva la implicación en runtime; así FACT_RolPermiso == matriz literal (auditable)."""
    if celda is None:
        return []
    return [celda]


def seed_permisos(db: Session) -> int:
    # Estado deseado desde la matriz: {(rol, recurso, accion): alcance}
    deseado = {}
    for recurso, fila in MATRIZ.items():
        for rol, celda in fila.items():
            for accion, alcance in _grants_de_celda(celda):
                deseado[(rol.value, recurso, accion.value)] = alcance.value

    actuales = {(p.rol, p.recurso, p.accion): p for p in db.query(RolPermiso).all()}
    cambios = 0
    # upsert
    for (rol, recurso, accion), alcance in deseado.items():
        p = actuales.get((rol, recurso, accion))
        if p is None:
            db.add(RolPermiso(rol=rol, recurso=recurso, accion=accion, alcance=alcance)); cambios += 1
        elif p.alcance != alcance:
            p.alcance = alcance; cambios += 1
    # borrar lo que ya no está en la matriz
    for llave, p in actuales.items():
        if llave not in deseado:
            db.delete(p); cambios += 1
    db.flush()
    return cambios


def sembrar_todo(db: Session) -> dict:
    nr = seed_recursos(db)
    np = seed_permisos(db)
    db.commit()
    logger.info(f"[authz.seed] recursos+={nr}, permisos_cambios={np}")
    return {"recursos_nuevos": nr, "permisos_cambios": np}
```

- [ ] **Step 3: `audit.py`** helper:

```python
"""Registro de eventos sensibles en Security.FACT_AuditoriaSeguridad (append-only)."""
from loguru import logger
from sqlalchemy.orm import Session
from app.models.seguridad_rbac import AuditoriaSeguridad

def registrar_evento_seguridad(db: Session, actor, evento: str, *, recurso=None, accion=None,
                               alcance=None, objetivo=None, detalle=None, resultado="OK") -> None:
    """No debe romper el flujo de negocio si falla (best-effort). Nunca guarda PII sensible."""
    try:
        db.add(AuditoriaSeguridad(
            actor_usuario_id=getattr(actor, "id", None),
            actor_rol=getattr(getattr(actor, "rol", None), "value", None),
            evento=evento, recurso=recurso, accion=accion, alcance=alcance,
            objetivo=objetivo, detalle=detalle, resultado=resultado))
        db.commit()
    except Exception as e:  # noqa: BLE001
        db.rollback()
        logger.warning(f"[authz.audit] no se pudo registrar '{evento}': {e}")
```

- [ ] **Step 4: Test audit** `test_authz_audit.py`:

```python
from types import SimpleNamespace
from app.core.authz.audit import registrar_evento_seguridad
from app.models.seguridad_rbac import AuditoriaSeguridad
from app.models.usuario import Rol

def test_registra_evento(db_session):
    actor = SimpleNamespace(id=1, rol=Rol.ADMIN)
    registrar_evento_seguridad(db_session, actor, "ROL_ASIGNADO", objetivo="user:5",
                               detalle="rol_anterior=CONSULTA rol_nuevo=FINANZAS")
    fila = db_session.query(AuditoriaSeguridad).order_by(AuditoriaSeguridad.id.desc()).first()
    assert fila.evento == "ROL_ASIGNADO" and fila.actor_rol == "ADMIN"
```

- [ ] **Step 5: `scripts/seed_authz.py`** (ejecutable, idempotente):

```python
"""Siembra la matriz RBAC en la BD. Idempotente. Uso: python scripts/seed_authz.py"""
from app.db.database import SessionLocal
from app.core.authz.seed import sembrar_todo

if __name__ == "__main__":
    db = SessionLocal()
    try:
        print(sembrar_todo(db))
    finally:
        db.close()
```

Run: `python -m pytest tests/test_authz_seed.py tests/test_authz_audit.py -v` → PASS
Run (contra BD local `scgcpr`): `python scripts/seed_authz.py` → imprime conteos; segunda corrida `permisos_cambios=0`.

- [ ] **Step 6: Commit** — `feat(seguridad) RBAC Fase 1 T5: seed idempotente de la matriz + helper de auditoria + script`.

---

### Task 6: Revocación por cambio de rol (`iat` + `roles_actualizado_en`)

**Files:**
- Modify: `backend/app/core/security.py` (añadir `iat` al access token)
- Modify: `backend/app/core/deps.py` (rechazar tokens con `iat < roles_actualizado_en`)
- Modify: `backend/app/api/v1/routers/admin.py` (al cambiar `rol` en update usuario: fijar
  `roles_actualizado_en=now()`, revocar refresh tokens y auditar `ROL_ASIGNADO`)
- Test: `backend/tests/test_authz_revocacion.py`

**Interfaces:**
- Consumes: `registrar_evento_seguridad` (Task 5); `token_store` (existente).
- Produces: access token con claim `iat` (epoch int); `get_current_user` valida `iat`.

- [ ] **Step 1: Añadir `iat` en `create_access_token`** (`security.py`):

```python
def create_access_token(subject, expires_delta=None, extra_claims=None) -> str:
    now = datetime.now(timezone.utc)
    expire = now + (expires_delta or timedelta(minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES))
    payload = {"sub": str(subject), "exp": expire, "iat": int(now.timestamp()),
               "type": "access", "jti": uuid.uuid4().hex}
    if extra_claims:
        payload.update(extra_claims)
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
```

- [ ] **Step 2: Validar `iat` en `get_current_user`** (`deps.py`) — tras cargar `user`:

```python
    # Revocación por cambio de rol: un access token emitido ANTES de roles_actualizado_en
    # ya no es válido (sus permisos podrían haber cambiado).
    ra = getattr(user, "roles_actualizado_en", None)
    if ra is not None:
        iat = payload.get("iat")
        if ra.tzinfo is None:
            ra = ra.replace(tzinfo=timezone.utc)
        if iat is None or iat < int(ra.timestamp()):
            raise credentials_exc
```

(añadir `from datetime import timezone` a los imports de `deps.py`).

- [ ] **Step 3: En `admin.py` update de usuario**, detectar cambio de rol. Localizar el endpoint
  `PUT /admin/usuarios/{id}` y, si `rol` cambia, fijar `roles_actualizado_en`, revocar refresh
  tokens del usuario (`token_store`) y auditar. Patrón:

```python
    rol_anterior = usuario.rol
    # ... aplicar cambios del payload ...
    if "rol" in datos and usuario.rol != rol_anterior:
        usuario.roles_actualizado_en = datetime.now(timezone.utc)
        registrar_evento_seguridad(db, current_user, "ROL_ASIGNADO", objetivo=f"user:{usuario.id}",
            detalle=f"rol_anterior={rol_anterior.value} rol_nuevo={usuario.rol.value}")
```

> Nota: seguir el estilo exacto del endpoint existente (nombres de variables/commit). No cambiar su
> RBAC (sigue siendo `AdminOnly`). La revocación de refresh tokens es best-effort si `token_store`
> expone un método por usuario; si no lo hay, basta la invalidación por `iat` (el access vence en
> 60 min y el refresh se puede revocar en logout). Documentar la limitación.

- [ ] **Step 4: Test** `test_authz_revocacion.py`:

```python
import time
from datetime import datetime, timezone, timedelta
from app.core.security import create_access_token, decode_token

def test_token_lleva_iat():
    t = create_access_token("1")
    assert "iat" in decode_token(t)

def test_iat_anterior_a_roles_actualizado_es_invalido():
    # token emitido "hace 10s"
    viejo = create_access_token("1", expires_delta=timedelta(minutes=60))
    iat = decode_token(viejo)["iat"]
    ra = datetime.fromtimestamp(iat + 5, tz=timezone.utc)  # rol cambiado DESPUÉS del token
    assert iat < int(ra.timestamp())  # la condición que get_current_user usa para rechazar
```

(La verificación E2E de `get_current_user` se hace con el TestClient en el test de endpoint de Task 7,
usando un usuario con `roles_actualizado_en` futuro.)

Run: `python -m pytest tests/test_authz_revocacion.py -v` → PASS

- [ ] **Step 5: Commit** — `feat(seguridad) RBAC Fase 1 T6: revocacion de permisos por cambio de rol (iat + roles_actualizado_en)`.

---

### Task 7: Endpoint contrato frontend + inspección

**Files:**
- Create: `backend/app/api/v1/routers/authz.py`
- Modify: `backend/app/api/v1/router.py` (registrar el router)
- Test: `backend/tests/test_authz_endpoint.py`

**Interfaces:**
- Consumes: `can` (Task 3), `MATRIZ`/`RECURSOS_META` (Task 2), `get_current_active_user`,
  `require_roles(Rol.ADMIN)`.
- Produces: `GET /authz/me/permisos` (autenticado), `GET /authz/matriz` (solo ADMIN).

- [ ] **Step 1: `authz.py`**:

```python
"""Contrato de autorización para el frontend + inspección de la matriz (solo ADMIN)."""
from fastapi import APIRouter, Depends
from app.core.deps import get_current_active_user, require_roles
from app.core.authz.constantes import Accion, RECURSOS_META
from app.core.authz import engine
from app.models.usuario import Rol, Usuario

router = APIRouter(prefix="/authz", tags=["Autorización"])
RequireAdmin = Depends(require_roles(Rol.ADMIN))

# acciones no-read que exponemos por recurso (para que el frontend decida botones)
_ACCIONES = [Accion.READ, Accion.REGISTER, Accion.CONFIGURE, Accion.APPROVE, Accion.EXPORT, Accion.ADMIN]


@router.get("/me/permisos")
def mis_permisos(current_user: Usuario = Depends(get_current_active_user)):
    """Capacidades efectivas del usuario: {recurso: {accion: alcance}} solo para lo concedido.
    El frontend deriva navegación/controles de aquí. Export por módulo incluido como
    `export_efectivo` (capado por lectura)."""
    permisos = {}
    for recurso in RECURSOS_META:
        caps = {}
        for accion in _ACCIONES:
            alc = engine.can(current_user, accion, recurso)
            if alc is not None:
                caps[accion.value] = alc.value
        exp = engine.alcance_export_modulo(current_user, recurso)
        if exp is not None:
            caps["export_efectivo"] = exp.value
        if caps:
            permisos[recurso] = caps
    return {"rol": current_user.rol.value, "permisos": permisos}


@router.get("/matriz", dependencies=[RequireAdmin])
def ver_matriz():
    """Matriz completa (solo ADMIN) para inspección/auditoría."""
    from app.core.authz.matrix import MATRIZ
    salida = []
    for recurso, (nombre, modulo) in RECURSOS_META.items():
        fila = {"recurso": recurso, "nombre": nombre, "modulo": modulo, "roles": {}}
        for rol, celda in MATRIZ[recurso].items():
            fila["roles"][rol.value] = None if celda is None else {
                "accion": celda[0].value, "alcance": celda[1].value}
        salida.append(fila)
    return {"recursos": salida}
```

- [ ] **Step 2: Registrar en `router.py`**:

```python
from app.api.v1.routers.authz import router as authz_router
...
api_router.include_router(authz_router)  # RBAC Fase 1: contrato de autorizacion
```

- [ ] **Step 3: Test endpoint** `test_authz_endpoint.py` (TestClient + login como en la suite existente):

```python
def test_me_permisos_rm(client, token_rm):
    r = client.get("/api/v1/authz/me/permisos", headers={"Authorization": f"Bearer {token_rm}"})
    assert r.status_code == 200
    data = r.json()
    # RM: puede registrar visita (own), no ve config.usuarios
    assert data["permisos"]["visita.registrar"]["register"] == "own"
    assert "config.usuarios" not in data["permisos"]

def test_matriz_solo_admin(client, token_rm, token_admin):
    assert client.get("/api/v1/authz/matriz",
                      headers={"Authorization": f"Bearer {token_rm}"}).status_code == 403
    r = client.get("/api/v1/authz/matriz", headers={"Authorization": f"Bearer {token_admin}"})
    assert r.status_code == 200 and len(r.json()["recursos"]) == 28
```

> Los fixtures `client`, `token_rm`, `token_admin` deben seguir el patrón de la suite existente
> (revisar `conftest.py`); si no existen, crearlos ahí reutilizando el fixture de sesión/usuarios.

Run: `python -m pytest tests/test_authz_endpoint.py -v` → PASS

- [ ] **Step 4: Verificación E2E de revocación** (cierra Task 6): test que crea un usuario con
  `roles_actualizado_en` en el futuro y confirma que su token previo da 401 en `/authz/me/permisos`.

- [ ] **Step 5: Commit** — `feat(seguridad) RBAC Fase 1 T7: endpoint /authz/me/permisos (contrato frontend) + /authz/matriz (ADMIN)`.

---

### Task 8: Suite completa + documentación + verificación final

**Files:**
- Modify: `CLAUDE.md` (nueva sección "25. Módulo de Seguridad RBAC/ABAC")
- Verify: toda la suite `pytest`

- [ ] **Step 1: Correr toda la suite** `cd backend && python -m pytest -q` → todos verdes
  (los ~350 previos + los nuevos de authz). Ninguna prueba existente debe romperse (es aditivo).

- [ ] **Step 2: `alembic upgrade head` + `python scripts/seed_authz.py`** contra `scgcpr` (local);
  segunda corrida del seed → `permisos_cambios=0` (idempotencia confirmada en vivo).

- [ ] **Step 3: Documentar en `CLAUDE.md`** una sección nueva concisa: el modelo (recurso/acción/
  alcance), la ubicación de la fuente de verdad (`app/core/authz/matrix.py`), cómo agregar/cambiar un
  permiso (editar la matriz → correr seed → el test-oráculo obliga a actualizar el spec), el endpoint
  de contrato, y que **Fase 2 (wiring de guards + flip) está pendiente**.

- [ ] **Step 4: Commit** — `docs(seguridad) RBAC Fase 1 T8: documentar modulo de autorizacion en CLAUDE.md + verificacion suite completa`.

---

## Cierre

Al terminar las 8 tareas: usar **superpowers:finishing-a-development-branch**. Reportar:
arquitectura implementada, archivos/migraciones, decisiones/suposiciones (incl. deuda §9 del spec),
resultados exactos de pytest, y recordar que **la activación (Fase 2) es una entrega aparte** — en
esta Fase 1 el acceso efectivo de los usuarios actuales NO cambió.
