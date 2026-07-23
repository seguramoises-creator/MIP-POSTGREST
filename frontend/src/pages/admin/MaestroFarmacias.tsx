/**
 * MaestroFarmacias.tsx — Maestro de Farmacias. Pantalla del menú lateral ("Maestros y
 * planeación" → ruta /farmacias/maestro), NO una tab de Admin (jul-2026: se movió al menú
 * junto a "Médicos"). Tabla + alta/edición directa (ADMIN/GERENTE_PRODUCTIVIDAD, sin
 * aprobación — crea origen=CONFIG, estado=ACTIVA).
 * Espejo de MaestroMedicos.tsx, alcance reducido a lo que pide la Tarea 8 del plan
 * `2026-07-22-modulo-farmacias.md`.
 */
import { useMemo, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, TextField, MenuItem, Button, Stack,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert, IconButton, Tooltip,
  CircularProgress, InputAdornment, Switch, FormControlLabel, Grid,
} from '@mui/material';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import { useCicloStore } from '../../store/ciclo.store';
import {
  listarMaestroFarmacias, crearMaestroFarmacia, actualizarMaestroFarmacia,
  type FarmaciaMaestro, type FarmaciaDatos,
} from '../../services/farmacias.service';
import { listarProvincias, listarMunicipios } from '../../services/visita.service';

const ESTADO_COLOR: Record<string, 'success' | 'warning' | 'error' | 'default'> = {
  ACTIVA: 'success', PENDIENTE_APROBACION: 'warning', RECHAZADA: 'error',
};

const formVacio: FarmaciaDatos = {
  es_cadena: false, cadena: '', sucursal: '', nombre: '', direccion: '',
  provincia: '', municipio: '', sector: '', encargado: '', telefono: '', email: '',
};

