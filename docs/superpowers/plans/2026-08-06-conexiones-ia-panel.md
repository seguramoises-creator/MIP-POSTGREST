# Panel de Conexiones de IA — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Dar al ADMIN una pantalla para administrar las conexiones a proveedores de IA (listar/crear/editar/probar/activar/eliminar), con credenciales siempre enmascaradas.

**Architecture:** Frontend-only sobre un backend ya existente (`/ia/conexiones`, 7 endpoints, solo ADMIN). Tres piezas: (1) service axios tipado; (2) página con dos bloques por capacidad (texto/voz), acciones por fila y snackbar de feedback; (3) diálogo crear/editar con manejo cuidadoso de credenciales enmascaradas. Ruta lazy `/conexiones-ia` + ítem de Sidebar, ambos ADMIN.

**Tech Stack:** React 18 + TypeScript, MUI v6, TanStack Query v5, axios (`import { api } from './api'`), react-router-dom v6 (`lazyWithReload`).

## Global Constraints

- Cero cambios de backend/modelo/migración. El contrato de §2 del spec es fijo.
- Credenciales: el backend SIEMPRE las devuelve enmascaradas y el `PUT` ignora campos nulos. En **editar**, un campo de credencial dejado vacío se OMITE del cuerpo del PUT (nunca se envía la máscara).
- `proveedor_tipo` se puebla desde `GET /ia/conexiones/proveedores`, nunca hardcodeado.
- Valores permitidos: `capacidad ∈ {texto, voz}`, `metodo_auth ∈ {api_key, usuario_password}`.
- Todo bajo `allowedRoles={['ADMIN']}` (ruta) y `roles: ['ADMIN']` (sidebar).
- Estilo del proyecto: MUI `sx`, React Query, español en el copy. Cliente `api` con `.then(r => r.data)`. Patrón de referencia para página con tabla+Dialog+mutations: `frontend/src/pages/admin/CategorizacionAdmin.tsx`.
- No agregar tests automatizados (presentación sobre backend cubierto). Verificación = build + smoke.

---

### Task 1: Service `iaConexiones.service.ts` (tipos + 7 funciones)

**Files:**
- Create: `frontend/src/services/iaConexiones.service.ts`

**Interfaces:**
- Produce (para Tasks 2 y 3):
  - tipos `Conexion`, `ConexionEntrada`, `ConexionCambio`, `ProveedoresIA`, `ResultadoPrueba`
  - `listarConexionesIA(): Promise<{ conexiones: Conexion[]; cifrado_configurado: boolean }>`
  - `proveedoresIA(): Promise<ProveedoresIA>`
  - `crearConexionIA(body: ConexionEntrada): Promise<Conexion>`
  - `actualizarConexionIA(id: number, body: ConexionCambio): Promise<Conexion>`
  - `eliminarConexionIA(id: number): Promise<void>`
  - `probarConexionIA(id: number): Promise<ResultadoPrueba>`
  - `activarConexionIA(id: number): Promise<Conexion>`

- [ ] **Step 1: Crear el archivo con tipos y funciones**

