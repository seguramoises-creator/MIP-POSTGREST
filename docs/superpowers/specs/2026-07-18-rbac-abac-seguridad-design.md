# Módulo de Seguridad RBAC/ABAC — Diseño (VISTA / Laboratorio Mallén)

**Fecha:** 2026-07-18
**Estado:** Aprobado (diseño) — pendiente escribir plan de implementación
**Repo:** MSM-postgres (edición PostgreSQL, `vista-mip.com`)

---

## 1. Objetivo

Control de acceso con **RBAC** (permisos a roles, no a personas) + **alcance de datos ABAC**
(`propio/equipo/todos`), **denegación por defecto**, aplicado en **backend Y frontend**, con
**auditoría separada** de acciones sensibles y **segregación de funciones** (mínimo privilegio,
separación Médico–Comercial, Finanzas-configura / Director-aprueba).

La **matriz de la §5 es la fuente de verdad funcional.**

## 2. Decisiones tomadas (con el cliente)

1. **Mapeo de roles:** reusar los 6 roles existentes que alinean + crear 4 nuevos.
   `SUPERADMIN = ADMIN`. Se conservan `DIR_COMERCIAL`, `CONSULTA`, `CAPACITACION` (no borrar).
2. **Despliegue en piloto en vivo:** **motor + seed primero (NO destructivo)** — no se cambia el
   acceso efectivo de los usuarios actuales en esta entrega. La activación de guards y el "flip"
   de la matriz es una **Fase 2** controlada y separada.
3. **Alcance de entrega:** este spec → plan por tareas → implementación de **Fase 1**.

### Mapeo canónico → enum `Rol`

| Rol canónico (prompt) | Código sistema (enum `Rol`) | ¿Nuevo? |
|---|---|---|
| Representante Médico | `REPRESENTANTE_MEDICO` | existe |
| Gerente de Distrito | `GERENTE_DISTRITO` | existe |
| Gerente de Producto | `GERENTE_MARCA` | existe |
| Gerente de Marketing | `GERENTE_MARKETING` | **nuevo** |
| Gerente de Capacitación y Productividad | `GERENTE_PRODUCTIVIDAD` | existe |
| Gerente Médico | `GERENTE_MEDICO` | **nuevo** |
| Director General | `PRESIDENCIA` | existe |
| Analista de Datos | `ANALISTA_DATOS` | **nuevo** |
| Finanzas | `FINANZAS` | **nuevo** |
| Superadmin | `ADMIN` | existe |

`DIR_COMERCIAL`, `CONSULTA`, `CAPACITACION` permanecen en el enum; no tienen fila propia en la
matriz del prompt y **no reciben permisos nuevos** en Fase 1 (siguen operando con sus
`require_roles` actuales hasta la Fase 2). Se documentan como roles fuera del alcance de esta
matriz.

## 3. Estado actual (hallazgos de inspección)

- **Autorización = solo role-gate.** `deps.require_roles(*roles)` → 403 si `user.rol not in roles`.
  ~40 constantes `Require*` hand-rolled repartidas en 15 routers. **No hay** tabla de permisos,
  `can()`, ni capa de policy. `export` no es separable de `read`.
- **Scope ABAC ad-hoc:** `Usuario.rm_id` (RM→propio), `Usuario.gerente_id` (GD→equipo), y un
  helper `app/core/scope_gd.py` que **anonimiza** (no filtra) para GD. Aplicado de forma
  inconsistente. Es la semilla del modelo `own/team/all`, sin centralizar.
- **Frontend:** `ProtectedRoute.tsx` + `allowedRoles` en `App.tsx` + listas de rol en `Sidebar.tsx`
  = 3 copias hand-maintained de las reglas rol→ruta.
- **Auditoría:** `Audit.FACT_Auditoria` (middleware) registra POST/PUT/PATCH/DELETE genéricos; no
  separa acciones sensibles.
