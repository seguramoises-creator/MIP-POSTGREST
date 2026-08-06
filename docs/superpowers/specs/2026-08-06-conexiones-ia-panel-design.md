# Spec — Panel de Conexiones de IA (Fase 0 · §20.4)

**Fecha:** 2026-08-06
**Módulo:** Formación ampliada — Fase 0 (capa de abstracción de IA), pieza de UI faltante.
**Alcance:** frontend-only (React 18 + TS + MUI v6 + TanStack Query v5). El backend (`ia_conexiones.py` + `conexion_service.py`) ya está completo y en producción; falta su pantalla.
**Origen:** el backend expone 7 endpoints bajo `/ia/conexiones` sin ninguna interfaz. Hoy la única forma de configurar/activar un proveedor de IA es por API o BD. El Simulacro (y Exámenes IA) ya remiten al usuario a una pantalla "Conexiones de IA" que no existe.

---

## 1. Objetivo

Dar al ADMIN una pantalla para administrar las conexiones a proveedores de IA sin
tocar código ni desplegar: listar, crear, editar, probar, activar y eliminar
conexiones de **texto** y **voz**, con las credenciales siempre enmascaradas.

## 2. Contrato del backend (ya existente, no se toca)

Prefijo `/ia/conexiones`, **todos los endpoints solo ADMIN**.

| Método | Ruta | Cuerpo / Query | Respuesta | Errores |
|---|---|---|---|---|
| GET | `` | `?capacidad=texto\|voz` (opcional) | `{ conexiones: Conexion[], cifrado_configurado: boolean }` | — |
| GET | `/proveedores` | — | `{ texto: string[], voz: string[] }` | — |
| POST | `` | `ConexionEntrada` | `Conexion` (201) | 422 (validación), 503 (falta llave de cifrado) |
| PUT | `/{id}` | `ConexionCambio` (parcial) | `Conexion` | 422, 503 |
| DELETE | `/{id}` | — | 204 | — |
| POST | `/{id}/probar` | — | `{ ok: boolean, detalle: string }` (siempre 200) | 404 |
| POST | `/{id}/activar` | — | `Conexion` | 409 (no verificada), 404 |

**`Conexion`** (lo que devuelve `a_dict`):
```ts
{
  id: number; nombre: string; capacidad: 'texto' | 'voz';
  proveedor_tipo: string; endpoint_url: string | null;
  metodo_auth: string; modelo: string | null;
  activa: boolean; verificada: boolean;
  ultima_verificacion: string | null;  // ISO datetime
  ultimo_error: string | null;
  credencial_1: string | null;  // SIEMPRE enmascarada (últimos 4 chars)
  credencial_2: string | null;  // SIEMPRE enmascarada
}
```

**`ConexionEntrada`** (crear — los 9 campos del §20.4):
```ts
{
  nombre: string;                 // requerido, 1..100
  capacidad: 'texto' | 'voz';     // requerido
  proveedor_tipo: string;         // requerido, debe estar en /proveedores[capacidad]
  endpoint_url?: string | null;
  metodo_auth: 'api_key' | 'usuario_password';  // default 'api_key'
  credencial_1?: string | null;
  credencial_2?: string | null;
  modelo?: string | null;
}
```

**`ConexionCambio`** (editar): todos los campos opcionales; el backend **solo aplica
los no-nulos**. Consecuencia clave: si el usuario no cambia una credencial, el
frontend **NO debe enviarla** (enviaría la máscara y pisaría la llave real).

Valores permitidos (del service): `CAPACIDADES=('texto','voz')`,
`METODOS_AUTH=('api_key','usuario_password')`. La lista de `proveedor_tipo` no se
hardcodea: sale de `GET /proveedores`.

## 3. Ubicación y navegación

- Página nueva: `frontend/src/pages/sistema/ConexionesIA.tsx`.
- Ruta: `/conexiones-ia`, protegida `allowedRoles={['ADMIN']}` en `App.tsx` (lazy con
  `lazyWithReload`, como el resto).
- Ítem de Sidebar: en el grupo administrativo que hoy contiene `/admin` y
  `/usuarios`, agregar `{ label: 'Conexiones de IA', path: '/conexiones-ia', icon:
  <Hub /> (o similar de MUI), roles: ['ADMIN'] }`.
- Service nuevo: `frontend/src/services/iaConexiones.service.ts` (tipos + las 7
  funciones), usando el cliente `api` (axios) igual que los demás services.

No se cuelga de "Formación" porque es configuración de sistema usada también por
Exámenes; sigue el criterio de `/admin`.

## 4. Diseño de la pantalla

### 4.1 Banner de llave de cifrado

Si `cifrado_configurado === false`, mostrar arriba un `Alert severity="error"`
persistente: "Falta configurar la llave de cifrado; no se pueden crear ni editar
conexiones." (Crear/editar sin llave devuelve 503.) Los botones "Nueva conexión" y
"Editar" quedan deshabilitados mientras esté en false.

