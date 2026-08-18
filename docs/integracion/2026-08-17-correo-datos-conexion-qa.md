# Correo a Mallén — datos de conexión al ambiente de calidad

> **La contraseña de `mallen_etl` NO va en este archivo ni en este repositorio (que es público).**
> Se envía por un canal aparte —llamada, WhatsApp o un segundo correo— nunca en el mismo
> mensaje que lleva host, puerto y usuario. Juntos, esos cuatro datos dan acceso completo a
> la capa de recepción a cualquiera que lea el correo o lo tenga reenviado.

**Asunto:** VISTA — ambiente de calidad listo para las pruebas de carga

**Adjunto:** `crear_esquema_ext.sql`

---

Buenos días,

El ambiente de calidad de VISTA ya está montado en el servidor SRVDVKPI y la capa de
recepción (esquema `ext`) está creada y disponible para que empiecen a subir información.

**Datos de conexión**

| | |
|---|---|
| Host | `192.168.5.21` |
| Puerto | `5432` |
| Base de datos | `scgcpr` |
| Usuario | `mallen_etl` |
| Cifrado | `sslmode=require` (obligatorio) |

La contraseña se la hago llegar por otra vía.

**Sobre el adjunto**

`crear_esquema_ext.sql` trae las 22 tablas de la capa de recepción con sus llaves e
índices, tal como quedaron en el servidor. Se los envío para que puedan replicar el
esquema en su ambiente y probar el mapeo antes de conectarse.

**Tres puntos a tener en cuenta**

1. El usuario `mallen_etl` está encerrado en el esquema `ext`: escribe ahí y no ve nada
   más de la base. Si intentan leer otra tabla les va a dar permiso denegado — es lo
   esperado, no un problema de configuración.
2. La conexión exige TLS. Sin `sslmode=require` en la cadena, el servidor rechaza.
3. VISTA nunca se conecta hacia su SQL Server. Todo lo que viaja lo empuja el proceso de
   carga de ustedes por ODBC contra estas tablas.

Cuando hagan la primera carga me avisan y validamos juntos que los datos estén llegando
completos.

Quedo pendiente.

Saludos,
Moisés Segura
