import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Grid, Card, CardContent, Typography, Box, CircularProgress,
  Alert, Divider, Chip, Table, TableBody, TableCell, TableHead, TableRow,
  LinearProgress, Select, MenuItem,
} from '@mui/material';
import {
  People, ArrowUpward, ArrowDownward,
} from '@mui/icons-material';
import {
  AreaChart, Area, XAxis, YAxis, CartesianGrid, Tooltip,
  ResponsiveContainer, PieChart, Pie, Cell,
  LabelList, RadarChart, Radar, PolarGrid, PolarAngleAxis, PolarRadiusAxis,
  ReferenceLine,
} from 'recharts';
import { api } from '../../services/api';

import { KPI_ORDEN, kpiNombre, kpiNombreCard } from '../../constants/kpi';

// ── Constante de estilo para títulos de sección (alineación uniforme) ────────
const SECTION_TITLE: React.CSSProperties = {
  fontSize: 11,
  fontWeight: 700,
  textTransform: 'uppercase',
  letterSpacing: '0.8px',
  color: 'inherit',          // usa 'text.secondary' en sx
};

// ── Helpers ─────────────────────────────────────────────────────────────────

function scoreColor(v: number): string {
  if (v >= 90) return '#2e7d32';
  if (v >= 80) return '#1565c0';
  if (v >= 60) return '#f57f17';
  return '#c62828';
}
function scoreLabel(v: number): string {
  if (v >= 90) return 'Excelente';
  if (v >= 80) return 'Bueno';
  if (v >= 60) return 'En Desarrollo';
  return 'Crítico';
}

// ── KPI Card por indicador (fila 1) ─────────────────────────────────────────

function IndicadorCard({ kpi }: { kpi: any }) {
  const pct = Number(kpi.cumplimiento_promedio_pct ?? 0);
  const delta: number | null = kpi.delta_vs_anterior ?? null;
  const color = scoreColor(pct);
  return (
    <Card elevation={1} sx={{ borderRadius: 2, height: '100%' }}>
      <CardContent sx={{ p: '14px !important' }}>
        <Typography
          sx={{ fontSize: 13, fontWeight: 700, color: 'text.secondary', lineHeight: 1.3, mb: 0.5, whiteSpace: 'pre-line' }}
          title={kpiNombre(kpi.codigo, kpi.nombre)}
        >
          {kpiNombreCard(kpi.codigo, kpi.nombre)}
        </Typography>
        <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.5, mt: 0.5 }}>
          <Typography sx={{ fontSize: 30, fontWeight: 900, color, lineHeight: 1.1 }}>
            {pct.toFixed(1)}%
          </Typography>
        </Box>
        {delta != null && (
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: delta >= 0 ? '#2e7d32' : '#c62828', lineHeight: 1.3 }}>
            {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)} pp
          </Typography>
        )}
        <LinearProgress
          variant="determinate"
          value={Math.min(pct, 100)}
          sx={{ mt: 1, height: 7, borderRadius: 3, bgcolor: `${color}20`, '& .MuiLinearProgress-bar': { bgcolor: color } }}
        />
        <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mt: 0.8 }}>
          <Chip
            label={scoreLabel(pct)}
            size="small"
            sx={{ height: 20, fontSize: 11, bgcolor: `${color}15`, color, fontWeight: 700, '& .MuiChip-label': { px: 1 } }}
          />
          <Typography sx={{ fontSize: 11, color: 'text.disabled' }}>
            {kpi.ponderacion_pct ?? '—'} pts
          </Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Card consolidado (fondo blanco, igual que el resto) ─────────────────────

