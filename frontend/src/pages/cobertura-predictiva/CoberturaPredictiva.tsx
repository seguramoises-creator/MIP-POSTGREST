/**
 * CoberturaPredictiva.tsx
 * Módulo 4DX — Cobertura Predictiva y Ritmo de Ejecución
 * Metodología: lead measures sobre médicos únicos visitados y cadencia diaria.
 * Fuente de datos: cat.KpiCoberturaPredictiva (vía cat.vwDashboardCoberturaPredictivaGD)
 */

import React, { useState, useCallback, useMemo } from 'react';
import {
  Box, Typography, Paper, Tab, Tabs, Grid, Card, CardContent,
  FormControl, InputLabel, Select, MenuItem, Chip, Alert,
  TableContainer, Table, TableHead, TableRow, TableCell, TableBody,
  LinearProgress, CircularProgress, Button, Tooltip, Divider,
  Collapse, IconButton, TextField, Stack, Badge, Autocomplete,
} from '@mui/material';
import {
  TrendingUp, Warning, CheckCircle, Cancel,
  Refresh, ExpandMore, ExpandLess,
  CalendarToday, People, FlagOutlined, SpeedOutlined,
  ArrowUpward, ArrowDownward,
} from '@mui/icons-material';
import {
  ResponsiveContainer, BarChart, Bar, XAxis, YAxis,
  CartesianGrid, Tooltip as RechartTooltip, Legend,
  ReferenceLine, Cell,
} from 'recharts';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { api } from '../../services/api';

// ── Colores de semáforo ───────────────────────────────────────────────────────
const SEM: Record<string, string> = {
  Verde: '#2e7d32',
  Amarillo: '#f57c00',
  Rojo: '#c62828',
};
const SEM_BG: Record<string, string> = {
  Verde: '#e8f5e9',
  Amarillo: '#fff3e0',
  Rojo: '#ffebee',
};

// ── Tipos ─────────────────────────────────────────────────────────────────────
interface Ciclo {
  ciclo_key: number;
  codigo_ciclo: string;
  linea: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  dias_habiles_ciclo: number | null;
  meta_cobertura_pct: number;
  pais_codigo: string;
  pais_nombre: string;
  cerrado?: boolean;
  abierto?: boolean;
}

interface DetalleRM {
  kpi_key: number;
  codigo_representante: string;
  nombre_vm: string;
  linea: string | null;
  gd: string | null;
  medicos_programados: number;
  medicos_visitados_unicos: number;
  cobertura_actual_pct: number;
  cobertura_esperada_pct: number;
  cobertura_proyectada_pct: number;
  meta_cobertura_pct: number;
  brecha_actual_vs_esperada_pct: number;
  brecha_proyectada_vs_meta_pct: number;
  medicos_requeridos_meta: number;
  medicos_pendientes_meta: number;
  medicos_diarios_requeridos: number;
  contactos_meta_ciclo: number;
  contactos_realizados: number;
  cumplimiento_contactos_pct: number;
  contactos_proyectados: number;
  contactos_pendientes: number;
  contactos_diarios_requeridos: number;
  dias_habiles_totales: number;
  dias_habiles_transcurridos: number;
  dias_habiles_restantes: number;
  estado_cobertura: 'Verde' | 'Amarillo' | 'Rojo';
  estado_ritmo: 'Verde' | 'Amarillo' | 'Rojo';
  estado_psp: 'Verde' | 'Amarillo' | 'Rojo';
  lectura_accionable: string | null;
}

interface DashboardData {
  ok: boolean;
  mensaje?: string;
  fuente?: string;
  ciclo?: { codigo: string; fecha_inicio: string; fecha_fin: string; meta_cobertura_pct: number };
  fecha_corte?: string;
  total_rms: number;
  cobertura_actual_promedio_pct: number;
  cobertura_esperada_promedio_pct: number;
  cobertura_proyectada_promedio_pct: number;
  meta_cobertura_pct: number;
  medicos_programados_total: number;
  medicos_unicos_visitados_total: number;
  contactos_realizados_total: number;
  contactos_meta_total: number;
  medicos_diarios_requeridos_max: number;
  rms_en_verde: number;
  rms_en_amarillo: number;
  rms_en_rojo: number;
  rms_psp_verde: number;
  rms_psp_rojo: number;
  pct_rms_en_riesgo: number;
  dias_habiles_totales: number;
  dias_habiles_transcurridos: number;
  dias_habiles_restantes: number;
  detalle_rms: DetalleRM[];
}

// ── Tipos: Cobertura por Categoría ───────────────────────────────────────────
interface CoberturaCategoria {
  categoria: string;          // A, B, C, D
  total_programados: number;
  visitados: number;
  pendientes: number;
  pct_visita: number;
}

