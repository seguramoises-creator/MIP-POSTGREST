/**
 * MaestroMedicos.tsx — Maestro de Médicos (fuente única del dato general del médico).
 * Subpestaña dentro de la sección Médicos. Tabla + KPIs + crear/editar con dedup.
 */
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Grid, Card, CardContent, Typography, TextField, MenuItem, Button, Stack,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Chip,
  Dialog, DialogTitle, DialogContent, DialogActions, Alert, IconButton, Tooltip,
  CircularProgress, InputAdornment, Stepper, Step, StepLabel,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import AddIcon from '@mui/icons-material/Add';
import EditIcon from '@mui/icons-material/Edit';
import SearchIcon from '@mui/icons-material/Search';
import RefreshIcon from '@mui/icons-material/Refresh';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';
import {
  mmListar, mmKpis, mmCrear, mmActualizar, mmPreview, mmImportar, mmExportar, mmHistorial,
  type MaestroMedico, type ImportPreview, type ImportResultado, type HistorialItem,
} from '../../services/maestroMedicos.service';
import HistoryIcon from '@mui/icons-material/History';

type Cat = { id: number; nombre: string };

const KPIS: { key: keyof import('../../services/maestroMedicos.service').MaestroMedicoKpis; label: string; color: string }[] = [
  { key: 'total', label: 'Total médicos', color: '#1e293b' },
  { key: 'activos', label: 'Activos', color: '#059669' },
  { key: 'nuevos_mes', label: 'Nuevos este mes', color: '#2563eb' },
  { key: 'sin_asignacion', label: 'Sin asignación', color: '#d97706' },
  { key: 'pendientes_validacion', label: 'Pendientes validación', color: '#dc2626' },
];

