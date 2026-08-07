# Pantalla de Onboarding + Biblioteca — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar interfaz a la Fase 2 del módulo de Formación — Biblioteca (subir, aprobar, confirmar lectura, progreso) y Onboarding (ruta estándar de 10 pasos, asignación, avance con bloqueos) — más el endpoint que permite al representante descubrir su propia ruta.

**Architecture:** Un endpoint backend nuevo de solo lectura con auto-scope (`GET /formacion/onboarding/mis-asignaciones`), y una ruta frontend `/formacion/onboarding` con 3 tabs por rol, cada uno en su archivo. Un service axios tipado centraliza el contrato.

**Tech Stack:** Backend: Python 3.13, FastAPI, SQLAlchemy 2.0, pytest. Frontend: React 18 + TypeScript, MUI v6, TanStack Query v5, axios, Zustand, react-router-dom v6 (`lazyWithReload`).

## Global Constraints

- El ÚNICO cambio de backend permitido es el de la Task 1 (una función de servicio + un endpoint + tests). **Sin migración** (no cambia el modelo).
- **El RM solo ve material aprobado**: lo garantiza el backend (`solo_aprobados` cuando el rol es REPRESENTANTE_MEDICO). La UI no filtra por su cuenta ni asume qué llega.
- **Quién puede marcar un paso lo decide el backend** (§4.6, `RolNoAutorizado` → 403). La UI muestra el botón cuando el paso está `disponible` y deja que el backend rechace; NO replica la regla de rol.
- **Los `bloqueos[]` se muestran TODOS**, no solo el primero: el backend los informa juntos a propósito.
- Valores permitidos: `tipo` de material ∈ {manual, ayuda_visual, estudio_clinico, ficha_tecnica, video}; `rol_en_ruta` ∈ {principal, relacionado}. `obligatorio` por defecto **true** (§5.3).
- Los 409 (`MaterialNoAprobado`, `PasoBloqueado`) y 403 (`RolNoAutorizado`) se muestran con el **mensaje real del backend**.
- País desde `useCicloStore((s) => s.paisCodigo)` (`string | null`); con `null`, query deshabilitada y aviso "Selecciona un país en el encabezado."
- `linea_id`, `rm_id`, `plantilla_id`, `asignacion_id`, `producto_id` van como campos numéricos: este router no expone catálogos para poblarlos.
- Estilo: MUI `sx`, React Query, español en el copy, `.then(r => r.data)` en el service. Referencias: `frontend/src/pages/formacion/Refuerzo.tsx` (shell de tabs) y `frontend/src/pages/formacion/refuerzo/CampanasRefuerzo.tsx` (tablas + diálogos + `detalleError`).
- Tests automatizados SOLO en la Task 1 (backend). El frontend se verifica con `npm run build` + smoke.

---

### Task 1: Backend — `GET /formacion/onboarding/mis-asignaciones`

**Files:**
- Modify: `backend/app/services/formacion_onboarding_service.py`
- Modify: `backend/app/api/v1/routers/formacion.py`
- Test: `backend/tests/test_formacion_onboarding_biblioteca.py`

**Interfaces:**
- Produce: `asignaciones_de_rm(db: Session, rm_id: int) -> list[dict]` en el servicio, y el endpoint `GET /formacion/onboarding/mis-asignaciones` que devuelve `MiAsignacion[]` con las claves `id`, `plantilla_id`, `nombre_plantilla`, `fecha_inicio`, `progreso_pct`, `completada_en`.

- [ ] **Step 1: Escribir el test que falla**

Añadir al final de `backend/tests/test_formacion_onboarding_biblioteca.py` (usa el fixture `escenario` que ya existe en el archivo, el cual crea un RM, una plantilla y una asignación):

```python
def test_asignaciones_de_rm_devuelve_solo_las_propias(escenario):
    """El representante descubre su ruta sin conocer el id (§4).

    Se crea una segunda asignación para OTRO representante: si la consulta no
    filtrara por rm_id, aparecerían las dos y el RM vería la ruta ajena.
    """
    db = escenario["db"]
    rm = escenario["rm"]
    plantilla = escenario["plantilla"]

    otro = RepresentanteMedico(pais_codigo="DO", linea_id=escenario["linea"].id,
                               codigo="VM02", nombre="Otro Representante")
    db.add(otro)
    db.flush()
    onboarding.asignar(db, plantilla.id, otro.id, date(2026, 7, 15))
    db.commit()

    filas = onboarding.asignaciones_de_rm(db, rm.id)

    assert len(filas) == 1
    assert filas[0]["id"] == escenario["asignacion"].id
    assert filas[0]["plantilla_id"] == plantilla.id
    assert filas[0]["nombre_plantilla"] == "Onboarding Cardiología"
    assert filas[0]["progreso_pct"] == 0.0
    assert filas[0]["completada_en"] is None


def test_asignaciones_de_rm_sin_ruta_devuelve_lista_vacia(escenario):
    """Un representante recién dado de alta no tiene ruta: lista vacía, no error."""
    db = escenario["db"]
    nuevo = RepresentanteMedico(pais_codigo="DO", linea_id=escenario["linea"].id,
                                codigo="VM03", nombre="Sin Ruta")
    db.add(nuevo)
    db.commit()

    assert onboarding.asignaciones_de_rm(db, nuevo.id) == []
```

- [ ] **Step 2: Correr el test para verificar que falla**

Run: `cd backend && python -m pytest tests/test_formacion_onboarding_biblioteca.py -k asignaciones_de_rm -v`
Expected: FAIL con `AttributeError: module 'app.services.formacion_onboarding_service' has no attribute 'asignaciones_de_rm'`.
(Si no hay PostgreSQL alcanzable, los tests se SALTAN — en ese caso anótalo en el reporte y continúa; el archivo entero se salta por diseño.)

- [ ] **Step 3: Implementar la función en el servicio**