- **Multiempresa:** VISTA es multi-**país** (single-company). El aislamiento `tenant` del prompt se
  mapea al filtro `pais_codigo` ya presente en `Usuario`.

## 4. Modelo de autorización

Tres ejes **separados** (nunca `"Ver (equipo)"` como string único):

### 4.1 Recursos (28, slugs estables)

| # | Slug | Funcionalidad de la matriz |
|---|---|---|
| 1 | `dashboard.ejecutivo` | Dashboard Ejecutivo (KPI consolidados) |
| 2 | `visita.registrar` | Registrar visita médica (propia, móvil) |
| 3 | `medico.panel` | Catálogo de médicos y datos de contacto |
| 4 | `categorizacion.basica` | Categorización: vista básica (médico + A/B/C) |
| 5 | `categorizacion.detalle` | Categorización: detalle y peso de variables |
| 6 | `planeacion.ciclo` | Planeación del ciclo |
| 7 | `cobertura.diaria` | Cobertura diaria / Ruptura de secuencia |
| 8 | `cobertura.predictiva` | Cobertura predictiva |
| 9 | `parrilla.configurar` | Parrilla de muestras: configurar por ciclo |
| 10 | `parrilla.consulta` | Parrilla de muestras: consulta |
| 11 | `productividad.comercial` | Productividad comercial (mapa/gráfico) |
| 12 | `ranking.rkt` | Ranking general de representantes (RKT) |
| 13 | `farmacia.configuracion` | Configuración de farmacias (alta/asignación) |
| 14 | `farmacia.visita` | Registro de visita a farmacia (propia) |
| 15 | `farmacia.cobertura` | Cobertura de farmacias (dashboard) |
| 16 | `coaching.hoja` | Registrar hoja de acompañamiento GD→RM |
| 17 | `coaching.kpi` | KPI Coaching consolidado de equipo |
| 18 | `examen.rendir` | Rendir examen de producto (propio) |
| 19 | `examen.configurar` | Configurar/publicar contenido y exámenes |
| 20 | `inteligencia.matriz` | Matriz de Potencial y Adopción |
| 21 | `inteligencia.encuesta.configurar` | Encuestas de mercado: crear y publicar |
| 22 | `inteligencia.encuesta.aplicar` | Encuestas de mercado: aplicar en visita |
| 23 | `costoroi.ver` | Ver resultados de Costo por Visita y ROI |
| 24 | `costoroi.configurar` | Configurar costos, pool de ventas y presupuesto |
| 25 | `config.productos` | Catálogo de productos y precios |
| 26 | `config.usuarios` | Usuarios y asignación de roles |
| 27 | `config.parametros` | Parámetros generales (ciclos, categorías, reglas) |
| 28 | `exportacion` | Exportar datos y reportes de módulos visibles |

### 4.2 Acciones y alcances

- **`Accion`**: `read`, `register`, `configure`, `approve`, `export`, `admin`.
- **`Alcance`**: `none`, `own`, `team`, `all` (orden: `none < own < team < all`).

### 4.3 Descomposición de la matriz y reglas de implicación

Cada celda de la §5 se descompone a `(rol, recurso, accion) → alcance`:

| Nivel matriz | Descomposición |
|---|---|
| Sin acceso (`—`) | ninguna fila (deny por defecto) |
| Ver (propio) | `(read, own)` |
| Ver (equipo) | `(read, team)` |
| Ver (todos) | `(read, all)` |
| Registrar | `(register, own)` salvo Coaching GD → `(register, team)` |
| Configurar | `(configure, all)` |
| Aprobar | `(approve, all)` |
| Exportar (equipo) | `(export, team)` |
| Exportar (todos) | `(export, all)` |
| Admin total | `(admin, all)` |

