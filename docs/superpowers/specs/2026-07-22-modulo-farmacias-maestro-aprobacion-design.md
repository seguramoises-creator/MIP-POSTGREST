# Módulo de Farmacias — Maestro, Aprobación del GD y Tipo de Visita Farmacia

> Diseño. Fecha: 2026-07-22. Fuente: `Ajuste_Modulo_Farmacias_Maestro_Aprobacion_Para_Moises.txt` v1.0.
> **Enfoque aprobado:** derivar del **módulo de Médicos ya construido** (maestro, panel, aprobación
> VM→GD, anti-duplicados) + los campos que el txt define. Todo campo/regla de la "v1.0" que el txt
> referencia pero no aporta queda marcado **⟦SUPUESTO⟧** o **⟦PREGUNTA⟧**.
>
> **Hallazgo base:** en el código **no existe módulo de Farmacias**; "Farmacia" solo es hoy el KPI
> externo `COB_FARMACIAS`. Esto construye el módulo desde cero espejando Médicos.

---

## 1. El molde: Médicos → Farmacias

| Pieza (Médicos, existente) | Equivalente Farmacias (nuevo) |
|---|---|
| `Config.DIM_Medico` (maestro central país-level) | **`Config.DIM_Farmacia`** (maestro único, F19) |
| `Visita.DIM_MedicoVisita` (panel del VM, referencia al maestro) | **`Visita.DIM_FarmaciaVisita`** (panel del VM) |
| `Visita.FactVisita` (registro de visita a médico) | **tipo de visita Farmacia** (§7) |
| `maestro_medico_service.detectar_duplicados` (duro/blando) | **anti-dup sobre CADENA+SUCURSAL** (F09/F25) |
| `visita_aprobacion_service` + `estado_aprobacion` (Bloque B) | **flujo VM→GD** para alta y asignación (F21) |
| `PanelMedico.tsx` + `MaestroMedicos.tsx` | **`PanelFarmacia.tsx`** + **`MaestroFarmacias.tsx`** |

---

## 2. Modelo de datos

### 2.1 `Config.DIM_Farmacia` — Maestro único (nuevo)
País-level, espejo de `DIM_Medico`. Campos:

| Campo | Tipo | Nota |
|---|---|---|
| id | PK | |
| pais_codigo | FK `DIM_Pais.codigo` | scope multipaís |
| es_cadena | Boolean | SI/NO (F20) |
| cadena | String(120) nullable | p. ej. "GBC" (solo si es_cadena) |
| sucursal | String(120) nullable | p. ej. "PANTOJA" (ubicación de la sucursal) |
| nombre | String(200) | **independiente** (farmacia no-cadena) |
| **nombre_completo** | String(250) | **derivado**: `cadena + " " + sucursal` si es_cadena, si no `nombre` (F20). Se calcula al guardar y se usa en todo listado/reporte |
| **direccion** | String(300) **NOT NULL** | calle, número, sector, ciudad — **bloqueante** (F23) |
| provincia / municipio / sector | String | ubicación |
| latitud / longitud | Numeric(10,7) | georreferencia |
| **encargado** | String(200) **NOT NULL** | nombre del encargado — **bloqueante** (F24) |
| telefono | String(40) | contacto |
| email | String(200) nullable | ⟦SUPUESTO⟧ opcional |
| **estado** | String(20) | `PENDIENTE_APROBACION` / `ACTIVA` / `RECHAZADA` / `INACTIVA` (§2.3 txt) |
| origen | String(12) | `VM` / `CONFIG` (quién la creó) |
| solicitado_por / aprobado_por | FK `DIM_Usuario` | trazabilidad |
| fecha_solicitud / fecha_aprobacion | DateTime | |
| motivo_rechazo | String(300) | obligatorio si RECHAZADA (F26) |
| activo | Boolean | baja lógica (INACTIVA) |
| created_at / updated_at | DateTime | |

**Índices:** `IX_Farmacia_cadena_sucursal` (para anti-dup y búsqueda), `IX_Farmacia_estado`.

### 2.2 `Visita.DIM_FarmaciaVisita` — Panel del VM (nuevo)
Espejo de `DIM_MedicoVisita`. **No duplica los datos**: referencia al maestro. Campos:

| Campo | Tipo | Nota |
|---|---|---|
| id | PK | |
| vm_id | FK `Config.DIM_RM.id` | representante dueño del panel |
| **maestro_farmacia_id** | FK `Config.DIM_Farmacia.id` | referencia al maestro (F19) |
| estado_aprobacion | String(16) | `APROBADO`/`PENDIENTE_ALTA`/`RECHAZADO` — de la **asignación** al panel |
| ciclo_alta_id / ciclo_baja_id | FK `DIM_Ciclo` | universo de cobertura desde el mes de aprobación (F21) |
| frecuencia_visita | String(20) nullable | ⟦PREGUNTA⟧ ¿las farmacias tienen F1/F2 como los médicos? |
| solicitado_por / aprobado_por / fechas / motivo | como Médicos | trazabilidad |
| ciclos_sin_visita | Integer | ruptura de secuencia (igual que médicos) |
| activo | Boolean | |

