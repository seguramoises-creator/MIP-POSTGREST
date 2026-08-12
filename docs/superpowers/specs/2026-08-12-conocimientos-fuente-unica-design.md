# Fuente única de `EVAL_CONOCIMIENTOS` — Diseño

**Fecha:** 2026-08-12
**Sub-proyecto:** 7 de la integración VISTA ↔ Laboratorio Mallén
**Estado:** aprobado, pendiente de plan

## 1. Por qué existe

El §7.2 del requerimiento encarga a VISTA el módulo **Conocimientos**: *"lectura de notas externas, solo si Laboratorio Mallén elige esa vía"*, sustituyendo al módulo de exámenes. La elección es el **pendiente 2 del §10**, todavía abierto y a cargo de Mallén.

Pero hay un problema que no depende de esa respuesta y que ya existe hoy: **tres caminos escriben el mismo indicador, y el último en correr gana sin dejar rastro.**

| Camino | Cómo escribe | Estado hoy |
|---|---|---|
| Excel del ETL (`KPI_RM`) | `etl_service`, los 8 indicadores de golpe | **De aquí vienen las 176 filas actuales** |
| Exámenes de VISTA | `examen_consolidacion_service` → `examen_kpi_service.upsert_nota_rm` | Nunca ha consolidado en producción (`exam.FactConsolidacionCiclo` vacía) |
| Notas de Mallén | no existe | — |

Los tres hacen **delete-then-insert** sobre `(rm_id, indicador_id, ciclo_id)`. No hay error, no hay aviso: solo un número distinto según el orden en que alguien pulse los botones. Este sub-proyecto convierte esa carrera en una decisión declarada.

`EVAL_CONOCIMIENTOS` en producción: `escala = 100`, `ponderacion_pct = 10`, `tipo_periodo = CICLO`, 176 filas entre 0 y 100. La nota va **0-100 directa** — no hay conversión de unidad, a diferencia de `VENTAS`.

## 2. El dueño, por país

Tabla nueva `Config.FuenteIndicador`: `(pais_codigo, indicador_codigo)` único → `fuente`, más `actualizado_en` y `actualizado_por_usuario_id`. Tres valores:

| Fuente | Quién produce la nota | Cómo llega al ciclo |
|---|---|---|
| `EXAMEN_VISTA` | El módulo de Exámenes | Capacitación consolida el (ciclo, país) |
| `NOTA_EXTERNA` | Mallén, llenando `ext.factevaluacionconocimiento` | El integrador de este sub-proyecto |
| `CAPTURA_MANUAL` | El responsable, tecleando las notas | Botón "Integrar al ciclo" de la pantalla de captura |

Es **por país y no por ciclo** porque la decisión del pendiente 2 es una política que Mallén toma una vez; no alterna entre ciclos. La tabla admite otros indicadores, pero **solo se usa para `EVAL_CONOCIMIENTOS`**: generalizarla ahora sería especular.

La migración **siembra cada país existente en `CAPTURA_MANUAL`**, que es el equivalente más cercano a lo que hace el Excel hoy. Las 176 filas actuales no se tocan: el dueño gobierna las escrituras futuras, no reescribe el pasado.

Un servicio `fuente_indicador_service` concentra la regla en un solo sitio — `fuente_de(db, pais_codigo, indicador_codigo)` y `asegurar_duenio(...)`, que levanta `FuenteAjenaError`. Repartir la comprobación por los tres caminos es cómo se vuelven a desincronizar.

## 3. El Excel sale de este proceso, para siempre

**Decisión del cliente (12-ago-2026): "nunca más Excel para este proceso".**

`EXCEL` no es uno de los tres valores de `fuente`, y no lo es a propósito: no es que hoy no sea el dueño, es que deja de ser una vía. La carga `KPI_RM` **omite siempre** las filas de `EVAL_CONOCIMIENTOS` y lo reporta en el resumen, apuntando a la pantalla de captura.

