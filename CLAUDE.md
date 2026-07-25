# MSM — Documentación Completa para IA

**Sistema MIP de Productividad y Reconocimiento Comercial Farmacéutico**
Versión: 2.0 | Fecha: junio 2026 | Ruta: `C:\Users\Lenovo\Proyecto\MSM\`

---

## 1. Visión General del Sistema

MSM (Sistema MIP) es una aplicación web empresarial multipaís para medir, gestionar y reconocer el desempeño de la fuerza de ventas farmacéutica: **Representantes Médicos (RM)** y **Gerentes de Distrito (GD)**. Opera en múltiples países con configuración por país.

El sistema permite:
- Importar catálogos maestros desde Excel (hojas DIM_* en un solo archivo, router `/dims`)
- Cargar datos de desempeño KPI desde archivos Excel (ETL)
- Calcular el **Score Integral (IUP)** por RM/ciclo
- Generar rankings de RM y de Gerentes de Distrito (mensuales, trimestrales, anuales, regionales)
- Otorgar reconocimientos (Oro, Plata, Bronce)
- Evaluar Receptividad/Compromiso de los RM bajo el modelo **LSII** (Liderazgo Situacional II)
- Medir cobertura médica con metodología **4DX** (lead measures) en vez de solo ventas históricas
- Categorizar médicos (A/B/C/D) mediante un motor de criterios ponderados
- Exportar reportes (Excel/PDF) de ranking y reconocimientos
- Monitorear KPIs en dashboards especializados
- Auditar todas las acciones del sistema

**REDISEÑO DE JUNIO 2026 — cambios estructurales clave respecto a la v1.0:**

1. **El motor de cálculo de Score Integral/Ranking:** vive en `motor_calculo_service.py` (**100% Python**, edición PostgreSQL). Ver §8.
2. **El esquema `DW` fue rediseñado.** `FACT_RendimientoComercial`, `FACT_Ranking` y `FACT_Reconocimiento` (v1.0) fueron reemplazados por `FACT_ResultadoIndicador` (entrada), `FACT_ScoreIntegralRM` + `FACT_RankingRM` + `FACT_RankingGerente` + `FACT_ReconocimientoRM` (salidas calculadas), más tablas derivadas nuevas para dashboards (ver §4).
3. **Cuatro módulos nuevos**: **LSII** (§12), **Cobertura Predictiva / 4DX** (§13, sustituye a Comercial), **Categorización Médica** (§14, sustituye a Capacitación) y **Exportación/Reportes** (§15, resuelve el pendiente histórico de exportación PDF/Excel).
4. **Dos routers y dos páginas frontend quedaron como código muerto, intencionalmente no registrados**: `comercial.py` / `Comercial.tsx` y `capacitacion.py` / `Capacitacion.tsx`. Siguen en el disco (con comentarios inline que documentan la sustitución) pero no se importan en `router.py` ni en `App.tsx`. No tocarlos salvo que se pida explícitamente reactivarlos.

---

## 2. Stack Tecnológico

### Backend
- **Lenguaje**: Python 3.13
- **Framework**: FastAPI 0.115.5
- **ORM**: SQLAlchemy 2.0.36 (sintaxis moderna `Mapped` + `mapped_column`)
- **Migraciones**: Alembic (configurado con `include_schemas=True` — crítico)
- **Base de datos**: PostgreSQL 14+ (psycopg2), IP `127.0.0.1`, puerto TCP 5432
- **Validación/Config**: Pydantic v2 + pydantic-settings v2
- **Auth**: JWT con python-jose 3.3.0 + passlib[bcrypt] 1.7.4
- **ETL**: pandas 2.2.3 + openpyxl 3.1.5
- **Scheduler**: APScheduler 3.10.4
- **Reportes**: ReportLab 4.2.5 (certificados PDF) + exportación in-memory para Excel/PDF tabular (§15)
- **Logs**: loguru 0.7.2
- **Server**: uvicorn con reload en desarrollo

### Frontend
- **Framework**: React 18 + TypeScript + Vite
- **UI**: Material UI (MUI) v6
- **Estado global**: Zustand v5
- **Data fetching**: TanStack React Query v5
- **Forms**: react-hook-form + zod
- **Charts**: recharts
- **HTTP**: axios
- **Router**: react-router-dom v6

### Infraestructura
- Desarrollo — Backend: `http://localhost:8000` | Frontend: `http://localhost:3000` | Swagger: `http://localhost:8000/api/v1/docs`
- Producción — `https://vista-mip.com` (Docker en Linux: frontend nginx + backend uvicorn + PostgreSQL; ver `DEPLOY-POSTGRES.md`)
- Base de datos: PostgreSQL, BD `scgcpr`, usuario `segura`

---

## 3. Estructura de Carpetas

```
C:\Users\Lenovo\Proyecto\MSM\
├── DIMS_FACTS_V2/                        ← Archivos Excel de datos y referencia
│   ├── DIM_MIP_FINAL.xlsx                ← Catálogos maestros (multi-hoja)
│   ├── FACT_MIP_FINAL.xlsx               ← Datos de hechos para carga ETL
│   ├── MIP_Dashboard_Ejecutivo.html      ← Prototipo HTML del dashboard
│   └── Requerimiento_Sistema_MIP.txt     ← Documento de requerimientos
├── backend/
│   ├── .env
│   ├── requirements.txt
│   ├── alembic.ini
│   ├── MIGRATIONS.md
│   ├── alembic/
│   │   ├── env.py                        ← include_schemas=True (NO QUITAR)
│   │   └── versions/                     ← ~20 migraciones versionadas (ver §19)
│   ├── app/
│   │   ├── main.py
│   │   ├── api/v1/
│   │   │   ├── router.py                 ← Registra todos los sub-routers
│   │   │   └── routers/
│   │   │       ├── auth.py
│   │   │       ├── admin.py              ← catálogos + Categorías/Criterios Médicos (CRUD)
│   │   │       ├── dims.py                ← importación masiva multi-hoja
│   │   │       ├── productividad.py
│   │   │       ├── cobertura_predictiva.py  ← NUEVO, sustituye a comercial.py
│   │   │       ├── coaching.py
│   │   │       ├── categorizacion.py        ← NUEVO, sustituye a capacitacion.py
│   │   │       ├── ranking.py
│   │   │       ├── reconocimiento.py
│   │   │       ├── dashboard.py
│   │   │       ├── etl.py                  ← incluye /etl/recalcular/{ciclo_id}
│   │   │       ├── exportacion.py          ← NUEVO
│   │   │       ├── lsii.py                 ← NUEVO
│   │   │       ├── comercial.py            ← CÓDIGO MUERTO, NO registrado en router.py
│   │   │       └── capacitacion.py         ← CÓDIGO MUERTO, NO registrado en router.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   ├── deps.py                   ← RBAC dependencies
│   │   │   ├── audit_middleware.py
│   │   │   ├── token_store.py
│   │   │   ├── pagination.py
│   │   │   └── logging.py
│   │   ├── db/database.py
│   │   ├── models/
│   │   │   ├── dimensiones.py            ← DIM_* (esquema Config) — incl. dims nuevas LSII/4DX/Categorización
│   │   │   ├── hechos.py                 ← FACT_* (esquemas DW/ETL/Audit) — rediseño jun-2026
│   │   │   └── usuario.py                ← DIM_Usuario, enum Rol (esquema Security) — ahora con gerente_id
│   │   ├── schemas/
│   │   │   ├── schemas.py
│   │   │   └── common.py
│   │   └── services/
│   │       ├── iup_service.py              ← Motor de Score Integral (Python, lectura)
│   │       ├── puntaje_service.py          ← Conversión valor→puntos (utilidad Python puntual)
│   │       ├── ranking_service.py
│   │       ├── recalculo_service.py        ← Orquestador — delega el cálculo al motor Python (§8)
│   │       ├── etl_service.py
│   │       ├── elegibilidad_service.py
│   │       ├── reconocimiento_service.py
│   │       ├── cobertura_predictiva_service.py  ← NUEVO — motor Motor_Formulas (4DX)
│   │       ├── categorizacion_service.py        ← NUEVO — motor 100% Python (no usa SPs)
│   │       ├── exportacion_service.py           ← NUEVO
│   │       ├── lsii_service.py                  ← NUEVO
│   │       ├── notification_service.py          ← cableado a ranking/reconocimiento/examen + correcciones (ver §22)
│   │       ├── examen_consolidacion_service.py   ← gate EVAL_CONOCIMIENTOS por (ciclo,país) — ver §22 (Exámenes v2.0)
│   │       └── scheduler.py (en app/core/)       ← APScheduler: correo de correcciones a fecha_limite+30min
├── frontend/
│   ├── package.json
│   ├── vite.config.ts
│   └── src/
│       ├── App.tsx                        ← define todas las rutas (ver lista abajo)
│       ├── services/
│       │   ├── api.ts
│       │   └── auth.service.ts
│       ├── store/auth.store.ts
│       ├── types/index.ts
│       └── pages/
│           ├── auth/Login.tsx
│           ├── dashboard/DashboardEjecutivo.tsx
│           ├── productividad/Productividad.tsx
│           ├── cobertura-predictiva/CoberturaPredictiva.tsx   ← reemplaza a Comercial.tsx
│           ├── coaching/Coaching.tsx
│           ├── categorizacion/
│           │   ├── Categorizacion.tsx                          ← reemplaza a Capacitacion.tsx
│           │   └── CategorizacionAdmin.tsx                     ← carga Excel + mantenimiento (tab de Admin.tsx)
│           ├── ranking/Ranking.tsx
│           ├── reconocimiento/Reconocimiento.tsx
│           ├── lsii/
│           │   ├── Lsii.tsx                                    ← vista evaluador (matriz D1-D4)
│           │   └── LsiiAdmin.tsx                                ← mantenimiento catálogo (tab de Admin.tsx)
│           ├── etl/ETL.tsx
│           ├── admin/
│           │   ├── Admin.tsx                                   ← mega-componente con tabs de mantenimiento
│           │   ├── Usuarios.tsx
│           │   ├── ImportDims.tsx
│           │   └── CoberturaPredictivaAdmin.tsx                 ← tab de Admin.tsx
│           ├── reportes/Reportes.tsx                            ← consume exportacion.py
│           ├── comercial/Comercial.tsx                          ← CÓDIGO MUERTO, sin ruta en App.tsx
│           └── capacitacion/Capacitacion.tsx                    ← CÓDIGO MUERTO, sin ruta en App.tsx
└── docker-compose.yml, DEPLOY-POSTGRES.md ← despliegue Docker en Linux (ver §20)
```

**Rutas registradas en `App.tsx`** (confirmado leyendo el archivo): `/login`, `/dashboard`, `/productividad`, `/cobertura-predictiva`, `/coaching`, `/categorizacion`, `/ranking`, `/reconocimiento`, `/lsii`, `/etl` (ADMIN, GERENTE_PRODUCTIVIDAD), `/admin` (ADMIN, GERENTE_PRODUCTIVIDAD), `/usuarios` (ADMIN), `/reportes`, `/sin-acceso`. No existen rutas `/comercial` ni `/capacitacion` — cualquier ruta desconocida redirige a `/dashboard`.

---

## 4. Base de Datos — Esquemas y Tablas

PostgreSQL, base de datos `scgcpr`, múltiples esquemas.

### Esquema `Config` — Dimensiones (catálogos maestros)

**Catálogos generales (conservados de v1.0):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_Pais` | `Pais` | Países |
| `DIM_Linea` | `Linea` | Líneas de productos por país |
| `DIM_Gerente` | `Gerente` | Gerentes de Distrito/Marca/Regional (`tipo` distingue el rol) |
| `DIM_RM` | `RepresentanteMedico` | Representantes Médicos |
| `DIM_Indicador` | `Indicador` | Indicadores por país (`UNIQUE(pais_id, codigo)`) |
| `DIM_IndicadorTabla` | `IndicadorTabla` | Rangos valor→puntos por indicador+país |
| `DIM_Ciclo` | `Ciclo` | Biciclos de trabajo (`cerrado` = snapshot inmutable, ver §8) |
| `DIM_Mes` | `Mes` | Catálogo de meses |
| `DIM_Premio` | `Premio` | Tipos de premios/reconocimientos |
| `DIM_Capacitacion` | `CapacitacionDim` | Catálogo legacy de cursos — sin CRUD propio activo; sustituido funcionalmente por Categorización Médica |
| `DIM_ReglaElegibilidad` | `ReglaElegibilidad` | Umbrales mínimos para ranking/premios |

**Dashboard (metadata, nuevas):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_MetaIndicador` | `MetaIndicador` | Metas configurables para tarjetas de dashboard |
| `DIM_CategoriaDesempeno` | `CategoriaDesempeno` | Umbrales de clasificación de desempeño (distribución de equipo) |
| `DIM_KpiDashboard` | `KpiDashboard` | Definición de KPIs que se muestran en los dashboards |

**LSII (nuevas — ver §12):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_ReceptividadOpcion` | `ReceptividadOpcion` | Catálogo de dimensiones/opciones de Receptividad-Compromiso. Incluye `score_oculto` (1-5) y `peso_dimension`, **nunca expuestos al evaluador (GD)** |
| `DIM_ConfiguracionLSII` | `ConfiguracionLSII` | Fila única global: `corte_desempeno`, `corte_receptividad` (umbral D1-D4) |

**Cobertura Predictiva / 4DX (nuevas — ver §13):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_TargetMedico` | `TargetMedico` | Universo de médicos programados por RM/ciclo |
| `DIM_Feriado` | `Feriado` | Feriados por país (cálculo de días hábiles / NETWORKDAYS) |
| `DIM_ParametroCobertura` | `ParametroCobertura` | Metas de cobertura, resolución en cascada país+línea+ciclo → país+línea → país |

