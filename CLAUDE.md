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
| `DIM_CriterioCategoria` | `CriterioCategoria` | Los 5 criterios ponderados del motor (ver §14) |
| `DIM_CriterioCategoriaTabla` | `CriterioCategoriaTabla` | Rangos/niveles por criterio (análogo a `DIM_IndicadorTabla`) |
| `DIM_Medico` | `Medico` | Médicos, deduplicados por `(pais_id, nombre)` — el Excel fuente no trae código estable |

**Nota**: `DIM_Indicador.modulo` está documentado en el modelo como `GESTION | RESULTADOS` (comentario heredado de v1.0), pero el motor de Score (`iup_service.py`) agrupa y filtra en la práctica por los valores `PRODUCTIVIDAD`, `COACHING`, `CAPACITACION` (ver §6-7) — el comentario del modelo quedó desactualizado tras el rediseño y no debe tomarse como la lista vigente de valores.

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
- **Productividad**: promedio de `FACT_ResultadoIndicador.puntos_obtenidos` para indicadores con `modulo == "PRODUCTIVIDAD"`.
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
- `motor_calculo_service.generar_ranking(db, ciclo_id, pais_codigo)` — Score Integral + Ranking (**delete-then-insert**).
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

**Migraciones del motor**: las migraciones de la etapa SP (`e7a91f4c2b58`, `b8c4d2e1f5a9`, `e2f5b9c4a1d8`, `2c771e676bd7`, `e8f1a2c3d4b5`) están **archivadas** en `backend/alembic/versions/_mssql_archive/`; el cálculo actual es 100% Python y no depende de ellas.

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

**Motor_Formulas** — distingue cobertura de contactos totales:
- `L = COUNT(DISTINCT medico_codigo)` visitados (médicos únicos — COBERTURA)
- `M = COUNT(*)` contactos totales (incluye repetidos — PSP/CONTACTOS)
- Días hábiles vía NETWORKDAYS sobre `DIM_Feriado`.
- Meta de cobertura: resolución en cascada `país+línea+ciclo → país+línea → país` (`DIM_ParametroCobertura`, busca la más específica primero).

**Endpoints principales** (verificados):

| Método | Ruta | Descripción |
|--------|------|-------------|
| GET | `/cobertura-predictiva/resumen` | Resumen del equipo (sustituye a `/dashboard/comercial`) |
| GET | `/cobertura-predictiva/rm/{rm_id}` | Detalle de un RM |
| GET / POST | `/cobertura-predictiva/parametros` | Metas de cobertura |
| GET / POST | `/cobertura-predictiva/feriados` | Feriados |
| POST | `/cobertura-predictiva/cargar/target-medicos` | Carga universo de médicos programados (`DIM_TargetMedico`) |
| POST | `/cobertura-predictiva/cargar/visitas` | Carga bitácora de visitas (`FACT_Visita`) |

**Carga masiva — resolución dual de RM**: las cargas (`target-medicos`, `visitas`) aceptan en la columna `RM_CODIGO` tanto el código de negocio (ej. `"VM01"`) como el ID numérico crudo de `Config.DIM_RM` (ej. `RM_ID=73`) — función `_resolver_rm`. Columnas `PAIS_ID`/`LINEA_ID` opcionales solo se usan para validar consistencia contra el RM real (`_validar_consistencia_dimensional`); una discrepancia no bloquea la carga, queda en `advertencias`. Las cargas son idempotentes (filas ya existentes para la misma clave se omiten).

**RBAC con auto-filtro de scope** (patrón repetido también en Categorización, §14): `REPRESENTANTE_MEDICO` se filtra forzosamente a su propio `rm_id` (403 si no coincide o falta); `GERENTE_DISTRITO` se filtra a su propio `gerente_id` (vía `Usuario.gerente_id`, ver §4/§17).

**Frontend**: `CoberturaPredictiva.tsx` (vista operativa, con selector relacional de Línea/Gerente por nombre — no texto libre) + `CoberturaPredictivaAdmin.tsx` (tab de mantenimiento en `Admin.tsx`).

---

## 14. Módulo Categorización Médica

**Archivos**: `app/api/v1/routers/categorizacion.py`, `app/services/categorizacion_service.py`. Router: `prefix="/categorizacion"`.

**Sustituye** a Capacitación (`capacitacion.py` permanece en disco, no registrado). A diferencia del motor IUP/Ranking, **el motor de cálculo es 100% Python — explícitamente no usa stored procedures**.

