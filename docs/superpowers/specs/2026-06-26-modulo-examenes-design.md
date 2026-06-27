# Spec — Módulo de Exámenes (Evaluación de Visitadores Médicos)

**Proyecto:** MSM / SCGCPR · **Fecha:** 2026-06-26 · **Estado:** Diseño aprobado
**Fuente del requerimiento:** `DIMS_FACTS_V2/KPI EXAMENES/modelo_examenes_prompt.md`

---

## 0. Resumen

Módulo nuevo y **autocontenido** para que el equipo de Capacitación/Asesoría
Médica cree exámenes sobre productos farmacéuticos (manual o con IA), los asigne a
**evaluados** (Representantes Médicos y Gerentes), permita tomarlos desde cualquier
dispositivo (mobile-first), los corrija automáticamente y genere KPIs/reportes.

La nota del examen, además de su uso interno, **alimenta el indicador
`EVAL_CONOCIMIENTOS`** del motor de Score/IUP existente (solo para evaluados RM),
reutilizando el pipeline de KPI actual.

### Decisiones de alcance (acordadas)

| Tema | Decisión |
|------|----------|
| Alcance del spec | Módulo **completo** (manual + IA + KPIs + dashboards + correo + responsive). La implementación se faseará en el plan. |
| Rol creador | **Crear rol nuevo `CAPACITACION`** (Asesor Médico). ADMIN también puede todo. |
| Código muerto | **Eliminar** `routers/capacitacion.py` y `pages/capacitacion/Capacitacion.tsx`. **No tocar** `FACT_Capacitacion`/`DIM_Capacitacion` ni el componente CAPACITACION del Score (siguen vivos). |
| IA | **Claude / Anthropic** (SDK `anthropic`), modelo por defecto `claude-sonnet-4-6` (config a Opus). Generación en **background**. |
| Mobile/offline | **Responsive + autosave en `localStorage`**. Sin service worker / sin offline real. |
| Evaluados | RM (`DIM_RM`) **y** Gerentes (`DIM_Gerente`) — tomador polimórfico. |
| KPI integración | La nota → indicador `EVAL_CONOCIMIENTOS` vía el motor existente (solo RM). |
| Correo | Reutiliza `notification_service` (no-op hasta configurar `MAIL_SERVER`). |
| Opciones | Tabla normalizada `exam.DimPreguntaOpcion`. |
| Convención | Esquema `exam` (minúscula) + tablas PascalCase, como el módulo `cat`. |

---

## 1. Arquitectura e integración

**Principio (RN-15):** autocontenido. Esquema `exam` propio; no mezcla tablas con
otros módulos. **Única salida** hacia el resto del sistema: el puente
`EVAL_CONOCIMIENTOS` (§7).

### Archivos backend nuevos
| Archivo | Propósito |
|---------|-----------|
| `app/models/exam_models.py` | Modelos ORM del esquema `exam` (importar en `alembic/env.py`) |
| `app/schemas/examenes.py` | Schemas Pydantic |
| `app/api/v1/routers/examenes.py` | Router `prefix="/examenes"` (registrar en `router.py`) |
| `app/services/examen_service.py` | CRUD, ciclo de vida, asignación, preparación de intento |
| `app/services/examen_correccion_service.py` | Corrección automática, KPIs, puente EVAL_CONOCIMIENTOS |
| `app/services/examen_ia_service.py` | Extracción de documentos + generación con Claude |
| `alembic/versions/<rev>_exam_schema.py` | Esquema `exam`, tablas, índices, vistas, rol `CAPACITACION`, seed `DIM_IndicadorTabla` |

### Frontend nuevo
`frontend/src/pages/examenes/` (pantallas §6), rutas en `App.tsx` con guardas por
rol, entradas en `Sidebar.tsx`, llamadas en `services/api.ts`, tipos en `types/index.ts`.

### Rol y RBAC
- Agregar `CAPACITACION` al enum `Rol` (`app/models/usuario.py`) → migración que
  amplía el `CHECK` de la columna `rol`.
