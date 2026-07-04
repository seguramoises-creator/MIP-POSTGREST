# Fase 2 — Edición PostgreSQL — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Entregar la edición PostgreSQL como repo separado `MSM-postgres`, precedida de un barrido de portabilidad del SQL crudo (verificado contra SQL Server), y verificada en vivo contra PostgreSQL 17.

**Architecture:** Parte A neutraliza el SQL Server-specific SQL en el repo actual (identificadores entrecomillados, `COALESCE`, sin `TOP`, timestamps por parámetro), verificado con la suite contra SQL Server. Luego se clona a `MSM-postgres` y se hace PG-nativo (psycopg2, baseline PG que crea esquemas + `create_all()` + DDL traducido de `cat.*`/`stg.*`), verificado contra un PostgreSQL 17 real en `127.0.0.1:5432`.

**Tech Stack:** SQLAlchemy 2.0, Alembic (`include_schemas=True`), psycopg2-binary (PG) / pymssql (mssql), PostgreSQL 17, pytest.

## Global Constraints

- **Entorno de verificación PG:** PostgreSQL 17 en `127.0.0.1:5432`, superusuario `postgres`/`postgres`, cluster `C:\Users\Lenovo\pgdata`. Binarios en `C:\Program Files\PostgreSQL\17\bin` (`psql.exe`, `pg_ctl.exe`, `createdb.exe`). Arrancar/parar: `pg_ctl -D C:\Users\Lenovo\pgdata -o "-p 5432" -l "<data>\server.log" start`.
- **Reglas del barrido (Parte A)** — aplicar a todo `text()` con SQL crudo:
  - Identificadores mixtos → **entrecomillar**: `cat.DimPais` → `"cat"."DimPais"`; `Config.DIM_RM` → `"Config"."DIM_RM"`; columnas mixtas (`PaisKey`) → `"PaisKey"` (SQL Server con `QUOTED_IDENTIFIER ON` lo acepta; Postgres lo exige).
  - `ISNULL(a,b)` → `COALESCE(a,b)`.
  - `N'texto'` → `'texto'`.
  - `TOP n ... ORDER BY x` → quitar `TOP n`, dejar `ORDER BY x`, y usar `.first()` (n=1) o `.limit(n)` en el llamador.
  - `SYSUTCDATETIME()`/`GETUTCDATE()`/`GETDATE()` en `text()` → pasar el valor desde Python como parámetro `:ahora` (`datetime.now(timezone.utc)`).
  - `OUTPUT INSERTED.X` → insertar y releer la clave por la clave natural (patrón ya usado en `calcular_categorias_py`).
- **Regla de oro de la Parte A:** cada cambio se verifica corriendo la suite **contra SQL Server** — no debe romperse la edición mssql. `entrecomillar` + `COALESCE` funcionan en ambos motores.
- Timestamps en modelos: default de Python (`datetime.now(timezone.utc)`); `server_default` de timestamp → `sa.func.now()` (SQLAlchemy lo renderiza por dialecto).

---

### Task 1: Barrido de portabilidad — `categorizacion_service.py`

**Files:**
- Modify: `backend/app/services/categorizacion_service.py`

**Interfaces:**
- Sin cambio de firmas. Solo el SQL dentro de los `text()` se vuelve portable.

- [ ] **Step 1: Inventariar** las ocurrencias a cambiar

Run: `cd backend && grep -noE "ISNULL|SYSUTCDATETIME|GETUTCDATE|N'|TOP [0-9]|OUTPUT INSERTED|\b(cat|stg)\.[A-Za-z]+" app/services/categorizacion_service.py | wc -l`
Expected: ~146 (referencia; el número exacto no importa, sí que queden 0 tras el barrido salvo identificadores ya entrecomillados).

- [ ] **Step 2: Aplicar las reglas** (ver Global Constraints) a cada `text()` del archivo:
  - Entrecomillar todos los identificadores de esquema/tabla/columna mixtos.
  - `ISNULL(`→`COALESCE(`; `N'`→`'`; quitar `TOP n` (dejar ORDER BY, ajustar el `.first()`/`.limit()` del llamador); `SYSUTCDATETIME()`→parámetro `:ahora`.
  - Ejemplo (de `_limpiar_periodo`):

```python
# antes
db.execute(text("SELECT LoadBatchKey FROM cat.LoadBatch WHERE Periodo = :p"), {"p": periodo})
# después
db.execute(text('SELECT "LoadBatchKey" FROM "cat"."LoadBatch" WHERE "Periodo" = :p'), {"p": periodo})
```