**5 criterios ponderados** (`DIM_CriterioCategoria`):

| Criterio | Peso |
|----------|------|
| Pacientes/Semana | 30% |
| Poder Adquisitivo | 20% |
| Potencial de Prescripción | 10% |
| Ubicación Territorial | 30% |
| KOL (Key Opinion Leader) | 10% |

Resultado: categoría **A/B/C/D** por médico/ciclo (`DIM_CategoriaMedica` + `FACT_CategorizacionMedica`).

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
| POST | `/auth/change-password` | Autenticado | Nueva contraseña (mín 12 chars, mayúscula, minúscula, número) |
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
- Bloqueo temporal tras 5 intentos fallidos (30 minutos)
- `FACT_Auditoria` registra todos los logins y acciones POST/PUT/PATCH/DELETE
- Contraseña: mínimo 12 chars, mayúscula, minúscula, número
- Archivos ETL: validación de magic bytes + nombre UUID para prevenir Path Traversal

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

- Las migraciones de la etapa de stored procedures (`e7a91f4c2b58`, `b8c4d2e1f5a9`, `e2f5b9c4a1d8`, `2c771e676bd7`) están **archivadas** en `_mssql_archive/` — el motor actual es 100% Python (§8) y no las usa
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
| Cargar datos iniciales de Cobertura Predictiva en producción | Pendiente | Módulo desplegado, falta cargar `DIM_TargetMedico`/`FACT_Visita` reales |
| Redesplegar web.config corregido y purgar caché | Pendiente | Ver nota en §21/§20 |
| Capturar screenshots reales de la app MSM | Pendiente / en curso | Para materiales comerciales |
| Módulo de Exámenes v2.0 | **Resuelto** | Esquema `exam` (autocontenido). **Gate de integración al KPI**: la entrega de un examen ya NO alimenta `DW.FACT_ResultadoIndicador`; la nota EVAL_CONOCIMIENTOS de los RM entra **solo** cuando Capacitación consolida el (ciclo, país) vía `examen_consolidacion_service.consolidar_ciclo` (tabla `exam.FactConsolidacionCiclo`, migración `c1e7a2f4b9d0`; guard de ciclo abierto; re-ejecutable; 1 recálculo). Endpoints `GET/POST /examenes/consolidacion`; panel `ConsolidacionPanel.tsx`. **4 mejoras**: (1) nota real + banner Aprobado/No Aprobado/Provisional + flag `provisional` en el reporte; (2) correo de correcciones a `fecha_limite+30min` (`notification_service.notificar_correcciones_examen` + `app/core/scheduler.py` APScheduler + botón demo `POST /examenes/{id}/correcciones/enviar`); (3) `analisis_preguntas` con `acierto_pct`/`fallan`/`aciertan`/`etiqueta` + tooltip de nombres + recomendaciones ≥40%; (4) tipo de pregunta `objecion` (Objeción de Producto, reusa `Pregunta.escenario`, banner naranja). |
| Notificaciones email | **Resuelto** | `notification_service.py` (smtplib, best-effort, no-op si `MAIL_SERVER=""`) cableado a: `ranking_service` (`notificar_ranking_generado`), `reconocimiento_service` (`notificar_reconocimiento_otorgado`), `examen_intento_service` (`notificar_resultado_examen`) y `notificar_correcciones_examen` (correcciones de examen, T+30min vía APScheduler). Gmail SMTP configurado en `.env`; envío real verificado. |
| Tests unitarios | **Resuelto (en curso)** | Suite `pytest` con **187 tests** (`backend/tests/test_*.py`): IUP, puntaje, elegibilidad, token_store, módulo Exámenes (incl. `test_examen_consolidacion_service.py`) y módulo Visita (`test_visita_service.py`, incl. guards de ciclo cerrado y foto/GPS). CI de GitHub Actions corre pytest+build. Cobertura ampliable a routers/ETL. |
| Refresh token en BD | **Resuelto** (FIX W-04 v2) | La blacklist vive en la base de datos (`Security.FACT_TokenRevocado`, modelo `TokenRevocado`). `token_store.revocar_token`/`token_esta_revocado` reciben `db`; revocación consistente entre workers y duradera tras reinicio. Purga oportuna de expirados con `purgar_expirados`. |
| Dashboard Power BI | Pendiente | Sin conexión a Power BI Embedded |

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
