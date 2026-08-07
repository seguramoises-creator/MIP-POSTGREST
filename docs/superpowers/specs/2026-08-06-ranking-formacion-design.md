# Spec — Ranking de Formación (Fase 6 · §8)

**Fecha:** 2026-08-06
**Módulo:** Formación ampliada — Fase 6, la última pieza sin construir del módulo.
**Alcance:** backend (servicio + router + tests) y frontend (service + página). **Sin migración.**
**Origen:** auditoría de ago-2026. `formacion.RankingFormacionPuntos` está migrada desde la Fase 1 pero **nunca tuvo un solo INSERT ni SELECT**: es una tabla fantasma. El §8.2 ("lo que este módulo aporta al Ranking gamificado") no llega a ningún lado; lo único existente es `puntos_de_refuerzo()`, un cálculo al vuelo del componente de refuerzo para `/mis-puntos`.

---

## 1. Objetivo

Dar vida al Ranking de Formación: calcular y persistir los puntos de cada RM por ciclo a partir de sus 4 fuentes (certificaciones, exámenes, refuerzo y onboarding), llevar la racha de constancia, y mostrarlo en una pantalla con podio y desglose.

## 2. Decisiones tomadas (por el usuario)

1. **Es un ranking propio del módulo, NO entra al Score Integral.** `motor_calculo_service.py` **no se toca**. El Score Integral, los rankings oficiales, los premios y la elegibilidad quedan exactamente igual. Este ranking es motivacional (§8) y aditivo puro: no puede alterar ningún número de negocio existente.
2. **La racha cuenta ciclos consecutivos con actividad de formación** (al menos 1 punto en el ciclo).

## 3. Modelo (ya existente, no se toca)

`formacion.RankingFormacionPuntos` — `UNIQUE(rm_id, ciclo_id)`:
`rm_id`, `ciclo_id`, `puntos_certificacion`, `puntos_examenes`, `puntos_refuerzo`, `puntos_onboarding`, `puntos_total`, `racha_ciclos`, `actualizado_en`.

Los cuatro componentes se guardan por separado a propósito (lo documenta el propio modelo): el RM debe poder ver **de dónde sale** su posición, no solo el total.

`formacion.ParametroFormacion` (`pais_codigo`, `clave`, `valor` Numeric(10,4)) se reutiliza para los pesos configurables — es genérico, así que **no hace falta migración**.

## 4. Cálculo de los puntos

Todo se calcula **por (rm_id, ciclo_id)**. El ciclo aporta `fecha_inicio` y `fecha_fin` (`Config.DIM_Ciclo`), necesarios porque dos fuentes no guardan `ciclo_id`.

### 4.1 Pesos configurables

Claves en `ParametroFormacion`, con estos valores por defecto:

| Clave | Defecto | Significado |
|---|---|---|
| `ranking_puntos_certificacion` | 50 | Puntos por certificación aprobada en el ciclo |
| `ranking_puntos_examen` | 30 | Puntos por examen aprobado en el ciclo |
| `ranking_puntos_paso_onboarding` | 5 | Puntos por paso de la ruta completado en el ciclo |
| `ranking_bono_ruta_completa` | 25 | Bono único al completar la ruta dentro del ciclo |

El componente de **Refuerzo no tiene peso propio**: sus puntos ya vienen calculados por `RefuerzoRespuesta.puntos_obtenidos` (10 base × % de participación, §10.6) y se suman tal cual. Introducir un multiplicador encima haría irreproducible el número que el RM ya ve en su tab de cápsulas.

Se sigue el patrón de `formacion_brechas_service`: `PESOS_DEFECTO` como dict, función `pesos(db, pais_codigo)` que superpone lo que haya en `ParametroFormacion`, y `fijar_peso(db, pais_codigo, clave, valor)` que **rechaza claves desconocidas**.

### 4.2 Los cuatro componentes

