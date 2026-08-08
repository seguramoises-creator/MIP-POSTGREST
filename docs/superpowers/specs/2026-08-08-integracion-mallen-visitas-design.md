# Spec — Integración Mallén, sub-proyecto 3: Integración de visitas

**Fecha:** 2026-08-08
**Módulo:** Integración con Laboratorio Mallén (esquema `ext` → esquemas internos de VISTA).
**Alcance:** backend (servicio + endpoints + tests) y frontend (sección de integración + pantallas de captura en solo lectura).
**Depende de:** sub-proyecto 1 (validación de lotes) y 2 (sincronización de dimensiones), ambos completos.

---

## 1. Objetivo

Integrar los cuatro hechos de visita que Mallén deja en `ext` a los destinos internos de VISTA, de modo que **los indicadores se calculen con datos del SFA de Mallén**, y apagar la captura manual de visitas dentro de VISTA, que deja de ser fuente de verdad.

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

Son exactamente las tablas que ya leen `cobertura_predictiva_service` y `cobertura_farmacia_service`, así que **no hay que tocar ningún motor de cálculo**: al poblarlas con datos de Mallén, los indicadores pasan a calcularse sobre ellos.

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
- `potencial` ← `prioridad` (TOP/REGULAR) — es el campo que `ext` usa para segmentar.
- `medico_nombre` y `especialidad` se resuelven desde `DIM_Medico` (ya sincronizado), no desde `ext`: el maestro es la fuente.
- La **frecuencia** (`F1`/`F2`) determina a qué indicador cuenta cada médico. `DIM_TargetMedico` no tiene columna de frecuencia; se conserva en el mapeo del hecho para que el cálculo pueda distinguirlos. *(Ver §7: punto que requiere verificación contra el motor de cobertura antes de implementar.)*

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
 "hallazgos": [
   {"hecho": "factvisitamedico", "origen_id": "V-01923",
    "problema": "No se pudo resolver el médico «MD-999»; sincroniza dimensiones primero.",
    "severidad": "error"}
 ]}
```

## 7. Punto que requiere verificación antes de implementar

`ext.panelmedico.frecuencia_objetivo` (`F1`/`F2`) es lo que separa COB_MD_F1 de COB_MD_F2, pero **`DIM_TargetMedico` no tiene una columna de frecuencia**. Antes de escribir el plan hay que leer `cobertura_predictiva_service` y determinar **cómo distingue hoy VISTA F1 de F2**:

- Si lo hace por un campo existente (p. ej. `potencial`), se mapea ahí y se documenta.
- Si lo hace por parámetros de `DIM_ParametroCobertura`, hay que ver cómo encaja la frecuencia que envía Mallén.
- Si hoy no lo distingue, **es un hueco real** y hay que decidir explícitamente con el cliente antes de construir, no inventar un mapeo.

Este punto se resuelve al escribir el plan; el spec lo deja marcado a propósito en vez de suponer.

## 8. Manejo de errores

Mismo criterio que los sub-proyectos 1 y 2: **una fila mala no detiene la integración**. Se registra un hallazgo y se sigue. Los hallazgos viajan en la respuesta del endpoint y al log, no se persisten (`Audit.IntegracionHallazgo` exige `lote_id` y aquí se trabaja por ciclo).

Un solo commit al final: o entra el conjunto coherente o no entra nada.

## 9. Fuera de alcance (YAGNI)

- Indicadores 5, 6 y 8 (ventas, prescripciones, coaching): **sub-proyecto 4**.
- Indicador 7 y la pantalla de captura manual de notas: sub-proyecto propio.
- Automatizar el disparo de la integración: sub-proyecto 5. Aquí es un botón.
- Desmantelar o vaciar el módulo de Visita: solo se cierra la escritura de visitas; el resto de fases y todos los datos históricos se conservan.
- Tocar `cobertura_predictiva_service` o `cobertura_farmacia_service`: los cálculos ya leen las tablas destino.
- Tocar el esquema `ext` de cualquier forma.

## 10. Verificación

**Backend** — tests en `backend/tests/test_integracion_visitas.py`, patrón PostgreSQL real:
1. Un `panelmedico` con sus dimensiones sincronizadas → crea `DIM_TargetMedico` con `programado` y `potencial` correctos.
2. Un `factvisitamedico` ejecutado → crea `DW.FACT_Visita` con `estado_visita='Realizada'` y `tipo_contacto` correcto.
3. Un `factvisitamedico` no ejecutado → `estado_visita='Cancelada'`.
4. **Re-integrar el mismo ciclo no duplica** (ni visitas ni targets).
5. Una visita cuyo `medico_codigo` no está sincronizado → se omite con hallazgo `error`, y el resto del lote sí entra.
6. Un `targetfarmacia` → crea `DIM_FarmaciaVisita` con `estado_aprobacion='APROBADA'`.
7. Un `factvisitafarmacia` → crea `FactVisitaFarmacia` con `registrado_por=NULL`.
8. **Los endpoints de captura responden 409** (uno por cada uno de los cinco).
9. Tras integrar, `cobertura_predictiva_service` devuelve cobertura distinta de cero para ese ciclo — la prueba de que el circuito completo funciona.

**Frontend** — `npm run build` + smoke: sembrar hechos en `ext`, integrar, ver los conteos, y comprobar que la pantalla de registro está en solo lectura con su aviso.