Añadir a `backend/app/services/formacion_onboarding_service.py` (después de `asignar`, antes de `_producto_ids_requeridos`):

```python
def asignaciones_de_rm(db: Session, rm_id: int) -> list[dict]:
    """Las rutas asignadas a un representante, para que descubra la suya (§4).

    `estado_ruta` consulta por id de asignación, que el representante no tiene
    forma de conocer: sin esto, la ruta existe pero él no puede abrirla.
    """
    filas = (db.query(OnboardingAsignacion, OnboardingPlantilla)
             .join(OnboardingPlantilla,
                   OnboardingAsignacion.plantilla_id == OnboardingPlantilla.id)
             .filter(OnboardingAsignacion.rm_id == rm_id)
             .order_by(OnboardingAsignacion.fecha_inicio.desc())
             .all())
    return [{
        "id": a.id, "plantilla_id": a.plantilla_id,
        "nombre_plantilla": p.nombre_plantilla,
        "fecha_inicio": a.fecha_inicio,
        "progreso_pct": float(a.progreso_pct),
        "completada_en": a.completada_en,
    } for a, p in filas]
```

Verifica que `OnboardingPlantilla` y `OnboardingAsignacion` ya estén importados en ese módulo (lo están, los usa `estado_ruta`).

- [ ] **Step 4: Correr el test para verificar que pasa**

Run: `cd backend && python -m pytest tests/test_formacion_onboarding_biblioteca.py -k asignaciones_de_rm -v`
Expected: 2 passed (o SKIPPED si no hay PostgreSQL).

- [ ] **Step 5: Exponer el endpoint**

Añadir a `backend/app/api/v1/routers/formacion.py`, **antes** del endpoint
`@router.get("/onboarding/asignaciones/{asignacion_id}")` (el orden importa: una ruta
literal debe declararse antes que una con parámetro que podría capturarla):

```python
@router.get("/onboarding/mis-asignaciones",
            summary="Mis rutas de formación (el representante descubre la suya)")
def mis_asignaciones(db: Session = Depends(get_db), usuario: Usuario = RequireAnyAuth):
    """Auto-scope: no recibe rm_id, siempre devuelve las del usuario en sesión.

    No es un filtro opcional sino el único comportamiento: no debe existir un
    camino por el que alguien pida la ruta de otro por esta vía.
    """
    return onboarding.asignaciones_de_rm(db, _rm_propio(usuario))
```

- [ ] **Step 6: Correr la suite completa del archivo**

Run: `cd backend && python -m pytest tests/test_formacion_onboarding_biblioteca.py -v`
Expected: todos pasan (o todos SKIPPED si no hay PostgreSQL). Ningún test previo se rompe.

- [ ] **Step 7: Commit**

```bash
git add backend/app/services/formacion_onboarding_service.py backend/app/api/v1/routers/formacion.py backend/tests/test_formacion_onboarding_biblioteca.py
git commit -m "feat(formacion) Onboarding: endpoint mis-asignaciones con auto-scope por rm_id"
```

---

### Task 2: Service `onboarding.service.ts` (tipos + 13 funciones)

**Files:**
- Create: `frontend/src/services/onboarding.service.ts`

**Interfaces:**
- Produce (para Tasks 3-6): tipos `TipoMaterial`, `RolEnRuta`, `Producto`, `Material`, `MaterialEntrada`, `ProgresoLectura`, `Confirmacion`, `Paso`, `MiAsignacion`, `PasoEstado`, `EstadoRuta`; constante `TIPOS_MATERIAL`; funciones `listarProductos`, `crearProducto`, `listarMateriales`, `subirMaterial`, `aprobarMaterial`, `confirmarLectura`, `confirmacionesDeMaterial`, `progresoLectura`, `crearPlantilla`, `pasosDePlantilla`, `asignarRuta`, `misAsignaciones`, `estadoRuta`, `completarPaso`.

- [ ] **Step 1: Crear el archivo completo**

