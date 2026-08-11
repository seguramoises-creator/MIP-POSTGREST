# Integración con Laboratorio Mallén — esquema `ext`

Capa de recepción donde **Mallén escribe y VISTA lee**. Implementa el
*Requerimiento de Datos · VISTA · Laboratorios Mallén* v1.0 (25-jul-2026).

VISTA nunca se conecta al SQL Server de Mallén: todo lo que viaja lo empuja su
proceso de carga por ODBC contra estas tablas.

## Qué hay aquí

| Archivo | Para qué |
|---|---|
| `crear_esquema_ext.sql` | Las 22 tablas con sus claves e índices. **Se entrega a Mallén** para que repliquen el esquema en su ambiente de pruebas |
| `crear_usuario_mallen.sql` | El usuario `mallen_etl`, limitado al esquema `ext` |
| `generar_certificado_pg.sh` | Certificado TLS autofirmado para PostgreSQL (`sslmode=require`, §8.1) |
| `generar_ddl_ext.py` | Regenera el `.sql` desde los modelos. **El `.sql` no se edita a mano** |

En producción el esquema lo crea la migración `0030_esquema_ext_integracion`,
no estos scripts: son la copia que Mallén replica y la referencia del contrato.
`tests/test_integracion_ext.py` compara el `.sql` con los modelos, así que no
pueden divergir sin que falle la suite.

## Puesta en marcha de un ambiente

1. Aplicar migraciones (`alembic upgrade head`) — crea `ext` con sus 22 tablas.
   Con Docker esto ocurre solo al arrancar el contenedor del backend.
2. **Habilitar TLS** (§8.1 — sin esto el ETL de Mallén no conecta):
   ```bash
   bash backend/scripts/integracion/generar_certificado_pg.sh
   docker compose --profile with-db up -d db
   docker compose exec -T db psql -U segura -d scgcpr -Atc 'SHOW ssl;'   # debe decir: on
   ```
   El `docker-compose.yml` activa TLS **solo si encuentra el certificado**; un
   servidor sin él arranca igual que siempre. Es deliberado: con `ssl=on` fijo,
   un despliegue sin certificados dejaría la base sin arrancar.
3. **Publicar el 5432 hacia el SQL Server** — ver la sección siguiente.
4. Ejecutar `crear_usuario_mallen.sql` **reemplazando antes** `CLAVE_A_DEFINIR`
   por la clave que entregue Mallén. Cada ambiente lleva la suya.
5. Entregar a Mallén: `crear_esquema_ext.sql`, el usuario, el host y el puerto.
6. Comprobar el aislamiento: conectado como `mallen_etl`, un
   `SELECT * FROM "Config"."DIM_RM"` debe fallar con permiso denegado.

## Abrir el 5432 solo al SQL Server (y por qué ufw no basta)

El compose base **no publica el 5432**: hacerlo rompería cualquier servidor que ya
tenga otro PostgreSQL en ese puerto (el piloto de VISTA es justo ese caso — el
contenedor no arrancaría). La publicación vive en un override aparte, que solo se
usa en los ambientes de Mallén:

```bash
export DB_BIND_ADDR=<IP interna del servidor de VISTA>
docker compose -f docker-compose.yml -f docker-compose.integracion.yml \
    --profile with-db up -d --build
```

Sin `DB_BIND_ADDR` queda en `127.0.0.1`, que no alcanza a nadie fuera del host:
seguro, pero inservible para la integración. Con la IP interna, el puerto queda
alcanzable desde la red de Mallén, así que **hay que restringir el origen**.

**`ufw` no sirve aquí.** Docker escribe sus propias reglas de `iptables` en la
tabla `nat` y el tráfico hacia un puerto publicado **se salta las reglas de ufw**:
la regla parece aplicada, `ufw status` la muestra, y el puerto sigue abierto a
todo el mundo. Es una de las confusiones más caras de Docker en producción.

Lo que sí funciona es la cadena `DOCKER-USER`, que Docker consulta antes que las
suyas y no reescribe:

```bash
# Permitir solo al SQL Server de Mallén
sudo iptables -I DOCKER-USER -p tcp --dport 5432 -s <IP_DEL_SQL_SERVER> -j ACCEPT
# Y bloquear al resto
sudo iptables -I DOCKER-USER -p tcp --dport 5432 -j DROP
```

El orden importa: `-I` inserta al principio, así que **la regla de ACCEPT debe
insertarse después** para quedar por encima del DROP. Compruébalo con
`sudo iptables -L DOCKER-USER -n --line-numbers`.

Estas reglas **no sobreviven a un reinicio** por sí solas: persístelas con
`iptables-persistent` (`netfilter-persistent save`) o vuelve a aplicarlas desde
el arranque. Un reinicio del servidor con las reglas perdidas deja la base
expuesta sin que nada lo avise.

## Tres diferencias respecto al DDL impreso en el documento

Están explicadas en detalle en el encabezado del `.sql` y en el docstring de
`app/models/integracion_ext.py`. En resumen:

1. **Los nombres van en minúsculas y sin comillas.** El documento crea las
   tablas sin comillas —y PostgreSQL pliega ese nombre a minúsculas— pero
   después las referencia entrecomilladas en las claves foráneas y los índices,
   lo que exige mayúsculas exactas. Ejecutado en ese orden, el script del
   documento falla en la primera sentencia de la sección 6.4. Se unificó sin
   comillas porque así `ext.DimPais`, `ext.dimpais` y `EXT.DIMPAIS` funcionan
   las tres, desde cualquier herramienta.
2. **Se añadieron las claves foráneas que el documento omite** explícitamente
   "por brevedad" al final de §6.4: `lote_id`, ciclo y representante en el resto
   de las tablas de hecho.
3. **Se añadieron dos índices únicos** `(pais_codigo, origen_id)`, en
   `factevaluacionconocimiento` y `factprescripciondetalle`. La §5.2 exige
   idempotencia para todos los hechos, pero la §6.5 solo los declaraba para
   tres: sin ellos, reenviar uno de esos dos lotes duplicaría filas en silencio.

Los dominios acotados (`tipo_visita`, `frecuencia_objetivo`, `prioridad`,
`estado`) **no llevan CHECK a propósito**: la §7.1 pide que las inconsistencias
se registren "sin detener el lote completo", y un CHECK rechazaría la fila.
Se validan al integrar.

## Lo que todavía no está

Esta es la **Fase A**: el esquema y el usuario, que es lo que desbloquea a
Mallén para desarrollar su carga. Falta el proceso de integración de §7.1
(validar, integrar, recalcular, cerrar el lote), las reglas de médicos TOP de
§7.3, y el módulo IR, cuya estructura sigue preliminar hasta que Close-Up
entregue la definición del indicador y el formato real del archivo.