// ── Panel: Cobertura por categoría de médico ──────────────────────────────────
const COLORES_CAT: Record<string, { main: string; bg: string; text: string }> = {
  A: { main: '#1b5e20', bg: '#e8f5e9', text: '#1b5e20' },
  B: { main: '#0d47a1', bg: '#e3f2fd', text: '#0d47a1' },
  C: { main: '#e65100', bg: '#fff3e0', text: '#e65100' },
  D: { main: '#b71c1c', bg: '#ffebee', text: '#b71c1c' },
};
const ETIQUETAS_CAT: Record<string, string> = {
  A: 'Alto potencial',
  B: 'Potencial medio',
  C: 'Potencial bajo',
  D: 'Sin prioridad',
};

const CoberturaPorCategoriaPanel = ({ data }: { data: CoberturaCategoria[] }) => {
  if (!data || data.length === 0) return (
    <Alert severity="info" sx={{ mt: 0 }}>
      Sin médicos planeados con categoría. Planifica el ciclo (Planeación) y verifica que los médicos tengan categoría A/B/C/D en el Panel Médico.
    </Alert>
  );

  const total_prog = data.reduce((s, r) => s + r.total_programados, 0);
  const total_vis  = data.reduce((s, r) => s + r.visitados, 0);
  const total_pend = data.reduce((s, r) => s + r.pendientes, 0);

  return (
    <Box>
      {/* Resumen global */}
      <Box display="flex" gap={2} mb={2} flexWrap="wrap">
        {[
          { label: 'Total programados', value: total_prog, color: '#1565c0' },
          { label: 'Visitados', value: total_vis, color: '#2e7d32' },
          { label: 'Pendientes', value: total_pend, color: '#c62828' },
          { label: '% Cobertura global', value: `${total_prog > 0 ? ((total_vis / total_prog) * 100).toFixed(1) : 0}%`, color: '#6a1b9a' },
        ].map(item => (
          <Box key={item.label} sx={{ flex: '1 1 110px', textAlign: 'center', p: 1, borderRadius: 2, bgcolor: '#f8f9fa', border: '1px solid #e0e0e0' }}>
            <Typography variant="h6" fontWeight={800} sx={{ color: item.color }}>{item.value}</Typography>
            <Typography variant="caption" color="text.secondary" display="block">{item.label}</Typography>
          </Box>
        ))}
      </Box>

      {/* Barras por categoría */}
      {data.map(row => {
        const col = COLORES_CAT[row.categoria] ?? COLORES_CAT['D'];
        const pct = Math.min(row.pct_visita, 100);
        return (
          <Box key={row.categoria} sx={{ mb: 2 }}>
            <Box display="flex" alignItems="center" justifyContent="space-between" mb={0.5}>
              <Box display="flex" alignItems="center" gap={1}>
                <Box sx={{
                  width: 32, height: 32, borderRadius: '50%', display: 'flex',
                  alignItems: 'center', justifyContent: 'center',
                  bgcolor: col.main, color: '#fff', fontWeight: 800, fontSize: 14,
                }}>
                  {row.categoria}
                </Box>
                <Box>
                  <Typography variant="body2" fontWeight={700} sx={{ color: col.text }}>
                    Categoría {row.categoria}
                    <Typography component="span" variant="caption" color="text.secondary" ml={0.5}>
                      — {ETIQUETAS_CAT[row.categoria] ?? ''}
                    </Typography>
                  </Typography>
                </Box>
              </Box>
              <Box textAlign="right">
                <Typography variant="body2" fontWeight={800} sx={{ color: col.main }}>
                  {row.visitados} <Typography component="span" variant="caption" color="text.secondary">/ {row.total_programados} méd.</Typography>
                </Typography>
                <Typography variant="caption" color="text.secondary">
                  {row.pendientes} pendientes
                </Typography>
              </Box>
            </Box>

            {/* Barra dual: visitados (relleno) + pendientes (fondo) */}
            <Tooltip
              title={`${row.visitados} visitados · ${row.pendientes} pendientes · ${pct.toFixed(1)}%`}
              arrow
            >
              <Box sx={{ position: 'relative', height: 20, bgcolor: col.bg, borderRadius: 3, overflow: 'hidden', border: `1px solid ${col.main}33`, cursor: 'default' }}>
                {/* Barra de visitados */}
                <Box sx={{
                  position: 'absolute', left: 0, top: 0, bottom: 0,
                  width: `${pct}%`,
                  bgcolor: col.main,
                  borderRadius: '3px 0 0 3px',
                  transition: 'width 0.6s cubic-bezier(0.4,0,0.2,1)',
                  display: 'flex', alignItems: 'center', justifyContent: 'flex-end', pr: 0.5,
                }}>
                  {pct > 15 && (
                    <Typography sx={{ color: '#fff', fontSize: 11, fontWeight: 700, lineHeight: 1 }}>
                      {pct.toFixed(0)}%
                    </Typography>
                  )}
                </Box>
                {/* Etiqueta flotante si el avance es muy bajo */}
                {pct <= 15 && (
                  <Typography sx={{
                    position: 'absolute', left: `${pct + 1}%`, top: '50%', transform: 'translateY(-50%)',
                    color: col.text, fontSize: 11, fontWeight: 700, lineHeight: 1,
                  }}>
                    {pct.toFixed(0)}%
                  </Typography>
                )}
              </Box>
            </Tooltip>
          </Box>
        );
      })}
    </Box>
  );
};