- Constantes del router: `RequireCapacitacion = require_roles(ADMIN, CAPACITACION)`.
- Evaluado: auth + auto-filtro a su `rm_id`/`gerente_id`.
- GD: scope a su equipo (`DIM_RM.gerente_id = Usuario.gerente_id`).

### Limpieza de código muerto
Eliminar `routers/capacitacion.py` y `pages/capacitacion/Capacitacion.tsx` (ya no
registrados). Confirmar que nada los importe. **No** tocar el scoring de Capacitación.

### Dependencias nuevas
`requirements.txt`: `anthropic`, `pdfplumber`, `python-docx`, `python-pptx`.
`.env` / `config.py`: `ANTHROPIC_API_KEY`, `EXAM_AI_MODEL=claude-sonnet-4-6`.

---

## 2. Modelo de datos (esquema `exam`)

Relaciones: `Examen 1—* Pregunta 1—* Opcion`; `Examen 1—* Asignacion 1—* Intento 1—* IntentoRespuesta`; `Examen 1—* FuenteIA`.

**Referencias a dimensiones existentes (no se duplican):**
- Evaluado = `DIM_RM` o `DIM_Gerente` (tomador polimórfico).
- `CreadoPorUsuarioId` → `Security.DIM_Usuario.id`.

### `exam.DimExamen`
`id`, `nombre`, `producto`, `nota_minima` (% aprobatorio, ej. 70), `tiempo_limite_min`,
`estado` [borrador|activo|completado|archivado], `fuente` [manual|ia],
`rand_preguntas` (bool), `rand_opciones` (bool), `creado_por_usuario_id` (FK Usuario),
`fecha_creacion`, `fecha_publicacion`, `activo`,
**`indicador_codigo`** (nullable; ej. `'EVAL_CONOCIMIENTOS'`),
**`ciclo_id`** (nullable FK `Config.DIM_Ciclo.id`).

### `exam.DimPregunta`
`id`, `examen_id` (FK), `tipo` [multi|caso], `escenario` (text null, solo `caso`),
`texto`, `explicacion`, `orden`, `activo`.

### `exam.DimPreguntaOpcion`
`id`, `pregunta_id` (FK), `texto_opcion`, `indice_original` (0-3), `es_correcta` (bool), `activo`.
Invariante: 4 opciones por pregunta, exactamente una `es_correcta`.

### `exam.FactAsignacionExamen`
`id`, `examen_id` (FK), `evaluado_tipo` [RM|GERENTE],
`evaluado_rm_id` (FK `DIM_RM`, null), `evaluado_gerente_id` (FK `DIM_Gerente`, null),
`fecha_asignacion`, `fecha_limite`, `intentos_max` (null=∞), `intentos_usados`,
`estado` [pendiente|completado|vencido], `notif_activa`.
**CHECK:** exactamente uno de `evaluado_rm_id`/`evaluado_gerente_id` no nulo, coherente con `evaluado_tipo`.

### `exam.FactIntentoExamen`
`id`, `asignacion_id` (FK), `evaluado_tipo`, `evaluado_rm_id`, `evaluado_gerente_id`,
`fecha_inicio`, `fecha_fin`, `score` (0-100), `aprobado` (bool), `tiempo_usado_seg`,
`orden_preguntas_json`, `user_agent`, `device_type`, `plataforma`, `ip_cliente`.

### `exam.FactIntentoRespuesta`
`id`, `intento_id` (FK), `pregunta_id` (FK), `opcion_elegida_id` (FK),
`indice_opcion_presentada`, `indice_original_elegido`, `es_correcta` (bool),
`mapa_opciones_json` (presentado↔original), `fecha_respuesta`.

### `exam.FactFuenteIA`
`id`, `examen_id` (FK), `tipo_archivo`, `nombre_archivo`, `ruta_archivo` (UUID, RN-10),
`texto_extraido_hash`, `prompt_usado`,
`estado_generacion` [pendiente|procesando|exitoso|error] (= estado del job background),
`mensaje_error`, `cargado_por_usuario_id`, `fecha_carga`.