function ConsolidadoCard({
  scoreProm, scoreMax, scoreMin, totalRms, elegibles, pctElegibles, tendencia, cicloNombre,
}: {
  scoreProm: number; scoreMax: number; scoreMin: number;
  totalRms: number; elegibles: number; pctElegibles: number;
  tendencia: any[]; cicloNombre?: string;
}) {
  const prev = tendencia.length >= 2
    ? Number(tendencia[tendencia.length - 2].score_promedio ?? 0)
    : null;
  const delta = prev != null ? scoreProm - prev : null;
  const prevLabel = tendencia.length >= 2
    ? (tendencia[tendencia.length - 2].ciclo_nombre ?? 'ciclo anterior')
    : 'ciclo anterior';
  const color = scoreColor(scoreProm);

  return (
    <Card elevation={2} sx={{ borderRadius: 3, height: '100%' }}>
      <CardContent sx={{ display: 'flex', flexDirection: 'column', height: '100%', boxSizing: 'border-box' }}>
        {/* Título alineado con el resto de tarjetas */}
        <Typography sx={{ ...SECTION_TITLE, color: 'text.secondary', mb: 0.3 }}>
          % Cumplimiento Global
        </Typography>
        {cicloNombre && (
          <Typography sx={{ fontSize: 11, color: 'text.secondary', mb: 0.5 }}>{cicloNombre}</Typography>
        )}

        {/* Valor principal */}
        <Typography sx={{ fontSize: 46, fontWeight: 900, color, lineHeight: 1, mt: 0.5 }}>
          {scoreProm.toFixed(1)}%
        </Typography>
        {delta != null && (
          <Typography sx={{ fontSize: 12, fontWeight: 700, color: delta >= 0 ? '#2e7d32' : '#c62828', mt: 0.4 }}>
            {delta >= 0 ? '▲' : '▼'} {Math.abs(delta).toFixed(1)} pp vs {prevLabel}
          </Typography>
        )}

        {/* Barra de progreso */}
        <Box sx={{ mt: 1.5 }}>
          <LinearProgress
            variant="determinate"
            value={Math.min(scoreProm, 100)}
            sx={{ height: 8, borderRadius: 4, bgcolor: `${color}18`, '& .MuiLinearProgress-bar': { bgcolor: color } }}
          />
          <Box sx={{ display: 'flex', justifyContent: 'space-between', mt: 0.4 }}>
            <Typography sx={{ fontSize: 9, color: 'text.disabled' }}>0%</Typography>
            <Typography sx={{ fontSize: 9, color: 'text.disabled' }}>Meta 100%</Typography>
          </Box>
        </Box>

        <Divider sx={{ my: 1.5 }} />

        {/* Grid de estadísticas */}
        <Typography sx={{ ...SECTION_TITLE, color: 'text.secondary', mb: 1 }}>
          Estadísticas del ciclo
        </Typography>
        <Box sx={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 1.2, flex: 1 }}>
          {[
            { label: 'Total RMs',    value: totalRms,                  color: '#1565c0',  size: 22 },
            { label: 'Elegibles',    value: `${elegibles}`,            color: '#2e7d32',  size: 22,
              sub: `${pctElegibles.toFixed(1)}% del equipo` },
            { label: 'Máximo ciclo', value: `${scoreMax.toFixed(1)}%`, color: '#2e7d32',  size: 17 },
            { label: 'Mínimo ciclo', value: `${scoreMin.toFixed(1)}%`, color: '#c62828',  size: 17 },
          ].map((s) => (
            <Box key={s.label}>
              <Typography sx={{ fontSize: 9, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.5 }}>
                {s.label}
              </Typography>
              <Typography sx={{ fontSize: s.size, fontWeight: 900, color: s.color, lineHeight: 1.2 }}>
                {s.value}
              </Typography>
              {s.sub && (
                <Typography sx={{ fontSize: 9, color: 'text.secondary' }}>{s.sub}</Typography>
              )}
            </Box>
          ))}
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Gráfico de tendencia con estadísticas ────────────────────────────────────

function TendenciaChart({ tendencia }: { tendencia: any[] }) {
  if (tendencia.length === 0) {
    return (
      <Box sx={{ height: 220, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
        <Typography color="text.secondary">Sin histórico de ciclos</Typography>
      </Box>
    );
  }
  const scores = tendencia.map(t => t.score_promedio);
  const min = Math.min(...scores);
  const max = Math.max(...scores);
  const avg = scores.reduce((s, v) => s + v, 0) / scores.length;
  const growth = scores.length >= 2 ? scores[scores.length - 1] - scores[0] : 0;
  const yMin = Math.max(0, Math.floor(min / 10) * 10 - 10);

  return (
    <Box>
      <ResponsiveContainer width="100%" height={200}>
        <AreaChart data={tendencia} margin={{ top: 22, right: 10, bottom: 0, left: 0 }}>
          <defs>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="5%" stopColor="#1565c0" stopOpacity={0.25} />
              <stop offset="95%" stopColor="#1565c0" stopOpacity={0.02} />
            </linearGradient>
          </defs>
          <CartesianGrid strokeDasharray="3 3" stroke="rgba(0,0,0,0.06)" />
          <XAxis dataKey="label" tick={{ fontSize: 10 }} />
          <YAxis domain={[yMin, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 9 }} width={36} />
          <Tooltip
            formatter={(v: number) => [`${v.toFixed(1)}%`, 'Cumplimiento']}
            contentStyle={{ fontSize: 12 }}
          />
          <ReferenceLine y={100} stroke="#2e7d32" strokeDasharray="5 4" strokeWidth={1} label={{ value: '100%', position: 'right', fontSize: 9, fill: '#2e7d32' }} />
          <Area
            type="monotone"
            dataKey="score_promedio"
            stroke="#1565c0"
            strokeWidth={2.5}
            fill="url(#areaGrad)"
            dot={{ r: 5, fill: '#1565c0', stroke: '#fff', strokeWidth: 2 }}
            activeDot={{ r: 7 }}
          >
            <LabelList
              dataKey="score_promedio"
              position="top"
              formatter={(v: number) => `${v.toFixed(1)}%`}
              style={{ fontSize: 10, fontWeight: 700, fill: '#1565c0' }}
            />
          </Area>
        </AreaChart>
      </ResponsiveContainer>

      <Divider sx={{ my: 1 }} />
      <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
        {[
          { label: 'Mínimo ciclo', value: `${min.toFixed(1)}%`, color: '#c62828' },
          { label: 'Promedio',     value: `${avg.toFixed(1)}%`, color: '#1565c0' },
          { label: 'Máximo ciclo', value: `${max.toFixed(1)}%`, color: '#2e7d32' },
          { label: 'Crecimiento',  value: `${growth >= 0 ? '▲' : '▼'} ${Math.abs(growth).toFixed(1)} pp`, color: growth >= 0 ? '#2e7d32' : '#c62828' },
        ].map(stat => (
          <Box key={stat.label} sx={{ textAlign: 'center' }}>
            <Typography sx={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 0.7, color: 'text.secondary' }}>
              {stat.label}
            </Typography>
            <Typography sx={{ fontSize: 16, fontWeight: 900, color: stat.color, lineHeight: 1.3 }}>
              {stat.value}
            </Typography>
          </Box>
        ))}
      </Box>
    </Box>
  );
}

// ── Panel de distribución (donut + leyenda) ──────────────────────────────────

const DIST_COLORS = ['#2e7d32', '#1565c0', '#f57f17', '#c62828'];
const DIST_LABELS = ['Excelente', 'Bueno', 'En Desarrollo', 'Crítico'];

function DistribucionPanel({ dist, totalRms }: { dist: any; totalRms: number }) {
  const distData = DIST_LABELS.map((label, i) => ({
    label,
    value: [dist.excelente, dist.bueno, dist.en_desarrollo, dist.critico][i] ?? 0,
    color: DIST_COLORS[i],
  }));
  const hasData = distData.some(d => d.value > 0);
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
      <Box sx={{ position: 'relative', flexShrink: 0, width: 110, height: 110 }}>
        <PieChart width={110} height={110}>
          <Pie
            data={hasData ? distData : [{ label: '', value: 1, color: '#e0e0e0' }]}
            dataKey="value"
            cx={53}
            cy={53}
            innerRadius={32}
            outerRadius={50}
            strokeWidth={2}
            stroke="#fff"
          >
            {(hasData ? distData : [{ label: '', value: 1, color: '#e0e0e0' }])
              .map((entry) => <Cell key={entry.label} fill={entry.color} />)}
          </Pie>
        </PieChart>
        <Box sx={{
          position: 'absolute', top: 0, left: 0, width: 110, height: 110,
          display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center',
          pointerEvents: 'none',
        }}>
          <Typography sx={{ fontSize: 20, fontWeight: 900, lineHeight: 1 }}>{totalRms}</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: 9, fontWeight: 600 }}>RMs</Typography>
        </Box>
      </Box>

      <Box sx={{ flex: 1, display: 'flex', flexDirection: 'column', gap: 0.9 }}>
        {distData.map((d) => {
          const pct = totalRms > 0 ? Math.round((d.value / totalRms) * 100) : 0;
          return (
            <Box key={d.label}>
              <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', mb: 0.25 }}>
                <Typography sx={{ fontSize: 10, fontWeight: 600, color: 'text.secondary' }}>{d.label}</Typography>
                <Box sx={{ display: 'flex', alignItems: 'baseline', gap: 0.4 }}>
                  <Typography sx={{ fontSize: 11, fontWeight: 800, color: d.color }}>{d.value}</Typography>
                  <Typography sx={{ fontSize: 9, color: 'text.disabled' }}>({pct}%)</Typography>
                </Box>
              </Box>
              <Box sx={{ height: 8, borderRadius: 4, bgcolor: `${d.color}20`, overflow: 'hidden' }}>
                <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: d.color, borderRadius: 4 }} />
              </Box>
            </Box>
          );
        })}
      </Box>
    </Box>
  );
}

