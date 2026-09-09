# VISTA Campo — app Android del Visitador Médico

.NET MAUI sobre .NET 10, **solo Android**. Consume la misma API que la suite web
(`/api/v1`), así que no define reglas de negocio propias: refleja las del servidor para
que el visitador no choque contra un error sin entender por qué.

El encargo completo, con endpoints y reglas, está en
[`docs/APP-MOVIL-VM-PROMPT.md`](../docs/APP-MOVIL-VM-PROMPT.md).

## Compilar y empaquetar

```bash
dotnet build   -f net10.0-android -c Debug
dotnet publish -f net10.0-android -c Release -p:AndroidPackageFormat=apk
```

El APK firmado (de depuración) sale en
`bin/Release/net10.0-android/publish/com.vistamip.campo-Signed.apk` (~29 MB) y se instala
en el teléfono sin cable. **Para publicar de verdad hace falta una clave de firma
propia**: la que usa esta compilación es la de depuración de Android y no sirve para
distribuir.

## Cómo está organizado

| Carpeta | Qué hay |
|---|---|
| `Modelos/` | Las entidades locales, con los atributos de SQLite |
| `Datos/` | `BaseLocal` — la base del teléfono y la cola de envíos |
| `Servicios/` | `ApiCliente`, `Sesion`, `ServicioInstalacion`, `ServicioSincronizacion` |
| `VistaModelos/` | Un modelo de vista por pantalla (MVVM, `CommunityToolkit.Mvvm`) |
| `Vistas/` | El XAML y los convertidores |

## Las tres decisiones que explican el resto

**1. Se escribe primero en el teléfono, siempre.** La pantalla confirma contra la base
local, no contra la red. El visitador termina la visita en el parqueo del edificio
médico, donde no hay señal, y necesita ver que su trabajo quedó guardado. La cola sube
sola al recuperar la conexión.

**2. Cada captura lleva una huella (`uuid_cliente`).** El caso que rompe no es «no
llegó» sino «llegó y se perdió la respuesta»: ahí el teléfono no puede distinguir un
envío perdido de uno que entró. Con la huella, el servidor reconoce el reenvío y
devuelve la visita que ya existe en vez de crear otra. Requiere la migración `0038` del
backend.

**3. La hora la pone el servidor.** La app manda «hace cuántos minutos» —calculado en el
momento del **envío**, no de la captura— y el servidor lo resta a su propio reloj. La
ventana es de **60 minutos**: pasados esos, la visita ya no se acepta, así que la cola
avisa en la propia lista desde los 45 en vez de esperar al rechazo.

## Lo que hace falta del servidor

La captura de visitas está condicionada a `MODO_INGESTA` (ver `captura_service.py` en el
backend):

- `integracion` → la app arranca en **modo consulta**: no dibuja los botones de registro
  y explica por qué. Es el caso de Laboratorios Mallén, donde las visitas llegan de su
  propio SFA.
- cualquier otro valor → captura habilitada.

## Alta de médicos y farmacias

Se dan de alta desde **Panel → «+ Médico» / «+ Farmacia»**, y ambas quedan **pendientes
de la aprobación del Gerente de Distrito**: hasta entonces existen en el panel pero no
admiten registro de visita, y la app lo dice con esas palabras.

**El alta pide conexión, y es una decisión, no una limitación.** Todo lo demás se guarda
primero en el teléfono y sube después; un alta no puede: lo primero que hace el servidor
es comprobar que ese médico o esa farmacia no existe ya, y esa comprobación vive en la
base central. Un alta guardada sin señal y enviada tres horas más tarde crearía justo el
duplicado que el mecanismo antiduplicados existe para evitar — y un duplicado en el
maestro lo arrastra el sistema entero: dos fichas del mismo médico, cobertura contada dos
veces, categorización partida. Registrar visitas, que es lo urgente en la calle, sigue
funcionando sin señal.

**Médico.** Se busca primero: si ya está en el panel de otro representante, se **copia**
la ficha en vez de reteclearla — que dos representantes visiten al mismo médico es normal
(líneas distintas), y volver a escribir dirección, teléfono y exequátur es la forma más
segura de que las dos fichas acaben distintas. La **clasificación sí la captura cada uno**,
porque el potencial de ese médico para su línea no tiene por qué ser el mismo.

El formulario de clasificación **se dibuja con lo que manda el servidor**
(`GET /categorizacion/plantilla`), nunca escrito en la app: el vocabulario es cerrado y
cambia por país (Potencial de Prescripción va «1» / «2 a 3» / «4 a 6» / «6 a 9» /
«10 o Mas»; KOL no es un sí/no). Un valor a mano no coincide con ninguna regla y el médico
quedaría **sin clasificar**. Y **la categoría no se elige ni se ve**: la calcula el sistema
al aprobar. Por eso el servidor no manda los puntajes de cada opción — si se vieran, se
podría capturar apuntando a la categoría deseada.

Si el servidor detecta un parecido, se muestran las coincidencias y decide el visitador.
Un parecido **duro** —exequátur o cédula repetidos, o el mismo nombre en el mismo centro—
no ofrece «continuar»: ahí no hay decisión que tomar.

**Farmacia.** Buscar antes de crear (regla F25): el formulario de creación no se habilita
hasta que una búsqueda vuelve vacía, y cambiar el nombre invalida la búsqueda anterior
—si no, se podría buscar una cosa y crear otra—. Si aparece, se **agrega al panel** en vez
de crearla otra vez. Al crearla, **dirección y encargado son obligatorios** (F23/F24).

## Pendiente

- **Probar en un teléfono real.** Compila y empaqueta, pero no se ha ejecutado: no hay
  aparato ni `adb` en la máquina donde se construyó. Los diez criterios de aceptación del
  encargo se verifican sobre un teléfono, no en el emulador.
- Clave de firma propia para distribuir.
- Aviso por notificación cuando una captura está por vencer.
- Editar la ficha de un médico ya dado de alta (hoy solo se consulta).