```ts
/**
 * iaConexiones.service.ts — Panel de Conexiones de IA (§20.4).
 * Rutas exactas del router backend `/ia/conexiones` (solo ADMIN).
 * Las credenciales SIEMPRE llegan enmascaradas; el backend nunca las expone en claro.
 */
import { api } from './api';

export type CapacidadIA = 'texto' | 'voz';
export type MetodoAuthIA = 'api_key' | 'usuario_password';

export interface Conexion {
  id: number;
  nombre: string;
  capacidad: CapacidadIA;
  proveedor_tipo: string;
  endpoint_url: string | null;
  metodo_auth: string;
  modelo: string | null;
  activa: boolean;
  verificada: boolean;
  ultima_verificacion: string | null;
  ultimo_error: string | null;
  credencial_1: string | null; // enmascarada
  credencial_2: string | null; // enmascarada
}

export interface ConexionEntrada {
  nombre: string;
  capacidad: CapacidadIA;
  proveedor_tipo: string;
  endpoint_url?: string | null;
  metodo_auth: MetodoAuthIA;
  credencial_1?: string | null;
  credencial_2?: string | null;
  modelo?: string | null;
}

// Editar: todos opcionales; el backend solo aplica los presentes.
export type ConexionCambio = Partial<ConexionEntrada>;

export interface ProveedoresIA { texto: string[]; voz: string[]; }
export interface ResultadoPrueba { ok: boolean; detalle: string; }

export const listarConexionesIA = () =>
  api.get<{ conexiones: Conexion[]; cifrado_configurado: boolean }>('/ia/conexiones')
    .then((r) => r.data);

export const proveedoresIA = () =>
  api.get<ProveedoresIA>('/ia/conexiones/proveedores').then((r) => r.data);

export const crearConexionIA = (body: ConexionEntrada) =>
  api.post<Conexion>('/ia/conexiones', body).then((r) => r.data);

export const actualizarConexionIA = (id: number, body: ConexionCambio) =>
  api.put<Conexion>(`/ia/conexiones/${id}`, body).then((r) => r.data);

export const eliminarConexionIA = (id: number) =>
  api.delete(`/ia/conexiones/${id}`).then(() => undefined);

export const probarConexionIA = (id: number) =>
  api.post<ResultadoPrueba>(`/ia/conexiones/${id}/probar`).then((r) => r.data);

export const activarConexionIA = (id: number) =>
  api.post<Conexion>(`/ia/conexiones/${id}/activar`).then((r) => r.data);
```

- [ ] **Step 2: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK (el service aún no se consume; TypeScript no falla por un módulo exportado sin importar).

- [ ] **Step 3: Commit**

```bash
git add frontend/src/services/iaConexiones.service.ts
git commit -m "feat(ia) Conexiones IA: capa de servicio frontend (tipos + 7 endpoints)"
```

---

### Task 2: Página `ConexionesIA.tsx` (lista, acciones, ruta, sidebar) — sin el diálogo

Renderiza la lista en dos bloques por capacidad, con acciones Probar/Activar/Eliminar y un Snackbar. El botón "Nueva/Editar" abre un diálogo que se implementa en Task 3; aquí se deja un placeholder de estado (`dialogo`) y los botones que lo setean, pero el componente de diálogo llega en Task 3. Registra ruta y sidebar.

**Files:**
- Create: `frontend/src/pages/sistema/ConexionesIA.tsx`
- Modify: `frontend/src/App.tsx` (import lazy + `<Route>`)
- Modify: `frontend/src/components/layout/Sidebar.tsx` (ítem en el grupo admin)

**Interfaces:**
- Consumes: todo el service de Task 1.
- Produce (para Task 3): en `ConexionesIA.tsx`, un estado `dialogo` de tipo
  `{ modo: 'crear' } | { modo: 'editar'; conexion: Conexion } | null` y su setter
  `setDialogo`, más una función `cerrarYRefetch()` que cierra el diálogo e invalida
  la query `['ia-conexiones']`. Task 3 consume estos para montar `<DialogoConexion>`.

- [ ] **Step 1: Crear la página con lista + acciones + snackbar**

Crea `frontend/src/pages/sistema/ConexionesIA.tsx`. Sigue el patrón de
`CategorizacionAdmin.tsx` para tabla + mutations. Estructura completa:

```tsx
/**
 * ConexionesIA.tsx — Panel de Conexiones de IA (§20.4), solo ADMIN.
 * Administra proveedores de IA de texto y voz sin tocar código: listar, crear,
 * editar, probar, activar, eliminar. Credenciales siempre enmascaradas.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Paper, Table, TableHead, TableBody, TableRow, TableCell,
  Button, Chip, Stack, Alert, Snackbar, Tooltip, IconButton, CircularProgress,
} from '@mui/material';
import { Add, Science, PlayArrow, Edit, Delete, Warning } from '@mui/icons-material';
import {
  listarConexionesIA, probarConexionIA, activarConexionIA, eliminarConexionIA,
  type Conexion, type CapacidadIA,
} from '../../services/iaConexiones.service';

type Dialogo = { modo: 'crear' } | { modo: 'editar'; conexion: Conexion } | null;

const CAPS: { key: CapacidadIA; titulo: string }[] = [
  { key: 'texto', titulo: 'Texto' }, { key: 'voz', titulo: 'Voz' },
];

export default function ConexionesIA() {
  const qc = useQueryClient();
  const [dialogo, setDialogo] = useState<Dialogo>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const lista = useQuery({ queryKey: ['ia-conexiones'], queryFn: listarConexionesIA });
  const cifradoOk = lista.data?.cifrado_configurado ?? true;
  const invalidar = () => qc.invalidateQueries({ queryKey: ['ia-conexiones'] });
  const cerrarYRefetch = () => { setDialogo(null); invalidar(); };

  const probar = useMutation({
    mutationFn: (id: number) => probarConexionIA(id),
    onSuccess: (r) => setAviso({ sev: r.ok ? 'success' : 'warning', msg: r.detalle || (r.ok ? 'Conexión válida.' : 'La prueba falló.') }),
    onError: () => setAviso({ sev: 'error', msg: 'No se pudo probar la conexión.' }),
    onSettled: invalidar,
  });
  const activar = useMutation({
    mutationFn: (id: number) => activarConexionIA(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Conexión activada.' }),
    onError: (e: any) => setAviso({ sev: 'warning', msg: e?.response?.data?.detail || 'No se pudo activar. Prueba la conexión primero.' }),
    onSettled: invalidar,
  });
  const eliminar = useMutation({
    mutationFn: (id: number) => eliminarConexionIA(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Conexión eliminada.' }),
    onError: () => setAviso({ sev: 'error', msg: 'No se pudo eliminar.' }),
    onSettled: invalidar,
  });

  const onEliminar = (c: Conexion) => {
    if (window.confirm(`¿Eliminar la conexión «${c.nombre}»?`)) eliminar.mutate(c.id);
  };

  const filasDe = (cap: CapacidadIA) => (lista.data?.conexiones || []).filter((c) => c.capacidad === cap);

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" mb={2}>
        <Typography variant="h5" fontWeight={800} sx={{ flex: 1 }}>Conexiones de IA</Typography>
        <Button variant="contained" startIcon={<Add />} disabled={!cifradoOk}
          onClick={() => setDialogo({ modo: 'crear' })}>Nueva conexión</Button>
      </Stack>

      {!cifradoOk && (
        <Alert severity="error" sx={{ mb: 2 }}>
          Falta configurar la llave de cifrado; no se pueden crear ni editar conexiones.
        </Alert>
      )}

      {lista.isLoading ? <CircularProgress /> : CAPS.map(({ key, titulo }) => (
        <Paper key={key} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3, p: 2 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>{titulo}</Typography>
          {filasDe(key).length === 0 ? (
            <Typography color="text.secondary" variant="body2">Sin conexiones de {titulo.toLowerCase()}.</Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Nombre</TableCell><TableCell>Proveedor</TableCell>
                  <TableCell>Modelo</TableCell><TableCell>Método</TableCell>
                  <TableCell>Estado</TableCell><TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filasDe(key).map((c) => (
                  <TableRow key={c.id}>
                    <TableCell>{c.nombre}</TableCell>
                    <TableCell>{c.proveedor_tipo}</TableCell>
                    <TableCell>{c.modelo || '—'}</TableCell>
                    <TableCell>{c.metodo_auth}</TableCell>
                    <TableCell>
                      <Stack direction="row" spacing={0.5} alignItems="center">
                        {c.activa && <Chip size="small" color="success" label="Activa" />}
                        <Tooltip title={c.ultima_verificacion ? `Última: ${new Date(c.ultima_verificacion).toLocaleString()}` : 'Nunca probada'}>
                          <Chip size="small" color={c.verificada ? 'primary' : 'default'}
                            label={c.verificada ? 'Verificada' : 'Sin verificar'} />
                        </Tooltip>
                        {c.ultimo_error && (
                          <Tooltip title={c.ultimo_error}><Warning color="warning" fontSize="small" /></Tooltip>
                        )}
                      </Stack>
                    </TableCell>
                    <TableCell align="right">
                      <Tooltip title="Probar"><span>
                        <IconButton size="small" onClick={() => probar.mutate(c.id)} disabled={probar.isPending}><Science fontSize="small" /></IconButton>
                      </span></Tooltip>
                      <Tooltip title={c.verificada ? 'Activar' : 'Prueba la conexión antes de activarla'}><span>
                        <IconButton size="small" color="primary" onClick={() => activar.mutate(c.id)} disabled={!c.verificada || c.activa || activar.isPending}><PlayArrow fontSize="small" /></IconButton>
                      </span></Tooltip>
                      <Tooltip title="Editar"><span>
                        <IconButton size="small" onClick={() => setDialogo({ modo: 'editar', conexion: c })} disabled={!cifradoOk}><Edit fontSize="small" /></IconButton>
                      </span></Tooltip>
                      <Tooltip title="Eliminar"><span>
                        <IconButton size="small" color="error" onClick={() => onEliminar(c)}><Delete fontSize="small" /></IconButton>
                      </span></Tooltip>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
      ))}

      {/* Task 3 monta aquí <DialogoConexion dialogo={dialogo} onClose={() => setDialogo(null)} onGuardado={cerrarYRefetch} setAviso={setAviso} /> */}

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}
```

