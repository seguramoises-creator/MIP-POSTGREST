# Fase 8 — Simulacro de Venta con IA (§9) — Diseño

Fecha: 2026-08-05 · Módulo: Ampliación del Módulo de Formación (MSM-postgres).
Plan padre: `docs/superpowers/plans/2026-07-29-formacion-ampliada.md`.

## 1. Propósito

El Representante Médico (RM) practica una conversación de venta contra un **médico
simulado por IA**, con un **estilo social** asignado (Directivo / Analítico /
Amistoso / Expresivo, de la Matriz de Estilos Sociales de la Guía MORE). Por cada
fase del modelo **MORE**, el médico plantea una **objeción hablada** (TTS); el RM
**elige** la mejor respuesta entre opciones generadas por IA; cada elección se
califica con retroalimentación. El resultado final es **D/P/A/E (1-4) por fase**,
en la misma escala que Coaching MORE, para que ambos módulos sean comparables.

Es una herramienta de **autopráctica** del RM (no atada a ciclo ni país). La IA
**genera** el escenario; el modelo MORE aporta el contenido (no se inventa teoría).

## 2. Lo que ya existe (sin migración)

- **Modelo (Fase 1, `0031`)**: `formacion.SimulacroSesion` (`rm_id`,
  `estilo_social_asignado`, `medico_simulado`, `genero_simulado`, `fecha`,
  `finalizada`; **sin `ciclo_id`/`pais`**), `formacion.SimulacroRonda`
  (`sesion_id`, `fase_more` ∈ {Planificacion, Apertura, Desarrollo, Cierre},
  `tecnica_objecion` (solo Desarrollo), `objecion_texto`, `opciones` JSON,
  `opcion_seleccionada`, `opcion_correcta` (1 letra), `es_correcta`,
  `retroalimentacion`; **sin columna de orden → se ordena por `id`**),
  `formacion.SimulacroResultado` (`calificacion_apertura/desarrollo/cierre`
  enteros 1-4, `calificacion_general` Numeric(4,2)).
- **Capa IA (Fase 0)**: `app.services.ia.conexion_service.adaptador_texto(db)` →
  `AdaptadorTexto.generar_texto(prompt, max_tokens)`; `adaptador_voz(db)` →
  `AdaptadorVoz.sintetizar(texto, voz) -> Audio`. `Audio` trae `contenido: bytes`
  y `mime`, o `en_navegador=True` + `aviso` cuando la síntesis debe ocurrir en el
  navegador (Web Speech API). La conexión activa se resuelve sola (Anthropic en
  prod para texto; ElevenLabs/REST/navegador para voz), con respaldo al `.env`.
  Sin conexión de texto → `SinConexionActiva`.

**Esta fase es servicio + router + frontend. No hay cambio de esquema.**

## 3. Alcance de fases (decisión de diseño)

El `SimulacroResultado` califica **tres** fases (Apertura, Desarrollo, Cierre). El
MVP **genera y califica esas tres**. `Planificacion` es un valor válido de
`fase_more` (preparación) pero **no tiene columna de calificación**, así que queda
**fuera del MVP** (extensión futura, informativa). Cada fase produce **una o más
rondas**; Desarrollo lleva `tecnica_objecion` (una de las 6 técnicas del §9.2.3.c).

## 4. Motor — `formacion_simulacro_service.py`

**`ESTILOS = ("Directivo","Analitico","Amistoso","Expresivo")`**,
**`FASES = ("Apertura","Desarrollo","Cierre")`**.

La **técnica de objeción** de cada ronda de Desarrollo la **nombra la IA** (el prompt
le pide usar técnicas reconocidas de manejo de objeciones del modelo MORE y devolver
su nombre en `tecnica_objecion`). No se hardcodea una lista cerrada: se valida solo
que el campo venga **no vacío** en las rondas de Desarrollo y se guarda tal cual
(`String(40)`). Así el contenido lo aporta el modelo MORE vía la IA, no una constante
del código que quizá no empate con la guía vigente del cliente.