```ts
/**
 * onboarding.service.ts — Onboarding y Biblioteca (§4 y §5).
 * Rutas exactas del router backend `/formacion`
 * (ver backend/app/api/v1/routers/formacion.py).
 *
 * El representante solo recibe material APROBADO: lo filtra el backend según el
 * rol, no esta capa.
 */
import { api } from './api';

export type TipoMaterial = 'manual' | 'ayuda_visual' | 'estudio_clinico' | 'ficha_tecnica' | 'video';
export type RolEnRuta = 'principal' | 'relacionado';

export const TIPOS_MATERIAL: TipoMaterial[] =
  ['manual', 'ayuda_visual', 'estudio_clinico', 'ficha_tecnica', 'video'];

export interface Producto {
  id: number; nombre_producto: string; rol_en_ruta: RolEnRuta; activo: boolean;
}

export interface Material {
  id: number; titulo: string; tipo: TipoMaterial; archivo_url: string;
  obligatorio: boolean; producto_id: number | null; aprobado_por_gm: boolean;
}

export interface MaterialEntrada {
  pais_codigo: string; titulo: string; tipo: TipoMaterial; archivo_url: string;
  producto_id?: number | null; obligatorio?: boolean;
  usado_en_examen_id?: number | null; usado_en_coaching_av?: boolean;
}

export interface ProgresoLectura {
  total: number; confirmados: number; completo: boolean;
  pendientes: { id: number; titulo: string; tipo: TipoMaterial }[];
}

export interface Confirmacion { rm_id: number; confirmado_en: string; }

export interface Paso {
  id: number; orden: number; titulo: string; tipo: string;
  plazo_sugerido: number | null; bloqueante: boolean; quien_lo_marca: string;
}

export interface MiAsignacion {
  id: number; plantilla_id: number; nombre_plantilla: string;
  fecha_inicio: string; progreso_pct: number; completada_en: string | null;
}

export interface PasoEstado {
  paso_id: number; orden: number; titulo: string; tipo: string;
  quien_lo_marca: string;
  estado: 'completado' | 'disponible' | 'bloqueado';
  bloqueos: string[];
  material?: ProgresoLectura | null;
}

export interface EstadoRuta {
  asignacion_id: number; rm_id: number; plantilla_id: number;
  total_pasos: number; completados: number; progreso_pct: number;
  pasos: PasoEstado[];
}

// ── Productos de línea (§4.3) ─────────────────────────────────────────────
export const listarProductos = (paisCodigo: string, lineaId: number) =>
  api.get<Producto[]>('/formacion/productos',
    { params: { pais_codigo: paisCodigo, linea_id: lineaId } }).then((r) => r.data);

export const crearProducto = (body: {
  pais_codigo: string; linea_id: number; nombre_producto: string; rol_en_ruta: RolEnRuta;
}) => api.post<{ id: number; nombre_producto: string; rol_en_ruta: RolEnRuta }>(
  '/formacion/productos', body).then((r) => r.data);

// ── Biblioteca (§5) ───────────────────────────────────────────────────────
export const listarMateriales = (paisCodigo: string, productoId?: number) =>
  api.get<Material[]>('/formacion/biblioteca', {
    params: { pais_codigo: paisCodigo, ...(productoId != null ? { producto_id: productoId } : {}) },
  }).then((r) => r.data);

export const subirMaterial = (body: MaterialEntrada) =>
  api.post<{ id: number; titulo: string; aprobado_por_gm: boolean }>(
    '/formacion/biblioteca', body).then((r) => r.data);

export const aprobarMaterial = (materialId: number) =>
  api.post<{ id: number; aprobado_por_gm: boolean }>(
    `/formacion/biblioteca/${materialId}/aprobar`).then((r) => r.data);

export const confirmarLectura = (materialId: number) =>
  api.post<{ material_id: number; confirmado_en: string }>(
    `/formacion/biblioteca/${materialId}/confirmar`).then((r) => r.data);

export const confirmacionesDeMaterial = (materialId: number) =>
  api.get<Confirmacion[]>(`/formacion/biblioteca/${materialId}/confirmaciones`)
    .then((r) => r.data);

export const progresoLectura = (productoIds: number[]) =>
  api.get<ProgresoLectura>('/formacion/biblioteca/progreso',
    { params: { producto_ids: productoIds.join(',') } }).then((r) => r.data);

// ── Onboarding (§4) ───────────────────────────────────────────────────────
export const crearPlantilla = (body: {
  pais_codigo: string; linea_id: number; nombre_plantilla: string; duracion_dias: number;
}) => api.post<{ id: number; nombre_plantilla: string; pasos: Paso[] }>(
  '/formacion/onboarding/plantillas', body).then((r) => r.data);

export const pasosDePlantilla = (plantillaId: number) =>
  api.get<Paso[]>(`/formacion/onboarding/plantillas/${plantillaId}/pasos`).then((r) => r.data);

export const asignarRuta = (body: { plantilla_id: number; rm_id: number; fecha_inicio?: string | null }) =>
  api.post<{ id: number; rm_id: number; progreso_pct: number }>(
    '/formacion/onboarding/asignaciones', body).then((r) => r.data);

export const misAsignaciones = () =>
  api.get<MiAsignacion[]>('/formacion/onboarding/mis-asignaciones').then((r) => r.data);

export const estadoRuta = (asignacionId: number) =>
  api.get<EstadoRuta>(`/formacion/onboarding/asignaciones/${asignacionId}`).then((r) => r.data);

export const completarPaso = (asignacionId: number, pasoId: number, observaciones?: string) =>
  api.post<{ paso_id: number; completado_en: string }>(
    `/formacion/onboarding/asignaciones/${asignacionId}/pasos/${pasoId}/completar`,
    null, { params: observaciones ? { observaciones } : {} }).then((r) => r.data);
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/onboarding.service.ts
git commit -m "feat(formacion) Onboarding: capa de servicio frontend (tipos + 14 endpoints)"
```

---

### Task 3: Shell de tabs + componente `ListaPasos` compartido + stubs + ruta + sidebar

Crea el contenedor de tabs, el componente de lista de pasos que reutilizan dos tabs, y los stubs. Registra ruta y sidebar.

**Files:**
- Create: `frontend/src/pages/formacion/Onboarding.tsx`
- Create: `frontend/src/pages/formacion/onboarding/ListaPasos.tsx`
- Create: `frontend/src/pages/formacion/onboarding/MiRuta.tsx` (stub)
- Create: `frontend/src/pages/formacion/onboarding/Biblioteca.tsx` (stub)
- Create: `frontend/src/pages/formacion/onboarding/RutasAdmin.tsx` (stub)
- Modify: `frontend/src/App.tsx`
- Modify: `frontend/src/components/layout/Sidebar.tsx`

**Interfaces:**
- Produce (para Tasks 4-6):
  - `export default function ListaPasos({ estado, onCompletar, completando }: { estado: EstadoRuta; onCompletar?: (pasoId: number) => void; completando?: number | null })` — renderiza la barra de progreso y la lista de pasos con sus bloqueos. Si `onCompletar` es `undefined`, no muestra botones (modo solo lectura).
  - Tres componentes por defecto sin props: `MiRuta`, `Biblioteca`, `RutasAdmin`.

- [ ] **Step 1: Crear los tres stubs**

`frontend/src/pages/formacion/onboarding/MiRuta.tsx`:
```tsx
// Tab "Mi ruta" del Onboarding (§4). Cuerpo en Task 4.
export default function MiRuta() {
  return null;
}
```

`frontend/src/pages/formacion/onboarding/Biblioteca.tsx`:
```tsx
// Tab "Biblioteca" (§5). Cuerpo en Task 5.
export default function Biblioteca() {
  return null;
}
```

`frontend/src/pages/formacion/onboarding/RutasAdmin.tsx`:
```tsx
// Tab "Rutas y plantillas" del Onboarding (§4, gestión). Cuerpo en Task 6.
export default function RutasAdmin() {
  return null;
}
```

