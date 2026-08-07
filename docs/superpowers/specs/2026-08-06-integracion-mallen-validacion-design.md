# Spec — Integración Mallén, sub-proyecto 1: Recepción y validación de lotes

**Fecha:** 2026-08-06
**Módulo:** Integración con Laboratorio Mallén (esquema `ext`).
**Alcance:** backend (servicio + router + migración + tests) y frontend (service + página).
**Origen:** el esquema `ext` está construido (22 tablas, migración `0030`, tests de contrato, SQL entregado al cliente, usuario `mallen_etl` sin DELETE), pero **no existe ningún servicio ni router que lo consuma**. Mallén todavía no ha enviado ningún lote; lo que los desbloquea es poder enviar y saber si su envío está bien.

---

## 1. Contexto: cómo funciona la integración

Dirección del flujo (§8 del Requerimiento de Datos): **Mallén empuja, VISTA lee.** VISTA nunca se conecta al SQL Server de Mallén.

1. Mallén abre una fila en `ext.controlcarga` con `estado = 'RECIBIDO'`, un `lote_id` propio y `filas_enviadas` declaradas.
2. Mallén escribe las filas de sus tablas, todas amarradas a ese `lote_id`.
3. **VISTA valida el lote** y lo mueve a `VALIDADO` o `RECHAZADO`, dejando el detalle en `mensaje`. ← *esto es lo que falta*
4. (Sub-proyectos posteriores) VISTA integra los datos válidos a sus esquemas internos y marca `INTEGRADO`.

Este sub-proyecto cubre **solo el paso 3**. No integra nada a los esquemas internos de VISTA.

## 2. La regla que manda el diseño

**§7.1: las inconsistencias se registran sin detener el lote completo.**

Por eso el contrato deliberadamente **no lleva `CHECK`** en los campos acotados (así lo documenta el modelo): un `CHECK` rechazaría el `INSERT` de Mallén y abortaría su envío entero por una fila mala. Al validar aquí, VISTA acepta el lote completo y devuelve un informe de qué corregir.

Consecuencia directa: **la validación nunca lanza una excepción por datos malos.** Anota el hallazgo y sigue con la fila siguiente.

## 3. Qué se valida

El contrato tiene 22 tablas: 9 dimensiones + 5 del módulo IR + 8 de hechos. De esas 8, una es `controlcarga` (la cabecera del lote), así que se validan las **7 tablas de datos**: `panelmedico`, `factvisitamedico`, `targetfarmacia`, `factvisitafarmacia`, `factventa`, `factevaluacionconocimiento`, `factprescripciondetalle`.

### 3.1 Dominios acotados
Los campos que el propio modelo señala como "los que rompen indicadores en silencio" (§11.6):

| Tabla | Campo | Valores válidos |
|---|---|---|
| `factvisitamedico` | `tipo_visita` | `V` (visita) o `R` (revisita) |
| `panelmedico` | `frecuencia_objetivo` | `F1` o `F2` |
| `panelmedico` | `prioridad` | `TOP` o `REGULAR` |
| `panelmedico` | `categoria` | `A`, `B`, `C` o `D` (opcional; si viene, debe ser uno de esos) |
| `controlcarga` | `estado` | `RECIBIDO`, `VALIDADO`, `INTEGRADO`, `RECHAZADO` |

La comparación es **exacta y sensible a mayúsculas** — así está el contrato. Un `"v"` minúscula es un hallazgo, no una equivalencia: aceptarlo en silencio dejaría a Mallén sin saber que su origen envía inconsistente.

### 3.2 Integridad referencial blanda
Que los códigos referenciados existan **dentro del propio `ext`** (no contra los catálogos internos de VISTA, que es tarea del sub-proyecto 2):

- `pais_codigo` en `ext.dimpais`
- `(pais_codigo, ciclo_codigo)` en `ext.dimciclo`
- `(pais_codigo, rm_codigo)` en `ext.dimrepresentante`
- `(pais_codigo, medico_codigo)` en `ext.dimmedico`
- `(pais_codigo, farmacia_codigo)` en `ext.dimfarmacia`

**Nota importante:** las tablas ya tienen estas FK declaradas, así que un código inexistente ni siquiera podría insertarse. La validación sirve para el caso real: **que la dimensión venga en un lote posterior al del hecho**. Se reporta como hallazgo informativo, no como error bloqueante.

### 3.3 Coherencia del lote
- **Conteo**: `filas_enviadas` declarado vs. filas realmente escritas con ese `lote_id` (sumando todas las tablas). Una discrepancia es el síntoma clásico de una carga cortada a la mitad.
- **Lote vacío**: un lote `RECIBIDO` sin ninguna fila.
- **Duplicados de `origen_id`**: los índices `ux_*_origen` ya lo impiden a nivel de base, así que no se re-valida — se documenta que la base lo garantiza y por qué no se duplica el trabajo.

### 3.4 Campos obligatorios de negocio
`panelmedico.prioridad` es obligatoria en todas las filas (regla nueva de §3.4 del requerimiento) y ya es `NOT NULL`. Se valida su **dominio**, no su presencia.

## 4. Dónde se guardan los hallazgos

`controlcarga.mensaje` es `String(500)`: alcanza para un resumen, no para el detalle fila a fila.

**Tabla nueva `Audit.IntegracionHallazgo`** — en un esquema **nuestro**, nunca en `ext`. `ext` es un contrato firmado con un tercero; agregarle una tabla obligaría a reeditar el SQL entregado y a repetir el permiso del usuario `mallen_etl`. Va en `Audit` porque es exactamente eso: la traza de qué vino mal y cuándo.

