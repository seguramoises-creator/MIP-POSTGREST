# Spec — Historial accionable en el Simulacro de Venta

**Fecha:** 2026-08-06
**Módulo:** Formación → Simulacro de Venta con IA (§9)
**Alcance:** frontend-only (`frontend/src/pages/formacion/Simulacro.tsx`)
**Origen:** follow-up de UX de la Fase 8 — el endpoint `detalle` (`GET /formacion/simulacro/sesion/{id}`) existe pero la página no lo consume.

---

## 1. Problema

En la pantalla de inicio del Simulacro (`PantallaInicio`), el RM ve una lista "Mis
prácticas" con una tarjeta por sesión y un chip de estado ("En curso" /
"Finalizada"). Hoy las tarjetas son **decorativas**: no se puede reabrir una
sesión a medias ni consultar el resultado de una terminada. Si un RM abandona una
práctica (cierra la pestaña tras responder 1 de 3 rondas), esa sesión queda
huérfana — no hay forma de retomarla ni de terminarla, y al calificar cuenta las
rondas sin responder como incorrectas.

## 2. Objetivo

Hacer que **toda tarjeta del historial haga algo**:

- **"En curso"** → reanudar la práctica en la primera ronda pendiente.
- **"Finalizada"** → abrir la pantalla de resultado D/P/A/E ya existente.

Sin cambios de backend, modelo, migración ni tipos: `detalleSimulacro(sesionId)`
ya existe en `services/formacion.service.ts` y apunta a `GET
/formacion/simulacro/sesion/{id}`, protegido por `_rm_ids_visibles` (el RM solo ve
sus propias sesiones).

## 3. Por qué el backend ya alcanza

`formacion_simulacro_service.ronda_publica(r)` revela `opcion_correcta` y
`retroalimentacion` **solo** cuando `r.opcion_seleccionada is not None`. Por eso el
detalle de una sesión a medias llega con:

- rondas **ya respondidas**: con `opcion_seleccionada`, `es_correcta`,
  `opcion_correcta`, `retroalimentacion`;
- rondas **pendientes**: "ciegas", sin la respuesta correcta.

Ese es exactamente el estado que la reanudación necesita, servido por un solo
endpoint sin filtrar por estado. El progreso vive en las filas de `SimulacroRonda`;
no hace falta un puntero "ronda actual" en el servidor.

`detalle` además devuelve `resultado` (`{apertura, desarrollo, cierre, general}` o
`null`), que alimenta directo la pantalla de resultado para las "Finalizada".

## 4. Diseño

Todo ocurre en `Simulacro.tsx`. El componente ya maneja el estado
`sesion / idx / feedback / seleccion / resultado`; se reutiliza tal cual.

### 4.1 Abrir una sesión del historial

Se agrega una acción de "abrir sesión" que:

1. Llama `detalleSimulacro(id)`.
2. **Si trae `resultado`** (sesión finalizada) → `setResultado(resultado)` y cae en
   la pantalla de resultado existente.
3. **Si no trae `resultado`** (en curso) → hidrata la sesión activa:
   - `setSesion({ sesion, rondas })`
   - `idx` = índice de la **primera** ronda con `opcion_seleccionada === null`.
   - `setFeedback(null)`, `setSeleccion(null)`.
   - reproduce la voz de esa ronda (`reproducir`).
4. **Borde — todas respondidas pero `finalizada === false`** (respondió la última
   ronda y cerró sin pulsar "Ver resultado"): no hay ronda pendiente →
   `finalizarSimulacro(sesion.id)` directo y mostrar el resultado.

La lógica de "primera ronda pendiente" e "hidratar o finalizar" se encapsula en un
helper local (p. ej. `abrirSesion(id)`), no se dispersa por el JSX.

### 4.2 UI de las tarjetas

- Cada tarjeta de "Mis prácticas" pasa a ser clicable: `cursor: pointer`, estado
  hover sutil (borde/realce), `role="button"`.
- La tarjeta que se está abriendo muestra un spinner pequeño mientras corre
  `detalleSimulacro`; las demás quedan deshabilitadas para evitar doble apertura.
- El chip de estado se conserva igual ("En curso" / "Finalizada").

### 4.3 Estado de apertura

Se usa una mutation de React Query (`abrir`) para tener `isPending` y `variables`
(el id que se está abriendo) sin introducir estado manual redundante. En
`onSuccess` se aplica la ramificación de §4.1; en `onError`, §5.

## 5. Manejo de errores

Si `detalleSimulacro` falla (403 por sesión ajena, 404, o error de red):

- No se cambia de pantalla (se queda en `PantallaInicio`).
- Se muestra un `Alert severity="warning"` breve: "No se pudo abrir la práctica."
- El error se limpia al intentar abrir otra tarjeta o iniciar una nueva práctica.

No se distingue el código de estado en el mensaje (el RM no puede hacer nada
distinto ante 403 vs 404); basta un aviso genérico.

## 6. Fuera de alcance (YAGNI)

- **Replay read-only** de rondas ya contestadas al reanudar: el RM ya las
  respondió y vio su retro; reproducirlas es más código y menos valor. Se salta
  directo a la ronda pendiente.
- Cambios de backend, endpoint nuevo, o puntero "ronda actual" en el servidor.
- Reanudar/ver sesiones de **otros** RM desde esta pantalla: la lista solo trae las
  propias (`mis-sesiones`); la vista gerencial sigue siendo el resumen agregado.
- Paginación o filtros del historial.

## 7. Verificación

Al ser un cambio de UI, la verificación es **en vivo** (mint JWT, no escribir
contraseña) + `tsc`/build:

1. Iniciar una práctica, responder **1 de 3** rondas, volver al inicio (recargar).
2. Reabrir la tarjeta "En curso" → debe caer en la **ronda 2** (primera pendiente),
   con la voz de esa ronda y sin fuga de la respuesta correcta.
3. Terminar la práctica; reabrir esa tarjeta ya "Finalizada" → debe mostrar la
   pantalla de resultado D/P/A/E.
4. Caso borde: responder las 3 rondas sin pulsar "Ver resultado", volver al inicio,
   reabrir "En curso" → debe finalizar y mostrar el resultado.
5. `npm run build` (tsc) limpio.

No se agregan tests automatizados nuevos (la lógica movida es de presentación; el
motor de calificación/serialización ya está cubierto por los 29 tests de la Fase 8).