---

## 3. Servicios / motores

### `examen_service.py`
- CRUD examen y preguntas/opciones (agregar/editar/eliminar/reordenar) — solo en `borrador` (RN-01).
- `publicar(examen)` — valida ≥1 pregunta (RN-02); estado → `activo`; set `fecha_publicacion`.
- `asignar(examen, evaluados[], fecha_limite, intentos_max, notif)` — crea `FactAsignacionExamen` por evaluado (RM y/o Gerente).
- `preparar_intento(asignacion, contexto_dispositivo)` — valida estado/fecha/intentos (RN-06);
  Fisher-Yates a preguntas (si `rand_preguntas`) y opciones (si `rand_opciones`);
  persiste `orden_preguntas_json` y el mapa de opciones; crea `FactIntentoExamen`;
  devuelve preguntas **sin** marcar la correcta.

### `examen_correccion_service.py`
- `registrar_respuesta(intento, pregunta, indice_presentado)` — guarda con `mapa_opciones_json`, índice presentado y original.
- `entregar(intento)` — anti-doble-entrega (RN); `score = round(correctas/total*100)`;
  `aprobado = score ≥ nota_minima`; `fecha_fin`, `tiempo_usado_seg`; ++`intentos_usados`;
  cierra asignación si aprobó o agotó intentos (RN-06); arma reporte; correo si `notif_activa`;
  **dispara puente EVAL_CONOCIMIENTOS** (§7).
- KPIs (§8): `calcular_kpis_examen`, `kpis_visitador`, `analisis_pregunta`.

### `examen_ia_service.py`
- `extraer_texto_fuente(path)` — pdfplumber (PDF) / python-docx (Word) / python-pptx (PPT) / texto pegado.
- `generar_preguntas_ia(texto, n_multi, n_casos)` — llama Claude (prompt base §11);
  `validar_preguntas_generadas(json)` (4 opciones, `correcta` 0-3, tipo válido);
  inserta como **borrador** para revisión (RN: IA siempre se revisa antes de publicar).
- Corre en `BackgroundTasks` con `SessionLocal()` propia; actualiza `FactFuenteIA.estado_generacion`.

### Aleatorización (Fisher-Yates)
La corrección compara siempre contra `DimPreguntaOpcion.es_correcta` (verdad original),
usando `mapa_opciones_json` para traducir la opción presentada → original (RN-05).

---

## 4. Endpoints (router `/examenes`)

### Capacitación (`RequireCapacitacion`)
- `POST /examenes` · `PUT /examenes/{id}`
- `POST /examenes/{id}/preguntas` · `PUT /examenes/{id}/preguntas/{pid}` · `DELETE /examenes/{id}/preguntas/{pid}`
- `POST /examenes/{id}/publicar`
- `POST /examenes/{id}/asignar`
- `POST /examenes/generar-ia` → `{job_id}` · `GET /examenes/generar-ia/{job_id}` (estado)
- `GET /examenes` (lista) · `GET /examenes/{id}` · `GET /examenes/{id}/resultados` · `GET /examenes/{id}/analisis-preguntas`

### Evaluado (auth + auto-filtro)
- `GET /examenes/mis-pendientes`
- `POST /examenes/{id}/iniciar` → intento + preguntas presentadas
- `POST /intentos/{id}/responder`
- `POST /intentos/{id}/entregar` → reporte
- `GET /intentos/{id}/reporte`
- `GET /examenes/mi-historial`

### GD (scope a su equipo)
- `GET /examenes/equipo/resultados` · `GET /examenes/equipo/ranking` · `GET /examenes/equipo/analisis-preguntas`

Todo POST/PUT/DELETE se audita en `FACT_Auditoria` (§9).

---

## 5. Integración con el motor de Score — `EVAL_CONOCIMIENTOS` (§7 detallado en 7)

Ver sección **7**. Resumen: al entregar un examen marcado (`indicador_codigo`), si el
evaluado es **RM** y el `ciclo_id` está **abierto**, se escribe la nota (0–10) en el
pipeline de KPI; el recálculo existente aplica la parametrización → IUP/ranking.

