# Spec — Pantalla de Refuerzo de Memoria + KPI (Fase 5 · §10 y §11)

**Fecha:** 2026-08-06
**Módulo:** Formación ampliada — Fase 5 ("el corazón operativo"), pieza de UI faltante.
**Alcance:** frontend-only. El backend (`formacion_refuerzo.py`, `formacion_refuerzo_service.py`, `formacion_kpi_refuerzo_service.py`) está completo y en producción; no tiene ninguna pantalla.
**Origen:** el router `/formacion/refuerzo` expone 10 endpoints sin interfaz. Hoy ni el RM puede responder sus cápsulas ni Capacitación puede armar una campaña sin llamar la API a mano.

---

## 1. Objetivo

Dar interfaz a los dos ciclos de vida del módulo, que son distintos y no se mezclan:

- **El representante** responde sus cápsulas pendientes y ve la corrección inmediata (§10.7) y sus puntos.
- **Capacitación** arma campañas, genera y confirma el calendario de rondas, carga cápsulas y publica.
- **Quien corresponda por rol** consulta el KPI (§11): 3 métricas por 4 desgloses.

## 2. Estructura: una ruta con tabs por rol

Ruta única `/formacion/refuerzo`, con **tabs que se muestran según el rol** — mismo patrón que `Admin.tsx`. Cada tab vive en su propio archivo para mantener los componentes enfocados.

| Tab | Visible para | Archivo |
|---|---|---|
| **Mis cápsulas** | quien tenga `rm_id` (RM; ADMIN si está enlazado) | `pages/formacion/refuerzo/MisCapsulas.tsx` |
| **Campañas** | ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION (+ GERENTE_MEDICO solo para cargar cápsulas) | `pages/formacion/refuerzo/CampanasRefuerzo.tsx` |
| **KPI** | ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION, PRESIDENCIA, GERENTE_MEDICO, GERENTE_DISTRITO, REPRESENTANTE_MEDICO | `pages/formacion/refuerzo/KpiRefuerzo.tsx` |

Shell: `pages/formacion/Refuerzo.tsx`. Service: `services/refuerzo.service.ts`.

`allowedRoles` de la ruta = la unión de los tres (todos los roles menos CONSULTA, que no aparece en ningún gate del router). Si un rol solo tiene un tab visible, ese tab se abre por defecto.

## 3. Contrato del backend (ya existente, no se toca)

Prefijo `/formacion/refuerzo`.

| Método | Ruta | Cuerpo / Query | Roles | Respuesta |
|---|---|---|---|---|
| POST | `/campanas` | `CampanaEntrada` | Capacitación | `{id, nombre, estado, modo_espaciado}` |
| GET | `/campanas` | `?pais_codigo=XX` (requerido) | Capacitación | `Campana[]` |
| POST | `/campanas/{id}/calendario` | `?inicio=ISO` (opcional) | Capacitación | `Ronda[]` |
| PUT | `/rondas/{id}/programar` | `?fecha_hora=ISO` (opcional) | Capacitación | `{id, fecha_hora_programada}` |
| POST | `/rondas/{id}/capsulas` | `CapsulaEntrada` | Contenido (+GERENTE_MEDICO) | `{id, formato}` |
| POST | `/rondas/{id}/publicar` | — | Capacitación | `{id, publicada, notificada_en}` |
| GET | `/mis-capsulas` | — | autenticado con `rm_id` | `CapsulaPendiente[]` |
| POST | `/capsulas/{id}/responder` | `{opcion?, texto_libre?}` | autenticado con `rm_id` | `ResultadoRespuesta` |
| GET | `/mis-puntos` | `?campana_id` (opcional) | autenticado con `rm_id` | `{puntos: number}` |
| GET | `/kpi` | `?campana_id&pais_codigo` | por rol (§11.5) | `ReporteKpi` |

**Tipos** (derivados del código real):

