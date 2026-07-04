# Fase 1 — Motor de cálculo a Python + core agnóstico de BD — Diseño

**Fecha:** 2026-07-04 · **Preparado para:** Moisés · **Confidencial**
**Estado:** Aprobado (brainstorming) — pendiente de plan de implementación.

---

## 1. Resumen y contexto

Objetivo estratégico: ofrecer el sistema en **dos ediciones** que comparten la misma
lógica — **PostgreSQL** (clientes grandes) y **SQL Server en contenedor** (clientes
pequeños) — cada una en su propio repositorio. El prerequisito para ambas es
**eliminar toda dependencia del dialecto de base de datos**, que hoy vive en
**5 stored procedures T-SQL**.

**Esta Fase 1** (en el repo actual, verificada contra SQL Server) mueve esos 5 SPs a
**Python puro** y hace el core **agnóstico de BD**. Fases posteriores: 2 = fork a
PostgreSQL; 3 = stacks de despliegue (TLS/backups) por edición.

**Decisiones confirmadas:** los **5 SPs** en esta fase; **migración que los elimina**
(downgrade los recrea); verificación por **caracterización** (SP == Python, números
idénticos).

---

## 2. Estado actual (fuente de verdad: `sys.sql_modules` de la BD viva)

Cinco stored procedures:

| SP | Tamaño | Rol |
|----|--------|-----|
| `DW.sp_RecalcularCiclo` | 1.149 ch | Orquestador Score/Ranking |
| `DW.sp_CompletarPuntajesCiclo` | 2.147 ch | Completa puntajes de `FACT_ResultadoIndicador` |
| `DW.sp_GenerarRankingCiclo` | 3.357 ch | Score integral + ranking RM |
| `cat.sp_CalcularCategoriaMedica` | 11.997 ch | ETL dimensional + categorización médica |
| `cat.sp_CalcularCoberturaPredictiva` | 18.911 ch | Cálculo de cobertura predictiva |

Invocados vía `EXEC` desde: `recalculo_service.py` (DW), `categorizacion_service.py`
(`cat.sp_CalcularCategoriaMedica`), `cobertura_predictiva_service.py`
(`cat.sp_CalcularCoberturaPredictiva`). El resto del código es SQLAlchemy portable.

Otro SQL crudo atado a SQL Server (auditoría de portabilidad, §6): `/admin/reset`
(`NOCHECK`, `[corchetes]`, `pymssql` directo), índices filtrados en migraciones,
`GETUTCDATE()`, `NVARCHAR`.

---

## 3. Motor Score/Ranking (`DW.*`) — lógica capturada

### 3.1 `recalcular_ciclo_py(db, ciclo_id, pais_codigo=None) -> dict`
1. Buscar el ciclo. Si no existe → `ValueError`.
2. Si `cerrado` → `{ciclo_id, abortado: True, motivo, filas_kpi_actualizadas: 0, rankings_generados: 0}`.
3. Si abierto → `completar_puntajes(...)` (→ n_kpi) y `generar_ranking(...)` (→ n_rank).
4. `{ciclo_id, abortado: False, motivo: None, filas_kpi_actualizadas: n_kpi, rankings_generados: n_rank}`.

### 3.2 `completar_puntajes(db, ciclo_id, pais_codigo=None) -> int`
Por cada `DW.FACT_ResultadoIndicador` con `activo=1`, `resultado_real` no nulo, del
ciclo (y país si se indica), uniendo `Config.DIM_Indicador`:
- `valor_pct = resultado_real*100 si DIM_Indicador.escala == 1, si no resultado_real`.
- `cumplimiento_pct = clamp(valor_pct, 0, 100)` → `resultado_porcentaje`.
- `puntos_obtenidos = (cumplimiento_pct/100) * DIM_Indicador.ponderacion_pct`.
- `fecha_calculo = ahora (UTC)`.

Segundo paso, uniendo `Config.DIM_MetaIndicador` (`activo=1`) por `indicador_id`:
- `factor_aplicado = meta.peso`; `puntos_maximos = meta.puntaje_maximo`.
- `porcentaje_logro`: si `meta_100` no nulo y ≠0 → `clamp((resultado_real/meta_100)*100, ≤100)`;
  si `meta_100==0` → 0; si no, con `objetivo` igual criterio; si `objetivo==0` → 0; si no,
  se deja el valor previo.

Devuelve el número de filas actualizadas (equivalente a `@filas_actualizadas`).

### 3.3 `generar_ranking(db, ciclo_id, pais_codigo=None) -> int`
- Si no hay filas con `puntos_obtenidos` → retorna 0.
- Por RM (group by `rm_id, pais_codigo`): `score_total = SUM(puntos_obtenidos)*100 /
  SUM(ponderacion_pct)`, `clamp(0,100)` a `DECIMAL(10,4)`. Join `DIM_RM` para `linea_id`,
  `gerente_id`.
- `categoria_id`: primer `DIM_CategoriaDesempeno` activo con `score_min ≤ score ≤ score_max`
  (orden por `id ASC`, `TOP 1`).
- `posicion_global = ROW_NUMBER over (score DESC, rm_id ASC)`;
  `posicion_linea = ROW_NUMBER partition by linea_id (score DESC, rm_id ASC)`.
- Capturar `posicion_anterior` del `FACT_RankingRM` existente (`tipo_ranking='MENSUAL'`).
- **Delete-then-insert** de `FACT_ScoreIntegralRM` y `FACT_RankingRM` (MENSUAL) del ciclo/país.
- `elegible/elegible_reconocimiento = score >= 90`.
- Devuelve nº de filas de ranking insertadas.