export default function MaestroFarmacias() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);

  const [q, setQ] = useState('');
  const [estado, setEstado] = useState('');
  const [openForm, setOpenForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<FarmaciaDatos>(formVacio);
  const [msg, setMsg] = useState<{ t: string; tipo: 'success' | 'error' } | null>(null);
  // Provincia/Municipio son listas desplegables del catálogo del sistema (no texto libre).
  // El modelo guarda el NOMBRE (string); `provinciaId` es solo para encadenar los municipios.
  const [provinciaId, setProvinciaId] = useState<number | ''>('');

  const flash = (t: string, tipo: 'success' | 'error' = 'success') => {
    setMsg({ t, tipo }); setTimeout(() => setMsg(null), 5000);
  };

  const { data: farmacias = [], isLoading } = useQuery({
    queryKey: ['farm-maestro', paisCodigo, q, estado],
    queryFn: () => listarMaestroFarmacias({
      pais_codigo: paisCodigo || undefined, q: q || undefined, estado: estado || undefined,
    }),
    enabled: !!paisCodigo,
  });

  const refrescar = () => qc.invalidateQueries({ queryKey: ['farm-maestro'] });

  // Catálogo de provincias del país + municipios en cascada de la provincia elegida.
  const { data: provincias = [] } = useQuery({
    queryKey: ['geo-provincias', paisCodigo],
    queryFn: () => listarProvincias(paisCodigo || undefined),
    enabled: !!paisCodigo,
  });
  const { data: municipios = [] } = useQuery({
    queryKey: ['geo-municipios', provinciaId],
    queryFn: () => listarMunicipios(provinciaId as number),
    enabled: provinciaId !== '',
  });
  // Al editar, la farmacia trae la provincia por NOMBRE: se resuelve a su id para poder
  // cargar sus municipios en el desplegable.
  useEffect(() => {
    if (openForm && form.provincia && provinciaId === '' && provincias.length) {
      const p = provincias.find((x) => x.nombre === form.provincia);
      if (p) setProvinciaId(p.id);
    }
  }, [openForm, form.provincia, provincias, provinciaId]);

  const abrirCrear = () => { setEditId(null); setForm(formVacio); setProvinciaId(''); setOpenForm(true); };
  const abrirEditar = (f: FarmaciaMaestro) => {
    setEditId(f.id);
    setProvinciaId('');   // el useEffect lo resuelve desde el nombre de la provincia
    setForm({
      es_cadena: f.es_cadena, cadena: f.cadena ?? '', sucursal: f.sucursal ?? '', nombre: f.nombre ?? '',
      direccion: f.direccion, provincia: f.provincia ?? '', municipio: f.municipio ?? '', sector: f.sector ?? '',
      encargado: f.encargado, telefono: f.telefono ?? '', email: f.email ?? '',
    });
    setOpenForm(true);
  };

  const guardar = useMutation({
    mutationFn: async () => {
      if (editId) return actualizarMaestroFarmacia(editId, form);
      if (!paisCodigo) throw new Error('Selecciona un país en la barra superior.');
      return crearMaestroFarmacia(paisCodigo, form);
    },
    onSuccess: () => { setOpenForm(false); refrescar(); flash(editId ? 'Farmacia actualizada' : 'Farmacia creada'); },
    onError: (e: any) => {
      const d = e?.response?.data?.detail;
      flash(typeof d === 'string' ? d : (d?.mensaje || e?.message || 'Error al guardar'), 'error');
    },
  });

  const setF = (k: keyof FarmaciaDatos, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  const faltantes = useMemo(() => {
    const f: string[] = [];
    if (!form.direccion.trim()) f.push('dirección');
    if (!form.encargado.trim()) f.push('encargado');
    if (form.es_cadena ? !form.cadena?.trim() : !form.nombre?.trim()) f.push('nombre');
    return f;
  }, [form]);

  return (
    <Box>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.t}</Alert>}
      {!paisCodigo && <Alert severity="info" sx={{ mb: 2 }}>Selecciona un país en la barra superior para ver su maestro de farmacias.</Alert>}

      <Card elevation={2} sx={{ borderRadius: 3 }}>
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }} alignItems="center">
            <TextField size="small" placeholder="Buscar por nombre…"
              value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 260 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }} />
            <TextField size="small" select label="Estado" value={estado}
              onChange={(e) => setEstado(e.target.value)} sx={{ minWidth: 180 }}>
              <MenuItem value="">Todos</MenuItem>
              <MenuItem value="ACTIVA">Activa</MenuItem>
              <MenuItem value="PENDIENTE_APROBACION">Pendiente aprobación</MenuItem>
              <MenuItem value="RECHAZADA">Rechazada</MenuItem>
            </TextField>
            <Box sx={{ flex: 1 }} />
            <Tooltip title="Actualizar"><IconButton onClick={refrescar}><RefreshIcon /></IconButton></Tooltip>
            <Button size="small" variant="contained" startIcon={<AddIcon />} disabled={!paisCodigo} onClick={abrirCrear}>
              Nueva farmacia
            </Button>
          </Stack>

          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}><CircularProgress /></Box>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 520 }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    {['Nombre', 'Encargado', 'Dirección', 'Teléfono', 'Estado', 'Origen', ''].map((h) => (
                      <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {farmacias.map((f) => (
                    <TableRow key={f.id} hover>
                      <TableCell>{f.nombre_completo}</TableCell>
                      <TableCell>{f.encargado || '—'}</TableCell>
                      <TableCell>{f.direccion || '—'}</TableCell>
                      <TableCell>{f.telefono || '—'}</TableCell>
                      <TableCell>
                        <Chip size="small" label={f.estado} color={ESTADO_COLOR[f.estado] ?? 'default'} />
                        {!f.activo && <Chip size="small" label="Inactiva" sx={{ ml: 0.5 }} />}
                      </TableCell>
                      <TableCell>{f.origen}</TableCell>
                      <TableCell align="right">
                        <IconButton size="small" onClick={() => abrirEditar(f)}><EditIcon fontSize="small" /></IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                  {farmacias.length === 0 && (
                    <TableRow><TableCell colSpan={7} align="center" sx={{ color: 'text.secondary', py: 3 }}>
                      No hay farmacias que coincidan con el filtro.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Diálogo Crear/Editar */}
      <Dialog open={openForm} onClose={() => setOpenForm(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editId ? 'Editar farmacia' : 'Nueva farmacia'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12}>
              <FormControlLabel
                control={<Switch checked={form.es_cadena} onChange={(e) => setF('es_cadena', e.target.checked)} />}
                label={form.es_cadena ? 'Es cadena' : 'No es cadena (farmacia independiente)'}
              />
            </Grid>
            {form.es_cadena ? (
              <>
                <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Cadena" value={form.cadena ?? ''} onChange={(e) => setF('cadena', e.target.value)} /></Grid>
                <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Sucursal" value={form.sucursal ?? ''} onChange={(e) => setF('sucursal', e.target.value)} /></Grid>
              </>
            ) : (
              <Grid item xs={12}><TextField fullWidth size="small" label="Nombre" value={form.nombre ?? ''} onChange={(e) => setF('nombre', e.target.value)} /></Grid>
            )}
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Dirección" value={form.direccion}
                         error={!form.direccion.trim()} onChange={(e) => setF('direccion', e.target.value)} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" required label="Encargado" value={form.encargado}
                         error={!form.encargado.trim()} onChange={(e) => setF('encargado', e.target.value)} />
            </Grid>
            <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Teléfono" value={form.telefono ?? ''} onChange={(e) => setF('telefono', e.target.value)} /></Grid>
            <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Email" value={form.email ?? ''} onChange={(e) => setF('email', e.target.value)} /></Grid>
            <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Sector" value={form.sector ?? ''} onChange={(e) => setF('sector', e.target.value)} /></Grid>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="Provincia" value={provinciaId}
                onChange={(e) => {
                  const id = e.target.value === '' ? '' : Number(e.target.value);
                  setProvinciaId(id);
                  const p = provincias.find((x) => x.id === id);
                  // Guarda el NOMBRE (contrato del modelo) y limpia el municipio al cambiar de provincia.
                  setForm((f) => ({ ...f, provincia: p ? p.nombre : '', municipio: '' }));
                }}>
                <MenuItem value=""><em>— Selecciona —</em></MenuItem>
                {provincias.map((p) => <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="Municipio" value={form.municipio ?? ''}
                disabled={provinciaId === ''}
                helperText={provinciaId === '' ? 'Elige primero la provincia' : ' '}
                onChange={(e) => setF('municipio', e.target.value)}>
                <MenuItem value=""><em>— Selecciona —</em></MenuItem>
                {municipios.map((m) => <MenuItem key={m.id} value={m.nombre}>{m.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            {faltantes.length > 0 && (
              <Grid item xs={12}><Typography variant="caption" color="error">Falta: {faltantes.join(', ')}.</Typography></Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenForm(false)}>Cancelar</Button>
          <Button variant="contained" disabled={guardar.isPending || faltantes.length > 0}
            onClick={() => guardar.mutate()}>
            {guardar.isPending ? <CircularProgress size={18} /> : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