---

## 6. Frontend (mobile-first)

`frontend/src/pages/examenes/`, rutas en `App.tsx`, entradas en `Sidebar.tsx`.

### Capacitación
`DashboardExamenes`, `ExamenesLista`, `ExamenCrearManual`, `ExamenCrearIA` (subir
PDF/Word/PPT o pegar texto + N multi/N casos → lanza job, polling), `ExamenRevisionIA`
(revisar/editar antes de publicar), `ExamenAsignar` (selector de RMs y Gerentes por
nombre + fecha límite + intentos), `ExamenResultados`, `ExamenAnalisisPregunta`.

### Evaluado (RM / Gerente)
`MisExamenesPendientes`, **`TomarExamen`** (centro del módulo), `ReporteResultado`, `MiHistorial`.

### GD
`EquipoResultados`, `Ranking`, `ComparativoEvaluado`, `AnalisisPregunta`, exportar (patrón `exportacion`).

### `TomarExamen` (requisitos)
- Mobile-first; una pregunta por pantalla en móvil; botones grandes/táctiles; opciones con área de toque amplia; sin depender de hover.
- Barra de progreso; temporizador visible si hay `tiempo_limite`; `Anterior`/`Siguiente`/`Entregar`; confirmación si faltan respuestas.
- **Autosave en `localStorage`** por selección; restaura al recargar/girar pantalla/caída breve.
- No permite modificar tras entregar; control de sesión por token.
- Compatible Safari iOS, Chrome Android/desktop, Edge, Safari iPadOS.
- "Imprimir / guardar PDF" del reporte vía `window.print()` + CSS de impresión (PDF server-side con ReportLab opcional).

---

## 7. Puente EVAL_CONOCIMIENTOS (detalle)

**Modelo:** `DimExamen.indicador_codigo` + `DimExamen.ciclo_id` designan que un examen
aporta al indicador en un ciclo.

**Al entregar** (`examen_correccion_service.entregar`), si `indicador_codigo` no es nulo:
1. **Solo evaluado tipo RM** (Gerentes no alimentan este indicador del IUP de RM).
2. **Solo si el ciclo está ABIERTO** (`recalculo_service.validar_ciclo_abierto`, §8 del CLAUDE.md).
   Si está cerrado → la nota queda en el reporte, **no toca el Score**.
3. `nota = score/10` del **último intento** del RM (RN-09).
4. Si hay **varios exámenes marcados** en el ciclo → **promedio** de notas (último intento de cada uno).
5. **Upsert** `valor_real = nota_promedio` en el pipeline de KPI
   (`ETL.FACT_KPI_RAW` / `DW.FACT_ResultadoIndicador.resultado_real`) para
   `(rm_id, indicador EVAL_CONOCIMIENTOS, ciclo_id, pais_codigo)`, resolviendo
   `linea_id`/`gerente_id`/`mes_id` desde `DIM_RM`.
6. Disparar recálculo → el motor aplica `DIM_IndicadorTabla` (factor) → `puntos` → IUP/ranking.
   **No se recalcula el factor en Python** (única fuente de verdad).

**Seed de parametrización** (migración): cargar en `Config.DIM_IndicadorTabla` para
`EVAL_CONOCIMIENTOS` (indicador_id=7, país DO) los rangos en **escala 0–10**:

| rango_desde | rango_hasta | puntos (factor) |
|---|---|---|
| 0 | 7.999… | 0 |
| 8.0 | 8.099… | 0.80 |
| 8.1 | 8.199… | 0.81 |
| … | … | … |
| 9.9 | 9.999… | 0.99 |
| 10 | 10 | 1.00 |

(El SP usa `escala=100` → toma el valor tal cual, sin ×100; los rangos 0–10 calzan con
`nota`. Verificar en implementación cómo el SP escala la columna `puntos` por `ponderacion`.)

**Nota:** hoy `EVAL_CONOCIMIENTOS` se cargaría por Excel (`KPI_RM`); el módulo de exámenes
se vuelve una **fuente alternativa** del mismo `valor_real`. No agrega tubería nueva.

