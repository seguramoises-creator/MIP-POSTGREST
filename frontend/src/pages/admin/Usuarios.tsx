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
  CircularProgress, MenuItem, Select, FormControl, InputLabel, FormHelperText,
  IconButton, Tooltip, Stack, Divider, InputAdornment, Checkbox, FormControlLabel,
  OutlinedInput,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import RefreshIcon from '@mui/icons-material/Refresh';
import EditIcon from '@mui/icons-material/Edit';
import Visibility from '@mui/icons-material/Visibility';
import VisibilityOff from '@mui/icons-material/VisibilityOff';
import Casino from '@mui/icons-material/Casino';
import ForwardToInbox from '@mui/icons-material/ForwardToInbox';
import { api } from '../../services/api';

// Genera una contraseña que cumple la política (mín. 12, mayúscula, minúscula,
// número y carácter especial). Evita ambigüedades (0/O, 1/l/I) para dictado.
function generarPassword(): string {
  const May = 'ABCDEFGHJKLMNPQRSTUVWXYZ', min = 'abcdefghijkmnpqrstuvwxyz';
  const num = '23456789', esp = '!@#$%*?';
  const pick = (s: string) => s[Math.floor(Math.random() * s.length)];
  const base = [pick(May), pick(min), pick(num), pick(esp)];
  const todos = May + min + num + esp;
  for (let i = 0; i < 10; i++) base.push(pick(todos));
  // barajar (Fisher–Yates)
  for (let i = base.length - 1; i > 0; i--) {
    const j = Math.floor(Math.random() * (i + 1));
    [base[i], base[j]] = [base[j], base[i]];
  }
  return base.join('');
}

// Los 13 roles de la matriz RBAC, en el mismo orden que las columnas de "Roles y Permisos".
const ROLES = [
  'REPRESENTANTE_MEDICO', 'GERENTE_DISTRITO', 'GERENTE_MARCA', 'GERENTE_MARKETING',
  'GERENTE_PRODUCTIVIDAD', 'GERENTE_MEDICO', 'PRESIDENCIA', 'ANALISTA_DATOS',
  'FINANZAS', 'ADMIN', 'CAPACITACION', 'DIR_COMERCIAL', 'CONSULTA',
];

// Etiqueta legible del rol (el value guardado sigue siendo el código del enum). Coincide con
// los nombres de columna de la matriz de Roles y Permisos.
const ROL_LABEL: Record<string, string> = {
  REPRESENTANTE_MEDICO: 'Representante',
  GERENTE_DISTRITO: 'Ger. Distrito',
  GERENTE_MARCA: 'Ger. Producto',
  GERENTE_MARKETING: 'Ger. Marketing',
  GERENTE_PRODUCTIVIDAD: 'Capac./Product.',
  GERENTE_MEDICO: 'Ger. Médico',
  PRESIDENCIA: 'Dir. General',
  ANALISTA_DATOS: 'Analista Datos',
  FINANZAS: 'Finanzas',
  ADMIN: 'Superadmin',
  CAPACITACION: 'Capacitación',
  DIR_COMERCIAL: 'Dir. Comercial',
  CONSULTA: 'Consulta',
};

const ROL_COLORS: Record<string, 'error' | 'warning' | 'info' | 'success' | 'default' | 'secondary' | 'primary'> = {
  ADMIN: 'error',
  PRESIDENCIA: 'warning',
  DIR_COMERCIAL: 'warning',
  GERENTE_PRODUCTIVIDAD: 'info',
  GERENTE_DISTRITO: 'info',
  GERENTE_MARCA: 'info',
  GERENTE_MARKETING: 'primary',
  GERENTE_MEDICO: 'primary',
  ANALISTA_DATOS: 'secondary',
  FINANZAS: 'warning',
  CAPACITACION: 'secondary',
  REPRESENTANTE_MEDICO: 'success',
  CONSULTA: 'default',
};