**Implicación de acciones (mínima, explícita):**
- `admin` ⇒ todas las acciones, alcance `all`.
- `configure` ⇒ `read` al mismo alcance.
- `approve` ⇒ `read` al mismo alcance.
- `register` ⇒ `read` al mismo alcance.
- `export` ⇒ **nada** (independiente de `read`, por diseño).

**Tope de export por lectura:** el alcance efectivo de export sobre un recurso =
`min(export_grant, read_scope(user, recurso))`. Export **nunca** amplía el alcance de lectura.

## 5. Matriz obligatoria (28 × 10) — fuente de verdad

Columnas = enum `Rol`. Leyenda: `—`=sin acceso · `R:own/team/all`=read · `REG:own/team`=register ·
`CFG`=configure(all) · `APR`=approve(all) · `EXP:team/all`=export · `ADMIN`=admin(all).

| # | Recurso | REPRESENTANTE_MEDICO | GERENTE_DISTRITO | GERENTE_MARCA | GERENTE_MARKETING | GERENTE_PRODUCTIVIDAD | GERENTE_MEDICO | PRESIDENCIA | ANALISTA_DATOS | FINANZAS | ADMIN |
|---|---|---|---|---|---|---|---|---|---|---|---|
| 1 | `dashboard.ejecutivo` | R:own | R:team | R:all | R:all | R:all | R:all | R:all | R:all | R:all | ADMIN |
| 2 | `visita.registrar` | REG:own | — | — | — | — | — | — | — | — | ADMIN |
| 3 | `medico.panel` | R:own | R:team | R:all | R:all | — | R:all | R:all | R:all | — | ADMIN |
| 4 | `categorizacion.basica` | R:own | R:team | R:all | R:all | — | R:all | R:all | R:all | — | ADMIN |
| 5 | `categorizacion.detalle` | — | — | CFG | R:all | — | R:all | R:all | R:all | — | ADMIN |
| 6 | `planeacion.ciclo` | REG:own | R:team | — | — | — | — | R:all | R:all | — | ADMIN |
| 7 | `cobertura.diaria` | R:own | R:team | R:all | R:all | R:all | R:all | R:all | R:all | R:all | ADMIN |
| 8 | `cobertura.predictiva` | R:own | R:team | R:all | R:all | R:all | R:all | R:all | R:all | — | ADMIN |
| 9 | `parrilla.configurar` | — | — | CFG | — | — | — | R:all | R:all | — | ADMIN | *(jul-2026: configura el Gerente de Producto, no el GD)* |
| 10 | `parrilla.consulta` | R:own | R:team | R:all | R:all | R:all | R:all | R:all | R:all | R:all | ADMIN |
| 11 | `productividad.comercial` | R:own | R:team | R:all | R:all | R:all | **—** | R:all | R:all | R:all | ADMIN |
| 12 | `ranking.rkt` | R:own | R:team | R:all | R:all | R:all | **—** | R:all | R:all | R:all | ADMIN |
| 13 | `farmacia.configuracion` | — | CFG | — | R:all | — | — | R:all | R:all | — | ADMIN |
| 14 | `farmacia.visita` | REG:own | — | — | — | — | — | — | — | — | ADMIN |
| 15 | `farmacia.cobertura` | R:own | R:team | R:all | R:all | R:all | — | R:all | R:all | — | ADMIN |
| 16 | `coaching.hoja` | R:own | REG:team | — | — | R:team | R:all | R:all | R:all | — | ADMIN |
| 17 | `coaching.kpi` | — | R:team | — | — | R:all | R:all | R:all | R:all | — | ADMIN |
| 18 | `examen.rendir` | REG:own | — | — | — | R:team | R:all | R:all | R:all | — | ADMIN |
| 19 | `examen.configurar` | — | R:team | — | — | CFG | CFG | R:all | R:all | — | ADMIN |
| 20 | `inteligencia.matriz` | R:own | R:team | CFG | CFG | — | R:all | R:all | R:all | — | ADMIN |
| 21 | `inteligencia.encuesta.configurar` | — | — | CFG | CFG | — | R:all | R:all | R:all | — | ADMIN |
| 22 | `inteligencia.encuesta.aplicar` | REG:own | — | R:all | R:all | — | — | R:all | R:all | — | ADMIN |
| 23 | `costoroi.ver` | R:own | R:team | R:all | R:all | — | **—** | R:all | R:all | R:all | ADMIN |
| 24 | `costoroi.configurar` | — | — | — | — | — | — | **APR** | — | **CFG** | ADMIN |
| 25 | `config.productos` | — | — | R:all | R:all | — | R:all | R:all | R:all | R:all | ADMIN |
| 26 | `config.usuarios` | — | — | — | — | — | — | **—** | — | — | ADMIN |
| 27 | `config.parametros` | — | — | — | — | — | — | R:all | R:all | — | ADMIN |
| 28 | `exportacion` | — | EXP:team | EXP:all | EXP:all | EXP:all | EXP:all | EXP:all | EXP:all | EXP:all | ADMIN |

