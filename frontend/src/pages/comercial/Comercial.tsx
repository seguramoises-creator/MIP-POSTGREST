import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, CircularProgress, Alert, Table,
  TableBody, TableCell, TableContainer, TableHead, TableRow, Paper, Chip,
  Tabs, Tab, TextField, MenuItem,
} from '@mui/material';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Legend, Cell,
} from 'recharts';
import { useMemo, useState, useEffect } from 'react';
import { api } from '../../services/api';

export default function Comercial() {
  const [tab, setTab] = useState(0);
  const [paisCodigo, setPaisId] = useState('');
  const [cicloId, setCicloId] = useState('');

  const { data: paises } = useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then((r) => r.data),
  });
  const { data: ciclos } = useQuery({
    queryKey: ['ciclos', paisCodigo],
    queryFn: () => api.get('/admin/ciclos', { params: { ...(paisCodigo && { pais_codigo: paisCodigo }) } }).then((r) => r.data),
  });
  const paisNombrePorId: Record<number, string> = Object.fromEntries((paises || []).map((p: any) => [p.id, p.nombre]));
  const cicloLabel = (c: any) => paisCodigo ? c.nombre : `${c.nombre} — ${paisNombrePorId[c.pais_codigo] || 'País desconocido'}`;

  // ── Auto-seleccionar República Dominicana al cargar ───────────────────
  useEffect(() => {
    if (!(paises || []).length || paisCodigo) return;
    const rd = (paises as any[]).find((p: any) =>
      p.codigo?.toUpperCase() === 'RD' ||
      p.nombre?.toLowerCase().includes('dominicana')
    );
    if (rd) setPaisId(String(rd.id));
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps

  // Obtener el último ciclo con datos reales
  const { data: _cicloEf } = useQuery({
    queryKey: ['ciclo-ef', paisCodigo],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisCodigo && { pais_codigo: Number(paisCodigo) }), size: 1, page: 1 },
    }).then(r => r.data?.ciclo_efectivo ?? null),
    enabled: !!paisCodigo,
    staleTime: 60_000,
  });
  // ── Auto-seleccionar el último ciclo CON DATOS ─────────────────────
  useEffect(() => {
    if (!_cicloEf || cicloId) return;
    setCicloId(String(_cicloEf));
  }, [_cicloEf]); // eslint-disable-line react-hooks/exhaustive-deps

  const filtros = { ...(paisCodigo && { pais_codigo: paisCodigo }), ...(cicloId && { ciclo_id: cicloId }) };

  const { data: kpis } = useQuery({
    queryKey: ['comercial-kpis', paisCodigo, cicloId],
    queryFn: () => api.get('/comercial', { params: filtros }).then(r => r.data),
    retry: 1,
  });
  const { data: ventas, isLoading: loadingVentas } = useQuery({
    queryKey: ['ventas', paisCodigo, cicloId],
    queryFn: () => api.get('/comercial/ventas', { params: filtros }).then(r => r.data),
    retry: 1,
    enabled: tab === 0,
  });
  const { data: evoir, isLoading: loadingEvoIR } = useQuery({
    queryKey: ['evoir', paisCodigo, cicloId],
    queryFn: () => api.get('/comercial/evoir', { params: filtros }).then(r => r.data),
    retry: 1,
    enabled: tab === 1,
  });

  const itemsVentas: any[] = ventas || [];
  const itemsEvoIR: any[] = evoir || [];

  const chartVentas = itemsVentas.slice(0, 10).map(v => ({
    nombre: v.rm_nombre || `RM${v.rm_id}`,
    ventas: Number(v.ventas_reales || 0),
    cuota: Number(v.cuota || 0),
  }));

  // Crecimiento por RM — top 10 mayor crecimiento (positivo o negativo)
  const chartCrecimiento = useMemo(() => {
    return [...itemsVentas]
      .sort((a, b) => Math.abs(Number(b.crecimiento_pct || 0)) - Math.abs(Number(a.crecimiento_pct || 0)))
      .slice(0, 10)
      .map(v => ({ nombre: v.rm_nombre || `RM${v.rm_id}`, crecimiento: Number(v.crecimiento_pct || 0) }));
  }, [itemsVentas]);

  const chartEvoIR = itemsEvoIR.slice(0, 10).map(v => ({
    nombre: v.rm_nombre || `RM${v.rm_id}`,
    evolucion: Number(v.evolucion_pct || 0),
  }));

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Comercial</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>Ventas, EVO IR y cumplimiento de cuota</Typography>

      {/* Filtros */}
      <Card elevation={1} sx={{ mb: 3, borderRadius: 2 }}>
        <CardContent>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="País" value={paisCodigo} onChange={(e) => { setPaisId(e.target.value); setCicloId(''); }}>
                <MenuItem value="">Todos los países</MenuItem>
                {(paises || []).map((p: any) => <MenuItem key={p.id} value={p.id}>{p.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="Ciclo" value={cicloId} onChange={(e) => setCicloId(e.target.value)}>
                <MenuItem value="">Todos los ciclos</MenuItem>
                {(ciclos || []).map((c: any) => <MenuItem key={c.id} value={c.id}>{cicloLabel(c)}</MenuItem>)}
              </TextField>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {kpis && (
        <Grid container spacing={2} mb={3}>
          {[
            { label: 'Total RMs', value: kpis.total_rms },
            { label: 'Ventas Totales', value: kpis.ventas_totales != null ? Number(kpis.ventas_totales).toLocaleString() : '—' },
            { label: 'Cuota Total', value: kpis.cuota_total != null ? Number(kpis.cuota_total).toLocaleString() : '—' },
            { label: 'Cumplimiento Promedio', value: kpis.cumplimiento_promedio_pct != null ? `${Number(kpis.cumplimiento_promedio_pct).toFixed(1)}%` : '—' },
          ].map((kpi) => (
            <Grid item xs={12} sm={6} md={3} key={kpi.label}>
              <Card elevation={2} sx={{ borderRadius: 2 }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Typography variant="caption" color="text.secondary">{kpi.label}</Typography>
                  <Typography variant="h5" fontWeight={700} color="primary.main">{kpi.value ?? '—'}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Ventas vs Cuota" />
        <Tab label="Evolución IR (EVO IR)" />
      </Tabs>

      {tab === 0 && (
        <>
          {chartVentas.length > 0 && (
            <Grid container spacing={2} mb={3}>
              <Grid item xs={12} md={6}>
                <Card elevation={2} sx={{ borderRadius: 2, height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" fontWeight={600} mb={2}>Ventas vs Cuota — Top 10 RMs</Typography>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={chartVentas}>
                        <CartesianGrid strokeDasharray="3 3" />
                        <XAxis dataKey="nombre" tick={{ fontSize: 11 }} />
                        <YAxis />
                        <Tooltip />
                        <Legend />
                        <Bar dataKey="ventas" fill="#584F46" name="Ventas Reales" />
                        <Bar dataKey="cuota" fill="#D8D2CB" name="Cuota" />
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={12} md={6}>
                <Card elevation={2} sx={{ borderRadius: 2, height: '100%' }}>
                  <CardContent>
                    <Typography variant="h6" fontWeight={600} mb={2}>Crecimiento — mayores variaciones</Typography>
                    <ResponsiveContainer width="100%" height={280}>
                      <BarChart data={chartCrecimiento}>
                        <CartesianGrid strokeDasharray="3 3" vertical={false} />
                        <XAxis dataKey="nombre" tick={{ fontSize: 11 }} />
                        <YAxis tickFormatter={(v) => `${v}%`} />
                        <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, 'Crecimiento']} />
                        <Bar dataKey="crecimiento" radius={[4, 4, 0, 0]}>
                          {chartCrecimiento.map((entry, i) => (
                            <Cell key={i} fill={entry.crecimiento >= 0 ? '#2e7d32' : '#c62828'} />
                          ))}
                        </Bar>
                      </BarChart>
                    </ResponsiveContainer>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>
          )}

          {loadingVentas ? <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box> : (
            <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: 'primary.main' }}>
                  <TableRow>{['RM', 'Ciclo', 'Ventas', 'Cuota', 'Cumplimiento', 'Crecimiento', 'Puntaje'].map(h => <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>)}</TableRow>
                </TableHead>
                <TableBody>
                  {itemsVentas.length === 0 ? <TableRow><TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>Sin datos</TableCell></TableRow> : itemsVentas.slice(0, 100).map((r: any, i: number) => (
                    <TableRow key={i} hover>
                      <TableCell>{r.rm_nombre || r.rm_id}</TableCell>
                      <TableCell>{r.ciclo_id}</TableCell>
                      <TableCell>{Number(r.ventas_reales || 0).toLocaleString()}</TableCell>
                      <TableCell>{Number(r.cuota || 0).toLocaleString()}</TableCell>
                      <TableCell><Chip label={`${Number(r.cumplimiento_pct || 0).toFixed(1)}%`} size="small" color={Number(r.cumplimiento_pct) >= 95 ? 'success' : 'warning'} /></TableCell>
                      <TableCell>
                        <Chip
                          label={`${Number(r.crecimiento_pct || 0) >= 0 ? '+' : ''}${Number(r.crecimiento_pct || 0).toFixed(1)}%`}
                          size="small" variant="outlined"
                          color={Number(r.crecimiento_pct || 0) >= 0 ? 'success' : 'error'}
                        />
                      </TableCell>
                      <TableCell>{Number(r.puntaje || 0).toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      {tab === 1 && (
        <>
          {chartEvoIR.length > 0 && (
            <Card elevation={2} sx={{ borderRadius: 2, mb: 3 }}>
              <CardContent>
                <Typography variant="h6" fontWeight={600} mb={2}>Evolución de prescripciones IR — Top 10</Typography>
                <ResponsiveContainer width="100%" height={280}>
                  <BarChart data={chartEvoIR}>
                    <CartesianGrid strokeDasharray="3 3" vertical={false} />
                    <XAxis dataKey="nombre" tick={{ fontSize: 11 }} />
                    <YAxis tickFormatter={(v) => `${v}%`} />
                    <Tooltip formatter={(v: number) => [`${v.toFixed(1)}%`, 'Evolución']} />
                    <Bar dataKey="evolucion" radius={[4, 4, 0, 0]}>
                      {chartEvoIR.map((entry, i) => (
                        <Cell key={i} fill={entry.evolucion >= 0 ? '#2e7d32' : '#c62828'} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>
              </CardContent>
            </Card>
          )}

          {loadingEvoIR ? <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box> : itemsEvoIR.length === 0 ? (
            <Alert severity="info">Sin datos de evolución IR para los filtros seleccionados.</Alert>
          ) : (
            <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: 'primary.main' }}>
                  <TableRow>{['RM', 'Producto', 'Prescripciones Actuales', 'Prescripciones Anteriores', 'Evolución', 'Puntaje'].map(h => <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>)}</TableRow>
                </TableHead>
                <TableBody>
                  {itemsEvoIR.slice(0, 100).map((r: any, i: number) => (
                    <TableRow key={i} hover>
                      <TableCell>{r.rm_nombre || r.rm_id}</TableCell>
                      <TableCell>{r.producto_nombre || r.producto_codigo || '—'}</TableCell>
                      <TableCell>{Number(r.prescripciones_actuales || 0).toLocaleString()}</TableCell>
                      <TableCell>{Number(r.prescripciones_anteriores || 0).toLocaleString()}</TableCell>
                      <TableCell>
                        <Chip
                          label={`${Number(r.evolucion_pct || 0) >= 0 ? '+' : ''}${Number(r.evolucion_pct || 0).toFixed(1)}%`}
                          size="small"
                          color={Number(r.evolucion_pct || 0) >= 0 ? 'success' : 'error'}
                        />
                      </TableCell>
                      <TableCell>{Number(r.puntaje || 0).toFixed(2)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}
    </Box>
  );
}
