import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, Chip, CircularProgress,
  TextField, MenuItem, Alert, Divider,
} from '@mui/material';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer,
  Cell, LabelList, ReferenceLine,
} from 'recharts';
import { useMemo, useEffect, useState } from 'react';
import { api } from '../../services/api';

import { KPI_ORDEN, kpiNombre } from '../../constants/kpi';

// ── helpers ───────────────────────────────────────────────────────────────────
function catColor(v: number) {
  if (v >= 90) return '#2e7d32';
  if (v >= 80) return '#1565c0';
  if (v >= 60) return '#ef6c00';
  return '#c62828';
}
function catInfo(v: number) {
  if (v >= 90) return { label: 'Excelente',    color: '#2e7d32', bg: '#e8f5e9' };
  if (v >= 80) return { label: 'Bueno',         color: '#1565c0', bg: '#e3f2fd' };
  if (v >= 60) return { label: 'En Desarrollo', color: '#e65100', bg: '#fff3e0' };
  return              { label: 'Riesgo',        color: '#c62828', bg: '#ffebee' };
}

// ── stat card ─────────────────────────────────────────────────────────────────
function StatCard({ label, value, sub, color = '#1565c0' }: {
  label: string; value: string | number; sub?: string; color?: string;
}) {
  return (
    <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%',
      borderTop: `3px solid ${color}` }}>
      <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary"
          sx={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', fontSize: '0.65rem' }}>
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={800} sx={{ color, lineHeight: 1.1, mt: 0.5 }}>{value}</Typography>
        {sub && <Typography variant="caption" sx={{ color: 'text.secondary', fontSize: '0.7rem' }}>{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

// ── custom tooltip del gráfico ────────────────────────────────────────────────
const ChartTooltip = ({ active, payload }: any) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const ci = catInfo(d.avg);
  return (
    <Box sx={{ bgcolor: 'white', border: '1px solid #e0e7ef', borderRadius: 1.5, p: 1.5, boxShadow: 2, minWidth: 200 }}>
      <Typography fontWeight={700} fontSize="0.8rem" mb={0.5}>{d.nombre}</Typography>
      <Typography fontSize="0.75rem" color="text.secondary">Peso: <b>{d.peso} pts</b></Typography>
      <Typography fontSize="0.75rem" color="text.secondary">
        Resultado: <b style={{ color: ci.color }}>{d.avg.toFixed(1)}%</b>
      </Typography>
      <Chip label={ci.label} size="small"
        sx={{ bgcolor: ci.bg, color: ci.color, fontWeight: 700, fontSize: '0.68rem', height: 20, mt: 0.5 }} />
    </Box>
  );
};

// ── dist card ─────────────────────────────────────────────────────────────────
function DistCard({ label, count, total, rangoLabel, color, bg }: {
  label: string; count: number; total: number; rangoLabel: string; color: string; bg: string;
}) {
  const pct = total ? ((count / total) * 100).toFixed(1) : '0.0';
  return (
    <Box sx={{ mb: 2, p: 1.5, borderRadius: 2, bgcolor: bg, border: `1px solid ${color}22` }}>
      <Typography variant="caption"
        sx={{ color, fontWeight: 800, textTransform: 'uppercase', letterSpacing: '1px', fontSize: '0.65rem' }}>
        {label}
      </Typography>
      <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 1, mt: 0.3 }}>
        <Typography variant="h4" fontWeight={900} sx={{ color, lineHeight: 1 }}>{count}</Typography>
        <Typography fontSize="0.75rem" color="text.secondary">RMs</Typography>
      </Box>
      <Typography fontSize="0.72rem" color="text.secondary" mt={0.3}>
        {pct}% del equipo · {rangoLabel}
      </Typography>
    </Box>
  );
}