```
lote_id        BigInteger  (FK a ext.controlcarga.lote_id)
tabla          String(40)   -- 'factvisitamedico', etc.
origen_id      String(60)   -- nullable: los hallazgos de lote no tienen fila
campo          String(40)   -- nullable: los de conteo no tienen campo
problema       String(300)  -- texto legible para el TI de Mallén
severidad      String(10)   -- 'error' | 'aviso'
detectado_en   DateTime
```

**Severidad:**
- `error` → dominio inválido o conteo descuadrado. El lote se marca `RECHAZADO`.
- `aviso` → referencia aún no recibida (§3.2). El lote puede quedar `VALIDADO`.

Un lote **sin ningún hallazgo de severidad `error`** pasa a `VALIDADO`. Con al menos uno, `RECHAZADO`.

**Migración necesaria**: crear `Audit.IntegracionHallazgo` (una tabla, sin tocar `ext`).

## 5. Re-validación

Validar un lote es **re-ejecutable**: borra los hallazgos previos de ese `lote_id` y los vuelve a calcular (delete-then-insert, igual que el resto del proyecto). Esto importa porque el flujo real de corrección es: Mallén reenvía el registro con el mismo `origen_id` (nunca borra — no tiene permiso), y se vuelve a validar.

**Guard**: solo se validan lotes en estado `RECIBIDO`, `VALIDADO` o `RECHAZADO`. Un lote ya `INTEGRADO` **no se re-valida** — sus datos ya viven en los esquemas internos de VISTA y re-marcarlo como `RECHAZADO` daría una foto falsa. Si se intenta, responde 409 con ese motivo.

## 6. API

Prefijo `/integracion`. **Roles: ADMIN y GERENTE_PRODUCTIVIDAD** — es operación de TI, no de negocio. Sigue el criterio de `/admin` y `/ia/conexiones` (gate por rol, no por la matriz RBAC, que exigiría migración).

| Método | Ruta | Descripción |
|---|---|---|
| GET | `/integracion/lotes` | `?pais_codigo&estado&limite` → lotes con su estado, filas y conteo de hallazgos |
| GET | `/integracion/lotes/{lote_id}` | Cabecera + sus hallazgos agrupados por tabla |
| POST | `/integracion/lotes/{lote_id}/validar` | Valida (o re-valida) y devuelve el resultado |
| GET | `/integracion/resumen` | `?pais_codigo` → conteo de lotes por estado, para el tablero |

`POST /validar` devuelve:
```json
{"lote_id": 1001, "estado": "RECHAZADO", "filas_declaradas": 1240,
 "filas_reales": 1238, "errores": 12, "avisos": 3,
 "mensaje": "1238 filas, 12 errores en 2 tabla(s), 3 aviso(s)"}
```
Ese mismo `mensaje` se escribe en `controlcarga.mensaje` (truncado a 500 si hiciera falta).

## 7. Frontend

Página `frontend/src/pages/integracion/LotesIntegracion.tsx`, ruta `/integracion/lotes`, ítem de Sidebar en el grupo de sistema (junto a Conexiones de IA). Service `frontend/src/services/integracion.service.ts`.

- **Tarjetas de resumen**: lotes por estado (Recibidos / Validados / Integrados / Rechazados).
- **Tabla de lotes**: `lote_id`, sistema origen, módulo, país, ciclo/período, fecha de recepción, filas, estado (chip de color) y nº de hallazgos.
- **Botón "Validar"** por fila, habilitado salvo en lotes `INTEGRADO` (con tooltip explicando por qué).
- **Al abrir un lote**: sus hallazgos en tabla — tabla, `origen_id`, campo, problema, severidad. Es lo que el usuario copia y manda al TI de Mallén.
- País desde el contexto global (`useCicloStore`), con la lista sin filtrar si no hay país elegido.
- Estado vacío honesto: **"Aún no se ha recibido ningún lote de Mallén."** — hoy es el estado real, y no debe parecer un error.

## 8. Fuera de alcance (YAGNI)

- **Integrar datos a los esquemas internos de VISTA** — es el sub-proyecto 2 en adelante; este entrega solo recepción y validación.
- Validación cruzada contra los catálogos internos de VISTA (`Config.DIM_*`): pertenece a la sincronización de dimensiones.
- Disparo automático de la validación (scheduler o trigger al detectar un lote nuevo): sub-proyecto 5. Aquí se valida con un botón.
- Notificar por correo a Mallén el resultado del lote.
- Tocar el esquema `ext` de cualquier forma: es contrato con un tercero.
- Reglas de negocio sobre los valores (p. ej. "un RM no debería tener más de N visitas/día"): esto valida el **contrato**, no la plausibilidad.

## 9. Verificación

**Backend** — tests en `backend/tests/test_integracion_validacion.py`, con el patrón PostgreSQL real del proyecto (se saltan si no hay base):
1. Un lote limpio → `VALIDADO`, cero hallazgos.
2. `tipo_visita = 'X'` → un hallazgo `error` en `factvisitamedico` y lote `RECHAZADO`.
3. `frecuencia_objetivo = 'F3'` y `prioridad = 'ALTA'` → dos hallazgos `error` en `panelmedico`.
4. `tipo_visita = 'v'` (minúscula) → hallazgo `error`: la comparación es sensible a mayúsculas.
5. `filas_enviadas` declaradas ≠ filas reales → hallazgo `error` de conteo, sin `origen_id` ni `campo`.
6. Re-validar el mismo lote **no duplica hallazgos** (delete-then-insert).
7. Un lote `INTEGRADO` no se re-valida (levanta el error que el router traduce a 409).
8. Un lote limpio con una referencia faltante → hallazgo `aviso` y el lote **sigue `VALIDADO`** (un aviso no rechaza).

**Frontend** — `npm run build` + smoke: ver la lista, validar un lote, abrir sus hallazgos.