- **Certificación** — `DW.FACT_Capacitacion` con `ciclo_id` del ciclo, `rm_id` del RM, `aprobado = True`, unida a `Config.DIM_Capacitacion` filtrando `tipo = 'CERTIFICACION'`. Cuenta × `ranking_puntos_certificacion`.
- **Exámenes** — `exam.IntentoExamen` con `evaluado_rm_id = rm_id`, `aprobado = True`, y `fecha_fin` **dentro del rango del ciclo** (`fecha_inicio ≤ fecha_fin::date ≤ fecha_fin` del ciclo). Cuenta × `ranking_puntos_examen`. Se usa `fecha_fin` (cuándo terminó el intento) y no `fecha_inicio`, porque el mérito es haberlo aprobado. Los intentos sin `fecha_fin` (abandonados) no cuentan.
- **Refuerzo** — suma de `RefuerzoRespuesta.puntos_obtenidos` del RM, restringida a respuestas cuya campaña (`RefuerzoRondaProgramada` → `RefuerzoCampana`) tenga `ciclo_id` igual al ciclo. Las campañas **sin `ciclo_id`** (la columna es nullable) no se atribuyen a ningún ciclo y por tanto no suman: es preferible a repartirlas por fecha y contarlas dos veces.
- **Onboarding** — `OnboardingPasoProgreso` del RM (vía `OnboardingAsignacion`) con `completado = True` y `completado_en` dentro del rango del ciclo. Cuenta × `ranking_puntos_paso_onboarding`. Si además la asignación tiene `completada_en` dentro del ciclo, se suma una vez `ranking_bono_ruta_completa`.

**`puntos_total`** = suma de los cuatro. **La racha no multiplica nada** (ver §4.3).

### 4.3 Racha

`racha_ciclos` = número de ciclos **consecutivos hacia atrás**, terminando en el ciclo calculado, en los que el RM tuvo `puntos_total > 0`. El ciclo actual cuenta como 1 si tiene puntos; si no tiene, la racha es 0.

La consecutividad se resuelve ordenando los ciclos del **mismo país** por `(anio, numero)` descendente y recorriéndolos hasta encontrar el primero sin puntos.

**La racha se registra y se muestra, pero no altera `puntos_total`.** Un multiplicador haría que el número dejara de ser explicable ("estos 145 puntos salen de aquí") y se volviera un compuesto que el RM no puede reproducir — justo lo contrario de lo que busca el §8.2 al guardar los componentes por separado.

### 4.4 Recálculo

`recalcular_ciclo(db, ciclo_id, pais_codigo)`:
1. Toma todos los RM activos del país (`Config.DIM_RM`).
2. Calcula los 4 componentes de cada uno.
3. **Delete-then-insert** de `RankingFormacionPuntos` para ese `ciclo_id` y esos RM — mismo criterio que el motor de ranking real, y lo que hace que re-ejecutar sea seguro.
4. Calcula la racha de cada RM **después** de persistir el ciclo actual (la racha lee los ciclos previos ya persistidos).
5. Devuelve `{ciclo_id, rms_procesados, puntos_totales}`.

Es **re-ejecutable**: correrlo dos veces da el mismo resultado.

**No hay guard de ciclo cerrado.** A diferencia del motor de Score, aquí recalcular no altera premios ni comisiones; y poder recomputar un ciclo cerrado es útil si se cargan certificaciones con retraso. Queda registrado en el docstring para que no se confunda con una omisión.

## 5. API

Prefijo `/formacion/ranking`.

| Método | Ruta | Roles | Descripción |
|---|---|---|---|
| POST | `/recalcular` | ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION | `?ciclo_id&pais_codigo` → recalcula y persiste |
| GET | `` | autenticado (con auto-scope) | `?ciclo_id&pais_codigo` → ranking ordenado |
| GET | `/mis-puntos` | autenticado con `rm_id` | `?ciclo_id` → desglose propio + racha |
| GET | `/pesos` | autenticado | `?pais_codigo` → pesos vigentes |
| PUT | `/pesos` | ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION | `{pais_codigo, clave, valor}` |

