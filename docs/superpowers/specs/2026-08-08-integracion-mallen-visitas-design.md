# Spec — Integración Mallén, sub-proyecto 3: Integración de visitas

**Fecha:** 2026-08-08
**Módulo:** Integración con Laboratorio Mallén (esquema `ext` → esquemas internos de VISTA).
**Alcance:** backend (servicio + endpoints + tests) y frontend (sección de integración + pantallas de captura en solo lectura).
**Depende de:** sub-proyecto 1 (validación de lotes) y 2 (sincronización de dimensiones), ambos completos.

---

## 1. Objetivo

Integrar los cuatro hechos de visita que Mallén deja en `ext`, **añadir el motor que calcula los cuatro indicadores de visita desde ellos** (ver §3.4), y apagar la captura manual de visitas dentro de VISTA, que deja de ser fuente de verdad.

## 2. El modelo, ya consensuado

**Mallén escribe en `ext` → VISTA lee, valida, sincroniza y calcula.** Ni Excel ni captura manual de visitas.

Los ocho indicadores quedan cubiertos así:

| # | Indicador | Fuente |
|---|---|---|
| 1 | COB_MD_F1 | `panelmedico` (denominador) + `factvisitamedico` (numerador) |
| 2 | COB_MD_F2 | igual |
| 3 | PROM_DIARIO | `factvisitamedico` + `dimciclo.dias_laborables` |
| 4 | COB_FARMACIAS | `targetfarmacia` + `factvisitafarmacia` |
| 5 | EVO_IR | `factprescripciondetalle` — *sub-proyecto 4* |
| 6 | VENTAS | `factventa` — *sub-proyecto 4* |
| 7 | EVAL_CONOCIMIENTOS | módulo de Exámenes de VISTA, captura manual por pantalla, o `factevaluacionconocimiento` — *fuera de este sub-proyecto* |
| 8 | EVAL_COACHING | `factvisitamedico.acompanado` + `gerente_codigo` — *sub-proyecto 4* |

**Este sub-proyecto cubre los indicadores 1 a 4**, es decir los cuatro que salen de las visitas.

**La solución es multipaís por diseño:** cada fila de `ext` trae su `pais_codigo` y la integración cubre todos los países por igual. No hay parametrización por país en ninguna parte de este sub-proyecto.

## 3. Mapeo de los cuatro hechos

| `ext` | Destino en VISTA | Rol |
|---|---|---|
| `panelmedico` | `Config.DIM_TargetMedico` | universo programado — denominador médico |
| `factvisitamedico` | `DW.FACT_Visita` | bitácora — numerador médico |
| `targetfarmacia` | `Visita.DIM_FarmaciaVisita` | panel de farmacias — denominador farmacia |
| `factvisitafarmacia` | `Visita.FactVisitaFarmacia` | bitácora — numerador farmacia |

Son las tablas que ya leen `cobertura_predictiva_service` y `cobertura_farmacia_service`, así que poblarlas alimenta directamente el **módulo de Cobertura Predictiva (4DX)** y sus dashboards en vivo.

**PERO eso NO alimenta los 8 indicadores del Score** — ver §3.4.

### 3.1 Resolución de referencias
Los hechos de `ext` traen códigos (`rm_codigo`, `ciclo_codigo`, `medico_codigo`, `farmacia_codigo`); los destinos internos esperan ids. Se resuelven con `integracion_mapeo.id_mapeado`, contra el mapeo que dejó el sub-proyecto 2.

Si una referencia no resuelve (la dimensión no se ha sincronizado), **la fila se omite con hallazgo `error`** indicando que hay que sincronizar dimensiones primero. No se crea la dimensión al vuelo: eso es trabajo del sub-proyecto 2 y hacerlo aquí duplicaría la lógica de adopción.

### 3.2 Idempotencia
Ni `DW.FACT_Visita` ni `Visita.FactVisitaFarmacia` tienen clave única natural: re-integrar un lote las duplicaría.

Se reutiliza `Config.MapeoExterno` con las entidades `visita_medico` y `visita_farmacia`, usando `codigo_externo = origen_id` (que el contrato garantiza único por país mediante los índices `ux_fvm_origen` / `ux_fvf_origen`). Misma pieza del sub-proyecto 2, sin tocar ninguna tabla existente.

`DIM_TargetMedico` sí tiene `UNIQUE(rm_id, ciclo_id, medico_codigo)` y `panelmedico` tiene `ux_tm_clave` equivalente, así que ahí el emparejamiento es directo por clave natural — pero igualmente se registra el mapeo, para que el conteo de "adoptados" sea comparable con el resto de la integración.

