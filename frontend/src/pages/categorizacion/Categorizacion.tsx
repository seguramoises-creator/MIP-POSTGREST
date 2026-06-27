/**
 * Categorizacion.tsx — Vista operativa del módulo de Categorización Médica.
 * Nueva versión jun-2026 — consume cat.* / stg.* via los endpoints:
 *   GET /categorizacion/resumen
 *   GET /categorizacion/resultados
 *   GET /categorizacion/componentes
 */
import { useState } from 'react';
import {
  Box, Grid, Paper, Typography, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, TablePagination, MenuItem, Select, FormControl,
  InputLabel, TextField, InputAdornment, LinearProgress, Card, CardContent,
  Divider, Tooltip, Tabs, Tab,
} from '@mui/material';
import SearchIcon from '@mui/icons-material/Search';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import AssessmentIcon from '@mui/icons-material/Assessment';
import ManageSearchIcon from '@mui/icons-material/ManageSearch';
import { useQuery } from '@tanstack/react-query';
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, Legend, ResponsiveContainer,
} from 'recharts';
import { api } from '../../services/api';
import DetalleMedicos from './DetalleMedicos';

// ── Paleta profesional A/B/C/D (sincronizada con DetalleMedicos.tsx) ─────────
// A = Teal esmeralda  B = Azul zafiro  C = Ámbar dorado  D = Gris acero
const COL_COLORS = {
  A: { bg: '#00695c', light: '#e0f2f1' },
  B: '#283593',
  C: '#ef6c00',
  D: '#455a64',
} as const;

const CAT_PAL: Record<string, { dark: string; mid: string; light: string; text: string }> = {
  A: { dark: '#00695c', mid: '#00897b', light: '#e0f2f1', text: '#fff' },
  B: { dark: '#1a237e', mid: '#283593', light: '#e8eaf6', text: '#fff' },
  C: { dark: '#e65100', mid: '#ef6c00', light: '#fff3e0', text: '#fff' },
  D: { dark: '#37474f', mid: '#455a64', light: '#eceff1', text: '#fff' },
};
const CATS = ['A', 'B', 'C', 'D'] as const;

// Celda de número con barra proporcional
function NumCell({ v, cat, max }: { v: number; cat?: typeof CATS[number]; max?: number }) {
  if (!v) return (
    <TableCell align="center" sx={{ bgcolor: '#f5f5f5', color: '#bdbdbd', fontSize: '0.78rem', px: 1 }}>—</TableCell>
  );
  const pal = cat ? CAT_PAL[cat] : null;
  const pct = max && max > 0 ? Math.round((v / max) * 100) : 0;
  return (
    <TableCell align="center" sx={{ px: 1, py: 0.5 }}>
      <Box>
        <Typography sx={{ fontWeight: 700, fontSize: '0.82rem', color: pal?.mid ?? 'inherit', lineHeight: 1.2 }}>
          {v.toLocaleString()}
        </Typography>
        {max && max > 0 && (
          <Box sx={{ height: 3, bgcolor: '#e0e0e0', borderRadius: 4, mt: 0.3, overflow: 'hidden' }}>
            <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: pal?.mid ?? '#90a4ae', borderRadius: 4 }} />
          </Box>
        )}
      </Box>
    </TableCell>
  );
}

// ── Tipos ──────────────────────────────────────────────────────────────────────
interface Resumen {
  total_medicos: number;
  categoria_a: number;
  categoria_b: number;
  categoria_c: number;
  categoria_d: number;
  sin_categoria: number;
  conciliacion_ok: number;
  conciliacion_diferencia: number;
  puntaje_promedio: number;
  periodos_disponibles: string[];
}

interface Resultado {
  MedicoCategoriaKey: number;
  NombreMedico: string;
  Especialidad: string | null;
  CodigoRepresentante: string | null;
  NombreRepresentante: string | null;
  Equipo: string | null;
  Periodo: string;
  PuntajeTotalPct: number | null;
  CategoriaCalculada: string | null;
  CategoriaExcel: string | null;
  EstadoConciliacion: string | null;
}