// ── Chip semáforo ─────────────────────────────────────────────────────────────
const SemaforoChip = ({ estado, label }: { estado: string; label?: string }) => (
  <Chip
    size="small"
    label={label ?? estado}
    icon={
      estado === 'Verde' ? <CheckCircle fontSize="small" /> :
      estado === 'Amarillo' ? <Warning fontSize="small" /> :
      <Cancel fontSize="small" />
    }
    sx={{
      bgcolor: SEM_BG[estado] ?? '#f5f5f5',
      color: SEM[estado] ?? '#666',
      border: `1px solid ${SEM[estado] ?? '#ccc'}`,
      fontWeight: 600,
      '& .MuiChip-icon': { color: SEM[estado] ?? '#666' },
    }}
  />
);

// ── KPI Card ──────────────────────────────────────────────────────────────────
const KpiCard = ({
  title, value, subtitle, color, icon, xs = 6, sm = 3,
}: {
  title: string; value: React.ReactNode; subtitle?: string;
  color?: string; icon?: React.ReactNode; xs?: number; sm?: number;
}) => (
  <Grid item xs={xs} sm={sm}>
    <Card elevation={2} sx={{ borderRadius: 2, height: '100%', borderTop: `4px solid ${color ?? '#1565c0'}` }}>
      <CardContent sx={{ py: 1.5, px: 2 }}>
        <Box display="flex" alignItems="center" gap={1} mb={0.5}>
          {icon && <Box sx={{ color: color ?? '#1565c0', display: 'flex' }}>{icon}</Box>}
          <Typography variant="caption" color="text.secondary" fontWeight={600} textTransform="uppercase">
            {title}
          </Typography>
        </Box>
        <Typography variant="h5" fontWeight={700} sx={{ color: color ?? 'text.primary' }}>
          {value}
        </Typography>
        {subtitle && <Typography variant="caption" color="text.secondary">{subtitle}</Typography>}
      </CardContent>
    </Card>
  </Grid>
);