### 3.3 Reglas por destino

**`DIM_TargetMedico`** (desde `panelmedico`):
- `programado` ← `activo` de `ext`.
- `potencial` **NO se escribe** (queda como esté). Corrige un error de una versión anterior de este spec, que lo mapeaba desde `prioridad` (TOP/REGULAR): `potencial` significa **categoría A/B/C** (así lo declara el propio modelo) y el §11.5 del requerimiento advierte literalmente que *"marcar TOP no es marcar categoría A"* — son criterios ortogonales. La `prioridad` de `ext` es competencia del **sub-proyecto de Médicos TOP** (§7.3 del requerimiento), que decidirá dónde vive; aquí no se le busca acomodo forzado.
- `medico_nombre` y `especialidad` se resuelven desde `DIM_Medico` (ya sincronizado), no desde `ext`: el maestro es la fuente.
- La **frecuencia** (`F1`/`F2`) NO se guarda aquí: `DIM_TargetMedico` no tiene esa columna y no se le añade. El motor de indicadores (§3.4) la lee directamente de `ext.panelmedico`, que es donde el dato existe. Esta tabla alimenta el módulo 4DX, no el cálculo del Score.

**`DW.FACT_Visita`** (desde `factvisitamedico`):
- `estado_visita` ← `'Realizada'` si `ejecutada` es verdadero; `'Cancelada'` si no. La `causa_no_visita` de `ext` no tiene destino en esta tabla y se descarta con hallazgo `aviso` la primera vez que aparece.
- `tipo_contacto` ← `tipo_visita` (`V` = visita, `R` = revisita).
- `carga_excel_id` queda `NULL`: no viene de una carga Excel.

**`Visita.DIM_FarmaciaVisita`** (desde `targetfarmacia`):
- `estado_aprobacion` ← `'APROBADA'`. Lo que viene del SFA es maestro oficial y **no entra a la cola de aprobación VM→GD**, igual que se hizo con `DIM_Farmacia` en el sub-proyecto 2.
- `maestro_farmacia_id` se resuelve por el mapeo de la entidad `farmacia`.
- `ciclos_sin_visita` **no se toca**: lo calcula el rodaje de cierre de ciclo de VISTA.

**`Visita.FactVisitaFarmacia`** (desde `factvisitafarmacia`):
- `registrado_por` queda `NULL` (no lo registró un usuario de VISTA).
- `fecha_hora` ← `fecha_visita` a las 00:00; el contrato solo trae fecha, no hora.
- `latitud`, `longitud`, `foto` quedan nulos: el contrato no los envía.

### 3.4 El motor de cálculo de indicadores (verificado, corrige un supuesto inicial)

**Hallazgo al escribir el plan:** VISTA **no calcula** los 8 indicadores del Score. Llegan **ya calculados** en el Excel `KPI_RM` → `FACT_ResultadoIndicador.resultado_real`, y el motor solo los convierte a puntos con `DIM_IndicadorTabla`. No existe ningún servicio que derive `COB_MD_F1` de unas visitas: el nombre solo aparece en un comentario del ETL.

Como el contrato de `ext` **no tiene tabla de indicadores calculados** (Mallén envía hechos, no porcentajes), si el Excel deja de usarse alguien debe calcular esos valores. **Decisión del cliente: los calcula VISTA.**

Este sub-proyecto añade el motor de los **cuatro indicadores de visita**, que escribe en `Config.DIM_Indicador` → `DW.FACT_ResultadoIndicador` por RM y ciclo, igual que hoy hace el ETL:

| Indicador | Fórmula |
|---|---|
| `COB_MD_F1` | médicos F1 **distintos visitados** / médicos F1 en el panel × 100 |
| `COB_MD_F2` | médicos F2 **distintos visitados** / médicos F2 en el panel × 100 |
| `PROM_DIARIO` | **médicos distintos visitados** / `dias_laborables` del ciclo |
| `COB_FARMACIAS` | farmacias **distintas visitadas** / farmacias en el target × 100 |

**Definición de «cubierto»: alcance — al menos una visita ejecutada.** Un médico cuenta en el numerador cuando tiene **una o más** visitas ejecutadas en el ciclo; visitarlo más veces no lo cuenta dos veces. Lo mismo para farmacias.

**Corrección de una versión anterior de este spec**, que definía cubierto como *"cumplir las `visitas_programadas` completas"*. El **§2.1 del requerimiento v2** dice literalmente: *"calcula la cobertura dividiendo la **cantidad de médicos distintos visitados** entre la cantidad de médicos programados para cada frecuencia"*, y para el promedio diario: *"**Médicos visitados** dividido entre los días laborables del ciclo"* — no visitas. La definición anterior venía del RFI del 22-jul, que el v2 reemplazó. Como el requerimiento es el documento acordado con Mallén, **los números de VISTA deben cuadrar con los suyos**.

