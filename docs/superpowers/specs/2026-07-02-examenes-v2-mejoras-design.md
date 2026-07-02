# Módulo de Exámenes v2.0 — Diseño de Mejoras

**Fecha:** 2026-07-02 · **Preparado para:** Moisés · **Confidencial**
**Estado:** Aprobado (brainstorming) — pendiente de plan de implementación.

---

## 1. Resumen

Cuatro mejoras al Módulo de Exámenes de VISTA más un cambio arquitectónico de fondo
en cómo el módulo integra su resultado al indicador de KPI **EVAL_CONOCIMIENTOS**.

| # | Mejora | Naturaleza |
|---|--------|-----------|
| A | **Gate de consolidación por (ciclo, país)** hacia `EVAL_CONOCIMIENTOS` | Arquitectura (backend + tabla nueva + frontend) |
| B | Nota real + banner Aprobado/No Aprobado + mensaje KPI | Frontend (bug de render) + campos de respuesta |
| C | Objeción de Producto — nuevo tipo de pregunta | Backend (tipo) + frontend creación/toma/reporte |
| D | Correo de correcciones a los 30 min del fin del tiempo hábil | APScheduler + notificación + botón demo |
| E | Estadísticas por pregunta con nombres + tooltip + recomendaciones | Backend (extensión) + frontend análisis |

**Principio rector (nota del cliente):** el módulo de exámenes es autocontenido
(esquema `exam`, con sus DIM/FACT propias). Las notas de los RM **solo** llegan al
KPI a través del proceso de consolidación por ciclo. Ninguna entrega individual
escribe al KPI.

---

## 2. Estado actual (base sobre la que se construye)

- **Esquema `exam`:** `DimExamen`, `DimPregunta`, `DimPreguntaOpcion`,
  `FactAsignacionExamen`, `FactIntentoExamen`, `FactIntentoRespuesta`, `FactFuenteIA`.
  Tipos de pregunta existentes: `multi`, `abierta`/`caso`.
- **Puente KPI actual** (`examen_kpi_service.alimentar_eval_conocimientos`): se
  dispara en **cada entrega** (desde `_finalizar_resultado` en
  `examen_intento_service.py`) y hace upsert inmediato a
  `DW.FACT_ResultadoIndicador` + recálculo. **Este comportamiento se elimina.**
- `examen_resultados_service.analisis_preguntas` ya da % de error por pregunta
  (sin nombres). Base de la mejora E.
- `notification_service.notificar_resultado_examen` envía correo por intento
  (inmediato, gated por `asignacion.notif_activa`). No hay APScheduler cableado.
- Frontend: `MisExamenes.tsx` (visitador), `Examenes.tsx` (creador),
  `EquipoExamenes.tsx` (estadísticas / vista Capacitación).
- El motor de Score/Ranking vive en SQL Server; el recálculo se dispara vía
  `recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)` y solo opera
  sobre ciclos abiertos (`validar_ciclo_abierto` → `CicloCerradoError`).

---

## 3. A — Gate de consolidación por (ciclo, país)

### 3.1 Tabla nueva `exam.FactConsolidacionCiclo`

| Columna | Tipo | Nota |
|---------|------|------|
| `id` | int PK | |
| `ciclo_id` | int FK `Config.DIM_Ciclo.id` | |
| `pais_codigo` | str(10) | |
| `estado` | str(15) | `pendiente` \| `consolidado` |
| `rms_consolidados` | int | # de RM escritos a la FACT en la última corrida |
| `nota_promedio_equipo` | Numeric(5,2) nullable | promedio de las notas consolidadas |
| `fecha_consolidacion` | DateTime nullable | UTC-aware |
| `consolidado_por_usuario_id` | int FK `Security.DIM_Usuario.id` nullable | |

`UNIQUE(ciclo_id, pais_codigo)`. Migración Alembic idempotente (patrón del proyecto).

### 3.2 Cambio de flujo

- En `examen_intento_service._finalizar_resultado`: **se elimina** la llamada a
  `examen_kpi_service.alimentar_eval_conocimientos`. La entrega ya no toca la FACT.
  (El correo de resultado por intento permanece si `notif_activa`.)
