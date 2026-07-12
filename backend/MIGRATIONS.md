# Migraciones de base de datos (Alembic)

Este proyecto usa **Alembic** para mantener sincronizados los modelos de SQLAlchemy
(`app/models/`) con el esquema real de la base de datos PostgreSQL. El error
`Invalid column name 'pais_id'` ocurrió porque el modelo `Indicador` definía una
columna que nunca se creó en la tabla `Config.DIM_Indicador` — el esquema y el
código se desincronizaron porque no existía un mecanismo de migraciones.

A partir de ahora, **ningún cambio de modelo debe aplicarse a mano con `ALTER TABLE`**.
Todo cambio de esquema pasa por una migración versionada.

## Configuración

`alembic/env.py` ya está configurado para:
- Tomar la cadena de conexión real desde `app.core.config.settings.DATABASE_URL`
  (es decir, desde tu `.env` — no hace falta tocar `alembic.ini`).
- Cargar el `Base.metadata` con **todos** los modelos (`usuario`, `dimensiones`, `hechos`)
  para que `--autogenerate` los detecte.
- Filtrar (`include_object`) tablas fuera de los esquemas de la app
  (`Config`, `Security`, `DW`, `Audit`, `ETL`, `dbo`).
- **`include_schemas=True`** en `context.configure()` (offline y online).

### ⚠️ Por qué `include_schemas=True` es crítico (no lo quites)

Esta es la opción que faltaba y causó la mayor parte de la confusión inicial.
Sin ella, Alembic **solo reflexiona el esquema por defecto (`dbo`)** de la BD
al comparar contra los modelos — nunca mira `Config.*`, `Security.*`,
`Audit.*`, etc. El resultado: cualquier `--autogenerate` "ve" esas tablas
como si no existieran y propone `CREATE TABLE` para tablas que ya están ahí
(esto generó el primer baseline gigante, y luego un intento de recrear
`Audit.FACT_Auditoria` desde cero).

Con `include_schemas=True`, Alembic reflexiona TODOS los esquemas de la BD
y puede comparar correctamente columna por columna — por eso el diff final
salió limpio (`ADD COLUMN` reales en vez de `CREATE TABLE`).

**Si en el futuro `--autogenerate` vuelve a proponer recrear tablas que ya
existen, lo primero que hay que revisar es que `include_schemas=True` siga
presente en ambas funciones `run_migrations_*` de `env.py`.**

## Estado actual (ya hecho — léelo para entender el setup)

Tu base de datos ya tenía todas las tablas creadas pero **sin** tabla
`alembic_version` — es decir, existía pero no estaba "bajo control" de Alembic.
Por eso el primer `--autogenerate` generó un script que intentaba **recrear
todas las tablas desde cero** (las veía como "nuevas"). Ese script habría
fallado al aplicarse (tablas duplicadas) y, peor, NO habría arreglado el
problema real porque "crear" `DIM_Indicador` con `pais_id` en una tabla que
ya existe no la altera.

La solución adoptada — el patrón estándar para meter Alembic en una BD viva —
fue dividirlo en dos migraciones, ya creadas en `alembic/versions/`:

1. **`fb61c3c89ec7_..._baseline...py`** — un *no-op* (no ejecuta ningún DDL).
   Representa "este es el punto donde empezamos a versionar". Se aplica con
   `alembic stamp head`, que le dice a Alembic "la BD ya está en esta
   revisión" sin tocar nada.
2. **`a1c4f9d2b6e0_agregar_pais_id_a_dim_indicador.py`** — la migración real
   que agrega `pais_id` a `Config.DIM_Indicador` siguiendo la secuencia segura:
   columna NULL → backfill → NOT NULL → FK.

## Aplicar (un solo paso, una sola vez)

Desde `backend/`, en tu máquina:

```powershell
cd C:\Users\Lenovo\Proyecto\MSM\backend

# 1. Marca la BD en el baseline SIN ejecutar DDL (las tablas ya existen)
python -m alembic stamp fb61c3c89ec7

# 2. Antes de continuar: abre a1c4f9d2b6e0_agregar_pais_id_a_dim_indicador.py
#    y revisa/ajusta DEFAULT_PAIS_ID al id real de Config.DIM_Pais que deben
#    usar los indicadores existentes.

# 3. Aplica la migración real (esta sí agrega la columna)
python -m alembic upgrade head
```

Verifica con `python -m alembic current` que quedó en `a1c4f9d2b6e0 (head)`,
y vuelve a probar `POST /api/v1/dims/importar` — debería responder 200.

Si necesitas regenerar el baseline desde cero por algún motivo, **no uses
directamente** el resultado de `--autogenerate` sobre una BD existente sin
`alembic_version`: siempre revísalo primero (ver advertencia arriba).

## Flujo de trabajo a futuro

Cada vez que cambies un modelo (agregar columna, tabla, índice, FK, etc.):

1. Modifica el modelo en `app/models/`.
2. Genera la migración:
   ```powershell
   python -m alembic revision --autogenerate -m "descripción corta del cambio"
   ```
3. **Revisa el archivo generado** en `alembic/versions/` — corrige nombres,
   agrega backfills si hace falta, ajusta `nullable`/defaults para no romper filas existentes.
4. Aplica:
   ```powershell
   python -m alembic upgrade head
   ```
5. Commitea el modelo Y el archivo de migración juntos en el mismo PR/commit.

## Plantilla para agregar una columna NOT NULL con FK sin romper datos existentes

```python
def upgrade():
    op.add_column('DIM_Indicador', sa.Column('pais_id', sa.Integer(), nullable=True), schema='Config')
    op.execute("UPDATE [Config].[DIM_Indicador] SET pais_id = 1 WHERE pais_id IS NULL")
    op.alter_column('DIM_Indicador', 'pais_id', nullable=False, schema='Config')
    op.create_foreign_key(
        'FK_Indicador_Pais', 'DIM_Indicador', 'DIM_Pais',
        ['pais_id'], ['id'], source_schema='Config', referencing_schema='Config'
    )

def downgrade():
    op.drop_constraint('FK_Indicador_Pais', 'DIM_Indicador', schema='Config', type_='foreignkey')
    op.drop_column('DIM_Indicador', 'pais_id', schema='Config')
```

## Comandos útiles

| Comando | Qué hace |
|---|---|
| `alembic current` | Muestra la revisión aplicada actualmente en la BD |
| `alembic history` | Lista todas las migraciones |
| `alembic upgrade head` | Aplica todas las migraciones pendientes |
| `alembic downgrade -1` | Revierte la última migración |
| `alembic check` | (Alembic ≥ 1.9) Compara modelos vs. BD y avisa si hay drift sin generar nada |

## Recomendación adicional

Considera correr `alembic check` como parte de tu chequeo de salud al iniciar
el servidor en desarrollo, o en CI, para detectar drift entre modelos y BD
**antes** de que cause un error 500 en producción como el de `pais_id`.