- [ ] **Step 2: Crear `ListaPasos.tsx`**

```tsx
/**
 * ListaPasos.tsx — Lista de pasos de una ruta con su estado y bloqueos (§4).
 * Compartido por «Mi ruta» y por la consulta de asignaciones de «Rutas y plantillas».
 *
 * Los bloqueos se muestran TODOS: el backend los informa juntos a propósito, para
 * que nadie descubra el segundo motivo justo después de resolver el primero.
 */
import {
  Box, Card, CardContent, Typography, Chip, Stack, LinearProgress, Button, Alert,
} from '@mui/material';
import type { EstadoRuta, PasoEstado } from '../../../services/onboarding.service';

const COLOR_ESTADO: Record<PasoEstado['estado'], 'success' | 'primary' | 'default'> = {
  completado: 'success', disponible: 'primary', bloqueado: 'default',
};
const ETIQUETA_ESTADO: Record<PasoEstado['estado'], string> = {
  completado: 'Completado', disponible: 'Disponible', bloqueado: 'Bloqueado',
};

export default function ListaPasos({ estado, onCompletar, completando }: {
  estado: EstadoRuta;
  onCompletar?: (pasoId: number) => void;
  completando?: number | null;
}) {
  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={2} mb={1}>
        <Typography variant="body2" color="text.secondary">
          {estado.completados} de {estado.total_pasos} pasos
        </Typography>
        <Typography variant="body2" fontWeight={700}>{estado.progreso_pct}%</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={Math.min(100, estado.progreso_pct)}
        sx={{ mb: 2, height: 8, borderRadius: 4 }} />

      {estado.pasos.map((p) => (
        <Card key={p.paso_id} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
              <Chip size="small" label={`${p.orden}`} />
              <Typography sx={{ flex: 1 }} fontWeight={600}>{p.titulo}</Typography>
              <Chip size="small" color={COLOR_ESTADO[p.estado]} label={ETIQUETA_ESTADO[p.estado]} />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {p.tipo} · lo marca: {p.quien_lo_marca}
            </Typography>

            {p.bloqueos.length > 0 && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {p.bloqueos.map((b, i) => <div key={i}>{b}</div>)}
              </Alert>
            )}

            {p.material && p.material.total > 0 && (
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                Lectura obligatoria: {p.material.confirmados} de {p.material.total} confirmados
                {p.material.pendientes.length > 0 &&
                  ` — falta: ${p.material.pendientes.map((m) => m.titulo).join(', ')}`}
              </Typography>
            )}

            {onCompletar && p.estado === 'disponible' && (
              <Button size="small" variant="contained" sx={{ mt: 1 }}
                disabled={completando === p.paso_id}
                onClick={() => onCompletar(p.paso_id)}>
                {completando === p.paso_id ? 'Marcando…' : 'Marcar completado'}
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
```

- [ ] **Step 3: Crear el shell `Onboarding.tsx`**

