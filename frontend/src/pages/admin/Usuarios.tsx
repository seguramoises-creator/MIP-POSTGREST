/**
 * Usuarios.tsx — Gestión de Usuarios del Sistema
 * Ruta: /usuarios  |  Solo ADMIN
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Button, Chip, Dialog,
  DialogTitle, DialogContent, DialogActions, TextField, Alert,
  CircularProgress, MenuItem, Select, FormControl, InputLabel,
  IconButton, Tooltip, Stack,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import EditIcon from '@mui/icons-material/Edit';
import { api } from '../../services/api';

const ROLES = [
  'ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD',
  'GERENTE_DISTRITO', 'GERENTE_MARCA', 'REPRESENTANTE_MEDICO', 'CONSULTA',
];

const ROL_COLORS: Record<string, 'error' | 'warning' | 'info' | 'success' | 'default'> = {
  ADMIN: 'error',
  PRESIDENCIA: 'warning',
  DIR_COMERCIAL: 'warning',
  GERENTE_PRODUCTIVIDAD: 'info',
  GERENTE_DISTRITO: 'info',
  GERENTE_MARCA: 'info',
  REPRESENTANTE_MEDICO: 'success',
  CONSULTA: 'default',
};

export default function Usuarios() {
  const qc = useQueryClient();
  const [openNew, setOpenNew]     = useState(false);
  const [openEdit, setOpenEdit]   = useState(false);
  const [editItem, setEditItem]   = useState<any>(null);
  const [form, setForm]           = useState<Record<string, any>>({});
  const [msg, setMsg]             = useState('');
  const [msgType, setMsgType]     = useState<'success' | 'error'>('success');

  const { data, isLoading, isError, refetch } = useQuery({
    queryKey: ['usuarios'],
    queryFn: () => api.get('/admin/usuarios').then((r) => r.data),
    retry: 1,
  });

  // Dimensiones para relacionar el usuario según su rol.
  const { data: rms } = useQuery({
    queryKey: ['rms-all'], queryFn: () => api.get('/admin/rms').then((r) => r.data), retry: 1,
  });
  const { data: gerentes } = useQuery({
    queryKey: ['gerentes-all'], queryFn: () => api.get('/admin/gerentes').then((r) => r.data), retry: 1,
  });

  // Selector relacional: RM (rm_id) o Gerente (gerente_id) según el rol elegido.
  const renderRelacion = () => {
    const rol = form.rol;
    if (rol === 'REPRESENTANTE_MEDICO') {
      return (
        <FormControl fullWidth size="small">
          <InputLabel>Representante médico (DIM_RM)</InputLabel>
          <Select label="Representante médico (DIM_RM)" value={form.rm_id ?? ''}
                  onChange={(e) => setForm({ ...form, rm_id: e.target.value, gerente_id: null })}>
            <MenuItem value=""><em>— Sin vincular —</em></MenuItem>
            {(Array.isArray(rms) ? rms : []).map((r: any) => (
              <MenuItem key={r.id} value={r.id}>{r.codigo} — {r.nombre}</MenuItem>
            ))}
          </Select>
        </FormControl>
      );
    }
    if (rol === 'GERENTE_DISTRITO' || rol === 'GERENTE_MARCA') {
      const tipo = rol === 'GERENTE_DISTRITO' ? 'DISTRITO' : 'MARCA';
      const label = rol === 'GERENTE_DISTRITO' ? 'Gerente de Distrito (DIM_Gerente)' : 'Gerente de Producto / Marca (DIM_Gerente)';
      const opts = (Array.isArray(gerentes) ? gerentes : []).filter((g: any) => g.tipo === tipo);
      return (
        <FormControl fullWidth size="small">
          <InputLabel>{label}</InputLabel>
          <Select label={label} value={form.gerente_id ?? ''}
                  onChange={(e) => setForm({ ...form, gerente_id: e.target.value, rm_id: null })}>
            <MenuItem value=""><em>— Sin vincular —</em></MenuItem>
            {opts.map((g: any) => (
              <MenuItem key={g.id} value={g.id}>{g.codigo} — {g.nombre}</MenuItem>
            ))}
          </Select>
        </FormControl>
      );
    }
    return null;
  };

  const showMsg = (text: string, type: 'success' | 'error' = 'success') => {
    setMsg(text); setMsgType(type);
    setTimeout(() => setMsg(''), 4000);
  };

  const createMut = useMutation({
    mutationFn: () => api.post('/admin/usuarios', form),
    onSuccess: () => {
      setOpenNew(false); setForm({});
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg('Usuario creado correctamente');
    },
    onError: (e: any) => showMsg(e.response?.data?.detail || e.message, 'error'),
  });

  const updateMut = useMutation({
    mutationFn: () => api.put(`/admin/usuarios/${editItem?.id}`, form),
    onSuccess: () => {
      setOpenEdit(false); setEditItem(null); setForm({});
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg('Usuario actualizado');
    },
    onError: (e: any) => showMsg(e.response?.data?.detail || e.message, 'error'),
  });

  const toggleMut = useMutation({
    mutationFn: (row: any) =>
      api.put(`/admin/usuarios/${row.id}`, { activo: !row.activo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg('Estado cambiado');
    },
    onError: (e: any) => showMsg(e.response?.data?.detail || e.message, 'error'),
  });

  const handleEdit = (row: any) => {
    setEditItem(row);
    setForm({ nombre_completo: row.nombre_completo || '', email: row.email || '', rol: row.rol || '',
              rm_id: row.rm_id ?? null, gerente_id: row.gerente_id ?? null });
    setOpenEdit(true);
  };

  const usuarios: any[] = Array.isArray(data) ? data : [];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>
        Administración de Usuarios
      </Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Gestión de cuentas y roles del sistema
      </Typography>

      {msg && (
        <Alert severity={msgType} sx={{ mb: 2 }} onClose={() => setMsg('')}>{msg}</Alert>
      )}

      <Card elevation={2} sx={{ borderRadius: 3 }}>
        <CardContent>
          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
            <Typography variant="h6" fontWeight={600}>
              Usuarios {!isLoading && `(${usuarios.length})`}
            </Typography>
            <Stack direction="row" spacing={1}>
              <Button startIcon={<RefreshIcon />} size="small" onClick={() => refetch()}>
                Actualizar
              </Button>
              <Button
                variant="contained" startIcon={<AddIcon />} size="small"
                onClick={() => { setForm({}); setOpenNew(true); }}
              >
                Nuevo Usuario
              </Button>
            </Stack>
          </Box>

          {isLoading && (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}>
              <CircularProgress />
            </Box>
          )}

          {isError && (
            <Alert severity="error">
              No se pudieron cargar los usuarios. Verifica que el backend esté activo.
            </Alert>
          )}

          {!isLoading && !isError && (
            <TableContainer component={Paper} elevation={0}
              sx={{ borderRadius: 2, border: '1px solid', borderColor: 'divider' }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: 'primary.main' }}>
                  <TableRow>
                    {['#', 'Usuario', 'Nombre', 'Email', 'Rol', 'Estado', ''].map((h) => (
                      <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {usuarios.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                        Sin usuarios registrados
                      </TableCell>
                    </TableRow>
                  ) : (
                    usuarios.map((row: any, i: number) => (
                      <TableRow key={row.id} hover>
                        <TableCell sx={{ color: 'text.secondary', fontSize: 12 }}>{i + 1}</TableCell>
                        <TableCell sx={{ fontWeight: 600 }}>{row.username}</TableCell>
                        <TableCell>{row.nombre_completo}</TableCell>
                        <TableCell sx={{ fontSize: 12, color: 'text.secondary' }}>{row.email}</TableCell>
                        <TableCell>
                          <Chip
                            label={row.rol}
                            size="small"
                            color={ROL_COLORS[row.rol] ?? 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          <Chip
                            label={row.activo ? 'Activo' : 'Inactivo'}
                            color={row.activo ? 'success' : 'default'}
                            size="small"
                            variant={row.activo ? 'filled' : 'outlined'}
                          />
                        </TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5}>
                            <Tooltip title="Editar">
                              <IconButton size="small" color="primary" onClick={() => handleEdit(row)}>
                                <EditIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            <Tooltip title={row.activo ? 'Desactivar' : 'Activar'}>
                              <Button
                                size="small"
                                variant="outlined"
                                color={row.activo ? 'warning' : 'success'}
                                onClick={() => toggleMut.mutate(row)}
                                disabled={toggleMut.isPending}
                                sx={{ minWidth: 80, fontSize: 11 }}
                              >
                                {row.activo ? 'Desactivar' : 'Activar'}
                              </Button>
                            </Tooltip>
                          </Stack>
                        </TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* ── Dialog: Crear ─────────────────────────────────────────────── */}
      <Dialog open={openNew} onClose={() => setOpenNew(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Nuevo Usuario</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              fullWidth size="small" label="Usuario (login)"
              value={form.username || ''}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Nombre Completo"
              value={form.nombre_completo || ''}
              onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Email" type="email"
              value={form.email || ''}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Contrasena" type="password"
              helperText="Minimo 12 caracteres, mayuscula, minuscula y numero"
              value={form.password || ''}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
            />
            <FormControl fullWidth size="small">
              <InputLabel>Rol</InputLabel>
              <Select
                label="Rol"
                value={form.rol || ''}
                onChange={(e) => setForm({ ...form, rol: e.target.value, rm_id: null, gerente_id: null })}
              >
                {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
              </Select>
            </FormControl>
            {renderRelacion()}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenNew(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() => createMut.mutate()}
            disabled={createMut.isPending}
          >
            {createMut.isPending ? <CircularProgress size={18} /> : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* ── Dialog: Editar ────────────────────────────────────────────── */}
      <Dialog open={openEdit} onClose={() => setOpenEdit(false)} maxWidth="sm" fullWidth>
        <DialogTitle>Editar: {editItem?.username}</DialogTitle>
        <DialogContent>
          <Stack spacing={2} sx={{ mt: 1 }}>
            <TextField
              fullWidth size="small" label="Nombre Completo"
              value={form.nombre_completo || ''}
              onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Email" type="email"
              value={form.email || ''}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            <FormControl fullWidth size="small">
              <InputLabel>Rol</InputLabel>
              <Select
                label="Rol"
                value={form.rol || ''}
                onChange={(e) => setForm({ ...form, rol: e.target.value, rm_id: null, gerente_id: null })}
              >
                {ROLES.map((r) => <MenuItem key={r} value={r}>{r}</MenuItem>)}
              </Select>
            </FormControl>
            {renderRelacion()}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenEdit(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={() => updateMut.mutate()}
            disabled={updateMut.isPending}
          >
            {updateMut.isPending ? <CircularProgress size={18} /> : 'Actualizar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