1. **`iniciar(db, rm_id, estilo=None, medico=None, genero=None) -> dict`**
   - Estilo/médico: si no se pasan, se eligen (estilo con `random.choice(ESTILOS)`;
     médico con nombre + género de una lista breve incrustada). Se aceptan por
     parámetro para pruebas deterministas.
   - Construye un **prompt estructurado** (estilo social + médico + las 3 fases +
     técnicas) y llama `conexion_service.adaptador_texto(db).generar_texto(prompt)`.
   - Parsea el **JSON del escenario** de forma robusta (patrón de
     `examen_ia_service`: quita fences ```` ```json ````, `json.loads`, valida).
     Forma esperada: `{"rondas": [{"fase_more","tecnica_objecion"?,"objecion_texto",
     "opciones":{"A":...,"B":...,...},"opcion_correcta":"B","retroalimentacion"}]}`.
   - Valida cada ronda (fase ∈ FASES; `opcion_correcta` ∈ claves de `opciones`;
     Desarrollo con `tecnica_objecion`). JSON inválido/incompleto tras 1 reintento
     → `SimulacroIAError` (el router lo traduce a 502).
   - Persiste `SimulacroSesion` + las `SimulacroRonda` (con `opcion_seleccionada`
     NULL, `es_correcta` NULL). Devuelve la sesión + las rondas **públicas** (ver 4.5).
2. **`voz_ronda(db, ronda_id) -> Audio`**: `adaptador_voz(db).sintetizar(objecion_texto)`.
   El router decide: `contenido` → `StreamingResponse` (audio); `en_navegador` →
   JSON `{en_navegador:true, texto, aviso}` para que el frontend use Web Speech.
3. **`responder(db, ronda_id, rm_id, opcion) -> dict`**: valida que la ronda sea del
   RM y no esté ya respondida; guarda `opcion_seleccionada`, calcula `es_correcta`,
   y **solo entonces** devuelve `{es_correcta, opcion_correcta, retroalimentacion}`.
   La correcta y la retro **nunca** viajan antes de responder (mismo criterio que
   Refuerzo §10.7 y el `score_oculto` de LSII).
4. **`finalizar(db, sesion_id) -> SimulacroResultado`**: por cada fase, `es_correcta`
   de sus rondas → ratio → escala **D/P/A/E** con `_a_escala(ratio)`
   (≥0.90→4, ≥0.70→3, ≥0.50→2, resto→1). `calificacion_general` = promedio de las
   tres, redondeado a 2 decimales. Marca `finalizada=True`. Re-ejecutable
   (delete-then-insert del resultado). Rondas sin responder cuentan como incorrectas.
5. **Serialización pública** `_ronda_publica(r)`: `{id, fase_more, tecnica_objecion,
   objecion_texto, opciones, opcion_seleccionada, es_correcta}` — **sin**
   `opcion_correcta` ni `retroalimentacion` mientras `opcion_seleccionada` sea NULL;
   una vez respondida, sí se incluyen (para poder repintar el histórico).
6. Lectura: `mis_sesiones(db, rm_id)`, `detalle(db, sesion_id)`,
   `resumen(db, rm_ids=None)` (agregado por RM: nº de prácticas, última general).

## 5. Endpoints — router `prefix="/formacion/simulacro"`

| Método | Ruta | Roles | Descripción |
|--------|------|-------|-------------|
| POST | `/iniciar` | RM(propio) + ADMIN | Genera el escenario con IA y arranca la sesión. |
| GET  | `/sesion/{id}` | dueño + Lectura | Estado + rondas públicas. |
| GET  | `/ronda/{id}/voz` | dueño + Lectura | Audio de la objeción (bytes) o señal `en_navegador`. |
| POST | `/ronda/{id}/responder` | dueño | Registra la opción, revela correcta + retro. |
| POST | `/sesion/{id}/finalizar` | dueño | Calcula el resultado D/P/A/E. |
| GET  | `/mis-sesiones` | RM | Historial del RM. |
| GET  | `/resumen` | Lectura (GD equipo / Capacitación) | Agregado de prácticas del equipo. |

"dueño" = el RM cuyo `rm_id` es de la sesión (o ADMIN). "Lectura" = ADMIN,
GERENTE_PRODUCTIVIDAD, CAPACITACION, GERENTE_DISTRITO (su equipo), PRESIDENCIA,
GERENTE_MEDICO. Ruta gateada por `allowedRoles` (los routers de Formación gatean por
`require_roles`, no por la matriz RBAC).

## 6. RBAC (auto-scope)

- **REPRESENTANTE_MEDICO**: auto-scope a su propio `rm_id` (vía `Usuario.rm_id`).
  Inicia/responde/finaliza solo sus sesiones; 403 si la sesión/ronda es de otro RM.
- **GERENTE_DISTRITO**: lectura de resultados de su equipo (`resumen`, `detalle`),
  scope por `Usuario.gerente_id`.
- **ADMIN / GERENTE_PRODUCTIVIDAD / CAPACITACION**: lectura de todo; ADMIN también
  puede iniciar en nombre de un RM (para demo).

## 7. Dependencia de IA y degradación

- **Texto (obligatorio)**: usa la conexión de texto activa (Anthropic en prod). Sin
  conexión → `SinConexionActiva` → el endpoint responde 503 con mensaje claro ("No
  hay una conexión de IA de texto activa; configúrala en Conexiones de IA"). **No
  hay fallback de contenido** — un simulacro sin IA no tiene sentido.
- **Voz (degradable)**: usa el adaptador de voz activo; si no hay proveedor real,
  la Fase 0 devuelve `en_navegador=True` y el **frontend** sintetiza con Web Speech
  API (con el aviso de que no es acento dominicano). Así funciona de una y mejora al
  configurar ElevenLabs. La voz **nunca bloquea** la práctica: si `voz_ronda` falla,
  el frontend cae a mostrar el texto de la objeción.

## 8. Frontend

- Página `pages/formacion/Simulacro.tsx`, ruta `/formacion/simulacro`, ítem
  "Simulacro de Venta" en el Sidebar (sección Formación).
  - **Inicio**: botón "Nueva práctica" → `POST /iniciar` (muestra el estilo social y
    el médico asignados con una breve caracterización).
  - **Por ronda**: chip de fase MORE (+ técnica en Desarrollo); reproduce el audio de
    la objeción — si la respuesta trae bytes, `<audio>`; si `en_navegador`,
    `window.speechSynthesis.speak(texto)` (botón "Escuchar"). Opciones como botones;
    al elegir → `responder` → resalta correcto/incorrecto + retro; botón "Siguiente".
  - **Final**: `finalizar` → resultado D/P/A/E por fase (barras/radar) + general +
    "Nueva práctica". Historial en "Mis prácticas".
  - Solo el RM practica; GD/Capacitación ven `resumen` (tabla por RM).
- Servicio: extender `services/formacion.service.ts` con las funciones del simulacro
  (incluye manejo de la respuesta de voz dual: blob vs `en_navegador`).

## 9. Pruebas (`tests/test_formacion_simulacro.py`)

Con la capa IA **mockeada** (monkeypatch de `conexion_service.adaptador_texto` a un
stub cuyo `generar_texto` devuelve un JSON de escenario canónico, y de
`adaptador_voz` a un stub que devuelve `Audio(en_navegador=True)`):

- `iniciar` parsea y persiste las rondas de las 3 fases; JSON con fences se limpia;
  JSON inválido tras reintento → `SimulacroIAError`.
- Las rondas públicas **no** exponen `opcion_correcta` ni `retroalimentacion` antes
  de responder; sí después.
- `responder` calcula `es_correcta`, revela la correcta+retro, y rechaza responder
  dos veces la misma ronda.
- `finalizar`: mapeo D/P/A/E por fase correcto en los bordes (ratios 1.0→4, 0.75→3,
  0.5→2, 0.0→1) y general = promedio; rondas sin responder cuentan como incorrectas;
  re-ejecutable.
- `voz_ronda` devuelve el `Audio` del adaptador (caso `en_navegador`).
- RBAC: un RM que intenta responder una ronda de otra sesión → 403 (prueba por API o
  por la función de scope).

## 10. Fuera de alcance

- **Reconocimiento de voz (STT)**: no existe adaptador ni scoring de texto libre; el
  RM responde eligiendo, no hablando. No en esta fase.
- **Fase `Planificacion`** como fase calificada (no tiene columna en el resultado).
- **Generación adaptativa ronda-a-ronda**: el escenario se genera completo en una
  sola llamada de texto (más barato y determinista).
- **Consolidación al KPI/Score**: el resultado del simulacro es formativo; no
  alimenta el Score Integral en esta fase (a diferencia de Coaching MORE).