```tsx
/**
 * Onboarding.tsx — Onboarding y Biblioteca (§4 y §5).
 * Shell de tabs: cada rol ve los que le corresponden, con los mismos gates que
 * el router backend (`formacion.py`).
 */
import { useMemo, useState } from 'react';
import { Box, Tabs, Tab, Typography, Alert } from '@mui/material';
import { useAuthStore } from '../../store/auth.store';
import MiRuta from './onboarding/MiRuta';
import Biblioteca from './onboarding/Biblioteca';
import RutasAdmin from './onboarding/RutasAdmin';

// "Mi ruta" es del representante (el backend exige enlace a rm_id).
const ROLES_MI_RUTA = ['REPRESENTANTE_MEDICO'];
// Gestión de rutas: RequireContenido del backend (crear plantillas). GERENTE_MEDICO
// sí puede operar este tab; solo «Asignar» le está vedado (RequireCapacitacion),
// y ese botón se oculta para él dentro del tab.
const ROLES_RUTAS = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
// Biblioteca: listar es RequireAnyAuth; las acciones se gatean dentro del tab.
const ROLES_BIBLIOTECA = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION',
  'GERENTE_MEDICO', 'PRESIDENCIA', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'];

export default function Onboarding() {
  const rol = useAuthStore((s) => s.rol);
  const [tab, setTab] = useState(0);

  const tabs = useMemo(() => {
    const t: { label: string; nodo: JSX.Element }[] = [];
    if (rol && ROLES_MI_RUTA.includes(rol)) t.push({ label: 'Mi ruta', nodo: <MiRuta /> });
    if (rol && ROLES_BIBLIOTECA.includes(rol)) t.push({ label: 'Biblioteca', nodo: <Biblioteca /> });
    if (rol && ROLES_RUTAS.includes(rol)) t.push({ label: 'Rutas y plantillas', nodo: <RutasAdmin /> });
    return t;
  }, [rol]);

  const activo = Math.min(tab, Math.max(0, tabs.length - 1));

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Formación inicial</Typography>
      {tabs.length === 0 ? (
        <Alert severity="info">Tu usuario no tiene acceso a ninguna vista de Formación inicial.</Alert>
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

- [ ] **Step 4: Registrar la ruta lazy en `App.tsx`**

Junto a los otros `lazyWithReload` de formación:
```tsx
const Onboarding = lazyWithReload(() => import('./pages/formacion/Onboarding'));
```
Y junto a las rutas `formacion/*`:
```tsx
<Route path="formacion/onboarding" element={<ProtectedRoute allowedRoles={['ADMIN','GERENTE_PRODUCTIVIDAD','CAPACITACION','GERENTE_MEDICO','PRESIDENCIA','GERENTE_DISTRITO','REPRESENTANTE_MEDICO']}><Onboarding /></ProtectedRoute>} />
```

- [ ] **Step 5: Agregar el ítem al Sidebar**

En el mismo grupo donde están 'Plan de Brechas', 'Calendario de Coaching', 'Simulacro de Venta' y 'Refuerzo de Memoria':
```tsx
{ label: 'Formación inicial', path: '/formacion/onboarding', icon: <School />, roles: ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO', 'PRESIDENCIA', 'GERENTE_DISTRITO', 'REPRESENTANTE_MEDICO'] },
```
Verifica que `School` esté importado desde `@mui/icons-material`; agrégalo al import existente si falta.

- [ ] **Step 6: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK. La ruta carga y muestra las tabs; el contenido está vacío (stubs).

- [ ] **Step 7: Commit**

```bash
git add frontend/src/pages/formacion/Onboarding.tsx frontend/src/pages/formacion/onboarding/ frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(formacion) Onboarding: shell de tabs + lista de pasos compartida + ruta + sidebar"
```

---

### Task 4: Tab "Mi ruta" (§4)

**Files:**
- Modify: `frontend/src/pages/formacion/onboarding/MiRuta.tsx`

**Interfaces:**
- Consumes: `misAsignaciones`, `estadoRuta`, `completarPaso` del service (Task 2); `ListaPasos` (Task 3).

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * MiRuta.tsx — La ruta de formación del representante (§4).
 * Descubre su asignación con `mis-asignaciones` (auto-scope por rm_id) y luego
 * consulta el estado detallado con sus bloqueos.
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Alert, CircularProgress, FormControl, InputLabel, Select, MenuItem, Snackbar,
} from '@mui/material';
import {
  misAsignaciones, estadoRuta, completarPaso,
} from '../../../services/onboarding.service';
import ListaPasos from './ListaPasos';

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

export default function MiRuta() {
  const qc = useQueryClient();
  const [sel, setSel] = useState<number | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const asignaciones = useQuery({ queryKey: ['onb-mis-asignaciones'], queryFn: misAsignaciones });

  // Al llegar la lista, abre la más reciente (el backend las ordena desc).
  useEffect(() => {
    if (sel === null && asignaciones.data && asignaciones.data.length > 0) {
      setSel(asignaciones.data[0].id);
    }
  }, [asignaciones.data, sel]);

  const ruta = useQuery({
    queryKey: ['onb-estado-ruta', sel],
    queryFn: () => estadoRuta(sel as number),
    enabled: sel !== null,
  });

  const completar = useMutation({
    mutationFn: (pasoId: number) => completarPaso(sel as number, pasoId),
    onSuccess: () => {
      setAviso({ sev: 'success', msg: 'Paso completado.' });
      qc.invalidateQueries({ queryKey: ['onb-estado-ruta', sel] });
      qc.invalidateQueries({ queryKey: ['onb-mis-asignaciones'] });
    },
    // 403 = no te toca marcarlo (§4.6); 409 = todavía está bloqueado. En ambos
    // casos el backend manda el motivo exacto: se muestra tal cual.
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo completar el paso.') }),
  });

  if (asignaciones.isLoading) return <CircularProgress />;
  if (asignaciones.isError) {
    return <Alert severity="warning">
      No se pudo cargar tu ruta. Si tu usuario no está enlazado a un representante,
      pídele a un administrador que lo enlace.
    </Alert>;
  }

  const lista = asignaciones.data || [];
  if (lista.length === 0) {
    return <Alert severity="info">Aún no tienes una ruta de formación asignada.</Alert>;
  }

  return (
    <Box>
      {lista.length > 1 && (
        <FormControl sx={{ mb: 2, minWidth: 280 }} size="small">
          <InputLabel>Ruta</InputLabel>
          <Select label="Ruta" value={sel ?? ''} onChange={(e) => setSel(Number(e.target.value))}>
            {lista.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.nombre_plantilla} — desde {a.fecha_inicio}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {ruta.isLoading && <CircularProgress />}
      {ruta.isError && <Alert severity="warning">No se pudo cargar el detalle de la ruta.</Alert>}
      {ruta.data && (
        <ListaPasos estado={ruta.data}
          onCompletar={(pasoId) => completar.mutate(pasoId)}
          completando={completar.isPending ? (completar.variables as number) : null} />
      )}

      <Snackbar open={!!aviso} autoHideDuration={8000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/formacion/onboarding/MiRuta.tsx
git commit -m "feat(formacion) Onboarding: tab Mi ruta (descubre la asignacion, muestra bloqueos)"
```

---

### Task 5: Tab "Biblioteca" (§5)

**Files:**
- Modify: `frontend/src/pages/formacion/onboarding/Biblioteca.tsx`

**Interfaces:**
- Consumes: `listarMateriales`, `subirMaterial`, `aprobarMaterial`, `confirmarLectura`, `confirmacionesDeMaterial`, `TIPOS_MATERIAL`, tipos `Material`/`TipoMaterial`/`Confirmacion` del service (Task 2); `useCicloStore`, `useAuthStore`.

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * Biblioteca.tsx — Material de formación (§5).
 * El representante solo ve lo APROBADO por Gerencia Médica: lo filtra el backend
 * según el rol (firewall PhRMA), no esta pantalla.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  MenuItem, FormControl, InputLabel, Select, CircularProgress, Snackbar,
  FormControlLabel, Switch, Link,
} from '@mui/material';
import { Add, CheckCircle, Visibility, DoneAll } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import { useAuthStore } from '../../../store/auth.store';
import {
  listarMateriales, subirMaterial, aprobarMaterial, confirmarLectura,
  confirmacionesDeMaterial, TIPOS_MATERIAL,
  type Material, type TipoMaterial,
} from '../../../services/onboarding.service';

function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

const ROLES_CONTENIDO = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
const ROLES_APRUEBA = ['ADMIN', 'GERENTE_MEDICO'];

export default function Biblioteca() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const rol = useAuthStore((s) => s.rol);
  const esRM = rol === 'REPRESENTANTE_MEDICO';
  const puedeSubir = !!rol && ROLES_CONTENIDO.includes(rol);
  const puedeAprobar = !!rol && ROLES_APRUEBA.includes(rol);

  const [productoId, setProductoId] = useState<string>('');
  const [subir, setSubir] = useState(false);
  const [verConfirmaciones, setVerConfirmaciones] = useState<Material | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const filtroProducto = productoId.trim() && !Number.isNaN(Number(productoId))
    ? Number(productoId) : undefined;

  const materiales = useQuery({
    queryKey: ['onb-biblioteca', paisCodigo, filtroProducto],
    queryFn: () => listarMateriales(paisCodigo as string, filtroProducto),
    enabled: !!paisCodigo,
  });
  const invalidar = () => qc.invalidateQueries({ queryKey: ['onb-biblioteca'] });

  const aprobar = useMutation({
    mutationFn: (id: number) => aprobarMaterial(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Material aprobado.' }),
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo aprobar.') }),
    onSettled: invalidar,
  });

  const confirmar = useMutation({
    mutationFn: (id: number) => confirmarLectura(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Lectura confirmada.' }),
    // 409 = material sin aprobar: no se puede confirmar lo que no pasó el firewall.
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo confirmar la lectura.') }),
    onSettled: invalidar,
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" mb={2}>
        <TextField size="small" label="Filtrar por producto (id)" value={productoId}
          onChange={(e) => setProductoId(e.target.value)} sx={{ width: 220 }} />
        <Box sx={{ flex: 1 }} />
        {puedeSubir && (
          <Button variant="contained" startIcon={<Add />} onClick={() => setSubir(true)}>
            Subir material
          </Button>
        )}
      </Stack>

      {materiales.isLoading ? <CircularProgress /> : materiales.isError ? (
        <Alert severity="warning">No se pudo cargar la biblioteca.</Alert>
      ) : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Título</TableCell><TableCell>Tipo</TableCell>
                <TableCell>Obligatorio</TableCell><TableCell>Aprobación</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(materiales.data || []).length === 0 ? (
                <TableRow><TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">Sin material para este filtro.</Typography>
                </TableCell></TableRow>
              ) : (materiales.data || []).map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <Link href={m.archivo_url} target="_blank" rel="noopener noreferrer">{m.titulo}</Link>
                  </TableCell>
                  <TableCell>{m.tipo}</TableCell>
                  <TableCell>
                    <Chip size="small" color={m.obligatorio ? 'primary' : 'default'}
                      label={m.obligatorio ? 'Obligatorio' : 'Opcional'} />
                  </TableCell>
                  <TableCell>
                    <Chip size="small" color={m.aprobado_por_gm ? 'success' : 'default'}
                      label={m.aprobado_por_gm ? 'Aprobado' : 'Pendiente de aprobación'} />
                  </TableCell>
                  <TableCell align="right">
                    {puedeAprobar && !m.aprobado_por_gm && (
                      <Button size="small" startIcon={<CheckCircle />}
                        disabled={aprobar.isPending && aprobar.variables === m.id}
                        onClick={() => aprobar.mutate(m.id)}>Aprobar</Button>
                    )}
                    {esRM && (
                      <Button size="small" startIcon={<DoneAll />}
                        disabled={confirmar.isPending && confirmar.variables === m.id}
                        onClick={() => confirmar.mutate(m.id)}>Confirmar lectura</Button>
                    )}
                    {puedeSubir && (
                      <Button size="small" startIcon={<Visibility />}
                        onClick={() => setVerConfirmaciones(m)}>Quién confirmó</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <DialogoMaterial abierto={subir} paisCodigo={paisCodigo}
        onClose={() => setSubir(false)}
        onCreado={() => { setSubir(false); invalidar(); setAviso({ sev: 'success', msg: 'Material subido.' }); }} />

      <DialogoConfirmaciones material={verConfirmaciones} onClose={() => setVerConfirmaciones(null)} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoMaterial({ abierto, paisCodigo, onClose, onCreado }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onCreado: () => void;
}) {
  const [titulo, setTitulo] = useState('');
  const [tipo, setTipo] = useState<TipoMaterial>('manual');
  const [url, setUrl] = useState('');
  const [producto, setProducto] = useState('');
  const [obligatorio, setObligatorio] = useState(true);   // §5.3: activado por defecto
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => subirMaterial({
      pais_codigo: paisCodigo, titulo, tipo, archivo_url: url,
      producto_id: producto.trim() && !Number.isNaN(Number(producto)) ? Number(producto) : null,
      obligatorio,
    }),
    onSuccess: () => {
      setTitulo(''); setUrl(''); setProducto(''); setTipo('manual');
      setObligatorio(true); setError(null); onCreado();
    },
    onError: (e) => setError(detalleError(e, 'No se pudo subir el material.')),
  });

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Subir material</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)}
            fullWidth required inputProps={{ maxLength: 250 }} />
          <FormControl fullWidth>
            <InputLabel>Tipo</InputLabel>
            <Select label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoMaterial)}>
              {TIPOS_MATERIAL.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField label="URL del archivo" value={url} onChange={(e) => setUrl(e.target.value)}
            fullWidth required />
          <TextField label="Producto (id, opcional)" value={producto}
            onChange={(e) => setProducto(e.target.value)} fullWidth />
          <FormControlLabel control={
            <Switch checked={obligatorio} onChange={(e) => setObligatorio(e.target.checked)} />
          } label="Lectura obligatoria" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!titulo.trim() || !url.trim() || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Subiendo…' : 'Subir'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoConfirmaciones({ material, onClose }: {
  material: Material | null; onClose: () => void;
}) {
  const datos = useQuery({
    queryKey: ['onb-confirmaciones', material?.id],
    queryFn: () => confirmacionesDeMaterial(material!.id),
    enabled: !!material,
  });

  return (
    <Dialog open={!!material} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Confirmaciones de «{material?.titulo}»</DialogTitle>
      <DialogContent>
        {datos.isLoading ? <CircularProgress /> : (datos.data || []).length === 0 ? (
          <Typography variant="body2" color="text.secondary">Nadie ha confirmado todavía.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow><TableCell>RM</TableCell><TableCell>Confirmado</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {(datos.data || []).map((c) => (
                <TableRow key={`${c.rm_id}-${c.confirmado_en}`}>
                  <TableCell>#{c.rm_id}</TableCell>
                  <TableCell>{new Date(c.confirmado_en).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK.

- [ ] **Step 3: Commit**

```bash
git add frontend/src/pages/formacion/onboarding/Biblioteca.tsx
git commit -m "feat(formacion) Onboarding: tab Biblioteca (subir, aprobar, confirmar lectura, confirmaciones)"
```

---

### Task 6: Tab "Rutas y plantillas" (§4, gestión)

**Files:**
- Modify: `frontend/src/pages/formacion/onboarding/RutasAdmin.tsx`

**Interfaces:**
- Consumes: `crearPlantilla`, `pasosDePlantilla`, `asignarRuta`, `estadoRuta` del service (Task 2); `ListaPasos` (Task 3); `useCicloStore`, `useAuthStore`.

- [ ] **Step 1: Reemplazar el stub por la implementación completa**

```tsx
/**
 * RutasAdmin.tsx — Gestión de rutas de inducción (§4).
 * Crear la ruta estándar de 10 pasos por línea, asignarla y consultar el avance.
 * «Asignar» exige RequireCapacitacion en el backend: se oculta para GERENTE_MEDICO
 * en vez de ofrecer un botón que siempre daría 403.
 */
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  CircularProgress, Snackbar,
} from '@mui/material';
import { Add, PersonAdd, Search } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import { useAuthStore } from '../../../store/auth.store';
import {
  crearPlantilla, pasosDePlantilla, asignarRuta, estadoRuta,
  type Paso, type EstadoRuta,
} from '../../../services/onboarding.service';
import ListaPasos from './ListaPasos';