interface Componente {
  CodigoComponente: string;
  NombreComponente: string;
  TipoEvaluacion: string;
  PesoPct: number;
  Requerido: boolean;
}

interface FilaRepresentante {
  equipo: string;
  representante: string;
  a: number; b: number; c: number; d: number; total: number;
}

interface FilaEspecialidad {
  especialidad: string;
  a: number; b: number; c: number; d: number; total: number;
}

// ── Colores de categoría (sincronizados con DetalleMedicos.tsx) ───────────────
const CAT_COLORS: Record<string, string> = {
  A: '#00897b',   // Teal esmeralda (un tono más claro)
  B: '#283593',   // Azul zafiro
  C: '#ef6c00',   // Ámbar dorado
  D: '#455a64',   // Gris acero
  '?': '#78909c',
};

const PIE_COLORS = ['#00897b', '#283593', '#ef6c00', '#455a64', '#9e9e9e'];

// Degradados por categoría (para gradiente en chip)
const CAT_GRAD: Record<string, string> = {
  A: 'linear-gradient(135deg, #00695c 0%, #00897b 100%)',
  B: 'linear-gradient(135deg, #1a237e 0%, #283593 100%)',
  C: 'linear-gradient(135deg, #e65100 0%, #ef6c00 100%)',
  D: 'linear-gradient(135deg, #37474f 0%, #455a64 100%)',
  '?': 'linear-gradient(135deg, #546e7a 0%, #78909c 100%)',
};

function CatChip({ cat }: { cat: string | null }) {
  const c = cat || '?';
  return (
    <Box sx={{
      display: 'inline-flex', alignItems: 'center', gap: 0.5,
      px: 1.1, py: 0.3, borderRadius: '16px',
      background: CAT_GRAD[c] || CAT_GRAD['?'],
      boxShadow: `0 2px 6px ${CAT_COLORS[c] || '#78909c'}50`,
    }}>
      <Box sx={{
        width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
        bgcolor: 'rgba(255,255,255,0.25)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontSize: '0.58rem', fontWeight: 900, color: '#fff',
      }}>{c}</Box>
      <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: '0.72rem', lineHeight: 1 }}>
        Cat. {c}
      </Typography>
    </Box>
  );
}

