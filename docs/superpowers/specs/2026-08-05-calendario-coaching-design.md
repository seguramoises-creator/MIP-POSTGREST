# Fase 4 — Calendario de Coaching (§7) — Diseño

Fecha: 2026-08-05 · Módulo: Ampliación del Módulo de Formación (MSM-postgres).
Plan padre: `docs/superpowers/plans/2026-07-29-formacion-ampliada.md`.

## 1. Decisión que desbloquea esta fase (punto abierto 8)

El requerimiento (§6) asumía que "Competencia" era un **eje nuevo** de la Matriz
LSII. No lo es: el eje Y (`FACT_EvaluacionReceptividad.score_desempeno`) ya existe
y se alimenta del score del ranking.

**Decisión del cliente (ago-2026):**
1. La Matriz LSII **no se toca** — conserva su cálculo actual. → La **Fase 3 se
   descarta** (no se redefine el eje Y).
2. El Calendario de Coaching **consume el cuadrante LSII vigente** que ya produce
   el módulo LSII. → Esta **Fase 4 se desbloquea**.
3. El cálculo de la matriz queda **desligado del módulo de Formación**: Formación
   *lee* el resultado de LSII, no lo produce ni lo altera.

Consecuencia de diseño: este módulo tiene **cero acoplamiento de escritura** con
LSII. Solo hace `SELECT` sobre `FACT_EvaluacionReceptividad`.

## 2. Propósito

Generar, **por Gerente de Distrito (GD) y ciclo**, un calendario **sugerido** de
acompañamientos: a cada RM del equipo se le asignan tantas visitas de coaching
como indica su cuadrante LSII, repartidas a lo largo del ciclo. El GD revisa,
edita y publica.

Es **planeación**, no ejecución: el registro real del coaching sigue en el módulo
**Coaching MORE** (esquema `coaching`). Este módulo no crea sesiones de coaching
ni las califica; solo sugiere cuándo deberían ocurrir.

## 3. Modelo de datos — YA EXISTE (sin migración)

La Fase 1 (`0031_formacion_ampliada`) ya creó ambas tablas. **No hay cambio de
esquema en esta fase.**

- `formacion.ParametroFrecuenciaLSII` — `(pais_codigo, cuadrante D1..D4) →
  visitas_por_ciclo`, `descripcion`. UNIQUE `(pais_codigo, cuadrante)`. Es la
  tabla configurable del §7.2 / §17.5 (valores ilustrativos, pendientes de
  confirmar con el cliente).
- `formacion.CalendarioCoachingSugerido` — una celda = `(gd_id, ciclo_id, rm_id,
  semana, dia_semana, cuadrante_al_generar, editado_manualmente, publicado,
  publicado_en, creado_en)`. `cuadrante_al_generar` es snapshot (auditoría: por
  qué se sugirió esa frecuencia aunque el cuadrante cambie después).

## 4. Motor — `formacion_calendario_service.py`

Función principal `generar(db, gd_id, ciclo_id, persistir=True) -> list[dict]`.

**Pasos:**

1. **Guard de ciclo abierto.** Reusar `recalculo_service.validar_ciclo_abierto`
   (levanta `CicloCerradoError` → 409). Ciclos cerrados = solo lectura.
2. **Equipo del GD.** RMs con `gerente_id == gd_id` (país del ciclo).
3. **Cuadrante vigente por RM.** Última `FACT_EvaluacionReceptividad` del RM en el
   ciclo (`order by id desc`, `activo=True`). Si el RM **no tiene evaluación LSII**
   en el ciclo → **no se agenda**; se devuelve en una lista aparte `sin_evaluar`
   (no hay base para asignar frecuencia). Nunca se inventa un cuadrante.
4. **Frecuencia.** `cuadrante → visitas_por_ciclo` desde `ParametroFrecuenciaLSII`
   (por país). Si un cuadrante no está configurado para ese país → usar el
   **default de arranque** (§6). Frecuencia 0 → RM sin visitas ese ciclo (válido).
5. **Orden por ROI del ciclo anterior (desempate §7).** Ordenar los RM por **ROI
   ascendente del ciclo inmediatamente anterior** del mismo país
   (`visita_costo_service.roi_ranking(db, ciclo_anterior_id)`): el de **menor ROI
   va primero** (necesita más atención → mejores cupos). RM sin ROI previo o sin
   ciclo anterior → al final (neutral, no se le da prioridad artificial).
6. **Reparto en el ciclo.** `semanas = ceil((fecha_fin - fecha_inicio + 1) / 7)`
   del `DIM_Ciclo`; si faltan fechas → fallback `SEMANAS_DEFECTO = 8` (biciclo).
   Las N visitas de cada RM se **espacian** entre las semanas: semana de la i-ésima
   visita = `round((i + 0.5) * semanas / N)`, acotada a `[1, semanas]`.
7. **Día de la semana.** Para no cargar todo en un mismo día, el `dia_semana` se
   asigna **round-robin** sobre `lunes..viernes` recorriendo los RM en el orden
   por ROI del paso 5. Así el GD reparte su semana y los RM prioritarios caen
   temprano en la semana.
8. **Persistencia (`persistir=True`).** **Delete-then-insert selectivo**: borra
   solo las celdas `(gd_id, ciclo_id)` con `publicado=False AND
   editado_manualmente=False`, e inserta las nuevas sugeridas. **Conserva** lo
   publicado y lo editado a mano — el GD puede regenerar tras un cambio de LSII
   sin perder su trabajo. `persistir=False` = vista previa (simulación).

