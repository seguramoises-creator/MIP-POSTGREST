# Spec — Pantalla de Onboarding + Biblioteca (Fase 2 · §4 y §5)

**Fecha:** 2026-08-06
**Módulo:** Formación ampliada — Fase 2, última pieza de UI faltante del módulo.
**Alcance:** frontend + **un endpoint de solo lectura en el backend** (ver §2). El resto del backend (`formacion.py`, `formacion_onboarding_service.py`, `formacion_biblioteca_service.py`) está completo y en producción.
**Origen:** el router `/formacion` expone 11 endpoints sin ninguna interfaz. Sin pantalla, ni el RM confirma lecturas ni Capacitación arma rutas de inducción.

---

## 1. Objetivo

Dar interfaz a las dos mitades inseparables de la Fase 2:

- **Biblioteca (§5):** Capacitación/Gerencia Médica suben material; **Gerencia Médica aprueba** (firewall PhRMA); el representante lo lee y **confirma**; todos ven el progreso de lectura obligatoria.
- **Onboarding (§4):** Capacitación crea la ruta estándar de 10 pasos por línea y la asigna a un representante; cada quien marca los pasos que le tocan (§4.6); el sistema informa **qué bloquea** cada paso.

## 2. Cambio de backend requerido (aprobado por el usuario)

Hoy la ruta de un representante solo se puede consultar por ID
(`GET /onboarding/asignaciones/{asignacion_id}`) y **no existe forma de que el RM
descubra el ID de la suya**. Sin esto, la pantalla no sirve para el destinatario
principal del §4.

**Endpoint nuevo — `GET /formacion/onboarding/mis-asignaciones`**

- **Roles:** cualquier autenticado (`RequireAnyAuth`), con **auto-scope**: usa
  `_rm_propio(usuario)` — el mismo helper que ya usan `confirmar_lectura` y
  `progreso`, que lanza 403 si el usuario no está enlazado a un representante.
- **Comportamiento:** devuelve las asignaciones de **ese** `rm_id`, ordenadas por
  `fecha_inicio` descendente. No acepta parámetro de `rm_id`: no hay forma de pedir
  la de otro (el scope no es un filtro opcional, es el único comportamiento).
- **Respuesta:**
  ```json
  [{"id": 1, "plantilla_id": 3, "nombre_plantilla": "Ruta Línea Cardio",
    "fecha_inicio": "2026-08-01", "progreso_pct": 40.0, "completada_en": null}]
  ```
- **Implementación:** una función nueva `asignaciones_de_rm(db, rm_id) -> list[dict]`
  en `formacion_onboarding_service.py` (consulta `OnboardingAsignacion` filtrando por
  `rm_id`, con `join` a `OnboardingPlantilla` para el nombre), más el endpoint que la
  expone. **Sin migración** (no cambia el modelo).
- **Test:** agregar a `backend/tests/test_formacion_onboarding_biblioteca.py` un caso
  que verifique (a) que devuelve solo las asignaciones del RM propio, y (b) que un
  usuario sin `rm_id` recibe 403.

Nada más del backend se toca.

## 3. Contrato del backend (existente + el nuevo)

Prefijo `/formacion`.

| Método | Ruta | Cuerpo / Query | Roles | Respuesta |
|---|---|---|---|---|
| GET | `/productos` | `?pais_codigo&linea_id` | autenticado | `Producto[]` |
| POST | `/productos` | `ProductoEntrada` | Capacitación | `{id, nombre_producto, rol_en_ruta}` |
| GET | `/biblioteca` | `?pais_codigo&producto_id?` | autenticado (RM ve solo aprobados) | `Material[]` |
| POST | `/biblioteca` | `MaterialEntrada` | Contenido (+GERENTE_MEDICO) | `{id, titulo, aprobado_por_gm}` |
| POST | `/biblioteca/{id}/aprobar` | — | **ADMIN o GERENTE_MEDICO** | `{id, aprobado_por_gm}` |
| POST | `/biblioteca/{id}/confirmar` | — | autenticado con `rm_id` | `{material_id, confirmado_en}` |
| GET | `/biblioteca/{id}/confirmaciones` | — | Contenido | `{rm_id, confirmado_en}[]` |
| GET | `/biblioteca/progreso` | `?producto_ids=1,2,3` (CSV) | autenticado con `rm_id` | `ProgresoLectura` |
| POST | `/onboarding/plantillas` | `PlantillaEntrada` | Contenido | `{id, nombre_plantilla, pasos[]}` |
| GET | `/onboarding/plantillas/{id}/pasos` | — | autenticado | `Paso[]` |
| POST | `/onboarding/asignaciones` | `AsignacionEntrada` | Capacitación | `{id, rm_id, progreso_pct}` |
| **GET** | **`/onboarding/mis-asignaciones`** | — | autenticado con `rm_id` | `MiAsignacion[]` *(NUEVO, §2)* |
| GET | `/onboarding/asignaciones/{id}` | — | autenticado (RM solo la suya) | `EstadoRuta` |
| POST | `/onboarding/asignaciones/{id}/pasos/{paso_id}/completar` | `?observaciones` | autenticado (el servicio valida el rol) | `{paso_id, completado_en}` |