### 2.3 Registro de visita a Farmacia — ver §7 (decisión de diseño).

---

## 3. Nomenclatura CADENA + SUCURSAL (F20)

- Campos **guardados por separado** (`cadena`, `sucursal`), display **compuesto** (`nombre_completo`).
- `nombre_completo` se calcula al guardar: `es_cadena ? f"{cadena} {sucursal}" : nombre`.
- El selector de **cadena** ofrece las cadenas **ya existentes** en el maestro (`SELECT DISTINCT cadena`)
  para evitar variantes de escritura (GBC vs G.B.C.).
- **Anti-duplicados sobre `(pais_codigo, cadena, sucursal)`** normalizados (mayúsculas, sin acentos),
  reusando el patrón de normalización de `maestro_medico_service`.

---

## 4. Flujo de aprobación VM→GD (F21, F26)

Dos acciones del VM (móvil), ambas terminan en aprobación del GD:

- **ACCIÓN A — agregar al panel una farmacia que YA existe** (maestro ACTIVA):
  crea `DIM_FarmaciaVisita` con `estado_aprobacion=PENDIENTE_ALTA`. GD aprueba → `APROBADO`, entra al
  panel y a cobertura desde el ciclo de aprobación.
- **ACCIÓN B — crear una farmacia nueva** (no existe en maestro):
  1. Búsqueda obligatoria sin resultado habilita el formulario (F25).
  2. Validación bloqueante: sin dirección/encargado no hay Guardar (F23/F24).
  3. Crea `DIM_Farmacia` en `PENDIENTE_APROBACION` (origen=VM) + `DIM_FarmaciaVisita` pendiente.
  4. GD revisa: **editar y aprobar** / aprobar / rechazar (motivo obligatorio, F26).
  5. Aprobada → maestro `ACTIVA` + panel `APROBADO`.

**Bandeja del GD** (§3.2 txt): lista de pendientes de su distrito (farmacia, tipo de solicitud, VM,
fecha), alerta de posible duplicado, acciones APROBAR / RECHAZAR / EDITAR Y APROBAR, todo trazado.
→ Espeja `visita_aprobacion_service` + el diálogo "Revisar y aprobar" de `PanelMedico.tsx`.

**Regla F22:** farmacia en `PENDIENTE_APROBACION` **no cuenta para cobertura ni aparece en Registro de
Visita** (guard en las queries de cobertura y en el selector de registro).

**Config/admin** (F: §3.3 txt): el rol administrador crea/edita farmacias **directo en el maestro sin
aprobación** — el flujo GD aplica solo a altas originadas por VM. (Igual que Médicos: admin salta el
Bloque B.)

---

## 5. Campos bloqueantes (F23, F24)

`direccion` y `encargado` → **NOT NULL en el modelo** + **validación dura en cliente y servidor**:
- Cliente: botón Guardar deshabilitado hasta completarlos (patrón de la clasificación obligatoria del
  médico en `PanelMedico.tsx`).
- Servidor: el endpoint rechaza (422) con los mensajes exactos del txt:
  - "Debe completar la dirección de la farmacia para poder grabarla."
  - "Debe indicar el nombre del encargado para poder grabar la farmacia."

---

## 6. Anti-duplicados (F25, F09)

- **Buscar-antes-de-crear:** el formulario de alta solo se habilita tras una búsqueda **sin resultado**
  en el maestro (por cadena/sucursal). Igual que el blindaje del Maestro de Médicos.
- **Blindaje duro:** `(pais, cadena, sucursal)` ya existente bloquea la creación (devuelve la existente).
- **Alerta blanda:** en la bandeja del GD, si `(cadena, sucursal)` **se parece** a una existente
  (normalizado), se muestra advertencia de posible duplicado — no bloquea, pero avisa.

---

## 7. Tipo de visita Farmacia (integrar en Registro de Visita)

**Decisión de diseño (la única que conviene revisar):** hoy `Visita.FactVisita` es solo de médicos
(`medico_id` FK NOT NULL). Dos opciones para registrar visitas a farmacia:

| Opción | Cómo | Pro / Contra |
|---|---|---|
| **A — Tabla paralela `Visita.FactVisitaFarmacia`** (recomendada) | Nueva tabla espejo con `farmacia_id` FK | ✅ No toca la lógica de médicos (cero regresión en producción). ➖ Dos tablas de visita |
| B — Discriminador en `FactVisita` | `tipo_contacto` + `farmacia_id` nullable, `medico_id` nullable | ✅ Un solo historial. ➖ Cambia una columna NOT NULL en uso y toca todo el cálculo de cobertura médica existente (riesgo) |

