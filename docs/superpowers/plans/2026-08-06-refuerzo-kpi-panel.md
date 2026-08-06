# Pantalla de Refuerzo de Memoria + KPI — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar interfaz a los dos ciclos de vida del Refuerzo de Memoria (el RM responde cápsulas con corrección inmediata; Capacitación arma campañas y publica rondas) y al reporte KPI del §11.

**Architecture:** Frontend-only sobre un backend ya existente (`/formacion/refuerzo`, 10 endpoints). Una ruta `/formacion/refuerzo` con un shell de tabs que se muestran según el rol; cada tab en su propio archivo para mantener componentes enfocados. Un service axios tipado centraliza el contrato.

**Tech Stack:** React 18 + TypeScript, MUI v6, TanStack Query v5, axios (`import { api } from './api'`), Zustand (`useAuthStore`, `useCicloStore`), react-router-dom v6 (`lazyWithReload`).

## Global Constraints

- Cero cambios de backend/modelo/migración. El contrato de §3 del spec es fijo.
- **La opción correcta NUNCA llega antes de responder.** `GET /mis-capsulas` no la trae; `POST /capsulas/{id}/responder` sí. La UI no debe deducirla, cachearla ni pedirla por otra vía.
- **`es_acierto === null` NO es `false`** (§10.5): en reflexión abierta y formatos sin correcta no se muestra "correcto/incorrecto", solo el acuse de participación.
- **Participación y aciertos nunca se mezclan** (§10.8): se muestran como columnas/tarjetas separadas; jamás se promedian en un único score.
- **`por_gd` puede no venir** en el KPI (el backend lo omite para GERENTE_DISTRITO y REPRESENTANTE_MEDICO): renderizar esa tabla solo si la clave existe.
- Valores permitidos: `modo_espaciado ∈ {creciente, fijo_48h}`, `duracion_dias ∈ {15,30,60,90}`, `formato ∈ {microlectura, reto, caso_breve, reflexion_abierta}`. Un `reto` exige `opcion_correcta` (el backend da 422 sin ella).
- País desde el contexto global: `useCicloStore((s) => s.paisCodigo)` (`string | null`); con `null`, query deshabilitada y mensaje "Selecciona un país en el encabezado."
- Estilo del proyecto: MUI `sx`, React Query, español en el copy, `.then(r => r.data)` en el service. Patrón de referencia: `frontend/src/pages/formacion/PlanBrechas.tsx` y `frontend/src/pages/admin/CategorizacionAdmin.tsx`.
- No agregar tests automatizados. Verificación = `npm run build` + smoke.

---

### Task 1: Service `refuerzo.service.ts` (tipos + 10 funciones)

**Files:**
- Create: `frontend/src/services/refuerzo.service.ts`

**Interfaces:**
- Produce (para Tasks 2-5): tipos `ModoEspaciado`, `FormatoCapsula`, `Campana`, `Ronda`, `CapsulaPendiente`, `ResultadoRespuesta`, `PreguntaExtremo`, `Metricas`, `ReporteKpi`, `CampanaEntrada`, `CapsulaEntrada`; constantes `DURACIONES`, `MODOS_ESPACIADO`, `FORMATOS`; y las funciones `crearCampana`, `listarCampanas`, `generarCalendario`, `programarRonda`, `agregarCapsula`, `publicarRonda`, `misCapsulas`, `responderCapsula`, `misPuntos`, `reporteKpi`.

- [ ] **Step 1: Crear el archivo completo**