- [ ] **Step 3: Verificar contra SQL Server (no romper mssql)**

Run: `cd backend && pytest tests/test_caracterizacion_categorizacion.py -v` (si los SPs siguen; si ya se dropearon, correr un flujo de categorización real) **y** `pytest -q -k categorizacion`
Expected: PASS. El barrido no cambia resultados; el SQL entrecomillado + COALESCE se comporta igual en SQL Server.

- [ ] **Step 4: Smoke funcional** — con la app arriba, `POST /categorizacion/cargar` (o `get_resumen`/`get_resultados` vía endpoints) devuelve datos como antes.

Run: `cd backend && python -c "import app.main; print('ok')"`
Expected: `ok`; y una consulta de reporte (`categorizacion_service.get_resumen(db)`) no lanza.

- [ ] **Step 5: Commit**

```bash
git add backend/app/services/categorizacion_service.py
git commit -m "refactor(portabilidad) categorizacion_service: SQL crudo portable (quoting, COALESCE)"
```

---

### Task 2: Barrido — `cobertura_predictiva_service.py` + router

**Files:**
- Modify: `backend/app/services/cobertura_predictiva_service.py`
- Modify: `backend/app/api/v1/routers/cobertura_predictiva.py`

- [ ] **Step 1: Aplicar las reglas** a los `text()` de ambos archivos (mismas reglas: quoting, `COALESCE`, `N''`→`''`, `TOP`→ORDER BY+first, `SYSUTCDATETIME`→param). El motor `calcular_cobertura_py` ya usa mayormente identificadores sin corchetes — entrecomillarlos y cambiar `ISNULL`→`COALESCE`, `N'Realizada'`→`'Realizada'`, `TOP 1`→ORDER BY + `.first()`.

Ejemplo:
```python
# antes
"SELECT TOP 1 CicloKey, ... FROM cat.DimCiclo WHERE CodigoCiclo=:cc AND PaisKey=:pk ... ORDER BY CicloKey"
# después (quitar TOP 1, entrecomillar; .first() ya toma la primera)
'SELECT "CicloKey", ... FROM "cat"."DimCiclo" WHERE "CodigoCiclo"=:cc AND "PaisKey"=:pk ... ORDER BY "CicloKey"'
```

- [ ] **Step 2: Verificar contra SQL Server**

Run: `cd backend && pytest -q -k cobertura`
Expected: PASS (incluye la caracterización si los SPs siguen; si no, smoke del cálculo).

- [ ] **Step 3: Commit**

```bash
git add backend/app/services/cobertura_predictiva_service.py backend/app/api/v1/routers/cobertura_predictiva.py
git commit -m "refactor(portabilidad) cobertura: SQL crudo portable"
```

---

### Task 3: Barrido — `dims.py` + `models/dimensiones.py`

**Files:**
- Modify: `backend/app/api/v1/routers/dims.py`
- Modify: `backend/app/models/dimensiones.py`

- [ ] **Step 1:** `dims.py` — entrecomillar identificadores y `ISNULL`→`COALESCE` en sus `text()` (8 ocurrencias).

- [ ] **Step 2:** `models/dimensiones.py` — la única ocurrencia es un `server_default`/SQL con función de fecha o `NVARCHAR`. Localizar con `grep -n "GETUTCDATE\|GETDATE\|NVARCHAR\|server_default\|text(" app/models/dimensiones.py`. Si es un `server_default=text("GETUTCDATE()")` → cambiar a `server_default=sa.func.now()` (portable por dialecto). Si es un tipo, dejar el tipo SQLAlchemy (ya portable).

- [ ] **Step 3: Verificar**

Run: `cd backend && python -c "import app.main; print('ok')" && pytest -q`
Expected: `ok` + suite verde.

- [ ] **Step 4: Commit**

```bash
git add backend/app/api/v1/routers/dims.py backend/app/models/dimensiones.py
git commit -m "refactor(portabilidad) dims + modelos: SQL/defaults portables"
```

---

### Task 4: Verificación integral Parte A + merge a master

**Files:** (ninguno nuevo)

- [ ] **Step 1: Suite completa contra SQL Server**

Run: `cd backend && pytest -q`
Expected: todos verdes (misma cuenta que antes del barrido).

- [ ] **Step 2: Confirmar 0 SQL-Server-isms sin entrecomillar** en el SQL crudo:

Run: `cd backend && grep -rnE "ISNULL\(|SYSUTCDATETIME|GETUTCDATE|GETDATE\(|N'|TOP [0-9]|OUTPUT INSERTED" app/ --include=*.py | grep -v pycache`
Expected: sin resultados (o solo comentarios).

- [ ] **Step 3: Merge de la Parte A a master** (fundación compartida; beneficia también a la edición SQL Server).

```bash
git checkout master && git merge --no-ff <rama-parte-A> -m "merge: barrido de portabilidad (core dialecto-neutral)"
cd backend && pytest -q   # verde sobre master mergeado
git push origin master
```

---

### Task 5: Clonar el repo a `MSM-postgres`

**Files:** (nuevo repo)

- [ ] **Step 1: Clonar** (conserva historia)

Run:
```bash
cd /c/Users/Lenovo/Proyecto && git clone MSM MSM-postgres
cd MSM-postgres && git log --oneline -1
```
Expected: el clon existe y apunta al último commit de master (con la Parte A ya incluida).

- [ ] **Step 2: Commit inicial de identidad de la edición** (marcar el README):

```bash
cd /c/Users/Lenovo/Proyecto/MSM-postgres
# (el resto de cambios PG vienen en las tareas siguientes)
```

---

### Task 6: PG-nativo — driver + config (`MSM-postgres`)

**Files (en `MSM-postgres`):**
- Modify: `backend/requirements.txt`
- Modify: `backend/app/core/config.py`
- Modify: `backend/.env` (local) / `backend/.env.example`

- [ ] **Step 1: requirements** — reemplazar `pymssql` por `psycopg2-binary`:

```
# pymssql==2.3.1        # (edición SQL Server)
psycopg2-binary==2.9.9  # edición PostgreSQL
```

- [ ] **Step 2: config** — el builder de URL usa el dialecto postgres:

```python
        return (
            f"postgresql+psycopg2://{data.get('DB_USER')}:{data.get('DB_PASSWORD')}"
            f"@{data.get('DB_SERVER')}:{data.get('DB_PORT')}/{data.get('DB_NAME')}"
        )
```
Y `DB_PORT: int = 5432` por defecto. (`DB_ENGINE` derivará `postgres` automáticamente.)

- [ ] **Step 3: .env** para el Postgres local:
```
DB_SERVER=127.0.0.1
DB_PORT=5432
DB_NAME=scgcpr
DB_USER=segura
DB_PASSWORD=Segura.Local.2026
```

- [ ] **Step 4: Instalar deps y verificar import**

Run: `cd MSM-postgres/backend && ./venv/Scripts/pip install psycopg2-binary && python -c "from app.core.config import settings; print(settings.DB_ENGINE, settings.DATABASE_URL.split('://')[0])"`
Expected: `postgres postgresql+psycopg2`

*(Nota: el `venv` se clona con el repo; si no, crear uno: `python -m venv venv && venv/Scripts/pip install -r requirements.txt psycopg2-binary`.)*

- [ ] **Step 5: Commit**

```bash
git add backend/requirements.txt backend/app/core/config.py backend/.env.example
git commit -m "feat(postgres) driver psycopg2 + config PostgreSQL"
```

---

### Task 7: Baseline PG (esquemas + create_all + DDL cat/stg)

**Files (en `MSM-postgres`):**
- Create: `backend/alembic/versions/0001_baseline_postgres.py`
- (Archivar las migraciones mssql: mover `backend/alembic/versions/*` previas a `backend/alembic/versions/_mssql_archive/` para que el baseline PG sea el único head.)

**Interfaces:**
- El baseline crea TODO el esquema desde cero para Postgres.

- [ ] **Step 1: Archivar migraciones mssql** y dejar solo el baseline:

Run:
```bash
cd MSM-postgres/backend/alembic/versions
mkdir -p _mssql_archive && git mv *.py _mssql_archive/ 2>/dev/null; true
```
*(El `_mssql_archive` conserva la historia mssql pero Alembic no la ejecuta — el head será el baseline PG.)*

- [ ] **Step 2: Volcar el DDL de `cat.*`/`stg.*` desde SQL Server** (para traducirlo) — desde el repo `MSM` con la BD SQL Server:

