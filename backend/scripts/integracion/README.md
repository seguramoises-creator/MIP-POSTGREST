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
| `generar_ddl_ext.py` | Regenera el `.sql` desde los modelos. **El `.sql` no se edita a mano** |

En producción el esquema lo crea la migración `0030_esquema_ext_integracion`,
no estos scripts: son la copia que Mallén replica y la referencia del contrato.
`tests/test_integracion_ext.py` compara el `.sql` con los modelos, así que no
pueden divergir sin que falle la suite.

## Puesta en marcha de un ambiente

1. Aplicar migraciones (`alembic upgrade head`) — crea `ext` con sus 22 tablas.
2. Ejecutar `crear_usuario_mallen.sql` **reemplazando antes** `CLAVE_A_DEFINIR`
   por la clave que entregue Mallén. Cada ambiente lleva la suya.
3. Entregar a Mallén: `crear_esquema_ext.sql`, el usuario y el puerto 5432
   abierto **solo** desde la IP de su SQL Server, con TLS (`sslmode=require`).
4. Comprobar el aislamiento: conectado como `mallen_etl`, un
   `SELECT * FROM "Config"."DIM_RM"` debe fallar con permiso denegado.

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
