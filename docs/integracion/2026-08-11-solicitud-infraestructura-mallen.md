# Solicitud de infraestructura — VISTA en Laboratorios Mallén

**Fecha:** 11-ago-2026
**Referencia:** Requerimiento de Datos · VISTA · Laboratorios Mallén v2, §8 y §9
**Objetivo:** habilitar el ambiente de **calidad** para que Laboratorio Mallén comience a enviar información de prueba al esquema `ext`.

---

## 1. Qué se pide

Conforme al §9 del requerimiento firmado, **la solución completa se aloja en la infraestructura de Laboratorio Mallén** — tanto los servidores de VISTA como el SQL Server desde el que se escribe la integración.

Se requieren **dos ambientes separados**: calidad y producción. **Para empezar las pruebas basta con calidad.**

## 2. Servidores (§9.1)

| Recurso | Calidad (para empezar) | Producción |
|---|---|---|
| Procesador | 4 vCPU | 8 vCPU |
| Memoria RAM | 8 GB | 16 GB |
| Disco | 100 GB SSD | 250 GB SSD, ampliable |
| Sistema operativo | Debian 13 | Debian 13 |
| Base de datos | PostgreSQL 17 | PostgreSQL 17 |
| Contenedores | Docker Engine 24+ y Docker Compose v2 | Docker Engine 24+ y Docker Compose v2 |
| Respaldo | No obligatorio | Diario, retención mínima 30 días |
| Disponibilidad | Horario laboral | Continua |

El dimensionamiento de producción contempla la operación actual —unos 100 representantes y 10.000 médicos— con margen de crecimiento. Si se incorporan más países o líneas, conviene revisar la memoria antes de escalar el procesador.

## 3. Red y puertos (§9.3)

| Puerto | Uso | Exposición |
|---|---|---|
| 443 | Acceso web de los usuarios | Según política de Mallén: interna o publicada |
| 80 | Redirección a HTTPS | La misma que el 443 |
| **5432** | **Escritura de la integración** | **Únicamente desde la IP del servidor de SQL Server** |
| 22 | Administración | Únicamente desde la VPN corporativa |
| Puerto interno del servicio web | Publicación hacia el servidor web del host | Solo en `127.0.0.1`, nunca a la red |

**El 5432 no debe exponerse a internet en ningún caso.** Como el SQL Server y el servidor de VISTA estarán en la misma red interna de Mallén, la conexión de la integración es interna: no hace falta abrir nada hacia afuera.

## 4. Requisitos adicionales (§9.4)

- **Un nombre de dominio por ambiente**, con su certificado TLS. El certificado corre a cargo de Laboratorio Mallén.
- **Servidor de correo saliente o cuenta SMTP**, para las notificaciones del sistema (avisos de aprobación, recordatorios de médicos TOP, resultados de exámenes).
- **Acceso VPN para el equipo de VISTA**, en calidad y en producción, para despliegue y soporte.
- **Credenciales y clave de firma propias por ambiente** — no se reutilizan entre calidad y producción.
- **Zona horaria del servidor** configurada en la del país de operación.

## 5. Qué instala VISTA (§9.2)

No hay que preparar nada de esto: lo instala VISTA sobre el Docker del servidor.

| Componente | Función |
|---|---|
| Contenedor de base de datos | PostgreSQL 17 con volumen persistente |
| Contenedor de aplicación | API de VISTA — **no se publica a la red**, solo la alcanza el servicio web |
| Contenedor de servicio web | Interfaz web y proxy hacia la API |
| Servidor web del host | Termina el TLS y publica el sitio |

Es la misma arquitectura con la que VISTA opera hoy. No se incorpora ningún componente nuevo.

## 6. Orden de puesta en marcha (§9.5)

El orden importa: **las credenciales de la integración se entregan después de instalar**, no antes.

1. **Laboratorio Mallén** prepara los servidores según esta especificación y habilita la VPN.
2. **VISTA** instala el sistema y crea el esquema, incluida la capa `ext` (22 tablas).
3. **VISTA** entrega las credenciales del usuario de integración (`mallen_etl`).
4. **Laboratorio Mallén** desarrolla y prueba su proceso de carga **contra calidad**.
5. Se valida un ciclo completo en calidad, **comparando los indicadores con la fuente**.
6. Se replica en producción y se cargan los datos históricos acordados.

## 7. Lo que Mallén necesitará de su lado

Para el paso 4, en su servidor de SQL Server:

- **Controlador psqlODBC 13 o superior** (o **Npgsql**, si el ETL es .NET).
- Conexión con **`sslmode=require`** — TLS obligatorio (§8.1).
- **Inserción por lotes** (`COPY` o inserciones agrupadas), no fila por fila.
- Destino: **únicamente el esquema `ext`**. Nombres en **minúsculas y sin comillas** (`ext.controlcarga`, `ext.panelmedico`, …).

**Permisos del usuario `mallen_etl`** (§8.2): `SELECT`, `INSERT`, `UPDATE`. **Sin `DELETE`, a propósito** — una corrección se hace reenviando el registro con el mismo `origen_id`, nunca borrando, para que la trazabilidad del lote quede intacta.

**Orden de carga**: primero las 9 dimensiones (`ext.dim*`), luego abrir el lote en `ext.controlcarga` con estado `RECIBIDO`, y después los hechos amarrados a ese `lote_id`. Las claves foráneas rechazan un hecho cuya dimensión no haya llegado antes.

El estado del lote lo mueve VISTA, no Mallén: de `RECIBIDO` pasa a `VALIDADO` o `RECHAZADO`, y finalmente a `INTEGRADO`.

---

## 8. Dos puntos que conviene cerrar en la misma conversación

**El piloto actual.** Hoy VISTA opera en un servidor propio (`vista-mip.com`) con datos reales de prueba. Hay que decidir si esos datos se migran al ambiente de producción de Mallén o si se arranca limpio y se cargan los históricos acordados (paso 6).

**Los dos pendientes abiertos del §10 que afectan a lo ya construido:**

- **Nº 8 — Momento del recordatorio y del escalamiento por médico TOP no visitado.** VISTA opera hoy con **2 días hábiles** tras la fecha planeada para avisar al representante y **50% del ciclo transcurrido** para escalar al Gerente de Distrito. Son valores de VISTA, configurables desde la propia aplicación; basta que Mallén confirme o proponga otros.
- **Nº 9 — Quién marca a un médico como TOP.** **Resuelto**: lo define Laboratorio Mallén desde `ext.panelmedico.prioridad`. Ni el Gerente de Distrito ni el representante lo marcan en VISTA.