### 4.2 Dos bloques por capacidad

Un bloque **Texto** y un bloque **Voz** (el sistema permite una activa por
capacidad). Cada bloque es una tabla de sus conexiones (obtenidas del listado
completo, particionado por `capacidad` en el cliente). Columnas:

- **Nombre**
- **Proveedor** (`proveedor_tipo`) · **Modelo** (`modelo` o "—")
- **Método** (`metodo_auth`)
- **Estado**: chips — `activa` → Chip verde "Activa"; `verificada` → Chip azul
  "Verificada" / gris "Sin verificar". Si `ultimo_error`, un icono de advertencia
  con el texto en tooltip. `ultima_verificacion` en tooltip del chip de verificación.
- **Acciones**: botones **Probar**, **Activar**, **Editar**, **Eliminar**.

Si un bloque no tiene filas: texto "Sin conexiones de {capacidad}."

### 4.3 Acciones por fila

- **Probar** → `POST /{id}/probar`. Muestra el resultado en un `Snackbar`/`Alert`:
  éxito (`ok:true`) verde con `detalle`; fallo (`ok:false`) naranja con `detalle`
  (el mensaje real del proveedor). Refetch de la lista (actualiza `verificada`,
  `ultima_verificacion`, `ultimo_error`).
- **Activar** → `POST /{id}/activar`. Deshabilitado si `!verificada` (con tooltip
  "Prueba la conexión antes de activarla"). Si el backend responde 409, mostrar ese
  aviso. Éxito → refetch (la que estaba activa en esa capacidad se desactiva sola).
- **Editar** → abre el diálogo (§4.4) precargado.
- **Eliminar** → `DELETE /{id}` tras confirmación (diálogo "¿Eliminar la conexión
  «{nombre}»?"). Refetch.

### 4.4 Diálogo Nueva / Editar conexión

Formulario con los 9 campos:

- `nombre` (TextField, requerido).
- `capacidad` (Select: Texto / Voz). Al cambiarla, se repuebla el desplegable de
  proveedor. En **editar**, `capacidad` es de solo-lectura (cambiarla no tiene
  sentido operativo y evita inconsistencias de proveedor).
- `proveedor_tipo` (Select poblado por `GET /proveedores`, filtrado por la
  `capacidad` elegida; requerido).
- `metodo_auth` (Select: api_key / usuario_password; default api_key).
- `endpoint_url` (TextField opcional).
- `modelo` (TextField opcional).
- `credencial_1`, `credencial_2` (TextField `type="password"`).
  - En **crear**: se envían tal cual (pueden ir vacías si el método no las usa).
  - En **editar**: llegan enmascaradas como placeholder informativo; los inputs
    arrancan **vacíos** con helperText "Déjalo en blanco para conservar la actual".
    Al guardar, un campo de credencial vacío **se omite del cuerpo** del PUT.

Guardar: crear → `POST`; editar → `PUT` solo con los campos con valor (para
credenciales, ver arriba). Error 422 → mostrar el mensaje del backend dentro del
diálogo (no cerrarlo). Error 503 → cerrar y mostrar el banner de llave.

### 4.5 Estado y datos

- React Query: una query `['ia-conexiones']` para el listado (incluye
  `cifrado_configurado`) y una query `['ia-proveedores']` para el desplegable.
- Mutations (crear/editar/probar/activar/eliminar) invalidan `['ia-conexiones']`
  en `onSettled`.
- Un único `Snackbar` de feedback reutilizado por probar/activar/eliminar.

## 5. Fuera de alcance (YAGNI)

- Ver credenciales en claro (el backend nunca las expone; imposible por diseño).
- Historial de auditoría en esta pantalla (ya se audita en backend; no se pidió UI).
- Edición de la capacidad de una conexión existente.
- Cualquier cambio de backend, modelo o migración.

## 6. Verificación

Frontend → build (`tsc` + `vite build`) + smoke en vivo con JWT de ADMIN
(minteado, sin escribir contraseña):

1. Entrar a `/conexiones-ia`; si falta la llave, ver el banner rojo.
2. Crear una conexión de texto de prueba → aparece en el bloque Texto, "Sin verificar".
3. **Probar** → snackbar con el `detalle` real (ok o error del proveedor).
4. Con una verificada, **Activar** → queda "Activa"; intentar activar una no
   verificada → aviso 409.
5. **Editar** dejando las credenciales en blanco → no se pisan (la máscara sigue con
   los mismos últimos 4 dígitos).
6. **Eliminar** con confirmación.
7. Verificar RBAC: un rol no-ADMIN no ve el ítem ni puede entrar a la ruta.

No se agregan tests automatizados (pantalla de presentación sobre un backend ya
cubierto).
