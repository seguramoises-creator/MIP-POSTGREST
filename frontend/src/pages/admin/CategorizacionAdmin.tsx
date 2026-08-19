/**
 * CategorizacionAdmin.tsx
 * Tab de administración del módulo de Categorización Médica.
 * Tabs:
 *   0 — Carga de Excel (historial de lotes)
 *   1 — Clasificación A/B/C/D (DimClasificacionMedica)
 *   2 — Componentes y Reglas (DimComponenteCategoria + DimReglaCategoriaMedica)
 */
import { useState } from 'react';
import {
  Box, Button, Typography, Alert, LinearProgress, Paper, Stack,
  Table, TableHead, TableBody, TableRow, TableCell,
  Chip, Stepper, Step, StepLabel, Divider,
  FormControl, InputLabel, Select, MenuItem, Tabs, Tab,
  TextField, IconButton, Tooltip, Dialog, DialogTitle,
  DialogContent, DialogActions, Grid,
} from '@mui/material';
import UploadFileIcon from '@mui/icons-material/UploadFile';
import CheckCircleOutlineIcon from '@mui/icons-material/CheckCircleOutline';
import EditIcon from '@mui/icons-material/Edit';
import AddIcon from '@mui/icons-material/Add';
import DeleteIcon from '@mui/icons-material/Delete';
import Block from '@mui/icons-material/Block';
import SaveIcon from '@mui/icons-material/Save';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

// ── Tipos ─────────────────────────────────────────────────────────────────────
interface Ciclo { id: number; nombre: string; pais_codigo: string; anio: number; numero: number; cerrado: boolean; }
interface Lote { LoadBatchKey: number; Periodo: string; ArchivoOrigen: string; FechaCargaUtc: string; UsuarioCarga: string; Estado: string; Mensaje: string | null; TotalMedicos: number; }
interface ResultadoCarga { load_batch_key: number; estado: string; filas_cargadas: number; total_medicos: number; categoria_a: number; categoria_b: number; categoria_c: number; categoria_d: number; conciliacion_ok: number; conciliacion_diferencia: number; }
interface Clasificacion { ClasificacionKey: number; CodigoPais: string; Clase: string; PuntajeMinPct: number; PuntajeMaxPct: number; Activo: boolean; VigenteDesde: string | null; VigenteHasta: string | null; }
interface Componente { ComponenteKey: number; CodigoComponente: string; NombreComponente: string; TipoEvaluacion: string; PesoComponentePct: number; PesoPct: number; Requerido: boolean; Activo: boolean; }
interface Regla { ReglaKey: number; CodigoComponente: string; NombreComponente: string; CodigoRegla: string; ValorMinimo: number | null; ValorMaximo: number | null; ValorTexto: string | null; Criterio: number; PuntajePct: number; PuntajePctDisplay: number; Activo: boolean; CodigoPais: string; }

const STEPS = ['Seleccionar archivo', 'Seleccionar ciclo', 'Cargar y calcular'];
const CLASE_COLORS: Record<string, string> = { A: '#1b5e20', B: '#1565c0', C: '#e65100', D: '#6a1b9a' };

