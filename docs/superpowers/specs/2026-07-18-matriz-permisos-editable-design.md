# Matriz de permisos editable (RBAC administrable desde la UI) — Diseño

**Fecha:** 2026-07-18 · **Estado:** aprobado por el cliente · **Ámbito:** edición PostgreSQL (vista-mip.com)

## Objetivo

Permitir que el **ADMIN edite la matriz de roles/permisos desde la pantalla** "Roles y
Permisos" (tab de Administración) y que el sistema **aplique los cambios en caliente**, sin
redeploy. La base de datos (`Security.FACT_RolPermiso`) pasa a ser la **fuente de verdad en
runtime**; `app/core/authz/matrix.py` queda como **valores de fábrica** (para el bootstrap
inicial y para un botón "Restablecer").

## No-objetivos

- No cambia el **catálogo de recursos** (`RECURSOS_META`, 32 funcionalidades): son estructurales,
  definidos en código. La UI no crea/borra recursos ni acciones.
- No toca `scope.py` (filtrado de datos own/team/all) ni las reglas de derivación del motor.
- No cambia la pantalla `/admin` (catálogos de sistema).
- No agrega roles nuevos (los 13 del enum `Rol` siguen fijos).

## Situación actual (por qué hoy es solo lectura)

- `engine.can(user, accion, recurso)` lee la matriz **en memoria desde el código**
  (`matrix.MATRIZ`). No consulta la BD.
- `Security.FACT_RolPermiso` (columnas `rol, recurso, accion, alcance`, único `(rol,recurso,accion)`)
  es hoy un **espejo** sembrado desde el código (`seed.sembrar_todo`, manual vía `scripts/seed_authz.py`).
- **El sembrado NO corre en el arranque** (solo migraciones `alembic upgrade head`). → pasar la BD
  a fuente de verdad no se sobrescribe solo.

## Arquitectura

### 1. Fuente de verdad en runtime (BD + caché)

Nuevo módulo `app/core/authz/runtime.py`:
- Caché en memoria de proceso: `_CACHE: {recurso: {rol_str: (Accion, Alcance)}}` + `_version`.
- `cargar(db)`: relee `FACT_RolPermiso` → `_CACHE`; fija `_version = MAX(actualizado_en)`.
- `refrescar_si_cambio(db)`: consulta barata `SELECT MAX(actualizado_en)`; si difiere de `_version`,
  recarga. (Robusto ante múltiples workers.)
- `celda(rol, recurso)`: lee del caché (reemplaza a `matrix._celda`).

`engine._celda` pasa a delegar en `runtime.celda`. Las reglas de derivación
(`admin ⇒ all`, `configure/approve/register ⇒ read`, export independiente) **no cambian**:
siguen en `engine.can` / `alcance_export_modulo`.

### 2. Los guards refrescan el caché

`deps.require/autorizar/autorizar_export` (y `authz.mis_permisos` / `ver_matriz`) reciben
`db: Session = Depends(get_db)` dentro de su `_dep` y llaman `runtime.refrescar_si_cambio(db)`
antes de evaluar. Coste: 1 query indexada por request protegido. Las **firmas de los endpoints no
cambian** (la inyección es interna al `_dep`). En el arranque (`lifespan`) se hace `runtime.cargar`
una vez.

### 3. Escritura (solo ADMIN, auditada)

Router `authz.py`:
- `PUT /authz/matriz` — body `{cambios: [{rol, recurso, accion|null, alcance|null}, ...]}`.
  Por cada cambio, dentro de **una transacción**:
  - Rechaza `rol == "ADMIN"` → 400 (columna Superadmin inmutable).
  - Valida `rol ∈ Rol`, `recurso ∈ RECURSOS_META`, `accion ∈ Accion|null`,
    `alcance ∈ {own,team,all}` cuando hay acción; `accion=null` ⇒ **borrar** las filas de
    `(rol,recurso)` (denegación por defecto).
  - Upsert/borrado en `FACT_RolPermiso` (regla: 1 fila base por celda; se reemplaza la anterior).
  - Audita cada celda: `registrar_evento_seguridad(evento="PERMISO_MODIFICADO", recurso, accion,
    alcance, objetivo=f"rol:{rol}", detalle="antes=… nuevo=…")`.
  - `actualizado_en = now()` en las filas tocadas (bumpea la versión del caché).
  - `runtime.cargar(db)` al final. Devuelve la matriz nueva (mismo shape que GET).