**Auto-scope de `GET /formacion/ranking`** (mismo criterio que el KPI de Refuerzo, §11.5):
- ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION, PRESIDENCIA, GERENTE_MEDICO → ven todo el país.
- GERENTE_DISTRITO → solo su equipo (`Usuario.gerente_id`).
- REPRESENTANTE_MEDICO → **ve el ranking completo del país** (es un ranking público: el podio pierde sentido si cada quien solo se ve a sí mismo), pero `/mis-puntos` sigue siendo estrictamente propio.

Respuesta de `GET /formacion/ranking`:
```json
[{"posicion": 1, "rm_id": 12, "rm_nombre": "…", "puntos_total": 145,
  "puntos_certificacion": 50, "puntos_examenes": 30,
  "puntos_refuerzo": 40, "puntos_onboarding": 25, "racha_ciclos": 3}]
```
Ordenado por `puntos_total` desc; empates por `rm_id` asc para que el orden sea estable entre llamadas. `posicion` se calcula al leer (no se persiste): así un recálculo de otro RM no obliga a reescribir filas ajenas.

`rm_nombre` sale de `Config.DIM_RM.nombre` con un join — el ranking sin nombres es inútil en pantalla.

## 6. Frontend

Página propia `frontend/src/pages/formacion/RankingFormacion.tsx`, ruta `/formacion/ranking`, ítem de Sidebar en el grupo de Formación. Service `frontend/src/services/rankingFormacion.service.ts`.

Visible para: ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION, PRESIDENCIA, GERENTE_MEDICO, GERENTE_DISTRITO, REPRESENTANTE_MEDICO.

- **Tarjeta "Mis puntos"** (solo si el usuario tiene `rm_id`): total, los 4 componentes desglosados y la racha como distintivo ("🔥 3 ciclos seguidos"). Si el endpoint da 403 (usuario sin representante enlazado), la tarjeta simplemente no se muestra — no es un error que deba interrumpir la pantalla.
- **Podio** de los 3 primeros del ciclo.
- **Tabla completa**: posición, RM, los 4 componentes, total y racha.
- **Botón "Recalcular"** (solo roles de Capacitación) con aviso del resultado.
- **Diálogo de pesos** (solo roles de Capacitación): los 4 valores editables, con el mensaje real del backend si se rechaza una clave.
- País y ciclo salen del contexto global (`useCicloStore`: `paisCodigo`, `cicloId`). Sin ellos, aviso y query deshabilitada.
- Estado vacío: "Este ciclo aún no tiene puntos calculados. Pulsa «Recalcular»." (para quien pueda recalcular) o el mensaje sin la instrucción (para quien no).

## 7. Fuera de alcance (YAGNI)

- Tocar `motor_calculo_service.py` o cualquier cálculo del Score Integral / ranking oficial.
- Recálculo automático disparado por ETL o por scheduler: se dispara a mano desde la pantalla. (Follow-up natural si se quiere automatizar.)
- Insignias, niveles o premios asociados al ranking.
- Histórico multi-ciclo en la UI (la racha ya resume la constancia).
- Migración: `RankingFormacionPuntos` y `ParametroFormacion` ya existen.

## 8. Verificación

**Backend** — tests nuevos en `backend/tests/test_formacion_ranking.py`, siguiendo el patrón PostgreSQL real del módulo (se saltan si no hay base):
1. Cada componente suma lo que debe: un escenario con 1 certificación aprobada, 1 examen aprobado dentro del ciclo, respuestas de refuerzo y pasos de onboarding completados → verifica los 4 valores y el total.
2. **Un examen aprobado FUERA del rango del ciclo no suma** (prueba la atribución por fecha).
3. **Una campaña de refuerzo sin `ciclo_id` no suma.**
4. **Re-ejecutar `recalcular_ciclo` da el mismo resultado** (no duplica ni acumula).
5. **La racha cuenta ciclos consecutivos** y se corta al primer ciclo sin puntos.
6. Los pesos configurados en `ParametroFormacion` **sobrescriben** los de defecto.

**Frontend** — `npm run build` + smoke en vivo: recalcular, ver el podio, comprobar que "Mis puntos" cuadra con la fila del RM en la tabla, y que un GD solo ve su equipo.