No falla el archivo entero por esas filas — mismo criterio que el resto del sistema con una fila que no aplica, y el mismo archivo trae los otros siete indicadores, que siguen cargando con normalidad.

El razonamiento: si la nota la teclea una persona, que la teclee dentro del sistema, con validación, dueño declarado y auditoría. Una hoja de cálculo no deja rastro de quién puso qué número ni cuándo.

## 4. La pantalla de captura

Sustituye al Excel para este indicador. Roles: **ADMIN, GERENTE_PRODUCTIVIDAD y CAPACITACION**.

Tabla propia `DW.FACT_NotaConocimiento`: `(pais_codigo, ciclo_id, rm_id, fecha_evaluacion, nota, tema, capturado_por_usuario_id, capturado_en)`, con `nota` entre 0 y 100 validada en el servicio, no solo en el formulario.

**Por qué una tabla intermedia y no escribir directo al indicador:** es lo que hace que las tres fuentes se comporten igual. Las tres **capturan primero y se integran después**, en un paso explícito — el examen tiene intentos → consolidación, Mallén tiene `ext` → integración, y la captura tiene su tabla → "Integrar al ciclo". De ahí salen tres propiedades que escribir directo no da: la nota se corrige antes de entrar, queda auditada con autor y fecha, y el reproceso es idempotente.

La pantalla lista los RM del ciclo en curso, muestra **cuáles ya tienen nota y cuáles faltan**, permite editar mientras el ciclo no se haya integrado, y tiene el botón que integra. Eso es *"todo lo necesario para integrarlo al ciclo"*: sin la lista de faltantes, el responsable no sabe cuándo terminó.

**Un RM puede tener varias notas en un ciclo** — temas o fechas distintas —, igual que en `ext` y que en los exámenes; por eso se promedian (§5), y "tiene nota" significa "tiene al menos una". La tabla **no lleva UNIQUE** por esa razón.

Eso obliga a una precaución explícita, porque una tabla sin UNIQUE cuyos valores se agregan es justo donde este proyecto ya se quemó una vez: **corregir una nota EDITA la fila existente, nunca añade otra.** Si corregir insertara, la nota vieja seguiría entrando al promedio y el número saldría mal sin que nada lo delatara. La pantalla trabaja siempre contra el `id` de la fila, y capturar una nota adicional para el mismo RM es una acción distinta y visible, no el efecto colateral de guardar dos veces.

## 5. Las tres puertas

Cada camino pregunta primero quién es el dueño y **se niega con un mensaje que nombra al dueño real**, en vez de pisar en silencio:

| Camino | Exige | Si no es el dueño |
|---|---|---|
| `examen_consolidacion_service.consolidar_ciclo` | `EXAMEN_VISTA` | 409 nombrando la fuente vigente |
| `integrar_conocimientos` (Mallén) | `NOTA_EXTERNA` | omite con `Hallazgo` de error |
| "Integrar al ciclo" (captura) | `CAPTURA_MANUAL` | 409 nombrando la fuente vigente |
| ETL `KPI_RM` | — | omite siempre las filas del indicador (§3) |

Los tres escriben igual, y ese "igual" es parte del diseño: **promedio de las notas del RM en el ciclo** → `FACT_ResultadoIndicador`, `resultado_real` 0-100 directo, guard de ciclo cerrado **antes** de cualquier borrado, y delete-then-insert acotado a `(rm_id, indicador_id, ciclo_id)`.

El promedio, y no la última nota, por coherencia con `examen_kpi_service._nota_promedio_rm`, que ya promedia. Un RM sin ninguna nota **no genera fila** — misma regla que la cuota nula en `VENTAS`: ausencia de dato no es un cero.

El guard de ciclo cerrado antes del borrado no es una precaución genérica: un delete-then-insert que luego aborta borra `puntos_obtenidos` para siempre, y ya ocurrió una vez en este proyecto.

## 6. El integrador de Mallén