Puntos de segregación resaltados: firewall Médico (`GERENTE_MEDICO` = `—` en 11/`productividad.comercial`,
12/`ranking.rkt`, 23/`costoroi.ver`; y `costoroi.configurar` = `—`); solo `ADMIN` en 26/`config.usuarios`
(ni `PRESIDENCIA`); Finanzas-configura (`FINANZAS` CFG) vs Director-aprueba (`PRESIDENCIA` APR) en 24.

## 6. Arquitectura de implementación

### 6.1 Fuente única de verdad
Módulo Python declarativo **`app/core/authz/matrix.py`** = la matriz de la §5 como estructura de
datos (canónica, editable en un solo lugar). Se **siembra idempotente** a BD para inspección/auditoría
y para el contrato del frontend.

### 6.2 Motor — `app/core/authz/engine.py`
- `can(user, accion, recurso) -> Alcance | None` — alcance concedido o `None` (deny). `admin`
  cortocircuita. Aplica implicación de acciones (§4.3) y el tope de export por lectura.
- `require(accion, recurso)` — dependency FastAPI: 403 si deny; devuelve `(user, alcance)`.
- `rm_ids_visibles(db, user, alcance) -> set[int] | None` — `own`→`{rm_id}`, `team`→equipo (GD via
  `gerente_id`), `all`→`None` (sin filtro). **Absorbe `scope_gd.py`.**
- `assert_ve_rm(user, rm_id, alcance)` — guard por registro anti-IDOR/BOLA.
- `permisos_efectivos(user) -> dict` — capacidades del usuario para el contrato frontend.

**`own` se determina con identidad autenticada** (`user.rm_id`), nunca con un id del cliente.

### 6.3 Persistencia
- `Security.DIM_Recurso` (catálogo de los 28 recursos: slug, nombre, módulo).
- `Security.FACT_RolPermiso` (`rol`, `recurso`, `accion`, `alcance`) — seed idempotente desde
  `matrix.py`. Migración Alembic para las 2 tablas + los 4 nuevos valores del enum `Rol`.
- `Security.DIM_Usuario.roles_actualizado_en` (timestamp) — para revocación (§6.5).

### 6.4 Contrato frontend
`GET /authz/me/permisos` → capacidades efectivas del usuario actual. El frontend deriva
navegación, rutas y controles de ahí (`useAuthz()` + `<Can recurso accion>` + `ProtectedRoute`
leyendo el contrato). Elimina las 3 copias. **Ocultar el menú no sustituye el guard del servidor.**

### 6.5 Auditoría + revocación
- `Security.FACT_AuditoriaSeguridad` (append-only, patrón trigger como coaching): asignación/revocación
  de rol, configure/publish, approve/reopen, **export (recurso, alcance, filtros, resultado)**, uso de
  la excepción Superadmin sobre datos cerrados. Sin datos personales sensibles en el log.