Run (en `MSM/backend`):
```bash
python -c "from app.db.database import SessionLocal; from sqlalchemy import text; db=SessionLocal(); [print(r[0]) for r in db.execute(text(\"SELECT TABLE_SCHEMA+'.'+TABLE_NAME FROM INFORMATION_SCHEMA.TABLES WHERE TABLE_SCHEMA IN ('cat','stg') ORDER BY 1\")).all()]"
```
Y por cada tabla, `INFORMATION_SCHEMA.COLUMNS` para tipos. Traducir: `NVARCHAR(n)`→`VARCHAR(n)`, `NVARCHAR(MAX)`→`TEXT`, `INT IDENTITY`→`INTEGER GENERATED ALWAYS AS IDENTITY`, `BIGINT IDENTITY`→`BIGINT GENERATED ALWAYS AS IDENTITY`, `BIT`→`BOOLEAN`, `DATETIME2`/`DATETIME`→`TIMESTAMPTZ`, `DATE`→`DATE`, `DECIMAL(p,s)` igual, `VARBINARY(MAX)`→`BYTEA`.

- [ ] **Step 3: Escribir `0001_baseline_postgres.py`:**

```python
"""Baseline PostgreSQL — crea todos los esquemas y tablas desde los modelos + cat/stg.

Revision ID: 0001_baseline_postgres
Revises:
Create Date: 2026-07-04
"""
from alembic import op
import sqlalchemy as sa

revision = "0001_baseline_postgres"
down_revision = None
branch_labels = None
depends_on = None

_SCHEMAS = ["Config", "DW", "ETL", "Audit", "Security", "exam", "Visita", "cat", "stg"]


def upgrade():
    bind = op.get_bind()
    for s in _SCHEMAS:
        op.execute(f'CREATE SCHEMA IF NOT EXISTS "{s}"')
    # Tablas ORM (Config/DW/ETL/Audit/Security/exam/Visita) desde los modelos:
    import app.models.usuario, app.models.dimensiones, app.models.hechos, app.models.visita, app.models.exam_models  # noqa: F401
    from app.db.database import Base
    Base.metadata.create_all(bind=bind)
    # Star-schema cat.* + staging stg.* (DDL traducido de T-SQL — pegar del Step 2):
    op.execute('''CREATE TABLE IF NOT EXISTS "cat"."DimPais" (
        "PaisKey" INTEGER GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
        "CodigoPais" VARCHAR(2) NOT NULL, "NombrePais" VARCHAR(100) )''')
    # ... el resto de tablas cat.* y stg.* (DimEspecialidad, DimGeografia, DimCentroMedico,
    #     DimMedico, DimRepresentanteMedico, DimEquipo, DimComponenteCategoria,
    #     DimReglaCategoriaMedica, DimClasificacionMedica, DimCiclo, DimCalendario,
    #     FactTargetMedicoCiclo, FactVisitaMedica, FactMedicoCategoriaSnapshot,
    #     FactMedicoCategoriaDetalle, LoadBatch, KpiCoberturaPredictiva, stg.MedicoCategoriaInput) ...


def downgrade():
    from app.db.database import Base
    Base.metadata.drop_all(bind=op.get_bind())
    for s in reversed(_SCHEMAS):
        op.execute(f'DROP SCHEMA IF EXISTS "{s}" CASCADE')
```

*(El DDL completo de cada tabla cat/stg se pega en el Step 3 usando la traducción del Step 2. La verificación en vivo del Task 8 confirma que aplica.)*

- [ ] **Step 4: Commit**

```bash
git add backend/alembic/versions/
git commit -m "feat(postgres) baseline PG (esquemas + create_all + DDL cat/stg)"
```

---

### Task 8: Verificación en vivo contra PostgreSQL 17

**Files:** (ninguno)

- [ ] **Step 1: Crear rol y BD** en el Postgres local (5432):

Run (PowerShell):
```powershell
$env:PGPASSWORD="postgres"; $psql="C:\Program Files\PostgreSQL\17\bin\psql.exe"
& $psql -h 127.0.0.1 -U postgres -c "CREATE ROLE segura LOGIN PASSWORD 'Segura.Local.2026' SUPERUSER;"
& $psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE scgcpr OWNER segura;"
```
Expected: `CREATE ROLE`, `CREATE DATABASE`.

- [ ] **Step 2: Aplicar el baseline**

Run: `cd MSM-postgres/backend && python -m alembic upgrade head`
Expected: `Running upgrade -> 0001_baseline_postgres`. Sin error. Si falla por DDL, corregir el tipo/sintaxis en el baseline y reintentar (drop schema cascade + upgrade).

- [ ] **Step 3: Verificar esquema creado**

