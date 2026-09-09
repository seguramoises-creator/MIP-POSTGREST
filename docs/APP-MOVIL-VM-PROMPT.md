# VISTA Campo — App Android para el Visitador Médico

**Qué es este documento.** El encargo completo para construir la aplicación móvil del
Visitador Médico (VM / Representante Médico) sobre .NET MAUI. Está escrito para
entregarse tal cual a quien la vaya a construir —persona o IA— sin necesidad de leer el
resto del repositorio: lleva los endpoints reales, las reglas de negocio que el servidor
ya impone y las decisiones de producto que no se deben reabrir.

**Contra qué se construye.** El backend existe y está en producción: FastAPI +
PostgreSQL, base `https://<host>/api/v1`. La app **no** define reglas de negocio nuevas;
consume las que el servidor ya tiene y las refleja en la interfaz para que el VM no
choque contra un 409 sin entender por qué.

---

## 0. Lo primero, porque bloquea el resto: hoy la captura está CERRADA

Antes de escribir una línea de la app hay que resolver esto, y no es un detalle de
configuración: es la razón de existir de la aplicación.

Los tres endpoints con los que el VM registraría su trabajo devuelven **409** de forma
incondicional, con este texto:

> «El registro de visitas está cerrado: las visitas provienen del SFA de Mallén y se
> integran automáticamente. Lo ya registrado sigue disponible para consulta.»

- `POST /visita/registrar`
- `POST /visita/no-visita`
- `POST /visita/{id}/foto`
- `POST /farmacias/{panel_id}/visita` y `POST /farmacias/{id}/foto`

Se cerraron porque **en la instalación de Mallén** las visitas entran por su propio SFA
(esquema `ext`) y una segunda puerta duplicaría o pisaría los datos. La decisión es
correcta para Mallén y equivocada para cualquier instalación donde la fuerza de ventas
registre en VISTA — que es justo el caso de esta app.

**La lógica de negocio sigue intacta**: `visita_registro_service.registrar_visita` y
`visita_farmacia_service.registrar_visita` conservan sus guardas, sus validaciones y su
escritura. Lo único cerrado es el router.

### Fase 0 — reabrir la captura, condicionada a la instalación

Trabajo de backend, previo a la app:

1. La captura se habilita **por configuración de instalación**, con el mismo mecanismo
   que ya decide el menú: `Config.DIM_Parametro` → `MODO_INGESTA`.
   - `MODO_INGESTA = integracion` (Mallén): los endpoints siguen devolviendo 409 con el
     mismo mensaje. **No cambia nada para el cliente actual.**
   - `MODO_INGESTA = excel` o `vista`: los endpoints vuelven a delegar en su servicio.
2. `GET /admin/config/app` ya expone `modo_ingesta`. **La app lo lee al arrancar** y, si
   viene `integracion`, arranca en **modo consulta**: oculta los botones de registro en
   vez de dejarlos puestos para que fallen. Un botón que revienta al pulsarlo es peor
   que un botón que no está.
3. Prueba de que no se rompió Mallén: con `MODO_INGESTA=integracion`, los cinco endpoints
   siguen devolviendo 409 y el mensaje es el mismo, palabra por palabra.

Si esta fase no se hace, la app se queda en un visor de solo lectura. Decidirlo es del
negocio, no del desarrollo; pero hay que decidirlo **antes**, no descubrirlo a mitad.

---

## 1. Para quién es y bajo qué condiciones se usa

El VM trabaja **de pie, en la calle, con una sola mano libre**, entre consultorio y
consultorio, con el teléfono al sol y con cobertura irregular (parqueos subterráneos,
edificios médicos, zonas rurales). Eso manda sobre cualquier preferencia estética:

- **Objetivo de tiempo: registrar una visita en menos de 20 segundos** y como máximo tres
  toques desde la pantalla de inicio.
- **Todo tiene que funcionar sin conexión** salvo iniciar sesión la primera vez.
- **Contraste alto y texto sólido**: peso 600 mínimo en etiquetas, nada de gris claro
  sobre blanco, nada de vidrio esmerilado ni translucidez — bajo el sol el contraste
  efectivo depende de lo que haya detrás y desaparece.
- **Áreas táctiles de 48 dp como mínimo**, separadas 8 dp. Se usa con prisa y a veces con
  el teléfono en la misma mano que el maletín.
