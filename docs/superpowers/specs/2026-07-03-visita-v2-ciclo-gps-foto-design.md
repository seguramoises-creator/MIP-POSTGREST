# Módulo de Visita v2 — Config por ciclo + GPS/Foto — Diseño

**Fecha:** 2026-07-03 · **Preparado para:** Moisés · **Confidencial**
**Estado:** Aprobado (brainstorming) — pendiente de plan de implementación.

---

## 1. Resumen

Tres mejoras al Módulo de Visita:

| Parte | Mejora | Naturaleza |
|-------|--------|-----------|
| A | Selector de **ciclo** en Parrilla y Costo/ROI (ver/editar por ciclo, histórico en solo-lectura) | Frontend + guards backend |
| B | **GPS + foto por visita** en el registro (almacenados en la BD) | Backend (esquema + endpoints) |
| C | Captura de **ubicación y cámara** en la pantalla de registro | Frontend |

**Hallazgo de la revisión:** la configuración de Parrilla y Costo **ya se guarda por
(ciclo, línea)** en la BD (`ParrillaPromocional`, `CostoEstructura`, `CostoProducto`,
`ParametroCosto` tienen `ciclo_id`+`linea_id`); los endpoints ya aceptan `ciclo_id`. El
motivo por el que "no se ve" es que **las pantallas no tienen selector de ciclo** y
siempre resuelven al ciclo por defecto. Parte A es exponer lo existente. GPS-en-registro
y foto sí son nuevos.

**Decisiones (confirmadas):** foto como **BLOB en SQL Server**; GPS+foto **por visita**
(el centro conserva su lat/long de referencia en `MedicoVisita`); ciclos cerrados
**seleccionables en solo-lectura**; foto **opcional**.

---

## 2. Estado actual (base)

- `MedicoVisita` (esquema `Visita`): tiene `latitud`/`longitud` (`Numeric(10,7)`), `centro_trabajo` (str). **Sin foto.**
- `VisitaRegistro` (`Visita.FactVisita`): `vm_id, ciclo_id, medico_id, tipo_visita, fecha_hora, comentario, productos, ejecutada, causa_no_visita, registrado_por`. **Sin lat/long/foto.**
- `ParrillaPromocional`, `CostoEstructura`, `CostoProducto`, `ParametroCosto`: todos con `ciclo_id`+`linea_id`.
- Endpoints (router `visita.py`) ya aceptan `ciclo_id` opcional: `obtener_parrilla`, `parrilla_penetracion`, `publicar_parrilla`, costo (`/costo/estructura`, `/costo/importar`). Cuando `ciclo_id` es None, resuelven `ciclo_por_defecto`.
- Frontend: `CostoRoiVisita.tsx` (selector de línea, sin ciclo), `ParrillaVisita.tsx` ("Ciclo actual", sin selector), `RegistrarVisita.tsx` (agenda + registro, sin GPS/foto).
- Inmutabilidad: `DIM_Ciclo.cerrado`; guard `recalculo_service.validar_ciclo_abierto` (lanza `CicloCerradoError`).
- `Config.DIM_CentroMedico` existe (Categorización) pero **no** se vincula a `MedicoVisita` — fuera de alcance.

---

## 3. Parte A — Selector de ciclo en Parrilla y Costo/ROI

### 3.1 Frontend

- **Fuente de ciclos:** `GET /admin/ciclos` (devuelve `{id, nombre, pais_codigo, cerrado, ...}`).
- **`CostoRoiVisita.tsx`:** añadir selector de Ciclo junto al de Línea. Pasar `ciclo_id`
  a `costoEstructura(cicloId, lineaId)`, `guardarCostoEstructura({..., ciclo_id})`,
  `importarCostoExcel(file, cicloId, lineaId)`.
- **`ParrillaVisita.tsx`:** añadir selector de Ciclo. Pasar `ciclo_id` a obtener/penetración/guardar/publicar.
- **Solo-lectura si `cerrado`:** cuando el ciclo elegido está cerrado, deshabilitar
  Guardar/Publicar/Importar y mostrar un chip "Ciclo cerrado — solo lectura". El GET
  sigue funcionando (muestra el histórico).

### 3.2 Backend (guards)

- `visita_costo_service.guardar_estructura` e `importar_excel`: al inicio, resolver el
  `ciclo_id` efectivo y `validar_ciclo_abierto(db, ciclo_id)`; si cerrado, `ValueError`
  → el endpoint responde 400 "Ciclo cerrado — solo lectura".
- `visita_parrilla_service.guardar_parrilla` y `publicar_parrilla`: mismo guard.
- Los servicios ya reciben `ciclo_id`; solo se agrega el guard. Ninguna migración.