- [ ] **Step 2: Registrar la ruta lazy en `App.tsx`**

Junto a los otros `lazyWithReload` (p. ej. cerca de las páginas de Simulacro/admin), añadir:

```tsx
const ConexionesIA = lazyWithReload(() => import('./pages/sistema/ConexionesIA'));
```

Y dentro del árbol de `<Route>` protegidas, añadir:

```tsx
<Route path="conexiones-ia" element={<ProtectedRoute allowedRoles={['ADMIN']}><ConexionesIA /></ProtectedRoute>} />
```

(Usa exactamente el mismo componente `ProtectedRoute` y el patrón `path` sin barra inicial que las rutas vecinas.)

- [ ] **Step 3: Agregar el ítem al Sidebar**

En `frontend/src/components/layout/Sidebar.tsx`, en el grupo administrativo que contiene los ítems `/admin` y `/usuarios`, agregar como nuevo ítem del array `items`:

```tsx
{ label: 'Conexiones de IA', path: '/conexiones-ia', icon: <Hub />, roles: ['ADMIN'] },
```

Asegúrate de que `Hub` esté importado desde `@mui/icons-material` (agrégalo al import existente de iconos si falta).

- [ ] **Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK. La página lista, prueba, activa y elimina; el botón "Nueva/Editar" cambia el estado `dialogo` pero aún no abre nada (el diálogo llega en Task 3). El comentario marcador NO debe romper el build.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/sistema/ConexionesIA.tsx frontend/src/App.tsx frontend/src/components/layout/Sidebar.tsx
git commit -m "feat(ia) Conexiones IA: pagina con lista/probar/activar/eliminar + ruta + sidebar (ADMIN)"
```

---

### Task 3: Diálogo crear/editar `DialogoConexion`

Componente de diálogo con los 9 campos, montado dentro de `ConexionesIA.tsx`. Maneja crear (POST) y editar (PUT parcial con omisión de credenciales sin tocar). Puebla `proveedor_tipo` desde `GET /proveedores` según la capacidad.

**Files:**
- Modify: `frontend/src/pages/sistema/ConexionesIA.tsx`

**Interfaces:**
- Consumes: `dialogo`/`setDialogo`/`cerrarYRefetch`/`setAviso` de Task 2;
  `crearConexionIA`, `actualizarConexionIA`, `proveedoresIA` del service.

- [ ] **Step 1: Añadir imports del diálogo y del service**

Ampliar los imports de `@mui/material` con: `Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, FormControl, InputLabel, Select`.
Ampliar el import del service con: `crearConexionIA, actualizarConexionIA, proveedoresIA, type ConexionEntrada, type ConexionCambio, type MetodoAuthIA`.
Añadir `import { useEffect } from 'react';` (junto a `useState`).

- [ ] **Step 2: Implementar el componente `DialogoConexion` al final del archivo**

```tsx
function DialogoConexion({ dialogo, onClose, onGuardado, setAviso }: {
  dialogo: { modo: 'crear' } | { modo: 'editar'; conexion: Conexion } | null;
  onClose: () => void;
  onGuardado: () => void;
  setAviso: (a: { sev: 'success' | 'warning' | 'error'; msg: string }) => void;
}) {
  const editando = dialogo?.modo === 'editar' ? dialogo.conexion : null;
  const [capacidad, setCapacidad] = useState<CapacidadIA>('texto');
  const [nombre, setNombre] = useState('');
  const [proveedor, setProveedor] = useState('');
  const [metodo, setMetodo] = useState<MetodoAuthIA>('api_key');
  const [endpoint, setEndpoint] = useState('');
  const [modelo, setModelo] = useState('');
  const [cred1, setCred1] = useState('');
  const [cred2, setCred2] = useState('');
  const [errorForm, setErrorForm] = useState<string | null>(null);

  const proveedores = useQuery({ queryKey: ['ia-proveedores'], queryFn: proveedoresIA, enabled: !!dialogo });

  // Precargar al abrir.
  useEffect(() => {
    if (!dialogo) return;
    setErrorForm(null); setCred1(''); setCred2('');
    if (editando) {
      setCapacidad(editando.capacidad); setNombre(editando.nombre);
      setProveedor(editando.proveedor_tipo); setMetodo(editando.metodo_auth as MetodoAuthIA);
      setEndpoint(editando.endpoint_url || ''); setModelo(editando.modelo || '');
    } else {
      setCapacidad('texto'); setNombre(''); setProveedor('');
      setMetodo('api_key'); setEndpoint(''); setModelo('');
    }
  }, [dialogo]); // eslint-disable-line react-hooks/exhaustive-deps

  const opcionesProveedor = proveedores.data ? proveedores.data[capacidad] : [];

  const guardar = useMutation({
    mutationFn: async () => {
      if (editando) {
        const body: ConexionCambio = {
          nombre, proveedor_tipo: proveedor, metodo_auth: metodo,
          endpoint_url: endpoint || null, modelo: modelo || null,
        };
        // Credenciales: solo enviar si el usuario escribió algo (no pisar la real).
        if (cred1) body.credencial_1 = cred1;
        if (cred2) body.credencial_2 = cred2;
        return actualizarConexionIA(editando.id, body);
      }
      const body: ConexionEntrada = {
        nombre, capacidad, proveedor_tipo: proveedor, metodo_auth: metodo,
        endpoint_url: endpoint || null, modelo: modelo || null,
        credencial_1: cred1 || null, credencial_2: cred2 || null,
      };
      return crearConexionIA(body);
    },
    onSuccess: () => { setAviso({ sev: 'success', msg: editando ? 'Conexión actualizada.' : 'Conexión creada.' }); onGuardado(); },
    onError: (e: any) => {
      const status = e?.response?.status;
      const detalle = e?.response?.data?.detail;
      if (status === 503) { setAviso({ sev: 'error', msg: detalle || 'Falta la llave de cifrado.' }); onClose(); return; }
      setErrorForm(detalle || 'No se pudo guardar la conexión.');
    },
  });

  const puedeGuardar = nombre.trim() && proveedor;

  return (
    <Dialog open={!!dialogo} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{editando ? 'Editar conexión' : 'Nueva conexión'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorForm && <Alert severity="error">{errorForm}</Alert>}
          <TextField label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} fullWidth required />
          <FormControl fullWidth disabled={!!editando}>
            <InputLabel>Capacidad</InputLabel>
            <Select label="Capacidad" value={capacidad} onChange={(e) => { setCapacidad(e.target.value as CapacidadIA); setProveedor(''); }}>
              <MenuItem value="texto">Texto</MenuItem>
              <MenuItem value="voz">Voz</MenuItem>
            </Select>
          </FormControl>
          <FormControl fullWidth required>
            <InputLabel>Proveedor</InputLabel>
            <Select label="Proveedor" value={proveedor} onChange={(e) => setProveedor(e.target.value)}>
              {opcionesProveedor.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel>Método de autenticación</InputLabel>
            <Select label="Método de autenticación" value={metodo} onChange={(e) => setMetodo(e.target.value as MetodoAuthIA)}>
              <MenuItem value="api_key">api_key</MenuItem>
              <MenuItem value="usuario_password">usuario_password</MenuItem>
            </Select>
          </FormControl>
          <TextField label="Endpoint URL (opcional)" value={endpoint} onChange={(e) => setEndpoint(e.target.value)} fullWidth />
          <TextField label="Modelo (opcional)" value={modelo} onChange={(e) => setModelo(e.target.value)} fullWidth />
          <TextField label={metodo === 'usuario_password' ? 'Usuario' : 'API Key'} type="password" value={cred1}
            onChange={(e) => setCred1(e.target.value)} fullWidth
            placeholder={editando?.credencial_1 || ''}
            helperText={editando ? 'Déjalo en blanco para conservar la actual.' : ''} />
          <TextField label={metodo === 'usuario_password' ? 'Contraseña' : 'Credencial secundaria (opcional)'} type="password" value={cred2}
            onChange={(e) => setCred2(e.target.value)} fullWidth
            placeholder={editando?.credencial_2 || ''}
            helperText={editando ? 'Déjalo en blanco para conservar la actual.' : ''} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!puedeGuardar || guardar.isPending} onClick={() => guardar.mutate()}>
          {guardar.isPending ? 'Guardando…' : 'Guardar'}
        </Button>
      </DialogActions>
    </Dialog>
  );
}
```

- [ ] **Step 3: Montar el diálogo en `ConexionesIA` reemplazando el comentario marcador**

Sustituir la línea comentario `{/* Task 3 monta aquí ... */}` por:

```tsx
      <DialogoConexion dialogo={dialogo} onClose={() => setDialogo(null)}
        onGuardado={cerrarYRefetch} setAviso={setAviso} />