**Tipos** (del código real):

```ts
type TipoMaterial = 'manual' | 'ayuda_visual' | 'estudio_clinico' | 'ficha_tecnica' | 'video';
type RolEnRuta = 'principal' | 'relacionado';

interface Producto { id: number; nombre_producto: string; rol_en_ruta: RolEnRuta; activo: boolean; }

interface Material {
  id: number; titulo: string; tipo: TipoMaterial; archivo_url: string;
  obligatorio: boolean; producto_id: number | null; aprobado_por_gm: boolean;
}
interface MaterialEntrada {
  pais_codigo: string; titulo: string; tipo: TipoMaterial; archivo_url: string;
  producto_id?: number | null; obligatorio?: boolean;
  usado_en_examen_id?: number | null; usado_en_coaching_av?: boolean;
}
interface ProgresoLectura {
  total: number; confirmados: number; completo: boolean;
  pendientes: { id: number; titulo: string; tipo: TipoMaterial }[];
}
interface Confirmacion { rm_id: number; confirmado_en: string; }

interface Paso {
  id: number; orden: number; titulo: string; tipo: string;
  plazo_sugerido: number | null; bloqueante: boolean; quien_lo_marca: string;
}
interface MiAsignacion {
  id: number; plantilla_id: number; nombre_plantilla: string;
  fecha_inicio: string; progreso_pct: number; completada_en: string | null;
}
interface PasoEstado {
  paso_id: number; orden: number; titulo: string; tipo: string;
  quien_lo_marca: string;
  estado: 'completado' | 'disponible' | 'bloqueado';
  bloqueos: string[];
  material?: ProgresoLectura | null;
}
interface EstadoRuta {
  asignacion_id: number; rm_id: number; plantilla_id: number;
  total_pasos: number; completados: number; progreso_pct: number;
  pasos: PasoEstado[];
}
```

## 4. Estructura: una ruta con tabs por rol

Ruta `/formacion/onboarding`, con tabs según rol — mismo patrón que la pantalla de Refuerzo.

| Tab | Visible para | Archivo |
|---|---|---|
| **Mi ruta** | REPRESENTANTE_MEDICO | `pages/formacion/onboarding/MiRuta.tsx` |
| **Biblioteca** | todos los roles con acceso a la ruta | `pages/formacion/onboarding/Biblioteca.tsx` |
| **Rutas y plantillas** | ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION, GERENTE_MEDICO | `pages/formacion/onboarding/RutasAdmin.tsx` |

Shell: `pages/formacion/Onboarding.tsx`. Service: `services/onboarding.service.ts`.
`allowedRoles` de la ruta = la unión.

**Nota de RBAC:** el gate de "Rutas y plantillas" incluye GERENTE_MEDICO porque
`POST /onboarding/plantillas` usa `RequireContenido` (que sí lo incluye). A
diferencia del caso de Refuerzo, aquí el rol **sí** puede operar el tab: crear
plantillas y ver pasos. Solo `POST /onboarding/asignaciones` le está vedado
(`RequireCapacitacion`), así que el botón "Asignar" se oculta para GERENTE_MEDICO.

## 5. Tab "Mi ruta" (§4)

1. Al abrir, `GET /onboarding/mis-asignaciones`.
   - **Sin asignaciones:** "Aún no tienes una ruta de formación asignada." (no es error).
   - **Una o varias:** selector; por defecto la más reciente.
2. Con la asignación elegida, `GET /onboarding/asignaciones/{id}` → `EstadoRuta`.
3. **Barra de progreso** con `progreso_pct` y "N de M pasos".
4. **Lista de pasos** en orden, cada uno con:
   - Estado: chip verde "Completado", azul "Disponible", gris "Bloqueado".
   - `titulo`, `tipo`, y **quién lo marca** (`quien_lo_marca`).
   - Si está bloqueado, **los motivos** (`bloqueos[]`, que el backend devuelve como
     frases listas para mostrar — se listan todas, no solo la primera: el backend las
     informa juntas a propósito para que el RM no descubra la segunda tras resolver la primera).
   - Si trae `material`, el progreso de lectura ("2 de 4 confirmados") y los títulos pendientes.
5. **Botón "Marcar completado"** solo en pasos con `estado === 'disponible'`.
   - `POST .../pasos/{paso_id}/completar`.
   - **El backend decide si el rol puede** (§4.6): un 403 (`RolNoAutorizado`) se muestra
     con su mensaje real. La UI **no** replica esa regla — solo muestra el botón cuando el
     paso está disponible; si el rol no corresponde, el backend lo dice. Esto es
     deliberado: la regla vive en un solo lugar.
   - Un 409 (`PasoBloqueado`) se muestra con su mensaje real.
   - Tras completar, refetch del estado.

## 6. Tab "Biblioteca" (§5)

Requiere país del contexto (`useCicloStore((s) => s.paisCodigo)`); si es `null`, aviso.