```ts
/**
 * refuerzo.service.ts — Refuerzo de Memoria y su KPI (§10 y §11).
 * Rutas exactas del router backend `/formacion/refuerzo`
 * (ver backend/app/api/v1/routers/formacion_refuerzo.py).
 *
 * LO QUE NUNCA LLEGA ANTES DE TIEMPO: `opcion_correcta` no viaja con el
 * enunciado en `misCapsulas`; solo la devuelve `responderCapsula` (§10.7).
 */
import { api } from './api';

export type ModoEspaciado = 'creciente' | 'fijo_48h';
export type FormatoCapsula = 'microlectura' | 'reto' | 'caso_breve' | 'reflexion_abierta';

export const MODOS_ESPACIADO: ModoEspaciado[] = ['creciente', 'fijo_48h'];
export const FORMATOS: FormatoCapsula[] = ['microlectura', 'reto', 'caso_breve', 'reflexion_abierta'];
export const DURACIONES = [15, 30, 60, 90];

export interface Campana {
  id: number; nombre: string; duracion_dias: number;
  modo_espaciado: ModoEspaciado; estado: string; aprobado_por_gm: boolean;
}

export interface Ronda {
  id: number; numero_ronda: number;
  fecha_hora_sugerida: string | null;
  fecha_hora_programada: string | null;
  publicada: boolean;
}

export interface CapsulaPendiente {
  capsula_id: number; formato: FormatoCapsula; enunciado: string;
  opciones: Record<string, string> | null;
  orden: number; ronda: number; campana: string; recibida_en: string | null;
}

export interface ResultadoRespuesta {
  capsula_id: number; tiempo_respuesta_seg: number; pct_participacion: number;
  puntos_obtenidos: number; es_acierto: boolean | null;
  opcion_seleccionada: string | null;
  opcion_correcta: string | null; explicacion: string | null; repetida: boolean;
}

export interface PreguntaExtremo {
  capsula_id: number; enunciado: string; pct_aciertos: number; respuestas: number;
}

export interface Metricas {
  respuestas: number; tiempo_promedio_seg: number;
  pct_participacion: number; pct_aciertos: number | null;
  pregunta_mas_acertada: PreguntaExtremo | null;
  pregunta_menos_acertada: PreguntaExtremo | null;
}

export interface ReporteKpi {
  total_respuestas: number;
  general: Metricas;
  por_representante: (Metricas & { rm_id: number | null })[];
  por_producto: (Metricas & { producto_id: number | null })[];
  por_pais: (Metricas & { pais_codigo: string | null })[];
  por_gd?: (Metricas & { gerente_id: number | null })[];
}

export interface CampanaEntrada {
  pais_codigo: string; nombre: string; duracion_dias: number;
  modo_espaciado: ModoEspaciado;
  producto_id?: number | null; ciclo_id?: number | null; material_fuente_id?: number | null;
}

export interface CapsulaEntrada {
  formato: FormatoCapsula; enunciado: string; orden: number;
  opciones?: Record<string, string> | null;
  opcion_correcta?: string | null; explicacion?: string | null;
}

// ── Campañas (Capacitación) ───────────────────────────────────────────────
export const crearCampana = (body: CampanaEntrada) =>
  api.post<{ id: number; nombre: string; estado: string; modo_espaciado: ModoEspaciado }>(
    '/formacion/refuerzo/campanas', body).then((r) => r.data);

export const listarCampanas = (paisCodigo: string) =>
  api.get<Campana[]>('/formacion/refuerzo/campanas', { params: { pais_codigo: paisCodigo } })
    .then((r) => r.data);

export const generarCalendario = (campanaId: number, inicio?: string) =>
  api.post<Ronda[]>(`/formacion/refuerzo/campanas/${campanaId}/calendario`, null,
    { params: inicio ? { inicio } : {} }).then((r) => r.data);

export const programarRonda = (rondaId: number, fechaHora?: string) =>
  api.put<{ id: number; fecha_hora_programada: string | null }>(
    `/formacion/refuerzo/rondas/${rondaId}/programar`, null,
    { params: fechaHora ? { fecha_hora: fechaHora } : {} }).then((r) => r.data);

export const agregarCapsula = (rondaId: number, body: CapsulaEntrada) =>
  api.post<{ id: number; formato: FormatoCapsula }>(
    `/formacion/refuerzo/rondas/${rondaId}/capsulas`, body).then((r) => r.data);

export const publicarRonda = (rondaId: number) =>
  api.post<{ id: number; publicada: boolean; notificada_en: string | null }>(
    `/formacion/refuerzo/rondas/${rondaId}/publicar`).then((r) => r.data);

// ── El representante responde ─────────────────────────────────────────────
export const misCapsulas = () =>
  api.get<CapsulaPendiente[]>('/formacion/refuerzo/mis-capsulas').then((r) => r.data);

export const responderCapsula = (capsulaId: number, body: { opcion?: string; texto_libre?: string }) =>
  api.post<ResultadoRespuesta>(`/formacion/refuerzo/capsulas/${capsulaId}/responder`, body)
    .then((r) => r.data);

export const misPuntos = (campanaId?: number) =>
  api.get<{ puntos: number }>('/formacion/refuerzo/mis-puntos',
    { params: campanaId != null ? { campana_id: campanaId } : {} }).then((r) => r.data);

// ── KPI (§11) — el backend recorta el alcance por rol ─────────────────────
export const reporteKpi = (params: { campana_id?: number; pais_codigo?: string } = {}) =>
  api.get<ReporteKpi>('/formacion/refuerzo/kpi', { params }).then((r) => r.data);
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/refuerzo.service.ts
git commit -m "feat(formacion) Refuerzo: capa de servicio frontend (tipos + 10 endpoints)"
```

---

### Task 2: Shell con tabs por rol + stubs de los 3 tabs + ruta + sidebar

Crea el contenedor con las tabs visibles según rol, y **tres archivos stub** (para que el build pase); Tasks 3-5 los rellenan. Registra ruta y sidebar.

**Files:**
- Create: `frontend/src/pages/formacion/Refuerzo.tsx`
- Create: `frontend/src/pages/formacion/refuerzo/MisCapsulas.tsx` (stub)
- Create: `frontend/src/pages/formacion/refuerzo/CampanasRefuerzo.tsx` (stub)
- Create: `frontend/src/pages/formacion/refuerzo/KpiRefuerzo.tsx` (stub)
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Consumes: nada del service todavía.
- Produce (para Tasks 3-5): tres componentes por defecto sin props —
  `export default function MisCapsulas()`, `export default function CampanasRefuerzo()`,
  `export default function KpiRefuerzo()`. Tasks 3-5 reemplazan el cuerpo del stub
  conservando esa firma exacta.

- [ ] **Step 1: Crear los tres stubs**

`frontend/src/pages/formacion/refuerzo/MisCapsulas.tsx`:
```tsx
// Tab "Mis cápsulas" del Refuerzo de Memoria (§10.5-§10.7). Cuerpo en Task 3.
export default function MisCapsulas() {
  return null;
}
```