- **Nada crítico en el borde superior**: la mano no llega. Las acciones principales van en
  la mitad inferior de la pantalla.

---

## 2. Stack y arquitectura

- **.NET MAUI**, .NET 9, **solo Android** en la primera entrega (mínimo API 26 / Android
  8.0; objetivo API 35). El proyecto se deja multiplataforma pero no se compila iOS.
- **MVVM** con `CommunityToolkit.Mvvm` (`ObservableObject`, `RelayCommand`). Nada de
  lógica en el code-behind salvo permisos y ciclo de vida.
- **SQLite** (`sqlite-net-pcl`) como base local — no es una caché opcional, es la fuente
  de verdad mientras no hay red (§5).
- **Refit** o `HttpClient` con `System.Text.Json` para la API. Un único
  `ApiClient` con el interceptor de token y el manejo de 401 → refresh → reintento.
- **Almacenamiento seguro**: `SecureStorage` para los tokens. Nunca en `Preferences` ni
  en la base SQLite.
- **Inyección de dependencias** con el contenedor de MAUI (`MauiProgram`).
- **Serilog** a archivo rotativo local, con un botón «Enviar diagnóstico» en Perfil.

### Estructura de carpetas

```
VistaCampo/
  Models/          entidades locales (espejo de la API + campos de sincronización)
  Data/            AppDatabase.cs, repositorios, migraciones de SQLite
  Services/        ApiClient, AuthService, SyncService, UbicacionService, FotoService
  ViewModels/      uno por pantalla
  Views/           XAML
  Resources/       Styles/Colores.xaml, Styles/Estilos.xaml, imágenes
  Platforms/Android/  permisos, FileProvider, íconos
```

---

## 3. Identidad visual — se lee del servidor, no se escribe en el código

La suite web ya resuelve esto y la app **debe hacer lo mismo**, porque las dos
instalaciones (VISTA y Laboratorios Mallén) comparten binario y se distinguen por
configuración:

- `GET /admin/config/marca` → `{ rojo, taupe, logo }`.
  - `rojo` = **color de acción** (botones, enlaces). `taupe` = **color de estructura**
    (barras, superficies fuertes). Los nombres son heredados; no describen el matiz.
  - `logo` = nombre de la identidad (`vista` | `mallen`). Trae consigo su juego de
    logotipos y su paleta afinada.
- Se lee **una vez al arrancar**, junto con `GET /admin/config/app`, y se guarda en
  SQLite para el siguiente arranque sin red.
- **El color vive en un objeto mutable que se actualiza antes de pintar.** Copiarlo a una
  constante estática al cargar el ensamblado lo congela en el valor de fábrica: ese error
  ya costó tres veces en la web que el color configurado no llegara a las barras mientras
  el resto de la aplicación sí cambiaba, sin que nada avisara. En MAUI eso significa
  `DynamicResource`, no `StaticResource`, para todo lo que venga de la marca.
- **Dos logotipos por identidad, y no es duplicación**: uno para fondo oscuro (barras,
  pantalla de entrada) y otro para fondo claro. Elegir por la **superficie** sobre la que
  se pinta, nunca por la pantalla.

Paleta de VISTA (la que rige si el servidor no responde): acción `#0050B4`, estructura
`#1A237E`, azul aclarado para botón sobre fondo oscuro `#2E6FD0`, fondo profundo
`#011D42`, casi negro `#00122C`.

**Contraste, medido y no supuesto:** texto pequeño ≥ 4.5:1 sobre su fondo; elementos
gráficos (bordes de botón, iconos que informan) ≥ 3:1. El azul de marca sobre el fondo
profundo da 2.24:1 — por eso el botón de la pantalla de entrada usa el aclarado.

---

## 4. Autenticación y sesión

| Qué | Endpoint |
|---|---|
| Entrar | `POST /auth/login` — **form-data** `username` + `password` |
| Renovar | `POST /auth/refresh` |
| Salir | `POST /auth/logout` |
| Quién soy | `GET /auth/me` |

- Respuesta de login: `access_token` (60 min), `refresh_token` (7 días),
  `debe_cambiar_password`, `password_expira_en_dias`, `password_motivo`.