```

- [ ] **Step 4: Verificar que compila**

Run: `cd frontend && npm run build`
Expected: build OK, sin errores de TypeScript. El flujo completo crear/editar queda operable.

- [ ] **Step 5: Commit**

```bash
git add frontend/src/pages/sistema/ConexionesIA.tsx
git commit -m "feat(ia) Conexiones IA: dialogo crear/editar (credenciales enmascaradas, proveedor por capacidad)"
```

---

## Verificación en vivo (tras Task 3, no es un commit)

Con JWT de ADMIN (minteado, sin escribir contraseña):

1. Entrar a `/conexiones-ia`. Si falta la llave de cifrado → banner rojo y botones "Nueva/Editar" deshabilitados.
2. Crear una conexión de texto de prueba → aparece en el bloque Texto, "Sin verificar".
3. **Probar** → snackbar con el `detalle` real (ok o error del proveedor); el chip pasa a "Verificada" si `ok`.
4. **Activar** una verificada → "Activa"; el botón Activar de una no verificada está deshabilitado.
5. **Editar** dejando las credenciales en blanco → guardar; la máscara conserva los mismos últimos 4 dígitos (no se pisó).
6. **Eliminar** con confirmación.
7. RBAC: un rol no-ADMIN no ve el ítem del Sidebar ni puede entrar a `/conexiones-ia`.

---

## Self-Review

- **Cobertura del spec:**
  - §2 contrato (7 endpoints, tipos) → Task 1.
  - §3 ubicación/ruta/sidebar/service → Task 1 + Task 2 Steps 2-3.
  - §4.1 banner de llave → Task 2 Step 1 (`!cifradoOk`).
  - §4.2 dos bloques por capacidad + chips + tooltips → Task 2 Step 1.
  - §4.3 acciones probar/activar(deshab. si no verificada)/editar/eliminar(confirm) → Task 2 Step 1.
  - §4.4 diálogo 9 campos, proveedor por capacidad, capacidad solo-lectura al editar, omisión de credencial en blanco → Task 3.
  - §4.5 React Query queries + mutations + snackbar → Tasks 2 y 3.
  - §6 verificación → sección "Verificación en vivo".
- **Placeholder scan:** sin TBD/TODO; código completo en cada paso. El comentario marcador de Task 2 Step 1 se elimina en Task 3 Step 3.
- **Consistencia de tipos:** `Dialogo`/`dialogo` mismo shape en Task 2 y Task 3; `setAviso` firma idéntica; `ConexionEntrada`/`ConexionCambio` de Task 1 usados en Task 3; `activarConexionIA` deshabilitado por `!c.verificada` coherente con el 409 del backend.