// ── Fila de RM en tabla ──────────────────────────────────────────────────────

function RMRow({ rm, rank, isBottom }: { rm: any; rank: number; isBottom?: boolean }) {
  const iup = Number(rm.score_total ?? 0);
  const color = scoreColor(iup);
  const pos = rm.posicion ?? rank;
  return (
    <TableRow hover>
      <TableCell sx={{ py: 0.8, width: 32, fontWeight: 700, color: isBottom ? '#c62828' : '#1565c0', fontSize: 12 }}>
        #{pos}
      </TableCell>
      <TableCell sx={{ py: 0.8 }}>
        <Typography sx={{ fontSize: 12, fontWeight: 600 }}>{rm.rm_nombre ?? '—'}</Typography>
        <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
          {rm.linea_nombre ?? ''}{rm.gerente_nombre && rm.gerente_nombre !== '—' ? ` · ${rm.gerente_nombre}` : ''}
        </Typography>
      </TableCell>
      <TableCell sx={{ py: 0.8, textAlign: 'right' }}>
        <Box sx={{ display: 'flex', flexDirection: 'column', alignItems: 'flex-end', gap: 0.3 }}>
          <Chip
            label={`${iup.toFixed(1)}%`}
            size="small"
            sx={{ bgcolor: `${color}20`, color, fontWeight: 700, fontSize: 11 }}
          />
          <Box sx={{ width: 60, height: 4, borderRadius: 2, bgcolor: `${color}20`, overflow: 'hidden' }}>
            <Box sx={{ height: '100%', width: `${Math.min(iup, 100)}%`, bgcolor: color, borderRadius: 2 }} />
          </Box>
        </Box>
      </TableCell>
    </TableRow>
  );
}