- El `access_token` es un JWT con `rol`, `username`, `nombre_completo`. **El rol del VM es
  `REPRESENTANTE_MEDICO`** y el servidor lo auto-acota a su propio `rm_id`: la app nunca
  manda `vm_id`, y si lo mandara recibiría 403.
- Si `debe_cambiar_password` viene `true`, la app va directo a cambiar contraseña y no
  deja pasar. Mínimo 12 caracteres, mayúscula, minúscula, número y un carácter especial.
- **Sesión sin red**: si el `refresh_token` sigue vigente pero no hay conexión, la app
  entra en modo sin conexión con los datos locales. Solo se expulsa al VM cuando el
  refresh vence de verdad o el servidor responde 401 a un refresh real.
- **El teclado móvil autocapitaliza y autocorrige el usuario**: `mdavid` llegaba como
  `Mdavid` y el login fallaba con «Credenciales incorrectas». En los campos de usuario y
  contraseña: `Keyboard="Plain"`, sin autocapitalización, sin corrección, sin corrector
  ortográfico. Al mostrar la contraseña en claro, mantener esas mismas propiedades.
- **Sin respuesta del servidor no se acusa a la contraseña.** Si no hubo respuesta HTTP,
  el mensaje es «No se pudo contactar el servidor. Revisa tu conexión.» — nunca
  «Credenciales incorrectas». Ese mensaje por omisión llegó a costar una tarde de
  restablecer claves mientras el problema era el túnel.

---

## 5. Sin conexión — la parte que decide si la app sirve

No es una funcionalidad más: el VM está bajo tierra en el parqueo del edificio médico
justo cuando termina la visita. Reglas:

1. **Escribir siempre local primero.** Toda captura entra en SQLite con
   `estado ∈ {pendiente, enviando, enviado, rechazado}` y un `uuid_cliente` generado en el
   dispositivo. La interfaz confirma contra la escritura **local**, no contra la red.
2. **Cola de salida ordenada por hora de captura**, reintentos con retroceso exponencial
   (5 s → 5 min, tope), y envío disparado por: recuperación de red, app en primer plano,
   y un tirón manual desde el encabezado.
3. **`uuid_cliente` viaja al servidor** para que un reintento no cree una visita doble.
   Esto exige un campo nuevo en el backend (`FactVisita.uuid_cliente`, único por VM):
   forma parte de la Fase 0.
4. **La hora la pone el servidor, no el teléfono.** El servidor calcula la hora restando
   `hace_minutos` a su propio reloj, y ese campo admite **como máximo 60**. Consecuencia
   para la app: una visita capturada sin red y enviada al día siguiente **será rechazada**
   por la ventana del ciclo. Por eso la cola muestra **antigüedad** en cada pendiente y
   avisa en rojo a partir de 45 minutos: «Envía antes de que venza la ventana».
   No inventar una hora: mandar `hace_minutos` calculado en el momento del envío.
5. **Un rechazo no se borra en silencio.** El elemento queda en la cola marcado en rojo,
   con el motivo textual del servidor y un botón «Ver detalle». El VM tiene derecho a
   saber que su trabajo no entró.
6. **Los catálogos se descargan al entrar y se refrescan cada 6 h**: panel médico, panel
   de farmacias, planeación del ciclo, causas de no-visita, productos de la parrilla,
   especialidades y centros. Sin ellos la app no puede capturar.
7. **Nunca mostrar una ausencia como un cero.** Sin planeación descargada, la agenda dice
   «Sin agenda descargada», no «0 visitas planeadas». Un cero afirma; una ausencia no.

---

## 6. Las pantallas

Navegación: `Shell` con **barra inferior de 5 pestañas** — Hoy · Registrar · Panel ·
Plan · Perfil. La barra inferior es obligatoria: el VM usa el pulgar.

### 6.1 Entrada

Fondo con el degradado de la identidad, tarjeta oscura centrada, logotipo de fondo
oscuro, campos blancos con la etiqueta **encima** (no flotante: sobre una caja blanca la
etiqueta flotante se apoya en el borde y hay que teñirla contra dos fondos a la vez).
Botón de ancho completo con el azul aclarado. Enlace «¿Olvidaste tu contraseña?» →
`POST /auth/forgot-password` (correo) y `POST /auth/reset-password` (código de 6 dígitos,
vence en 15 min).