**Funciones auxiliares del servicio:**
- `listar(db, gd_id, ciclo_id) -> list[CalendarioCoachingSugerido]`.
- `mover_celda(db, celda_id, semana, dia_semana)` → marca `editado_manualmente=True`.
- `publicar(db, gd_id, ciclo_id)` → `publicado=True`, `publicado_en=now` a todas
  las celdas del GD/ciclo. Guard de ciclo abierto.
- `frecuencias(db, pais_codigo)` / `fijar_frecuencia(db, pais_codigo, cuadrante,
  visitas, descripcion?)` — leer/escribir `ParametroFrecuenciaLSII` (valida
  `cuadrante ∈ {D1,D2,D3,D4}` y `visitas >= 0`).

## 5. Valores de arranque (configurables)

`FRECUENCIA_DEFECTO` en el servicio (se puede sobrescribir por país en la tabla):

| Cuadrante | Estilo | visitas_por_ciclo |
|-----------|--------|-------------------|
| D1 | Dirigir  | 4 |
| D2 | Entrenar | 3 |
| D3 | Apoyar   | 2 |
| D4 | Delegar  | 1 |

Lógica: a menor desarrollo, más acompañamiento; D4 (delegar) el mínimo. Marcados
como **ilustrativos** (§7.2, punto abierto 4) — el cliente los confirma o ajusta
sin desplegar, escribiendo en `ParametroFrecuenciaLSII`. Un `seed` idempotente
(`scripts/seed_frecuencia_lsii.py`) los carga por país si no existen.

## 6. Endpoints — router `prefix="/formacion/calendario-coaching"`

| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| POST | `/generar` | Escritura + GD(propio) | Genera (o previsualiza con `persistir=false`). Body `{gd_id?, ciclo_id, persistir}`. GD omite `gd_id` (se auto-resuelve). Devuelve `{celdas, sin_evaluar, semanas}`. |
| GET  | `` | Lectura + GD(propio) | Calendario del GD/ciclo (`?gd_id=&ciclo_id=`). |
| PUT  | `/celda/{id}` | Escritura + GD(propio) | Mover día/semana de una celda → `editado_manualmente=true`. |
| POST | `/publicar` | Escritura + GD(propio) | Publica el calendario del GD/ciclo. |
| GET  | `/frecuencias` | Lectura | Tabla de frecuencia vigente del país + cuadrantes válidos. |
| PUT  | `/frecuencias` | Config | Fija `visitas_por_ciclo` de un cuadrante para el país. |

## 7. RBAC (patrón de auto-scope, como Cobertura/Categorización)

- **GERENTE_DISTRITO**: auto-scope forzoso a su propio `gerente_id` (vía
  `Usuario.gerente_id`). Omite `gd_id` en las peticiones; si envía uno ajeno → 403.
- **ADMIN, GERENTE_PRODUCTIVIDAD**: cualquier GD; además **configuran las
  frecuencias** (PUT `/frecuencias`).
- **Lectura del calendario** (GET): además PRESIDENCIA, GERENTE_MEDICO,
  CAPACITACION (visión consolidada, sin editar).
- Ruta gateada por `allowedRoles` (los routers de Formación gatean por
  `require_roles`, **no** por la matriz RBAC — un `recurso` inexistente denegaría
  a todos; lección de la Fase 7).

## 8. Frontend

- Página `pages/formacion/CalendarioCoaching.tsx`, ruta `/formacion/calendario`,
  ítem "Calendario de Coaching" en el Sidebar (sección Formación).
  - País/ciclo del encabezado global; para GD, su equipo fijo; para ADMIN/GERPROD,
    selector de GD.
  - Cuadrícula **RM (filas) × semanas (columnas)**; cada celda muestra el día
    sugerido; badge de cuadrante LSII por RM; sección aparte "Sin evaluación LSII".
  - Botón "Generar" (previa) → "Publicar". Edición de celda por selector de día/semana
    (marca editado). Solo-lectura si el ciclo está cerrado (`esSoloLectura`).
- Config de frecuencias como **tab en Admin** (patrón `LsiiAdmin`/`CategorizacionAdmin`).
- Servicio `services/formacion.service.ts` (extender el existente de la Fase 7).

## 9. Pruebas (`tests/test_formacion_calendario.py`)

Motor con reporte/datos construidos:
- Frecuencia por cuadrante respeta `ParametroFrecuenciaLSII` y cae al default si
  falta.
- RM sin evaluación LSII → va a `sin_evaluar`, no se agenda.
- Reparto: N visitas quedan espaciadas en las semanas correctas (casos N=1,2,4 con
  semanas=8); acotado a `[1, semanas]`.
- Desempate: orden por ROI ascendente del ciclo anterior; RM sin ROI al final.
- Persistencia: delete-then-insert **conserva** celdas publicadas y editadas a mano;
  regenerar no las pisa.
- Guard: generar/publicar sobre ciclo cerrado → `CicloCerradoError`.
- RBAC: GD con `gd_id` ajeno → 403 (prueba por API).

## 10. Fuera de alcance

- **Fase 3** (redefinir el eje Competencia de LSII): descartada por decisión del
  cliente. La matriz no se toca.
- **Ejecución del coaching** (registrar/calificar la sesión): sigue en Coaching
  MORE. Este módulo no crea ni cierra sesiones.
- **Notificación al GD/RM** de la publicación: no en esta fase (se puede enganchar
  luego a `notification_service`, como el Refuerzo).