### 3.3 Firmas (frontend service)

```ts
costoEstructura(cicloId?: number, lineaId?: number)   // ciclo_id como query param
guardarCostoEstructura(datos)                          // datos.ciclo_id incluido
importarCostoExcel(file, cicloId?, lineaId?)
// Parrilla: obtenerParrilla(cicloId?, lineaId?), publicarParrilla(lineaId, cicloId?), etc.
```

---

## 4. Parte B — GPS + Foto por visita (backend)

### 4.1 Esquema (`Visita.FactVisita`) + migración idempotente

Nuevas columnas nullable en `VisitaRegistro`:

| Columna | Tipo |
|---------|------|
| `latitud` | `Numeric(10,7)` nullable |
| `longitud` | `Numeric(10,7)` nullable |
| `foto` | `LargeBinary` (VARBINARY(MAX)) nullable |
| `foto_mime` | `String(40)` nullable |

Migración `add_gps_foto_factvisita`: `op.add_column` con guard de existencia (patrón del proyecto).

### 4.2 Schemas

- `VisitaRegistrar`: añadir `latitud: float | None = None`, `longitud: float | None = None`.
- La foto **no** viaja en el JSON; se sube aparte (multipart).

### 4.3 Servicio (`visita_registro_service`)

- `registrar_visita`: persistir `latitud`/`longitud` si vienen.
- `guardar_foto_visita(db, visita_id, contenido: bytes, mime: str) -> None`:
  valida **magic bytes** (JPEG `\xff\xd8\xff`, PNG `\x89PNG\r\n`) y **tamaño ≤ 3 MB**;
  guarda `foto`+`foto_mime`. `ValueError` si inválida.
- `obtener_foto_visita(db, visita_id) -> tuple[bytes, str] | None`.

### 4.4 Endpoints (router `visita.py`)

| Método | Ruta | Descripción |
|--------|------|-------------|
| POST | `/visita/{visita_id}/foto` | Multipart `archivo: UploadFile`. Solo el VM dueño de la visita (scope) o gestión. Valida y guarda BLOB. |
| GET | `/visita/{visita_id}/foto` | Devuelve la imagen (`Response(content=bytes, media_type=mime)`). 404 si no hay foto. |

`POST /visita/registrar` sin cambios de contrato salvo los campos `latitud`/`longitud` opcionales.

---

## 5. Parte C — Frontend registro (GPS + cámara)

`RegistrarVisita.tsx` (formulario de registro):

- **Ubicación:** botón "📍 Capturar ubicación" → `navigator.geolocation.getCurrentPosition`
  (con manejo de error/permiso denegado). Muestra `lat, long` capturadas; se envían en `registrar`.
- **Foto (opcional):** `<input type="file" accept="image/*" capture="environment">` →
  vista previa en miniatura (`URL.createObjectURL`). No bloquea el registro si no hay foto.
- **Guardar:** `registrar` (con lat/long) → recibe `visita_id`; si hay foto, `POST .../foto`.
  Mensajes de éxito/aviso (p.ej. "visita registrada; foto no subida" si falla solo la foto).
- **Lista "Registradas hoy":** íconos 📍 (si hay GPS) y 📷 (si hay foto); la miniatura se
  puede abrir desde `GET /visita/{id}/foto`.

Servicio frontend: `subirFotoVisita(visitaId, file)`, `urlFotoVisita(visitaId)`.

---

## 6. Alcance y pruebas

- **Migración:** una (columnas GPS/foto en `FactVisita`). Parte A no lleva migración.
- **Tests backend (`pytest`):**
  - `registrar_visita` persiste `latitud`/`longitud`.
  - `guardar_foto_visita`: acepta JPEG/PNG válidos; rechaza tipo inválido y > 3 MB.
  - `obtener_foto_visita` devuelve bytes+mime; None si no hay.
  - Guards de ciclo cerrado: `guardar_estructura`/`importar` (Costo) y `guardar`/`publicar`
    (Parrilla) lanzan sobre ciclo cerrado.
- **Frontend:** `tsc -b` limpio; verificación en navegador del selector de ciclo (solo-lectura
  en cerrado) y del flujo de registro (subida de foto con archivo; geolocalización se valida
  a nivel de UI).

## 7. Fuera de alcance (YAGNI)

- Vincular `MedicoVisita` ↔ `Config.DIM_CentroMedico` (Categorización).
- Compresión/resize de imagen en servidor (solo se valida tamaño/límite; el navegador puede
  reducir antes de subir en una mejora futura).
- Mapa/visor de coordenadas (se muestran lat/long en texto por ahora).