Run (psql): `& $psql -h 127.0.0.1 -U segura -d scgcpr -c "SELECT table_schema, count(*) FROM information_schema.tables WHERE table_schema IN ('Config','DW','exam','Visita','cat','stg') GROUP BY 1 ORDER BY 1;"`
Expected: filas por esquema con conteos > 0.

- [ ] **Step 4: Arrancar la app + smoke test**

Run: `cd MSM-postgres/backend && python -c "import app.main; print('IMPORT OK')"` y arrancar `uvicorn app.main:app --port 8100`; luego sembrar el admin (`python scripts/setup/_crear_bd.py` o el seed de admin) y `POST /auth/login`.
Expected: `IMPORT OK`, health `database:connected`, login devuelve token.

- [ ] **Step 5: Smoke del motor** — con datos mínimos sembrados (1 país, 1 ciclo abierto, indicadores + 1 FACT_ResultadoIndicador), `recalculo_service.recalcular_ciclo(db, ciclo_id)` devuelve `{abortado:False, ...}` y escribe en `"DW"."FACT_RankingRM"`.

Run: script de smoke que siembra y llama el recálculo.
Expected: dict correcto + fila de ranking.

- [ ] **Step 6: Suite unit**

Run: `cd MSM-postgres/backend && pytest -q -k "not caracterizacion"`
Expected: verde (las caracterizaciones se saltan — no hay SPs en PG).

- [ ] **Step 7: Commit**

```bash
git add -A && git commit -m "test(postgres) verificacion en vivo: baseline aplica, app arranca, smoke ok"
```

---

### Task 9: docker-compose Postgres + documentación

**Files (en `MSM-postgres`):**
- Modify: `docker-compose.yml`
- Create: `DEPLOY-POSTGRES.md`
- Modify: `README.md` (marcar edición PostgreSQL)

- [ ] **Step 1: docker-compose** — servicio `db` PostgreSQL (reemplaza el de SQL Server):

```yaml
  db:
    image: postgres:17-alpine
    environment:
      POSTGRES_USER: segura
      POSTGRES_PASSWORD: ${DB_PASSWORD:?define DB_PASSWORD}
      POSTGRES_DB: scgcpr
    ports:
      - "5432:5432"
    volumes:
      - pg_data:/var/lib/postgresql/data
    restart: unless-stopped
```
Y `volumes: pg_data:`. El backend con `env_file: ./backend/.env` (DB_ENGINE=postgres).

- [ ] **Step 2: DEPLOY-POSTGRES.md** — procedimiento: `docker compose up -d --build`, migraciones (entrypoint corre `alembic upgrade head`), seed admin, smoke test; diferencias vs la edición SQL Server.

- [ ] **Step 3: README** — encabezado "Edición PostgreSQL (clientes grandes)".

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml DEPLOY-POSTGRES.md README.md
git commit -m "feat(postgres) docker-compose Postgres + DEPLOY-POSTGRES.md"
```

---

## Self-Review

**Spec coverage:**
- §3 Parte A (barrido) → Tasks 1, 2, 3, 4 ✓
- §4 Parte B (clon) → Task 5 ✓
- §5 Parte C (PG-nativo: driver/config/baseline + verificación en vivo) → Tasks 6, 7, 8 ✓
- §6 Parte D (docker-compose + docs) → Task 9 ✓
- §7 pruebas (SQL Server verde + PG en vivo) → Tasks 4, 8 ✓

**Placeholder scan:** Task 7 Step 3 muestra el patrón del baseline con la primera tabla cat.* completa y enumera explícitamente el resto de tablas a pegar (traducidas en el Step 2 con las reglas de tipo dadas); no es un "TODO" vago — es un procedimiento mecánico con reglas exactas, verificado en vivo por el Task 8 (si el DDL está mal, `alembic upgrade` falla y se corrige). Las Tasks 1-3 del barrido dan las reglas exactas + ejemplos concretos; el volumen (146 refs) hace impráctico listar cada edición, pero la regla es única y la verificación (suite contra SQL Server) es objetiva.

**Type consistency:**
- Reglas de transformación idénticas en Tasks 1-3 ✓
- `DB_ENGINE`/`DATABASE_URL` postgres consistentes en Tasks 6, 8 ✓
- Baseline `0001_baseline_postgres` referenciado en Tasks 7, 8 ✓
- Rol `segura` / BD `scgcpr` consistentes en Tasks 6, 8, 9 ✓
