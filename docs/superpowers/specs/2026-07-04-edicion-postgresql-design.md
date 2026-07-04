# Fase 2 — Edición PostgreSQL — Diseño

**Fecha:** 2026-07-04 · **Preparado para:** Moisés · **Confidencial**
**Estado:** Aprobado (brainstorming) — pendiente de plan de implementación.

---

## 1. Resumen y contexto

Segunda de tres fases del plan multi-edición. **Fase 1 (completa, en `master`)** movió el
motor de cálculo (los 5 stored procedures) a Python puro, dejando el core casi agnóstico de
BD. **Esta Fase 2** entrega la **edición PostgreSQL** (clientes grandes) como un repositorio
separado `MSM-postgres`, verificada **end-to-end** contra un PostgreSQL real.

**Entorno de verificación disponible:** PostgreSQL 17 corriendo en `127.0.0.1:5432`
(superusuario `postgres`/`postgres`, cluster `C:\Users\Lenovo\pgdata`) — permite verificar en
vivo que las migraciones aplican y la app arranca contra Postgres.

---

## 2. Estado actual (portabilidad pendiente)

Tras la Fase 1, queda **SQL crudo con dialecto SQL Server** (~77 ocurrencias) en 5 archivos:
`categorizacion_service.py`, `cobertura_predictiva_service.py`,
`api/v1/routers/cobertura_predictiva.py`, `api/v1/routers/dims.py`, `models/dimensiones.py`.
Patrones a neutralizar:
- **Identificadores mixtos sin comillas** (`cat.DimPais`, `DW.FACT_...`): en Postgres los
  nombres mixtos se pliegan a minúsculas si no van entre comillas → no matchean. Solución
  portable: **entrecomillar** (`"cat"."DimPais"`), que funciona también en SQL Server con
  `QUOTED_IDENTIFIER ON` (default).
- `ISNULL(a,b)` → `COALESCE(a,b)` (ANSI).
- `N'texto'` → `'texto'`.
- `TOP n` → quitar y usar `ORDER BY` + `.first()`/`.limit(n)`.
- `GETUTCDATE()`/`SYSUTCDATETIME()`/`GETDATE()` → pasar el timestamp desde Python como
  parámetro; `server_default` de timestamps en modelos → `func.now()` (SQLAlchemy lo
  renderiza por dialecto).
- `DATEPART(WEEKDAY,...)` → cálculo en Python (ya hecho en el motor de cobertura).

El star-schema `cat.*` y el staging `stg.*` **no son modelos ORM** — solo existen como DDL en
migraciones T-SQL (`NVARCHAR`, `IDENTITY`, etc.). El baseline PG debe recrearlos traducidos.

---

## 3. Parte A — Barrido de portabilidad (repo actual `MSM`)

Neutralizar los 77 SQL-Server-isms para que el mismo SQL corra en ambos motores:
- Entrecomillar todos los identificadores en `text()`.
- `ISNULL`→`COALESCE`, `N''`→`''`, quitar `TOP` (ORDER BY + first/limit).
- Timestamps por parámetro; `server_default` timestamps → `func.now()`.
- `/admin/reset` ya está ramificado por `DB_ENGINE` (Fase 1).

**Verificación:** la **suite completa sigue verde contra SQL Server** (no romper la edición
mssql). Esto es la fundación compartida; se commitea a `master` (beneficia a ambas ediciones).

---

## 4. Parte B — Crear el repo `MSM-postgres`

`git clone` del repo `MSM` a `C:\Users\Lenovo\Proyecto\MSM-postgres` (repo git separado que
conserva la historia). A partir de aquí, la edición PostgreSQL evoluciona en su propio repo.

---

## 5. Parte C — Hacer `MSM-postgres` PG-nativo (verificado en vivo)

- **Driver / dependencias:** `requirements.txt` reemplaza `pymssql` por `psycopg2-binary`.
- **Config:** `build_db_url` genera `postgresql+psycopg2://…`; `DB_PORT` default `5432`;
  `DB_ENGINE` deriva `postgres`. `.env` / `.env.example` para Postgres
  (`DB_NAME=scgcpr`, `DB_USER=segura`, `DB_PORT=5432`).
- **Alembic:** `alembic/env.py` conserva `include_schemas=True`. Los esquemas
  (`Config`, `DW`, `ETL`, `Audit`, `Security`, `exam`, `Visita`, `cat`, `stg`) se crean con
  `CREATE SCHEMA IF NOT EXISTS` al inicio del baseline.
- **Baseline PG** — una sola migración nueva (`0001_baseline_postgres`) que:
  1. Crea los esquemas.
  2. `Base.metadata.create_all(bind=op.get_bind())` — todas las tablas ORM (Config/DW/ETL/
     Audit/Security/exam/Visita) con sus tipos ya portables (`LargeBinary`→`bytea`,
     `Numeric`, `String`, `Boolean`).
  3. DDL explícito (portable) del star-schema `cat.*` y staging `stg.*` traducido de T-SQL
     (`NVARCHAR`→`VARCHAR`, `IDENTITY`→`GENERATED ALWAYS AS IDENTITY`, `BIT`→`boolean`,
     `DATETIME2`→`timestamptz`), + datos semilla mínimos de catálogos si el SP los requería.
- **docker-compose:** servicio `db` = `postgres:17-alpine` con volumen; backend con
  `psycopg2`; frontend igual.

**Verificación en vivo (contra el Postgres en 5432):**
1. Crear rol `segura` y BD `scgcpr` en el Postgres local.
2. `alembic upgrade head` → aplica el baseline **sin error** (todas las tablas/esquemas creados).
3. `python -c "import app.main"` + arrancar uvicorn contra Postgres.
4. **Smoke test:** `POST /auth/login` (tras sembrar el admin), y un recálculo mínimo
   (`recalcular_ciclo_py`) con datos sembrados → devuelve el dict correcto y escribe el ranking.
5. `pytest` de la suite unit (dialecto-agnóstica) en verde.

---

## 6. Parte D — Documentación

En `MSM-postgres`: `DEPLOY-POSTGRES.md` con el procedimiento (`docker compose up`,
migraciones, seed del admin, smoke test) y las diferencias respecto a la edición SQL Server.
Actualizar `README`/`CLAUDE.md` de esa edición para indicar que es la **edición PostgreSQL**.

---

## 7. Alcance y pruebas

- **Parte A:** verificada contra SQL Server (suite completa verde) en el repo `MSM`.
- **Parte C:** verificada en vivo contra PostgreSQL 17 (`5432`): migración aplica, app arranca,
  smoke test de login + recálculo, suite unit verde.
- **Sin cambios funcionales:** la lógica de negocio es idéntica; solo cambia el motor de BD.

## 8. Fuera de alcance (Fase 2)

- Edición SQL Server-contenedor + stacks de despliegue/TLS/backups (Fase 3).
- Migración de datos reales SQL Server → PostgreSQL (cada cliente parte de BD limpia; la
  carga se hace por los flujos ETL/DIMs existentes).
- Optimizaciones específicas de PostgreSQL (índices GIN, particionado, etc.).