`frontend/src/pages/formacion/refuerzo/CampanasRefuerzo.tsx`:
```tsx
// Tab "Campañas" del Refuerzo de Memoria (§10.2-§10.4). Cuerpo en Task 4.
export default function CampanasRefuerzo() {
  return null;
}
```

`frontend/src/pages/formacion/refuerzo/KpiRefuerzo.tsx`:
```tsx
// Tab "KPI" del Refuerzo de Memoria (§11). Cuerpo en Task 5.
export default function KpiRefuerzo() {
  return null;
}
```

- [ ] **Step 2: Crear el shell `Refuerzo.tsx`**

```tsx
/**
 * Refuerzo.tsx — Refuerzo de Memoria y su KPI (§10 y §11).
 * Shell de tabs: cada rol ve solo los que le corresponden, con los mismos
 * gates que el router backend (`formacion_refuerzo.py`).
 */
import { useMemo, useState } from 'react';
import { Box, Tabs, Tab, Typography, Alert } from '@mui/material';
import { useAuthStore } from '../../store/auth.store';
import MisCapsulas from './refuerzo/MisCapsulas';
import CampanasRefuerzo from './refuerzo/CampanasRefuerzo';
import KpiRefuerzo from './refuerzo/KpiRefuerzo';

// Mismos gates que el router: RequireCapacitacion y el _VEN_TODO del §11.5.
// "Mis cápsulas" va por rol y no por `rm_id` porque el store de auth solo
// guarda el rol; el backend exige el enlace a representante y responde 403 si
// falta, que es la única fuente de verdad de ese dato.
const ROLES_CAPSULAS = ['REPRESENTANTE_MEDICO'];
const ROLES_CAMPANAS = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
const ROLES_KPI = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'PRESIDENCIA',
  'GERENTE_MEDICO', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'];

export default function Refuerzo() {
  const rol = useAuthStore((s) => s.rol);
  const [tab, setTab] = useState(0);

  const tabs = useMemo(() => {
    const t: { label: string; nodo: JSX.Element }[] = [];
    if (rol && ROLES_CAPSULAS.includes(rol)) t.push({ label: 'Mis cápsulas', nodo: <MisCapsulas /> });
    if (rol && ROLES_CAMPANAS.includes(rol)) t.push({ label: 'Campañas', nodo: <CampanasRefuerzo /> });
    if (rol && ROLES_KPI.includes(rol)) t.push({ label: 'KPI', nodo: <KpiRefuerzo /> });
    return t;
  }, [rol]);

  const activo = Math.min(tab, Math.max(0, tabs.length - 1));

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Refuerzo de Memoria</Typography>
      {tabs.length === 0 ? (
        <Alert severity="info">Tu usuario no tiene acceso a ninguna vista de Refuerzo.</Alert>
      ) : (
        <>
          <Tabs value={activo} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
            {tabs.map((t) => <Tab key={t.label} label={t.label} />)}
          </Tabs>
          {tabs[activo]?.nodo}
        </>
      )}
    </Box>
  );
}
```

Nota verificada: `frontend/src/store/auth.store.ts` expone `rol` (tipo `Rol | null`) pero **no** guarda `rm_id`. Por eso el gate de "Mis cápsulas" es por rol. Si el usuario tuviera el rol pero no el enlace a representante, el backend responde 403 y el tab muestra ese error — comportamiento aceptable y honesto (el enlace lo corrige un ADMIN en Usuarios).

- [ ] **Step 3: Registrar la ruta lazy en `App.tsx`**

Junto a los otros `lazyWithReload` de formación:
```tsx
const Refuerzo = lazyWithReload(() => import('./pages/formacion/Refuerzo'));
```
Y junto a las rutas `formacion/*` existentes:
```tsx
<Route path="formacion/refuerzo" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','CAPACITACION','PRESIDENCIA','GERENTE_MEDICO','GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><Refuerzo /></ProtectedRoute>} />
```

- [ ] **Step 4: Agregar el ítem al Sidebar**

En el mismo grupo donde están 'Plan de Brechas', 'Calendario de Coaching' y 'Simulacro de Venta':
```tsx
{ label: 'Refuerzo de Memoria', path: '/formacion/refuerzo', icon: <Psychology />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'PRESIDENCIA', 'GERENTE_MEDICO', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
```
Verifica que `Psychology` esté importado desde `@mui/icons-material`; agrégalo al import existente si falta.

- [ ] **Step 5: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK. La ruta carga y muestra las tabs; el contenido de cada tab está vacío (stubs).

- [ ] **Step 6: Commit**

```bash
git add frontend/src/pages/formacion/Refuerzo.tsx frontend/src/pages/formacion/refuerzo/ frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(formacion) Refuerzo: shell de tabs por rol + ruta + sidebar"
```

---

### Task 3: Tab "Mis cápsulas" (§10.5–§10.7)

**Files:**
- Modify: `frontend/src/pages/formacion/refuerzo/MisCapsulas.tsx`