// ── Componente principal ───────────────────────────────────────────────────────
export default function Categorizacion() {
  const [tab, setTab] = useState(0);
  const [periodo, setPeriodo] = useState<string>('');
  const [categoria, setCategoria] = useState('');
  const [busqueda, setBusqueda] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);

  // Resumen
  const { data: resumen, isLoading: loadingResumen } = useQuery<Resumen>({
    queryKey: ['cat-resumen', periodo],
    queryFn: async () => {
      const params = new URLSearchParams();
      if (periodo) params.set('periodo', periodo);
      const r = await api.get(`/categorizacion/resumen?${params}`);
      return r.data;
    },
  });

  // Resultados paginados
  const { data: resultados, isLoading: loadingResultados } = useQuery({
    queryKey: ['cat-resultados', periodo, categoria, busqueda, page, rowsPerPage],
    queryFn: async () => {
      const params = new URLSearchParams({ skip: String(page * rowsPerPage), limit: String(rowsPerPage) });
      if (periodo) params.set('periodo', periodo);
      if (categoria) params.set('categoria', categoria);
      if (busqueda) params.set('representante', busqueda);
      const r = await api.get(`/categorizacion/resultados?${params}`);
      return r.data as { total: number; items: Resultado[] };
    },
  });

  // Componentes y pesos
  const { data: componentes = [] } = useQuery<Componente[]>({
    queryKey: ['cat-componentes'],
    queryFn: async () => {
      const r = await api.get('/categorizacion/componentes');
      return r.data;
    },
    staleTime: Infinity,
  });

  // Por representante
  const { data: porRep = [] } = useQuery<FilaRepresentante[]>({
    queryKey: ['cat-por-rep', periodo],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (periodo) p.set('periodo', periodo);
      const r = await api.get(`/categorizacion/por-representante?${p}`);
      return r.data;
    },
  });

  // Por especialidad
  const { data: porEsp = [] } = useQuery<FilaEspecialidad[]>({
    queryKey: ['cat-por-esp', periodo],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (periodo) p.set('periodo', periodo);
      const r = await api.get(`/categorizacion/por-especialidad?${p}`);
      return r.data;
    },
  });

  // Agrupar por equipo para la tabla jerárquica
  const equipos = Array.from(new Set(porRep.map(r => r.equipo)));
  const subtotalEquipo = (eq: string) => {
    const filas = porRep.filter(r => r.equipo === eq);
    return filas.reduce((acc, f) => ({
      a: acc.a + f.a, b: acc.b + f.b, c: acc.c + f.c, d: acc.d + f.d, total: acc.total + f.total,
    }), { a: 0, b: 0, c: 0, d: 0, total: 0 });
  };
  const grandTotal = porRep.reduce((acc, f) => ({
    a: acc.a + f.a, b: acc.b + f.b, c: acc.c + f.c, d: acc.d + f.d, total: acc.total + f.total,
  }), { a: 0, b: 0, c: 0, d: 0, total: 0 });
  const grandTotalEsp = porEsp.reduce((acc, f) => ({
    a: acc.a + f.a, b: acc.b + f.b, c: acc.c + f.c, d: acc.d + f.d, total: acc.total + f.total,
  }), { a: 0, b: 0, c: 0, d: 0, total: 0 });

  const pieData = resumen
    ? [
        { name: 'A', value: resumen.categoria_a },
        { name: 'B', value: resumen.categoria_b },
        { name: 'C', value: resumen.categoria_c },
        { name: 'D', value: resumen.categoria_d },
        { name: 'Sin cat.', value: resumen.sin_categoria },
      ].filter((d) => d.value > 0)
    : [];

  const conciliacionPct =
    resumen && resumen.total_medicos > 0
      ? Math.round((resumen.conciliacion_ok / resumen.total_medicos) * 100)
      : 0;

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      {/* Encabezado */}
      <Box display="flex" alignItems="center" gap={1.5} mb={3}>
        <MedicalServicesIcon sx={{ fontSize: 32, color: 'primary.main' }} />
        <Box>
          <Typography variant="h5" fontWeight={700}>Categorización Médica</Typography>
          <Typography variant="body2" color="text.secondary">
            Clasificación A/B/C/D por criterios ponderados
          </Typography>
        </Box>
      </Box>

      {/* Selector de período */}
      {resumen && resumen.periodos_disponibles.length > 0 && (
        <Box mb={3} maxWidth={240}>
          <FormControl fullWidth size="small">
            <InputLabel>Período</InputLabel>
            <Select
              value={periodo}
              label="Período"
              onChange={(e) => { setPeriodo(e.target.value); setPage(0); }}
            >
              <MenuItem value="">Todos</MenuItem>
              {resumen.periodos_disponibles.map((p) => (
                <MenuItem key={p} value={p}>{p}</MenuItem>
              ))}
            </Select>
          </FormControl>
        </Box>
      )}


      {/* ── Pestañas — mismo estilo que Admin.tsx ──────────────────────── */}
      <Box mb={3}>
        <Tabs
          value={tab}
          onChange={(_, v) => { setTab(v as number); }}
          variant="scrollable"
          scrollButtons="auto"
          sx={{
            borderBottom: '3px solid #1565c0',
            '& .MuiTab-root': {
              bgcolor: '#bbdefb',
              borderTopLeftRadius: 8,
              borderTopRightRadius: 8,
              mr: 0.5,
              color: '#1565c0',
              fontWeight: 600,
              minHeight: 40,
              fontSize: 13,
              textTransform: 'none',
              '&.Mui-selected': {
                bgcolor: '#1565c0',
                color: '#fff',
                fontWeight: 700,
              },
              '&:hover:not(.Mui-selected)': {
                bgcolor: '#90caf9',
              },
            },
            '& .MuiTabs-indicator': { display: 'none' },
          }}
        >
          <Tab
            icon={<AssessmentIcon sx={{ fontSize: 17 }} />}
            iconPosition="start"
            label="Resumen General"
          />
          <Tab
            icon={<ManageSearchIcon sx={{ fontSize: 17 }} />}
            iconPosition="start"
            label="Detalle por Médico"
          />
        </Tabs>
      </Box>

      {/* ── Tab 0: Resumen ─────────────────────────────────────────────── */}
      {tab === 0 && (
      <Box>
      {/* KPI cards */}
      <Grid container spacing={2} mb={3}>
        {[
          { label: 'Total médicos', value: resumen?.total_medicos ?? 0, color: 'primary.main' },
          { label: 'Categoría A', value: resumen?.categoria_a ?? 0, color: CAT_COLORS.A },
          { label: 'Categoría B', value: resumen?.categoria_b ?? 0, color: CAT_COLORS.B },
          { label: 'Categoría C', value: resumen?.categoria_c ?? 0, color: CAT_COLORS.C },
          { label: 'Categoría D', value: resumen?.categoria_d ?? 0, color: CAT_COLORS.D },
          { label: 'Puntaje promedio', value: `${resumen?.puntaje_promedio ?? 0}%`, color: 'text.primary' },
        ].map((k) => (
          <Grid item xs={6} sm={4} md={2} key={k.label}>
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent sx={{ p: 2, '&:last-child': { pb: 2 } }}>
                <Typography variant="h5" fontWeight={700} color={k.color}>
                  {loadingResumen ? '…' : k.value}
                </Typography>
                <Typography variant="caption" color="text.secondary">{k.label}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      <Grid container spacing={3} mb={3}>
        {/* Gráfico de distribución */}
        <Grid item xs={12} md={5}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
            <Typography variant="subtitle1" fontWeight={600} mb={1}>Distribución por Categoría</Typography>
            {pieData.length > 0 ? (
              <ResponsiveContainer width="100%" height={220}>
                <PieChart>
                  <Pie data={pieData} cx="50%" cy="50%" outerRadius={80} dataKey="value" label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}>
                    {pieData.map((_, i) => <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />)}
                  </Pie>
                  <ReTooltip />
                  <Legend />
                </PieChart>
              </ResponsiveContainer>
            ) : (
              <Box display="flex" alignItems="center" justifyContent="center" height={220}>
                <Typography color="text.secondary" variant="body2">Sin datos para el período seleccionado</Typography>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* Componentes y Pesos */}
        <Grid item xs={12} md={7}>
          <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
            <Typography variant="subtitle1" fontWeight={600} mb={1}>Componentes y Pesos</Typography>
            {componentes.map((c) => (
              <Box key={c.CodigoComponente} mb={1}>
                <Box display="flex" justifyContent="space-between" mb={0.3}>
                  <Tooltip title={`${c.TipoEvaluacion} · ${c.Requerido ? 'Requerido' : 'Opcional'}`}>
                    <Typography variant="body2">{c.NombreComponente}</Typography>
                  </Tooltip>
                  <Typography variant="body2" fontWeight={700}>{c.PesoPct}%</Typography>
                </Box>
                <LinearProgress variant="determinate" value={c.PesoPct} sx={{ height: 6, borderRadius: 3 }} />
              </Box>
            ))}
          </Paper>
        </Grid>
      </Grid>

      {/* Tabla de resultados */}
      <Paper variant="outlined">
        <Box sx={{ p: 2, display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'center' }}>
          <Typography variant="subtitle1" fontWeight={600} mr="auto">Resultados por Médico</Typography>
          <TextField
            size="small"
            placeholder="Buscar representante…"
            value={busqueda}
            onChange={(e) => { setBusqueda(e.target.value); setPage(0); }}
            InputProps={{ startAdornment: <InputAdornment position="start"><SearchIcon fontSize="small" /></InputAdornment> }}
            sx={{ width: 220 }}
          />
          <FormControl size="small" sx={{ minWidth: 110 }}>
            <InputLabel>Categoría</InputLabel>
            <Select value={categoria} label="Categoría" onChange={(e) => { setCategoria(e.target.value); setPage(0); }}>
              <MenuItem value="">Todas</MenuItem>
              {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
            </Select>
          </FormControl>
        </Box>

        {loadingResultados && <LinearProgress />}

        <Table size="small" stickyHeader>
          <TableHead>
            <TableRow sx={{ bgcolor: 'grey.50' }}>
              <TableCell><b>Médico</b></TableCell>
              <TableCell><b>Especialidad</b></TableCell>
              <TableCell><b>Representante</b></TableCell>
              <TableCell><b>Equipo</b></TableCell>
              <TableCell><b>Período</b></TableCell>
              <TableCell align="center"><b>Puntaje</b></TableCell>
              <TableCell align="center"><b>Cat. calculada</b></TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {!loadingResultados && (resultados?.items ?? []).length === 0 && (
              <TableRow>
                <TableCell colSpan={7} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  Sin resultados para los filtros aplicados
                </TableCell>
              </TableRow>
            )}
            {(resultados?.items ?? []).map((r) => (
              <TableRow key={r.MedicoCategoriaKey} hover>
                <TableCell sx={{ fontWeight: 500 }}>{r.NombreMedico}</TableCell>
                <TableCell>{r.Especialidad || '—'}</TableCell>
                <TableCell>{r.NombreRepresentante || r.CodigoRepresentante || '—'}</TableCell>
                <TableCell>{r.Equipo || '—'}</TableCell>
                <TableCell>{r.Periodo}</TableCell>
                <TableCell align="center">
                  {r.PuntajeTotalPct != null
                    ? `${Number(r.PuntajeTotalPct).toFixed(1)}%`
                    : '—'}
                </TableCell>
                <TableCell align="center"><CatChip cat={r.CategoriaCalculada} /></TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>

        <TablePagination
          component="div"
          count={resultados?.total ?? 0}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value)); setPage(0); }}
          rowsPerPageOptions={[10, 25, 50, 100]}
          labelRowsPerPage="Filas:"
        />
      </Paper>

      {/* ── Tablas de resumen ─────────────────────────────────────────────── */}
      <Grid container spacing={3} mt={1}>

        {/* ── Tabla por Representante ── */}
        <Grid item xs={12} xl={7}>
          <Paper elevation={3} sx={{ display: 'flex', flexDirection: 'column', height: 560, overflow: 'hidden', borderRadius: 2, border: '1px solid #e0e0e0' }}>
            {/* Encabezado */}
            <Box sx={{ background: 'linear-gradient(135deg,#1a237e 0%,#283593 100%)', px: 2.5, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
              <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 1, flexGrow: 1 }}>
                CATEGORIZACIÓN POR REPRESENTANTE
              </Typography>
              <Chip label={`${grandTotal.total.toLocaleString()} médicos`} size="small"
                sx={{ bgcolor: 'rgba(255,255,255,0.18)', color: '#fff', fontWeight: 700, fontSize: '0.72rem' }} />
            </Box>
            {porRep.length === 0
              ? <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary', flex: 1 }}>
                  <Typography variant="body2">Sin datos — cargue médicos categorizados desde <strong>Administración → Categorización</strong></Typography>
                </Box>
              : (
              <Box sx={{ flex: 1, overflow: 'auto' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ bgcolor: '#37474f', color: '#fff', fontWeight: 700, fontSize: '0.78rem', pl: 2, minWidth: 180 }}>
                      Equipo / Representante
                    </TableCell>
                    {CATS.map(c => (
                      <TableCell key={c} align="center"
                        sx={{ bgcolor: CAT_PAL[c].dark, color: '#fff', fontWeight: 800, fontSize: '0.9rem', width: 70, py: 1 }}>
                        {c}
                      </TableCell>
                    ))}
                    <TableCell align="center" sx={{ bgcolor: '#212121', color: '#fff', fontWeight: 800, fontSize: '0.82rem', width: 75, py: 1 }}>
                      TOTAL
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {equipos.map((eq, eqIdx) => {
                    const sub = subtotalEquipo(eq);
                    const reps = porRep.filter(r => r.equipo === eq);
                    return [
                      /* fila de equipo */
                      <TableRow key={`eq-${eq}`} sx={{ bgcolor: eqIdx % 2 === 0 ? '#e8eaf6' : '#ede7f6' }}>
                        <TableCell sx={{ pl: 2, fontWeight: 800, fontSize: '0.82rem', color: '#1a237e',
                          borderLeft: '4px solid #3f51b5', letterSpacing: 0.3 }}>
                          ▸ {eq}
                        </TableCell>
                        {CATS.map(c => {
                          const v = sub[c.toLowerCase() as 'a'|'b'|'c'|'d'];
                          return (
                            <TableCell key={c} align="center"
                              sx={{ fontWeight: 700, fontSize: '0.82rem', color: CAT_PAL[c].mid,
                                bgcolor: `${CAT_PAL[c].light}88` }}>
                              {v ? v.toLocaleString() : '—'}
                            </TableCell>
                          );
                        })}
                        <TableCell align="center" sx={{ fontWeight: 800, fontSize: '0.84rem', color: '#37474f' }}>
                          {sub.total.toLocaleString()}
                        </TableCell>
                      </TableRow>,
                      /* filas de representantes */
                      ...reps.map(r => (
                        <TableRow key={`${eq}-${r.representante}`} hover
                          sx={{ '&:hover': { bgcolor: '#f3f4fe' }, borderLeft: '4px solid transparent' }}>
                          <TableCell sx={{ pl: 5, fontSize: '0.78rem', color: '#546e7a', fontStyle: 'italic' }}>
                            {r.representante}
                          </TableCell>
                          <NumCell v={r.a} cat="A" max={sub.a || 1} />
                          <NumCell v={r.b} cat="B" max={sub.b || 1} />
                          <NumCell v={r.c} cat="C" max={sub.c || 1} />
                          <NumCell v={r.d} cat="D" max={sub.d || 1} />
                          <TableCell align="center" sx={{ fontWeight: 600, fontSize: '0.8rem', color: '#455a64' }}>
                            {r.total.toLocaleString()}
                          </TableCell>
                        </TableRow>
                      )),
                    ];
                  })}
                  {/* Total general */}
                  <TableRow sx={{ bgcolor: '#1a237e' }}>
                    <TableCell sx={{ color: '#fff', fontWeight: 800, fontSize: '0.84rem', pl: 2, letterSpacing: 0.5 }}>
                      TOTAL GENERAL
                    </TableCell>
                    {CATS.map(c => (
                      <TableCell key={c} align="center"
                        sx={{ bgcolor: CAT_PAL[c].mid, color: '#fff', fontWeight: 800, fontSize: '0.88rem', py: 1.2 }}>
                        {grandTotal[c.toLowerCase() as 'a'|'b'|'c'|'d'].toLocaleString()}
                      </TableCell>
                    ))}
                    <TableCell align="center" sx={{ bgcolor: '#212121', color: '#fff', fontWeight: 800, fontSize: '0.9rem', py: 1.2 }}>
                      {grandTotal.total.toLocaleString()}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              </Box>
            )}
          </Paper>
        </Grid>

        {/* ── Tabla por Especialidad ── */}
        <Grid item xs={12} xl={5}>
          <Paper elevation={3} sx={{ display: 'flex', flexDirection: 'column', height: 560, overflow: 'hidden', borderRadius: 2, border: '1px solid #e0e0e0' }}>
            <Box sx={{ background: 'linear-gradient(135deg,#004d40 0%,#00695c 100%)', px: 2.5, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
              <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 1, flexGrow: 1 }}>
                CATEGORIZACIÓN POR ESPECIALIDAD
              </Typography>
              <Chip label={`${porEsp.length} especialidades`} size="small"
                sx={{ bgcolor: 'rgba(255,255,255,0.18)', color: '#fff', fontWeight: 700, fontSize: '0.72rem' }} />
            </Box>
            {porEsp.length === 0
              ? <Box sx={{ py: 6, textAlign: 'center', color: 'text.secondary', flex: 1 }}>
                  <Typography variant="body2">Sin datos — cargue médicos categorizados desde <strong>Administración → Categorización</strong></Typography>
                </Box>
              : (
              <Box sx={{ flex: 1, overflow: 'auto' }}>
              <Table size="small" stickyHeader>
                <TableHead>
                  <TableRow>
                    <TableCell sx={{ bgcolor: '#37474f', color: '#fff', fontWeight: 700, fontSize: '0.78rem', pl: 2, minWidth: 170 }}>
                      Especialidad
                    </TableCell>
                    {CATS.map(c => (
                      <TableCell key={c} align="center"
                        sx={{ bgcolor: CAT_PAL[c].dark, color: '#fff', fontWeight: 800, fontSize: '0.9rem', width: 55, py: 1 }}>
                        {c}
                      </TableCell>
                    ))}
                    <TableCell align="center" sx={{ bgcolor: '#212121', color: '#fff', fontWeight: 800, fontSize: '0.82rem', width: 70, py: 1 }}>
                      TOTAL
                    </TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {porEsp.map((r, i) => {
                    const maxVal = Math.max(r.a, r.b, r.c, r.d, 1);
                    return (
                      <TableRow key={r.especialidad} hover sx={{
                        bgcolor: i % 2 === 0 ? '#fff' : '#f1f8f6',
                        '&:hover': { bgcolor: '#e0f2f1' },
                      }}>
                        <TableCell sx={{ pl: 2, fontWeight: 600, fontSize: '0.78rem', color: '#004d40',
                          borderLeft: `3px solid ${i % 2 === 0 ? '#00897b' : '#26a69a'}` }}>
                          {r.especialidad}
                        </TableCell>
                        <NumCell v={r.a} cat="A" max={maxVal} />
                        <NumCell v={r.b} cat="B" max={maxVal} />
                        <NumCell v={r.c} cat="C" max={maxVal} />
                        <NumCell v={r.d} cat="D" max={maxVal} />
                        <TableCell align="center" sx={{ fontWeight: 700, fontSize: '0.82rem', color: '#00695c' }}>
                          {r.total.toLocaleString()}
                        </TableCell>
                      </TableRow>
                    );
                  })}
                  <TableRow sx={{ bgcolor: '#004d40' }}>
                    <TableCell sx={{ color: '#fff', fontWeight: 800, fontSize: '0.84rem', pl: 2, letterSpacing: 0.5 }}>
                      TOTAL GENERAL
                    </TableCell>
                    {CATS.map(c => (
                      <TableCell key={c} align="center"
                        sx={{ bgcolor: CAT_PAL[c].mid, color: '#fff', fontWeight: 800, fontSize: '0.88rem', py: 1.2 }}>
                        {grandTotalEsp[c.toLowerCase() as 'a'|'b'|'c'|'d'].toLocaleString()}
                      </TableCell>
                    ))}
                    <TableCell align="center" sx={{ bgcolor: '#212121', color: '#fff', fontWeight: 800, fontSize: '0.9rem', py: 1.2 }}>
                      {grandTotalEsp.total.toLocaleString()}
                    </TableCell>
                  </TableRow>
                </TableBody>
              </Table>
              </Box>
            )}
          </Paper>
        </Grid>

      </Grid>
      </Box>
      )}

      {/* Tab 1: Detalle por Médico */}
      {tab === 1 && <DetalleMedicos periodo={periodo} />}
    </Box>
  );
}
