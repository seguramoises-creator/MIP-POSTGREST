import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, MenuItem,
  CircularProgress, Grid, Divider, Table, TableHead, TableRow, TableCell, TableBody, LinearProgress,
} from '@mui/material';
import { Paid, TrendingUp, TrendingDown, Save, Tune, Leaderboard } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  costoRoi, costoRanking, obtenerParametrosCosto, guardarParametrosCosto, listarLineasVisita,
  type RoiResumen, type RoiRanking, type ParametroCosto, type Catalogo,
} from '../../services/visita.service';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

export default function CostoRoiVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esGestor = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD';

  const [roi, setRoi] = useState<RoiResumen | null>(null);
  const [ranking, setRanking] = useState<RoiRanking | null>(null);
  const [lineas, setLineas] = useState<Catalogo[]>([]);
  const [lineaParam, setLineaParam] = useState<number | ''>('');       // '' = default del ciclo
  const [params, setParams] = useState<ParametroCosto | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const money = (v: number) => `${roi?.moneda ?? 'RD$'} ${Math.round(v).toLocaleString()}`;

  const cargarParams = useCallback((lid: number | '') => {
    obtenerParametrosCosto(lid || undefined).then(setParams).catch(() => setParams(null));
  }, []);

  const cargar = useCallback(() => {
    setCargando(true);
    const tareas: Promise<unknown>[] = [costoRoi().then(setRoi).catch(() => setRoi(null))];
    if (esGestor) {
      tareas.push(costoRanking().then(setRanking).catch(() => setRanking(null)));
      tareas.push(listarLineasVisita().then(setLineas).catch(() => {}));
      tareas.push(Promise.resolve(cargarParams('')));
    }
    Promise.all(tareas).finally(() => setCargando(false));
  }, [esGestor, cargarParams]);
  useEffect(() => { cargar(); }, [cargar]);

  const onLineaParam = (v: number | '') => { setLineaParam(v); cargarParams(v); };
  const setP = (campo: keyof ParametroCosto, v: number | string) =>
    setParams((p) => p ? { ...p, [campo]: v } : p);

  async function guardar() {
    if (!params) return;
    setGuardando(true); setMsg(null);
    try {
      await guardarParametrosCosto({
        linea_id: lineaParam === '' ? null : Number(lineaParam),
        costo_visita: Number(params.costo_visita) || 0,
        costo_muestra: Number(params.costo_muestra) || 0,
        costo_fijo_ciclo: Number(params.costo_fijo_ciclo) || 0,
        moneda: params.moneda || 'RD$',
      });
      setMsg({ tipo: 'success', texto: 'Parámetros de costo guardados.' });
      cargar();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudieron guardar los parámetros.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const kpi = (label: string, valor: string, color = 'text.primary', icon?: React.ReactNode) => (
    <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
      <Stack direction="row" alignItems="center" spacing={0.5}>
        {icon}
        <Typography variant="caption" color="text.secondary">{label}</Typography>
      </Stack>
      <Typography variant="h6" fontWeight={700} sx={{ color }}>{valor}</Typography>
    </CardContent></Card>
  );

  const roiColor = roi?.roi_pct == null ? 'text.secondary' : roi.roi_pct >= 0 ? 'success.main' : 'error.main';

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Paid color="primary" />
        <Typography variant="h5" fontWeight={700}>Costo & ROI de Visita</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Costo de operar las visitas (contactos + muestras + fijo) frente a los ingresos del ciclo.
      </Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {roi && !roi.configurado && (
        <Alert severity={esGestor ? 'warning' : 'info'} sx={{ mb: 2 }}>
          {esGestor ? 'Configura los parámetros de costo abajo para calcular el ROI.'
                    : 'Los parámetros de costo del ciclo aún no están configurados.'}
        </Alert>
      )}

      {roi && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={6} md={2.4}>{kpi('Costo total', money(roi.costo_total))}</Grid>
            <Grid item xs={6} md={2.4}>{kpi('Costo / contacto', money(roi.costo_por_contacto))}</Grid>
            <Grid item xs={6} md={2.4}>{kpi('Costo / médico', money(roi.costo_por_medico))}</Grid>
            <Grid item xs={6} md={2.4}>{kpi('Ingresos', money(roi.ingresos))}</Grid>
            <Grid item xs={12} md={2.4}>
              {kpi('ROI', roi.roi_pct == null ? '—' : `${roi.roi_pct}%`, roiColor,
                   roi.roi_pct != null && roi.roi_pct >= 0 ? <TrendingUp fontSize="small" color="success" /> : <TrendingDown fontSize="small" color="error" />)}
            </Grid>
          </Grid>

          <Card variant="outlined" sx={{ mb: 3 }}>
            <CardContent>
              <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>Desglose de costo</Typography>
              <Grid container spacing={2}>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">Visitas ({roi.contactos} contactos)</Typography>
                  <Typography variant="body1" fontWeight={600}>{money(roi.costo_visitas)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">Muestras ({roi.muestras} uds)</Typography>
                  <Typography variant="body1" fontWeight={600}>{money(roi.costo_muestras)}</Typography>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Typography variant="caption" color="text.secondary">Costo fijo del ciclo</Typography>
                  <Typography variant="body1" fontWeight={600}>{money(roi.costo_fijo)}</Typography>
                </Grid>
              </Grid>
              <Divider sx={{ my: 1.5 }} />
              <Stack direction="row" spacing={2} flexWrap="wrap">
                <Chip label={`Utilidad: ${money(roi.utilidad)}`} color={roi.utilidad >= 0 ? 'success' : 'error'} />
                {roi.ratio_ingreso_costo != null && <Chip variant="outlined" label={`Ingreso/Costo: ${roi.ratio_ingreso_costo}×`} />}
                <Chip variant="outlined" label={`${roi.medicos_visitados} médicos visitados`} />
              </Stack>
            </CardContent>
          </Card>
        </>
      )}

      {/* Configuración de parámetros (solo gestión) */}
      {esGestor && params && (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap">
              <Tune fontSize="small" color="action" />
              <Typography variant="subtitle1" fontWeight={700}>Parámetros de costo</Typography>
              <Box sx={{ flex: 1 }} />
              <TextField select size="small" label="Alcance" value={lineaParam} sx={{ minWidth: 220 }}
                         onChange={(e) => onLineaParam(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value=""><em>Default del ciclo</em></MenuItem>
                {lineas.map((l) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
              </TextField>
            </Stack>
            <Grid container spacing={2}>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth size="small" type="number" label="Costo por contacto" value={params.costo_visita}
                           inputProps={{ min: 0, step: 0.01 }} onChange={(e) => setP('costo_visita', Number(e.target.value))} />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth size="small" type="number" label="Costo por muestra" value={params.costo_muestra}
                           inputProps={{ min: 0, step: 0.01 }} onChange={(e) => setP('costo_muestra', Number(e.target.value))} />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth size="small" type="number" label="Costo fijo del ciclo" value={params.costo_fijo_ciclo}
                           inputProps={{ min: 0, step: 0.01 }} onChange={(e) => setP('costo_fijo_ciclo', Number(e.target.value))} />
              </Grid>
              <Grid item xs={6} sm={3}>
                <TextField fullWidth size="small" label="Moneda" value={params.moneda}
                           onChange={(e) => setP('moneda', e.target.value)} />
              </Grid>
            </Grid>
            <Button variant="contained" size="small" startIcon={<Save />} sx={{ mt: 2 }} disabled={guardando} onClick={guardar}>
              {guardando ? 'Guardando…' : 'Guardar parámetros'}
            </Button>
          </CardContent>
        </Card>
      )}

      {/* Ranking de ROI por VM (gestión) */}
      {esGestor && ranking && ranking.items.length > 0 && (
        <>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <Leaderboard color="primary" />
            <Typography variant="h6" fontWeight={700}>ROI por visitador</Typography>
            {ranking.no_cumplen > 0 && <Chip size="small" color="error" label={`${ranking.no_cumplen} no rentables`} />}
          </Stack>
          <Card variant="outlined">
            <Box sx={{ overflowX: 'auto' }}>
              <Table size="small">
                <TableHead><TableRow>
                  <TableCell>Visitador</TableCell>
                  <TableCell align="center">Costo</TableCell>
                  <TableCell align="center">Ingresos</TableCell>
                  <TableCell width={180}>ROI</TableCell>
                </TableRow></TableHead>
                <TableBody>
                  {ranking.items.map((it) => (
                    <TableRow key={it.vm_id} hover>
                      <TableCell>{it.nombre}{it.zona ? ` · ${it.zona}` : ''}</TableCell>
                      <TableCell align="center">{Math.round(it.costo_total).toLocaleString()}</TableCell>
                      <TableCell align="center">{Math.round(it.ingresos).toLocaleString()}</TableCell>
                      <TableCell>
                        <Stack spacing={0.3}>
                          <LinearProgress variant="determinate"
                                          value={Math.max(0, Math.min(100, it.valor))}
                                          color={it.cumple ? 'success' : 'error'} />
                          <Typography variant="caption" color={it.cumple ? 'success.main' : 'error.main'}>{it.valor}%</Typography>
                        </Stack>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Box>
          </Card>
        </>
      )}
    </Box>
  );
}
