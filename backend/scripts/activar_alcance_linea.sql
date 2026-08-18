-- Activa el alcance de LINEA en una instalacion YA sembrada (sub-proyecto 8, ago-2026).
--
-- POR QUE HACE FALTA ESTE SCRIPT
-- La matriz RBAC vive en Security.FACT_RolPermiso y esa tabla es la fuente de verdad en
-- runtime; `matrix.py` solo aporta los valores de fabrica. El entrypoint del contenedor
-- siembra la matriz UNICAMENTE cuando DIM_Usuario esta vacia, asi que en un servidor que
-- ya tiene usuarios (calidad de Mallen, produccion) las celdas nuevas NO llegan solas.
--
-- NO USAR "Restablecer a fabrica" desde la UI para esto: esa accion sincroniza con borrado
-- y revierte cualquier permiso afinado a mano en ese servidor. Este script toca 6 celdas
-- y nada mas.
--
-- QUE CAMBIA (decision de la gerencia de Mallen: "acceso sobre sus lineas asignadas, todo el pais")
--   cobertura.predictiva  | GERENTE_DISTRITO: team -> linea   | GERENTE_MARCA: all -> linea
--   productividad.comercial| idem                              | idem
--   ranking.rkt           | idem                              | idem
-- Para el Gerente de Distrito es una AMPLIACION (de su equipo a su linea completa);
-- para el Gerente de Marca es una RESTRICCION (de todo el pais a solo su linea).
--
-- LA TRAMPA: `actualizado_en` tiene onupdate del lado de Python (SQLAlchemy), no un trigger
-- del motor. Un UPDATE crudo que no lo fije explicitamente deja el sello igual, el caché de
-- cada worker no detecta cambio (`MAX(actualizado_en)`) y la matriz sigue sirviendose vieja
-- hasta el proximo reinicio. Por eso el SET de abajo lo escribe a mano. No quitarlo.
--
-- USO (en el servidor):
--   docker compose exec -T db psql -U segura -d scgcpr -f - < activar_alcance_linea.sql
-- o, si el archivo ya esta dentro del contenedor:
--   docker compose exec db psql -U segura -d scgcpr -f /ruta/activar_alcance_linea.sql

BEGIN;

-- 1) Antes: deja constancia en el log de psql de como estaban las celdas.
\echo '--- ANTES ---'
SELECT recurso, rol, accion, alcance, actualizado_en
  FROM "Security"."FACT_RolPermiso"
 WHERE recurso IN ('cobertura.predictiva', 'productividad.comercial', 'ranking.rkt')
   AND rol     IN ('GERENTE_DISTRITO', 'GERENTE_MARCA')
 ORDER BY recurso, rol;

-- 2) El cambio. Acotado por recurso Y por rol: ninguna otra celda se toca.
UPDATE "Security"."FACT_RolPermiso"
   SET alcance        = 'linea',
       actualizado_en = NOW() AT TIME ZONE 'UTC'   -- sella el cache; ver nota arriba
 WHERE recurso IN ('cobertura.predictiva', 'productividad.comercial', 'ranking.rkt')
   AND rol     IN ('GERENTE_DISTRITO', 'GERENTE_MARCA')
   AND accion  = 'read'
   AND alcance <> 'linea';                          -- idempotente: re-ejecutar no hace nada

-- 3) Despues: deben quedar 6 filas en 'linea'. Si salen menos, la instalacion no tenia
--    alguna de esas celdas sembradas (revisar antes de commitear).
\echo '--- DESPUES ---'
SELECT recurso, rol, accion, alcance, actualizado_en
  FROM "Security"."FACT_RolPermiso"
 WHERE recurso IN ('cobertura.predictiva', 'productividad.comercial', 'ranking.rkt')
   AND rol     IN ('GERENTE_DISTRITO', 'GERENTE_MARCA')
 ORDER BY recurso, rol;

COMMIT;

-- No hace falta reiniciar el backend: cada worker recarga su cache en la siguiente
-- peticion al ver que avanzo MAX(actualizado_en).