// ── Barra de progreso con meta ────────────────────────────────────────────────
const BarraMeta = ({ actual, esperada, meta }: { actual: number; esperada: number; meta: number }) => {
  const color = actual >= meta ? '#2e7d32' : actual >= esperada * 0.95 ? '#f57c00' : '#c62828';
  return (
    <Box sx={{ width: '100%' }}>
      <Box display="flex" justifyContent="space-between" mb={0.3}>
        <Typography variant="caption" fontWeight={600} sx={{ color }}>{actual.toFixed(1)}%</Typography>
        <Typography variant="caption" color="text.secondary">Meta {meta.toFixed(0)}%</Typography>
      </Box>
      <Box sx={{ position: 'relative', height: 10, bgcolor: '#f0f0f0', borderRadius: 5, overflow: 'hidden' }}>
        <Box sx={{ position: 'absolute', height: '100%', width: `${Math.min(actual, 100)}%`, bgcolor: color, borderRadius: 5, transition: 'width 0.4s' }} />
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${Math.min(esperada, 100)}%`, width: 2, bgcolor: '#f57c00', opacity: 0.8 }} />
        <Box sx={{ position: 'absolute', top: 0, bottom: 0, left: `${Math.min(meta, 100)}%`, width: 2, bgcolor: '#1565c0' }} />
      </Box>
      <Typography variant="caption" color="#f57c00">Esperado: {esperada.toFixed(1)}%</Typography>
    </Box>
  );
};

// ── Dashboard tab ─────────────────────────────────────────────────────────────
const DashboardTab = ({
  data, loading, error,
  catData, catLoading, filtroVM,
}: {
  data?: DashboardData; loading: boolean; error: string | null;
  catData?: CoberturaCategoria[]; catLoading?: boolean; filtroVM?: string;
}) => {
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [sortField, setSortField] = useState<keyof DetalleRM>('estado_cobertura');
  const [sortDir, setSortDir] = useState<'asc' | 'desc'>('asc');

  const sortedRMs = useMemo(() => {
    if (!data?.detalle_rms) return [];
    // Item 9 (Mallén): filtro por representante. Si el valor coincide EXACTO con un código
    // (selección del desplegable) se filtra por código exacto — así "VM-1" no arrastra a
    // "VM-11". Al teclear libre, se hace búsqueda por coincidencia en nombre o código.
    const q = (filtroVM ?? '').trim().toLowerCase();
    const esCodigoExacto = !!q && data.detalle_rms.some(r => (r.codigo_representante ?? '').toLowerCase() === q);
    const base = !q
      ? data.detalle_rms
      : esCodigoExacto
        ? data.detalle_rms.filter(r => (r.codigo_representante ?? '').toLowerCase() === q)
        : data.detalle_rms.filter(r =>
            (r.nombre_vm ?? '').toLowerCase().includes(q) ||
            (r.codigo_representante ?? '').toLowerCase().includes(q));
    const order: Record<string, number> = { Verde: 0, Amarillo: 1, Rojo: 2 };
    return [...base].sort((a, b) => {
      const av = sortField === 'estado_cobertura' ? (order[a.estado_cobertura] ?? 0) : (a[sortField] as number);
      const bv = sortField === 'estado_cobertura' ? (order[b.estado_cobertura] ?? 0) : (b[sortField] as number);
      return sortDir === 'asc' ? (av > bv ? 1 : -1) : (av < bv ? 1 : -1);
    });
  }, [data?.detalle_rms, sortField, sortDir, filtroVM]);

  const handleSort = (field: keyof DetalleRM) => {
    if (field === sortField) setSortDir(d => d === 'asc' ? 'desc' : 'asc');
    else { setSortField(field); setSortDir('asc'); }
  };

  if (loading) return (
    <Box display="flex" justifyContent="center" alignItems="center" height={300}>
      <CircularProgress />
      <Typography ml={2} color="text.secondary">Cargando dashboard 4DX…</Typography>
    </Box>
  );

  if (error) return (
    <Alert severity={error.includes('Sin datos') ? 'info' : 'error'} sx={{ mt: 2 }}>
      {error}
    </Alert>
  );

  if (!data) return null;

  // Cuando hay un representante filtrado, las tarjetas KPI de arriba deben reflejar
  // SOLO ese subconjunto (antes mostraban siempre el agregado país → "no cambia").
  const filtroActivo = !!(filtroVM ?? '').trim();
  const resumen = (() => {
    if (!filtroActivo) return data;
    const rms = sortedRMs;
    const sum = (f: (r: DetalleRM) => number) => rms.reduce((a, r) => a + (f(r) || 0), 0);
    const avg = (f: (r: DetalleRM) => number) => (rms.length ? sum(f) / rms.length : 0);
    const cnt = (e: string) => rms.filter(r => r.estado_cobertura === e).length;
    return {
      ...data,
      total_rms: rms.length,
      cobertura_actual_promedio_pct: avg(r => r.cobertura_actual_pct),
      cobertura_proyectada_promedio_pct: avg(r => r.cobertura_proyectada_pct),
      medicos_programados_total: sum(r => r.medicos_programados),
      medicos_unicos_visitados_total: sum(r => r.medicos_visitados_unicos),
      contactos_realizados_total: sum(r => r.contactos_realizados),
      contactos_meta_total: sum(r => r.contactos_meta_ciclo),
      medicos_diarios_requeridos_max: rms.reduce((m, r) => Math.max(m, r.medicos_diarios_requeridos || 0), 0),
      rms_en_verde: cnt('Verde'),
      rms_en_amarillo: cnt('Amarillo'),
      rms_en_rojo: cnt('Rojo'),
    };
  })();

  const progresoCiclo = data.dias_habiles_totales
    ? Math.round(data.dias_habiles_transcurridos / data.dias_habiles_totales * 100)
    : 0;

  const chartCobertura = sortedRMs.slice(0, 15).map(r => ({
    name: r.nombre_vm || r.codigo_representante,
    actual: +r.cobertura_actual_pct.toFixed(1),
    proyectada: +r.cobertura_proyectada_pct.toFixed(1),
    fill: SEM[r.estado_cobertura],
  }));

  const chartRitmo = sortedRMs.slice(0, 15).map(r => ({
    name: r.nombre_vm || r.codigo_representante,
    medicos_dia: r.medicos_diarios_requeridos,
    contactos_dia: r.contactos_diarios_requeridos,
    fill: SEM[r.estado_ritmo],
  }));
  // El "ritmo diario requerido" es 0 cuando no quedan días hábiles en el ciclo
  // (transcurridos = totales). En ese caso el gráfico saldría vacío: mostramos un
  // mensaje claro en vez de barras en cero.
  const ritmoSinDias = (data.dias_habiles_restantes ?? 0) <= 0;

  return (
    <Box>
      {/* Progreso del ciclo */}
      <Paper sx={{ p: 2, mb: 2, borderRadius: 2, bgcolor: '#e3f2fd' }}>
        <Box display="flex" alignItems="center" justifyContent="space-between" flexWrap="wrap" gap={1}>
          <Box display="flex" alignItems="center" gap={1}>
            <CalendarToday sx={{ color: '#1565c0' }} />
            <Typography fontWeight={700} color="#1565c0">
              Ciclo {data.ciclo?.codigo} · Corte: {data.fecha_corte}
            </Typography>
            {data.fuente && <Chip label={data.fuente} size="small" sx={{ bgcolor: '#bbdefb', color: '#0d47a1', fontWeight: 600 }} />}
          </Box>
          <Box display="flex" alignItems="center" gap={2}>
            <Typography variant="body2" color="text.secondary">
              <b>{data.dias_habiles_transcurridos}</b> / {data.dias_habiles_totales} días hábiles ({data.dias_habiles_restantes} restantes)
            </Typography>
          </Box>
        </Box>
        <Box mt={1.5}>
          <LinearProgress
            variant="determinate"
            value={progresoCiclo}
            sx={{ height: 12, borderRadius: 6, bgcolor: '#bbdefb', '& .MuiLinearProgress-bar': { bgcolor: '#1565c0' } }}
          />
          <Typography variant="caption" color="#1565c0" fontWeight={600}>
            {progresoCiclo}% del ciclo transcurrido
          </Typography>
        </Box>
      </Paper>

      {/* KPI Cards */}
      <Grid container spacing={1.5} mb={2}>
        <KpiCard
          title="Cobertura actual promedio"
          value={`${resumen.cobertura_actual_promedio_pct.toFixed(1)}%`}
          subtitle={`Meta: ${data.meta_cobertura_pct?.toFixed(0) ?? 90}%`}
          color={resumen.cobertura_actual_promedio_pct >= (data.meta_cobertura_pct ?? 90) ? '#2e7d32' : '#c62828'}
          icon={<People />}
        />
        <KpiCard
          title="Cobertura proyectada"
          value={`${resumen.cobertura_proyectada_promedio_pct.toFixed(1)}%`}
          subtitle="Run-rate al fin de ciclo"
          color={resumen.cobertura_proyectada_promedio_pct >= (data.meta_cobertura_pct ?? 90) ? '#2e7d32' : '#f57c00'}
          icon={<TrendingUp />}
        />
        <KpiCard
          title="Médicos visitados / Prog."
          value={`${resumen.medicos_unicos_visitados_total} / ${resumen.medicos_programados_total}`}
          subtitle="Médicos únicos"
          color="#1565c0"
          icon={<FlagOutlined />}
        />
        <KpiCard
          title="Contactos realizados"
          value={resumen.contactos_realizados_total.toLocaleString()}
          subtitle={`Meta: ${resumen.contactos_meta_total.toLocaleString()}`}
          color="#6a1b9a"
          icon={<SpeedOutlined />}
        />
        <KpiCard title="RMs en Verde" value={resumen.rms_en_verde} subtitle={`de ${resumen.total_rms}`} color="#2e7d32" icon={<CheckCircle />} xs={6} sm={2} />
        <KpiCard title="RMs en Amarillo" value={resumen.rms_en_amarillo} subtitle="Seguimiento" color="#f57c00" icon={<Warning />} xs={6} sm={2} />
        <KpiCard title="RMs en Rojo" value={resumen.rms_en_rojo} subtitle="Acción inmediata" color="#c62828" icon={<Cancel />} xs={6} sm={2} />
        <KpiCard title="Méd. diarios req. (máx)" value={resumen.medicos_diarios_requeridos_max} subtitle="VM más atrasado" color="#c62828" icon={<ArrowUpward />} xs={6} sm={2} />
      </Grid>

      {/* Cobertura por categoría de médico */}
      <Paper sx={{ p: 2, mb: 2, borderRadius: 2, border: '1px solid #e0e0e0' }}>
        <Box display="flex" alignItems="center" justifyContent="space-between" mb={1.5}>
          <Box display="flex" alignItems="center" gap={1}>
            <Typography variant="subtitle1" fontWeight={800} color="#1565c0">
              🎯 Cobertura por Categoría de Médico
            </Typography>
            <Chip size="small" label="A/B/C/D" sx={{ bgcolor: '#e3f2fd', color: '#1565c0', fontWeight: 700 }} />
          </Box>
          {catLoading && <CircularProgress size={16} />}
        </Box>
        <CoberturaPorCategoriaPanel data={catData ?? []} />
      </Paper>

      {/* Gráficos */}
      <Grid container spacing={2} mb={2}>
        <Grid item xs={12} md={7}>
          <Paper sx={{ p: 2, borderRadius: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
              Cobertura actual vs proyectada (top 15 VMs)
            </Typography>
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartCobertura} margin={{ top: 5, right: 10, left: -10, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-35} textAnchor="end" interval={0} height={78}
                       tickFormatter={(v: string) => (v && v.length > 12 ? v.slice(0, 11) + '…' : v)} />
                <YAxis domain={[0, 100]} tickFormatter={(v: number) => `${v}%`} tick={{ fontSize: 10 }} />
                <RechartTooltip formatter={(v: number) => `${v}%`} />
                <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
                <ReferenceLine y={90} stroke="#1565c0" strokeDasharray="4 2" label={{ value: 'Meta', fill: '#1565c0', fontSize: 10 }} />
                <Bar dataKey="actual" name="Actual" radius={[3, 3, 0, 0]}>
                  {chartCobertura.map((e, i) => <Cell key={i} fill={e.fill} />)}
                </Bar>
                <Bar dataKey="proyectada" name="Proyectada" fill="#90caf9" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
          </Paper>
        </Grid>
        <Grid item xs={12} md={5}>
          <Paper sx={{ p: 2, borderRadius: 2 }}>
            <Typography variant="subtitle2" fontWeight={700} mb={1.5}>
              Ritmo diario requerido (méd. + contactos)
            </Typography>
            {ritmoSinDias ? (
              <Box sx={{ height: 280, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', textAlign: 'center', color: 'text.secondary', px: 2 }}>
                <Warning sx={{ fontSize: 40, color: '#f57c00', mb: 1 }} />
                <Typography variant="body2" fontWeight={700}>Sin días hábiles restantes en el ciclo</Typography>
                <Typography variant="caption">
                  {data.dias_habiles_transcurridos}/{data.dias_habiles_totales} días transcurridos · 0 restantes.
                  El ritmo diario requerido no aplica cuando el ciclo ya llegó a su fin.
                  Verifica la <b>fecha fin</b> y los <b>días laborables</b> del ciclo si esperabas días disponibles.
                </Typography>
              </Box>
            ) : (
            <ResponsiveContainer width="100%" height={280}>
              <BarChart data={chartRitmo} margin={{ top: 5, right: 10, left: -10, bottom: 4 }}>
                <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                <XAxis dataKey="name" tick={{ fontSize: 10 }} angle={-35} textAnchor="end" interval={0} height={78}
                       tickFormatter={(v: string) => (v && v.length > 12 ? v.slice(0, 11) + '…' : v)} />
                <YAxis tick={{ fontSize: 10 }} />
                <RechartTooltip />
                <Legend verticalAlign="bottom" wrapperStyle={{ fontSize: 11, paddingTop: 4 }} />
                <Bar dataKey="medicos_dia" name="Méd/día" fill="#ef5350" radius={[3, 3, 0, 0]} />
                <Bar dataKey="contactos_dia" name="Cont/día" fill="#ab47bc" radius={[3, 3, 0, 0]} />
              </BarChart>
            </ResponsiveContainer>
            )}
          </Paper>
        </Grid>
      </Grid>

      {/* Tabla */}
      <Paper sx={{ borderRadius: 2 }}>
        <Box p={2} display="flex" alignItems="center" justifyContent="space-between">
          <Typography variant="subtitle2" fontWeight={700}>
            Detalle por Representante Médico ({data.total_rms})
          </Typography>
          <Typography variant="caption" color="text.secondary">
            Clic en fila → lectura accionable
          </Typography>
        </Box>
        <TableContainer>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow sx={{ '& th': { bgcolor: '#e3f2fd', fontWeight: 700, fontSize: 11 } }}>
                <TableCell>VM</TableCell>
                <TableCell>Línea / GD</TableCell>
                <TableCell align="center" sx={{ cursor: 'pointer' }} onClick={() => handleSort('estado_cobertura')}>
                  Estado {sortField === 'estado_cobertura' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </TableCell>
                <TableCell align="center" sx={{ minWidth: 170 }}>Cobertura</TableCell>
                <TableCell align="center" sx={{ cursor: 'pointer' }} onClick={() => handleSort('medicos_diarios_requeridos')}>
                  Méd/día {sortField === 'medicos_diarios_requeridos' ? (sortDir === 'asc' ? '↑' : '↓') : ''}
                </TableCell>
                <TableCell align="center">PSP</TableCell>
                <TableCell align="right">Contactos</TableCell>
                <TableCell align="center">Ritmo</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {sortedRMs.map(rm => (
                <React.Fragment key={rm.kpi_key}>
                  <TableRow
                    hover
                    onClick={() => setExpandedRow(expandedRow === rm.kpi_key ? null : rm.kpi_key)}
                    sx={{ cursor: 'pointer', bgcolor: expandedRow === rm.kpi_key ? '#f3f8ff' : undefined, borderLeft: `4px solid ${SEM[rm.estado_cobertura]}` }}
                  >
                    <TableCell>
                      <Typography variant="body2" fontWeight={600}>{rm.nombre_vm || rm.codigo_representante}</Typography>
                    </TableCell>
                    <TableCell>
                      <Typography variant="caption">{rm.linea ?? '—'}</Typography>
                      {rm.gd && <Typography variant="caption" display="block" color="text.secondary">{rm.gd}</Typography>}
                    </TableCell>
                    <TableCell align="center"><SemaforoChip estado={rm.estado_cobertura} /></TableCell>
                    <TableCell sx={{ minWidth: 190 }}>
                      <BarraMeta actual={rm.cobertura_actual_pct} esperada={rm.cobertura_esperada_pct} meta={rm.meta_cobertura_pct} />
                      <Typography variant="caption" color="text.secondary">
                        {rm.medicos_visitados_unicos}/{rm.medicos_programados} únicos
                      </Typography>
                    </TableCell>
                    <TableCell align="center">
                      <Typography variant="body2" fontWeight={700} sx={{ color: rm.medicos_diarios_requeridos > 5 ? '#c62828' : rm.medicos_diarios_requeridos > 3 ? '#f57c00' : '#2e7d32' }}>
                        {rm.medicos_diarios_requeridos}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">{rm.medicos_pendientes_meta} pend.</Typography>
                    </TableCell>
                    <TableCell align="center"><SemaforoChip estado={rm.estado_psp} /></TableCell>
                    <TableCell align="right">
                      <Typography variant="body2">{rm.contactos_realizados} / {rm.contactos_meta_ciclo}</Typography>
                      <Typography variant="caption" color="text.secondary">{rm.cumplimiento_contactos_pct.toFixed(1)}%</Typography>
                    </TableCell>
                    <TableCell align="center"><SemaforoChip estado={rm.estado_ritmo} /></TableCell>
                  </TableRow>
                  <TableRow>
                    <TableCell colSpan={8} sx={{ py: 0, px: 0, borderBottom: 'none' }}>
                      <Collapse in={expandedRow === rm.kpi_key} timeout="auto" unmountOnExit>
                        <Box sx={{ bgcolor: '#f8f9fa', px: 3, py: 1.5, borderBottom: '1px solid #e0e0e0' }}>
                          <Grid container spacing={2}>
                            <Grid item xs={12} md={8}>
                              <Typography variant="caption" fontWeight={700} color="#1565c0" display="block" mb={0.5}>
                                📋 Lectura accionable
                              </Typography>
                              <Typography variant="body2">{rm.lectura_accionable ?? 'Sin lectura disponible.'}</Typography>
                            </Grid>
                            <Grid item xs={12} md={4}>
                              <Stack spacing={0.5}>
                                {[
                                  ['Días hábiles totales', rm.dias_habiles_totales],
                                  ['Transcurridos', rm.dias_habiles_transcurridos],
                                  ['Restantes', rm.dias_habiles_restantes],
                                  ['Proyección cobertura', `${rm.cobertura_proyectada_pct.toFixed(1)}%`],
                                  ['Contactos proyectados', Math.round(rm.contactos_proyectados)],
                                ].map(([k, v]) => (
                                  <Box key={String(k)} display="flex" justifyContent="space-between">
                                    <Typography variant="caption" color="text.secondary">{k}:</Typography>
                                    <Typography variant="caption" fontWeight={600}>{String(v)}</Typography>
                                  </Box>
                                ))}
                              </Stack>
                            </Grid>
                          </Grid>
                        </Box>
                      </Collapse>
                    </TableCell>
                  </TableRow>
                </React.Fragment>
              ))}
              {sortedRMs.length === 0 && (
                <TableRow>
                  <TableCell colSpan={8} align="center" sx={{ py: 4 }}>
                    <Typography color="text.secondary">Sin datos para los filtros seleccionados</Typography>
                  </TableCell>
                </TableRow>
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </Paper>
    </Box>
  );
};

// ── Componente principal ──────────────────────────────────────────────────────
// Nota: la carga y el reset de datos se hacen desde
// Administración → Cobertura Predictiva (CoberturaPredictivaAdmin.tsx).
export default function CoberturaPredictiva() {
  const [paisCodigo, setPaisCodigo] = useState('DO');
  const [cicloSeleccionado, setCicloSeleccionado] = useState('');
  const [fechaCorte, setFechaCorte] = useState('');
  const [lineaFiltro, setLineaFiltro] = useState('');
  const [gdFiltro, setGdFiltro] = useState('');
  const [busquedaVM, setBusquedaVM] = useState('');  // Item 9: búsqueda de representante

  const { data: ciclos = [], isLoading: ciclosLoading } = useQuery<Ciclo[]>({
    queryKey: ['cob-ciclos', paisCodigo],
    queryFn: () => api.get(`/cobertura-predictiva/vivo/ciclos?pais_codigo=${paisCodigo}`).then(r => r.data),
    staleTime: 5 * 60 * 1000,
  });

  React.useEffect(() => {
    // Default = ciclo ABIERTO del país (no el primero de la lista, que sería un ciclo cerrado).
    if (ciclos.length && !cicloSeleccionado) {
      const abierto = ciclos.find(c => c.abierto);
      setCicloSeleccionado((abierto ?? ciclos[ciclos.length - 1]).codigo_ciclo);
    }
  }, [ciclos]);

  const cicloActual = ciclos.find(c => c.codigo_ciclo === cicloSeleccionado);

  const dashboardEnabled = Boolean(cicloSeleccionado && paisCodigo);
  const { data: dashData, isLoading: dashLoading, error: dashError } = useQuery<DashboardData>({
    queryKey: ['cob-dashboard', cicloSeleccionado, paisCodigo, fechaCorte, lineaFiltro, gdFiltro],
    queryFn: () => {
      const p = new URLSearchParams({ ciclo_codigo: cicloSeleccionado, pais_codigo: paisCodigo });
      if (fechaCorte) p.set('fecha_corte', fechaCorte);
      if (lineaFiltro) p.set('linea', lineaFiltro);
      if (gdFiltro) p.set('gd', gdFiltro);
      return api.get(`/cobertura-predictiva/vivo/dashboard?${p}`).then(r => r.data);
    },
    enabled: dashboardEnabled,
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  // Item 9 (Mallén): lista de representantes del ciclo para el desplegable "Buscar representante".
  const repOptions = React.useMemo(() => {
    const seen = new Map<string, { codigo: string; nombre: string }>();
    (dashData?.detalle_rms ?? []).forEach(r => {
      const cod = r.codigo_representante ?? '';
      if (cod && !seen.has(cod)) seen.set(cod, { codigo: cod, nombre: r.nombre_vm ?? '' });
    });
    return [...seen.values()].sort((a, b) =>
      a.codigo.localeCompare(b.codigo, undefined, { numeric: true }));
  }, [dashData]);

  const { data: catData, isLoading: catLoading } = useQuery<CoberturaCategoria[]>({
    queryKey: ['cob-categorias', cicloSeleccionado, paisCodigo, gdFiltro, lineaFiltro, busquedaVM],
    queryFn: () => {
      const p = new URLSearchParams({ ciclo_codigo: cicloSeleccionado, pais_codigo: paisCodigo });
      if (gdFiltro) p.set('gd', gdFiltro);
      if (lineaFiltro) p.set('linea', lineaFiltro);
      if (busquedaVM) p.set('rep', busquedaVM);   // filtra el panel de categorías por representante
      return api.get(`/cobertura-predictiva/vivo/categorias?${p}`).then(r => r.data);
    },
    enabled: dashboardEnabled,
    staleTime: 2 * 60 * 1000,
    retry: false,
  });

  // Líneas disponibles para el filtro: se derivan del detalle en vivo (ya no de cat.DimCiclo).
  const lineasDisponibles = useMemo(
    () => [...new Set((dashData?.detalle_rms ?? []).map(r => r.linea).filter(Boolean) as string[])],
    [dashData]);

  const errorMsg = dashError
    ? (dashError as any).response?.data?.detail ?? 'Error al cargar el dashboard'
    : !dashData?.ok ? (dashData?.mensaje ?? null) : null;

  return (
    <Box sx={{ p: { xs: 1, md: 2 } }}>
      <Box display="flex" alignItems="center" gap={1} mb={2}>
        <TrendingUp sx={{ color: '#1565c0', fontSize: 28 }} />
        <Box>
          <Typography variant="h5" fontWeight={800} color="#1565c0">Cobertura Predictiva y Ritmo de Ejecución</Typography>
          <Typography variant="body2" color="text.secondary">
            Metodología 4DX · Lead measures: médicos únicos visitados y cadencia diaria requerida
          </Typography>
        </Box>
      </Box>

      {/* Filtros */}
      <Paper sx={{ p: 2, mb: 2, borderRadius: 2 }}>
        <Grid container spacing={2} alignItems="flex-start">
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>País</InputLabel>
              <Select value={paisCodigo} label="País" onChange={e => { setPaisCodigo(e.target.value); setCicloSeleccionado(''); }}>
                <MenuItem value="DO">República Dominicana</MenuItem>
                <MenuItem value="CR">Costa Rica</MenuItem>
                <MenuItem value="GT">Guatemala</MenuItem>
                <MenuItem value="PA">Panamá</MenuItem>
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small" disabled={ciclosLoading || ciclos.length === 0}>
              <InputLabel>Ciclo</InputLabel>
              <Select value={cicloSeleccionado} label="Ciclo" onChange={e => setCicloSeleccionado(e.target.value)}>
                {ciclos.map(c => (
                  <MenuItem key={c.codigo_ciclo} value={c.codigo_ciclo}>{c.codigo_ciclo}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel shrink>Fecha corte</InputLabel>
              <Select value={fechaCorte} label="Fecha corte" displayEmpty notched onChange={e => setFechaCorte(e.target.value)}>
                <MenuItem value="">Hoy</MenuItem>
                {cicloActual?.fecha_fin && (
                  <MenuItem value={cicloActual.fecha_fin}>{cicloActual.fecha_fin}</MenuItem>
                )}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel shrink>Línea</InputLabel>
              <Select value={lineaFiltro} label="Línea" displayEmpty notched onChange={e => setLineaFiltro(e.target.value)}>
                <MenuItem value="">Todas</MenuItem>
                {lineasDisponibles.map(l => <MenuItem key={l} value={l}>{l}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel shrink>GD</InputLabel>
              <Select value={gdFiltro} label="GD" displayEmpty notched onChange={e => setGdFiltro(e.target.value)}>
                <MenuItem value="">Todos</MenuItem>
                {[...new Set(dashData?.detalle_rms?.map(r => r.gd).filter(Boolean) ?? [])].map(g => (
                  <MenuItem key={g} value={g!}>{g}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            {/* Item 9 (Mallén): desplegable de representantes — elegir de la lista o teclear para buscar. */}
            <Autocomplete
              size="small"
              options={repOptions}
              value={repOptions.find(o => o.codigo === busquedaVM) ?? null}
              onChange={(_e, v) => setBusquedaVM(v?.codigo ?? '')}
              getOptionLabel={(o) => o.nombre || o.codigo}
              isOptionEqualToValue={(o, v) => o.codigo === v.codigo}
              noOptionsText="Sin representantes en este ciclo"
              renderInput={(params) => (
                <TextField {...params} label="Buscar representante" placeholder="Todos · buscar por nombre…" />
              )}
            />
          </Grid>
        </Grid>
      </Paper>

      <Paper sx={{ p: 2, borderRadius: 2, minHeight: 300 }}>
        <DashboardTab
          data={dashData}
          loading={dashLoading}
          error={errorMsg}
          catData={catData}
          catLoading={catLoading}
          filtroVM={busquedaVM}
        />
      </Paper>
    </Box>
  );
}