### 6.2 Hoy — la pantalla de inicio

Lo que el VM mira entre visita y visita. De arriba abajo:

1. **Encabezado**: país y ciclo vigente, y un punto de estado de sincronización
   (verde = al día, ámbar = N pendientes, rojo = N rechazados). Tocarlo abre la cola.
2. **Cuatro cifras del día**: Vistas, Revisitas, Farmacias, Acompañadas.
   Fuente: `GET /visita/mis-visitas-hoy`.
3. **Avance de la semana** contra la agenda, con barra: `GET /visita/dia` si la
   instalación lo expone; si no, se calcula contra la planeación local.
   **Sin agenda no se pinta un cero**: se muestra «—» y el texto «Sin visitas planeadas
   para esta semana». Acusar de incumplimiento a quien no tenía nada planeado es peor que
   no informar.
4. **Agenda de hoy** (`GET /visita/agenda-hoy`): lista de médicos programados con su
   estado (pendiente / registrada). Cada fila con acción directa **Registrar**.
5. **Últimos registros** del día, con su hora y un indicador de si ya subió.

### 6.3 Registrar visita médica — la pantalla que más se usa

`POST /visita/registrar`. Cuerpo:

```jsonc
{
  "medico_id": 123,
  "tipo_visita": "V",        // "V" Vista | "R" Revisita  — únicos valores
  "comentario": "…",         // 10-1000 caracteres, y no puede ser genérico
  "hace_minutos": 0,         // 0-60; el servidor resta esto a SU reloj
  "acompanado": false,        // visita acompañada por el Gerente de Distrito
  "productos": [ { … } ],
  "latitud": 18.48, "longitud": -69.93
}
```

Reglas que la app debe hacer cumplir **antes** de dejar pulsar Guardar, para que el VM no
pierda el texto contra un 422:

- **Médico**: se elige del panel local. Buscador que filtra por nombre según se escribe,
  con los de hoy primero. Si el médico no está en el panel, la pantalla ofrece «Agregar al
  panel» (§6.4) en vez de dejar al VM atascado.
- **Tipo**: dos botones grandes, Vista / Revisita. Nunca un desplegable.
- **Comentario**: mínimo 10 caracteres **y** rechazado si es genérico (el servidor mantiene
  una lista de frases vacías tipo «visita realizada», «ok», «sin novedad»). La app valida
  el largo en vivo y muestra el motivo exacto si el servidor lo rechaza. **No** borrar lo
  escrito ante un error.
- **Ventana de 60 minutos**: un selector de «hace cuánto» con los valores 0 / 15 / 30 / 45 /
  60. Pasados los 60 minutos la visita **no se puede registrar** — decirlo con esas
  palabras, no ofrecer un campo de fecha que el servidor va a rechazar.
- **Ciclo**: si el ciclo está cerrado o su ventana venció, el servidor responde con un
  motivo legible. La app lo muestra tal cual y **desactiva la captura** con un aviso
  permanente en Hoy: «El ciclo C07-2026 venció. Habla con tu gerente.»
- **GPS**: `latitud`/`longitud` son **opcionales**. Se piden con
  `Permissions.LocationWhenInUse` y precisión media, con un tope de 8 segundos: si no hay
  señal, se registra la visita **sin** coordenadas. Bloquear el registro por falta de GPS
  dentro de un edificio médico haría inservible la app justo donde se usa.
- **Foto**: opcional, `POST /visita/{id}/foto` después de crear la visita. JPEG o PNG,
  **máximo 3 MB** — la app recomprime a 1600 px de lado mayor y calidad 80 antes de subir.
  La foto va en la cola por separado: una foto que falla no debe tumbar la visita que ya
  entró.
- **Productos**: la parrilla del ciclo (`GET /visita/parrilla`, `GET /visita/productos`) —
  selección múltiple con casillas grandes. Opcional.
- **Acompañado**: interruptor. Alimenta el conteo de visitas con Gerente de Distrito.

**No-visita** (`POST /visita/no-visita`): botón secundario en la misma pantalla, con el
catálogo de causas de `GET /visita/causas` y comentario opcional. Registrar por qué no se
pudo entrar es información, no una excusa: la pantalla lo trata con el mismo peso visual
que una visita.