Consecuencia directa: `visitas_programadas` **no participa en el cálculo** y **no tiene destino interno** — `DIM_TargetMedico` no tiene esa columna y no se le añade (§Global Constraints). Queda disponible en `ext` para quien la necesite. No hay, por tanto, caso de "frecuencia no declarada" que avisar.

> **Nota abierta (no bloquea):** el §11.6 del requerimiento menciona una vez *"la cobertura completa queda en cero mientras la cobertura simple funciona"* y la liga al par `tipo_visita` V/R, sin definirla. Es la única aparición de un segundo concepto de cobertura en todo el documento. Se implementa lo que dice el §2.1, que es explícito y normativo; si Mallén confirma que además quieren la "completa", se añade como indicador aparte sin tocar estos cuatro.

**El cálculo se hace directamente sobre `ext`**, no sobre las tablas internas. Razón: `ext.panelmedico` trae `frecuencia_objetivo` (F1/F2) y `visitas_programadas`, que son justo lo que separa los dos indicadores de cobertura — y `DIM_TargetMedico` **no tiene columna de frecuencia**. Calcular desde el origen evita inventar un mapeo o alterar una tabla existente para que quepa el dato.

**Qué visitas cuentan:** solo las que tienen `ejecutada = true`. Tanto `V` (visita) como `R` (revisita) cuentan como contacto: ambas son presencia frente al médico. Las no ejecutadas se excluyen del numerador pero el médico sigue en el denominador — no visitar no reduce el universo.

**Escritura idempotente:** delete-then-insert de las filas de `FACT_ResultadoIndicador` de esos cuatro indicadores para el `(rm_id, ciclo_id)` procesado. No se tocan los otros cuatro indicadores, que siguen llegando por su vía.

**Los puntos no se calculan aquí:** se escribe `resultado_real` y el motor existente (`motor_calculo_service.completar_puntajes`) hace la conversión a puntos, igual que con los datos del Excel. Así el camino de puntuación sigue siendo uno solo.

### 3.5 Paso 3 del §7.1 — disparar el recálculo del Score

Escribir `resultado_real` **no actualiza nada visible**: el Score Integral, los rankings y los reconocimientos siguen mostrando los valores del cálculo anterior hasta que corre el motor. El §7.1 paso 3 lo exige: *"Recalcula los ocho indicadores del ciclo, **el score integral, los rankings y los reconocimientos**, con el motor que ya existe."*

Tras integrar los hechos y escribir los indicadores, el orquestador llama a `recalculo_service.recalcular_ciclo(db, ciclo_id, pais_codigo)` — el mismo servicio que dispara el ETL y el botón "Calcular IUP y Ranking". **No se escribe una línea de cálculo nueva**: se engancha el existente, que ya trae su guard de ciclo abierto.

- Se llama **después del commit** de la integración: el motor abre su propia transacción y debe ver los datos ya escritos.
- Si el ciclo está **cerrado**, `recalcular_ciclo` devuelve `abortado=true` sin escribir nada. Eso no es un error de la integración: los hechos entran (son historia), pero el Score no se recalcula. Se refleja en la respuesta y se avisa en la UI.
- El resultado del recálculo viaja en la respuesta del endpoint, para que la pantalla muestre qué pasó y no solo "integrado".

### 3.6 Paso 4 del §7.1 — cerrar el lote

Hoy **nadie escribe `INTEGRADO`**. El sub-proyecto 1 mueve los lotes a `VALIDADO`/`RECHAZADO` y ahí se quedan; el guard `LoteYaIntegrado` que se construyó protege contra un estado que nunca se alcanza. El §7.1 paso 4 pide: *"Marca el lote como INTEGRADO o RECHAZADO y deja el detalle en el campo de mensaje."*

**Reconciliación lote ↔ ciclo:** la integración trabaja por `(pais_codigo, ciclo_codigo)`, pero el estado vive en el lote. Se resuelve sin ambigüedad con el dato que ya existe: **los lotes que se cierran son exactamente los referenciados por el `lote_id` de las filas integradas** en esa corrida. Se recogen mientras se recorren los hechos; no hace falta inferir nada.