export default function MaestroMedicos() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);

  const [q, setQ] = useState('');
  const [estado, setEstado] = useState('');
  const [openForm, setOpenForm] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<Record<string, any>>({});
  const [msg, setMsg] = useState<{ t: string; tipo: 'success' | 'error' } | null>(null);
  const [dupBlando, setDupBlando] = useState<{ mensaje: string; coincidencias: any[] } | null>(null);
  // Importación Excel (Stepper)
  const [openImport, setOpenImport] = useState(false);
  const [impPaso, setImpPaso] = useState(0);
  const [impFile, setImpFile] = useState<File | null>(null);
  const [impPreview, setImpPreview] = useState<ImportPreview | null>(null);
  const [impResultado, setImpResultado] = useState<ImportResultado | null>(null);
  const [impBusy, setImpBusy] = useState(false);

  const cerrarImport = () => {
    setOpenImport(false); setImpPaso(0); setImpFile(null);
    setImpPreview(null); setImpResultado(null); setImpBusy(false);
  };
  const previsualizar = async () => {
    if (!impFile || !paisCodigo) return;
    setImpBusy(true);
    try { setImpPreview(await mmPreview(paisCodigo, impFile)); setImpPaso(1); }
    catch (e: any) { flash(e?.response?.data?.detail || e?.message || 'No se pudo previsualizar', 'error'); }
    finally { setImpBusy(false); }
  };
  const ejecutarImport = async () => {
    if (!impFile || !paisCodigo) return;
    setImpBusy(true);
    try { setImpResultado(await mmImportar(paisCodigo, impFile)); setImpPaso(2); refrescar(); }
    catch (e: any) { flash(e?.response?.data?.detail || e?.message || 'No se pudo importar', 'error'); }
    finally { setImpBusy(false); }
  };

  const flash = (t: string, tipo: 'success' | 'error' = 'success') => {
    setMsg({ t, tipo }); setTimeout(() => setMsg(null), 5000);
  };

  // Listado + KPIs
  const { data: medicos = [], isLoading } = useQuery({
    queryKey: ['mm-listar', q, estado],
    queryFn: () => mmListar({ q: q || undefined, estado: estado || undefined, limit: 300 }),
  });
  const { data: kpis } = useQuery({ queryKey: ['mm-kpis'], queryFn: mmKpis });

  // Catálogos relacionales
  const { data: especialidades = [] } = useQuery<Cat[]>({
    queryKey: ['geo-esp'],
    queryFn: () => api.get('/categorizacion/geo/especialidades').then((r) => r.data),
  });
  const { data: provincias = [] } = useQuery<Cat[]>({
    queryKey: ['geo-prov', paisCodigo],
    queryFn: () => api.get('/categorizacion/geo/provincias', { params: { pais_codigo: paisCodigo } }).then((r) => r.data),
    enabled: !!paisCodigo,
  });
  const { data: municipios = [] } = useQuery<Cat[]>({
    queryKey: ['geo-muni', form.provincia_id],
    queryFn: () => api.get('/categorizacion/geo/municipios', { params: { provincia_id: form.provincia_id } }).then((r) => r.data),
    enabled: !!form.provincia_id,
  });
  const { data: centros = [] } = useQuery<Cat[]>({
    queryKey: ['geo-centros', paisCodigo],
    queryFn: () => api.get('/categorizacion/geo/centros', { params: { pais_codigo: paisCodigo } }).then((r) => r.data),
    enabled: !!paisCodigo,
  });
  const nombreDe = (arr: Cat[], id: number | null) => arr.find((x) => x.id === id)?.nombre || '—';

  const refrescar = () => {
    qc.invalidateQueries({ queryKey: ['mm-listar'] });
    qc.invalidateQueries({ queryKey: ['mm-kpis'] });
  };

  const [hist, setHist] = useState<{ medico: MaestroMedico; items: HistorialItem[] } | null>(null);
  const verHistorial = async (m: MaestroMedico) => {
    try { setHist({ medico: m, items: await mmHistorial(m.id) }); }
    catch (e: any) { flash(e?.response?.data?.detail || e?.message || 'No se pudo cargar el historial', 'error'); }
  };

  const exportar = async () => {
    try {
      const blob = await mmExportar({ q: q || undefined, estado: estado || undefined });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url; a.download = 'maestro_medicos.xlsx'; a.click();
      URL.revokeObjectURL(url);
    } catch (e: any) {
      flash(e?.response?.data?.detail || e?.message || 'No se pudo exportar', 'error');
    }
  };

  const abrirCrear = () => { setEditId(null); setForm({ activo: true }); setOpenForm(true); };
  const abrirEditar = (m: MaestroMedico) => {
    setEditId(m.id);
    setForm({ ...m });
    setOpenForm(true);
  };

  const guardar = useMutation({
    mutationFn: async (confirmar: boolean) => {
      if (editId) {
        const { id, pais_codigo, estado_validacion, origen, ...campos } = form as any;
        return mmActualizar(editId, campos);
      }
      if (!paisCodigo) throw new Error('Selecciona un país en la barra superior.');
      return mmCrear({ ...(form as any), pais_codigo: paisCodigo, confirmar_duplicado: confirmar });
    },
    onSuccess: () => { setOpenForm(false); setDupBlando(null); refrescar(); flash(editId ? 'Médico actualizado' : 'Médico creado'); },
    onError: (e: any) => {
      const d = e?.response?.data?.detail;
      if (e?.response?.status === 409 && d?.tipo === 'duro') {
        flash(d.mensaje, 'error');
      } else if (e?.response?.status === 409 && d?.tipo === 'blando') {
        setDupBlando({ mensaje: d.mensaje, coincidencias: d.coincidencias || [] });
      } else {
        flash(d || e?.message || 'Error al guardar', 'error');
      }
    },
  });

  const setF = (k: string, v: any) => setForm((f) => ({ ...f, [k]: v }));

  const listaCoincidencias = (arr: any[]) => (
    <Box component="ul" sx={{ m: 0, pl: 2 }}>
      {arr.map((c, i) => (
        <li key={i}>
          <b>{c.nombre}</b>{c.exequatur ? ` · exeq. ${c.exequatur}` : ''}{c.cedula ? ` · doc. ${c.cedula}` : ''}
        </li>
      ))}
    </Box>
  );

  return (
    <Box>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.t}</Alert>}

      {/* KPI cards */}
      <Grid container spacing={1.5} sx={{ mb: 2 }}>
        {KPIS.map((k) => (
          <Grid item xs={6} md={2.4} key={k.key}>
            <Card elevation={2} sx={{ borderRadius: 2 }}>
              <CardContent sx={{ py: 1.5 }}>
                <Typography variant="h5" fontWeight={800} sx={{ color: k.color }}>
                  {kpis ? (kpis as any)[k.key] : '—'}
                </Typography>
                <Typography variant="caption" color="text.secondary">{k.label}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {/* Barra de acciones + filtros */}
      <Card elevation={2} sx={{ borderRadius: 3 }}>
        <CardContent>
          <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} sx={{ mb: 2 }} alignItems="center">
            <TextField size="small" placeholder="Buscar por nombre, código o documento…"
              value={q} onChange={(e) => setQ(e.target.value)} sx={{ minWidth: 280 }}
              InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }} />
            <TextField size="small" select label="Estado" value={estado}
              onChange={(e) => setEstado(e.target.value)} sx={{ minWidth: 160 }}>
              <MenuItem value="">Todos</MenuItem>
              <MenuItem value="APROBADO">Aprobado</MenuItem>
              <MenuItem value="PENDIENTE">Pendiente validación</MenuItem>
            </TextField>
            <Box sx={{ flex: 1 }} />
            <Tooltip title="Actualizar"><IconButton onClick={refrescar}><RefreshIcon /></IconButton></Tooltip>
            <Button size="small" variant="outlined" startIcon={<UploadFileIcon />}
              disabled={!paisCodigo} onClick={() => setOpenImport(true)}>Importar Excel</Button>
            <Button size="small" variant="outlined" onClick={exportar}>Exportar Excel</Button>
            <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={abrirCrear}>
              Nuevo médico
            </Button>
          </Stack>

          {isLoading ? (
            <Box sx={{ display: 'flex', justifyContent: 'center', my: 4 }}><CircularProgress /></Box>
          ) : (
            <TableContainer component={Paper} elevation={0} sx={{ maxHeight: 520 }}>
              <Table stickyHeader size="small">
                <TableHead>
                  <TableRow>
                    {['Nombre', 'Código', 'Documento', 'Especialidad', 'Provincia', 'Teléfono', 'Estado', ''].map((h) => (
                      <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {medicos.map((m) => (
                    <TableRow key={m.id} hover>
                      <TableCell>{m.nombre}</TableCell>
                      <TableCell>{m.codigo || '—'}</TableCell>
                      <TableCell>{m.cedula || m.exequatur || '—'}</TableCell>
                      <TableCell>{nombreDe(especialidades, m.especialidad_id)}</TableCell>
                      <TableCell>{nombreDe(provincias, m.provincia_id)}</TableCell>
                      <TableCell>{m.telefono || '—'}</TableCell>
                      <TableCell>
                        <Chip size="small" label={m.estado_validacion}
                          color={m.estado_validacion === 'APROBADO' ? 'success' : 'warning'} />
                        {!m.activo && <Chip size="small" label="Inactivo" sx={{ ml: 0.5 }} />}
                      </TableCell>
                      <TableCell align="right" sx={{ whiteSpace: 'nowrap' }}>
                        <Tooltip title="Historial"><IconButton size="small" onClick={() => verHistorial(m)}><HistoryIcon fontSize="small" /></IconButton></Tooltip>
                        <IconButton size="small" onClick={() => abrirEditar(m)}><EditIcon fontSize="small" /></IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                  {medicos.length === 0 && (
                    <TableRow><TableCell colSpan={8} align="center" sx={{ color: 'text.secondary', py: 3 }}>
                      No hay médicos en el maestro que coincidan con el filtro.
                    </TableCell></TableRow>
                  )}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </CardContent>
      </Card>

      {/* Diálogo Crear/Editar */}
      <Dialog open={openForm} onClose={() => setOpenForm(false)} maxWidth="md" fullWidth>
        <DialogTitle>{editId ? 'Editar médico' : 'Nuevo médico'}</DialogTitle>
        <DialogContent>
          <Grid container spacing={2} sx={{ mt: 0.5 }}>
            <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Nombre completo" value={form.nombre || ''} onChange={(e) => setF('nombre', e.target.value)} /></Grid>
            <Grid item xs={12} sm={3}><TextField fullWidth size="small" label="Código" value={form.codigo || ''} onChange={(e) => setF('codigo', e.target.value)} /></Grid>
            <Grid item xs={12} sm={3}><TextField fullWidth size="small" label="Documento / Cédula" value={form.cedula || ''} onChange={(e) => setF('cedula', e.target.value)} /></Grid>
            <Grid item xs={12} sm={3}><TextField fullWidth size="small" label="Exequátur" value={form.exequatur || ''} onChange={(e) => setF('exequatur', e.target.value)} /></Grid>
            <Grid item xs={12} sm={5}>
              <TextField fullWidth size="small" select label="Especialidad" value={form.especialidad_id ?? ''} onChange={(e) => setF('especialidad_id', e.target.value || null)}>
                <MenuItem value=""><em>— Sin especialidad —</em></MenuItem>
                {especialidades.map((x) => <MenuItem key={x.id} value={x.id}>{x.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}><TextField fullWidth size="small" label="Teléfono" value={form.telefono || ''} onChange={(e) => setF('telefono', e.target.value)} /></Grid>
            <Grid item xs={12} sm={6}><TextField fullWidth size="small" label="Email" value={form.email || ''} onChange={(e) => setF('email', e.target.value)} /></Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" select label="Centro médico" value={form.centro_medico_id ?? ''} onChange={(e) => setF('centro_medico_id', e.target.value || null)}>
                <MenuItem value=""><em>— Sin centro —</em></MenuItem>
                {centros.map((x) => <MenuItem key={x.id} value={x.id}>{x.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField fullWidth size="small" select label="Provincia" value={form.provincia_id ?? ''} onChange={(e) => setF('provincia_id', e.target.value || null)}>
                <MenuItem value=""><em>— Sin provincia —</em></MenuItem>
                {provincias.map((x) => <MenuItem key={x.id} value={x.id}>{x.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField fullWidth size="small" select label="Municipio" value={form.municipio_id ?? ''} onChange={(e) => setF('municipio_id', e.target.value || null)} disabled={!form.provincia_id}>
                <MenuItem value=""><em>— Sin municipio —</em></MenuItem>
                {municipios.map((x) => <MenuItem key={x.id} value={x.id}>{x.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}><TextField fullWidth size="small" label="Sector" value={form.sector || ''} onChange={(e) => setF('sector', e.target.value)} /></Grid>
            <Grid item xs={12}><TextField fullWidth size="small" label="Dirección" value={form.direccion || ''} onChange={(e) => setF('direccion', e.target.value)} /></Grid>
            <Grid item xs={12}><TextField fullWidth size="small" label="Observaciones" multiline minRows={2} value={form.observaciones || ''} onChange={(e) => setF('observaciones', e.target.value)} /></Grid>
            <Grid item xs={12}>
              <TextField fullWidth size="small" select label="Estado" value={form.activo === false ? '0' : '1'} onChange={(e) => setF('activo', e.target.value === '1')}>
                <MenuItem value="1">Activo</MenuItem>
                <MenuItem value="0">Inactivo</MenuItem>
              </TextField>
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenForm(false)}>Cancelar</Button>
          <Button variant="contained" disabled={guardar.isPending || !(form.nombre || '').trim()}
            onClick={() => guardar.mutate(false)}>
            {guardar.isPending ? <CircularProgress size={18} /> : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirmación de duplicado BLANDO */}
      <Dialog open={!!dupBlando} onClose={() => setDupBlando(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Posible médico duplicado</DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>{dupBlando?.mensaje}</Alert>
          <Typography variant="body2" sx={{ mb: 1 }}>Coincidencias encontradas:</Typography>
          {dupBlando && listaCoincidencias(dupBlando.coincidencias)}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDupBlando(null)}>El médico ya existe (cancelar)</Button>
          <Button color="warning" variant="contained" disabled={guardar.isPending}
            onClick={() => guardar.mutate(true)}>
            Crear de todas formas
          </Button>
        </DialogActions>
      </Dialog>

      {/* Importación Excel — Stepper */}
      <Dialog open={openImport} onClose={cerrarImport} maxWidth="sm" fullWidth>
        <DialogTitle>Importar Maestro de Médicos ({paisCodigo})</DialogTitle>
        <DialogContent>
          <Stepper activeStep={impPaso} sx={{ my: 2 }}>
            <Step><StepLabel>Archivo</StepLabel></Step>
            <Step><StepLabel>Previsualizar</StepLabel></Step>
            <Step><StepLabel>Resultado</StepLabel></Step>
          </Stepper>

          {impPaso === 0 && (
            <Box>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Sube un .xlsx con al menos la columna <b>nombre</b>. Columnas reconocidas:
                codigo, cedula, exequatur, telefono, email, direccion, sector, observaciones,
                especialidad_id, provincia_id, municipio_id, centro_medico_id.
              </Typography>
              <Button variant="outlined" component="label" startIcon={<UploadFileIcon />}>
                {impFile ? impFile.name : 'Seleccionar archivo .xlsx'}
                <input hidden type="file" accept=".xlsx"
                  onChange={(e) => setImpFile(e.target.files?.[0] || null)} />
              </Button>
            </Box>
          )}

          {impPaso === 1 && impPreview && (
            <Box>
              <Alert severity="info" sx={{ mb: 1.5 }}>
                {impPreview.filas} filas · <b>{impPreview.nuevos}</b> nuevos ·{' '}
                <b>{impPreview.actualizados}</b> actualizados ·{' '}
                <b>{impPreview.posibles_duplicados}</b> posibles duplicados ·{' '}
                <b>{impPreview.errores}</b> con error.
              </Alert>
              {impPreview.detalle_errores.length > 0 && (
                <Box component="ul" sx={{ m: 0, pl: 2, maxHeight: 160, overflow: 'auto' }}>
                  {impPreview.detalle_errores.map((e, i) => (
                    <li key={i}>Fila {e.fila}: {e.error}</li>
                  ))}
                </Box>
              )}
            </Box>
          )}

          {impPaso === 2 && impResultado && (
            <Alert severity="success">
              Importación completada — <b>{impResultado.creados}</b> creados,{' '}
              <b>{impResultado.actualizados}</b> actualizados,{' '}
              <b>{impResultado.duplicados_marcados}</b> marcados como posible duplicado,{' '}
              <b>{impResultado.errores.length}</b> con error.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrarImport}>{impPaso === 2 ? 'Cerrar' : 'Cancelar'}</Button>
          {impPaso === 0 && (
            <Button variant="contained" disabled={!impFile || impBusy} onClick={previsualizar}>
              {impBusy ? <CircularProgress size={18} /> : 'Previsualizar'}
            </Button>
          )}
          {impPaso === 1 && (
            <Button variant="contained" color="warning" disabled={impBusy} onClick={ejecutarImport}>
              {impBusy ? <CircularProgress size={18} /> : 'Confirmar importación'}
            </Button>
          )}
        </DialogActions>
      </Dialog>

      {/* Historial de cambios */}
      <Dialog open={!!hist} onClose={() => setHist(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Historial — {hist?.medico.nombre}</DialogTitle>
        <DialogContent dividers>
          {hist && hist.items.length === 0 && (
            <Typography variant="body2" color="text.secondary">Sin registros de cambios.</Typography>
          )}
          {hist?.items.map((h, i) => (
            <Box key={i} sx={{ mb: 1, pb: 1, borderBottom: '1px solid #eee' }}>
              <Typography variant="caption" color="text.secondary">
                {h.fecha ? new Date(h.fecha).toLocaleString() : '—'} · {h.usuario}
              </Typography>
              <Typography variant="body2"><b>{h.accion}</b>{h.detalle ? ` — ${h.detalle}` : ''}</Typography>
            </Box>
          ))}
        </DialogContent>
        <DialogActions><Button onClick={() => setHist(null)}>Cerrar</Button></DialogActions>
      </Dialog>
    </Box>
  );
}