**Las visitas no se editan ni se borran.** No existen esos endpoints, a propósito. El
historial es solo lectura y la app no debe insinuar lo contrario con un icono de lápiz.

### 6.4 Panel médico

`GET /visita/medicos` (el panel del VM) y `GET /visita/medicos/{id}` (ficha).

- **Lista** con buscador, filtro por clasificación (A/B/C/D) y por estado
  (aprobado / pendiente de aprobación / de baja).
- **Ficha**: nombre, especialidad, centro médico, provincia/municipio, clasificación,
  frecuencia planeada y su historial de visitas.
- **Agregar un médico**: primero `GET /visita/medicos/existentes` — busca en el maestro
  para **no duplicar**; si ya existe, se copia la ficha al panel. Solo si no existe se
  crea con `POST /visita/medicos`.
- **Un alta queda PENDIENTE hasta que el Gerente de Distrito la aprueba**
  (`/visita/aprobaciones`, `/visita/medicos/{id}/aprobar`). La app lo dice con esas
  palabras y marca la ficha con un distintivo «Pendiente de aprobación». Un médico
  pendiente **sí** se puede visitar; lo que está pendiente es su alta en el maestro.
- **Baja y reactivación**: `POST /visita/medicos/{id}/baja` y `/reactivar`, con motivo.
- **Clasificación**: `GET/PUT /visita/medicos/{id}/clasificacion`. Cambiarla genera una
  **solicitud** que resuelve el gerente (`/visita/medicos/cambios/{id}/resolver`), no un
  cambio inmediato. La app no debe pintar el valor nuevo como si ya estuviera aplicado.

### 6.5 Panel de farmacias

`GET /farmacias/panel`, `GET /farmacias/cobertura`.

- Alta con antiduplicado: `GET /farmacias/maestro/buscar` → `POST /farmacias/panel/agregar`
  (existe en el maestro) o `POST /farmacias/panel/crear` (no existe). Mismo flujo de
  aprobación por el gerente.
- **Registrar visita a farmacia**: `POST /farmacias/{panel_id}/visita`, con foto opcional
  por `POST /farmacias/{visita_id}/foto` (mismos límites: JPEG/PNG, 3 MB).
- **Guarda F22**: solo se puede registrar sobre una farmacia **aprobada** en el panel y
  **activa** en el maestro. La app filtra la lista para que las no elegibles ni siquiera
  aparezcan como opción, en vez de dejar que el servidor las rechace.

### 6.6 Plan — la planeación del ciclo

`GET /visita/planeacion`, `POST /visita/planeacion`,
`GET /visita/planeacion/estado`, `POST /visita/planeacion/publicar`.

El VM programa, por cada médico de su panel, en qué **semana** del ciclo lo verá. Tres
reglas que el servidor impone y que la app debe impedir antes de enviar, señalando la
fila exacta:

- **P01** — máximo 2 registros por médico en el ciclo: **una Vista y una Revisita**.
- **P02** — la Revisita va en una semana **igual o posterior** a la de la Vista.
- **P03** — Vista y Revisita **no el mismo día**.

Además:

- **Publicar congela el plan.** Una vez publicado no se edita; solo el gerente puede
  desbloquearlo (`POST /visita/planeacion/desbloquear`). La app muestra el estado
  publicado/borrador de forma permanente, y en publicado los controles se apagan **con el
  motivo escrito**, no simplemente en gris.
- **Médicos TOP sin planear**: el servidor los expone aparte. Son la primera cosa que debe
  ver el VM al abrir la pantalla, no un dato escondido al final.
- `GET /visita/planeacion/resumen` da el conteo por semana para la cabecera.

### 6.7 Ruptura y cierre — solo lectura en el móvil

`GET /visita/ruptura` muestra los médicos del panel **sin visita en el ciclo**. Es la
lista de trabajo pendiente del VM y por eso va en el móvil. El **cierre** del ciclo
(`POST /visita/cierre`) es del gerente: **no va en la app**.

### 6.8 Muestras

`POST /visita/muestras` y `GET /visita/muestras/resumen`. Entrega de muestras por producto
en una visita. Va como paso opcional al final del registro, no como pantalla aparte.

### 6.9 Perfil