- Solo pasan a `INTEGRADO` los lotes que estaban en `VALIDADO`. Uno en `RECHAZADO` no se rescata por la puerta de atrás, y uno ya en `INTEGRADO` se deja como está (la re-ejecución es idempotente).
- `mensaje` recibe el detalle de la corrida (filas integradas y actualizadas por hecho).
- Escribir `estado`/`mensaje` **no viola la prohibición sobre `ext`**: esa prohibición es sobre el **esquema** (DDL). El propio contrato asigna esos dos campos a VISTA — el sub-proyecto 1 ya los escribe.

## 4. Apagado de la captura de visitas

El SFA de Mallén pasa a ser la fuente de verdad de las visitas. Los endpoints de captura dejan de aceptar escrituras:

| Endpoint | Módulo |
|---|---|
| `POST /visita/registrar` | Visita médica |
| `POST /visita/no-visita` | Visita médica |
| `POST /visita/{visita_id}/foto` | Visita médica |
| `POST /farmacias/{panel_id}/visita` | Farmacias |
| `POST /farmacias/{visita_id}/foto` | Farmacias |

Responden **409** con un mensaje explícito: las visitas provienen del SFA de Mallén y ya no se registran en VISTA.

**Apagado global, sin parametrización por país:** la integración cubre todos los países por igual.

**Todo lo capturado se conserva.** Las visitas, fotos y GPS históricos siguen consultables; solo se cierra la escritura.

**Lo que NO se toca:** parrilla promocional, muestras, costo y ROI, planeación, proyección, ruptura y cierre de ciclo, panel médico. El SFA no cubre esas fases y siguen funcionando igual.

## 5. Frontend

- **`RegistrarVisita.tsx`** y el registro de visita a farmacia: pasan a **solo lectura**, con un aviso visible explicando que las visitas ahora provienen del SFA de Mallén. Los controles de captura se ocultan; lo ya registrado se sigue viendo.
- **Sección "Visitas"** en `/integracion/lotes`, junto a "Dimensiones": tabla con los cuatro hechos (filas en `ext` vs. integradas), botón **"Integrar visitas"** y el reporte por hecho (integrados / actualizados / omitidos) con sus hallazgos.

## 6. API

Prefijo `/integracion` (router existente). **Roles: ADMIN y GERENTE_PRODUCTIVIDAD.**

| Método | Ruta | Descripción |
|---|---|---|
| POST | `/integracion/visitas/integrar` | `?pais_codigo&ciclo_codigo` → integra los 4 hechos |
| GET | `/integracion/visitas/resumen` | `?pais_codigo&ciclo_codigo` → filas en `ext` vs. integradas por hecho |

**Se integra por ciclo, no por lote**: los hechos de `ext` llevan `ciclo_codigo` y es la unidad natural de trabajo (un ciclo se cierra y se recalcula). El `lote_id` sirve para la trazabilidad de la recepción, no para el cálculo.

Respuesta de `POST /integrar`:
```json
{"pais_codigo": "DO", "ciclo_codigo": "C01-2026",
 "hechos": [
   {"hecho": "panelmedico", "en_ext": 480, "integrados": 12, "actualizados": 468, "omitidos": 0}
 ],
 "indicadores": {"rms": 24, "filas": 96},
 "recalculo": {"abortado": false, "filas_kpi_actualizadas": 192, "rankings_generados": 24},
 "lotes_cerrados": [1042, 1043],
 "hallazgos": [
   {"hecho": "factvisitamedico", "origen_id": "V-01923",
    "problema": "No se pudo resolver el médico «MD-999»; sincroniza dimensiones primero.",
    "severidad": "error"}
 ]}
```

`recalculo` es el dict que devuelve `recalculo_service.recalcular_ciclo` tal cual (§3.5); `lotes_cerrados` son los que pasaron a `INTEGRADO` (§3.6).

## 7. El punto de F1/F2 — RESUELTO

El spec marcó como pendiente cómo distingue VISTA `F1` de `F2`. **Verificado: no lo distingue en ninguna parte.** `cobertura_predictiva_service` menciona `frecuencia_objetivo` una sola vez, en la lectura de un Excel; ningún servicio calcula esos indicadores. Llegaban ya separados desde el archivo `KPI_RM`.

**Resolución:** el motor de §3.4 calcula ambos **directamente desde `ext.panelmedico.frecuencia_objetivo`**, que es donde el dato existe. No se añade columna a `DIM_TargetMedico` ni se reutiliza `potencial` para algo que no significa eso.

`DIM_TargetMedico` sigue recibiendo el panel (para el módulo 4DX), pero **no es la fuente del cálculo de los indicadores**.

## 8. Manejo de errores

Mismo criterio que los sub-proyectos 1 y 2: **una fila mala no detiene la integración**. Se registra un hallazgo y se sigue. Los hallazgos viajan en la respuesta del endpoint y al log, no se persisten (`Audit.IntegracionHallazgo` exige `lote_id` y aquí se trabaja por ciclo).

