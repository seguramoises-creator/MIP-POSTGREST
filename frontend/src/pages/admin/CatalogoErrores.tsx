/**
 * CatalogoErrores.tsx — Matriz de errores del sistema (mantenible por ADMIN).
 * Tab dentro de Administración, después de "Servidor de Correo (SMTP)".
 * Documenta cada error con su descripción, causa y solución. CRUD contra /admin/catalogo-errores.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, Button, Chip, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  Alert, CircularProgress, Stack, IconButton, Tooltip, InputAdornment, MenuItem, Switch,
  FormControlLabel,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import DeleteIcon from '@mui/icons-material/DeleteOutline';
import SearchIcon from '@mui/icons-material/Search';
import ReportProblemIcon from '@mui/icons-material/ReportProblem';
import { api } from '../../services/api';

interface ErrorCat {
  id: number; codigo: string; titulo: string; descripcion?: string | null; causa?: string | null;
  solucion?: string | null; categoria?: string | null; http_status?: number | null; activo: boolean;
}

const CATEGORIAS = ['Validación', 'Permisos', 'Datos', 'Sistema', 'Correo', 'Otro'];
const CAT_COLOR: Record<string, 'error' | 'warning' | 'info' | 'success' | 'default' | 'secondary'> = {
  Validación: 'warning', Permisos: 'secondary', Datos: 'info', Sistema: 'error', Correo: 'success', Otro: 'default',
};

export default function CatalogoErrores() {
  const qc = useQueryClient();
  const [q, setQ] = useState('');
  const [open, setOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<Partial<ErrorCat>>({ activo: true });
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['catalogo-errores'],
    queryFn: () => api.get<ErrorCat[]>('/admin/catalogo-errores').then((r) => r.data),
    retry: 1,
  });
  const errores = Array.isArray(data) ? data : [];

  const filtrados = useMemo(() => {
    const t = q.trim().toLowerCase();
    if (!t) return errores;
    return errores.filter((e) =>
      `${e.codigo} ${e.titulo} ${e.categoria ?? ''} ${e.descripcion ?? ''} ${e.http_status ?? ''}`.toLowerCase().includes(t));
  }, [errores, q]);

  const flash = (tipo: 'success' | 'error', texto: string) => { setMsg({ tipo, texto }); setTimeout(() => setMsg(null), 4000); };
  const errMsg = (e: any) => e?.response?.data?.detail || 'No se pudo guardar.';

  const abrirNuevo = () => { setEditId(null); setForm({ activo: true, categoria: 'Sistema' }); setOpen(true); };
  const abrirEditar = (e: ErrorCat) => { setEditId(e.id); setForm({ ...e }); setOpen(true); };

  const guardarMut = useMutation({
    mutationFn: () => editId
      ? api.put(`/admin/catalogo-errores/${editId}`, form)
      : api.post('/admin/catalogo-errores', form),
    onSuccess: () => { setOpen(false); qc.invalidateQueries({ queryKey: ['catalogo-errores'] }); flash('success', 'Guardado.'); },
    onError: (e: any) => flash('error', errMsg(e)),
  });
  const borrarMut = useMutation({
    mutationFn: (id: number) => api.delete(`/admin/catalogo-errores/${id}`),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['catalogo-errores'] }); flash('success', 'Eliminado.'); },
    onError: (e: any) => flash('error', errMsg(e)),
  });

  const set = (k: keyof ErrorCat, v: unknown) => setForm((f) => ({ ...f, [k]: v }));
  const puedeGuardar = (form.codigo || '').trim().length >= 2 && (form.titulo || '').trim().length >= 2;

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mb: 0.5 }}>
        <ReportProblemIcon color="warning" />
        <Typography variant="h6" fontWeight={700}>Matriz de Errores</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Catálogo de errores del sistema con su descripción, causa y solución. Manténlo aquí para que
        el equipo entienda cada error que aparece.
      </Typography>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Stack direction="row" spacing={1.5} alignItems="center" sx={{ mb: 2 }} flexWrap="wrap">
        <TextField size="small" placeholder="Buscar por código, título, categoría…" value={q}
          onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 280, flex: '1 1 280px' }}
          InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }} />
        <Button variant="contained" startIcon={<AddIcon />} onClick={abrirNuevo}>Nuevo error</Button>
        <Typography variant="caption" color="text.secondary">{filtrados.length} de {errores.length}</Typography>
      </Stack>

      {isLoading && <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}><CircularProgress /></Box>}
      {isError && <Alert severity="error" action={<Button size="small" onClick={() => refetch()}>Reintentar</Button>}>No se pudo cargar el catálogo.</Alert>}

      {!isLoading && !isError && (
        <TableContainer component={Paper} variant="outlined" sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: 'action.hover' }}>
              <TableRow>
                {['Código', 'Título', 'Categoría', 'HTTP', 'Descripción', 'Estado', ''].map((h) => (
                  <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {filtrados.map((e) => (
                <TableRow key={e.id} hover>
                  <TableCell sx={{ fontFamily: 'ui-monospace, Menlo, Consolas, monospace', fontWeight: 700, whiteSpace: 'nowrap' }}>{e.codigo}</TableCell>
                  <TableCell sx={{ fontWeight: 600 }}>{e.titulo}</TableCell>
                  <TableCell>{e.categoria && <Chip size="small" label={e.categoria} color={CAT_COLOR[e.categoria] ?? 'default'} variant="outlined" />}</TableCell>
                  <TableCell>{e.http_status ?? '—'}</TableCell>
                  <TableCell sx={{ maxWidth: 360, color: 'text.secondary', fontSize: 13 }}>{e.descripcion}</TableCell>
                  <TableCell>
                    <Chip size="small" label={e.activo ? 'Activo' : 'Inactivo'} color={e.activo ? 'success' : 'default'}
                      variant={e.activo ? 'filled' : 'outlined'} />
                  </TableCell>
                  <TableCell>
                    <Stack direction="row" spacing={0.5}>
                      <Tooltip title="Editar"><IconButton size="small" color="primary" onClick={() => abrirEditar(e)}><EditIcon fontSize="small" /></IconButton></Tooltip>
                      <Tooltip title="Eliminar"><IconButton size="small" color="error"
                        onClick={() => { if (confirm(`¿Eliminar el error "${e.codigo}"?`)) borrarMut.mutate(e.id); }}><DeleteIcon fontSize="small" /></IconButton></Tooltip>
                    </Stack>
                  </TableCell>
                </TableRow>
              ))}
              {filtrados.length === 0 && (
                <TableRow><TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>Sin errores en el catálogo.</TableCell></TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      )}

      {/* Dialogo crear/editar */}
      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editId ? 'Editar error' : 'Nuevo error'}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <Stack direction="row" spacing={2}>
              <TextField label="Código" size="small" value={form.codigo ?? ''} disabled={!!editId}
                onChange={(e) => set('codigo', e.target.value.toUpperCase())} sx={{ flex: 1 }}
                helperText={editId ? 'El código no se cambia' : 'Ej. MED-DUP-DURO'} />
              <TextField label="HTTP" size="small" type="number" value={form.http_status ?? ''}
                onChange={(e) => set('http_status', e.target.value === '' ? null : Number(e.target.value))} sx={{ width: 110 }} />
            </Stack>
            <TextField label="Título" size="small" value={form.titulo ?? ''} onChange={(e) => set('titulo', e.target.value)} fullWidth />
            <TextField select label="Categoría" size="small" value={form.categoria ?? ''} onChange={(e) => set('categoria', e.target.value)} fullWidth>
              {CATEGORIAS.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </TextField>
            <TextField label="Descripción" size="small" value={form.descripcion ?? ''} onChange={(e) => set('descripcion', e.target.value)} fullWidth multiline minRows={2} />
            <TextField label="Causa probable" size="small" value={form.causa ?? ''} onChange={(e) => set('causa', e.target.value)} fullWidth multiline minRows={2} />
            <TextField label="Solución" size="small" value={form.solucion ?? ''} onChange={(e) => set('solucion', e.target.value)} fullWidth multiline minRows={2} />
            <FormControlLabel control={<Switch checked={form.activo ?? true} onChange={(e) => set('activo', e.target.checked)} />} label="Activo" />
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" disabled={!puedeGuardar || guardarMut.isPending} onClick={() => guardarMut.mutate()}>
            {guardarMut.isPending ? <CircularProgress size={18} /> : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