Nombre, rol, país, línea y gerente (`GET /visita/mi-gerente`). Cambiar contraseña, ver la
cola de sincronización, forzar la descarga de catálogos, enviar diagnóstico y cerrar
sesión. Versión de la app y del servidor.

---

## 7. Permisos de Android

| Permiso | Para qué | Cuándo se pide |
|---|---|---|
| `INTERNET`, `ACCESS_NETWORK_STATE` | API y estado de red | Instalación |
| `ACCESS_COARSE_LOCATION`, `ACCESS_FINE_LOCATION` | GPS de la visita | La primera vez que se registra una visita, explicando para qué |
| `CAMERA` | Foto del centro | La primera vez que se toma una foto |
| `POST_NOTIFICATIONS` | Aviso de pendientes por vencer | Al primer pendiente |

Se piden **en contexto y con explicación**, nunca todos de golpe al abrir. Si el VM
deniega ubicación o cámara, la app **sigue funcionando**: son campos opcionales. Nada
justifica bloquear la captura por un permiso denegado.

---

## 8. Errores: qué decir y qué no

- **409 con mensaje del servidor** → mostrar el mensaje tal cual, en un aviso persistente.
  Son reglas de negocio (ciclo cerrado, captura deshabilitada, plan publicado) y el texto
  ya está redactado para el usuario final.
- **422** → señalar el campo concreto y **conservar lo escrito**.
- **401** → un intento de refresh; si también falla, a la pantalla de entrada **sin borrar
  la cola local**.
- **Sin respuesta HTTP** → «Sin conexión. Guardado en tu teléfono, se enviará solo.»
  Jamás traducir un fallo de red a un error de datos o de credenciales.
- **403** → «No tienes permiso para esta operación», y registrar en el log local qué
  endpoint fue. Un botón gris nunca es la forma de comunicar una falta de permiso: si el
  rol no la tiene, la acción no se dibuja.

---

## 9. Fuera de alcance de la primera entrega

Nada de esto va en el móvil, y decirlo evita la discusión a mitad de camino: cierre de
ciclo, aprobación de altas, edición de la parrilla, costos y ROI, matriz LSII, exámenes,
rankings, tableros ejecutivos, administración de catálogos. Todo eso es trabajo de
escritorio y ya vive en la suite web.

---

## 10. Criterios de aceptación

La entrega se considera terminada cuando, **verificado sobre un teléfono real y no en el
emulador**:

1. Un VM registra una visita completa —médico, tipo, comentario, GPS y foto— en **menos de
   20 segundos** desde la pantalla de inicio.
2. En **modo avión**: se registran tres visitas y una visita a farmacia, la app confirma
   cada una, y al recuperar la red las cuatro suben **sin duplicados** y en orden.
3. Una visita en cola con más de 60 minutos de antigüedad se marca en rojo con el motivo,
   **no** se envía en silencio ni se borra.
4. Con `MODO_INGESTA=integracion` la app entra en modo consulta: **ningún** botón de
   registro visible, y un aviso explicando por qué.
5. Con el ciclo cerrado, la captura queda apagada **con el motivo del servidor escrito en
   pantalla**.
6. La planeación rechaza P01, P02 y P03 **en el teléfono**, señalando la fila, antes de
   enviar nada.
7. Los colores y el logotipo salen de `/admin/config/marca`: cambiando la identidad en el
   servidor y reabriendo la app, la app cambia — sin recompilar.
8. Al sol directo se leen todas las etiquetas de la barra inferior y de la agenda.
9. Un médico sin planeación muestra «—», nunca «0%».
10. Cerrar sesión y volver a entrar **no pierde** los pendientes de la cola.

---

## 11. Orden de construcción sugerido

1. **Fase 0** — reabrir la captura en el backend con el interruptor por instalación (§0).
2. Esqueleto MAUI, DI, tema desde `/admin/config/marca`, entrada y sesión.
3. SQLite, catálogos y descarga inicial.
4. Hoy + Registrar visita médica **en línea**.
5. Cola sin conexión, `uuid_cliente` y reintentos.
6. Panel médico y alta con antiduplicado.
7. Panel de farmacias y su registro.
8. Planeación con P01-P03.
9. Foto, GPS y muestras.
10. Ruptura, Perfil, diagnóstico y pulido de campo.