Espejo de `VENTAS`. `ext.factevaluacionconocimiento` trae `(pais_codigo, ciclo_codigo, rm_codigo, fecha_evaluacion, nota, tema)` con `ux_fec_origen` único por `(pais_codigo, origen_id)`, así que un RM puede traer varias notas de temas o fechas distintas: se promedian.

Respeta lo ya establecido en `integracion_indicadores_service`: gate de estado del lote (solo filas de lotes `VALIDADO`/`INTEGRADO`), hallazgos por RM o ciclo sin mapeo, y el guard de ciclo cerrado. Reutiliza `integracion_mapeo.id_mapeado` para resolver `ENT_REPRESENTANTE` y `ENT_CICLO` — no vuelve a consultar `Config` por su cuenta.

## 7. Fuera de alcance (YAGNI)

- **Generalizar el dueño a otros indicadores.** La tabla lo admite; solo se usa para este.
- **Migrar o reescribir las 176 filas históricas.**
- **Cambiar el módulo de Exámenes** más allá de añadirle su puerta.
- **Un flujo de aprobación de las notas capturadas.** El responsable captura e integra; si más adelante hace falta que alguien revise, es otro sub-proyecto.
- **Tocar `motor_calculo_service`, `recalculo_service`, `cobertura_predictiva_service`, `cobertura_farmacia_service`, `visita_costo_service`** ni el esquema `ext`.

## 8. Verificación

**El dueño**
1. Un país sin fila en `FuenteIndicador` responde `CAPTURA_MANUAL` (el default de la semilla), no un error.
2. Cambiar el dueño queda registrado con usuario y fecha.
3. `fuente` solo admite los tres valores; cualquier otro se rechaza.

**Las puertas**
4. Con dueño `CAPTURA_MANUAL`, consolidar exámenes da 409 y **no escribe ninguna fila** en `FACT_ResultadoIndicador`.
5. Con dueño `EXAMEN_VISTA`, el integrador de Mallén omite y emite hallazgo de error, sin escribir.
6. Con dueño `NOTA_EXTERNA`, "Integrar al ciclo" de la captura da 409 sin escribir.
7. Cada camino escribe cuando SÍ es el dueño. Es el test que impide que una puerta quede cerrada para todos.
8. Una carga `KPI_RM` con filas de `EVAL_CONOCIMIENTOS` **omite esas filas, carga las demás** y lo reporta. Con cualquiera de los tres dueños: el Excel nunca escribe este indicador.

**El cálculo, en los tres caminos**
9. Dos notas del mismo RM en el ciclo → se escribe el promedio.
10. Un RM sin notas → no se escribe fila (no se escribe 0).
11. `resultado_real` queda 0-100; tras `completar_puntajes`, una nota de 80 con ponderación 10 da 8 puntos. **Atraviesa el motor**: afirmar solo sobre `resultado_real` es comparar el valor consigo mismo.
12. Ciclo cerrado → ninguno de los tres escribe ni borra nada.
13. Reintegrar el mismo ciclo no duplica ni dobla.

**La captura**
14. Una nota fuera de 0-100 se rechaza en el servicio, no solo en el formulario.
15. La pantalla distingue los RM del ciclo con nota de los que faltan.
16. Editar una nota antes de integrar cambia lo que se integra; el registro conserva autor y fecha.
17. **Corregir una nota deja UNA fila, no dos**, y el promedio integrado usa el valor corregido. Es el test que impide que una corrección se convierta en una nota extra que arrastra el promedio hacia el valor equivocado.
18. Capturar deliberadamente una segunda nota del mismo RM (otro tema) SÍ crea una fila más, y el promedio pasa a considerar las dos. Junto con el 17, fija dónde está la frontera entre corregir y añadir.

**Lo que las tres escrituras deben rellenar**
19. La fila de `FACT_ResultadoIndicador` que escribe cada camino trae `pais_codigo`, `linea_id` y `gerente_id` tomados del RM — son `NOT NULL` y no vienen en la nota.