**Recomendación: Opción A** — menor riesgo sobre un sistema en producción; la cobertura de farmacias
es un cálculo independiente de la de médicos (universo y denominador distintos). El registro reusa el
patrón de `RegistrarVisita.tsx` (hora servidor, GPS, foto opcional).

---

## 8. Cobertura de Farmacias (KPI) — ⚠️ coordinar con la integración

`COB_FARMACIAS` hoy se alimenta del **ETL externo** (y en la arquitectura de integración quedó asignado
al **SFA del cliente** por API). Este módulo permite calcular la cobertura **internamente** (farmacias
del panel visitadas / farmacias del panel activas), igual que el 4DX de médicos.

**⟦PREGUNTA⟧ (la misma tensión del §16 de la arquitectura):** ¿el número de `COB_FARMACIAS` del *score*
sale del **SFA externo** o de **este módulo interno**? Pueden coexistir (panel interno operativo + SFA
para el score), pero hay que decidir la fuente oficial. **No bloquea** construir el panel/registro; sí
decide si además cableamos la cobertura interna al score.

---

## 9. RBAC

Reusa el modelo existente. VM auto-scope a su `rm_id`; aprobación = roles que aprueban médicos
(ADMIN / GERENTE_DISTRITO / GERENTE_PRODUCTIVIDAD). Se agregan a la matriz editable los recursos:
`farmacia.panel` (VM lee/solicita), `farmacia.aprobar` (GD), `farmacia.maestro` (admin/config).

---

## 10. Frontend

- **`PanelFarmacia.tsx`** (móvil VM): buscar en maestro → Acción A (agregar) / Acción B (crear con
  formulario bloqueante) → ver estado de sus solicitudes y motivos de rechazo.
- **Bandeja de aprobación del GD**: tab/pantalla con pendientes, alerta de duplicado, APROBAR/RECHAZAR/
  EDITAR Y APROBAR (espeja el diálogo de médicos).
- **`MaestroFarmacias.tsx`** (admin/config, tab de Admin): CRUD directo + listado con `nombre_completo`.
- **Registro de visita**: agregar el tipo Farmacia (selector de farmacias activas del panel).

---

## 11. Reglas de negocio F19–F26 → dónde se implementan

| Regla | Implementación |
|---|---|
| F19 maestro único + panel referenciado | `DIM_Farmacia` + `DIM_FarmaciaVisita.maestro_farmacia_id` |
| F20 nombre CADENA+SUCURSAL | `nombre_completo` derivado (§3) |
| F21 alta/asignación con aprobación GD | flujo §4 |
| F22 PENDIENTE no cuenta cobertura ni registro | guard en queries (§4) |
| F23 dirección bloqueante | NOT NULL + validación dura (§5) |
| F24 encargado bloqueante | NOT NULL + validación dura (§5) |
| F25 formulario solo tras búsqueda sin resultado | anti-dup (§6) |
| F26 rechazo con motivo + histórico | `motivo_rechazo` + auditoría (§4) |

---

## 12. Supuestos y preguntas abiertas

- **⟦PREGUNTA⟧** ¿La "v1.0 sección 2.4" tiene **campos adicionales** de farmacia además de los del txt
  (tipo de farmacia, RNC/registro mercantil, horario, categoría)? Los omito hasta confirmar.
- **⟦PREGUNTA⟧** ¿Las farmacias tienen **frecuencia F1/F2** como los médicos, o la cobertura de
  farmacias es simple (visitada / no visitada)? Afecta el modelo del panel y el KPI.
- **⟦PREGUNTA⟧** Fuente oficial de `COB_FARMACIAS` para el score: SFA externo vs. módulo interno (§8).
- **⟦DECISIÓN⟧** Registro de visita: Opción A (tabla paralela) vs. B (discriminador) — recomiendo A.
- **⟦SUPUESTO⟧** El maestro de farmacias es país-level (como el de médicos), no por línea.

---

## 13. Plan por fases (para writing-plans)

1. **Modelo + migración**: `DIM_Farmacia` + `DIM_FarmaciaVisita` (+ `FactVisitaFarmacia` si Opción A).
2. **Servicio maestro**: `maestro_farmacia_service` (crear, anti-dup CADENA+SUCURSAL, nombre_completo).
3. **Flujo de aprobación**: extender/espejar `visita_aprobacion_service` para farmacias.
4. **Router**: `/farmacias` (panel VM, bandeja GD, maestro admin) + validación dura servidor.
5. **Registro de visita Farmacia** + guard F22.
6. **Frontend**: PanelFarmacia + bandeja GD + MaestroFarmacias + tipo Farmacia en Registro.
7. **Cobertura interna** (condicional a §8) + tests.

Cada fase con TDD y su verificación, siguiendo el flujo del repo.