- `examen_kpi_service` se refactoriza: la lógica de cálculo del promedio por RM
  (`_nota_promedio_rm`) y el upsert a `FACT_ResultadoIndicador` se exponen como
  funciones reutilizables **sin** recálculo embebido. Ya no se auto-dispara.

### 3.3 Servicio nuevo `examen_consolidacion_service.py`

- `estado_consolidacion(db, ciclo_id, pais_codigo) -> dict`: preview sin escribir.
  Devuelve `{estado, rms_con_nota, rms_pendientes:[nombres], nota_promedio,
  ultima_consolidacion, ciclo_abierto}`. "RM con nota" = RM del país con al menos
  un examen `EVAL_CONOCIMIENTOS` del ciclo con intento finalizado con `score`.
- `consolidar_ciclo(db, ciclo_id, pais_codigo, usuario_id) -> dict`:
  1. `validar_ciclo_abierto(db, ciclo_id)` (aborta con mensaje si cerrado).
  2. Por cada RM del país con exámenes marcados del ciclo: calcular promedio y
     upsert idempotente (delete-then-insert) en `FACT_ResultadoIndicador`.
  3. Marcar/actualizar la fila `FactConsolidacionCiclo` a `consolidado` con
     conteo, promedio, fecha y usuario.
  4. **Un** `recalcular_ciclo(db, ciclo_id, pais_codigo)` al final.
  - Re-ejecutable mientras el ciclo esté abierto (recalcula limpio).

### 3.4 Endpoints (router `examenes.py`)

RBAC = `RequireCapacitacion` (ADMIN, GERENTE_PRODUCTIVIDAD).

- `GET /examenes/consolidacion?ciclo_id=&pais_codigo=` → `estado_consolidacion`.
- `POST /examenes/consolidacion/consolidar` (body `{ciclo_id, pais_codigo}`) →
  `consolidar_ciclo`. Respuesta: `{rms_consolidados, nota_promedio_equipo,
  recalculo:{...}, estado}`.

### 3.5 Frontend

Panel "Consolidación de Ciclo → KPI" en `EquipoExamenes.tsx`: selector ciclo + país,
tarjeta de preview (RM con nota / pendientes con nombres / promedio), estado del gate
y fecha de última consolidación, botón **Consolidar ciclo** (deshabilitado si el ciclo
está cerrado), con confirmación.

---

## 4. B — Nota real + banner Aprobado/No Aprobado

- **Backend:** el endpoint de entrega (`POST .../entregar` o equivalente) incluye en
  la respuesta `score`, `aprobado`, `nota_minima` y `provisional` (bool = quedan
  abiertas sin calificar). El score ya se calcula correctamente hoy.
- **Frontend `MisExamenes.tsx`:** el resultado se renderiza desde **estado de React**
  (no manipulación de DOM — origen del bug 0%). Banners:
  - `aprobado` → verde: "¡Examen Aprobado! Suma para tu KPI al consolidar el ciclo."
  - `!aprobado && !provisional` → rojo: "Examen no aprobado — por debajo de nota
    mínima", muestra nota obtenida y mínima + "NO suma para KPI. Solicita un nuevo
    intento a tu supervisor."
  - `provisional` → neutro: "Pendiente de calificación del Gerente."

Redacción del mensaje KPI alineada con el gate: el aporte al KPI ocurre al consolidar.

---

## 5. C — Objeción de Producto (tipo de pregunta)

- **Sin cambio de esquema:** `Pregunta.tipo` es String; se agrega el valor
  `"objecion"`. El texto de la objeción del médico se guarda en el campo existente
  `Pregunta.escenario`. Calificación idéntica a `multi` (opción correcta única).
- **Validación** (crear pregunta): si `tipo == "objecion"`, `escenario` es
  obligatorio.
- **Creación (`Examenes.tsx`):** botón "🛡️ + Objeción de Producto" con tooltip guía;
  placeholder de `escenario`: *"Ej: El Dr. García dice: No receto [Producto X] porque
  escuché que causa [efecto adverso]…"*.
- **Toma (`MisExamenes.tsx`):** banner **naranja** "Objeción del Médico sobre el
  Producto" con el escenario, antes de las opciones.