- **Revocación al cambiar rol:** al cambiar `Usuario.rol` se fija `roles_actualizado_en=now()` y se
  revocan sus refresh tokens; `get_current_user` rechaza access tokens con `iat < roles_actualizado_en`.
  Un cambio de rol no deja permisos viejos vivos hasta el vencimiento de 60 min.

### 6.6 Reglas de segregación (codificadas como datos, no `if` especiales)
- **Solo Superadmin gestiona usuarios/roles:** `config.usuarios` = `ADMIN` únicamente. Anti-autoescalamiento:
  un no-admin nunca ve ni llama el endpoint de asignación de roles.
- **Finanzas configura / Director aprueba** (`costoroi.configurar`): `FINANZAS`=configure, `PRESIDENCIA`=approve.
  Roles distintos ⇒ "quien configura no aprueba" es estructural. Workflow de estados atómico validado en
  servidor (Fase 2).
- **Firewall Médico–Comercial:** `GERENTE_MEDICO` sin acceso a `productividad.comercial`, `ranking.rkt`,
  `costoroi.ver`, `costoroi.configurar`. Sin herencia jerárquica que lo rompa.
- **Analista de Datos:** lectura amplia + export; **cero** register/configure/approve/admin.
- **Excepción datos cerrados:** solo `admin` (Superadmin) puede modificar ciclos/pools cerrados; cada uso
  se audita.

## 7. Fases

### Fase 1 — esta entrega (NO destructiva)
Entregables:
1. Enum `Rol` + 4 valores nuevos + migración (enum + `DIM_Recurso` + `FACT_RolPermiso` +
   `roles_actualizado_en`).
2. `matrix.py` (matriz §5 como datos) + seed idempotente + script de siembra.
3. Motor `engine.py` (`can`, `require`, `rm_ids_visibles`, `assert_ve_rm`, `permisos_efectivos`).
4. `Security.FACT_AuditoriaSeguridad` + helper de registro.
5. `GET /authz/me/permisos` + `GET /authz/matriz` (inspección, solo ADMIN).
6. Revocación por `roles_actualizado_en` (backend).
7. **Suite de pruebas completa** (§8), incluida la parametrizada 28×10.

**No se rewirean endpoints existentes** → acceso efectivo actual sin cambios.

### Fase 2 — posterior, controlada (fuera de esta entrega)
Reemplazar `require_roles` por `require(accion, recurso)`; aplicar filtros de scope en
repositorios/KPIs/búsquedas/gráficos/export; derivar frontend del contrato; workflow atómico de
Costo/ROI; **flip** de la matriz. Se planifica aparte.

## 8. Pruebas obligatorias (Fase 1)

- **Parametrizada 28 recursos × 10 roles** contra `can()` — el resultado esperado sale de `matrix.py`
  (self-check: la matriz codificada == la tabla del spec).
- Filtros de alcance `own`/`team`/`all` (resolución a `rm_ids`).
- Negativas por cada `(rol, recurso, accion)` no concedido → `None`.
- Implicación: `configure`/`approve`/`register` conceden `read`; `export` no deriva de `read`.
- Tope de export por lectura (export nunca amplía alcance).
- `admin` concede todo.
- Firewall Médico (sin `productividad.comercial`/`ranking.rkt`/`costoroi.*`).
- Solo `ADMIN` en `config.usuarios` (incl. `PRESIDENCIA` denegado).
- Finanzas-configura / Director-aprueba en `costoroi.configurar`.
- Analista no escribe (todas las acciones ≠ read/export → deny).
- Revocación: token emitido antes de `roles_actualizado_en` → 401.
- Seed idempotente: re-ejecutar no duplica ni cambia filas.
- Aislamiento por país (`pais_codigo`) donde aplica.

## 9. Deuda declarada / decisiones pendientes