Un solo commit al final: o entra el conjunto coherente o no entra nada.

## 9. Fuera de alcance (YAGNI)

- Indicadores 5, 6 y 8 (ventas, prescripciones, coaching): **sub-proyecto 4**.
- Indicador 7 y la pantalla de captura manual de notas: sub-proyecto propio.
- **Médicos TOP** (§3.4, §7.3 y §11.5 del requerimiento): sub-proyecto propio, inmediatamente después de este. Son tres reglas de negocio — no publicar una planeación que omita un TOP, marcar los TOP sin visita y sin revisita, y recordatorio al RM con escalamiento al GD. Aquí solo se establece lo que las habilita: **no se quema `prioridad` dentro de `potencial`** (§3.3), para que ese sub-proyecto pueda modelarla bien.
- Automatizar el disparo de la integración: sub-proyecto 5. Aquí es un botón.
- Desmantelar o vaciar el módulo de Visita: solo se cierra la escritura de visitas; el resto de fases y todos los datos históricos se conservan.
- Tocar `cobertura_predictiva_service` o `cobertura_farmacia_service`: los cálculos ya leen las tablas destino.
- Tocar el esquema `ext` de cualquier forma.

## 10. Verificación

**Backend** — tests en `backend/tests/test_integracion_visitas.py`, patrón PostgreSQL real:
1. Un `panelmedico` con sus dimensiones sincronizadas → crea `DIM_TargetMedico` con `programado` correcto y **`potencial` en nulo** (la prioridad TOP no se quema ahí).
2. Un `factvisitamedico` ejecutado → crea `DW.FACT_Visita` con `estado_visita='Realizada'` y `tipo_contacto` correcto.
3. Un `factvisitamedico` no ejecutado → `estado_visita='Cancelada'`.
4. **Re-integrar el mismo ciclo no duplica** (ni visitas ni targets).
5. Una visita cuyo `medico_codigo` no está sincronizado → se omite con hallazgo `error`, y el resto del lote sí entra.
6. Un `targetfarmacia` → crea `DIM_FarmaciaVisita` con `estado_aprobacion='APROBADA'`.
7. Un `factvisitafarmacia` → crea `FactVisitaFarmacia` con `registrado_por=NULL`.
8. **Los endpoints de captura responden 409** (uno por cada uno de los cinco).
9. Tras integrar, `cobertura_predictiva_service` devuelve cobertura distinta de cero para ese ciclo — la prueba de que el circuito 4DX funciona.

**Motor de indicadores (§3.4):**
10. Un RM con 2 médicos F1, uno visitado **3 veces** y otro **ninguna** → `COB_MD_F1 = 50`. Es el caso que fija «distintos visitados»: las 3 visitas al mismo médico cuentan **una sola vez**, así que repetir no infla la cobertura.
11. Los médicos F2 del mismo RM no afectan a `COB_MD_F1` y viceversa.
12. `PROM_DIARIO` = **médicos distintos** visitados / `dias_laborables`. Con 1 médico visitado 3 veces en un ciclo de 20 días → `0.05`, no `0.15`. Es el caso que distingue médicos de visitas.
13. Una visita con `ejecutada = false` no cuenta en el numerador, pero su médico **sí sigue** en el denominador de cobertura.
14. Recalcular el mismo ciclo **no duplica** filas en `FACT_ResultadoIndicador` (delete-then-insert), y **no toca** los otros cuatro indicadores del ciclo.
15. Se escribe `resultado_real` y NO `puntos_obtenidos`: la conversión a puntos sigue siendo del motor existente.

**Recálculo y cierre de lote (§3.5, §3.6):**
16. Integrar un ciclo **abierto** deja el Score y el ranking actualizados: `FACT_ScoreIntegralRM` y `FACT_RankingRM` tienen filas del ciclo que antes no existían.
17. Integrar un ciclo **cerrado**: los hechos entran, el recálculo devuelve `abortado=true` y ninguna FACT calculada cambia.
18. Un lote en `VALIDADO` cuyas filas se integran → queda `INTEGRADO` con el detalle en `mensaje`.
19. Un lote en `RECHAZADO` **no** pasa a `INTEGRADO` aunque alguna de sus filas se recorra.
20. Re-integrar el mismo ciclo con el lote ya en `INTEGRADO` no falla ni revierte el estado.

**Frontend** — `npm run build` + smoke: sembrar hechos en `ext`, integrar, ver los conteos, y comprobar que la pantalla de registro está en solo lectura con su aviso.