// ── Sub-componente: Pestaña Carga Excel ───────────────────────────────────────
function TabCarga() {
  const qc = useQueryClient();
  const [step, setStep] = useState(0);
  const [archivo, setArchivo] = useState<File | null>(null);
  const [periodo, setPeriodo] = useState('');
  const [resultado, setResultado] = useState<ResultadoCarga | null>(null);
  const [error, setError] = useState('');

  const { data: ciclos = [] } = useQuery<Ciclo[]>({ queryKey: ['ciclos-cat'], queryFn: async () => (await api.get('/admin/ciclos')).data });
  const { data: lotes = [], isLoading: loadingLotes } = useQuery<Lote[]>({ queryKey: ['cat-lotes'], queryFn: async () => (await api.get('/categorizacion/lotes?limit=20')).data });

  const mutation = useMutation({
    mutationFn: async () => {
      if (!archivo || !periodo) throw new Error('Faltan datos');
      const fd = new FormData();
      fd.append('archivo', archivo);
      fd.append('periodo', periodo);
      return (await api.post('/categorizacion/cargar', fd, { headers: { 'Content-Type': 'multipart/form-data' }, timeout: 300_000 })).data as ResultadoCarga;
    },
    onSuccess: (data) => { setResultado(data); setStep(3); qc.invalidateQueries({ queryKey: ['cat-lotes'] }); qc.invalidateQueries({ queryKey: ['cat-resumen'] }); },
    onError: (err: any) => {
      const detail = err.response?.data?.detail;
      const detailStr = Array.isArray(detail) ? detail.map((d: any) => `[${(d.loc || []).join('.')}] ${d.msg}`).join(' | ') : typeof detail === 'string' ? detail : detail ? JSON.stringify(detail) : null;
      setError(detailStr || err.response?.data ? JSON.stringify(err.response?.data) : err.message || 'Error desconocido');
    },
  });

  const estadoColor = (e: string) => e === 'CALCULADO' || e === 'EXITOSO' ? 'success' : e === 'ERROR' ? 'error' : 'default';
  const reset = () => { setStep(0); setArchivo(null); setPeriodo(''); setResultado(null); setError(''); };

  return (
    <Box>
      {step < 3 && (
        <Paper variant="outlined" sx={{ p: 3, mb: 4 }}>
          <Stepper activeStep={step} sx={{ mb: 4 }}>
            {STEPS.map((s) => <Step key={s}><StepLabel>{s}</StepLabel></Step>)}
          </Stepper>
          {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

          {step === 0 && (
            <Box textAlign="center" py={2}>
              <Button component="label" variant="outlined" size="large" startIcon={<UploadFileIcon />} sx={{ mb: 2 }}>
                {archivo ? archivo.name : 'Seleccionar archivo .xlsx'}
                <input type="file" accept=".xlsx" hidden onChange={(e) => { setArchivo(e.target.files?.[0] || null); setError(''); }} />
              </Button>
              {archivo && <Typography variant="body2" color="text.secondary">{(archivo.size / 1024 / 1024).toFixed(2)} MB</Typography>}
              <Box mt={3}><Button variant="contained" disabled={!archivo} onClick={() => setStep(1)}>Siguiente</Button></Box>
            </Box>
          )}

          {step === 1 && (
            <Box maxWidth={360} mx="auto" py={2}>
              <FormControl fullWidth sx={{ mb: 3 }}>
                <InputLabel>Ciclo</InputLabel>
                <Select value={periodo} label="Ciclo" onChange={(e) => setPeriodo(e.target.value)}>
                  {Array.from(new Map(ciclos.map(c => [c.nombre, c])).values()).sort((a, b) => a.nombre.localeCompare(b.nombre)).map((c) => (
                    <MenuItem key={c.nombre} value={c.nombre}>
                      {c.nombre}{!c.cerrado && <Chip label="Activo" size="small" color="success" sx={{ ml: 1 }} />}
                    </MenuItem>
                  ))}
                </Select>
              </FormControl>
              <Box display="flex" gap={1}>
                <Button variant="outlined" onClick={() => setStep(0)}>Atrás</Button>
                <Button variant="contained" disabled={!periodo} onClick={() => setStep(2)}>Siguiente</Button>
              </Box>
            </Box>
          )}

          {step === 2 && (
            <Box py={2}>
              <Paper variant="outlined" sx={{ p: 2, mb: 3, bgcolor: 'grey.50' }}>
                <Typography variant="body2"><b>Archivo:</b> {archivo?.name}</Typography>
                <Typography variant="body2"><b>Ciclo:</b> {periodo}</Typography>
                <Typography variant="body2"><b>Tamaño:</b> {((archivo?.size || 0) / 1024 / 1024).toFixed(2)} MB</Typography>
              </Paper>
              {mutation.isPending && <Box mb={2}><Typography variant="body2" color="text.secondary" mb={1}>Procesando…</Typography><LinearProgress /></Box>}
              <Box display="flex" gap={1}>
                <Button variant="outlined" onClick={() => setStep(1)} disabled={mutation.isPending}>Atrás</Button>
                <Button variant="contained" color="success" disabled={mutation.isPending} onClick={() => mutation.mutate()}>Cargar y Calcular</Button>
              </Box>
            </Box>
          )}
        </Paper>
      )}

      {step === 3 && resultado && (
        <Paper variant="outlined" sx={{ p: 3, mb: 4, borderColor: 'success.main' }}>
          <Box display="flex" alignItems="center" gap={1} mb={2}>
            <CheckCircleOutlineIcon color="success" />
            <Typography variant="h6" color="success.main" fontWeight={700}>Carga completada — {resultado.total_medicos} médicos procesados</Typography>
          </Box>
          <Divider sx={{ mb: 2 }} />
          <Box display="flex" flexWrap="wrap" gap={2} mb={2}>
            {[{ label: 'A', value: resultado.categoria_a }, { label: 'B', value: resultado.categoria_b }, { label: 'C', value: resultado.categoria_c }, { label: 'D', value: resultado.categoria_d }].map((c) => (
              <Box key={c.label} sx={{ textAlign: 'center', p: 1.5, border: 1, borderColor: 'divider', borderRadius: 2, minWidth: 80 }}>
                <Typography variant="h5" fontWeight={700} color={CLASE_COLORS[c.label]}>{c.value}</Typography>
                <Typography variant="caption">Cat. {c.label}</Typography>
              </Box>
            ))}
          </Box>
          <Typography variant="body2" color="text.secondary">Conciliación OK: <b>{resultado.conciliacion_ok}</b> · Diferencias: <b>{resultado.conciliacion_diferencia}</b></Typography>
          <Box mt={2}><Button variant="outlined" onClick={reset}>Nueva carga</Button></Box>
        </Paper>
      )}

      <Typography variant="subtitle1" fontWeight={600} mb={1}>Historial de cargas recientes</Typography>
      {loadingLotes ? <LinearProgress /> : (
        <Paper variant="outlined">
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: 'grey.50' }}>
                <TableCell><b>Lote</b></TableCell><TableCell><b>Período</b></TableCell>
                <TableCell><b>Fecha carga</b></TableCell><TableCell><b>Usuario</b></TableCell>
                <TableCell><b>Médicos</b></TableCell><TableCell><b>Estado</b></TableCell><TableCell><b>Mensaje</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {lotes.length === 0 && (
                <TableRow><TableCell colSpan={7} align="center">Sin cargas registradas</TableCell></TableRow>
              )}
              {lotes.map((l) => (
                <TableRow key={l.LoadBatchKey} hover>
                  <TableCell>{l.LoadBatchKey}</TableCell>
                  <TableCell>{l.Periodo}</TableCell>
                  <TableCell>{new Date(l.FechaCargaUtc).toLocaleString('es-DO')}</TableCell>
                  <TableCell>{l.UsuarioCarga}</TableCell>
                  <TableCell>{l.TotalMedicos}</TableCell>
                  <TableCell><Chip label={l.Estado} size="small" color={estadoColor(l.Estado) as any} /></TableCell>
                  <TableCell sx={{ maxWidth: 200, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{l.Mensaje || '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}
    </Box>
  );
}

// ── Sub-componente: Pestaña Clasificación A/B/C/D ─────────────────────────────
function TabClasificacion() {
  const qc = useQueryClient();
  const [editRow, setEditRow] = useState<Clasificacion | null>(null);
  const [open, setOpen] = useState(false);
  const { data: rows = [], isLoading } = useQuery<Clasificacion[]>({ queryKey: ['cat-clasificacion'], queryFn: async () => (await api.get('/categorizacion/params/clasificacion')).data });
  const { data: paises = [] } = useQuery<string[]>({ queryKey: ['cat-paises'], queryFn: async () => (await api.get('/categorizacion/params/paises')).data });

  const mut = useMutation({
    mutationFn: async (body: any) => (await api.put('/categorizacion/params/clasificacion', body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cat-clasificacion'] });
      setOpen(false);
      setEditRow(null);
    },
  });

  const openEdit = (r: Clasificacion) => { setEditRow({ ...r }); setOpen(true); };
  const openNew = () => {
    setEditRow({ ClasificacionKey: 0, CodigoPais: paises[0] || '', Clase: 'A', PuntajeMinPct: 0, PuntajeMaxPct: 1, Activo: true, VigenteDesde: null, VigenteHasta: null });
    setOpen(true);
  };

  return (
    <Box>
      <Box display="flex" justifyContent="space-between" alignItems="center" mb={2}>
        <Typography variant="subtitle1" fontWeight={600}>Rangos de Clasificación Médica (A/B/C/D)</Typography>
        <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={openNew}>Nuevo rango</Button>
      </Box>
      {isLoading && <LinearProgress />}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: '#686158' }}>
              {['País','Clase','Puntaje Mín','Puntaje Máx','Activo','Vigente Desde','Vigente Hasta',''].map(h => (
                <TableCell key={h} sx={{ color: '#fff', fontWeight: 700, fontSize: '0.78rem' }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {rows.map((r) => (
              <TableRow key={r.ClasificacionKey} hover>
                <TableCell>{r.CodigoPais}</TableCell>
                <TableCell>
                  <Chip label={r.Clase} size="small" sx={{ bgcolor: CLASE_COLORS[r.Clase], color: '#fff', fontWeight: 700 }} />
                </TableCell>
                <TableCell>{(r.PuntajeMinPct * 100).toFixed(0)}%</TableCell>
                <TableCell>{(r.PuntajeMaxPct * 100).toFixed(0)}%</TableCell>
                <TableCell>
                  <Chip label={r.Activo ? 'Activo' : 'Inactivo'} size="small" color={r.Activo ? 'success' : 'default'} />
                </TableCell>
                <TableCell>{r.VigenteDesde || '—'}</TableCell>
                <TableCell>{r.VigenteHasta || '—'}</TableCell>
                <TableCell>
                  <Tooltip title="Editar">
                    <IconButton size="small" onClick={() => openEdit(r)}><EditIcon fontSize="small" /></IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={open} onClose={() => setOpen(false)} maxWidth="xs" fullWidth>
        <DialogTitle>{editRow?.ClasificacionKey ? 'Editar Clasificación' : 'Nueva Clasificación'}</DialogTitle>
        <DialogContent>
          {editRow && (
            <Box display="flex" flexDirection="column" gap={2} pt={1}>
              {!editRow.ClasificacionKey && (
                <>
                  <FormControl fullWidth size="small">
                    <InputLabel>País</InputLabel>
                    <Select value={editRow.CodigoPais} label="País"
                      onChange={(e) => setEditRow({ ...editRow, CodigoPais: e.target.value })}>
                      {paises.map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                    </Select>
                  </FormControl>
                  <FormControl fullWidth size="small">
                    <InputLabel>Clase</InputLabel>
                    <Select value={editRow.Clase} label="Clase"
                      onChange={(e) => setEditRow({ ...editRow, Clase: e.target.value })}>
                      {['A','B','C','D'].map(c => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                    </Select>
                  </FormControl>
                </>
              )}
              <TextField size="small" label="Puntaje Mínimo (0-1)" type="number"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={editRow.PuntajeMinPct}
                onChange={(e) => setEditRow({ ...editRow, PuntajeMinPct: parseFloat(e.target.value) })} />
              <TextField size="small" label="Puntaje Máximo (0-1)" type="number"
                inputProps={{ step: 0.01, min: 0, max: 1 }}
                value={editRow.PuntajeMaxPct}
                onChange={(e) => setEditRow({ ...editRow, PuntajeMaxPct: parseFloat(e.target.value) })} />
              <TextField size="small" label="Vigente Desde (YYYY-MM-DD)"
                value={editRow.VigenteDesde || ''}
                onChange={(e) => setEditRow({ ...editRow, VigenteDesde: e.target.value || null })} />
              <TextField size="small" label="Vigente Hasta (vacío = sin fin)"
                value={editRow.VigenteHasta || ''}
                onChange={(e) => setEditRow({ ...editRow, VigenteHasta: e.target.value || null })} />
            </Box>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpen(false)}>Cancelar</Button>
          <Button variant="contained" startIcon={<SaveIcon />}
            onClick={() => editRow && mut.mutate(editRow)} disabled={mut.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Sub-componente: Pestaña Reglas por Componente ────────────────────────────
function TabReglas() {
  const qc = useQueryClient();
  const [selComp, setSelComp] = useState('');
  const [editRegla, setEditRegla] = useState<Partial<Regla> & { CodigoRegla?: string } | null>(null);
  const [openDlg, setOpenDlg] = useState(false);
  const [editPeso, setEditPeso] = useState<{ key: number; peso: string } | null>(null);

  const { data: paises = [] } = useQuery<string[]>({
    queryKey: ['cat-paises'],
    queryFn: async () => (await api.get('/categorizacion/params/paises')).data,
  });

  const { data: componentes = [] } = useQuery<Componente[]>({
    queryKey: ['cat-componentes'],
    queryFn: async () => (await api.get('/categorizacion/componentes')).data,
  });

  const { data: reglas = [], isLoading } = useQuery<Regla[]>({
    queryKey: ['cat-reglas', selComp],
    queryFn: async () => {
      const qs = selComp ? `?componente=${selComp}` : '';
      return (await api.get(`/categorizacion/params/reglas${qs}`)).data;
    },
  });

  const mutPeso = useMutation({
    mutationFn: async ({ key, peso }: { key: number; peso: string }) => {
      return (await api.put(`/categorizacion/params/componentes/${key}`, { PesoPct: parseFloat(peso) })).data;
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cat-componentes'] });
      setEditPeso(null);
    },
  });

  const mutRegla = useMutation({
    mutationFn: async (body: any) => (await api.put('/categorizacion/params/reglas', body)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cat-reglas', selComp] });
      setOpenDlg(false);
      setEditRegla(null);
    },
  });

  const mutDel = useMutation({
    mutationFn: async (key: number) => (await api.delete(`/categorizacion/params/reglas/${key}`)).data,
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['cat-reglas', selComp] });
    },
  });

  const openEdit = (r: Regla) => {
    setEditRegla({ ...r, PuntajePct: r.PuntajePctDisplay });
    setOpenDlg(true);
  };
  const openNew = () => {
    const firstComp = componentes[0]?.CodigoComponente || '';
    setEditRegla({
      ReglaKey: 0,
      CodigoComponente: selComp || firstComp,
      CodigoPais: paises[0] || '',
      Criterio: 1,
      PuntajePct: 0,
      Activo: true,
      CodigoRegla: '',
    });
    setOpenDlg(true);
  };

  const tipoComp = (cod: string) => {
    const c = componentes.find(x => x.CodigoComponente === cod);
    return c?.TipoEvaluacion || 'NUMERICO';
  };

  const activeReglas = reglas.filter(r => r.Activo);

  return (
    <Box>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>Pesos por Componente</Typography>
      <Paper variant="outlined" sx={{ mb: 3 }}>
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: '#686158' }}>
              {['Componente','Tipo','Peso (%)',''].map(h => (
                <TableCell key={h} sx={{ color: '#fff', fontWeight: 700, fontSize: '0.78rem' }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {componentes.map((c) => (
              <TableRow key={c.ComponenteKey} hover>
                <TableCell sx={{ fontWeight: 600 }}>{c.NombreComponente}</TableCell>
                <TableCell><Chip label={c.TipoEvaluacion} size="small" variant="outlined" /></TableCell>
                <TableCell>
                  {editPeso?.key === c.ComponenteKey ? (
                    <Box display="flex" alignItems="center" gap={1}>
                      <TextField size="small" type="number" value={editPeso.peso} sx={{ width: 80 }}
                        inputProps={{ step: 1, min: 0, max: 100 }}
                        onChange={(e) => setEditPeso({ ...editPeso, peso: e.target.value })} />
                      <Button size="small" variant="contained"
                        onClick={() => mutPeso.mutate({ key: c.ComponenteKey, peso: editPeso.peso })}>
                        OK
                      </Button>
                      <Button size="small" onClick={() => setEditPeso(null)}>✕</Button>
                    </Box>
                  ) : (
                    <Box display="flex" alignItems="center" gap={1}>
                      <Typography fontWeight={700} color="primary">{c.PesoPct}%</Typography>
                      <Tooltip title="Editar peso">
                        <IconButton size="small"
                          onClick={() => setEditPeso({ key: c.ComponenteKey, peso: String(c.PesoPct) })}>
                          <EditIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </Box>
                  )}
                </TableCell>
                <TableCell>
                  <Button size="small"
                    variant={selComp === c.CodigoComponente ? 'contained' : 'outlined'}
                    onClick={() => setSelComp(selComp === c.CodigoComponente ? '' : c.CodigoComponente)}>
                    Ver reglas
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      <Box display="flex" justifyContent="space-between" alignItems="center" mb={1}>
        <Typography variant="subtitle1" fontWeight={700}>
          {selComp
            ? `Reglas — ${componentes.find(c => c.CodigoComponente === selComp)?.NombreComponente}`
            : 'Reglas (todos los componentes)'}
        </Typography>
        <Button size="small" variant="contained" startIcon={<AddIcon />} onClick={openNew} disabled={!selComp}>
          Nueva regla
        </Button>
      </Box>
      {isLoading && <LinearProgress />}
      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow sx={{ bgcolor: '#686158' }}>
              {['Componente','Criterio','Valor Texto','Mín','Máx','Puntaje %','País','Activo',''].map(h => (
                <TableCell key={h} sx={{ color: '#fff', fontWeight: 700, fontSize: '0.78rem' }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {activeReglas.map((r) => (
              <TableRow key={r.ReglaKey} hover>
                <TableCell sx={{ fontSize: '0.78rem' }}>{r.NombreComponente}</TableCell>
                <TableCell align="center">{r.Criterio}</TableCell>
                <TableCell>{r.ValorTexto || '—'}</TableCell>
                <TableCell align="right">{r.ValorMinimo ?? '—'}</TableCell>
                <TableCell align="right">{r.ValorMaximo ?? '—'}</TableCell>
                <TableCell align="center" sx={{ fontWeight: 700, color: '#1565c0' }}>
                  {r.PuntajePctDisplay}%
                </TableCell>
                <TableCell>{r.CodigoPais}</TableCell>
                <TableCell><Chip label="Activo" size="small" color="success" /></TableCell>
                <TableCell>
                  <Tooltip title="Editar">
                    <IconButton size="small" onClick={() => openEdit(r)}><EditIcon fontSize="small" /></IconButton>
                  </Tooltip>
                  <Tooltip title="Desactivar">
                    <IconButton size="small" color="error" onClick={() => mutDel.mutate(r.ReglaKey)}>
                      <DeleteIcon fontSize="small" />
                    </IconButton>
                  </Tooltip>
                </TableCell>
              </TableRow>
            ))}
            {activeReglas.length === 0 && (
              <TableRow>
                <TableCell colSpan={9} align="center" sx={{ py: 3, color: 'text.secondary' }}>
                  {selComp ? 'Sin reglas para este componente' : 'Selecciona un componente para ver sus reglas'}
                </TableCell>
              </TableRow>
            )}
          </TableBody>
        </Table>
      </Paper>

      <Dialog open={openDlg} onClose={() => setOpenDlg(false)} maxWidth="sm" fullWidth>
        <DialogTitle>{editRegla?.ReglaKey ? 'Editar Regla' : 'Nueva Regla'}</DialogTitle>
        <DialogContent>
          {editRegla && (
            <Grid container spacing={2} pt={1}>
              {!editRegla.ReglaKey && (
                <>
                  <Grid item xs={6}>
                    <FormControl fullWidth size="small">
                      <InputLabel>Componente</InputLabel>
                      <Select value={editRegla.CodigoComponente || ''} label="Componente"
                        onChange={(e) => setEditRegla({ ...editRegla, CodigoComponente: e.target.value })}>
                        {componentes.map(c => (
                          <MenuItem key={c.CodigoComponente} value={c.CodigoComponente}>
                            {c.NombreComponente}
                          </MenuItem>
                        ))}
                      </Select>
                    </FormControl>
                  </Grid>
                  <Grid item xs={6}>
                    <FormControl fullWidth size="small">
                      <InputLabel>País</InputLabel>
                      <Select value={editRegla.CodigoPais || ''} label="País"
                        onChange={(e) => setEditRegla({ ...editRegla, CodigoPais: e.target.value })}>
                        {paises.map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
                      </Select>
                    </FormControl>
                  </Grid>
                </>
              )}
              <Grid item xs={6}>
                <TextField fullWidth size="small" label="Criterio (orden)" type="number"
                  value={editRegla.Criterio || 1}
                  onChange={(e) => setEditRegla({ ...editRegla, Criterio: parseInt(e.target.value) })} />
              </Grid>
              <Grid item xs={6}>
                <TextField fullWidth size="small" label="Puntaje %" type="number"
                  inputProps={{ step: 0.5, min: 0, max: 100 }}
                  value={editRegla.PuntajePct || 0}
                  onChange={(e) => setEditRegla({ ...editRegla, PuntajePct: parseFloat(e.target.value) })} />
              </Grid>
              {tipoComp(editRegla.CodigoComponente || '') === 'TEXTO' ? (
                <Grid item xs={12}>
                  <TextField fullWidth size="small" label="Valor Texto (exacto)"
                    value={editRegla.ValorTexto || ''}
                    onChange={(e) => setEditRegla({ ...editRegla, ValorTexto: e.target.value })} />
                </Grid>
              ) : (
                <>
                  <Grid item xs={6}>
                    <TextField fullWidth size="small" label="Valor Mínimo" type="number"
                      value={editRegla.ValorMinimo ?? ''}
                      onChange={(e) => setEditRegla({
                        ...editRegla,
                        ValorMinimo: e.target.value ? parseFloat(e.target.value) : null,
                      })} />
                  </Grid>
                  <Grid item xs={6}>
                    <TextField fullWidth size="small" label="Valor Máximo" type="number"
                      value={editRegla.ValorMaximo ?? ''}
                      onChange={(e) => setEditRegla({
                        ...editRegla,
                        ValorMaximo: e.target.value ? parseFloat(e.target.value) : null,
                      })} />
                  </Grid>
                </>
              )}
              <Grid item xs={12}>
                <TextField fullWidth size="small" label="Código Regla (referencia)"
                  value={editRegla.CodigoRegla || ''}
                  onChange={(e) => setEditRegla({ ...editRegla, CodigoRegla: e.target.value })} />
              </Grid>
            </Grid>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setOpenDlg(false)}>Cancelar</Button>
          <Button variant="contained" startIcon={<SaveIcon />}
            onClick={() => editRegla && mutRegla.mutate(editRegla)} disabled={mutRegla.isPending}>
            Guardar
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Componente principal ───────────────────────────────────────────────────────
// ── Sub-componente: Catálogos geográficos (Especialidad / Provincia / Municipio / Centro) ──
interface Pais { id: number; codigo: string; nombre: string; }
interface GeoItem { id: number; nombre: string; pais_codigo?: string; provincia_id?: number; activo?: boolean; }

type GeoTipo = 'especialidad' | 'provincia' | 'municipio' | 'centro';
const GEO_LABEL: Record<GeoTipo, string> = {
  especialidad: 'Especialidades', centro: 'Centros médicos', provincia: 'Provincias', municipio: 'Municipios',
};

export function TabGeo({ tipos = ['especialidad', 'provincia', 'municipio', 'centro'] }: { tipos?: GeoTipo[] }) {
  const qc = useQueryClient();
  const [cat, setCat] = useState<GeoTipo>(tipos[0]);
  const [pais, setPais] = useState('');
  const [editId, setEditId] = useState<number | null>(null);
  const [editNombre, setEditNombre] = useState('');
  const [provinciaId, setProvinciaId] = useState<number | ''>('');
  const [nombre, setNombre] = useState('');
  const [error, setError] = useState('');

  const { data: paises = [] } = useQuery<Pais[]>({ queryKey: ['geo-paises'], queryFn: async () => (await api.get('/admin/paises')).data });
  const { data: provincias = [] } = useQuery<GeoItem[]>({
    queryKey: ['geo-prov', pais], queryFn: async () => (await api.get('/categorizacion/geo/provincias', { params: pais ? { pais_codigo: pais } : {} })).data,
  });
  const necesitaPais = cat === 'provincia' || cat === 'centro';
  const necesitaProv = cat === 'municipio';

  // En el admin se muestran también los inactivos (para poder reactivarlos).
  const { data: items = [], isLoading } = useQuery<GeoItem[]>({
    queryKey: ['geo-items', cat, pais, provinciaId],
    queryFn: async () => {
      const inc = { incluir_inactivos: true };
      if (cat === 'especialidad') return (await api.get('/categorizacion/geo/especialidades', { params: inc })).data;
      if (cat === 'provincia') return (await api.get('/categorizacion/geo/provincias', { params: { ...inc, ...(pais ? { pais_codigo: pais } : {}) } })).data;
      if (cat === 'centro') return (await api.get('/categorizacion/geo/centros', { params: { ...inc, ...(pais ? { pais_codigo: pais } : {}) } })).data;
      if (!provinciaId) return [];
      return (await api.get('/categorizacion/geo/municipios', { params: { ...inc, provincia_id: provinciaId } })).data;
    },
  });

  const crear = useMutation({
    mutationFn: async () => {
      setError('');
      if (cat === 'especialidad') return api.post('/categorizacion/geo/especialidades', { nombre });
      if (cat === 'provincia') return api.post('/categorizacion/geo/provincias', { pais_codigo: pais, nombre });
      if (cat === 'centro') return api.post('/categorizacion/geo/centros', { pais_codigo: pais, nombre });
      return api.post('/categorizacion/geo/municipios', { provincia_id: provinciaId, nombre });
    },
    onSuccess: () => { setNombre(''); qc.invalidateQueries({ queryKey: ['geo-items'] }); qc.invalidateQueries({ queryKey: ['geo-prov'] }); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'No se pudo crear'),
  });
  const toggleActivo = useMutation({
    mutationFn: async ({ id, activo }: { id: number; activo: boolean }) =>
      api.patch(`/categorizacion/geo/${cat}/${id}`, { activo }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['geo-items'] }); qc.invalidateQueries({ queryKey: ['geo-prov'] }); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'No se pudo actualizar'),
  });
  const borrar = useMutation({
    mutationFn: async (id: number) => api.delete(`/categorizacion/geo/${cat}/${id}`, { params: { permanente: true } }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['geo-items'] }); qc.invalidateQueries({ queryKey: ['geo-prov'] }); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'No se pudo borrar'),
  });
  const renombrar = useMutation({
    mutationFn: async () => api.patch(`/categorizacion/geo/${cat}/${editId}`, { nombre: editNombre }),
    onSuccess: () => { setEditId(null); setEditNombre(''); qc.invalidateQueries({ queryKey: ['geo-items'] }); qc.invalidateQueries({ queryKey: ['geo-prov'] }); },
    onError: (e: any) => setError(e?.response?.data?.detail ?? 'No se pudo renombrar'),
  });

  const puedeCrear = nombre.trim().length >= 2 && (!necesitaPais || !!pais) && (!necesitaProv || !!provinciaId);

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Mantenimiento de catálogos usados como listas desplegables en el maestro de médicos
        (Panel Médico). La baja es lógica (no borra el histórico).
      </Typography>
      <Grid container spacing={1.5} alignItems="center" sx={{ mb: 2 }}>
        <Grid item xs={12} sm={3}>
          <FormControl size="small" fullWidth>
            <InputLabel>Catálogo</InputLabel>
            <Select label="Catálogo" value={cat} onChange={(e) => { setCat(e.target.value as GeoTipo); setProvinciaId(''); }}>
              {tipos.map((t) => <MenuItem key={t} value={t}>{GEO_LABEL[t]}</MenuItem>)}
            </Select>
          </FormControl>
        </Grid>
        {(necesitaPais || cat === 'municipio') && (
          <Grid item xs={12} sm={3}>
            <FormControl size="small" fullWidth>
              <InputLabel>País</InputLabel>
              <Select label="País" value={pais} onChange={(e) => { setPais(e.target.value); setProvinciaId(''); }}>
                <MenuItem value="">Todos</MenuItem>
                {paises.map((p) => <MenuItem key={p.id} value={p.codigo}>{p.nombre}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
        )}
        {necesitaProv && (
          <Grid item xs={12} sm={3}>
            <FormControl size="small" fullWidth>
              <InputLabel>Provincia</InputLabel>
              <Select label="Provincia" value={provinciaId} onChange={(e) => setProvinciaId(Number(e.target.value))}>
                {provincias.map((p) => <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
        )}
      </Grid>

      <Stack direction="row" spacing={1} sx={{ mb: 2 }} alignItems="center">
        <TextField size="small" label="Nuevo nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
                   onKeyDown={(e) => { if (e.key === 'Enter' && puedeCrear) crear.mutate(); }} sx={{ minWidth: 260 }} />
        <Button variant="contained" startIcon={<AddIcon />} disabled={!puedeCrear || crear.isPending}
                onClick={() => crear.mutate()}>Agregar</Button>
      </Stack>
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper variant="outlined">
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell sx={{ fontWeight: 700 }}>Nombre</TableCell>
              <TableCell align="center" sx={{ fontWeight: 700 }}>Estado</TableCell>
              <TableCell align="right" sx={{ fontWeight: 700 }}>Acciones</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {isLoading && <TableRow><TableCell colSpan={3}>Cargando…</TableCell></TableRow>}
            {!isLoading && items.length === 0 && (
              <TableRow><TableCell colSpan={3} sx={{ color: 'text.secondary', py: 3, textAlign: 'center' }}>
                {necesitaProv && !provinciaId ? 'Elige una provincia' : 'Sin registros'}
              </TableCell></TableRow>
            )}
            {items.map((it) => {
              const activo = it.activo !== false;
              return (
              <TableRow key={it.id} hover sx={{ opacity: activo ? 1 : 0.6 }}>
                <TableCell>
                  {editId === it.id ? (
                    <TextField size="small" value={editNombre} autoFocus fullWidth
                               onChange={(e) => setEditNombre(e.target.value)}
                               onKeyDown={(e) => { if (e.key === 'Enter' && editNombre.trim().length >= 2) renombrar.mutate(); }} />
                  ) : it.nombre}
                </TableCell>
                <TableCell align="center">
                  <Chip size="small" label={activo ? 'Activo' : 'Inactivo'} color={activo ? 'success' : 'default'} variant={activo ? 'filled' : 'outlined'} />
                </TableCell>
                <TableCell align="right">
                  {editId === it.id ? (
                    <>
                      <Button size="small" variant="contained" disabled={editNombre.trim().length < 2 || renombrar.isPending}
                              onClick={() => renombrar.mutate()}>Guardar</Button>
                      <Button size="small" onClick={() => { setEditId(null); setEditNombre(''); }}>Cancelar</Button>
                    </>
                  ) : (
                    <>
                      <Tooltip title="Editar / corregir nombre">
                        <IconButton size="small" color="primary" onClick={() => { setError(''); setEditId(it.id); setEditNombre(it.nombre); }}><EditIcon fontSize="small" /></IconButton>
                      </Tooltip>
                      <Tooltip title={activo ? 'Desactivar' : 'Activar'}>
                        <IconButton size="small" color={activo ? 'warning' : 'success'}
                                    onClick={() => toggleActivo.mutate({ id: it.id, activo: !activo })}>
                          {activo ? <Block fontSize="small" /> : <CheckCircleOutlineIcon fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                      <Tooltip title="Borrar permanentemente">
                        <IconButton size="small" color="error"
                                    onClick={() => { if (window.confirm(`¿Borrar permanentemente "${it.nombre}"? Esta acción no se puede deshacer.`)) borrar.mutate(it.id); }}>
                          <DeleteIcon fontSize="small" />
                        </IconButton>
                      </Tooltip>
                    </>
                  )}
                </TableCell>
              </TableRow>
            ); })}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  );
}

export default function CategorizacionAdmin() {
  const [tab, setTab] = useState(0);

  return (
    <Box>
      <Typography variant="h6" fontWeight={700} mb={1}>Administración — Categorización Médica</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Carga de datos, clasificaciones A/B/C/D y reglas de puntuación por componente.
      </Typography>
      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3, borderBottom: 1, borderColor: 'divider' }}>
        <Tab label="Carga de Excel" />
        <Tab label="Clasificación A/B/C/D" />
        <Tab label="Componentes y Reglas" />
        <Tab label="Catálogos geográficos" />
      </Tabs>
      {tab === 0 && <TabCarga />}
      {tab === 1 && <TabClasificacion />}
      {tab === 2 && <TabReglas />}
      {tab === 3 && <TabGeo />}
    </Box>
  );
}