**Interfaces:**
- Consumes: `misCapsulas`, `responderCapsula`, `misPuntos`, tipos `CapsulaPendiente` y `ResultadoRespuesta` del service de Task 1.
- Produce: nada (hoja).

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * MisCapsulas.tsx — Tab del representante (§10.5-§10.7).
 * La opción correcta NO llega con el enunciado: solo al responder. Por eso el
 * resaltado se hace con el resultado de la mutation, sin recargar la lista.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, Button, Stack, Alert, Chip,
  TextField, CircularProgress, Divider,
} from '@mui/material';
import { EmojiEvents } from '@mui/icons-material';
import {
  misCapsulas, responderCapsula, misPuntos,
  type CapsulaPendiente, type ResultadoRespuesta,
} from '../../../services/refuerzo.service';

const ETIQUETA_FORMATO: Record<string, string> = {
  microlectura: 'Microlectura', reto: 'Reto',
  caso_breve: 'Caso breve', reflexion_abierta: 'Reflexión abierta',
};

export default function MisCapsulas() {
  const qc = useQueryClient();
  const [resultados, setResultados] = useState<Record<number, ResultadoRespuesta>>({});
  const [textos, setTextos] = useState<Record<number, string>>({});

  const pendientes = useQuery({ queryKey: ['refuerzo-mis-capsulas'], queryFn: misCapsulas });
  const puntos = useQuery({ queryKey: ['refuerzo-mis-puntos'], queryFn: () => misPuntos() });

  const responder = useMutation({
    mutationFn: (v: { capsulaId: number; opcion?: string; texto_libre?: string }) =>
      responderCapsula(v.capsulaId, { opcion: v.opcion, texto_libre: v.texto_libre }),
    onSuccess: (r) => {
      setResultados((prev) => ({ ...prev, [r.capsula_id]: r }));
      qc.invalidateQueries({ queryKey: ['refuerzo-mis-puntos'] });
    },
  });

  if (pendientes.isLoading) return <CircularProgress />;
  // 403 típico: el usuario tiene rol de representante pero no está enlazado a
  // uno en Config.DIM_RM. Se dice tal cual en vez de mostrar una lista vacía.
  if (pendientes.isError) {
    return <Alert severity="warning">
      No se pudieron cargar tus cápsulas. Si tu usuario no está enlazado a un representante,
      pídele a un administrador que lo enlace.
    </Alert>;
  }

  const lista = pendientes.data || [];
  // Se conservan en pantalla las ya respondidas en esta sesión, para que el
  // usuario vea su corrección aunque salgan de "pendientes".
  const visibles = lista.filter((c) => !resultados[c.capsula_id]);
  const respondidas = lista.filter((c) => resultados[c.capsula_id]);

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" mb={2}>
        <EmojiEvents color="warning" />
        <Typography fontWeight={700}>{puntos.data?.puntos ?? 0} puntos de Refuerzo</Typography>
      </Stack>

      {visibles.length === 0 && respondidas.length === 0 && (
        <Alert severity="info">No tienes cápsulas pendientes.</Alert>
      )}

      {[...respondidas, ...visibles].map((c) => (
        <TarjetaCapsula key={c.capsula_id} capsula={c}
          resultado={resultados[c.capsula_id]}
          texto={textos[c.capsula_id] || ''}
          onTexto={(v) => setTextos((p) => ({ ...p, [c.capsula_id]: v }))}
          enviando={responder.isPending && responder.variables?.capsulaId === c.capsula_id}
          onResponder={(opcion, texto_libre) =>
            responder.mutate({ capsulaId: c.capsula_id, opcion, texto_libre })} />
      ))}
    </Box>
  );
}