// ── Etiqueta encima de un selector ───────────────────────────────────────────
function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontSize: 11, fontWeight: 700, color: 'text.secondary', textTransform: 'uppercase', letterSpacing: 0.8, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

// ── Página principal ─────────────────────────────────────────────────────────

export default function DashboardEjecutivo() {
  const [selectedPais,    setSelectedPais]    = useState<string | ''>('');
  const [selectedCiclo,   setSelectedCiclo]   = useState<number | ''>('');
  const [selectedLinea,   setSelectedLinea]   = useState<number | ''>('');
  const [selectedGerente, setSelectedGerente] = useState<number | ''>('');

  const handlePaisChange = (val: string | '') => {
    setSelectedPais(val);
    setSelectedCiclo('');
    setSelectedLinea('');
    setSelectedGerente('');
  };

  // Catálogos para los selectores
  const { data: catalogos } = useQuery({
    queryKey: ['dashboard-catalogos', selectedPais],
    queryFn: () =>
      api.get('/dashboard/catalogos', {
        params: selectedPais ? { pais_codigo: selectedPais } : {},
      }).then((r) => r.data),
  });

  // Datos del dashboard
  const { data, isLoading, error } = useQuery({
    queryKey: ['dashboard-ejecutivo', selectedPais, selectedCiclo, selectedLinea, selectedGerente],
    queryFn: () => {
      const params: Record<string, string | number> = {};
      if (selectedPais)    params.pais_codigo    = selectedPais;
      if (selectedCiclo)   params.ciclo_id   = Number(selectedCiclo);
      if (selectedLinea)   params.linea_id   = Number(selectedLinea);
      if (selectedGerente) params.gerente_id = Number(selectedGerente);
      return api.get('/dashboard/ejecutivo', { params }).then((r) => r.data);
    },
    retry: 1,
  });

  // Datos derivados
  const d          = data || {};
  const total_rms  = Number(d.total_rms ?? 0);
  const iupProm    = Number(d.iup_promedio ?? d.score_promedio ?? 0);
  const scoreMax   = Number(d.score_maximo ?? d.iup_maximo ?? 0);
  const scoreMin   = Number(d.score_minimo ?? d.iup_minimo ?? 0);
  const kpisInd: any[]   = d.kpis_indicadores ?? [];
  const top5: any[]      = d.top5 ?? [];
  const bottom5: any[]   = d.bottom5 ?? [];
  const gerentes: any[]  = d.top_gerentes ?? [];
  const tendencia: any[] = (d.tendencia ?? []).map((t: any) => ({
    ...t,
    label: t.ciclo_nombre ?? `C${t.ciclo_numero}`,
  }));
  const dist          = d.distribucion ?? {};
  const comp          = d.componentes_iup ?? {};
  const cicloNombre   = d.ciclo_nombre as string | undefined;

  const paises: any[]      = catalogos?.paises     ?? [];
  const ciclos: any[]      = catalogos?.ciclos      ?? [];

  // ── Auto-seleccionar República Dominicana al cargar ───────────────────
  useEffect(() => {
    if (!paises.length || selectedPais) return;
    const rd = paises.find((p: any) =>
      p.codigo?.toUpperCase() === 'RD' ||
      p.nombre?.toLowerCase().includes('dominicana')
    );
    if (rd) handlePaisChange(rd.codigo);
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Ciclo: el backend elige el correcto automáticamente cuando no hay filtro ─

  const lineas: any[]      = catalogos?.lineas      ?? [];
  const gerentesCat: any[] = catalogos?.gerentes    ?? [];

  // Etiquetas cortas para el radar (8 KPIs)
  const KPI_RADAR_LABEL: Record<string, string> = {
    COB_MD_F2:          'COB F2',
    COB_MD_F1:          'COB F1',
    PROM_DIARIO:        'Diario',
    COB_FARMACIAS:      'Farmacias',
    EVO_IR:             'EVO IR',
    VENTAS:             'Ventas',
    EVAL_CONOCIMIENTOS: 'Conoc.',
    EVAL_COACHING:      'Coach',
  };

  // Datos para el radar — 8 KPIs Real vs Meta
  const radarKpisData = [...kpisInd]
    .sort((a, b) => (KPI_ORDEN[a.codigo] ?? 99) - (KPI_ORDEN[b.codigo] ?? 99))
    .map(kpi => ({
      subject: KPI_RADAR_LABEL[kpi.codigo] ?? kpi.codigo,
      real:    Math.min(Number(kpi.cumplimiento_promedio_pct ?? 0), 120),
      meta:    100,
    }));

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Dashboard Ejecutivo</Typography>
      <Typography variant="body2" color="text.secondary" mb={1.5}>
        Indicadores estratégicos MIP — Vista de Presidencia
      </Typography>

      {/* ── Barra de filtros ─────────────────────────────────────────────── */}
      <Card elevation={1} sx={{ borderRadius: 2, mb: 2.5 }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', gap: 3, alignItems: 'center', flexWrap: 'wrap' }}>

            {/* Los 4 selectores con el mismo ancho para alineación perfecta */}
            {[
              {
                label: 'País',
                value: selectedPais,
                onChange: (v: any) => handlePaisChange(v),
                placeholder: 'Todos los países',
                options: paises.map((p: any) => ({ id: p.codigo, nombre: p.nombre })),
                disabled: false,
              },
              {
                label: 'Ciclo',
                value: selectedCiclo,
                onChange: (v: any) => setSelectedCiclo(v === '' ? '' : Number(v)),
                placeholder: selectedPais ? 'Último ciclo con datos' : 'Seleccione un país',
                options: ciclos.map((c: any) => ({ id: c.id, nombre: c.nombre ?? c.nombre_canonico })),
                disabled: !selectedPais,
              },
              {
                label: 'Línea Terapéutica',
                value: selectedLinea,
                onChange: (v: any) => setSelectedLinea(v === '' ? '' : Number(v)),
                placeholder: 'Todas las líneas',
                options: lineas.map((l: any) => ({ id: l.id, nombre: l.nombre })),
                disabled: false,
              },
              {
                label: 'Gerente de Distrito',
                value: selectedGerente,
                onChange: (v: any) => setSelectedGerente(v === '' ? '' : Number(v)),
                placeholder: 'Todos los gerentes',
                options: gerentesCat.map((g: any) => ({ id: g.id, nombre: g.nombre })),
                disabled: false,
              },
            ].map((f) => (
              <Box key={f.label} sx={{ width: 205 }}>
                <FilterLabel>{f.label}</FilterLabel>
                <Select
                  size="small"
                  fullWidth
                  value={f.value}
                  onChange={(e) => f.onChange(e.target.value)}
                  displayEmpty
                  disabled={f.disabled}
                >
                  <MenuItem value=""><em>{f.placeholder}</em></MenuItem>
                  {f.options.map((o) => <MenuItem key={o.id} value={o.id}>{o.nombre}</MenuItem>)}
                </Select>
              </Box>
            ))}

            {cicloNombre && (
              <Box sx={{ ml: 'auto' }}>
                <Chip
                  label={`Mostrando: ${cicloNombre}`}
                  sx={{ bgcolor: '#1a237e', color: '#fff', fontWeight: 700, fontSize: 15, height: 36, px: 1.5, letterSpacing: 0.5, borderRadius: 2 }}
                />
              </Box>
            )}

          </Box>
        </CardContent>
      </Card>

      {/* ── Estado de carga / error ──────────────────────────────────────── */}
      {isLoading && (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}>
          <CircularProgress size={48} />
        </Box>
      )}
      {error && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          No se pudo cargar el dashboard. Verifique que hay datos cargados en el sistema.
        </Alert>
      )}

      {!isLoading && !error && (
        <>
          {/* ── Fila 1: KPIs por indicador ─────────────────────────────── */}
          {kpisInd.length > 0 && (
            <Box
              sx={{
                display: 'grid',
                gridTemplateColumns: `repeat(${Math.min(Math.max(kpisInd.length, 4), 8)}, 1fr)`,
                gap: 1.5,
                mt: 1,
                mb: 2.5,
              }}
            >
              {[...kpisInd]
                .sort((a, b) => (KPI_ORDEN[a.codigo] ?? 99) - (KPI_ORDEN[b.codigo] ?? 99))
                .map((kpi) => (
                  <IndicadorCard key={kpi.codigo} kpi={kpi} />
                ))}
            </Box>
          )}

          {/* ── Fila 2: Consolidado + Tendencia + Radar/Distribución ───── */}
          <Grid container spacing={2} mb={2.5} alignItems="stretch">

            {/* Card consolidado oscuro */}
            <Grid item xs={12} md={3}>
              <ConsolidadoCard
                scoreProm={iupProm}
                scoreMax={scoreMax}
                scoreMin={scoreMin}
                totalRms={total_rms}
                elegibles={Number(d.total_elegibles ?? 0)}
                pctElegibles={Number(d.pct_elegibles ?? 0)}
                tendencia={tendencia}
                cicloNombre={cicloNombre}
              />
            </Grid>

            {/* Tendencia histórica con estadísticas */}
            <Grid item xs={12} md={6}>
              <Card elevation={2} sx={{ borderRadius: 3, height: '100%' }}>
                <CardContent>
                  <Typography sx={{ ...SECTION_TITLE, color: 'text.secondary', mb: 0.5 }}>
                    Tendencia de Cumplimiento Histórica
                  </Typography>
                  <Divider sx={{ mb: 1.5 }} />
                  <TendenciaChart tendencia={tendencia} />
                </CardContent>
              </Card>
            </Grid>

            {/* Radar + Distribución */}
            <Grid item xs={12} md={3}>
              <Box sx={{ display: 'flex', flexDirection: 'column', gap: 2, height: '100%' }}>

                {/* Radar KPIs — 8 indicadores Real vs Meta */}
                <Card elevation={2} sx={{ borderRadius: 3, flex: 1 }}>
                  <CardContent sx={{ pb: '12px !important', height: '100%', boxSizing: 'border-box' }}>
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
                      <Box sx={{ width: 3, height: 14, borderRadius: 2, bgcolor: 'primary.main' }} />
                      <Typography sx={{ ...SECTION_TITLE, color: 'text.secondary' }}>
                        Scorecard Radar
                      </Typography>
                    </Box>

                    {radarKpisData.length > 0 ? (
                      <>
                        <ResponsiveContainer width="100%" height={178}>
                          <RadarChart data={radarKpisData} margin={{ top: 12, right: 22, bottom: 8, left: 22 }}>
                            <PolarGrid stroke="rgba(0,0,0,0.1)" />
                            <PolarAngleAxis
                              dataKey="subject"
                              tick={{ fill: 'rgba(0,0,0,0.6)', fontSize: 9, fontWeight: 600 }}
                            />
                            <PolarRadiusAxis domain={[0, 100]} tick={false} axisLine={false} />
                            {/* Meta — línea punteada verde */}
                            <Radar
                              name="Meta"
                              dataKey="meta"
                              stroke="#4caf50"
                              fill="#4caf50"
                              fillOpacity={0.08}
                              strokeWidth={1.5}
                              strokeDasharray="4 3"
                            />
                            {/* Real — relleno azul primario */}
                            <Radar
                              name="Real"
                              dataKey="real"
                              stroke="#1976d2"
                              fill="#1976d2"
                              fillOpacity={0.22}
                              strokeWidth={2.2}
                              dot={{ r: 3.5, fill: '#1976d2', strokeWidth: 0 }}
                            />
                          </RadarChart>
                        </ResponsiveContainer>

                        {/* Leyenda */}
                        <Box sx={{ display: 'flex', justifyContent: 'center', gap: 3, mt: 0.5 }}>
                          {[
                            { color: '#1976d2', label: 'Real' },
                            { color: '#4caf50', label: 'Meta' },
                          ].map(l => (
                            <Box key={l.label} sx={{ display: 'flex', alignItems: 'center', gap: 0.6 }}>
                              <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: l.color }} />
                              <Typography sx={{ fontSize: 10, color: 'text.secondary', fontWeight: 600 }}>
                                {l.label}
                              </Typography>
                            </Box>
                          ))}
                        </Box>
                      </>
                    ) : (
                      <Box sx={{ height: 178, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                        <Typography sx={{ color: 'text.disabled', fontSize: 12 }}>
                          Sin datos KPI
                        </Typography>
                      </Box>
                    )}
                  </CardContent>
                </Card>

                {/* Distribución del equipo */}
                <Card elevation={2} sx={{ borderRadius: 3, flex: 1 }}>
                  <CardContent sx={{ pb: '10px !important' }}>
                    <Typography sx={{ ...SECTION_TITLE, color: 'text.secondary', mb: 1 }}>
                      Distribución del Equipo
                    </Typography>
                    <DistribucionPanel dist={dist} totalRms={total_rms} />
                  </CardContent>
                </Card>

              </Box>
            </Grid>
          </Grid>

          {/* ── Fila 3: Top 5 / Bottom 5 / Top Gerentes ────────────────── */}
          <Grid container spacing={2} alignItems="stretch">

            {/* Top 5 representantes */}
            <Grid item xs={12} md={4} sx={{ display: 'flex' }}>
              <Card elevation={2} sx={{ borderRadius: 3, width: '100%', display: 'flex', flexDirection: 'column' }}>
                <CardContent sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mb: 1.5 }}>
                    <ArrowUpward sx={{ color: '#2e7d32', fontSize: 16 }} />
                    <Typography sx={{ ...SECTION_TITLE, fontSize: 9, color: 'text.secondary' }}>
                      Top 5 Representantes
                    </Typography>
                  </Box>
                  <Divider sx={{ mb: 0.5 }} />
                  {top5.length > 0 ? (
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10 }}>#</TableCell>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10 }}>Representante</TableCell>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10, textAlign: 'right' }}>MIP</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {top5.map((rm, i) => <RMRow key={rm.rm_id} rm={rm} rank={i + 1} />)}
                      </TableBody>
                    </Table>
                  ) : (
                    <Typography color="text.secondary" sx={{ py: 2, fontSize: 13 }}>Sin datos</Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Bottom 5 representantes */}
            <Grid item xs={12} md={4} sx={{ display: 'flex' }}>
              <Card elevation={2} sx={{ borderRadius: 3, width: '100%', display: 'flex', flexDirection: 'column' }}>
                <CardContent sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mb: 1.5 }}>
                    <ArrowDownward sx={{ color: '#c62828', fontSize: 16 }} />
                    <Typography sx={{ ...SECTION_TITLE, fontSize: 9, color: 'text.secondary' }}>
                      Bottom 5 Representantes
                    </Typography>
                  </Box>
                  <Divider sx={{ mb: 0.5 }} />
                  {bottom5.length > 0 ? (
                    <Table size="small">
                      <TableHead>
                        <TableRow>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10 }}>#</TableCell>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10 }}>Representante</TableCell>
                          <TableCell sx={{ py: 0.4, fontWeight: 700, fontSize: 10, textAlign: 'right' }}>MIP</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {bottom5.map((rm, i) => <RMRow key={rm.rm_id} rm={rm} rank={i + 1} isBottom />)}
                      </TableBody>
                    </Table>
                  ) : (
                    <Typography color="text.secondary" sx={{ py: 2, fontSize: 13 }}>Sin datos</Typography>
                  )}
                </CardContent>
              </Card>
            </Grid>

            {/* Top gerentes + resumen */}
            <Grid item xs={12} md={4} sx={{ display: 'flex' }}>
              <Card elevation={2} sx={{ borderRadius: 3, width: '100%', display: 'flex', flexDirection: 'column' }}>
                <CardContent sx={{ flex: 1 }}>
                  <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, mb: 1.5 }}>
                    <People sx={{ color: '#6a1b9a', fontSize: 16 }} />
                    <Typography sx={{ ...SECTION_TITLE, fontSize: 9, color: 'text.secondary' }}>
                      Top Gerentes de Distrito
                    </Typography>
                  </Box>
                  <Divider sx={{ mb: 1.5 }} />
                  {gerentes.length > 0 ? (
                    <Box sx={{ display: 'flex', flexDirection: 'column', gap: 1.5 }}>
                      {gerentes.slice(0, 5).map((g: any) => {
                        const iup = Number(g.score_promedio ?? g.iup_promedio ?? 0);
                        const col = scoreColor(iup);
                        return (
                          <Box key={g.gerente_id}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 0.4 }}>
                              <Box>
                                <Typography sx={{ fontSize: 12, fontWeight: 700 }}>{g.gerente_nombre}</Typography>
                                <Typography variant="caption" color="text.secondary" sx={{ fontSize: 10 }}>
                                  {g.total_rms} RMs
                                </Typography>
                              </Box>
                              <Typography sx={{ fontSize: 17, fontWeight: 900, color: col }}>{iup.toFixed(1)}%</Typography>
                            </Box>
                            <LinearProgress
                              variant="determinate"
                              value={Math.min(iup, 100)}
                              sx={{ height: 7, borderRadius: 4, bgcolor: `${col}20`, '& .MuiLinearProgress-bar': { bgcolor: col } }}
                            />
                          </Box>
                        );
                      })}
                    </Box>
                  ) : (
                    <Typography color="text.secondary" sx={{ py: 2, fontSize: 13 }}>Sin datos de gerentes</Typography>
                  )}

                  {/* Resumen del equipo */}
                  {total_rms > 0 && (
                    <Box sx={{
                      mt: 2.5, p: 1.5, borderRadius: 2,
                      bgcolor: 'rgba(0,0,0,0.04)',
                      border: '1px solid rgba(0,0,0,0.07)',
                    }}>
                      <Typography sx={{ fontSize: 9, textTransform: 'uppercase', letterSpacing: 1, color: 'text.secondary', fontWeight: 700, mb: 1 }}>
                        Resumen del equipo
                      </Typography>
                      <Box sx={{ display: 'flex', justifyContent: 'space-around' }}>
                        {[
                          { label: 'Total RMs',  value: total_rms,                        color: '#1565c0' },
                          { label: 'Elegibles',  value: d.total_elegibles ?? 0,           color: '#2e7d32' },
                          { label: 'IUP Prom.',  value: `${iupProm.toFixed(0)}%`,         color: scoreColor(iupProm) },
                        ].map(stat => (
                          <Box key={stat.label} sx={{ textAlign: 'center' }}>
                            <Typography sx={{ fontSize: 22, fontWeight: 900, color: stat.color, lineHeight: 1 }}>
                              {stat.value}
                            </Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: 9 }}>
                              {stat.label}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    </Box>
                  )}
                </CardContent>
              </Card>
            </Grid>

          </Grid>
        </>
      )}
    </Box>
  );
}