1. **`team` para roles no-GD.** La matriz asigna `read:team` a `GERENTE_PRODUCTIVIDAD` en
   `coaching.hoja` (16) y `examen.rendir` (18). `team` hoy se deriva solo de `gerente_id` (GD→RM). Para
   roles sin relación de equipo persistida, la **resolución** de `team` queda pendiente de definición en
   Fase 2 (default conservador). En Fase 1 `can()` devuelve el alcance literal `team` y la matriz se
   codifica tal cual; no se decide la resolución aún.
2. **Módulos inexistentes.** Farmacias (13-15), Inteligencia de mercado / Encuestas (20-22) y Matriz
   Potencial-Adopción no existen como módulos en la app. Entran al **catálogo de recursos** pero sin
   endpoints que guardar todavía.
3. **Datos de contacto médico** (teléfono/dirección): permiso centralizado en `medico.panel` para poder
   separar luego `medical_contact.read` de la categorización. No se cambia la matriz hoy; no duplicar el
   dato sensible en logs/tokens/URLs/exports temporales.
4. **`DIR_COMERCIAL`, `CONSULTA`, `CAPACITACION`:** fuera de la matriz del prompt en Fase 1. **Resuelto en
   Fase 2** — se derivan por regla en `matrix.py` para no romper usuarios existentes: `CAPACITACION`=fila de
   `GERENTE_PRODUCTIVIDAD`, `DIR_COMERCIAL`=fila de `ANALISTA_DATOS`, `CONSULTA`=igual sin export.

---

## 9-bis. Deuda de Fase 2 (flip de la matriz, jul-2026)

La Fase 2 cableó los endpoints de los módulos cubiertos por la matriz (`require/autorizar` + scope) y el
frontend (`usePuede`/`ProtectedRoute`/`Sidebar`). Pendientes que quedaron **flagged sin resolver**:

1. **`parrilla.configurar`** — ~~conflicto~~ **RESUELTO (jul-2026)**: decisión del cliente = configura el
   **Gerente de Producto** (`GERENTE_MARCA`) + ADMIN (inversión de marca). La matriz §5 fila 9 se ajustó
   (GERENTE_MARCA=configure, GD=sin acceso→solo consulta vía `parrilla.consulta`); endpoints `POST /visita/parrilla`
   y `/parrilla/publicar` cableados a `require(CONFIGURE, parrilla.configurar)`; frontend `ParrillaVisita`
   configura solo ADMIN/GERENTE_MARCA.
2. **`categorizacion.detalle`** (config de pesos de la categorización): la matriz da `configure` al Gerente
   de Producto; hoy el CRUD de criterios es ADMIN-only en `admin.py`. No se cableó (0 usuarios
   `GERENTE_MARCA` reales). Cablear si se activa ese rol.
3. **Módulos fuera de la matriz del prompt** (`reconocimiento`, `lsii`, `etl`, la megapantalla Admin de
   Configuración): no tienen recurso en los 28. Siguen gateados por `require_roles`/`allowedRoles`.
   **Decisión:** extender la matriz con recursos para estos módulos, o dejarlos por rol.
4. **Export por scope:** `exportacion` ya filtra por `rm_ids` (GD exporta su equipo, no toda la empresa).
   Si a futuro se agregan endpoints de export por módulo, aplicar el mismo `alcance_export_modulo` + filtro.
5. **UI Costo/ROI:** implementada (badge estado + Aprobar/Reabrir). El workflow no incluye notificación al
   Director cuando Finanzas deja algo en BORRADOR (posible mejora).

## 10. Compatibilidad

- No se reemplaza el sistema de autenticación (JWT) — se extiende.
- Fase 1 es aditiva: nuevas tablas, nuevo módulo, nuevo endpoint, 4 nuevos valores de enum. Ningún
  endpoint existente cambia su RBAC → usuarios y datos actuales intactos.
- Migraciones y seed idempotentes (re-ejecutables).