**Categorización Médica (nuevas — ver §14):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_Especialidad` | `Especialidad` | Especialidades médicas |
| `DIM_Provincia` | `Provincia` | Provincias por país |
| `DIM_Municipio` | `Municipio` | Municipios por provincia |
| `DIM_CentroMedico` | `CentroMedico` | Centros/instituciones médicas |
| `DIM_CategoriaMedica` | `CategoriaMedica` | Categorías resultantes A/B/C/D |
| `DIM_CriterioCategoria` | `CriterioCategoria` | Catálogo de los 5 criterios. ⚠️ **Ningún cálculo lo usa** — el motor real vive en `cat.*` (ver aviso en §14) |
| `DIM_CriterioCategoriaTabla` | `CriterioCategoriaTabla` | Rangos/niveles por criterio (análogo a `DIM_IndicadorTabla`) |
| `DIM_Medico` | `Medico` | Médicos, deduplicados por `(pais_id, nombre)` — el Excel fuente no trae código estable |

**Nota (corregida jul-2026, hallazgo de auditoría)**: los valores REALES de `DIM_Indicador.modulo` en los datos importados son `GESTION` y `RESULTADOS` (confirmado directamente en `DIMS_FACTS_V2/KPI GESTION/DIM_MIP_FINAL.xlsx`) — `productividad.py` siempre filtró correctamente por `GESTION`. `iup_service.py` filtraba por `PRODUCTIVIDAD` (un valor que nunca existió en los datos reales): ese componente del Score Integral daba **0 para todo representante** hasta el fix de jul-2026, que hizo que `_get_puntaje_productividad` y `_obtener_pesos` usen/remapeen `GESTION`. Ver §7 para el alcance real de este motor.

### Esquema `DW` — Tablas de Hechos (REDISEÑADO jun-2026)

**Entrada de KPIs:**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_ResultadoIndicador` | `ResultadoIndicador` | **Sustituye a `FACT_RendimientoComercial` (v1.0).** KPI por RM/indicador/ciclo: `rm_id`, `indicador_id`, `ciclo_id`, `pais_id`, `valor_real`, `resultado_porcentaje`, `puntos_obtenidos`, `activo` |

**Conservadas de v1.0 (alimentan el componente COMERCIAL del Score, fuera de `FACT_ResultadoIndicador`):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_Ventas` | `Ventas` | Ventas vs cuota mensual: `ventas_reales`, `cuota`, `cumplimiento_pct`, `crecimiento_pct`, `puntaje` |
| `FACT_EVOIR` | `EvoIR` | Evolución prescripciones IR: `prescripciones_actuales`, `prescripciones_anteriores`, `evolucion_pct`, `puntaje` |
| `FACT_Coaching` | `Coaching` | Acompañamientos gerenciales: `coaching_programado`, `coaching_ejecutado`, `calificacion_calidad`, `puntaje` |
| `FACT_Capacitacion` | `CapacitacionFact` | Legacy — participación en cursos (tabla conservada; el flujo activo de "categorización" es independiente, ver abajo) |

**Cobertura Predictiva / 4DX (nueva):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_Visita` | `Visita` | Bitácora cruda de visitas (rm/médico/fecha/ciclo). Fuente de L=`COUNT(DISTINCT medico_codigo)` y M=`COUNT(*)` del Motor_Formulas |

**Categorización Médica (nueva):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_CategorizacionMedica` | `CategorizacionMedica` | Resultado por médico/criterio/ciclo del motor de categorización (100% Python) |

**Salidas calculadas — sustituyen a `FACT_Ranking` y `FACT_Reconocimiento` (v1.0):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_ScoreIntegralRM` | `ScoreIntegralRM` | Score consolidado por RM/ciclo: `score_total` + componentes por módulo. Es la fuente de "historial" para el componente de Consistencia (ver §7) |
| `FACT_RankingRM` | `RankingRM` | Ranking de RM: `posicion`, `posicion_anterior`, `elegible`, `tipo_ranking` |
| `FACT_RankingGerente` | `RankingGerente` | Ranking de Gerentes de Distrito, consolidado por el equipo de RMs (resuelve el pendiente histórico "Ranking Gerentes de Distrito") |
| `FACT_ReconocimientoRM` | `ReconocimientoRM` | Premios otorgados: `iup_al_momento`, `posicion_ranking`, `certificado_generado` |

**Derivadas para dashboards (nuevas):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_ScorecardIndicador` | `ScorecardIndicador` | Agregado por indicador |
| `FACT_DistribucionEquipo` | `DistribucionEquipo` | Distribución de RMs por umbral de score (90/80/60) por gerente/equipo |
| `FACT_DashboardEjecutivo` | `DashboardEjecutivoFact` | Snapshot consolidado del dashboard ejecutivo |
| `FACT_TendenciaCiclo` | `TendenciaCiclo` | Serie histórica por ciclo (gráficos de tendencia) |

**LSII (nueva):**

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_EvaluacionReceptividad` | `EvaluacionReceptividad` | Cabecera de evaluación: `rm_id`, `gerente_id`, `ciclo_id`, `score_desempeno`, `score_receptividad`, `nivel_lsii`, `estilo_liderazgo`, `fecha_evaluacion` |
| `FACT_EvaluacionReceptividadDetalle` | `EvaluacionReceptividadDetalle` | Detalle por dimensión, con **snapshot** de `score_oculto`/`peso_dimension` al momento de evaluar (para que cambios futuros al catálogo no alteren evaluaciones históricas) |

### Esquema `ETL`

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_CargaExcel` | `CargaExcel` | Control de trabajos ETL (PENDIENTE/PROCESANDO/EXITOSO/ERROR) |
| `FACT_KPI_RAW` | `KpiRaw` | **Nueva** — staging table: filas crudas de `KPI_RM` antes de validarse/normalizarse hacia `FACT_ResultadoIndicador` |

### Esquema `Audit`

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `FACT_Auditoria` | `Auditoria` | Log de todas las acciones (LOGIN, CREATE, UPDATE, DELETE, ETL, RANKING) |

### Esquema `Security`

| Tabla | Clase ORM | Descripción |
|-------|-----------|-------------|
| `DIM_Usuario` | `Usuario` | Usuarios del sistema. **Nuevo en esta versión**: columna `gerente_id` (FK a `Config.DIM_Gerente`) — permite que un usuario con rol `GERENTE_DISTRITO` se autorresuelva a su propio equipo en los endpoints con auto-filtro de scope (ver §13, §17) |

---

## 5. Modelos ORM

**Sintaxis**: SQLAlchemy 2.0 moderno con `Mapped[tipo]` y `mapped_column()`. **Nunca** `Column()` antiguo.
**Base declarativa**: definida en `app/db/database.py`.

```python
class RepresentanteMedico(Base):
    __tablename__ = "DIM_RM"
    __table_args__ = {"schema": "Config"}

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    pais_id: Mapped[int] = mapped_column(Integer, ForeignKey("Config.DIM_Pais.id"), nullable=False)
    gerente: Mapped["Gerente"] = relationship("Gerente", back_populates="rms")
```

**Relaciones definidas**: `Gerente.rms` ↔ `RepresentanteMedico.gerente`; `Indicador.tablas` ↔ `IndicadorTabla.indicador`; `CriterioCategoria.tabla` ↔ `CriterioCategoriaTabla.criterio`; `ReceptividadOpcion` cuelga de una dimensión LSII (estructura catálogo→opciones igual que `Indicador`→`IndicadorTabla`).

`hechos.py` incluye un docstring de cabecera extenso que documenta explícitamente el mapeo v1.0→v2.0 (qué tabla vieja fue reemplazada por cuál nueva y por qué) — consultarlo ahí para el detalle de diseño, no solo este documento.

---

## 6. Indicadores de Desempeño

Los indicadores son configurables por país (`DIM_Indicador`, `UNIQUE(pais_id, codigo)`).

| Código | Nombre | Período | Ponderación típica |
|--------|--------|---------|-------------------|
| `COB_MD_F2` | Cobertura Médicos Frecuencia 2 | CICLO | 15% |
| `COB_MD_F1` | Cobertura Médicos Frecuencia 1 | CICLO | 15% |
| `PROM_DIARIO` | Promedio Diario de Visitas | CICLO | 10% |
| `COB_FARMACIAS` | Cobertura de Farmacias | CICLO | 5% |
| `EVAL_CONOCIMIENTOS` | Evaluación de Conocimientos | MES | 10% |
| `EVAL_COACHING` | Evaluación de Coaching | MES | 15% |
| `EVO_IR` | Evolución de Prescripciones IR | MES | 20% |
| `VENTAS` | Ventas vs. Cuota | MES | 15% |

**Escala del indicador** (campo `DIM_Indicador.escala`, según el docstring vigente de `puntaje_service.py`):
- `1` → el valor ya viene como porcentaje (0-100), se usa directo
- `100` → el valor ya viene como score directo (0-100), se usa directo

Nota: a diferencia de v1.0, `puntaje_service.convertir_a_puntaje()` ya **no** recibe ni aplica la normalización por escala — recibe el valor ya normalizado y solo busca el rango en `DIM_IndicadorTabla`. La normalización por escala (si aplica `×100` u otra transformación) ahora ocurre en `motor_calculo_service.completar_puntajes` (Python) durante el recálculo masivo (ver §8). `puntaje_service.py` queda como utilidad para cálculos puntuales fuera de ese flujo.

**Pesos del Score** (campo `DIM_Indicador.peso_iup`): fracción decimal (ej. `0.15` = 15%). La suma por módulo da el peso del módulo en el Score total — ver §7.

---

## 7. Motor de Score Integral (antes "Motor IUP")

> ⚠️ **ALCANCE REAL DE ESTA FÓRMULA (verificado jul-2026, auditoría pre-lanzamiento).**
> Este motor de 5 componentes (`iup_service.py`) **NO es el que calcula el Ranking Mensual
> automático** (el que corre tras cada ETL / `POST /etl/recalcular/{ciclo_id}` y alimenta
> Reconocimiento por defecto). Ese lo calcula `motor_calculo_service.generar_ranking` (§8)
> con una fórmula mucho más simple: `SUM(puntos_obtenidos) × 100 / SUM(ponderacion_pct)`
> sobre `FACT_ResultadoIndicador` únicamente — **sin** Comercial/Coaching/Capacitación/
> Consistencia. Esto no es un bug de la migración a Python: un test de caracterización ya
> retirado (`test_caracterizacion_motor.py`, comparaba contra el SP real de SQL Server byte
> a byte) confirmó que el stored procedure original **ya usaba esta misma fórmula simple**.
> El motor de 5 componentes de esta sección **sí corre**, vía `ranking_service.py`, cuando
> se dispara `POST /ranking/generar` (botón manual, usado para tipos TRIMESTRAL/ANUAL/
> REGIONAL). Si se necesita que el Ranking Mensual automático también use los 5
> componentes, es un cambio de diseño explícito — no asumir que ya está así.

**Archivo**: `app/services/iup_service.py`

```
Score = Σ (puntaje_módulo × peso_módulo)
Score ∈ [0, 100]
```

**REDISEÑO**: la fuente de productividad pasó de `FACT_RendimientoComercial.puntaje` (v1.0) a `FACT_ResultadoIndicador.puntos_obtenidos`. El nombre "IUP" se conserva como métrica interna (claves `iup_productividad`, `iup_comercial`, etc., por compatibilidad con `ranking_service`/`elegibilidad_service`/dashboards), pero la salida consolidada se persiste en `FACT_ScoreIntegralRM.score_total`, no en `FACT_Ranking.iup_total`.

**Módulos y pesos por defecto** (usados solo si `DIM_Indicador` no tiene `peso_iup` configurado):
- PRODUCTIVIDAD: 30%
- COMERCIAL: 30%
- COACHING: 15%
- CAPACITACION: 10%
- CONSISTENCIA: 15%

**Función principal**: `calcular_iup(db, rm_id, pais_id, ciclo_id) → dict` — retorna `iup_productividad`, `iup_comercial`, `iup_coaching`, `iup_capacitacion`, `iup_consistencia`, `iup_total`, `score_total`, `pesos_aplicados`.

**Cómo se calcula cada componente:**
- **Productividad**: promedio de `FACT_ResultadoIndicador.puntos_obtenidos` para indicadores con `modulo == "GESTION"` (fix jul-2026 — antes filtraba por `"PRODUCTIVIDAD"`, un valor que nunca existió en los datos reales; el componente siempre daba 0). `_obtener_pesos` remapea la clave `GESTION`→`PRODUCTIVIDAD` para que un `peso_iup` configurado sí se aplique.
- **Comercial** (FIX W-02): promedio de `FACT_Ventas.puntaje` y `FACT_EVOIR.puntaje`, **solo de los componentes que tengan datos cargados en el ciclo** — si falta uno, no penaliza al RM; si no hay ninguno, el componente es 0.
- **Coaching** / **Capacitación**: promedio simple de `FACT_Coaching.puntaje` / `FACT_Capacitacion.puntaje` del ciclo.
- **Consistencia** (FIX W-08, implementa el pendiente histórico "IUP consistencia completo" — **ya resuelto**): promedio de `FACT_ScoreIntegralRM.score_total` de hasta los **3 ciclos previos más recientes** del RM (ordenados por `DIM_Ciclo.anio/numero` descendente, excluyendo el ciclo actual). Si tiene 1-2 ciclos previos, usa los disponibles. Si no tiene historial (RM nuevo), usa **0** como base neutral — nunca 50 — para no darle ventaja artificial sobre RMs con trayectoria.

**Reglas generales**:
- Los pesos se leen dinámicamente desde `DIM_Indicador.peso_iup` agrupado por módulo (FIX C-02, sin constantes hardcodeadas).
- Si no hay pesos configurados → usa los pesos por defecto.
- Los pesos se normalizan para que sumen 1.0; `CONSISTENCIA` siempre tiene su clave garantizada (no es un módulo de indicadores).
- El score final se acota a `[0, 100]`.

---

## 8. Servicio de Recálculo — en Python (motor agnóstico de BD)

**Archivo**: `app/services/recalculo_service.py` (orquestación) + `app/services/motor_calculo_service.py` (motor).

**El motor de Score/Ranking es 100% Python** (`motor_calculo_service.py`), con
`decimal.Decimal` para aritmética exacta. **No hay stored procedures en la BD**: el
cálculo de puntajes, score integral y ranking vive en Python, igual que
Categorización (`categorizacion_service.calcular_categorias_py`) y Cobertura
(`cobertura_predictiva_service.calcular_cobertura_py`).

- `motor_calculo_service.completar_puntajes(db, ciclo_id, pais_codigo)` — `resultado_porcentaje` + `puntos_obtenidos`.
- `motor_calculo_service.generar_ranking(db, ciclo_id, pais_codigo)` — Score Integral + Ranking **MENSUAL** (**delete-then-insert**). Fórmula: `SUM(FACT_ResultadoIndicador.puntos_obtenidos) × 100 / SUM(Indicador.ponderacion_pct)` — **no** es el motor de 5 componentes de §7 (confirmado idéntico al SP original de SQL Server vía caracterización, no es una simplificación introducida por la migración a Python).
- `motor_calculo_service.recalcular_ciclo_py(db, ciclo_id, pais_codigo)` — orquestador (guard de ciclo abierto).

`recalculo_service.recalcular_ciclo` delega en `motor_calculo_service.recalcular_ciclo_py`, conservando
idéntico el contrato de dict (`{ciclo_id, abortado, motivo?, filas_kpi_actualizadas, rankings_generados}`).

```python
def recalcular_ciclo(db, ciclo_id, pais_codigo=None) -> dict:
    from app.services import motor_calculo_service
    return motor_calculo_service.recalcular_ciclo_py(db, ciclo_id, pais_codigo)