---

## 8. KPIs (§9 del prompt)

Calculados en `examen_correccion_service` y expuestos vía endpoints + vistas:
- Promedio del equipo (por examen), % aprobación, completitud.
- Score individual (último intento), ranking (último intento, RN-09).
- % error por pregunta (sobre **todos** los intentos, RN-08).
- Evolución por visitador, promedio histórico por visitador.

---

## 9. Seguridad y auditoría (§16)

Auth obligatoria; RBAC por rol; evaluado solo ve lo suyo; GD solo su equipo;
Capacitación ve todo. Auditar: creación, publicación, asignación, inicio de intento,
entrega, cambios de preguntas, generación IA. Guardar `user_agent`/`device_type`/`plataforma`
en el intento. Anti-doble-entrega; validación de `fecha_limite` e `intentos_max`. Archivo
fuente IA con nombre UUID (patrón seguro del ETL), nunca visible al evaluado (RN-10).

---

## 10. Vistas SQL (§17)

Creadas en la migración: `exam.vwDashboardCapacitacion`, `exam.vwResultadosExamen`,
`exam.vwAnalisisPregunta`, `exam.vwHistorialVisitador`.

---

## 11. Prompt base de IA

```text
Eres un experto en capacitación farmacéutica. Analiza el siguiente documento y genera
exactamente {N} preguntas de evaluación:
- {N_MULTI} de opción múltiple
- {N_CASOS} casos clínicos

Para cada pregunta devuelve JSON con este esquema:
tipo        : 'multi' | 'caso'
escenario   : string, solo para caso
texto       : string
opciones    : [string, string, string, string]  (exactamente 4)
correcta    : 0|1|2|3
explicacion : string

DOCUMENTO:
{contenido_del_archivo}
```
Regla: las preguntas de IA **siempre** se muestran a Capacitación para revisión/edición antes de guardar o publicar.

---

## 12. Pruebas (pytest, patrón `MagicMock`/`FakeQuery`)

- Corrección: `score`/`aprobado`; guard anti-doble-entrega.
- Fisher-Yates: determinismo con semilla; integridad del `mapa_opciones`.
- Fórmulas KPI.
- `validar_preguntas_generadas`: JSON IA válido/ inválido.
- `preparar_intento`: aleatorización + mapeo.
- **Puente EVAL_CONOCIMIENTOS**: promedio de varios exámenes; solo RM; guard de ciclo cerrado (no escribe).

Corren en el CI ya existente (`.github/workflows/ci.yml`).

---

## 13. Criterios de aceptación (§19 del prompt)

1. Capacitación crea examen manual.
2. Capacitación genera examen con IA y edita antes de guardar.
3. El examen se publica solo si tiene ≥1 pregunta.
4. Se asigna a evaluados (RM y Gerentes) con fecha límite e intentos máximos.
5. El examen se toma desde iPhone, Android, iPad, tablet, laptop o desktop.
6. Interfaz responsive y touch-friendly.
7. Aleatoriza preguntas y opciones si está configurado.
8. Corrige automáticamente.
9. El evaluado recibe retroalimentación inmediata.
10. El historial conserva todos los intentos.
11. El ranking usa el último intento.
12. El análisis por pregunta usa todos los intentos.
13. Capacitación y GD ven KPIs y reportes.
14. Se guarda auditoría y fuente IA.
15. No se mezclan tablas del módulo con otros — **salvo** el puente de salida EVAL_CONOCIMIENTOS (§7).
16. **(Nuevo)** La nota de un examen marcado actualiza `EVAL_CONOCIMIENTOS` del RM en el ciclo abierto, vía el motor existente.

---

## 14. Fuera de alcance (YAGNI por ahora)
- PWA completa / offline real (service worker, cola de sync).
- PDF server-side de reportes (se usa `window.print()`); ReportLab opcional a futuro.
- Exámenes con tipos de pregunta distintos a `multi`/`caso` (siempre 4 opciones, 1 correcta).