// ── main ──────────────────────────────────────────────────────────────────────
export default function Coaching() {
  const [paisId,  setPaisId]  = useState('');
  const [cicloId, setCicloId] = useState('');

  const { data: paises } = useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then(r => r.data),
  });
  const { data: ciclos } = useQuery({
    queryKey: ['ciclos', paisId],
    queryFn: () => api.get('/admin/ciclos', { params: { ...(paisId && { pais_codigo: paisId }) } }).then(r => r.data),
  });
  const { data: indicadores } = useQuery({
    queryKey: ['indicadores', paisId],
    queryFn: () => api.get('/admin/indicadores', { params: { ...(paisId && { pais_codigo: paisId }), size: 100 } })
      .then(r => r.data?.items ?? r.data ?? []),
    enabled: !!paisId,
  });

  const paisNombrePorId: Record<number, string> = Object.fromEntries(
    (paises || []).map((p: any) => [p.id, p.nombre])
  );
  const cicloLabel = (c: any) =>
    paisId ? c.nombre : `${c.nombre} — ${paisNombrePorId[c.pais_codigo] || ''}`;
  const cicloActivo = (ciclos || []).find((c: any) => String(c.id) === cicloId);
  const cicloNombre = cicloActivo?.nombre_canonico || cicloActivo?.nombre
    || (cicloId ? `Ciclo ${cicloId}` : 'Ciclo activo');

  useEffect(() => {
    if (!(paises || []).length || paisId) return;
    const rd = (paises as any[]).find((p: any) =>
      p.codigo?.toUpperCase() === 'RD' || p.nombre?.toLowerCase().includes('dominicana')
    );
    if (rd) setPaisId(rd.codigo);
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: _cicloEf } = useQuery({
    queryKey: ['ciclo-ef', paisId],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisId && { pais_codigo: paisId }), size: 1, page: 1 },
    }).then(r => r.data?.ciclo_efectivo ?? null),
    enabled: !!paisId,
    staleTime: 60_000,
  });
  useEffect(() => {
    if (!_cicloEf || cicloId) return;
    setCicloId(String(_cicloEf));
  }, [_cicloEf]); // eslint-disable-line react-hooks/exhaustive-deps

  const { data: prodData, isLoading: loadProd } = useQuery({
    queryKey: ['prod-scorecard', paisId, cicloId],
    queryFn: () => api.get('/productividad', {
      params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: cicloId }), size: 5000, page: 1 },
    }).then(r => r.data?.items ?? r.data ?? []),
    enabled: !!paisId && !!cicloId,
    retry: 1,
  });

  const { data: rankData, isLoading: loadRank } = useQuery({
    queryKey: ['rank-scorecard', paisId, cicloId],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: Number(cicloId) }), size: 500, page: 1 },
    }).then(r => r.data?.items ?? r.data ?? []),
    enabled: !!paisId && !!cicloId,
    retry: 1,
  });

  const isLoading = loadProd || loadRank;

  // ── scorecard rows: promedio por indicador ────────────────────────────────
  const scorecardRows = useMemo(() => {
    const prods: any[] = Array.isArray(prodData) ? prodData
      : Array.isArray((prodData as any)?.items) ? (prodData as any).items : [];
    const inds: any[] = Array.isArray(indicadores) ? indicadores
      : Array.isArray((indicadores as any)?.items) ? (indicadores as any).items : [];
    if (!inds.length) return [];

    // El endpoint devuelve indicador_codigo + cumplimiento_pct (no indicador_id)
    const grupos: Record<string, { suma: number; n: number }> = {};
    for (const row of prods) {
      const codigo = row.indicador_codigo;
      if (!codigo) continue;
      grupos[codigo] = grupos[codigo] || { suma: 0, n: 0 };
      grupos[codigo].suma += Number(row.cumplimiento_pct ?? row.porcentaje_cumplimiento ?? 0);
      grupos[codigo].n    += 1;
    }

    return inds
      .filter((ind: any) => ind.activo !== false)
      .map((ind: any) => {
        const g    = grupos[ind.codigo];
        const avg  = g && g.n ? g.suma / g.n : 0;
        // ponderacion_pct es entero 0-100 (ej: 15 = 15%).
        // Si no está, usa peso_iup (decimal 0.15) × 100.
        const peso = ind.ponderacion_pct != null
          ? Number(ind.ponderacion_pct)
          : Math.round((ind.peso_iup ?? 0) * 100);
        // nombre canónico (override desde constants) + corto para el eje Y
        const nombre = kpiNombre(ind.codigo, ind.nombre as string);
        const nombreCorto = nombre.length > 26 ? nombre.substring(0, 25) + '…' : nombre;
        return { id: ind.id, codigo: ind.codigo as string, nombre, nombreCorto, peso, avg, diffPp: avg - 85 };
      })
      .filter(r => r.peso > 0)
      .sort((a, b) => (KPI_ORDEN[a.codigo] ?? 99) - (KPI_ORDEN[b.codigo] ?? 99));
  }, [prodData, indicadores]);

  // ── distribución IUP desde ranking ───────────────────────────────────────
  const dist = useMemo(() => {
    const items: any[] = Array.isArray(rankData) ? rankData : [];
    if (!items.length) return null;
    // score_ciclo_actual = puntos del ciclo seleccionado (no el acumulado)
    // Redondeamos a 1 decimal para que 89.95 → 90.0 (igual que toFixed en pantalla)
    const pts = items.map(r =>
      Math.round(Number(r.score_ciclo_actual ?? r.score_total ?? 0) * 10) / 10
    );
    const avg = pts.reduce((a, b) => a + b, 0) / pts.length;
    const max = Math.max(...pts);
    return {
      total:       items.length,
      elegibles:   pts.filter(p => p >= 90).length,
      excelentes:  pts.filter(p => p >= 90).length,
      buenos:      pts.filter(p => p >= 80 && p < 90).length,
      enDesarrollo:pts.filter(p => p >= 60 && p < 80).length,
      criticos:    pts.filter(p => p <  60).length,
      avgPts: avg, maxPts: max,
    };
  }, [rankData]);

  const destInd = useMemo(() => {
    const find = (kws: string[]) =>
      scorecardRows.find(r => kws.some(k => r.nombre.toLowerCase().includes(k.toLowerCase())));
    return { evoIR: find(['evo', 'ir']), cobF2: find(['f2', 'frecuencia 2']) };
  }, [scorecardRows]);

  const nActivos = scorecardRows.length;
  const hayKpiData = scorecardRows.some(r => r.avg > 0);

  // dominio X del gráfico
  const maxAvg = scorecardRows.length ? Math.max(...scorecardRows.map(r => r.avg)) : 100;
  const xMax   = Math.ceil(Math.max(105, maxAvg + 8) / 10) * 10;

  return (
    <Box>
      {/* header */}
      <Box sx={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between',
        mb: 2.5, flexWrap: 'wrap', gap: 1 }}>
        <Box>
          <Typography variant="h5" fontWeight={800} sx={{ letterSpacing: '-0.3px' }}>
            Indicadores de Desempeño
          </Typography>
          <Typography variant="body2" color="text.secondary">
            Scorecard Integral · {cicloNombre} · {nActivos} indicadores activos
          </Typography>
        </Box>
        {dist && (
          <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center' }}>
            <Chip label={`${dist.elegibles} / ${dist.total} elegibles`} size="small"
              sx={{ bgcolor: '#e8f5e9', color: '#2e7d32', fontWeight: 700, fontSize: '0.78rem',
                height: 28, px: 0.5, border: '1px solid #a5d6a7' }} />
            <Chip label={`${dist.avgPts.toFixed(1)} pts promedio`} size="small"
              sx={{ bgcolor: '#e3f2fd', color: '#1565c0', fontWeight: 700, fontSize: '0.78rem',
                height: 28, px: 0.5, border: '1px solid #90caf9' }} />
          </Box>
        )}
      </Box>

      {/* filtros */}
      <Card elevation={0} sx={{ mb: 3, border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="País" value={paisId}
                onChange={e => { setPaisId(e.target.value); setCicloId(''); }}>
                <MenuItem value="">Todos los países</MenuItem>
                {(paises || []).map((p: any) => <MenuItem key={p.id} value={p.codigo}>{p.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField select fullWidth size="small" label="Ciclo" value={cicloId}
                onChange={e => setCicloId(e.target.value)}>
                <MenuItem value="">Todos los ciclos</MenuItem>
                {(ciclos || []).map((c: any) => <MenuItem key={c.id} value={c.id}>{cicloLabel(c)}</MenuItem>)}
              </TextField>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* KPI cards */}
      <Grid container spacing={2} mb={3}>
        {[
          { label: 'Total RMs',     value: dist?.total ?? '—',   sub: '— Equipo completo',  color: '#5c6bc0' },
          { label: 'Prom. MIP',     value: dist ? dist.avgPts.toFixed(1) : '—',
            sub: dist ? `▲ ${Math.max(0, dist.avgPts - 80).toFixed(1)} pts` : '—', color: '#1565c0' },
          { label: 'Puntaje Máx.',  value: dist ? dist.maxPts.toFixed(1) : '—',
            sub: cicloNombre, color: '#2e7d32' },
          { label: 'RMs ≥ 90 pts',  value: dist ? `${dist.excelentes} / ${dist.total}` : '—',
            sub: dist ? `▲ ${dist.elegibles} elegibles` : '—', color: '#2e7d32' },
          { label: 'EVO IR Prom.',
            value: destInd.evoIR ? `${destInd.evoIR.avg.toFixed(1)}%` : '—',
            sub: destInd.evoIR ? `${destInd.evoIR.diffPp >= 0 ? '▲' : '▼'} ${Math.abs(destInd.evoIR.diffPp).toFixed(1)} pp` : '—',
            color: '#00838f' },
          { label: 'Cob. Méd. F2',
            value: destInd.cobF2 ? `${destInd.cobF2.avg.toFixed(1)}%` : '—',
            sub: destInd.cobF2 ? `${destInd.cobF2.diffPp >= 0 ? '▲' : '▼'} ${Math.abs(destInd.cobF2.diffPp).toFixed(1)} pp` : '—',
            color: '#7b1fa2' },
        ].map(c => (
          <Grid item xs={6} sm={4} md={2} key={c.label}>
            <StatCard {...c} />
          </Grid>
        ))}
      </Grid>

      {/* gráfico + distribución */}
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>
      ) : !scorecardRows.length ? (
        <Alert severity="info">Sin indicadores configurados para este país. Importa los catálogos DIM primero.</Alert>
      ) : (
        <>
        {!hayKpiData && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Los indicadores están configurados pero aún no hay datos KPI cargados para este ciclo. Las barras mostrarán 0% hasta que se cargue el archivo ETL.
          </Alert>
        )}
        <Grid container spacing={3}>
          {/* gráfico de barras horizontal */}
          <Grid item xs={12} md={8}>
            <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <CardContent>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                  <Box sx={{ width: 3, height: 20, bgcolor: '#1565c0', borderRadius: 2 }} />
                  <Typography variant="subtitle1" fontWeight={700}>
                    Scorecard Integral de Indicadores
                  </Typography>
                </Box>

                <ResponsiveContainer width="100%" height={scorecardRows.length * 52 + 40}>
                  <BarChart
                    layout="vertical"
                    data={scorecardRows}
                    margin={{ top: 4, right: 70, left: 4, bottom: 8 }}
                    barCategoryGap="28%"
                  >
                    <CartesianGrid strokeDasharray="3 3" horizontal={false} stroke="#e8eaf6" />
                    <XAxis
                      type="number"
                      domain={[0, xMax]}
                      tickFormatter={v => `${v}%`}
                      tick={{ fontSize: 11, fill: '#78909c' }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <YAxis
                      type="category"
                      dataKey="nombreCorto"
                      width={168}
                      tick={{ fontSize: 12, fill: '#37474f', fontWeight: 500 }}
                      axisLine={false}
                      tickLine={false}
                    />
                    <Tooltip content={<ChartTooltip />} cursor={{ fill: '#f0f4ff' }} />
                    {/* línea de referencia en 100% */}
                    <ReferenceLine x={100} stroke="#90a4ae" strokeDasharray="4 3"
                      label={{ value: 'Meta 100%', position: 'top', fontSize: 10, fill: '#90a4ae' }} />
                    <Bar dataKey="avg" radius={[0, 6, 6, 0]} maxBarSize={28}>
                      {/* pts dentro de la barra */}
                      <LabelList
                        dataKey="peso"
                        position="insideLeft"
                        formatter={(v: number) => `${v} pts`}
                        style={{ fontSize: 11, fontWeight: 700, fill: 'rgba(255,255,255,0.92)' }}
                      />
                      {/* porcentaje fuera de la barra */}
                      <LabelList
                        dataKey="avg"
                        position="right"
                        formatter={(v: number) => `${v.toFixed(1)}%`}
                        style={{ fontSize: 12, fontWeight: 700, fill: '#37474f' }}
                      />
                      {scorecardRows.map((row, i) => (
                        <Cell key={i} fill={catColor(row.avg)} />
                      ))}
                    </Bar>
                  </BarChart>
                </ResponsiveContainer>

                {/* leyenda de categorías */}
                <Box sx={{ display: 'flex', gap: 2, mt: 1.5, flexWrap: 'wrap', justifyContent: 'center' }}>
                  {[
                    { label: 'Excelente ≥ 90%',    color: '#2e7d32', bg: '#e8f5e9' },
                    { label: 'Bueno 80–89%',        color: '#1565c0', bg: '#e3f2fd' },
                    { label: 'En Desarrollo 60–79%',color: '#ef6c00', bg: '#fff3e0' },
                    { label: 'Riesgo < 60%',        color: '#c62828', bg: '#ffebee' },
                  ].map(cat => (
                    <Box key={cat.label} sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
                      <Box sx={{ width: 10, height: 10, borderRadius: 1, bgcolor: cat.color }} />
                      <Typography fontSize="0.7rem" sx={{ color: cat.color, fontWeight: 600 }}>
                        {cat.label}
                      </Typography>
                    </Box>
                  ))}
                </Box>

                {/* total MIP */}
                {dist && (
                  <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                    mt: 2, pt: 2, borderTop: '1px solid #e0e7ef' }}>
                    <Box>
                      <Typography variant="caption" color="text.secondary"
                        sx={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px' }}>
                        Total Puntos MIP
                      </Typography>
                      <Typography variant="caption"
                        sx={{ display: 'block', color: 'text.secondary', fontSize: '0.68rem' }}>
                        Base: 100 puntos
                      </Typography>
                    </Box>
                    <Box sx={{ textAlign: 'right' }}>
                      <Typography variant="h4" fontWeight={900}
                        sx={{ color: catColor(dist.avgPts), lineHeight: 1 }}>
                        {dist.avgPts.toFixed(1)}
                      </Typography>
                      <Typography variant="caption"
                        sx={{ color: 'text.secondary', fontSize: '0.68rem', display: 'block', mb: 0.3 }}>
                        puntos obtenidos
                      </Typography>
                      <Chip label={catInfo(dist.avgPts).label} size="small"
                        sx={{ bgcolor: catInfo(dist.avgPts).bg, color: catInfo(dist.avgPts).color,
                          fontWeight: 700, fontSize: '0.72rem', height: 22 }} />
                    </Box>
                  </Box>
                )}
              </CardContent>
            </Card>
          </Grid>

          {/* distribución */}
          {dist && (
            <Grid item xs={12} md={4}>
              <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%' }}>
                <CardContent>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 2 }}>
                    <Box sx={{ width: 3, height: 20, bgcolor: '#1565c0', borderRadius: 2 }} />
                    <Typography variant="subtitle1" fontWeight={700}>Distribución del Equipo</Typography>
                  </Box>
                  <DistCard label="Excelente"    count={dist.excelentes}   total={dist.total}
                    rangoLabel="≥ 90 puntos MIP"  color="#2e7d32" bg="#e8f5e9" />
                  <DistCard label="Bueno"         count={dist.buenos}       total={dist.total}
                    rangoLabel="80–89 puntos MIP" color="#1565c0" bg="#e3f2fd" />
                  <DistCard label="En Desarrollo" count={dist.enDesarrollo} total={dist.total}
                    rangoLabel="60–79 puntos MIP" color="#e65100" bg="#fff3e0" />
                  <DistCard label="Crítico"       count={dist.criticos}  total={dist.total}
                    rangoLabel="menor a 60 pts"   color="#c62828" bg="#ffebee" />
                  <Divider sx={{ my: 1.5 }} />
                  <Box sx={{ p: 1.5, bgcolor: '#f8f9fa', borderRadius: 1.5, border: '1px solid #e8eaf6' }}>
                    <Typography variant="caption"
                      sx={{ color: '#5c6bc0', fontWeight: 700, textTransform: 'uppercase',
                        letterSpacing: '0.8px', fontSize: '0.6rem' }}>
                      Principio Rector:
                    </Typography>
                    <Typography variant="caption"
                      sx={{ display: 'block', color: 'text.secondary', fontStyle: 'italic',
                        fontSize: '0.72rem', mt: 0.5, lineHeight: 1.4 }}>
                      "El desempeño comercial sobresaliente impulsa la salud de los pacientes y el crecimiento sostenible de la organización."
                    </Typography>
                  </Box>
                </CardContent>
              </Card>
            </Grid>
          )}
        </Grid>
        </>
      )}
    </Box>
  );
}