```

**REGLA DE NEGOCIO CRÍTICA**: el recálculo **solo opera sobre el ciclo ABIERTO** de cada país (`DIM_Ciclo.cerrado == False`). Los ciclos cerrados son snapshots históricos inmutables — el motor nunca los toca, ni siquiera si llegan datos nuevos o correcciones. `validar_ciclo_abierto(db, ciclo_id)` es el guard central, reutilizado por `ranking_service` y `reconocimiento_service` para garantizar que ningún camino de cálculo pueda escribir sobre un ciclo cerrado; levanta `CicloCerradoError` si el ciclo está cerrado.

**Disparadores**: automáticamente al final de un ETL en modo `PRODUCCION`, o manualmente vía `POST /etl/recalcular/{ciclo_id}` (pantalla "Calcular IUP y Ranking").

**Respuesta**: `{ciclo_id, abortado, motivo?, filas_kpi_actualizadas, rankings_generados}` — si `abortado=true` (ciclo cerrado), no se escribió nada.

**Migraciones del motor**: las migraciones de la etapa SP (`e7a91f4c2b58`, `b8c4d2e1f5a9`, `e2f5b9c4a1d8`, `2c771e676bd7`, `e8f1a2c3d4b5`) pertenecían a la edición SQL Server y **no existen en este repo** (single-head desde `0001_baseline_postgres`, verificado jul-2026); el cálculo actual es 100% Python y no depende de ellas.

---

## 9. Motor de Puntaje (Python)

**Archivo**: `app/services/puntaje_service.py` — utilidad de conversión usada fuera del flujo masivo de recálculo (que vive en `motor_calculo_service`, 100% Python, ver §8).

- `convertir_a_puntaje(db, indicador_id, valor, pais_id) → Decimal`: busca el rango `[rango_desde, rango_hasta]` (inclusive) en `DIM_IndicadorTabla` filtrando por indicador **y** país. Sin tabla configurada → devuelve el valor acotado a `[0,100]` (pass-through). Valor sobre el rango máximo → puntos máximos de la tabla. Valor bajo el mínimo → 0 puntos.
- `convertir_puntaje_por_codigo(db, indicador_codigo, valor, pais_id)`: variante por código (útil en ETL, donde se tiene el código del Excel, no el ID).
- `calcular_puntaje_coaching(cumplimiento_pct, calificacion_calidad, peso_cantidad=0.7, peso_calidad=0.3)`: `resultado = 0.7×cumplimiento% + 0.3×calidad`, acotado a `[0,100]`.
- `calcular_cumplimiento(valor_real, valor_meta)`: acotado a `[0,100]`, evita división por cero.

---

## 10. Motor ETL

**Archivo**: `app/services/etl_service.py` + router `app/api/v1/routers/etl.py`

**Tipos de archivo soportados** (`tipo_archivo`, validados en el endpoint): `KPI_RM` (preferido — un solo archivo con `pais_codigo`+`ciclo_id` por fila, alimenta `FACT_ResultadoIndicador` vía `ETL.FACT_KPI_RAW`), y los legacy `PRODUCTIVIDAD`, `COMERCIAL`, `COACHING`, `CAPACITACION` (siguen aceptados por el validador del endpoint aunque sus routers REST `comercial.py`/`capacitacion.py` ya no estén registrados — alimentan directamente `FACT_Ventas`/`FACT_EVOIR`/`FACT_Coaching`/`FACT_Capacitacion` vía `etl_service`, sin pasar por esos routers).

**Seguridad de archivos** (sin cambios respecto a v1.0):
- FIX C-06: nombre de archivo seguro con UUID (`_safe_filename`) — previene Path Traversal.
- FIX W-06: valida magic bytes (`PK\x03\x04` para .xlsx, `\xd0\xcf\x11\xe0` para .xls) antes de guardar.
- FIX W-01: `datetime.now(timezone.utc)`, nunca `utcnow()`.

**Flujo**: `POST /etl/cargar` (sube archivo, valida extensión+magic bytes+tamaño máximo, registra job en `FACT_CargaExcel` con estado `PENDIENTE`, lanza `procesar_excel_task` en `BackgroundTasks` con sesión propia) → Leer → Validar estructura → Validar integridad referencial → Enriquecer → Cargar → (si modo `PRODUCCION`) Recalcular (ver §8).

**Modos**: `SIMULACION` (valida sin escribir) y `PRODUCCION` (escribe y dispara recálculo).

**Endpoints confirmados**: `POST /etl/cargar`, `GET /etl/status/{job_id}`, `POST /etl/recalcular/{ciclo_id}` (NUEVO — disparo manual), `GET /etl/historial`.

---

## 11. Router de Importación de DIMs

**Archivo**: `app/api/v1/routers/dims.py` — sin cambios respecto a v1.0.

Permite cargar todos los catálogos maestros desde un solo archivo Excel multi-hoja.

**Hojas reconocidas** (nombre exacto en MAYÚSCULAS), en orden de carga: `DIM_PAIS` (1) → `DIM_LINEA` (2) → `DIM_GERENTE` (3) → `DIM_RM` (4) → `DIM_INDICADOR` (5) → `DIM_INDICADOR_TABLA` (6) → `DIM_CICLO` (7) → `DIM_MES` (8).

**Endpoints**: `POST /dims/preview` (detecta hojas + columnas, no escribe) y `POST /dims/importar` (importa hojas seleccionadas). Registros existentes se omiten (no duplica); retorna `insertados + omitidos + errores` por hoja.

---

## 12. Módulo LSII (Liderazgo Situacional II)

**Archivos**: `app/api/v1/routers/lsii.py`, `app/services/lsii_service.py`. Router: `prefix="/lsii"`.

Implementa el modelo de Liderazgo Situacional II (Hersey-Blanchard): cruza un eje **Desempeño** con un eje **Receptividad/Compromiso** para ubicar a cada RM en un cuadrante D1-D4 y sugerir el estilo de liderazgo del GD hacia él.

**Regla de ocultamiento (la más importante del módulo)**: `DIM_ReceptividadOpcion` tiene `score_oculto` (1-5) y `peso_dimension`. Estos campos **nunca se exponen al evaluador (GD)**:
- `GET /lsii/catalogo` (vista del evaluador, `RequireEvaluador` = ADMIN, GERENTE_PRODUCTIVIDAD, GERENTE_DISTRITO, GERENTE_MARCA) responde con `ReceptividadDimensionPublic` — sin los campos ocultos.
- Solo los endpoints bajo `/lsii/admin/*` (`RequireAdminLsii` = ADMIN, GERENTE_PRODUCTIVIDAD) devuelven `score_oculto`/`peso_dimension`.

**Endpoints** (verificados leyendo `lsii.py` línea por línea):

| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| GET | `/lsii/catalogo` | RequireEvaluador | Catálogo de dimensiones/opciones (sin puntos ocultos) |
| POST | `/lsii/evaluar` | RequireEvaluador | Registra evaluación y devuelve el cruce LSII |
| GET | `/lsii/matriz` | Autenticado | Puntos del scatter (última evaluación por RM en el ciclo); RM ve solo la suya |
| GET | `/lsii/rm/{rm_id}` | Autenticado | Histórico de evaluaciones de un RM |
| GET | `/lsii/admin/dimensiones` | RequireAdminLsii | Catálogo completo, incluye puntos ocultos y pesos |
| POST | `/lsii/admin/dimensiones` | RequireAdminLsii | Crear/actualizar una dimensión completa |
| DELETE | `/lsii/admin/dimensiones/{codigo}` | RequireAdminLsii | Soft-delete de una dimensión |
| PATCH | `/lsii/admin/opciones/{opcion_id}` | RequireAdminLsii | Editar puntualmente una opción |
| GET | `/lsii/admin/configuracion` | RequireAdminLsii | Umbral de corte D1-D4 vigente |
| PUT | `/lsii/admin/configuracion` | RequireAdminLsii | Actualizar umbral de corte D1-D4 |

`FACT_EvaluacionReceptividad`/`Detalle` guardan un **snapshot** de `score_oculto`/`peso_dimension` al momento de evaluar — cambios posteriores al catálogo no alteran evaluaciones históricas.

**Frontend**: `Lsii.tsx` — matriz scatter D1-D4 (eje Desempeño invertido: D1 arriba-izquierda, D4 abajo-derecha; marcadores con iniciales en círculo y descripciones de cuadrante en las esquinas), KPI cards, panel "Resumen por Cuadrante", donut "Distribución por Nivel LSII" y barras "Distribución de Colaboradores" (ambos en orden D1→D4 con esquema de color consistente), tabla "Detalle por Colaborador" con barras de progreso y recomendación. + `LsiiAdmin.tsx` (tab de mantenimiento dentro de `Admin.tsx`).

---

## 13. Módulo Cobertura Predictiva (4DX)

**Archivos**: `app/api/v1/routers/cobertura_predictiva.py`, `app/services/cobertura_predictiva_service.py`. Router: `prefix="/cobertura-predictiva"`.

**Sustituye** a `/comercial` y a `GET /dashboard/comercial` (ambos retirados — `comercial.py` permanece en disco, no registrado). Cambia el enfoque de **lag measure** (ventas/EVO IR históricos) a **lead measure** (ritmo de cobertura/visitas), siguiendo la metodología 4DX.

**FLUJO ACTIVO — EN VIVO desde el módulo Visita (jul-2026):** el dashboard que consume el frontend
NO depende de Excel. Se calcula en tiempo real desde las tablas operativas del módulo Visita, vía
endpoints `GET /cobertura-predictiva/vivo/{ciclos,dashboard,categorias}`:
- **Programado (J)** = Vistas planeadas en `Visita.PlaneacionCiclo` (Planeación del Ciclo).
- **Realizado (L/M)** = visitas ejecutadas en `Visita.FactVisita` (Registrar Visita). L=`COUNT(DISTINCT medico)` entre los planeados, M=`COUNT(*)`.
- **Días hábiles (N)** = `Ciclo.dias_laborables` (config del ciclo); solo si es 0 cae a NETWORKDAYS sobre `DIM_Feriado`.
- **Cobertura** = `L / J` (médicos planeados visitados / total planeados). Meta en cascada `país+línea+ciclo → país+línea → país` (`DIM_ParametroCobertura`, default 90%).

**LEGACY (importación por Excel) — retirado de la UI:** existían endpoints `cargar/target-medicos`,
`cargar/visitas`, `feriados` y `cat/cargar-excel` (llenaban `DIM_TargetMedico`/`DW.FACT_Visita`/`DIM_Feriado`).
Siguen en el router pero **`CoberturaPredictivaAdmin.tsx` ya no los expone** — solo queda la Meta de
Cobertura. Los feriados no se gestionan aquí porque los días hábiles ya vienen del ciclo (`dias_laborables`).

**Endpoints** (activos): `GET /cobertura-predictiva/vivo/ciclos|dashboard|categorias`,
`GET /cobertura-predictiva/resumen` y `/rm/{rm_id}`, `GET/POST /cobertura-predictiva/parametros` (Meta).
Los `cargar/*` y `feriados` quedan como legacy no expuestos en la UI.

**RBAC con auto-filtro de scope** (patrón repetido también en Categorización, §14): `REPRESENTANTE_MEDICO` se filtra forzosamente a su propio `rm_id` (403 si no coincide o falta); `GERENTE_DISTRITO` se filtra a su propio `gerente_id` (vía `Usuario.gerente_id`, ver §4/§17).

**Frontend**: `CoberturaPredictiva.tsx` (vista operativa en vivo; selector de ciclo por defecto en el abierto, buscador de representante por nombre) + `CoberturaPredictivaAdmin.tsx` (tab de Admin: **solo la Meta de Cobertura**).

---

## 14. Módulo Categorización Médica

**Archivos**: `app/api/v1/routers/categorizacion.py`, `app/services/categorizacion_service.py`. Router: `prefix="/categorizacion"`.

**Sustituye** a Capacitación (`capacitacion.py` permanece en disco, no registrado). A diferencia del motor IUP/Ranking, **el motor de cálculo es 100% Python — explícitamente no usa stored procedures**.

**5 criterios ponderados**:

| Criterio | Peso |
|----------|------|
| Pacientes/Semana | 30% |
| Poder Adquisitivo | 20% |
| Potencial de Prescripción | 10% |
| Ubicación Territorial | 30% |
| KOL (Key Opinion Leader) | 10% |

Resultado: categoría **A/B/C/D** por médico/ciclo (`DIM_CategoriaMedica` + `FACT_CategorizacionMedica`).

> ⚠️ **DÓNDE VIVE REALMENTE EL MOTOR (verificado jul-2026).** Pese a lo que sugieren su
> nombre y su CRUD en Admin, **`Config.DIM_CriterioCategoria` / `DIM_CriterioCategoriaTabla`
> NO los usa ningún cálculo**: son un catálogo paralelo sin consumidores. El motor real
> puntúa con el esquema **`cat.*`**:
> - `cat.DimComponenteCategoria` — los 5 componentes (`Requerido` marca los que exige el cálculo).
> - `cat.DimReglaCategoriaMedica` — reglas por país: rango numérico o `ValorTexto`, cada una
>   con su aporte `PuntajePct`.
> - `cat.DimClasificacionMedica` — bandas `PuntajeMinPct..PuntajeMaxPct` → Clase A/B/C/D.
>
> **La fórmula es una SUMA directa de `PuntajePct`**, no un promedio ponderado: cada regla ya
> trae su aporte. Y **pese al sufijo `Pct`, la escala es una FRACCIÓN 0–1** (0.30 = 30%); el
> tope suma 1.00 con los pesos 30/20/10/30/10. Las bandas usan la misma escala (DO:
> A=0.86–1.00, B=0.66–0.85, C=0.46–0.65, D=0.00–0.45). Para mostrar al usuario: ×100.
>
> **Cada criterio tiene vocabulario CERRADO y no intuitivo** — p. ej. Potencial de
> Prescripción es `"1" / "2 a 3" / "4 a 6" / "6 a 9" / "10 o Mas"`, y KOL es
> `"Ninguno" / "Profesor Universitario" / … / "Presidente de Sociedad, Charlista"` (**no** es
> un sí/no). Cualquier formulario debe usar desplegables servidos por
> `GET /categorizacion/plantilla`: un valor escrito a mano no matchea ninguna regla y el
> médico queda **sin clasificar**.
>
> **Solo DO tiene reglas cargadas** (27 reglas + 4 bandas). CR/GT/HN/PA/VE están vacíos:
> ahí no se puede clasificar. Diagnóstico: `scripts/diagnostico_config_categorizacion.py`.

Reutiliza `DIM_Gerente` (`tipo=DISTRITO`) y `DIM_RM` en lugar de crear dimensiones nuevas "Distrito"/"Representante". `DIM_Medico` se deduplica por `(pais_id, nombre)` porque el Excel fuente no trae un código de médico estable.

**Endpoints principales** (verificados):

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/categorizacion` | Listado paginado de categorizaciones |
| GET | `/categorizacion/resumen` | Dashboard ejecutivo de categorización |
| GET | `/categorizacion/medicos` | Listado paginado de médicos |
| GET | `/categorizacion/medicos/{id}/historial` | Evolución de categoría ciclo a ciclo |
| POST | `/categorizacion/calcular` | Captura + cálculo de 1 médico/ciclo |
| POST | `/categorizacion/recalcular` | Cálculo masivo de un ciclo |
| POST | `/categorizacion/simular` | Simulador — cálculo sin persistencia |
| POST | `/categorizacion/cargar` | Carga masiva desde Excel (mismo patrón Stepper/FormData que `ETL.tsx`) |

Mantenimiento de catálogos (`DIM_CategoriaMedica`, `DIM_CriterioCategoria` + `DIM_CriterioCategoriaTabla`) vía `/admin/categorias-medicas` y `/admin/criterios-categoria` (+ `/tabla`) en `admin.py` — mismo patrón CRUD que Indicadores/Indicadores-Tabla.

**Frontend**: `Categorizacion.tsx` (vista operativa) + `CategorizacionAdmin.tsx` (carga Excel + mantenimiento, tab de `Admin.tsx`).

---

## 14b. Módulo Maestro de Médicos (jul-2026)

**Archivos**: `app/api/v1/routers/maestro_medicos.py` (`prefix="/medicos"`), `app/services/maestro_medico_service.py`. Frontend: `pages/medicos/Medicos.tsx` (contenedor con **dos subpestañas**: Categorización | Maestro de Médicos) + `pages/medicos/MaestroMedicos.tsx` + `services/maestroMedicos.service.ts`. Ruta `/medicos`, ítem de menú "Médicos" (sustituye "Categorización Médica"; `/categorizacion` se conserva por compatibilidad).

**Idea central**: `Config.DIM_Medico` promovido a **Maestro país-level** — fuente única del dato *general* del médico. Tres planos separados: **Maestro** (identidad + datos generales) · **Categorización** (esquema `cat.*`, snapshot A/B/C/D por período, intacto) · **Asignación** (`Visita.DIM_MedicoVisita`, panel del rep, ahora con FK `maestro_medico_id`, migración `0013`).

**Modelo** (migración `0012`): `DIM_Medico` enriquecido con `telefono, direccion, sector, exequatur, observaciones, estado_validacion (APROBADO|PENDIENTE), origen (MANUAL|EXCEL|PANEL|…), created_at, updated_at`. Índice `IX_Medico_exequatur`.

**Dedup en cascada** (`maestro_medico_service.detectar_duplicados`): **DURA** (bloquea, `DuplicadoDuroError`) = exequátur **o** cédula ya existentes; **BLANDA** (advierte, `PosibleDuplicadoError` salvo `confirmar_duplicado`) = mismo nombre normalizado (acentos incluidos, compara en Python) **y** mismo centro/provincia — requiere al menos una dimensión de ubicación (evita falsos positivos por homónimos).

**Puente Panel↔Maestro** (`visita_service`): al **crear** un médico en el Panel se resuelve/crea su médico central (match duro → linkea; sin match → `crear_maestro(origen=PANEL, estado=PENDIENTE)`); al **editar**, solo los campos GENERALES (`_MAESTRO_SYNC`: nombre/código/especialidad/exequátur/teléfono/email/dirección/sector) se sincronizan al Maestro — los de asignación (frecuencia, zona…) no. Backfill idempotente: `scripts/backfill_maestro_medicos.py`.

**Endpoints** (`RequireEscritura` = ADMIN/GERENTE_PRODUCTIVIDAD para escritura; lectura = autenticado):

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/medicos/maestro` | Listado paginado + filtros (`q, especialidad_id, provincia_id, estado, activo`) |
| GET | `/medicos/maestro/kpis` | `{total, activos, nuevos_mes, sin_asignacion, pendientes_validacion}` |
| GET | `/medicos/maestro/preview` · `/importar` | Importación Excel: preview (no persiste) + upsert idempotente por llave dura |
| GET | `/medicos/maestro/exportar` | Exporta a Excel (in-memory, respeta filtros) |
| GET | `/medicos/maestro/{id}` · `/{id}/historial` | Ficha + historial de cambios (`Audit.FACT_Auditoria`, tabla=DIM_Medico) |
| POST | `/medicos/maestro` | Crear (409 `{tipo: duro/blando, coincidencias}` si dup) |
| PUT | `/medicos/maestro/{id}` | Actualizar |

> **No ciclo-dependiente**: el Maestro es país-level, el guard de ciclo abierto no aplica (sí a la asignación del Panel). El esquema `cat.*` no se toca.

---

## 14c. Alta de Médico con Clasificación y Aprobación (Bloque B, jul-2026)

Rediseño del alta de un médico en el Panel: el representante ya **no elige** la categoría —
captura los 5 criterios y la letra **la revela el sistema al aprobar el Gerente de Distrito**.

**Principio rector**: la categoría **no es elegible por nadie**. Ni el rep al capturar ni el GD
al revisar la ven o la eligen; ambos manipulan solo los valores crudos. Así la clasificación es
auditable (siempre recalculable desde los valores) y no negociable. Mismo criterio que el
`score_oculto` de LSII (§12): `GET /categorizacion/plantilla` **nunca devuelve los puntajes**,
porque conocerlos permitiría capturar apuntando a la categoría deseada.

**Flujo:**

1. **Alta (rep)** — `POST /visita/medicos` exige `clasificacion` (los 5 criterios; 422 si falta
   alguno). El médico queda `PENDIENTE_ALTA` y **sin categoría** (`categoria = NULL`). Los valores
   se guardan en `Visita.MedicoClasificacion` (staging 1:1, migración `0021`).
2. **Aviso** — correo al Gerente de Distrito del VM
   (`notification_service.notificar_medico_pendiente_aprobacion`, best-effort).
3. **Revisión (GD)** — `GET/PUT /visita/medicos/{id}/clasificacion`: ve la plantilla y **puede
   corregirla**. El PUT da 409 si el alta ya no está pendiente (tras aprobar, editarla a mano
   rompería la trazabilidad del cálculo).
4. **Aprobación** — `POST /visita/medicos/{id}/aprobar` dispara
   `visita_aprobacion_service._clasificar_al_aprobar`: el motor puntúa y **sella
   `MedicoVisita.categoria`**. Una BAJA no recalcula nada.
5. **Destino del dato** — la clasificación queda en el **Panel** (plano de asignación, por RM/línea);
   el **Maestro de Médicos (`DIM_Medico`) queda SIN clasificación** a propósito: un mismo médico
   puede tener categorías distintas según la línea que lo visita.

**Motor de un médico**: `categorizacion_service.calcular_categoria_de_valores(db, pais, valores)`,
con `_puntuar()` pura (testeable sin BD). Reutiliza los helpers `_regla_aplica`/`_mejor_regla` del
motor batch de Excel — **a propósito**: garantiza que un médico dé la MISMA categoría venga del
Excel o del Panel. Si falta regla de un componente requerido → `estado=PENDIENTE` y `categoria=None`:
**no se inventa una letra**, y la aprobación no se bloquea (el médico queda sin clasificar).

**Blindaje anti-duplicados (estricto)**: `maestro_medico_service.detectar_duplicados` bloquea
(`DuplicadoDuroError`) por **exequátur, cédula, O mismo nombre normalizado en el MISMO centro**.
Mismo nombre en la misma **provincia** pero en **otro centro** sigue siendo blando (advierte):
dos homónimos en centros distintos pueden ser médicos reales diferentes. **`confirmar_duplicado`
ya no puede saltarse la regla dura** — tampoco la importación por Excel, que reporta la fila con
el médico existente (`preview_excel` expone `bloqueados_duplicado` para verlo antes de importar).

**Cambios de esquema (migración `0021_medico_clasificacion`)**: `Visita.MedicoClasificacion`
(nueva) y `Visita.DIM_MedicoVisita.categoria` → **NULLABLE** (NULL = capturado, aún sin clasificar).
Escrita a mano: el autogenerate arrastraba ~40 renombrados de índices ajenos al cambio.

**Frontend**: `PanelMedico.tsx` — sección "Clasificación del médico (obligatoria)" en el alta
(campos **renderizados desde la plantilla del país**, no hardcodeados; Guardar bloqueado hasta
completarlos) y diálogo **"Revisar y aprobar"** para el GD. Al **editar** un médico la clasificación
no se muestra ni se envía (la ajusta el GD al aprobar).

---

## 14d. Módulo de Farmacias (jul-2026)

**Archivos**: `app/api/v1/routers/farmacias.py` (`prefix="/farmacias"`), `app/services/maestro_farmacia_service.py`,
`app/services/farmacia_aprobacion_service.py`, `app/services/visita_farmacia_service.py`,
`app/services/cobertura_farmacia_service.py`. Frontend: `pages/visita/PanelFarmacia.tsx` (VM),
`pages/farmacias/BandejaAprobacionFarmacias.tsx` (GD), `pages/admin/MaestroFarmacias.tsx` (CRUD directo),
`services/farmacias.service.ts`. Spec/plan: `docs/superpowers/specs/2026-07-22-modulo-farmacias-maestro-aprobacion-design.md`
+ `docs/superpowers/plans/2026-07-22-modulo-farmacias.md`.

**Idea central**: espejo del módulo de Médicos (§14b), con tres capas separadas:

| Capa | Tabla | Descripción |
|------|-------|-------------|
| **Maestro** (país-level) | `Config.DIM_Farmacia` | Identidad única de la farmacia. Estados `PENDIENTE_APROBACION \| ACTIVA \| RECHAZADA \| INACTIVA` |
| **Panel** (por VM) | `Visita.DIM_FarmaciaVisita` | Referencia al maestro (`maestro_farmacia_id`, F19) + estado de la solicitud del VM: `PENDIENTE_ALTA \| APROBADO \| RECHAZADO` |
| **Registro** (visita) | `Visita.FactVisitaFarmacia` | Bitácora de visitas. **Opción A**: tabla PARALELA a `Visita.FactVisita` (médicos) — cero regresión, nunca comparten fila ni discriminador |

**Flujo VM→GD (F21)** — `farmacia_aprobacion_service.py`, espejo de `visita_aprobacion_service`:
- **Acción A** (`solicitar_agregar_al_panel`): el VM agrega al panel una farmacia que YA existe y está
  `ACTIVA` en el maestro. Solo crea el panel en `PENDIENTE_ALTA`; el maestro no se toca.
- **Acción B** (`solicitar_crear`): el VM da de alta una farmacia nueva. Crea el maestro
  (`estado="PENDIENTE_APROBACION"`, `origen="VM"`) + el panel enlazado en `PENDIENTE_ALTA`.
- **Bandeja del GD** (`GET /farmacias/aprobacion/pendientes`, auto-scope a su distrito): **aprobar**
  (maestro → `ACTIVA` si seguía pendiente; panel → `APROBADO` con `ciclo_alta_id` = ciclo de trabajo del
  VM), **rechazar** (motivo obligatorio, F26 — maestro origen VM pendiente → `RECHAZADA` +
  `motivo_rechazo`; panel → `RECHAZADO`), o **editar y aprobar** (corrige el maestro —p.ej. dirección—
  y aprueba en el mismo paso).
- El alta directa en el maestro sin pasar por aprobación (`POST/PUT /farmacias/maestro`) es exclusiva de
  ADMIN/GERENTE_PRODUCTIVIDAD (`origen="CONFIG"`, `estado="ACTIVA"` de entrada).

**Campos bloqueantes (F23/F24)**: `direccion` y `encargado` son `NOT NULL` en el modelo **y** validados
con mensaje de negocio exacto en `maestro_farmacia_service.validar_bloqueantes` (cliente y servidor;
el 422 lleva el mensaje del servicio, no el genérico de Pydantic — los schemas de payload no llevan
`min_length` a propósito).

**Nomenclatura CADENA + SUCURSAL (F20)**: `nombre_completo` es **derivado**, nunca capturado a mano —
`cadena + " " + sucursal` (normalizado: NFKD sin acentos, mayúsculas, espacios colapsados) si
`es_cadena`, si no `nombre` normalizado. Se recalcula en cada `crear_maestro`/`actualizar_maestro` que
toque esos campos.

**Anti-duplicados (F25/F09)** — `maestro_farmacia_service.py`, dos niveles:
- **DURA** (`detectar_duplicados`, bloquea con `DuplicadoDuroError`): misma `(pais_codigo, cadena,
  sucursal)` normalizada entre farmacias activas y no rechazadas. Corre en `crear_maestro` (Acción B y
  alta directa). El formulario del VM solo se habilita tras una búsqueda sin resultado
  (`GET /farmacias/maestro/buscar`).
- **BLANDA** (`detectar_posibles_duplicados`, jul-2026, Tarea 9): coincidencia por **prefijo** del
  `nombre_completo` normalizado (en cualquier dirección, p.ej. `"GBC PANTOJA"` vs `"GBC PANTOJA 2"`)
  contra OTRA farmacia ya `ACTIVA` del maestro. **No bloquea** — es la alerta "Posible duplicado"
  visible en la bandeja del GD (`posible_duplicado` en `GET /farmacias/aprobacion/pendientes`, solo
  para altas `NUEVA`/Acción B; en Acción A la farmacia ya ES esa misma fila del maestro, no aplica).

**Regla F22 (bloqueante transversal)**: una farmacia en `PENDIENTE_APROBACION`/panel `PENDIENTE_ALTA`
**no cuenta para cobertura ni admite Registro de Visita**. Se aplica en dos guards independientes:
`visita_farmacia_service._guard_f22` (levanta `PanelNoAprobadoError` → 409) y el universo de
`cobertura_farmacia_service._universo_ids` (filtra directo por `estado_aprobacion="APROBADO"`).

**Registro de visita — AD-HOC, en el MISMO módulo de Visita, SIN planeación de ciclo**: a diferencia de
Médicos, **no existe** un equivalente de `PlaneacionCiclo` para farmacias — el VM registra cuando la
hace, sin universo planeado ni ruptura de secuencia programada. La UI vive en la misma pantalla
**Registrar Visita** (selector Médico/Farmacia), pero el backend escribe en la tabla paralela
`FactVisitaFarmacia` (Opción A). Reusa hora-servidor (`hace_minutos`, ventana), guard de ciclo abierto
(`recalculo_service.validar_ciclo_abierto`) y foto BLOB con magic bytes JPEG/PNG ≤ 3 MB
(`POST/GET /farmacias/{visita_id}/foto`), igual que `FactVisita` de médicos.

**Cobertura interna simple — COEXISTE con el SFA, no pisa el score**: `cobertura_farmacia_service.py`
calcula `visitadas / universo` sobre el panel `APROBADO`+activo del VM, **sin F1/F2** (a diferencia de
Médicos: solo visitada/no-visitada, decisión aprobada en el spec). Es puramente informativo/operativo —
**nunca** toca `motor_calculo_service`/`iup_service`: `COB_FARMACIAS` del Score/Ranking (§6-7) sigue
viniendo del SFA externo. `GET /farmacias/cobertura` (auto-scope VM/GD igual que el resto del módulo).

**Endpoints** (verificados en `farmacias.py`):

| Método | Ruta | Recurso RBAC | Descripción |
|--------|------|--------------|-------------|
| GET | `/farmacias/maestro/buscar` | `farmacia.panel` (read) | Búsqueda anti-dup (habilita el form si no hay resultado, F25) |
| POST | `/farmacias/panel/agregar` | `farmacia.panel` (register) | Acción A |
| POST | `/farmacias/panel/crear` | `farmacia.panel` (register) | Acción B (bloqueantes + anti-dup duro) |
| GET | `/farmacias/panel` | `farmacia.panel` (read) | Panel del VM — incluye `motivo` de rechazo (F26, jul-2026) |
| GET | `/farmacias/cobertura` | `farmacia.panel` (read) | Cobertura interna simple (Task 7) |
| POST | `/farmacias/{panel_id}/visita` | `farmacia.panel` (register) | Registro AD-HOC, guard F22 + ciclo abierto |
| POST/GET | `/farmacias/{visita_id}/foto` | `farmacia.panel` | Foto BLOB (magic bytes JPEG/PNG, ≤ 3 MB) |
| GET | `/farmacias/aprobacion/pendientes` | `farmacia.aprobar` (read) | Bandeja del GD — incluye `posible_duplicado` (§3.2, jul-2026) |
| POST | `/farmacias/aprobacion/{panel_id}/aprobar` `/rechazar` `/editar-aprobar` | `farmacia.aprobar` (approve) | Solo GERENTE_DISTRITO (su equipo) + ADMIN |
| GET/POST/PUT | `/farmacias/maestro` (+ `/{id}`) | `farmacia.maestro` (read/configure) | CRUD directo, solo GERENTE_PRODUCTIVIDAD + ADMIN |

**RBAC** (matriz, §25): 3 recursos — `farmacia.panel` (VM `register` propio; GD `read` de su equipo
`team`; el resto de gerencias `read all` salvo FINANZAS sin acceso; espejo de `medico.panel`),
`farmacia.aprobar` (SOLO GERENTE_DISTRITO `approve team` + ADMIN), `farmacia.maestro` (SOLO
GERENTE_PRODUCTIVIDAD `configure` + ADMIN, mismo patrón que `lsii.admin`/`etl.cargar`). **Nota
histórica**: la Fase 1 de RBAC (§25) había reservado especulativamente 3 filas
`farmacia.configuracion`/`farmacia.visita`/`farmacia.cobertura` con un diseño que NO coincidía con el
aprobado aquí; quedaron sin consumidor y se **retiraron** en la Tarea 9 (cierre del módulo,
`constantes.py`/`matrix.py`/`test_authz_matriz.py`, matriz 35→32 recursos).

**Reglas de negocio F19–F26** (spec §11):

| Regla | Resumen | Dónde |
|-------|---------|-------|
| F19 | Maestro único + panel referenciado | `DIM_Farmacia` + `DIM_FarmaciaVisita.maestro_farmacia_id` |
| F20 | Nombre visible CADENA+SUCURSAL | `nombre_completo` derivado |
| F21 | Alta/asignación con aprobación del GD | `farmacia_aprobacion_service` |
| F22 | PENDIENTE no cuenta cobertura ni admite registro | guards en `visita_farmacia_service`/`cobertura_farmacia_service` |
| F23 | Dirección bloqueante | NOT NULL + `validar_bloqueantes` |
| F24 | Encargado bloqueante | NOT NULL + `validar_bloqueantes` |
| F25 | Formulario solo tras búsqueda sin resultado | `detectar_duplicados` (dura) |
| F26 | Rechazo con motivo + histórico visible al VM | `motivo_rechazo` (maestro) / `motivo` (panel), expuesto en `GET /farmacias/panel` |

---

## 15. Módulo Exportación / Reportes

**Archivo**: `app/api/v1/routers/exportacion.py` (99 líneas). Router: `prefix="/exportacion"`. Resuelve el pendiente histórico de v1.0 "Exportación PDF/Excel de reportes".

Generación **en memoria** vía `BytesIO` + `StreamingResponse` — no se cachea en disco (a diferencia de los certificados PDF de `reconocimiento_service.py`, que sí persisten).

**RBAC**: `RequireReportes` restringido a roles con visión consolidada/gerencial (ADMIN, PRESIDENCIA, DIR_COMERCIAL, GERENTE_PRODUCTIVIDAD).

**Endpoints** (verificados vía grep):

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/exportacion/ranking/excel` | Exporta ranking a Excel (.xlsx) |
| GET | `/exportacion/ranking/pdf` | Exporta ranking a PDF (tabular) |
| GET | `/exportacion/reconocimientos/excel` | Exporta reconocimientos a Excel (.xlsx) |
| GET | `/exportacion/reconocimientos/pdf` | Exporta reconocimientos a PDF (tabular) |

**Frontend**: `Reportes.tsx`.

---

## 16. API Endpoints

Base URL: `http://localhost:8000/api/v1`

### Auth (`/auth`)
| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| POST | `/auth/login` | Público | Form-data `username`+`password` → `access_token` + `refresh_token` |
| POST | `/auth/logout` | Autenticado | Invalida el refresh_token |
| POST | `/auth/refresh` | Público | Renueva access_token |
| POST | `/auth/change-password` | Autenticado | Cambia la propia (valida la actual + política de complejidad) |
| POST | `/auth/forgot-password` | Público | "Olvidó su contraseña" — envía código al correo; respuesta SIEMPRE genérica |
| POST | `/auth/reset-password` | Público | Valida `{email, codigo, password_nuevo}` y fija la nueva |
| GET | `/auth/me` | Autenticado | Datos del usuario actual |

### Admin (`/admin`)
| Método | Ruta | Roles |
|--------|------|-------|
| GET/POST/PUT/DELETE | `/admin/paises` | ADMIN (+ lectura: GERENTE_PRODUCTIVIDAD/DISTRITO/MARCA) |
| GET/POST/PUT | `/admin/lineas` | ADMIN (+ lectura ampliada) |
| GET/POST/PUT | `/admin/gerentes` | ADMIN (+ lectura ampliada) |
| GET/POST/PUT | `/admin/rms` | ADMIN (+ lectura ampliada) |
| GET/POST/PUT/DELETE | `/admin/indicadores` (+ `/tabla`) | ADMIN (lectura: cualquier autenticado) |
| GET/POST/PUT/DELETE | `/admin/categorias-medicas` | ADMIN (lectura: cualquier autenticado) |
| GET/POST/PUT/DELETE | `/admin/criterios-categoria` (+ `/tabla`) | ADMIN (lectura: cualquier autenticado) |
| GET/POST | `/admin/ciclos` (`?abierto=true` filtra solo abiertos) | ADMIN (+ lectura ampliada) |
| GET | `/admin/ciclos/actual?pais_codigo=XX` | ADMIN (+ lectura) | Ciclo abierto más reciente por país |
| PATCH | `/admin/ciclos/{id}/cerrar` `/abrir` | ADMIN | Cierra o reabre un ciclo |
| POST | `/admin/reset` | ADMIN — borra datos por fase (`tipo=facts` o `tipo=dims`, ver nota abajo) |
| GET/POST/PUT/DELETE | `/admin/reglas-elegibilidad` | ADMIN/GERENTE_PRODUCTIVIDAD |
| GET/POST | `/admin/premios` | ADMIN/GERENTE_PRODUCTIVIDAD (alta: ADMIN) |
| GET/POST/PUT/DELETE | `/admin/usuarios` | ADMIN |
| POST | `/admin/usuarios/{id}/reset-password` | ADMIN — restablece la contraseña de cualquier usuario (fuerza cambio en próximo login) |

> `POST /admin/reset?tipo=facts|dims` (hallazgo nuevo, no documentado en v1.0): borrado administrativo en dos fases con `TRUNCATE ... RESTART IDENTITY CASCADE` (PostgreSQL). `facts` borra todo `DW`/`ETL`/`Audit` (sin riesgo de FK, las FACT apuntan hacia los DIM). `dims` borra `Config` — solo seguro después de `facts`; nulifica `pais_codigo` en usuarios antes de truncar. Operación destructiva, ADMIN únicamente — pensada para entornos de prueba/reset de demo, no usar contra datos de producción reales sin respaldo previo.

### DIMs — Importación masiva (`/dims`)
Ver §11. `POST /dims/preview`, `POST /dims/importar` — ADMIN, GERENTE_PRODUCTIVIDAD.

### ETL (`/etl`)
| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| POST | `/etl/cargar` | ADMIN, GERENTE_PRODUCTIVIDAD | Sube Excel, lanza procesamiento en background |
| GET | `/etl/status/{id}` | ADMIN, GERENTE_PRODUCTIVIDAD | Estado de un job |
| POST | `/etl/recalcular/{ciclo_id}` | ADMIN, GERENTE_PRODUCTIVIDAD | Dispara el recálculo (`motor_calculo_service`, Python) manualmente (ver §8) |
| GET | `/etl/historial` | ADMIN, GERENTE_PRODUCTIVIDAD | Historial de cargas |

### Productividad (`/productividad`)
GET `/productividad`, `/productividad/rm/{rm_id}`, `/productividad/pais/{id}`, `/productividad/resumen` — sin cambios respecto a v1.0.

### Cobertura Predictiva (`/cobertura-predictiva`) — ver §13

### Coaching (`/coaching`)
GET `/coaching`, `/coaching/resumen`.

### Categorización Médica (`/categorizacion`) — ver §14

### Ranking (`/ranking`)
| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| GET | `/ranking` | Autenticado | Ranking de RM (`?pais_id=&ciclo_id=&tipo=&top=`) |
| GET | `/ranking/regional` | Autenticado | Ranking multipaís |
| GET | `/ranking/anual` | Autenticado | Histórico anual |
| POST | `/ranking/generar` | ADMIN | Dispara cálculo en background |

> Nota: el ranking de Gerentes de Distrito ahora se persiste en `FACT_RankingGerente` (ver §4). Confirmar el endpoint exacto en `ranking.py` antes de invocarlo si no aparece arriba — esta tabla no fue releída línea por línea en la última verificación.

### Reconocimiento (`/reconocimiento`)
GET `/reconocimiento`, POST `/reconocimiento`.

### Exportación (`/exportacion`) — ver §15

### Dashboard (`/dashboard`)
| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| GET | `/dashboard/catalogos` | Autenticado | Catálogos para filtros del dashboard |
| GET | `/dashboard/ejecutivo` | ADMIN, PRESIDENCIA, DIR_COMERCIAL, GERENTE_PRODUCTIVIDAD | Score regional, Top/Bottom 5 RMs, Top gerentes, tendencia histórica, distribución por umbrales 90/80/60, componentes radar |
| GET | `/dashboard/productividad` | Autenticado | Cobertura F1/F2, farmacias, promedio diario |
| GET | `/dashboard/reconocimiento` | Autenticado | Elegibles, premiados, certificados |
| GET | `/dashboard/capacitacion` | Autenticado | Tasa aprobación, asistencia, horas (legacy) |

**`GET /dashboard/comercial` fue retirado** — sustituido por `GET /cobertura-predictiva/resumen` (§13).

### Sistema
GET `/health`.

---

## 17. Autenticación y RBAC

### JWT
- Access token: 60 min (`JWT_ACCESS_TOKEN_EXPIRE_MINUTES`)
- Refresh token: 7 días (`JWT_REFRESH_TOKEN_EXPIRE_DAYS`)
- Payload: `sub` (user_id), `rol`, `username`, `nombre_completo`
- Blacklist de refresh tokens persistida en la base de datos (`Security.FACT_TokenRevocado`, `token_store.py`) — consistente entre workers y duradera tras reinicio (FIX W-04 v2, ver §22)

### Roles y permisos
```
ADMIN                  → acceso total
PRESIDENCIA            → lectura total + dashboard ejecutivo
DIR_COMERCIAL          → lectura total (sin admin)
GERENTE_PRODUCTIVIDAD  → ETL + admin catálogos + importar DIMs + recalcular + LSII admin + Cobertura/Categorización admin
GERENTE_DISTRITO       → coaching + su equipo (auto-filtro por Usuario.gerente_id en Cobertura Predictiva y Categorización) + evaluador LSII
GERENTE_MARCA          → su línea propia + evaluador LSII
REPRESENTANTE_MEDICO   → solo ve sus propios datos (auto-filtro por rm_id en Productividad, Cobertura Predictiva, LSII)
CONSULTA               → solo lectura
```

### Dependencias RBAC (patrón en `deps.py` + constantes por router)
```python
RequireAdmin        = Depends(require_roles(Rol.ADMIN))
RequirePresidencia  = Depends(require_roles(Rol.ADMIN, Rol.PRESIDENCIA))
RequireDirComercial = Depends(require_roles(Rol.ADMIN, Rol.PRESIDENCIA, Rol.DIR_COMERCIAL))
RequireGerente      = Depends(require_roles(Rol.ADMIN, ...todos los GERENTE...))
RequireAnyAuth      = Depends(get_current_active_user)
```
Cada router nuevo (`lsii.py`, `cobertura_predictiva.py`, `categorizacion.py`, `exportacion.py`) define sus propias constantes locales siguiendo el mismo patrón (`RequireEvaluador`, `RequireAdminLsii`, `AdminOGerProd`, `RequireReportes`, `LecturaCatalogos` en `admin.py`).

**Auto-filtro de scope** (patrón nuevo, repetido en Cobertura Predictiva y Categorización): `REPRESENTANTE_MEDICO` se restringe a su propio `rm_id` (403 si falta o no coincide); `GERENTE_DISTRITO` se restringe a su propio `gerente_id`, resuelto vía la nueva columna `Security.DIM_Usuario.gerente_id`.

### Seguridad
- Bloqueo temporal de login tras **3 intentos fallidos** (30 minutos). El bloqueo solo afecta a
  `/auth/login`: la recuperación por correo/código (`/auth/forgot-password` → `/auth/reset-password`)
  funciona aunque la cuenta esté bloqueada y, al completarse con éxito, **desbloquea la cuenta**
  (limpia `intentos_fallidos`/`bloqueado_hasta`). El ADMIN también desbloquea al instante desde
  Administración de Usuarios (casilla "Bloqueado" → `PATCH /admin/usuarios/{id}/bloqueo`).
- `FACT_Auditoria` registra todos los logins y acciones POST/PUT/PATCH/DELETE
- Contraseña: mínimo 12 chars, mayúscula, minúscula, número **y carácter especial** (política real en `password_policy_service.validar_complejidad`); no reutilización de las últimas N (`FACT_PasswordHistorial`)
- Archivos ETL: validación de magic bytes + nombre UUID para prevenir Path Traversal

### Activación de cuenta por enlace (jul-2026) — **cómo nace un usuario**
Al crear un usuario **con correo** el sistema NO envía contraseña: manda un **enlace de
activación de un solo uso** y el usuario crea la suya. Una clave enviada por correo queda
archivada para siempre en el buzón y en cada servidor por el que pasó; el enlace caduca y
muere al usarse.

- **Modelo**: `Security.FACT_ActivacionCuenta` (token **SHA-256**, `expira_en`, `usado`,
  `usado_en`, `usado_ip`) + `Security.DIM_Usuario.activado_en` (migración `0023`).
  `activado_en` NULL = creada pero su titular nunca fijó su clave. **No confundir con
  `activo`**, que es el interruptor manual del ADMIN.
- **Por qué SHA-256 y no bcrypt** (a diferencia de `FACT_PasswordReset`): el usuario llega
  con el token y nada más, así que hay que buscar la fila POR el token; bcrypt usa un salt
  distinto por hash y obligaría a recorrer la tabla entera. Es seguro porque la entropía la
  pone `secrets.token_urlsafe(32)` (256 bits), no una persona.
- **Servicio**: `activacion_service.py` — `generar_token`, `enviar_activacion`, `validar`,
  `activar`, `reenviar_por_email`. Caducidad 24 h, configurable en `ACTIVACION_EXPIRA_HORAS`.
- **Endpoints públicos**: `GET /auth/activacion/{token}` (valida antes de pintar el formulario),
  `POST /auth/activacion {token,password}`, `POST /auth/activacion/reenviar {email}` (respuesta
  siempre genérica). ADMIN: `POST /admin/usuarios/{id}/reenviar-activacion` (409 si ya activó).
- **`POST /admin/usuarios` con `password` OPCIONAL**: vacío + con correo → enlace de activación
  (la cuenta nace con un hash aleatorio que nadie conoce); con contraseña → el ADMIN la entrega
  por otra vía y la cuenta nace ya activada. **Sin correo la contraseña es obligatoria** (422):
  no hay a dónde mandar el enlace.
- **Reglas que evitan callejones sin salida** (cubiertas por `tests/test_activacion_reglas.py`):
  el login **corta antes** de `verify_password` si `activado_en is None` (si no, la clave
  aleatoria fallaría siempre y a los 3 intentos la cuenta quedaría bloqueada); una contraseña
  débil **no consume** el token; y `password_reset_service.restablecer` también marca
  `activado_en` (probar la titularidad del correo equivale a activar, para quien perdió el enlace).
- **Frontend**: `pages/auth/ActivarCuenta.tsx`, ruta **pública** `/activar/:token` en `App.tsx`
  (va antes del catch-all y **no** se condiciona a `isAuthenticated` — quien llega del correo
  nunca lo está). En Usuarios: chip **"Sin activar"** (≠ Inactivo) y botón de reenvío.

### Gestión de contraseñas (jul-2026)
- **ADMIN restablece cualquier contraseña** desde Administración de Usuarios: `POST /admin/usuarios/{id}/reset-password` (valida complejidad, guarda hasheada, `debe_cambiar_password=True`). UI: campo + botón en el diálogo de editar usuario.
- **"Olvidó su contraseña"** (`password_reset_service.py` + modelo `Security.FACT_PasswordReset`, migración `0010`):
  - `POST /auth/forgot-password {email}` → respuesta **genérica** (nunca revela si el correo existe); si existe, genera **código de 6 dígitos guardado HASHEADO** (bcrypt), invalida los previos y lo envía por correo (`notification_service.notificar_codigo_recuperacion`).
  - `POST /auth/reset-password {email, codigo, password_nuevo}` → valida el código (**vigente, no usado, máx. 5 intentos, expira 15 min**), aplica la política de complejidad, guarda y **consume el código (no reutilizable)**.
  - Login: enlace "¿Olvidó su contraseña?" → diálogo de 2 pasos (correo → código + nueva contraseña).

---

## 18. Configuración (.env)

```env
APP_NAME=SCGCPR
APP_VERSION=1.0.0
APP_ENV=development
DEBUG=true
API_PREFIX=/api/v1

DB_SERVER=127.0.0.1        # host de PostgreSQL (o `db` con el compose with-db)
DB_PORT=5432               # PostgreSQL
DB_NAME=scgcpr
DB_USER=segura
DB_PASSWORD=<tu_password_db>   # nunca commitear el valor real (ver .env.example)

JWT_SECRET_KEY=scgcpr-dev-local-secret-2026-cambiar-produccion
JWT_ALGORITHM=HS256
JWT_ACCESS_TOKEN_EXPIRE_MINUTES=60
JWT_REFRESH_TOKEN_EXPIRE_DAYS=7

# CORS: puede ser JSON array o CSV
CORS_ORIGINS=["http://localhost:3000","http://localhost:5173"]

LOG_LEVEL=INFO
LOG_FILE=logs/scgcpr.log
```

En producción, `CORS_ORIGINS` debe incluir `https://vista-mip.com`. El `field_validator("CORS_ORIGINS", mode="before")` en `config.py` acepta tanto JSON array como string CSV (sin cambios respecto a v1.0).

---

## 19. Migraciones con Alembic

**Guía completa**: `backend/MIGRATIONS.md`. Hay aproximadamente 20 migraciones en `backend/alembic/versions/`. Migraciones confirmadas relevantes al rediseño (además de las 4 ya documentadas en v1.0 — baseline, `pais_id` en indicador, unique constraint, columnas faltantes):

- Las migraciones de la etapa de stored procedures (`e7a91f4c2b58`, `b8c4d2e1f5a9`, `e2f5b9c4a1d8`, `2c771e676bd7`) pertenecen a la edición SQL Server y **no existen en este repo** (verificado jul-2026: cadena single-head desde `0001_baseline_postgres`) — el motor actual es 100% Python (§8) y no las usa
- Migraciones adicionales asociadas a los modelos nuevos: `DIM_TargetMedico`/`DIM_Feriado`/`DIM_ParametroCobertura`/`FACT_Visita`/`Usuario.gerente_id` (Cobertura Predictiva) y las DIM/FACT de Categorización Médica (`DIM_Especialidad`, `DIM_Provincia`, `DIM_Municipio`, `DIM_CentroMedico`, `DIM_CategoriaMedica`, `DIM_CriterioCategoria`, `DIM_CriterioCategoriaTabla`, `DIM_Medico`, `FACT_CategorizacionMedica`)

### ⚠️ Regla crítica de Alembic
`env.py` tiene `include_schemas=True` en `context.configure()`. **No quitar esta opción.** Sin ella, Alembic solo reflexiona el esquema `public` y propone recrear todas las tablas de `Config.*`, `DW.*`, etc.

### Comandos útiles
```powershell
cd C:\Users\Lenovo\Proyecto\MSM\backend
python -m alembic current
python -m alembic upgrade head
python -m alembic revision --autogenerate -m "descripcion del cambio"
python -m alembic check
```

### Flujo para agregar una columna NOT NULL con FK (plantilla segura)
```python
def upgrade():
    op.add_column('DIM_Tabla', sa.Column('nueva_col', sa.Integer(), nullable=True), schema='Config')
    op.execute("UPDATE [Config].[DIM_Tabla] SET nueva_col = 1 WHERE nueva_col IS NULL")
    op.alter_column('DIM_Tabla', 'nueva_col', nullable=False, schema='Config')
    op.create_foreign_key('FK_nombre', 'DIM_Tabla', 'DIM_Otra', ['nueva_col'], ['id'],
                          source_schema='Config', referencing_schema='Config')
```

---

## 20. Cómo Correr el Proyecto

### Backend (desarrollo)
```powershell
cd C:\Users\Lenovo\Proyecto\MSM\backend
.\venv\Scripts\activate
pip install -r requirements.txt
pip install bcrypt==3.2.2   # Fix compatibilidad passlib 1.7.4 + bcrypt 4.x
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Frontend (desarrollo)
```powershell
cd C:\Users\Lenovo\Proyecto\MSM\frontend
npm install
npm run dev
```

### Producción
El sistema está desplegado en `https://vista-mip.com` con **Docker en Linux**: frontend (nginx sirviendo el build de Vite + proxy `/api/v1`) + backend (uvicorn/FastAPI + psycopg2) + PostgreSQL, orquestados por `docker-compose.yml`. Las migraciones Alembic corren solas al arrancar el contenedor del backend. Deploy: `git pull && docker compose --profile with-db up -d --build`. Ver **`DEPLOY-POSTGRES.md`** para el procedimiento completo.

### Crear tablas e inicializar (primera vez)
```bash
# Las migraciones Alembic construyen TODO el esquema (0001_baseline_postgres → head):
python -m alembic upgrade head
# Sembrar el usuario admin:
python scripts/setup/crear_admin_pg.py
```
> Con Docker es automático: el contenedor del backend corre `alembic upgrade head` al
> arrancar. El admin se siembra con `docker compose exec backend python scripts/setup/crear_admin_pg.py`.

### Credenciales por defecto
- **Usuario**: `admin` | **Contraseña**: `Admin1234!` | **Swagger**: `http://localhost:8000/api/v1/docs`

### Flujo de carga de datos inicial
1. `POST /dims/preview` → subir `DIM_MIP_FINAL.xlsx` → revisar hojas detectadas
2. `POST /dims/importar` → seleccionar todas las hojas → importar catálogos
3. `POST /etl/cargar` → subir `FACT_MIP_FINAL.xlsx` con `tipo_archivo=KPI_RM`, `modo=PRODUCCION`
4. El recálculo de Score/Ranking se dispara automáticamente (motor Python `motor_calculo_service`) o manualmente: `POST /etl/recalcular/{ciclo_id}`
5. Para Cobertura Predictiva: `POST /cobertura-predictiva/cargar/target-medicos` y `.../cargar/visitas`
6. Para Categorización Médica: `POST /categorizacion/cargar`

---

## 21. Problemas Conocidos

### bcrypt / passlib
**Síntoma**: `verify_password` lanza `"password cannot be longer than 72 bytes"`. **Causa**: incompatibilidad passlib 1.7.4 con bcrypt 4.x+. **Solución**: `pip install bcrypt==3.2.2`

### Conexión a PostgreSQL
**Síntoma**: `Connection refused` o `fe_sendauth: no password supplied`. **Causa**: host/puerto o credenciales incorrectos, o `.env` no cargado (correr desde `backend/`). **Solución**: `DB_SERVER`/`DB_PORT=5432`/`DB_PASSWORD` correctos; con el compose `with-db` usar `DB_SERVER=db`.

### Alembic propone recrear tablas existentes
**Causa**: `include_schemas=True` falta en `env.py`. **Verificación**: revisar que esté en `run_migrations_offline` y `run_migrations_online`.

### Comentario desactualizado en `DIM_Indicador.modulo`
El modelo documenta `modulo` como `GESTION | RESULTADOS`, pero el código de `iup_service.py` opera con `PRODUCTIVIDAD | COACHING | CAPACITACION` (y `COMERCIAL` se deriva de `FACT_Ventas`/`FACT_EVOIR`, no de `Indicador.modulo`). Si se va a tocar este campo, verificar los valores reales en la BD antes de asumir cualquiera de las dos documentaciones.

### web.config / caché de IIS
Después de cambios al `web.config` de producción, IIS y el navegador pueden servir una versión cacheada. Redesplegar y purgar caché del navegador tras cualquier cambio de configuración (tarea abierta, ver §22).

---

## 22. Pendiente de Implementar

| Feature | Estado | Notas |
|---------|--------|-------|
| Completar frontend | Resuelto en buena parte | Ya existen vistas para todos los módulos (Dashboard, Productividad, Cobertura Predictiva, Coaching, Categorización, Ranking, Reconocimiento, LSII, ETL, Admin, Reportes) |
| Módulo de Visita Médica (VISTA) | **Resuelto** (8 fases) | Esquema `Visita` en PostgreSQL; router `prefix="/visita"` en `visita.py`. Fases: Panel Médico (`DIM_MedicoVisita`), Planeación (`PlaneacionCiclo`, reglas P01-P03), Registro (`FactVisita`, hora servidor/ventana 60min), Ruptura+Cierre (`CierreCicloVisita`, rodaje idempotente de `ciclos_sin_visita`), Cobertura (gauges/ranking tiempo real), Proyección (ritmo vs requerido + simulador), Parrilla+Muestras (`ParrillaPromocional`+`MuestraEntregada`, cruce por producto normalizado), Costo+ROI (`ParametroCosto`, ingresos de `FACT_Ventas`). Servicios `visita_*_service.py`; páginas `frontend/src/pages/visita/*`. RBAC: VM auto-scope a `rm_id`; cierre/parrilla/costo = ADMIN+GERENTE_PRODUCTIVIDAD. Reutiliza `Config.DIM_RM` (VM), `DIM_Ciclo`, `DIM_Especialidad`, `DIM_Linea`. **v2 (jul-2026):** Parrilla y Costo/ROI tienen **selector de ciclo** en el frontend (`CostoRoiVisita.tsx`/`ParrillaVisita.tsx`) — la config siempre se guardó por `(ciclo,línea)`, ahora se puede ver/editar por ciclo; los ciclos **cerrados** quedan en **solo-lectura** (guard `_guard_ciclo_abierto` en `guardar_parrilla`/`publicar_parrilla`/`guardar_estructura`/`importar_excel`). El **registro de visita** captura **GPS** (`FactVisita.latitud/longitud`) y **foto del centro** como BLOB (`FactVisita.foto`/`foto_mime`, BYTEA, migración `d4b8f1a6c290`), con endpoints `POST/GET /visita/{id}/foto` (validación magic bytes JPEG/PNG + 3 MB) y captura por `navigator.geolocation` + `<input capture>` en `RegistrarVisita.tsx` (foto opcional). |
| IUP consistencia completo | **Resuelto** | Ver §7 — promedio de los 3 ciclos previos más recientes, base neutral 0 si no hay historial |
| Exportación PDF/Excel de reportes | **Resuelto** | Ver §15 — `exportacion.py` |
| Ranking Gerentes de Distrito | **Resuelto** | `FACT_RankingGerente` (ver §4) |
| Certificados de premios PDF | **Resuelto** | `reconocimiento_service.generar_certificado_pdf` (ReportLab) se dispara como BackgroundTask tanto al otorgar premio manual (`reconocimiento.py`) como en la generación automática (`reconocimiento_service.generar_reconocimientos_automaticos`); marca `certificado_generado=True`. |
| Cargar datos iniciales de Cobertura Predictiva en producción | **OBSOLETO — no hay nada que cargar** | Verificado (jul-2026): el dashboard se calcula **en vivo** desde el módulo Visita — `_medicos_planeados` lee `Visita.PlaneacionCiclo` y las visitas salen de `Visita.FactVisita`. Toda la ruta `vivo` (`ciclos_vivo`/`dashboard_vivo`/`categorias_vivo`) **nunca toca** `Config.DIM_TargetMedico` ni `DW.FACT_Visita`: esas tablas solo las leen `calcular_cobertura_rm`/`calcular_cobertura_equipo` (endpoints legacy `/resumen` y `/rm/{id}`), que el frontend ya no llama. El pendiente venía de la etapa de importación por Excel, retirada de la UI. |
| Redesplegar web.config corregido y purgar caché | Pendiente | Ver nota en §21/§20 |
| Capturar screenshots reales de la app MSM | Pendiente / en curso | Para materiales comerciales |
| Módulo de Exámenes v2.0 | **Resuelto** | Esquema `exam` (autocontenido). **Gate de integración al KPI**: la entrega de un examen ya NO alimenta `DW.FACT_ResultadoIndicador`; la nota EVAL_CONOCIMIENTOS de los RM entra **solo** cuando Capacitación consolida el (ciclo, país) vía `examen_consolidacion_service.consolidar_ciclo` (tabla `exam.FactConsolidacionCiclo`, migración `c1e7a2f4b9d0`; guard de ciclo abierto; re-ejecutable; 1 recálculo). Endpoints `GET/POST /examenes/consolidacion`; panel `ConsolidacionPanel.tsx`. **4 mejoras**: (1) nota real + banner Aprobado/No Aprobado/Provisional + flag `provisional` en el reporte; (2) correo de correcciones a `fecha_limite+30min` (`notification_service.notificar_correcciones_examen` + `app/core/scheduler.py` APScheduler + botón demo `POST /examenes/{id}/correcciones/enviar`); (3) `analisis_preguntas` con `acierto_pct`/`fallan`/`aciertan`/`etiqueta` + tooltip de nombres + recomendaciones ≥40%; (4) tipo de pregunta `objecion` (Objeción de Producto, reusa `Pregunta.escenario`, banner naranja). |
| Notificaciones email | **Resuelto** | `notification_service.py` (smtplib, best-effort, no-op si `MAIL_SERVER=""`) cableado a: `ranking_service` (`notificar_ranking_generado`), `reconocimiento_service` (`notificar_reconocimiento_otorgado`), `examen_intento_service` (`notificar_resultado_examen`) y `notificar_correcciones_examen` (correcciones de examen, T+30min vía APScheduler). Gmail SMTP configurado en `.env`; envío real verificado. |
| Tests unitarios | **Resuelto (en curso)** | Suite `pytest` con **756 tests** (`backend/tests/test_*.py`): IUP, puntaje, elegibilidad, token_store, RBAC/authz, módulo Exámenes (incl. `test_examen_consolidacion_service.py`), módulo Visita (`test_visita_service.py`, incl. guards de ciclo cerrado, foto/GPS y el flujo de alta+aprobación del Bloque B) y el motor de categorización de un médico (`test_categorizacion_un_medico.py`). CI de GitHub Actions corre pytest+build. Cobertura ampliable a routers/ETL. |
| Refresh token en BD | **Resuelto** (FIX W-04 v2) | La blacklist vive en la base de datos (`Security.FACT_TokenRevocado`, modelo `TokenRevocado`). `token_store.revocar_token`/`token_esta_revocado` reciben `db`; revocación consistente entre workers y duradera tras reinicio. Purga oportuna de expirados con `purgar_expirados`. |
| Dashboard Power BI | **DESCARTADO** | Decisión del cliente (jul-2026): *"nunca voy a trabajar con Dashboard Power BI"*. No proponerlo ni retomarlo. Los dashboards del sistema (ejecutivo, cobertura, LSII, categorización) se construyen dentro de la app con recharts — esa es la vía definitiva, no un paso intermedio. |

---

## 23. Convenciones de Código

### Backend
- **Modelos**: `Mapped[tipo]` + `mapped_column()` (SQLAlchemy 2.0). Nunca `Column()` antiguo.
- **Schemas**: Pydantic v2 con `model_config = ConfigDict(from_attributes=True)` en responses
- **Routers**: `APIRouter(prefix="/<módulo>", tags=["..."])`. Prefijo en el router, no en el endpoint.
- **Constantes RBAC por router**: definir `Depends(require_roles(...))` como constante de módulo y reutilizarla en las firmas de los endpoints (ver §17).
- **Services**: reciben `db: Session`, no acceden a HTTP. Lógica de negocio pura. El motor de Score/Ranking masivo vive en `motor_calculo_service` (100% Python, §8), igual que Categorización y Cobertura Predictiva.
- **BackgroundTasks**: siempre crear sesión propia con `SessionLocal()` y cerrarla en `finally`
- **Logs**: `from loguru import logger`. Nunca `print()`.
- **Timestamps**: `datetime.now(timezone.utc)`. Nunca `datetime.utcnow()` (deprecated).
- **Seguridad de archivos**: nombre con UUID (`_safe_filename`), validar magic bytes
- **Cargas Excel con resolución dual de entidad**: cuando una columna de referencia puede venir como código de negocio o como ID numérico crudo, resolver ambos casos explícitamente (patrón `_resolver_rm` en `cobertura_predictiva.py`) en vez de asumir un solo formato.
- **Código muerto vía no-registro**: si un módulo se sustituye pero se decide no borrar el código viejo, dejarlo sin registrar en `router.py`/`App.tsx` y documentar la sustitución con un comentario inline (patrón usado en `comercial.py`/`capacitacion.py`, y comentado explícitamente en `router.py`).

### Frontend
- Componentes funcionales con TypeScript estricto
- Estilos: MUI `sx` prop
- Forms: react-hook-form + zod
- Llamadas API: en `services/` con axios
- Pantallas de carga Excel: patrón Stepper + FormData (ver `ETL.tsx`, replicado en `CategorizacionAdmin.tsx`)
- Páginas de administración de catálogos de un módulo nuevo: como tab dentro de `Admin.tsx` (patrón `LsiiAdmin.tsx`, `CoberturaPredictivaAdmin.tsx`, `CategorizacionAdmin.tsx`), no como ruta top-level separada
- Selectores de relación (línea, gerente, etc.): usar selector relacional con nombre visible, nunca un campo de texto libre para un ID
- **Contexto global País+Ciclo (v2)**: tienda Zustand en `frontend/src/store/ciclo.store.ts` distingue
  `cicloAbierto` (de trabajo, único editable) de `cicloId`/`ciclo` (en consulta, default = abierto);
  `esSoloLectura` se deriva de compararlos. La barra superior (`CicloPaisBadge`) es **informativa**;
  el `CicloPaisHeader` (montado 1 vez en `MainLayout`, arriba del `Outlet`) da país (Select solo para
  roles multipaís) y ciclo (default abierto) a todos los módulos. Los módulos de **captura** leen
  `esSoloLectura` para apagar sus controles; el backend rechaza (409) cualquier escritura sobre un ciclo
  cerrado vía `recalculo_service.validar_ciclo_abierto`. RM/Gerentes ven su país fijo; nadie edita ciclos
  cerrados/futuros (sin excepción para ADMIN).

### Migraciones
- Ningún cambio de esquema a mano con `ALTER TABLE`
- Todo cambio de modelo → generar migración → revisar → aplicar → commitear junto con el modelo
- El cálculo de Score/Ranking/Categorización/Cobertura es 100% Python (no hay stored procedures); una migración solo cambia esquema/datos, nunca lógica de cálculo

---

## 24. Cómo Solicitar Mejoras a una IA

Para pedir mejoras, referencia sección y archivo. Ejemplos:

**Agregar endpoint nuevo**:
> "En MSM (sección 16 - API Endpoints), agrega un endpoint GET `/ranking/gerentes` si no existe ya un equivalente para `FACT_RankingGerente` (sección 4). Usa el patrón de `ranking.py` existente."

**Modificar el motor de Score**:
> "En MSM (sección 7 - Motor de Score Integral), modifica `iup_service.py` para que el componente de Comercial también considere [...]. Recuerda que el cálculo masivo por ciclo vive en `motor_calculo_service` (sección 8, 100% Python) — si el cambio debe aplicar al recálculo masivo, también hay que tocarlo ahí."

**Agregar migración**:
> "En MSM (sección 19 - Migraciones), genera una migración Alembic para [...]. Usa la plantilla de columna NOT NULL segura de MIGRATIONS.md."

**Corregir bug**:
> "En MSM (sección 21 - Problemas Conocidos), implementa en `app/core/security.py` la solución directa con bcrypt (sin passlib) para eliminar la dependencia que causa el error de 72 bytes."

**Agregar criterio a Categorización Médica**:
> "En MSM (sección 14 - Categorización Médica), agrega un sexto criterio `DIGITALIZACION` con peso 5% (reduciendo proporcionalmente los demás a 95%). Sigue el patrón de `DIM_CriterioCategoria` + `DIM_CriterioCategoriaTabla` existente y actualiza `categorizacion_service.py`."

**Agregar dimensión LSII**:
> "En MSM (sección 12 - LSII), agrega una nueva dimensión de Receptividad vía `POST /lsii/admin/dimensiones`. Recuerda que `score_oculto`/`peso_dimension` nunca deben exponerse en `GET /lsii/catalogo`."

---

## 25. Módulo de Seguridad RBAC/ABAC (jul-2026)

**Spec/plan**: `docs/superpowers/specs/2026-07-18-rbac-abac-seguridad-design.md` +
`docs/superpowers/plans/2026-07-18-rbac-abac-fase1.md`.

Control de acceso con **RBAC** (permisos a roles) + **alcance ABAC** (`own/team/all`), **denegación
por defecto**. Modelo de tres ejes: **recurso** (28 funcionalidades) × **acción**
(`read/register/configure/approve/export/admin`) × **alcance**.

**Fuente de verdad = BD (editable desde la UI), con el código como valores de fábrica** (jul-2026):
- **Runtime**: el motor lee la matriz de `Security.FACT_RolPermiso` vía un **caché en memoria**
  (`app/core/authz/runtime.py`), que se recarga cuando cambia `MAX(actualizado_en)` (migración
  `0019`). Los guards (`deps.require/autorizar/autorizar_export`) llaman `runtime.refrescar_si_cambio(db)`
  antes de evaluar. **Anti-bloqueo**: si el caché no cargó o la tabla está vacía, `runtime.celda` cae a
  `matrix.MATRIZ` (fábrica).
- **Edición**: `app/core/authz/edicion.py` (`aplicar_cambios`, `restablecer`, `matriz_actual`) +
  endpoints **`PUT /authz/matriz`** (guardar, en caliente) y **`POST /authz/matriz/restablecer`**
  (volver a fábrica), solo ADMIN, **auditados** (`PERMISO_MODIFICADO` / `PERMISOS_RESTABLECIDOS`).
  Salvaguarda: la **columna ADMIN es inmutable** (400 si se intenta) y la acción `admin` no es
  asignable. Frontend: pestaña **"Roles y Permisos"** (en `Administracion.tsx`, tras Usuarios) con
  modo Editar → selects Acción/Alcance por celda + Guardar/Descartar/Restablecer (`MatrizRoles.tsx`).
- **`matrix.py` = valores de fábrica** (`MATRIZ[recurso][rol] = (accion, alcance)|None`): siembra
  inicial (`scripts/seed_authz.py`) y destino del botón "Restablecer". `tests/test_authz_matriz.py`
  (oráculo del spec §5) sigue validando la fábrica. Spec:
  `docs/superpowers/specs/2026-07-18-matriz-permisos-editable-design.md`.

**Motor** (`app/core/authz/`):
- `engine.can(user, accion, recurso) -> Alcance | None` — `admin` concede todo; `configure/approve/register`
  implican `read` al mismo alcance; `export` es independiente. `alcance_export_modulo(user, recurso)`
  capa el export por la lectura del módulo (nunca la amplía).
- `scope.rm_ids_visibles(db, user, alcance)` / `scope.assert_ve_rm(...)` — filtros `own/team/all` +
  guard anti-IDOR. `app/core/authz/deps.py`: `require(accion,recurso)` / `autorizar(accion,recurso)` /
  `autorizar_export(recurso)` (dependencies FastAPI que reemplazan a `require_roles`).
- `seed.sembrar_todo(db)` — siembra idempotente de la matriz a `Security.DIM_Recurso`/`FACT_RolPermiso`
  (`scripts/seed_authz.py`). `audit.registrar_evento_seguridad(...)` → `Security.FACT_AuditoriaSeguridad`
  (append-only, acciones sensibles).

**Roles** (enum `Rol`, +4 nuevos jul-2026): `GERENTE_MARKETING`, `GERENTE_MEDICO`, `ANALISTA_DATOS`,
`FINANZAS`. Mapeo canónico: `GERENTE_MARCA`=Gerente de Producto, `GERENTE_PRODUCTIVIDAD`=Capacitación y
Productividad, `PRESIDENCIA`=Director General, `ADMIN`=Superadmin. **La matriz cubre los 13 roles del enum**:
`DIR_COMERCIAL`=fila de `ANALISTA_DATOS`, `CONSULTA`=igual sin export (derivados en `matrix.py`);
**`CAPACITACION`=fila PROPIA mínima** (coordinador de exámenes: solo `examen.configurar` CFG + `examen.rendir`
read all; NO hereda de GERENTE_PRODUCTIVIDAD — ajuste jul-2026 para que no gane LSII/ETL/reconocimiento/ranking).

**Módulo Exámenes 100% matriz-driven (jul-2026)**: `examenes.py` (antes `RequireCapacitacion`) ahora usa la
matriz: gestión (crear/publicar/preguntas/asignar/calificar/resultados/consolidar) = `require(CONFIGURE,
examen.configurar)` (CAPACITACION+GERPROD+GERENTE_MEDICO+ADMIN); vista de equipo (resumen/recomendaciones) =
`require(READ, examen.rendir)` (GD ve su equipo — celda ajustada); el **auto-servicio** (rendir/responder/
entregar/reporte propios) sigue en `RequireAnyAuth` (la autorización es tener el examen ASIGNADO, self-scoped,
no un rol). **Toda la app queda matriz-driven salvo `/admin`** (megapantalla de catálogos = admin de sistema).

**Contrato frontend**: `GET /authz/me/permisos` (capacidades efectivas del usuario). El frontend deriva
navegación/rutas/controles de aquí vía el hook `usePuede()` (store `permisos.store.ts`, suscribe a `permisos`
para re-render al cargar) + `ProtectedRoute recurso=/accion=` + ítems de `Sidebar` con `recurso`.
`GET /authz/matriz` (solo ADMIN) = inspección.

**Revocación por cambio de rol**: `create_access_token` emite `iat`; `deps.get_current_user` rechaza
tokens con `iat < Usuario.roles_actualizado_en` (que `PUT /admin/usuarios/{id}` fija al cambiar el rol,
+ auditoría `ROL_ASIGNADO`). La autorización siempre lee `user.rol` **fresco de la BD**, así que un token
viejo nunca acarrea permisos obsoletos; la revocación por `iat` es defensa adicional.

**Cómo cambiar un permiso**: normalmente **desde la UI** (pestaña "Roles y Permisos" → Editar →
Guardar) — se aplica en caliente, sin redeploy. Para cambiar los **valores de fábrica** (nuevo default
del sistema): editar `matrix.py` → actualizar el oráculo del spec (el test lo obliga) → desplegar;
"Restablecer a fábrica" o `scripts/seed_authz.py` los aplican. NO dispersar condicionales
`if rol == ...` por el código.

**FASE 1 (implementada, NO destructiva)**: motor + matriz + seed + auditoría + revocación + endpoint +
pruebas (`tests/test_authz_*.py`, incl. parametrizada 28×10). Migración `0017_rbac_fase1`.

**FASE 2 (implementada, jul-2026)** — flip de la matriz, módulo por módulo. Endpoints cableados con
`require/autorizar` + scope (criterio: agregar el guard de matriz CONSERVANDO el scope existente —GD ve el
agregado de empresa con nombres solo de su equipo vía `scope_gd`, regla del cliente— y SIN regresar
escrituras que el cliente amplió deliberadamente). Cierres reales: firewall Médico-Comercial en
`productividad`/`ranking`/`costoroi`; `FINANZAS` fuera de `cobertura.predictiva`. Módulos:
`productividad`, `ranking`, `cobertura_predictiva`, `coaching`/`coaching_more`, `visita` (registrar +
planeación + parrilla-read), `exportacion` (capada por lectura + **filtrada por scope** en el servicio +
auditada). **Workflow Costo/ROI** (Finanzas CONFIGURE → Director APPROVE): `Visita.CostoEstructura` con
`estado` (BORRADOR/APROBADO), guard `_guard`+`CostoAprobadoError`(409), reabrir solo ADMIN (auditado);
migración `0018`; UI en `CostoRoiVisita.tsx`. Tests `tests/test_authz_wiring.py`.

**DEUDA / decisiones pendientes (Fase 2):**
- ~~`parrilla.configurar`~~ **RESUELTO (jul-2026)**: configura el **Gerente de Producto** (`GERENTE_MARCA`)
  + ADMIN (decisión del cliente). Matriz fila 9 ajustada (GERENTE_MARCA=configure, GD=solo consulta);
  `POST /visita/parrilla` y `/parrilla/publicar` con `require(CONFIGURE, parrilla.configurar)`; frontend
  `ParrillaVisita` edita solo ADMIN/GERENTE_MARCA.
- ~~`categorizacion.detalle`~~ **RESUELTO (jul-2026)**: las escrituras del motor (criterios+pesos+categorías)
  en `admin.py` → `require(CONFIGURE, categorizacion.detalle)` = Gerente de Producto (GERENTE_MARCA) + ADMIN.
  Lecturas amplias (datos de referencia de la vista básica).
- ~~Módulos fuera de la matriz~~ **RESUELTO (jul-2026, extender)**: +4 recursos (matriz 28→**32**):
  `reconocimiento`, `lsii.evaluar`, `lsii.admin`, `etl.cargar` (wireados en sus routers + nav/rutas). Solo
  `/admin` (megapantalla de catálogos = administración de sistema) queda por rol (ADMIN+GERPROD).
- ~~Export scope~~ **RESUELTO**: `exportacion` filtra por `rm_ids` (GD exporta su equipo), capado por lectura + auditado.
- ~~Notificación Costo/ROI~~ **RESUELTO (jul-2026)**: al guardar Finanzas un BORRADOR se avisa por correo al
  Director (`notification_service.notificar_costo_pendiente_aprobacion`, best-effort).
- **Los 5 puntos de deuda de Fase 2 quedaron RESUELTOS (jul-2026).**
- Del spec §9 (Fase 1): `team` para roles no-GD (`GERENTE_PRODUCTIVIDAD` en coaching/examen — alcance
  literal, sin resolución de equipo); módulos inexistentes (Inteligencia/Encuestas — Farmacias ya se
  construyó, ver §14d); separación de `medical_contact.read` de `medico.panel`.