```ts
type ModoEspaciado = 'creciente' | 'fijo_48h';           // MODOS_ESPACIADO
type FormatoCapsula = 'microlectura' | 'reto' | 'caso_breve' | 'reflexion_abierta';  // FORMATOS
const DURACIONES = [15, 30, 60, 90];                     // días

interface Campana {
  id: number; nombre: string; duracion_dias: number;
  modo_espaciado: ModoEspaciado; estado: string; aprobado_por_gm: boolean;
}
interface Ronda {
  id: number; numero_ronda: number;
  fecha_hora_sugerida: string | null;
  fecha_hora_programada: string | null;
  publicada: boolean;
}
interface CapsulaPendiente {
  capsula_id: number; formato: FormatoCapsula; enunciado: string;
  opciones: Record<string, string> | null;   // SIN opcion_correcta
  orden: number; ronda: number; campana: string; recibida_en: string | null;
}
interface ResultadoRespuesta {
  capsula_id: number; tiempo_respuesta_seg: number; pct_participacion: number;
  puntos_obtenidos: number; es_acierto: boolean | null;
  opcion_seleccionada: string | null;
  opcion_correcta: string | null;    // llega SOLO aquí (§10.7)
  explicacion: string | null; repetida: boolean;
}
interface Metricas {
  respuestas: number; tiempo_promedio_seg: number;
  pct_participacion: number; pct_aciertos: number | null;
  pregunta_mas_acertada: PreguntaExtremo | null;
  pregunta_menos_acertada: PreguntaExtremo | null;
}
interface PreguntaExtremo {
  capsula_id: number; enunciado: string; pct_aciertos: number; respuestas: number;
}
interface ReporteKpi {
  total_respuestas: number;
  general: Metricas;
  por_representante: (Metricas & { rm_id: number | null })[];
  por_producto: (Metricas & { producto_id: number | null })[];
  por_pais: (Metricas & { pais_codigo: string | null })[];
  por_gd?: (Metricas & { gerente_id: number | null })[];   // ausente para GD y RM
}
```

## 4. Tab "Mis cápsulas" (§10.5–§10.7)

Es el flujo diario del RM. Lista `GET /mis-capsulas` (solo de rondas ya publicadas).

- **Vacío:** "No tienes cápsulas pendientes." (No es un error: es el estado normal entre rondas.)
- **Tarjeta por cápsula**, en orden de ronda/orden, con chip de `formato`, nombre de `campana` y nº de `ronda`, y el `enunciado`.
- **Según formato:**
  - `reto` → botones con las `opciones` (clave + texto); al elegir uno se responde.
  - `microlectura` / `caso_breve` → botón "Marcar como leída" (responde sin opción).
  - `reflexion_abierta` → `TextField` multilínea + botón "Enviar" (manda `texto_libre`).
- **Corrección inmediata (§10.7):** al responder, la respuesta trae `opcion_correcta` y `explicacion` **siempre**, se haya acertado o no. Se resalta en el acto, sin recargar: opción correcta en verde, la elegida-incorrecta en rojo, y un `Alert` con la explicación. Se muestran también `puntos_obtenidos` y `pct_participacion`.
  - Si `es_acierto === null` (reflexión abierta o formato sin correcta): **no** se muestra "correcto/incorrecto" — solo el acuse de participación. Es una regla del backend (§10.5) que la UI debe respetar: `null` no es `false`.
  - Si `repetida === true`, avisar "Ya habías respondido esta cápsula" y mostrar el resultado previo sin permitir cambiarlo.
- **Puntos:** encabezado con `GET /mis-puntos` ("N puntos de Refuerzo"), refrescado tras cada respuesta.
- Al responder, la cápsula sale de la lista de pendientes (invalidar la query) pero su resultado permanece visible hasta que el usuario pase a la siguiente.

**El % de aciertos depende de que la correcta no se filtre antes de responder** — `mis-capsulas` no la trae, y la UI no debe intentar deducirla ni cachearla.

## 5. Tab "Campañas" (§10.2–§10.4)

Requiere un país. Se toma del contexto global con `useCicloStore((s) => s.paisCodigo)` (tipo `string | null`), igual que `PlanBrechas.tsx`; se pasa como query a `GET /campanas`. Mientras `paisCodigo` sea `null`, la query queda deshabilitada (`enabled: !!paisCodigo`) y el tab muestra "Selecciona un país en el encabezado."