export default function Usuarios() {
  const qc = useQueryClient();
  const [openNew, setOpenNew]     = useState(false);
  const [openEdit, setOpenEdit]   = useState(false);
  const [editItem, setEditItem]   = useState<any>(null);
  const [nuevaPass, setNuevaPass] = useState('');
  const [editBloqueado, setEditBloqueado] = useState(false); // casilla bloqueado (editar)
  const [showPwd, setShowPwd]         = useState(false);   // ver contraseña (crear)
  const [showResetPwd, setShowResetPwd] = useState(false); // ver contraseña (restablecer)
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
  const { data: paises } = useQuery({
    queryKey: ['paises-all'], queryFn: () => api.get('/admin/paises').then((r) => r.data), retry: 1,
  });

  // Selector de País (obligatorio para el REPRESENTANTE_MEDICO; recomendado para todos). Se guarda
  // en Usuario.pais_codigo y fija el contexto de país del usuario. El value es el CÓDIGO del país.
  const renderPais = () => (
    <FormControl fullWidth size="small">
      <InputLabel>País{form.rol === 'REPRESENTANTE_MEDICO' ? ' *' : ''}</InputLabel>
      <Select label={`País${form.rol === 'REPRESENTANTE_MEDICO' ? ' *' : ''}`}
              value={form.pais_codigo ?? ''}
              onChange={(e) => setForm({ ...form, pais_codigo: e.target.value })}>
        <MenuItem value=""><em>— Sin país —</em></MenuItem>
        {(Array.isArray(paises) ? paises : []).map((p: any) => (
          <MenuItem key={p.codigo} value={p.codigo}>{p.codigo} — {p.nombre}</MenuItem>
        ))}
      </Select>
    </FormControl>
  );

  // Selector relacional: RM (rm_id) o Gerente (gerente_id) según el rol elegido.
  const renderRelacion = () => {
    const rol = form.rol;
    if (rol === 'REPRESENTANTE_MEDICO') {
      // OBLIGATORIO: sin vínculo a un DIM_RM el usuario recibe 403 y no ve su cobertura ni
      // puede registrar visitas. El backend también lo valida (422).
      const falta = !form.rm_id;
      return (
        <FormControl fullWidth size="small" required error={falta}>
          <InputLabel>Representante médico (DIM_RM) *</InputLabel>
          <Select label="Representante médico (DIM_RM) *" value={form.rm_id ?? ''}
                  onChange={(e) => setForm({ ...form, rm_id: e.target.value, gerente_id: null })}>
            {(Array.isArray(rms) ? rms : []).map((r: any) => (
              <MenuItem key={r.id} value={r.id}>{r.codigo} — {r.nombre}</MenuItem>
            ))}
          </Select>
          <FormHelperText>
            {falta ? 'Obligatorio: sin vincular, el representante no puede ver su cobertura.' : ' '}
          </FormHelperText>
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

  // Mensaje legible desde un error de axios, incluyendo el 422 de FastAPI/Pydantic
  // (detail = array de {loc, msg}) que de otro modo se vería como "status code 422".
  const errorMsg = (e: any): string => {
    // El backend puede responder con `detail` (FastAPI default) o `detalle`
    // (handler custom de validación en main.py). Ambos pueden ser array Pydantic.
    const d = e?.response?.data?.detail ?? e?.response?.data?.detalle ?? e?.response?.data?.error;
    if (Array.isArray(d)) {
      return d
        .map((x: any) => {
          const campo = Array.isArray(x.loc) ? x.loc[x.loc.length - 1] : '';
          return campo ? `${campo}: ${x.msg}` : x.msg;
        })
        .join(' · ');
    }
    return d || e?.message || 'Error desconocido';
  };

  const EMAIL_RE = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
  // El email es OPCIONAL: vacío se permite (usuario sin correo). Si se escribe algo,
  // debe ser un correo válido; si no, se avisa y se evita el 422 del servidor.
  const emailInvalido = (): boolean => {
    const v = (form.email || '').trim();
    if (v === '') return false;               // opcional: sin correo, se permite
    if (!EMAIL_RE.test(v)) {
      showMsg('El correo electrónico no es válido. Déjalo vacío o escribe uno con formato usuario@dominio.com.', 'error');
      return true;
    }
    return false;
  };
  const submitCreate = () => { if (!emailInvalido()) createMut.mutate(); };
  const submitUpdate = () => {
    if (emailInvalido()) return;
    const id = editItem?.id;
    updateMut.mutate(undefined, {
      onSuccess: () => { if (id != null) paisesMut.mutate({ id, paises: form.paises || [] }); },
    });
  };

  const createMut = useMutation({
    mutationFn: () => api.post('/admin/usuarios', form),
    onSuccess: (_r, _v, _c) => {
      // Se lee `form` ANTES de limpiarlo: si no, el mensaje siempre diría "contraseña".
      const conEnlace = !!form.email && !(form.password || '').trim();
      const correo = form.email;
      setOpenNew(false); setForm({});
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg(conEnlace
        ? `Usuario creado. Se envió el enlace de activación a ${correo} (válido 24 horas).`
        : 'Usuario creado con la contraseña indicada. Entrégasela por una vía segura, no por correo.');
    },
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  // Reenvía el enlace cuando venció o no llegó. El anterior queda inservible al instante.
  const reenviarMut = useMutation({
    mutationFn: (row: any) => api.post(`/admin/usuarios/${row.id}/reenviar-activacion`),
    onSuccess: (r: any) => showMsg(r.data?.message || 'Enlace de activación reenviado'),
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  const updateMut = useMutation({
    mutationFn: () => api.put(`/admin/usuarios/${editItem?.id}`, form),
    onSuccess: () => {
      setOpenEdit(false); setEditItem(null); setForm({});
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg('Usuario actualizado');
    },
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  const toggleMut = useMutation({
    mutationFn: (row: any) =>
      api.put(`/admin/usuarios/${row.id}`, { activo: !row.activo }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg('Estado cambiado');
    },
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  // Bloquear/desbloquear un usuario con la casilla "Bloqueado" (solo ADMIN).
  const bloqueoMut = useMutation({
    mutationFn: (v: { id: number; bloqueado: boolean }) =>
      api.patch(`/admin/usuarios/${v.id}/bloqueo`, { bloqueado: v.bloqueado }),
    onSuccess: (_r, v) => {
      qc.invalidateQueries({ queryKey: ['usuarios'] });
      showMsg(v.bloqueado ? 'Usuario bloqueado' : 'Usuario desbloqueado');
    },
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  // Restablecer contraseña de un usuario (solo ADMIN) — desde la edición.
  const resetPassMut = useMutation({
    mutationFn: () => api.post(`/admin/usuarios/${editItem?.id}/reset-password`, { password_nuevo: nuevaPass }),
    onSuccess: (r: any) => { setNuevaPass(''); showMsg(r.data?.message || 'Contraseña restablecida'); },
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

  const handleEdit = async (row: any) => {
    setEditItem(row);
    setNuevaPass('');
    setEditBloqueado(!!row.bloqueado);
    setForm({ nombre_completo: row.nombre_completo || '', email: row.email || '', rol: row.rol || '',
              pais_codigo: row.pais_codigo ?? '', rm_id: row.rm_id ?? null, gerente_id: row.gerente_id ?? null,
              paises: [] });
    setOpenEdit(true);
    // Los países visibles del usuario se cargan aparte (endpoint propio de alcance) para no
    // acoplar el PUT de perfil con el PUT de alcance — cada uno reemplaza su propio conjunto.
    try {
      const r = await api.get(`/admin/usuarios/${row.id}/paises`);
      setForm((f) => ({ ...f, paises: r.data?.paises || [] }));
    } catch {
      // si falla la carga, se deja vacío (= todos los países); el admin puede corregirlo a mano
    }
  };

  // Fija los países visibles del usuario editado. Se dispara junto con "Actualizar" —
  // reemplaza el conjunto completo (PUT), no lo añade.
  const paisesMut = useMutation({
    mutationFn: (v: { id: number; paises: string[] }) =>
      api.put(`/admin/usuarios/${v.id}/paises`, { paises: v.paises }),
    onError: (e: any) => showMsg(errorMsg(e), 'error'),
  });

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
                    {['#', 'Usuario', 'Nombre', 'Email', 'Rol', 'Estado', 'Bloqueado', ''].map((h) => (
                      <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {usuarios.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={8} align="center" sx={{ py: 4, color: 'text.secondary' }}>
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
                            label={ROL_LABEL[row.rol] ?? row.rol}
                            size="small"
                            color={ROL_COLORS[row.rol] ?? 'default'}
                          />
                        </TableCell>
                        <TableCell>
                          {/* "Sin activar" ≠ "Inactivo": la cuenta está habilitada, lo que
                              falta es que su titular abra el enlace y cree su contraseña.
                              Distinguirlas evita que el admin "arregle" con el interruptor
                              de activo/inactivo algo que solo se resuelve reenviando. */}
                          {row.activo && !row.activado_en ? (
                            <Tooltip title="El usuario todavía no abrió el enlace de activación ni creó su contraseña">
                              <Chip label="Sin activar" color="warning" size="small" />
                            </Tooltip>
                          ) : (
                            <Chip
                              label={row.activo ? 'Activo' : 'Inactivo'}
                              color={row.activo ? 'success' : 'default'}
                              size="small"
                              variant={row.activo ? 'filled' : 'outlined'}
                            />
                          )}
                        </TableCell>
                        <TableCell>
                          <Tooltip title={row.bloqueado ? 'Bloqueado — desmarca para desbloquear' : 'Marca para bloquear el acceso'}>
                            <Checkbox
                              size="small" color="error"
                              checked={!!row.bloqueado}
                              disabled={bloqueoMut.isPending}
                              onChange={() => bloqueoMut.mutate({ id: row.id, bloqueado: !row.bloqueado })}
                            />
                          </Tooltip>
                        </TableCell>
                        <TableCell>
                          <Stack direction="row" spacing={0.5}>
                            <Tooltip title="Editar">
                              <IconButton size="small" color="primary" onClick={() => handleEdit(row)}>
                                <EditIcon fontSize="small" />
                              </IconButton>
                            </Tooltip>
                            {/* Solo aparece donde sirve: cuenta sin activar y con correo. */}
                            {!row.activado_en && row.email && (
                              <Tooltip title="Reenviar enlace de activación (invalida el anterior)">
                                <IconButton size="small" color="info"
                                            disabled={reenviarMut.isPending}
                                            onClick={() => reenviarMut.mutate(row)}>
                                  <ForwardToInbox fontSize="small" />
                                </IconButton>
                              </Tooltip>
                            )}
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
              autoComplete="off"
              value={form.username || ''}
              onChange={(e) => setForm({ ...form, username: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Nombre Completo"
              value={form.nombre_completo || ''}
              onChange={(e) => setForm({ ...form, nombre_completo: e.target.value })}
            />
            <TextField
              fullWidth size="small" label="Email (opcional)" type="email"
              autoComplete="off"
              value={form.email || ''}
              onChange={(e) => setForm({ ...form, email: e.target.value })}
            />
            {/* Con correo, lo normal es DEJARLA VACÍA: el sistema envía un enlace de
                activación y el usuario crea su propia contraseña. Una clave enviada por
                correo queda archivada para siempre en el buzón y en cada servidor por el
                que pasó; el enlace, en cambio, caduca y muere al usarse.
                autoComplete="new-password" evita que el navegador rellene este campo con
                las credenciales guardadas del ADMIN (causa de que un rep quedara con una
                contraseña distinta a la esperada). */}
            <TextField
              fullWidth size="small"
              label={form.email ? 'Contraseña (opcional)' : 'Contraseña'}
              type={showPwd ? 'text' : 'password'}
              autoComplete="new-password"
              helperText={form.email
                ? 'Déjala vacía (recomendado): se enviará un enlace de activación para que el usuario cree su contraseña.'
                : 'Sin correo no hay dónde enviar el enlace de activación, así que aquí es obligatoria. Mín. 8 caracteres (12 para ADMIN) · mayúscula, minúscula, número y especial (!@#$%…)'}
              value={form.password || ''}
              onChange={(e) => setForm({ ...form, password: e.target.value })}
              InputProps={{
                endAdornment: (
                  <InputAdornment position="end">
                    <Tooltip title="Generar contraseña segura">
                      <IconButton edge="end" size="small"
                                  onClick={() => { setForm({ ...form, password: generarPassword() }); setShowPwd(true); }}>
                        <Casino fontSize="small" />
                      </IconButton>
                    </Tooltip>
                    <IconButton edge="end" size="small" onClick={() => setShowPwd((v) => !v)}>
                      {showPwd ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                    </IconButton>
                  </InputAdornment>
                ),
              }}
            />
            <FormControl fullWidth size="small">
              <InputLabel>Rol</InputLabel>
              <Select
                label="Rol"
                value={form.rol || ''}
                onChange={(e) => setForm({ ...form, rol: e.target.value, rm_id: null, gerente_id: null })}
              >
                {ROLES.map((r) => <MenuItem key={r} value={r}>{ROL_LABEL[r] ?? r}</MenuItem>)}
              </Select>
            </FormControl>
            {renderPais()}
            {renderRelacion()}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenNew(false)}>Cancelar</Button>
          <Button
            variant="contained"
            onClick={submitCreate}
            disabled={createMut.isPending || (form.rol === 'REPRESENTANTE_MEDICO' && !form.rm_id)}
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
              fullWidth size="small" label="Email (opcional)" type="email"
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
                {ROLES.map((r) => <MenuItem key={r} value={r}>{ROL_LABEL[r] ?? r}</MenuItem>)}
              </Select>
            </FormControl>
            {renderPais()}
            {renderRelacion()}

            {/* Alcance de países visibles (Security.FACT_UsuarioPais). Independiente del
                "País" de arriba (contexto/vínculo del usuario): esto restringe qué países
                puede CONSULTAR en el sistema. */}
            <FormControl fullWidth size="small">
              <InputLabel>Países visibles</InputLabel>
              <Select
                multiple
                label="Países visibles"
                value={Array.isArray(form.paises) ? form.paises : []}
                onChange={(e) => {
                  const v = e.target.value;
                  setForm({ ...form, paises: typeof v === 'string' ? v.split(',') : v });
                }}
                input={<OutlinedInput label="Países visibles" />}
                renderValue={(selected: string[]) => {
                  if (selected.length === 0) return 'Todos los países';
                  const lista = Array.isArray(paises) ? paises : [];
                  return selected
                    .map((cod) => {
                      const p = lista.find((x: any) => x.codigo === cod);
                      return p ? `${p.codigo} — ${p.nombre}` : cod;
                    })
                    .join(', ');
                }}
              >
                {(Array.isArray(paises) ? paises : []).map((p: any) => (
                  <MenuItem key={p.codigo} value={p.codigo}>
                    <Checkbox size="small" checked={(form.paises || []).includes(p.codigo)} />
                    {p.codigo} — {p.nombre}
                  </MenuItem>
                ))}
              </Select>
              <FormHelperText>
                Sin países seleccionados, el usuario ve todos. Con países, solo esos.
              </FormHelperText>
            </FormControl>

            {/* Casilla de bloqueo: marcada = usuario bloqueado; desmarcar = desbloquear. */}
            <FormControlLabel
              control={
                <Checkbox
                  color="error"
                  checked={editBloqueado}
                  disabled={bloqueoMut.isPending}
                  onChange={() => {
                    const nuevo = !editBloqueado;
                    setEditBloqueado(nuevo);
                    if (editItem?.id != null) bloqueoMut.mutate({ id: editItem.id, bloqueado: nuevo });
                  }}
                />
              }
              label={editBloqueado ? 'Usuario BLOQUEADO — desmarque para desbloquear' : 'Usuario desbloqueado (marque para bloquear)'}
            />

            {/* Restablecer contraseña (solo ADMIN). Mín. 12 caracteres con mayúscula,
                minúscula, número y carácter especial. El usuario deberá cambiarla al entrar. */}
            <Divider textAlign="left" sx={{ pt: 1 }}>Restablecer contraseña</Divider>
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField
                fullWidth size="small" label="Nueva contraseña"
                type={showResetPwd ? 'text' : 'password'}
                autoComplete="new-password"
                value={nuevaPass} onChange={(e) => setNuevaPass(e.target.value)}
                helperText="Mín. 8 (12 para ADMIN) · mayúscula, minúscula, número y carácter especial"
                InputProps={{
                  endAdornment: (
                    <InputAdornment position="end">
                      <Tooltip title="Generar contraseña segura">
                        <IconButton edge="end" size="small"
                                    onClick={() => { setNuevaPass(generarPassword()); setShowResetPwd(true); }}>
                          <Casino fontSize="small" />
                        </IconButton>
                      </Tooltip>
                      <IconButton edge="end" size="small" onClick={() => setShowResetPwd((v) => !v)}>
                        {showResetPwd ? <VisibilityOff fontSize="small" /> : <Visibility fontSize="small" />}
                      </IconButton>
                    </InputAdornment>
                  ),
                }}
              />
              <Button
                variant="outlined" sx={{ whiteSpace: 'nowrap', mt: 0.25 }}
                disabled={resetPassMut.isPending || nuevaPass.trim().length < 8}
                onClick={() => resetPassMut.mutate()}
              >
                {resetPassMut.isPending ? <CircularProgress size={18} /> : 'Restablecer'}
              </Button>
            </Stack>
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenEdit(false)}>Cerrar</Button>
          <Button
            variant="contained"
            onClick={submitUpdate}
            disabled={updateMut.isPending || paisesMut.isPending || (form.rol === 'REPRESENTANTE_MEDICO' && !form.rm_id)}
          >
            {updateMut.isPending || paisesMut.isPending ? <CircularProgress size={18} /> : 'Actualizar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