function TarjetaCapsula({ capsula, resultado, texto, onTexto, enviando, onResponder }: {
  capsula: CapsulaPendiente;
  resultado?: ResultadoRespuesta;
  texto: string;
  onTexto: (v: string) => void;
  enviando: boolean;
  onResponder: (opcion?: string, texto_libre?: string) => void;
}) {
  const opciones = capsula.opciones || {};
  const esReto = capsula.formato === 'reto';
  const esAbierta = capsula.formato === 'reflexion_abierta';

  return (
    <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" mb={1}>
          <Chip size="small" color="primary" label={ETIQUETA_FORMATO[capsula.formato] || capsula.formato} />
          <Typography variant="caption" color="text.secondary">
            {capsula.campana} · Ronda {capsula.ronda}
          </Typography>
        </Stack>
        <Typography sx={{ mb: 2 }}>{capsula.enunciado}</Typography>

        {esReto && (
          <Stack spacing={1}>
            {Object.entries(opciones).map(([k, v]) => {
              const esCorrecta = resultado && k === resultado.opcion_correcta;
              const elegidaMal = resultado && k === resultado.opcion_seleccionada && !esCorrecta;
              return (
                <Button key={k} fullWidth
                  variant={resultado ? 'outlined' : 'contained'}
                  color={esCorrecta ? 'success' : elegidaMal ? 'error' : 'primary'}
                  disabled={!!resultado || enviando}
                  onClick={() => onResponder(k, undefined)}
                  sx={{ justifyContent: 'flex-start', textTransform: 'none' }}>
                  <strong style={{ marginRight: 8 }}>{k}.</strong> {v}
                </Button>
              );
            })}
          </Stack>
        )}

        {esAbierta && !resultado && (
          <Stack spacing={1}>
            <TextField multiline minRows={3} fullWidth value={texto}
              onChange={(e) => onTexto(e.target.value)} placeholder="Escribe tu reflexión…" />
            <Button variant="contained" disabled={!texto.trim() || enviando}
              onClick={() => onResponder(undefined, texto)}>Enviar</Button>
          </Stack>
        )}

        {!esReto && !esAbierta && !resultado && (
          <Button variant="contained" disabled={enviando}
            onClick={() => onResponder(undefined, undefined)}>Marcar como leída</Button>
        )}

        {enviando && <CircularProgress size={20} sx={{ mt: 1 }} />}

        {resultado && (
          <>
            <Divider sx={{ my: 2 }} />
            {resultado.repetida && (
              <Alert severity="info" sx={{ mb: 1 }}>Ya habías respondido esta cápsula.</Alert>
            )}
            {/* es_acierto null = no hay correcta que medir (§10.5): solo acuse. */}
            {resultado.es_acierto !== null && (
              <Alert severity={resultado.es_acierto ? 'success' : 'error'} sx={{ mb: 1 }}>
                {resultado.es_acierto ? '¡Correcto!' : `La opción correcta era la ${resultado.opcion_correcta}.`}
              </Alert>
            )}
            {resultado.explicacion && (
              <Alert severity="info" sx={{ mb: 1 }}>{resultado.explicacion}</Alert>
            )}
            <Typography variant="caption" color="text.secondary">
              +{resultado.puntos_obtenidos} puntos · participación {resultado.pct_participacion}% ·
              respondida en {resultado.tiempo_respuesta_seg}s
            </Typography>
          </>
        )}
      </CardContent>
    </Card>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/formacion/refuerzo/MisCapsulas.tsx
git commit -m "feat(formacion) Refuerzo: tab Mis capsulas con correccion inmediata (10.7)"
```

---

### Task 4: Tab "Campañas" (§10.2–§10.4)

**Files:**
- Modify: `frontend/src/pages/formacion/refuerzo/CampanasRefuerzo.tsx`

**Interfaces:**
- Consumes: `listarCampanas`, `crearCampana`, `generarCalendario`, `programarRonda`, `agregarCapsula`, `publicarRonda`, tipos `Campana`, `Ronda`, `CampanaEntrada`, `CapsulaEntrada`, constantes `DURACIONES`, `MODOS_ESPACIADO`, `FORMATOS`; `useCicloStore`.
- Produce: nada (hoja).

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * CampanasRefuerzo.tsx — Tab de Capacitación (§10.2-§10.4).
 * VISTA sugiere el calendario; nada sale publicado hasta que alguien lo
 * confirma y publica explícitamente (§10.3).
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, MenuItem, FormControl, InputLabel, Select, CircularProgress, Snackbar,
} from '@mui/material';
import { Add, CalendarMonth, Publish, Check } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import {
  listarCampanas, crearCampana, generarCalendario, programarRonda,
  agregarCapsula, publicarRonda,
  DURACIONES, MODOS_ESPACIADO, FORMATOS,
  type Campana, type Ronda, type ModoEspaciado, type FormatoCapsula,
} from '../../../services/refuerzo.service';

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o string.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

export default function CampanasRefuerzo() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const [sel, setSel] = useState<Campana | null>(null);
  const [rondas, setRondas] = useState<Ronda[]>([]);
  const [nueva, setNueva] = useState(false);
  const [capsulaEn, setCapsulaEn] = useState<Ronda | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const campanas = useQuery({
    queryKey: ['refuerzo-campanas', paisCodigo],
    queryFn: () => listarCampanas(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const calendario = useMutation({
    mutationFn: (campanaId: number) => generarCalendario(campanaId),
    onSuccess: (r) => { setRondas(r); setAviso({ sev: 'success', msg: `${r.length} ronda(s) sugeridas.` }); },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo generar el calendario.') }),
  });

  const confirmar = useMutation({
    mutationFn: (rondaId: number) => programarRonda(rondaId),
    onSuccess: (r) => {
      setRondas((prev) => prev.map((x) => x.id === r.id
        ? { ...x, fecha_hora_programada: r.fecha_hora_programada } : x));
      setAviso({ sev: 'success', msg: 'Ronda confirmada.' });
    },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo confirmar.') }),
  });

  const publicar = useMutation({
    mutationFn: (rondaId: number) => publicarRonda(rondaId),
    onSuccess: (r) => {
      setRondas((prev) => prev.map((x) => x.id === r.id ? { ...x, publicada: r.publicada } : x));
      setAviso({ sev: 'success', msg: 'Ronda publicada y notificada.' });
    },
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo publicar la ronda.') }),
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={2}>
        <Typography variant="subtitle1" fontWeight={700} sx={{ flex: 1 }}>Campañas de {paisCodigo}</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setNueva(true)}>Nueva campaña</Button>
      </Stack>

      {campanas.isLoading ? <CircularProgress /> : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Nombre</TableCell><TableCell>Duración</TableCell>
                <TableCell>Espaciado</TableCell><TableCell>Estado</TableCell>
                <TableCell>GM</TableCell><TableCell align="right">Rondas</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(campanas.data || []).length === 0 ? (
                <TableRow><TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">Sin campañas en este país.</Typography>
                </TableCell></TableRow>
              ) : (campanas.data || []).map((c) => (
                <TableRow key={c.id} selected={sel?.id === c.id}>
                  <TableCell>{c.nombre}</TableCell>
                  <TableCell>{c.duracion_dias} días</TableCell>
                  <TableCell>{c.modo_espaciado}</TableCell>
                  <TableCell><Chip size="small" label={c.estado} /></TableCell>
                  <TableCell>
                    <Chip size="small" color={c.aprobado_por_gm ? 'success' : 'default'}
                      label={c.aprobado_por_gm ? 'Aprobada' : 'Sin aprobar'} />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" startIcon={<CalendarMonth />}
                      onClick={() => { setSel(c); setRondas([]); calendario.mutate(c.id); }}
                      disabled={calendario.isPending}>Calendario</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {sel && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Rondas de «{sel.nombre}»</Typography>
          {rondas.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Pulsa «Calendario» para generar las rondas sugeridas.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell><TableCell>Sugerida</TableCell>
                  <TableCell>Programada</TableCell><TableCell>Estado</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rondas.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.numero_ronda}</TableCell>
                    <TableCell>{r.fecha_hora_sugerida ? new Date(r.fecha_hora_sugerida).toLocaleString() : '—'}</TableCell>
                    <TableCell>{r.fecha_hora_programada ? new Date(r.fecha_hora_programada).toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      <Chip size="small" color={r.publicada ? 'success' : 'default'}
                        label={r.publicada ? 'Publicada' : 'Borrador'} />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" startIcon={<Check />} onClick={() => confirmar.mutate(r.id)}
                        disabled={confirmar.isPending || r.publicada}>Confirmar</Button>
                      <Button size="small" startIcon={<Add />} onClick={() => setCapsulaEn(r)}
                        disabled={r.publicada}>Cápsula</Button>
                      <Button size="small" startIcon={<Publish />} onClick={() => publicar.mutate(r.id)}
                        disabled={publicar.isPending || r.publicada}>Publicar</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
      )}

      <DialogoCampana abierto={nueva} paisCodigo={paisCodigo}
        onClose={() => setNueva(false)}
        onCreada={() => { setNueva(false); qc.invalidateQueries({ queryKey: ['refuerzo-campanas', paisCodigo] }); setAviso({ sev: 'success', msg: 'Campaña creada.' }); }} />

      <DialogoCapsula ronda={capsulaEn} onClose={() => setCapsulaEn(null)}
        onCreada={() => { setCapsulaEn(null); setAviso({ sev: 'success', msg: 'Cápsula agregada.' }); }} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoCampana({ abierto, paisCodigo, onClose, onCreada }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onCreada: () => void;
}) {
  const [nombre, setNombre] = useState('');
  const [duracion, setDuracion] = useState(30);
  const [modo, setModo] = useState<ModoEspaciado>('creciente');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => crearCampana({ pais_codigo: paisCodigo, nombre, duracion_dias: duracion, modo_espaciado: modo }),
    onSuccess: () => { setNombre(''); setError(null); onCreada(); },
    onError: (e) => setError(detalleError(e, 'No se pudo crear la campaña.')),
  });

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Nueva campaña de Refuerzo</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
            fullWidth required inputProps={{ maxLength: 200 }} />
          <FormControl fullWidth>
            <InputLabel>Duración</InputLabel>
            <Select label="Duración" value={duracion} onChange={(e) => setDuracion(Number(e.target.value))}>
              {DURACIONES.map((d) => <MenuItem key={d} value={d}>{d} días</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel>Modo de espaciado</InputLabel>
            <Select label="Modo de espaciado" value={modo} onChange={(e) => setModo(e.target.value as ModoEspaciado)}>
              {MODOS_ESPACIADO.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
            </Select>
          </FormControl>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!nombre.trim() || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Creando…' : 'Crear'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoCapsula({ ronda, onClose, onCreada }: {
  ronda: Ronda | null; onClose: () => void; onCreada: () => void;
}) {
  const [formato, setFormato] = useState<FormatoCapsula>('microlectura');
  const [enunciado, setEnunciado] = useState('');
  const [orden, setOrden] = useState(1);
  const [opcionesTxt, setOpcionesTxt] = useState('A: \nB: ');
  const [correcta, setCorrecta] = useState('');
  const [explicacion, setExplicacion] = useState('');
  const [error, setError] = useState<string | null>(null);

  const esReto = formato === 'reto';

  // "A: texto" por línea → {A: "texto"}. Formato simple y explícito para el
  // usuario; el backend espera un objeto clave→texto.
  const parseOpciones = (): Record<string, string> => {
    const out: Record<string, string> = {};
    opcionesTxt.split('\n').forEach((linea) => {
      const i = linea.indexOf(':');
      if (i > 0) {
        const k = linea.slice(0, i).trim();
        const v = linea.slice(i + 1).trim();
        if (k && v) out[k] = v;
      }
    });
    return out;
  };

  const crear = useMutation({
    mutationFn: () => agregarCapsula(ronda!.id, {
      formato, enunciado, orden,
      opciones: esReto ? parseOpciones() : null,
      opcion_correcta: esReto ? correcta : null,
      explicacion: explicacion || null,
    }),
    onSuccess: () => { setEnunciado(''); setCorrecta(''); setError(null); onCreada(); },
    onError: (e) => setError(detalleError(e, 'No se pudo agregar la cápsula.')),
  });

  // El backend rechaza un reto sin correcta (422): se exige antes de enviar.
  const opciones = esReto ? parseOpciones() : {};
  const puedeGuardar = enunciado.trim() &&
    (!esReto || (correcta.trim() && Object.keys(opciones).length >= 2 && opciones[correcta.trim()] !== undefined));

  return (
    <Dialog open={!!ronda} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Agregar cápsula {ronda ? `a la ronda ${ronda.numero_ronda}` : ''}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <FormControl fullWidth>
            <InputLabel>Formato</InputLabel>
            <Select label="Formato" value={formato} onChange={(e) => setFormato(e.target.value as FormatoCapsula)}>
              {FORMATOS.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField label="Enunciado" value={enunciado} onChange={(e) => setEnunciado(e.target.value)}
            fullWidth required multiline minRows={2} />
          <TextField label="Orden" type="number" value={orden}
            onChange={(e) => setOrden(Number(e.target.value) || 1)} fullWidth />
          {esReto && (
            <>
              <TextField label="Opciones (una por línea, formato «A: texto»)" value={opcionesTxt}
                onChange={(e) => setOpcionesTxt(e.target.value)} fullWidth multiline minRows={3} />
              <TextField label="Opción correcta (la clave, ej. A)" value={correcta}
                onChange={(e) => setCorrecta(e.target.value)} fullWidth required
                helperText="Un reto necesita su opción correcta para corregirse al instante." />
            </>
          )}
          <TextField label="Explicación (opcional)" value={explicacion}
            onChange={(e) => setExplicacion(e.target.value)} fullWidth multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!puedeGuardar || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Guardando…' : 'Agregar'}</Button>
      </DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/formacion/refuerzo/CampanasRefuerzo.tsx
git commit -m "feat(formacion) Refuerzo: tab Campanas (calendario sugerido, confirmar, capsulas, publicar)"
```

---

### Task 5: Tab "KPI" (§11)

**Files:**
- Modify: `frontend/src/pages/formacion/refuerzo/KpiRefuerzo.tsx`

**Interfaces:**
- Consumes: `reporteKpi`, tipos `ReporteKpi`, `Metricas`, `PreguntaExtremo` del service de Task 1; `useCicloStore`.
- Produce: nada (hoja).

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * KpiRefuerzo.tsx — Reporte de KPI del Refuerzo (§11): 3 métricas por 4 desgloses.
 *
 * Participación y aciertos NO se mezclan (§10.8): se calculan sobre universos
 * distintos y se muestran en columnas separadas. `pct_aciertos` puede ser null
 * (nada calificable en el segmento) y eso NO es 0.
 * El alcance lo recorta el backend por rol (§11.5); `por_gd` puede no venir.
 */
import { useQuery } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Table, TableHead, TableBody, TableRow, TableCell,
  Grid, Card, CardContent, Alert, CircularProgress, Stack,
} from '@mui/material';
import { useCicloStore } from '../../../store/ciclo.store';
import { reporteKpi, type Metricas, type PreguntaExtremo } from '../../../services/refuerzo.service';

const fmtTiempo = (seg: number) =>
  seg >= 60 ? `${Math.floor(seg / 60)} min ${seg % 60}s` : `${seg}s`;
const pct = (v: number | null) => (v === null || v === undefined ? '—' : `${v}%`);

export default function KpiRefuerzo() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const kpi = useQuery({
    queryKey: ['refuerzo-kpi', paisCodigo],
    queryFn: () => reporteKpi(paisCodigo ? { pais_codigo: paisCodigo } : {}),
  });

  if (kpi.isLoading) return <CircularProgress />;
  if (kpi.isError) return <Alert severity="warning">No se pudo cargar el KPI de Refuerzo.</Alert>;
  const d = kpi.data;
  if (!d) return null;

  if (d.total_respuestas === 0) {
    return <Alert severity="info">Todavía no hay respuestas de Refuerzo para este alcance.</Alert>;
  }

  return (
    <Box>
      <Grid container spacing={2} mb={2}>
        <Tarjeta titulo="Participación" valor={pct(d.general.pct_participacion)} />
        <Tarjeta titulo="Aciertos" valor={pct(d.general.pct_aciertos)} />
        <Tarjeta titulo="Tiempo promedio" valor={fmtTiempo(d.general.tiempo_promedio_seg)} />
        <Tarjeta titulo="Respuestas" valor={String(d.total_respuestas)} />
      </Grid>

      {(d.general.pregunta_mas_acertada || d.general.pregunta_menos_acertada) && (
        <Grid container spacing={2} mb={2}>
          <Extremo titulo="Pregunta más acertada" p={d.general.pregunta_mas_acertada} />
          <Extremo titulo="Pregunta menos acertada" p={d.general.pregunta_menos_acertada} />
        </Grid>
      )}

      <TablaDesglose titulo="Por representante" clave="rm_id" etiqueta="RM" filas={d.por_representante} />
      <TablaDesglose titulo="Por producto" clave="producto_id" etiqueta="Producto" filas={d.por_producto} />
      <TablaDesglose titulo="Por país" clave="pais_codigo" etiqueta="País" filas={d.por_pais} />
      {/* El backend omite `por_gd` para GD y RM (§11.3.c): no se inventa la tabla. */}
      {d.por_gd && (
        <TablaDesglose titulo="Por gerente de distrito" clave="gerente_id" etiqueta="GD" filas={d.por_gd} />
      )}
    </Box>
  );
}