- **Filtro opcional por producto**: `GET /productos?pais_codigo&linea_id` necesita
  `linea_id`, que esta pantalla no tiene de forma fiable. Por eso el filtro de producto
  se ofrece como **campo numérico opcional** (`producto_id`) que se pasa a
  `GET /biblioteca`; sin él se listan todos los del país. (No se inventa un selector
  de línea que el contrato no soporta aquí.)
- **Tabla de materiales**: título, tipo, obligatorio (chip), aprobado por GM (chip
  verde "Aprobado" / gris "Pendiente de aprobación"), y enlace "Abrir" a `archivo_url`
  (`target="_blank"`, `rel="noopener noreferrer"`).
- **Acciones según rol:**
  - **"Subir material"** (Contenido: ADMIN/GERENTE_PRODUCTIVIDAD/CAPACITACION/GERENTE_MEDICO)
    → diálogo con `titulo`, `tipo` (Select con los 5), `archivo_url`, `producto_id`
    (opcional), `obligatorio` (Switch, **por defecto activado** según §5.3).
  - **"Aprobar"** por fila (solo ADMIN y GERENTE_MEDICO, y solo si `!aprobado_por_gm`)
    → `POST /biblioteca/{id}/aprobar`.
  - **"Confirmar lectura"** por fila (REPRESENTANTE_MEDICO) → `POST /biblioteca/{id}/confirmar`.
    Un **409** (`MaterialNoAprobado`) se muestra con su mensaje: no se puede confirmar
    material que no pasó el firewall.
  - **"Quién confirmó"** por fila (Contenido) → diálogo que lista `GET /biblioteca/{id}/confirmaciones`.
- **Progreso propio** (REPRESENTANTE_MEDICO): si el usuario indicó uno o más
  `producto_id`, mostrar `GET /biblioteca/progreso?producto_ids=…` como
  "N de M materiales obligatorios confirmados" + lista de pendientes por título.

**El RM solo ve material aprobado** — lo garantiza el backend (`solo_aprobados` cuando
el rol es REPRESENTANTE_MEDICO); la UI no filtra por su cuenta.

## 7. Tab "Rutas y plantillas" (§4, gestión)

- **"Nueva ruta estándar"** → diálogo: `nombre_plantilla`, `linea_id` (numérico),
  `duracion_dias` (por defecto 30). `POST /onboarding/plantillas` crea la plantilla
  **con sus 10 pasos estándar** y los devuelve; se muestran en una tabla tras crearla.
- **Consultar pasos de una plantilla**: campo `plantilla_id` + `GET /onboarding/plantillas/{id}/pasos`
  → tabla con orden, título, tipo, plazo, bloqueante, quién lo marca.
- **"Asignar a un representante"** (oculto para GERENTE_MEDICO) → diálogo:
  `plantilla_id`, `rm_id`, `fecha_inicio` (opcional) → `POST /onboarding/asignaciones`.
- **Consultar una asignación**: campo `asignacion_id` + `GET /onboarding/asignaciones/{id}`
  → el mismo detalle de pasos/bloqueos que ve el RM (reutiliza el componente de lista de
  pasos del tab "Mi ruta"), en modo solo lectura salvo que el rol pueda marcar pasos.

`linea_id`, `rm_id`, `plantilla_id` y `asignacion_id` van como **campos numéricos**:
este router no expone catálogos para poblarlos y no se inventa un selector que el
contrato no soporta. (Follow-up posible: enlazarlos a `/admin/lineas` y `/admin/rms`.)

## 8. Fuera de alcance (YAGNI)

- Editar o eliminar materiales, plantillas, pasos o asignaciones (el router no expone esos verbos).
- Subida de archivos: `archivo_url` es una URL; no hay endpoint de carga binaria aquí.
- Selectores relacionales para línea/RM/plantilla (ver §7).
- Cualquier otro cambio de backend además del endpoint de §2.

## 9. Verificación

Backend: `pytest backend/tests/test_formacion_onboarding_biblioteca.py -v` (incluye los 2 casos nuevos).
Frontend: `npm run build` + smoke en vivo con JWT minteado:

1. Capacitación: crear ruta estándar → ver sus 10 pasos → asignar a un RM.
2. Contenido: subir material obligatorio de un producto → aparece "Pendiente de aprobación".
3. RM: en Biblioteca **no** debe ver ese material sin aprobar (lo filtra el backend).
4. Gerencia Médica: aprobar el material → el RM ya lo ve → "Confirmar lectura".
5. Intentar confirmar un material no aprobado (vía otro camino) → 409 con su mensaje.
6. RM: "Mi ruta" → la asignación aparece **sin** conocer el ID (endpoint nuevo);
   un paso bloqueado muestra **todos** sus motivos, incluida la lectura pendiente.
7. RM: intentar completar un paso cuyo `quien_lo_marca` es el GD → 403 con el mensaje real.
8. Usuario sin `rm_id` en "Mi ruta" → mensaje claro (403 del backend), no pantalla vacía.