**Aritmética:** usar `decimal.Decimal` con las precisiones del SP (`DECIMAL(18,6)` en sumas,
`DECIMAL(10,4)` en score) y el mismo redondeo, para igualdad exacta con el SP.

**Módulo:** `app/services/motor_calculo_service.py`. `recalculo_service.recalcular_ciclo`
deja de hacer `EXEC DW.sp_RecalcularCiclo` y llama a `motor_calculo_service.recalcular_ciclo_py`
(mismo dict de retorno; RBAC/logging/auditoría intactos).

---

## 4. Motores `cat.*` — categorización y cobertura

Son **ETL dimensional + cálculo** sobre el star schema `cat.*` (+ staging `stg.*`):

- **`cat.sp_CalcularCategoriaMedica(@LoadBatchKey)`**: conforma dimensiones
  (`cat.DimEspecialidad`, `DimGeografia`, `DimCentroMedico`, `DimMedico`,
  `DimRepresentanteMedico`) desde `stg.MedicoCategoriaInput`, aplica
  `cat.DimReglaCategoriaMedica`/`DimComponenteCategoria` y escribe
  `cat.FactMedicoCategoriaSnapshot`/`FactMedicoCategoriaDetalle`.
- **`cat.sp_CalcularCoberturaPredictiva(@CodigoCiclo, @CodigoPais, @FechaCorte, @RepresentanteKey, @Linea)`**:
  cálculo de cobertura predictiva por ciclo/país/representante/línea.

**Enfoque:** replicar cada SP como función Python dentro de su servicio
(`categorizacion_service.py`, `cobertura_predictiva_service.py`), leyendo el T-SQL
vigente **paso a paso** durante la implementación (se captura en el plan, no aquí, por
volumen — 12k/19k chars). El **harness de caracterización (§5) garantiza la equivalencia**
independientemente de los detalles internos: mismos snapshots de salida = correcto.

---

## 5. Verificación por caracterización (el corazón de la fase)

Antes de dropear cada SP:
1. **Semilla** de datos representativos por (ciclo, país) — reutilizar seeds existentes
   o crear fixtures deterministas.
2. **Correr el SP actual**, capturar un *golden snapshot* de las tablas de salida
   (`FACT_ResultadoIndicador` completado, `FACT_ScoreIntegralRM`, `FACT_RankingRM`,
   `cat.FactMedicoCategoria*`, salida de cobertura) — filas ordenadas y normalizadas.
3. **Correr el motor Python** sobre el mismo estado inicial.
4. **Assert de igualdad exacta** (todas las columnas relevantes: score, puntos,
   posiciones, categoría, elegible, snapshots). Diferencia = fallo.

Más **tests unitarios** de casos límite calculados a mano: clamp <0 y >100, empates
(desempate por `rm_id`), ciclo cerrado (abortado), `meta_100` vs `objetivo` vs sin meta,
score exactamente 90 (elegible), país nulo (todos) vs país filtrado, reglas de categoría
en los bordes de rango.

Los tests de caracterización viven en `backend/tests/` y corren contra la BD SQL Server
local (marcados para poder saltarse sin BD).

---

## 6. Auditoría de portabilidad (core agnóstico de BD)

Revisar y neutralizar el SQL crudo atado a SQL Server, para que el mismo código corra
en PostgreSQL y SQL Server:

- **`/admin/reset`** (`admin.py`): usa `pymssql` directo + `NOCHECK` + `[corchetes]`.
  Reescribir a SQLAlchemy neutral, o ramificar por `settings.DB_ENGINE` (`mssql`/`postgres`)
  con la sintaxis correspondiente (`ALTER TABLE ... DISABLE TRIGGER ALL` / FKs por dialecto).
- **`GETUTCDATE()` / `NVARCHAR` / `SYSUTCDATETIME()`** en SQL crudo → tipos/func neutrales
  (los modelos ya usan `datetime.now(timezone.utc)`).
- **Índices filtrados** en migraciones (`... WHERE ...`) → índices parciales (portables; PG
  y SQL Server los soportan con la misma sintaxis Alembic `postgresql_where`/`mssql_where`).
- **Identificadores mixtos** (`DIM_RM`, `FactVisita`): SQLAlchemy los entrecomilla solo,
  pero el SQL crudo debe usar comillas correctas por dialecto (o evitarse).
- Añadir `DB_ENGINE` a `config.py` (deriva del `DATABASE_URL`) para las (pocas) ramas
  de dialecto que queden.

No se cambia el comportamiento; solo se elimina el amarre a un motor.

---

## 7. Migración final (drop de los 5 SPs)

Una migración Alembic al final de la fase que **dropea** los 5 SPs (`DROP PROCEDURE IF
EXISTS`), con `downgrade` que los **recrea** desde su definición vigente (por seguridad/rollback).
Solo se aplica tras pasar toda la caracterización. Python queda como única fuente de verdad.

---

## 8. Alcance y pruebas

- **Módulos nuevos/modificados:** `motor_calculo_service.py` (nuevo);
  `recalculo_service.py`, `categorizacion_service.py`, `cobertura_predictiva_service.py`,
  `admin.py`, `config.py` (modificados); 1 migración (drop SPs).
- **Tests:** caracterización (SP vs Python, por SP) + unitarios de casos límite. Meta:
  la suite completa (`pytest`) en verde y la equivalencia demostrada.
- **Orden interno (reduce riesgo):** 1a motor DW → 1b Categorización → 1c Cobertura →
  1d auditoría de portabilidad + migración drop.

## 9. Fuera de alcance (Fase 1)

- Fork a PostgreSQL y baseline de migraciones PG (Fase 2).
- Stacks de despliegue Docker por edición, TLS, backups (Fase 3).
- Cambios funcionales: el resultado de negocio debe ser **idéntico** al actual
  (la caracterización lo garantiza).
