-- ===========================================================================
-- VISTA · Laboratorios Mallen — usuario de integracion
-- ===========================================================================
-- Requerimiento de Datos v1.0, seccion 8.2.
--
-- Es el control que impide que un error de la integracion toque el resto del
-- sistema: este usuario solo alcanza el esquema `ext`. Correr DESPUES de
-- crear_esquema_ext.sql, conectado como superusuario o dueno de la base.
--
-- ANTES DE EJECUTAR: reemplazar CLAVE_A_DEFINIR por la clave que entregue
-- Laboratorio Mallen. No dejarla escrita en ningun archivo versionado ni
-- enviarla por correo; cada ambiente (calidad y produccion) lleva la suya.
-- ===========================================================================

CREATE USER mallen_etl WITH PASSWORD 'CLAVE_A_DEFINIR';

GRANT USAGE ON SCHEMA ext TO mallen_etl;
GRANT SELECT, INSERT, UPDATE ON ALL TABLES IN SCHEMA ext TO mallen_etl;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA ext TO mallen_etl;

-- ---------------------------------------------------------------------------
-- IMPRESCINDIBLE, y no esta en el documento: los GRANT de arriba solo alcanzan
-- a las tablas que EXISTEN en este momento. Cualquier tabla que se agregue
-- despues a `ext` nacera sin permisos y la carga de Mallen fallara con
-- "permiso denegado" sobre una tabla que a simple vista esta bien creada.
-- ALTER DEFAULT PRIVILEGES hace que los permisos se apliquen tambien a las
-- futuras. Debe ejecutarlo el MISMO rol que crea las tablas (el dueno del
-- esquema): los privilegios por defecto se registran por rol creador.
-- ---------------------------------------------------------------------------
ALTER DEFAULT PRIVILEGES IN SCHEMA ext
    GRANT SELECT, INSERT, UPDATE ON TABLES TO mallen_etl;
ALTER DEFAULT PRIVILEGES IN SCHEMA ext
    GRANT USAGE, SELECT ON SEQUENCES TO mallen_etl;

-- ---------------------------------------------------------------------------
-- Sin DELETE, a proposito (seccion 8.2): una correccion se hace reenviando el
-- registro con el mismo origen_id, nunca borrando, para que la trazabilidad del
-- lote quede intacta.
--
-- Tampoco recibe permisos sobre los demas esquemas: no puede leer ni escribir
-- las tablas internas de VISTA. Se revoca ademas la creacion de objetos en
-- `public`, que en instalaciones antiguas de PostgreSQL viene abierta a todos.
-- ---------------------------------------------------------------------------
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
REVOKE ALL ON SCHEMA public FROM mallen_etl;

-- ===========================================================================
-- Comprobacion: debe devolver exactamente SELECT, INSERT y UPDATE, y nada mas.
-- ===========================================================================
-- SELECT table_name, string_agg(privilege_type, ', ' ORDER BY privilege_type)
-- FROM information_schema.table_privileges
-- WHERE grantee = 'mallen_etl'
-- GROUP BY table_name ORDER BY table_name;
--
-- Y esta debe fallar con "permiso denegado", que es la prueba de que el
-- aislamiento funciona:
-- SELECT * FROM "Config"."DIM_RM" LIMIT 1;   -- ejecutada como mallen_etl
