import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Grid, Card, CardContent, Table, TableBody, TableCell,
  TableContainer, TableHead, TableRow, Paper, Chip, CircularProgress,
  Tabs, Tab, TextField, MenuItem, Alert,
} from '@mui/material';
import {
  PieChart, Pie, Cell, Tooltip as ChartTooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip,
} from 'recharts';
import { useMemo, useEffect, useState } from 'react';
import { api } from '../../services/api';

const COLOR_APROBADO = '#2e7d32';
const COLOR_NO_APROBADO = '#c62828';
const PALETA = ['#1565c0', '#2e7d32', '#ef6c00', '#6a1b9a', '#00838f', '#c62828'];

export default function Capacitacion() {
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

  const { data: resumen } = useQuery({
    queryKey: ['cap-resumen', paisCodigo, cicloId],
    queryFn: () => api.get('/capacitacion/resumen', { params: filtros }).then(r => r.data),
    retry: 1,
  });
  const { data, isLoading } = useQuery({
    queryKey: ['capacitacion', paisCodigo, cicloId],
    queryFn: () => api.get('/capacitacion', { params: filtros }).then(r => r.data),
    retry: 1,
    enabled: tab === 0,
  });
  const { data: catalogo, isLoading: loadingCatalogo } = useQuery({
    queryKey: ['cap-catalogo'],
    queryFn: () => api.get('/capacitacion/catalogo').then(r => r.data),
    retry: 1,
    enabled: tab === 1,
  });

  const items: any[] = data || [];
  const cursos: any[] = catalogo || [];

  // Aprobación: aprobados vs no aprobados (asistentes)
  const distribAprobacion = useMemo(() => {
    let aprobados = 0, noAprobados = 0;
    for (const r of items) {
      if (!r.asistio) continue;
      if (r.aprobado) aprobados++; else noAprobados++;
    }
    return [
      { nombre: 'Aprobados', valor: aprobados, color: COLOR_APROBADO },
      { nombre: 'No aprobados', valor: noAprobados, color: COLOR_NO_APROBADO },
    ].filter(d => d.valor > 0);
  }, [items]);

  // Calificación promedio por tipo de capacitación
  const porTipo = useMemo(() => {
    const grupos: Record<string, { suma: number; n: number }> = {};
    for (const r of items) {
      const tipo = r.tipo || '—';
      grupos[tipo] = grupos[tipo] || { suma: 0, n: 0 };
      grupos[tipo].suma += Number(r.calificacion || 0);
      grupos[tipo].n += 1;
    }
    return Object.entries(grupos).map(([nombre, { suma, n }]) => ({ nombre, calificacion: n ? suma / n : 0 }));
  }, [items]);

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Capacitación</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>Cursos, certificaciones y evaluaciones</Typography>

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

      {resumen && (
        <Grid container spacing={2} mb={3}>
          {[
            ['Total Registros', resumen.total_registros],
            ['Horas de Formación', resumen.horas_formacion_total != null ? Number(resumen.horas_formacion_total).toLocaleString() : '—'],
            ['Calificación Promedio', resumen.calificacion_promedio != null ? Number(resumen.calificacion_promedio).toFixed(2) : '—'],
            ['Tasa de Aprobación', resumen.tasa_aprobacion_pct != null ? `${Number(resumen.tasa_aprobacion_pct).toFixed(1)}%` : '—'],
          ].map(([l, v]) => (
            <Grid item xs={12} sm={6} md={3} key={l as string}>
              <Card elevation={2} sx={{ borderRadius: 2 }}>
                <CardContent sx={{ textAlign: 'center' }}>
                  <Typography variant="caption" color="text.secondary">{l}</Typography>
                  <Typography variant="h5" fontWeight={700} color="primary.main">{v ?? '—'}</Typography>
                </CardContent>
              </Card>
            </Grid>
          ))}
        </Grid>
      )}

      <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 3 }}>
        <Tab label="Registros de participación" />
        <Tab label="Catálogo de cursos" />
      </Tabs>

      {tab === 0 && (
        <>
          {(distribAprobacion.length > 0 || porTipo.length > 0) && (
            <Grid container spacing={2} mb={3}>
              {distribAprobacion.length > 0 && (
                <Grid item xs={12} md={5}>
                  <Card elevation={2} sx={{ borderRadius: 2, height: '100%' }}>
                    <CardContent>
                      <Typography variant="h6" fontWeight={600} mb={1}>Aprobación (asistentes)</Typography>
                      <ResponsiveContainer width="100%" height={240}>
                        <PieChart>
                          <Pie data={distribAprobacion} dataKey="valor" nameKey="nombre" cx="50%" cy="50%" outerRadius={80} label={(e: any) => `${e.nombre}: ${e.valor}`}>
                            {distribAprobacion.map((entry, i) => <Cell key={i} fill={entry.color} />)}
                          </Pie>
                          <ChartTooltip />
                          <Legend />
                        </PieChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                </Grid>
              )}
              {porTipo.length > 0 && (
                <Grid item xs={12} md={7}>
                  <Card elevation={2} sx={{ borderRadius: 2, height: '100%' }}>
                    <CardContent>
                      <Typography variant="h6" fontWeight={600} mb={1}>Calificación promedio por tipo de curso</Typography>
                      <ResponsiveContainer width="100%" height={240}>
                        <BarChart data={porTipo} margin={{ top: 8, right: 16 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} />
                          <XAxis dataKey="nombre" tick={{ fontSize: 11 }} />
                          <YAxis domain={[0, 100]} />
                          <Tooltip formatter={(v: number) => [v.toFixed(1), 'Calificación']} />
                          <Bar dataKey="calificacion" radius={[4, 4, 0, 0]}>
                            {porTipo.map((_, i) => <Cell key={i} fill={PALETA[i % PALETA.length]} />)}
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </CardContent>
                  </Card>
                </Grid>
              )}
            </Grid>
          )}

          {isLoading ? <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box> : items.length === 0 ? (
            <Alert severity="info">Sin registros de capacitación para los filtros seleccionados.</Alert>
          ) : (
            <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
              <Table size="small">
                <TableHead sx={{ bgcolor: 'primary.main' }}>
                  <TableRow>{['RM', 'Capacitación', 'Tipo', 'Asistió', 'Calificación', 'Aprobado', 'Horas', 'Puntaje', 'Fecha'].map(h => <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>)}</TableRow>
                </TableHead>
                <TableBody>
                  {items.slice(0, 100).map((r: any, i: number) => (
                    <TableRow key={i} hover>
                      <TableCell>{r.rm_nombre || r.rm_id}</TableCell>
                      <TableCell>{r.capacitacion_nombre || r.capacitacion_id}</TableCell>
                      <TableCell>{r.tipo || '—'}</TableCell>
                      <TableCell><Chip label={r.asistio ? 'Sí' : 'No'} color={r.asistio ? 'success' : 'default'} size="small" /></TableCell>
                      <TableCell>{r.calificacion != null ? Number(r.calificacion).toFixed(2) : '—'}</TableCell>
                      <TableCell><Chip label={r.aprobado ? 'Aprobado' : 'No aprobado'} color={r.aprobado ? 'success' : 'error'} size="small" /></TableCell>
                      <TableCell>{r.horas_completadas}</TableCell>
                      <TableCell>{Number(r.puntaje || 0).toFixed(2)}</TableCell>
                      <TableCell>{r.fecha_actividad ? new Date(r.fecha_actividad).toLocaleDateString() : '—'}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </TableContainer>
          )}
        </>
      )}

      {tab === 1 && (
        loadingCatalogo ? <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box> : cursos.length === 0 ? (
          <Alert severity="info">No hay cursos activos en el catálogo.</Alert>
        ) : (
          <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
            <Table size="small">
              <TableHead sx={{ bgcolor: 'primary.main' }}>
                <TableRow>{['Código', 'Nombre', 'Tipo', 'Duración (h)', 'Puntaje aprobación', 'Obligatorio'].map(h => <TableCell key={h} sx={{ color: 'white', fontWeight: 700 }}>{h}</TableCell>)}</TableRow>
              </TableHead>
              <TableBody>
                {cursos.map((c: any) => (
                  <TableRow key={c.id} hover>
                    <TableCell>{c.codigo}</TableCell>
                    <TableCell>{c.nombre}</TableCell>
                    <TableCell><Chip label={c.tipo} size="small" /></TableCell>
                    <TableCell>{Number(c.duracion_horas || 0).toFixed(1)}</TableCell>
                    <TableCell>{Number(c.puntaje_aprobacion || 0).toFixed(1)}</TableCell>
                    <TableCell>
                      <Chip label={c.obligatorio ? 'Obligatorio' : 'Opcional'} size="small" color={c.obligatorio ? 'warning' : 'default'} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </TableContainer>
        )
      )}
    </Box>
  );
}