function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

export default function RutasAdmin() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const rol = useAuthStore((s) => s.rol);
  const puedeAsignar = rol !== 'GERENTE_MEDICO';   // RequireCapacitacion en el backend

  const [nueva, setNueva] = useState(false);
  const [asignar, setAsignar] = useState(false);
  const [plantillaId, setPlantillaId] = useState('');
  const [pasos, setPasos] = useState<Paso[] | null>(null);
  const [asignacionId, setAsignacionId] = useState('');
  const [estado, setEstado] = useState<EstadoRuta | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const verPasos = useMutation({
    mutationFn: (id: number) => pasosDePlantilla(id),
    onSuccess: (r) => setPasos(r),
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudieron cargar los pasos.') }),
  });

  const verAsignacion = useMutation({
    mutationFn: (id: number) => estadoRuta(id),
    onSuccess: (r) => setEstado(r),
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo cargar la asignación.') }),
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" spacing={2} mb={2}>
        <Button variant="contained" startIcon={<Add />} onClick={() => setNueva(true)}>
          Nueva ruta estándar
        </Button>
        {puedeAsignar && (
          <Button variant="outlined" startIcon={<PersonAdd />} onClick={() => setAsignar(true)}>
            Asignar a un representante
          </Button>
        )}
      </Stack>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Pasos de una plantilla</Typography>
        <Stack direction="row" spacing={1} alignItems="center" mb={2}>
          <TextField size="small" label="ID de plantilla" value={plantillaId}
            onChange={(e) => setPlantillaId(e.target.value)} sx={{ width: 180 }} />
          <Button startIcon={<Search />} disabled={!plantillaId.trim() || verPasos.isPending}
            onClick={() => verPasos.mutate(Number(plantillaId))}>Consultar</Button>
          {verPasos.isPending && <CircularProgress size={20} />}
        </Stack>
        {pasos && (pasos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">Esa plantilla no tiene pasos.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell><TableCell>Título</TableCell><TableCell>Tipo</TableCell>
                <TableCell>Plazo</TableCell><TableCell>Bloqueante</TableCell><TableCell>Lo marca</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pasos.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.orden}</TableCell>
                  <TableCell>{p.titulo}</TableCell>
                  <TableCell>{p.tipo}</TableCell>
                  <TableCell>{p.plazo_sugerido ?? '—'}</TableCell>
                  <TableCell>
                    <Chip size="small" color={p.bloqueante ? 'warning' : 'default'}
                      label={p.bloqueante ? 'Sí' : 'No'} />
                  </TableCell>
                  <TableCell>{p.quien_lo_marca}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Avance de una asignación</Typography>
        <Stack direction="row" spacing={1} alignItems="center" mb={2}>
          <TextField size="small" label="ID de asignación" value={asignacionId}
            onChange={(e) => setAsignacionId(e.target.value)} sx={{ width: 180 }} />
          <Button startIcon={<Search />} disabled={!asignacionId.trim() || verAsignacion.isPending}
            onClick={() => verAsignacion.mutate(Number(asignacionId))}>Consultar</Button>
          {verAsignacion.isPending && <CircularProgress size={20} />}
        </Stack>
        {/* Solo lectura: sin onCompletar no se muestran botones de marcar. */}
        {estado && <ListaPasos estado={estado} />}
      </Paper>

      <DialogoPlantilla abierto={nueva} paisCodigo={paisCodigo} onClose={() => setNueva(false)}
        onCreada={(r) => {
          setNueva(false); setPasos(r.pasos); setPlantillaId(String(r.id));
          setAviso({ sev: 'success', msg: `Ruta «${r.nombre_plantilla}» creada con ${r.pasos.length} pasos.` });
        }} />

      <DialogoAsignar abierto={asignar} onClose={() => setAsignar(false)}
        onAsignada={(id) => {
          setAsignar(false); setAsignacionId(String(id));
          setAviso({ sev: 'success', msg: `Ruta asignada (asignación #${id}).` });
        }} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoPlantilla({ abierto, paisCodigo, onClose, onCreada }: {
  abierto: boolean; paisCodigo: string; onClose: () => void;
  onCreada: (r: { id: number; nombre_plantilla: string; pasos: Paso[] }) => void;
}) {
  const [nombre, setNombre] = useState('');
  const [lineaId, setLineaId] = useState('');
  const [duracion, setDuracion] = useState('30');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => crearPlantilla({
      pais_codigo: paisCodigo, linea_id: Number(lineaId),
      nombre_plantilla: nombre, duracion_dias: Number(duracion) || 30,
    }),
    onSuccess: (r) => { setNombre(''); setLineaId(''); setError(null); onCreada(r); },
    onError: (e) => setError(detalleError(e, 'No se pudo crear la ruta.')),
  });

  const valido = nombre.trim() && lineaId.trim() && !Number.isNaN(Number(lineaId));

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Nueva ruta estándar</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info">Se crearán automáticamente los 10 pasos estándar de la ruta.</Alert>
          <TextField label="Nombre de la ruta" value={nombre} onChange={(e) => setNombre(e.target.value)}
            fullWidth required inputProps={{ maxLength: 200 }} />
          <TextField label="ID de línea" value={lineaId} onChange={(e) => setLineaId(e.target.value)}
            fullWidth required />
          <TextField label="Duración (días)" value={duracion} onChange={(e) => setDuracion(e.target.value)}
            fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!valido || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Creando…' : 'Crear'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoAsignar({ abierto, onClose, onAsignada }: {
  abierto: boolean; onClose: () => void; onAsignada: (id: number) => void;
}) {
  const [plantilla, setPlantilla] = useState('');
  const [rm, setRm] = useState('');
  const [fecha, setFecha] = useState('');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => asignarRuta({
      plantilla_id: Number(plantilla), rm_id: Number(rm),
      fecha_inicio: fecha || null,
    }),
    onSuccess: (r) => { setPlantilla(''); setRm(''); setFecha(''); setError(null); onAsignada(r.id); },
    onError: (e) => setError(detalleError(e, 'No se pudo asignar la ruta.')),
  });

  const valido = plantilla.trim() && rm.trim()
    && !Number.isNaN(Number(plantilla)) && !Number.isNaN(Number(rm));

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Asignar ruta a un representante</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="ID de plantilla" value={plantilla}
            onChange={(e) => setPlantilla(e.target.value)} fullWidth required />
          <TextField label="ID del representante" value={rm}
            onChange={(e) => setRm(e.target.value)} fullWidth required />
          <TextField label="Fecha de inicio (opcional)" type="date" value={fecha}
            onChange={(e) => setFecha(e.target.value)} fullWidth
            InputLabelProps={{ shrink: true }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!valido || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Asignando…' : 'Asignar'}</Button>
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
git add frontend/src/pages/formacion/onboarding/RutasAdmin.tsx
git commit -m "feat(formacion) Onboarding: tab Rutas y plantillas (crear ruta estandar, asignar, avance)"
```

---

## Verificación en vivo (tras Task 6, no es un commit)

Con JWT minteado (sin escribir contraseña), por rol:

1. Capacitación: «Nueva ruta estándar» (línea válida) → aparecen los 10 pasos → «Asignar a un representante».
2. Contenido: «Subir material» obligatorio de un producto → aparece "Pendiente de aprobación".
3. RM: en Biblioteca ese material **no** debe aparecer (lo filtra el backend).
4. Gerencia Médica: «Aprobar» → el RM ya lo ve → «Confirmar lectura» funciona.
5. RM: intentar confirmar un material sin aprobar (por API) → 409 con su mensaje real.
6. RM: «Mi ruta» muestra la asignación **sin** conocer el ID; un paso bloqueado lista **todos** sus motivos, incluida la lectura pendiente.
7. RM: intentar completar un paso cuyo `quien_lo_marca` es el GD → 403 con el mensaje real del backend.
8. GERENTE_MEDICO: en «Rutas y plantillas» NO aparece el botón «Asignar».

---

## Self-Review

- **Cobertura del spec:**
  - §2 endpoint nuevo + servicio + tests → Task 1.
  - §3 contrato y tipos → Task 2.
  - §4 estructura de tabs + gates → Task 3.
  - §5 Mi ruta (descubrir asignación, bloqueos completos, completar con 403/409) → Task 4 + `ListaPasos` (Task 3).
  - §6 Biblioteca (listar, subir con obligatorio=true por defecto, aprobar, confirmar con 409, quién confirmó, filtro por producto) → Task 5.
  - §7 Rutas y plantillas (crear estándar, ver pasos, asignar oculto para GM, consultar avance en solo lectura) → Task 6.
  - §8 fuera de alcance → respetado (sin editar/eliminar, sin carga binaria, sin selectores relacionales).
  - §9 verificación → sección "Verificación en vivo" + tests de Task 1.
  - **Gap consciente:** el progreso propio de lectura (`GET /biblioteca/progreso`) no se cablea en la UI porque exige una lista de `producto_ids` que esta pantalla no puede construir de forma fiable (no hay catálogo de productos sin `linea_id`); el mismo dato aparece por paso en «Mi ruta» vía `PasoEstado.material`, que es donde tiene valor. La función `progresoLectura` queda disponible en el service para cuando se enlacen los catálogos.
- **Placeholder scan:** sin TBD/TODO; código completo en cada paso. Los stubs de Task 3 se reemplazan en Tasks 4-6 conservando `export default function X()`.
- **Consistencia de tipos:** `ListaPasos` recibe `EstadoRuta` y `onCompletar?`/`completando?` — usado con botones en Task 4 y sin ellos en Task 6; `detalleError` se define en cada archivo que lo usa (Tasks 4, 5, 6), coherente con el precedente de `CampanasRefuerzo.tsx`; `misAsignaciones()` devuelve `MiAsignacion[]` y `estadoRuta(id)` devuelve `EstadoRuta`, ambos definidos en Task 2.
