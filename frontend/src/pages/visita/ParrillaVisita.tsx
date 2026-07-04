import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, MenuItem,
  CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, IconButton, Grid,
  LinearProgress, Avatar, ToggleButton, ToggleButtonGroup,
} from '@mui/material';
import { Add, Delete, Save, Campaign, Edit, Publish, Inventory2, BarChart, Person, SupervisorAccount } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { api } from '../../services/api';
import {
  listarLineasVisita, obtenerParrilla, guardarParrilla, publicarParrilla, parrillaPenetracion, listarProductosDim,
  type Catalogo, type ParrillaItem, type PenetracionCiclo, type ProductoDim,
} from '../../services/visita.service';

const DOT = ['#E8833A', '#1E52C7', '#0F9B8E', '#7A5AF8', '#5A6472', '#C0392B', '#2AA76A'];

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

export default function ParrillaVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esGestor = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD' || rol === 'GERENTE_MARCA';

  const [lineas, setLineas] = useState<Catalogo[]>([]);
  const [lineaId, setLineaId] = useState<number | ''>('');
  const [ciclos, setCiclos] = useState<{ id: number; nombre: string; cerrado: boolean }[]>([]);
  const [cicloId, setCicloId] = useState<number | ''>('');
  const [parrilla, setParrilla] = useState<ParrillaItem[]>([]);
  const [pen, setPen] = useState<PenetracionCiclo | null>(null);
  const [productosDim, setProductosDim] = useState<ProductoDim[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [editando, setEditando] = useState(false);
  const [draft, setDraft] = useState<ParrillaItem[]>([]);
  const [vistaVM, setVistaVM] = useState(false);   // el gestor previsualiza como VM (solo lectura)

  const cicloParam = cicloId || undefined;
  const cerrado = !!ciclos.find((c) => c.id === cicloId)?.cerrado;
  const soloLectura = !esGestor || vistaVM || cerrado;
  const lineaParam = esGestor ? (lineaId || undefined) : undefined;

  const cargarParrilla = useCallback(() => {
    obtenerParrilla(lineaParam, cicloParam).then(setParrilla).catch(() => setParrilla([]));
    parrillaPenetracion(lineaParam, cicloParam).then(setPen).catch(() => setPen(null));
  }, [lineaParam, cicloParam]);

  useEffect(() => {
    const tareas: Promise<unknown>[] = [];
    if (esGestor) {
      tareas.push(listarLineasVisita().then((ls) => { setLineas(ls); if (ls.length && !lineaId) setLineaId(ls[0].id); }).catch(() => {}));
    }
    api.get<{ id: number; nombre: string; cerrado: boolean }[]>('/admin/ciclos').then((r) => setCiclos(r.data)).catch(() => {});
    Promise.all(tareas).finally(() => setCargando(false));
  }, [esGestor]);   // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    setEditando(false);
    if (esGestor && lineaId) listarProductosDim(Number(lineaId)).then(setProductosDim).catch(() => {});
    if (!esGestor || lineaId) cargarParrilla();
  }, [esGestor, lineaId, cargarParrilla]);

  const publicada = parrilla.length > 0 && parrilla.every((p) => p.publicada);

  // ── Edición ──
  const filaVacia = (): ParrillaItem => ({ producto: '', prioridad: draft.length + 1, meta_muestras: 1 });
  const iniciarEdicion = () => { setDraft(parrilla.length ? parrilla.map((p) => ({ ...p })) : [filaVacia()]); setEditando(true); setMsg(null); };
  const setFila = (i: number, patch: Partial<ParrillaItem>) => setDraft((d) => d.map((x, idx) => idx === i ? { ...x, ...patch } : x));
  const elegirProducto = (i: number, codigo: string) => {
    const p = productosDim.find((x) => x.codigo === codigo);
    if (!p) { setFila(i, { producto: codigo, producto_id: null }); return; }
    setFila(i, {
      producto: p.codigo, producto_id: p.id, nombre: p.nombre, area_terapeutica: p.area_terapeutica,
      descripcion: p.descripcion, segmento_target: p.segmento_target, meta_muestras: p.meta_muestras_visita,
      gerente_producto: p.gerente_producto,
    });
  };

  async function guardar() {
    if (!lineaId) return;
    const items = draft.filter((d) => d.producto.trim());
    setGuardando(true); setMsg(null);
    try {
      await guardarParrilla(Number(lineaId), items, cicloParam);
      setMsg({ tipo: 'success', texto: 'Parrilla guardada como borrador. Publícala para que el equipo la reciba.' });
      setEditando(false); cargarParrilla();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo guardar la parrilla.') });
    } finally { setGuardando(false); }
  }

  async function publicar() {
    if (!lineaId) return;
    setGuardando(true); setMsg(null);
    try {
      const r = await publicarParrilla(Number(lineaId), cicloParam);
      setMsg({ tipo: 'success', texto: `Parrilla publicada al equipo (${r.publicados} productos). Los visitadores ya la reciben.` });
      cargarParrilla();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo publicar la parrilla.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const dot = (i: number) => (
    <Avatar sx={{ width: 26, height: 26, fontSize: 13, fontWeight: 700, bgcolor: DOT[i % DOT.length] }}>{i + 1}</Avatar>
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" justifyContent="space-between" alignItems="flex-start" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
        <Box>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Campaign color="primary" />
            <Typography variant="h5" fontWeight={700}>Parrilla Promocional</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary">
            Configurada por Gerente de Producto · Se despliega automáticamente al VM · Solo lectura para el visitador
          </Typography>
        </Box>
        {esGestor && (
          <ToggleButtonGroup exclusive size="small" value={vistaVM ? 'vm' : 'gerente'} onChange={(_, v) => v && setVistaVM(v === 'vm')}>
            <ToggleButton value="gerente"><SupervisorAccount fontSize="small" sx={{ mr: 0.5 }} /> Gerente</ToggleButton>
            <ToggleButton value="vm"><Person fontSize="small" sx={{ mr: 0.5 }} /> Vista VM</ToggleButton>
          </ToggleButtonGroup>
        )}
      </Stack>

      {esGestor && !vistaVM && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          <b>Solo el Gerente de Producto puede modificar la parrilla.</b> Una vez publicada, el visitador médico la recibe automáticamente y no puede editarla.
        </Alert>
      )}
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {esGestor && (
        <Stack direction="row" spacing={1.5} sx={{ mb: 2 }} alignItems="center" flexWrap="wrap">
          <TextField select size="small" label="Ciclo" value={cicloId} sx={{ minWidth: 180 }}
                     onChange={(e) => setCicloId(Number(e.target.value))}>
            <MenuItem value=""><em>Ciclo actual</em></MenuItem>
            {ciclos.map((c) => <MenuItem key={c.id} value={c.id}>{c.nombre}{c.cerrado ? ' (cerrado)' : ''}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Línea" value={lineaId} sx={{ minWidth: 220 }}
                     onChange={(e) => setLineaId(Number(e.target.value))}>
            {lineas.map((l) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
          </TextField>
          {cerrado && <Chip size="small" label="Ciclo cerrado — solo lectura" />}
        </Stack>
      )}

      {/* KPIs */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={6}>
          <Card variant="outlined"><CardContent sx={{ py: 1.75 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>CICLO ACTIVO</Typography>
            <Typography variant="h5" fontWeight={700} color="primary.main">Ciclo actual</Typography>
            <Typography variant="caption" color={publicada ? 'success.main' : 'warning.main'}>
              {publicada ? 'Parrilla publicada ✓' : 'Parrilla en borrador'}
            </Typography>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} sm={6}>
          <Card variant="outlined"><CardContent sx={{ py: 1.75 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>PRODUCTOS EN PARRILLA</Typography>
            <Typography variant="h5" fontWeight={700}>{parrilla.length}</Typography>
            <Typography variant="caption" color="text.secondary">en orden de importancia</Typography>
          </CardContent></Card>
        </Grid>
      </Grid>

      {/* Parrilla del ciclo */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }} flexWrap="wrap">
            <Inventory2 fontSize="small" color="action" />
            <Typography variant="subtitle1" fontWeight={700}>Parrilla del Ciclo</Typography>
            <Box sx={{ flex: 1 }} />
            {!soloLectura && !editando && (
              <>
                <Button size="small" startIcon={<Edit />} onClick={iniciarEdicion}>Editar</Button>
                <Button size="small" variant="contained" startIcon={<Publish />} disabled={guardando || parrilla.length === 0}
                        onClick={publicar}>Publicar al equipo</Button>
              </>
            )}
          </Stack>

          {editando ? (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell width={70}>Prior.</TableCell><TableCell>Producto</TableCell>
                  <TableCell>Mensaje clave</TableCell><TableCell>Segmento target</TableCell>
                  <TableCell width={110} align="center">Meta/visita</TableCell><TableCell width={48} />
                </TableRow></TableHead>
                <TableBody>
                  {draft.map((it, i) => (
                    <TableRow key={i}>
                      <TableCell><TextField size="small" type="number" value={it.prioridad} sx={{ width: 60 }}
                                            onChange={(e) => setFila(i, { prioridad: Number(e.target.value) })} /></TableCell>
                      <TableCell>
                        <TextField select size="small" fullWidth value={it.producto}
                                   onChange={(e) => elegirProducto(i, e.target.value)}>
                          <MenuItem value=""><em>— Producto —</em></MenuItem>
                          {productosDim.map((p) => <MenuItem key={p.id} value={p.codigo}>{p.codigo} · {p.area_terapeutica}</MenuItem>)}
                        </TextField>
                      </TableCell>
                      <TableCell><TextField size="small" fullWidth value={it.mensaje_clave ?? ''}
                                            onChange={(e) => setFila(i, { mensaje_clave: e.target.value })} /></TableCell>
                      <TableCell><TextField size="small" fullWidth value={it.segmento_target ?? ''}
                                            onChange={(e) => setFila(i, { segmento_target: e.target.value })} /></TableCell>
                      <TableCell align="center"><TextField size="small" type="number" value={it.meta_muestras} sx={{ width: 80 }}
                                            inputProps={{ min: 0 }} onChange={(e) => setFila(i, { meta_muestras: Number(e.target.value) })} /></TableCell>
                      <TableCell><IconButton size="small" color="error" onClick={() => setDraft((d) => d.filter((_, idx) => idx !== i))}><Delete fontSize="small" /></IconButton></TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
              <Stack direction="row" spacing={1.5} sx={{ mt: 1.5 }}>
                <Button size="small" startIcon={<Add />} onClick={() => setDraft((d) => [...d, filaVacia()])}>Agregar producto</Button>
                <Button size="small" variant="contained" startIcon={<Save />} disabled={guardando} onClick={guardar}>
                  {guardando ? 'Guardando…' : 'Guardar borrador'}
                </Button>
                <Button size="small" onClick={() => setEditando(false)}>Cancelar</Button>
              </Stack>
            </Box>
          ) : parrilla.length === 0 ? (
            <Alert severity="info">
              {soloLectura ? 'La parrilla del ciclo aún no ha sido publicada por el Gerente de Producto.'
                           : 'Sin productos. Usa "Editar" para armar la parrilla y luego publícala.'}
            </Alert>
          ) : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell width={40}>#</TableCell><TableCell>Producto</TableCell>
                  <TableCell align="center">Meta muestras/visita</TableCell>
                  <TableCell>Segmento target</TableCell><TableCell align="center">Estado</TableCell>
                </TableRow></TableHead>
                <TableBody>
                  {parrilla.map((p, i) => (
                    <TableRow key={p.id ?? i} hover>
                      <TableCell>{dot(i)}</TableCell>
                      <TableCell>
                        <Typography variant="body2" fontWeight={700}>{p.nombre || p.producto}</Typography>
                        <Typography variant="caption" color="text.secondary">
                          {[p.area_terapeutica, p.descripcion || p.mensaje_clave].filter(Boolean).join(' · ')}
                        </Typography>
                      </TableCell>
                      <TableCell align="center">
                        <Typography variant="body2" fontWeight={700} color="primary.main">{p.meta_muestras}</Typography>
                        <Typography variant="caption" color="text.secondary">muestras/visita</Typography>
                      </TableCell>
                      <TableCell><Typography variant="body2" color="text.secondary">{p.segmento_target || '—'}</Typography></TableCell>
                      <TableCell align="center">
                        <Chip size="small" color={p.publicada ? 'success' : 'warning'} variant="outlined"
                              label={p.publicada ? '✓ Activo' : 'Borrador'} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Penetración del ciclo */}
      <Card variant="outlined">
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <BarChart fontSize="small" color="action" />
            <Typography variant="subtitle1" fontWeight={700}>Penetración del Ciclo</Typography>
            {pen && <Chip size="small" variant="outlined" label={`Panel ${pen.panel} · ${pen.visitas} visitas`} />}
          </Stack>
          {!pen || pen.productos.length === 0 ? (
            <Alert severity="info">Aún no hay datos de penetración para esta línea.</Alert>
          ) : (
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell width={40}>#</TableCell><TableCell>Producto</TableCell>
                  <TableCell width={220}>Penetración médicos</TableCell>
                  <TableCell align="center">Muestras total</TableCell><TableCell align="center">Promedio/visita</TableCell>
                </TableRow></TableHead>
                <TableBody>
                  {pen.productos.map((p, i) => {
                    const color = p.penetracion_pct >= 60 ? 'success' : p.penetracion_pct >= 40 ? 'warning' : 'error';
                    return (
                      <TableRow key={p.producto} hover>
                        <TableCell>{dot(i)}</TableCell>
                        <TableCell>
                          <Typography variant="body2" fontWeight={700}>{p.nombre || p.producto}</Typography>
                          <Typography variant="caption" color="text.secondary">{p.segmento_target || ''}</Typography>
                        </TableCell>
                        <TableCell>
                          <Stack direction="row" alignItems="center" spacing={1}>
                            <Typography variant="caption" fontWeight={700} sx={{ minWidth: 34 }}>{p.penetracion_pct}%</Typography>
                            <LinearProgress variant="determinate" value={Math.min(100, p.penetracion_pct)} color={color} sx={{ flex: 1, height: 6, borderRadius: 3 }} />
                            <Typography variant="caption" color="text.secondary" sx={{ whiteSpace: 'nowrap' }}>{p.medicos} méd.</Typography>
                          </Stack>
                        </TableCell>
                        <TableCell align="center"><Typography variant="body2" fontWeight={700}>{p.muestras_total}</Typography></TableCell>
                        <TableCell align="center"><Typography variant="body2" fontWeight={700} color="primary.main">{p.promedio_visita}</Typography></TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </Box>
          )}
        </CardContent>
      </Card>
    </Box>
  );
}