function Tarjeta({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <Grid item xs={6} md={3}>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent>
          <Typography variant="caption" color="text.secondary">{titulo}</Typography>
          <Typography variant="h5" fontWeight={800}>{valor}</Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}

function Extremo({ titulo, p }: { titulo: string; p: PreguntaExtremo | null }) {
  if (!p) return null;
  return (
    <Grid item xs={12} md={6}>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent>
          <Typography variant="caption" color="text.secondary">{titulo}</Typography>
          <Typography variant="body2" sx={{ my: 1 }}>{p.enunciado}</Typography>
          <Stack direction="row" spacing={2}>
            <Typography variant="caption">Aciertos: <strong>{p.pct_aciertos}%</strong></Typography>
            <Typography variant="caption">Respuestas: <strong>{p.respuestas}</strong></Typography>
          </Stack>
        </CardContent>
      </Card>
    </Grid>
  );
}

function TablaDesglose({ titulo, clave, etiqueta, filas }: {
  titulo: string; clave: string; etiqueta: string;
  filas: (Metricas & Record<string, unknown>)[];
}) {
  return (
    <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3, p: 2 }}>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>{titulo}</Typography>
      {filas.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Sin datos.</Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{etiqueta}</TableCell>
              <TableCell align="right">Respuestas</TableCell>
              <TableCell align="right">Participación</TableCell>
              <TableCell align="right">Aciertos</TableCell>
              <TableCell align="right">Tiempo prom.</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filas.map((f, i) => (
              <TableRow key={`${String(f[clave])}-${i}`}>
                <TableCell>{f[clave] === null || f[clave] === undefined ? '—' : String(f[clave])}</TableCell>
                <TableCell align="right">{f.respuestas}</TableCell>
                <TableCell align="right">{pct(f.pct_participacion)}</TableCell>
                <TableCell align="right">{pct(f.pct_aciertos)}</TableCell>
                <TableCell align="right">{fmtTiempo(f.tiempo_promedio_seg)}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/formacion/refuerzo/KpiRefuerzo.tsx
git commit -m "feat(formacion) Refuerzo: tab KPI (3 metricas x 4 desgloses, por_gd condicional)"
```

---

## Verificación en vivo (tras Task 5, no es un commit)

Con JWT minteado (sin escribir contraseña), por rol:

1. Capacitación: crear campaña → «Calendario» → «Confirmar» una ronda → «Cápsula» tipo `reto` con opciones y correcta → «Publicar».
2. Intentar guardar un `reto` sin opción correcta → el botón «Agregar» está deshabilitado.
3. RM: abrir «Mis cápsulas»; en la pestaña de red, confirmar que `GET /mis-capsulas` **no** trae `opcion_correcta`; responder → ver resaltado verde/rojo + explicación + puntos.
4. Responder otra vez la misma cápsula (recargando) → `repetida: true`, sin cambiar el resultado.
5. Una cápsula `reflexion_abierta` → tras responder NO debe decir correcto/incorrecto (solo acuse y puntos).
6. GD y RM: tab KPI → **no** aparece la tabla «Por gerente de distrito». Capacitación: sí aparece.

---

## Self-Review

- **Cobertura del spec:**
  - §2 estructura de tabs por rol + archivos → Task 2.
  - §3 contrato y tipos → Task 1.
  - §4 Mis cápsulas (formatos, corrección inmediata, `es_acierto null`, `repetida`, puntos) → Task 3.
  - §5 Campañas (país del contexto, crear, calendario sugerido, confirmar, cápsula con validación de `reto`, publicar con 409) → Task 4.
  - §6 KPI (3 métricas, extremos, 4 desgloses, `por_gd` condicional, `pct_aciertos` null ≠ 0) → Task 5.
  - §7 fuera de alcance → respetado (no se editan/eliminan campañas; `aprobado_por_gm` solo se muestra; sin gráficos; `producto_id`/`ciclo_id`/`material_fuente_id` no se piden en el diálogo por no tener catálogo — se omiten, el backend los acepta nulos).
  - §8 verificación → sección "Verificación en vivo".
- **Placeholder scan:** sin TBD/TODO; código completo en cada paso. Los stubs de Task 2 son intencionales y se reemplazan en Tasks 3-5 conservando la firma `export default function X()`.
- **Consistencia de tipos:** `Metricas` incluye `pregunta_*` (coincide con `_metricas | _pregunta_extremos` del backend); `TablaDesglose` recibe `(Metricas & Record<string, unknown>)[]`, compatible con `por_representante`/`por_producto`/`por_pais`/`por_gd`; `detalleError` se define en Task 4 (único archivo que lo usa); `responder.variables?.capsulaId` coincide con el tipo del `mutationFn` de Task 3.
