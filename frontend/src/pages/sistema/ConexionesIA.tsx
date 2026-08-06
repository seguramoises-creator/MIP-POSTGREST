/**
 * ConexionesIA.tsx — Panel de Conexiones de IA (§20.4), solo ADMIN.
 * Administra proveedores de IA de texto y voz sin tocar código: listar, crear,
 * editar, probar, activar, eliminar. Credenciales siempre enmascaradas.
 */
import { useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Paper, Table, TableHead, TableBody, TableRow, TableCell,
  Button, Chip, Stack, Alert, Snackbar, Tooltip, IconButton, CircularProgress,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem, FormControl, InputLabel, Select,
} from '@mui/material';
import { Add, Science, PlayArrow, Edit, Delete, Warning } from '@mui/icons-material';
import {
  listarConexionesIA, probarConexionIA, activarConexionIA, eliminarConexionIA,
  crearConexionIA, actualizarConexionIA, proveedoresIA,
  type Conexion, type CapacidadIA, type ConexionEntrada, type ConexionCambio, type MetodoAuthIA,
} from '../../services/iaConexiones.service';

type Dialogo = { modo: 'crear' } | { modo: 'editar'; conexion: Conexion } | null;

const CAPS: { key: CapacidadIA; titulo: string }[] = [
  { key: 'texto', titulo: 'Texto' }, { key: 'voz', titulo: 'Voz' },
];

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o detail string.
// Sin esto, un detail en array se pasaría como hijo de React y tumbaría la pantalla.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

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
    onError: (e: any) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo activar. Prueba la conexión primero.') }),
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

      <DialogoConexion dialogo={dialogo} onClose={() => setDialogo(null)}
        onGuardado={cerrarYRefetch} setAviso={setAviso} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoConexion({ dialogo, onClose, onGuardado, setAviso }: {
  dialogo: { modo: 'crear' } | { modo: 'editar'; conexion: Conexion } | null;
  onClose: () => void;
  onGuardado: () => void;
  setAviso: (a: { sev: 'success' | 'warning' | 'error'; msg: string }) => void;
}) {
  const qc = useQueryClient();
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
        // Solo incluir los campos realmente modificados: el backend solo desactiva
        // la conexión (verificada=False, activa=False) si "cambios" no queda vacío,
        // y para proveedor_tipo/metodo_auth basta con que la CLAVE esté presente
        // (no compara valores) — así que nunca deben ir si no cambiaron.
        const body: ConexionCambio = {};
        if (nombre !== editando.nombre) body.nombre = nombre;
        if (proveedor !== editando.proveedor_tipo) body.proveedor_tipo = proveedor;
        if (metodo !== editando.metodo_auth) body.metodo_auth = metodo;
        if (endpoint !== (editando.endpoint_url || '')) body.endpoint_url = endpoint;
        if (modelo !== (editando.modelo || '')) body.modelo = modelo;
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
      if (status === 503) {
        setAviso({ sev: 'error', msg: detalleError(e, 'Falta la llave de cifrado.') });
        qc.invalidateQueries({ queryKey: ['ia-conexiones'] });
        onClose();
        return;
      }
      setErrorForm(detalleError(e, 'No se pudo guardar la conexión.'));
    },
  });

  const puedeGuardar = nombre.trim() && proveedor;

  return (
    <Dialog open={!!dialogo} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>{editando ? 'Editar conexión' : 'Nueva conexión'}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {errorForm && <Alert severity="error">{errorForm}</Alert>}
          {editando && (editando.activa || editando.verificada) && (
            <Alert severity="info">
              Al guardar un cambio, la conexión quedará sin verificar y desactivada. Deberás probarla y activarla de nuevo.
            </Alert>
          )}
          <TextField label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)} fullWidth required
            inputProps={{ maxLength: 100 }} />
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
