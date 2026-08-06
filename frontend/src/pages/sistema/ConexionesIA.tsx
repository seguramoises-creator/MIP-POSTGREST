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