- `POST /authz/matriz/restablecer` — reaplica `matrix.py` (`seed.sembrar_todo`, que ya hace
  delete-then-sync), audita `evento="PERMISOS_RESTABLECIDOS"`, `runtime.cargar(db)`.

`GET /authz/matriz` pasa a leer del runtime (BD) e incluye por cada rol un flag `editable`
(false solo para ADMIN).

### 4. Salvaguardas

- **Superadmin (ADMIN) inmutable**: el endpoint rechaza cambios sobre esa columna; su acceso total
  se preserva en `engine.can` (`admin ⇒ all`), no depende de filas de BD.
- **Denegación por defecto** intacta: quitar una celda = borrar filas; ausencia = sin acceso.
- **Auditoría** de cada celda modificada y de cada restablecimiento (tabla existente
  `Security.FACT_AuditoriaSeguridad`).
- **Bootstrap sin auto-pisado**: el arranque solo carga el caché; el sembrado inicial sigue por
  script. Restablecer es explícito.

### 5. Migración

`0019_rolpermiso_actualizado_en`: agrega `Security.FACT_RolPermiso.actualizado_en TIMESTAMP`
(nullable→backfill `now()`→se usa como versión). Sin otros cambios de esquema.

### 6. Frontend (`MatrizRoles.tsx`)

- Botón **"Editar"** (solo visible/activo para ADMIN) alterna modo edición.
- En edición, cada celda editable = dos `Select` compactos: **Acción** (—/Ver/Registrar/
  Configurar/Aprobar/Exportar) + **Alcance** (propio/equipo/todo, oculto si acción es — o Admin).
  La **columna Superadmin queda bloqueada** (chip "Admin", no editable).
- Estado *dirty*; botones **"Guardar cambios"** (envía solo el diff a `PUT`), **"Descartar"**
  (revierte al último cargado) y **"Restablecer a valores de fábrica"** (con diálogo de confirmación
  → `POST /restablecer`). Tras guardar: toast + refetch.
- Fuera de edición se mantiene la vista de solo lectura actual (colores + búsqueda + resaltado).

## Pruebas

- `runtime`: `cargar` arma el caché; `refrescar_si_cambio` recarga al cambiar la versión.
- `engine`: `can` lee del caché de BD (un cambio en BD altera la decisión).
- `PUT /authz/matriz`: aplica, audita, rechaza columna ADMIN (400), `accion=null` borra la celda.
- `POST /restablecer`: vuelve a los valores de `matrix.py`.
- RBAC del endpoint: no-ADMIN → 403.
- **Se conserva** `test_authz_matriz.py` (oráculo): sigue validando que `matrix.py` (los valores de
  fábrica) coincide con el spec §5. La suite de wiring (403 por rol) sigue verde porque, tras el
  seed/fábrica, la BD == `matrix.py`.

## Despliegue

Construir y probar **en local**; luego `git pull && docker compose --profile with-db up -d --build`.
La migración corre sola al arrancar. La BD ya tiene los permisos sembrados; la columna nueva se
backfillea. **No hace falta re-seed** salvo que se quiera volver a fábrica.

## Riesgo

Toca el núcleo de autorización de toda la app. Mitigación: Superadmin inmutable, denegación por
defecto, auditoría, pruebas, y rollout local-primero. Un `POST /restablecer` devuelve todo a los
valores de fábrica si algo queda mal configurado.