- **Lista de campañas** del país: nombre, duración, modo de espaciado, estado, `aprobado_por_gm`.
- **"Nueva campaña"** → diálogo: `nombre`, `duracion_dias` (Select con 15/30/60/90 — el backend rechaza otros), `modo_espaciado` (Select creciente/fijo_48h), y opcionales `producto_id`, `ciclo_id`, `material_fuente_id` (campos numéricos simples; no hay endpoint de catálogo para ellos en este router).
- **Al seleccionar una campaña**, panel de rondas:
  - **"Generar calendario"** → `POST /campanas/{id}/calendario` (opcionalmente con fecha de inicio). Devuelve las rondas **sugeridas**; nada queda publicado (§10.3).
  - **Tabla de rondas**: nº, fecha sugerida, fecha programada, estado (publicada o no).
  - **"Confirmar"** por ronda → `PUT /rondas/{id}/programar` (con fecha elegida o aceptando la sugerida). Confirmar es obligatorio: ninguna ronda debe salir sin que alguien la mire.
  - **"Agregar cápsula"** por ronda → diálogo: `formato` (Select con los 4), `enunciado`, `orden`, y si el formato es `reto`: `opciones` (pares clave/texto) + `opcion_correcta` + `explicacion`. El backend **rechaza (422) un `reto` sin `opcion_correcta`** — la UI lo exige antes de enviar.
  - **"Publicar"** por ronda → `POST /rondas/{id}/publicar`. Un 409 (`CampanaNoPublicable`) se muestra con el mensaje real del backend.

## 6. Tab "KPI" (§11)

`GET /kpi` con filtros opcionales `campana_id` y `pais_codigo`. **El backend ya recorta el alcance por rol** — la UI no filtra por su cuenta ni asume qué verá.

- **Tarjetas de las 3 métricas** del bloque `general`: `pct_participacion`, `pct_aciertos` (si es `null` → "—", no 0) y `tiempo_promedio_seg` (formateado a min/seg), más `total_respuestas`.
- **Preguntas extremas** (§11.4): dos tarjetas — "Más acertada" y "Menos acertada" — con enunciado, `pct_aciertos` y `respuestas`. Si son `null`, ocultar la sección.
- **Cuatro tablas de desglose**: Por representante, Por producto, Por país, y **Por GD solo si `por_gd` viene en la respuesta** (para un GD o un RM el backend lo omite a propósito — la UI no debe mostrar una tabla vacía ni inventarla).
- Cada tabla: la clave del grupo + las 3 métricas.

**Las dos métricas nunca se mezclan (§10.8):** participación y aciertos se calculan sobre universos distintos y se muestran como columnas separadas; no se promedian ni se combinan en un "score" único.

## 7. Fuera de alcance (YAGNI)

- Aprobación de campaña por Gerente Médico (`aprobado_por_gm` se muestra, no se edita: no hay endpoint).
- Editar o eliminar campañas, rondas o cápsulas (el router no expone esos verbos).
- Selectores relacionales para `producto_id` / `ciclo_id` / `material_fuente_id` (no hay endpoint de catálogo en este router; van como numéricos).
- Gráficos del KPI: tablas y tarjetas bastan para la primera versión.
- Cualquier cambio de backend, modelo o migración.

## 8. Verificación

Build (`tsc` + `vite build`) + smoke en vivo con JWT (minteado, sin escribir contraseña):

1. Como Capacitación: crear campaña → generar calendario → confirmar una ronda → agregar una cápsula tipo `reto` con su correcta → publicar.
2. Intentar agregar un `reto` sin `opcion_correcta` → la UI lo impide (y el backend daría 422).
3. Como RM: ver la cápsula en "Mis cápsulas"; **verificar en la respuesta de red que `mis-capsulas` NO trae `opcion_correcta`**; responder → ver el resaltado inmediato con la correcta y la explicación; ver los puntos actualizados.
4. Responder de nuevo la misma cápsula → `repetida: true`, sin cambiar el resultado.
5. Como RM y como GD: abrir el KPI → confirmar que **no** aparece la tabla "Por GD".
6. Como Capacitación: abrir el KPI → sí aparece "Por GD".

No se agregan tests automatizados (presentación sobre un backend ya cubierto por la suite).