- **Reporte:** objeción original + opción elegida + opción correcta + explicación.

---

## 6. D — Correo de correcciones (T+30 min)

- **"Fin del tiempo hábil" = `FactAsignacionExamen.fecha_limite`** (único cierre por
  examen). El envío se programa a `fecha_limite + 30 min`.
- **APScheduler:** singleton en `app/core/scheduler.py` (`BackgroundScheduler`),
  arrancado/cerrado en el lifespan de `main.py`. Al publicar/asignar un examen con
  `fecha_limite`, se programa el job `enviar_correcciones_examen(examen_id)`.
- **Notificación** `notification_service.notificar_correcciones_examen(db, examen_id)`:
  por cada participante (último intento por asignación), arma el HTML de cada pregunta
  incorrecta: enunciado, opción elegida (✗), opción correcta (✓), explicación.
  Best-effort / no-op si `MAIL_SERVER=""` (comportamiento actual).
- **Botón demo:** `POST /examenes/{examen_id}/correcciones/enviar` (RequireCapacitacion)
  → dispara el envío ahora y devuelve el conteo. En `Examenes.tsx`/`EquipoExamenes.tsx`.
- **Aviso al visitador** al finalizar (texto en `MisExamenes.tsx`): "Recibirás por
  correo las correcciones 30 minutos después de concluido el tiempo hábil del examen."

---

## 7. E — Estadísticas por pregunta con nombres

- **Backend:** extender `examen_resultados_service.analisis_preguntas(db, examen_id)`
  para incluir por pregunta: `acierto_pct`, `error_pct`, `aciertan:[nombres]`,
  `fallan:[nombres]`, y `etiqueta` (✓ Bien comprendida / ⚡ Requiere refuerzo /
  ⚠️ Brecha crítica según umbrales). Nombres desde el **último intento por asignación**
  (consistente con `resumen_examen`), resolviendo RM/Gerente → nombre.
- **Recomendaciones:** función/endpoint que liste preguntas con `error_pct >= 40` y
  los nombres de quienes fallaron.
- **Frontend `EquipoExamenes.tsx` "Análisis por Pregunta":** selector de examen, barras
  verde (% acierto) / roja (% desacierto) por pregunta, **tooltip con nombres** al pasar
  el cursor, cards resumen (mejor / más fallada) y lista de recomendaciones.

---

## 8. Lógica de KPI (reglas)

| Condición | Ve el visitador | Suma KPI |
|-----------|-----------------|----------|
| Nota ≥ mínima | Banner verde "APROBADO" | ✅ Sí — **al consolidar el ciclo** |
| Nota < mínima | Banner rojo + nota real | ❌ No |
| Tiempo agotado sin entregar | Nota sobre lo respondido | ❌ No (si < mínima) |

El "✅ Sí" se materializa en `FACT_ResultadoIndicador` únicamente cuando Capacitación
ejecuta la consolidación del (ciclo, país).

---

## 9. Alcance y pruebas

- **Migración:** una sola tabla nueva (`exam.FactConsolidacionCiclo`), Alembic idempotente.
- **Tests (`pytest`, sumar a la suite existente):**
  - Consolidación: gate abierto vs. cerrado (abortado), idempotencia, promedio por RM,
    recálculo disparado exactamente una vez, estado persistido.
  - Entrega ya **no** escribe a la FACT (regresión del auto-feed eliminado).
  - Tipo `objecion`: validación (escenario obligatorio) y calificación por opción.
  - `analisis_preguntas` extendido: nombres correctos de aciertan/fallan, etiquetas,
    recomendaciones ≥40%.
  - Correcciones: armado del cuerpo (preguntas incorrectas del último intento).
- **Reutiliza** tablas/servicios existentes salvo lo indicado.

---

## 10. Fuera de alcance (YAGNI)

- Reprogramación dinámica del job de correo si cambia `fecha_limite` tras publicar
  (se programa al publicar/asignar; el botón manual cubre reenvíos).
- Consolidación multi-país en un clic (se opera por país; iterar países queda a criterio
  del operador). Se puede añadir después sin cambiar el modelo.
