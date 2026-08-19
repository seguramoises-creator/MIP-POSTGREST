/**
 * DetalleMedicos.tsx — Pestaña "Detalle por Médico" del módulo Categorización.
 * Filtros en cascada: País → Provincia → Municipio → Especialidad → Representante
 * Gráficos: Pie distribución + Bar top-especialidades
 * Tabla: médico con score total, categoría, y expansión de componentes.
 */
import { useState, useEffect } from 'react';
import {
  Box, Grid, Paper, Typography, Chip, Collapse, Table, TableHead,
  TableBody, TableRow, TableCell, TablePagination, MenuItem, Select,
  FormControl, InputLabel, IconButton, Tooltip, LinearProgress, Card,
  CardContent, Divider, Button, Stack, CircularProgress,
} from '@mui/material';
import FilterListIcon from '@mui/icons-material/FilterList';
import ExpandMoreIcon from '@mui/icons-material/ExpandMore';
import ExpandLessIcon from '@mui/icons-material/ExpandLess';
import SearchIcon from '@mui/icons-material/Search';
import ClearIcon from '@mui/icons-material/Clear';
import { useQuery } from '@tanstack/react-query';
import {
  PieChart, Pie, Cell, Tooltip as ReTooltip, Legend, ResponsiveContainer,
  BarChart, Bar, XAxis, YAxis, CartesianGrid,
} from 'recharts';
import { api } from '../../services/api';

// ── Paleta profesional A/B/C/D ───────────────────────────────────────────────
// A = Teal esmeralda  B = Azul zafiro  C = Ámbar dorado  D = Gris acero
const CAT_PAL: Record<string, { dark: string; mid: string; light: string; glow: string; text: string }> = {
  A: { dark: '#00695c', mid: '#00897b', light: '#e0f2f1', glow: '#00897b60', text: '#fff' },
  B: { dark: '#686158', mid: '#283593', light: '#e8eaf6', glow: '#3949ab60', text: '#fff' },
  C: { dark: '#e65100', mid: '#ef6c00', light: '#fff3e0', glow: '#f57c0060', text: '#fff' },
  D: { dark: '#37474f', mid: '#455a64', light: '#eceff1', glow: '#546e7a60', text: '#fff' },
  '?': { dark: '#424242', mid: '#757575', light: '#f5f5f5', glow: '#9e9e9e40', text: '#fff' },
};
const CAT_COLORS = ['#00897b', '#283593', '#ef6c00', '#455a64', '#9e9e9e'];
const CAT_LABEL: Record<string, string> = {
  A: 'Alto potencial',
  B: 'Potencial medio',
  C: 'Seguimiento',
  D: 'Bajo potencial',
};

// ── Tipos ────────────────────────────────────────────────────────────────────
interface Filtros {
  paises: { CodigoPais: string; NombrePais: string }[];
  provincias: string[];
  municipios: string[];
  especialidades: string[];
  representantes: { CodigoRepresentante: string; NombreRepresentante: string }[];
}
interface MedicoDetalle {
  MedicoCategoriaKey: number;
  NombreMedico: string;
  Especialidad: string;
  Provincia: string;
  Municipio: string;
  Equipo: string;
  Representante: string;
  Periodo: string;
  PuntajeTotalPct: number;
  CategoriaCalculada: string;
  CategoriaExcel: string;
  EstadoConciliacion: string;
}
interface Componente {
  NombreComponente: string;
  CodigoComponente: string;
  ValorEntradaTexto: string | null;
  ValorEntradaNumero: number | null;
  PuntajePct: number;
  EstadoComponente: string;
}

// ── Sub-componentes ───────────────────────────────────────────────────────────
function CatChip({ cat }: { cat: string }) {
  const c = cat || '?';
  const pal = CAT_PAL[c] ?? CAT_PAL['?'];
  return (
    <Box
      sx={{
        display: 'inline-flex', alignItems: 'center', gap: 0.6,
        px: 1.2, py: 0.35, borderRadius: '20px',
        background: `linear-gradient(135deg, ${pal.dark} 0%, ${pal.mid} 100%)`,
        boxShadow: `0 2px 8px ${pal.glow}`,
        userSelect: 'none',
      }}
    >
      <Box sx={{
        width: 18, height: 18, borderRadius: '50%',
        bgcolor: 'rgba(255,255,255,0.28)',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 900, fontSize: '0.65rem', color: '#fff', flexShrink: 0,
      }}>{c}</Box>
      <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: '0.72rem', lineHeight: 1 }}>
        Cat. {c}
      </Typography>
    </Box>
  );
}

function ScoreBar({ value }: { value: number }) {
  const pct = Math.min(100, Math.max(0, value));
  const color = pct >= 70 ? '#00695c' : pct >= 50 ? '#283593' : pct >= 30 ? '#ef6c00' : '#455a64';
  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Box sx={{ flex: 1, height: 6, bgcolor: '#e0e0e0', borderRadius: 3, overflow: 'hidden' }}>
        <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: color, borderRadius: 3, transition: 'width .4s' }} />
      </Box>
      <Typography sx={{ fontSize: '0.78rem', fontWeight: 700, color, minWidth: 38, textAlign: 'right' }}>
        {pct.toFixed(1)}%
      </Typography>
    </Box>
  );
}

function ComponenteRow({ key_ }: { key_: number }) {
  const { data: comps = [], isLoading } = useQuery<Componente[]>({
    queryKey: ['cat-comp', key_],
    queryFn: async () => {
      const r = await api.get(`/categorizacion/detalle-medicos/${key_}/componentes`);
      return r.data;
    },
    staleTime: 5 * 60_000,
  });
  if (isLoading) return <Box sx={{ p: 2 }}><CircularProgress size={20} /></Box>;
  if (!comps.length) return <Typography sx={{ p: 2, color: 'text.secondary', fontSize: '0.82rem' }}>Sin detalle de componentes</Typography>;
  return (
    <Box sx={{ p: 1.5, bgcolor: '#f8fafc' }}>
      <Grid container spacing={1}>
        {comps.map((c) => {
          const pct = Math.min(100, Math.max(0, c.PuntajePct));
          const color = pct >= 70 ? '#00695c' : pct >= 40 ? '#283593' : '#ef6c00';
          const val = c.ValorEntradaTexto || (c.ValorEntradaNumero != null ? String(c.ValorEntradaNumero) : '—');
          return (
            <Grid item xs={12} sm={6} md={4} lg={2.4} key={c.CodigoComponente}>
              <Paper variant="outlined" sx={{ p: 1.2, borderRadius: 2, borderColor: '#e3e8f0' }}>
                <Typography sx={{ fontSize: '0.68rem', color: 'text.secondary', fontWeight: 600, textTransform: 'uppercase', letterSpacing: 0.3 }}>
                  {c.NombreComponente}
                </Typography>
                <Typography sx={{ fontSize: '0.82rem', fontWeight: 700, mt: 0.3, mb: 0.5 }}>{val}</Typography>
                <Box sx={{ height: 5, bgcolor: '#e0e0e0', borderRadius: 3, overflow: 'hidden' }}>
                  <Box sx={{ height: '100%', width: `${pct}%`, bgcolor: color, borderRadius: 3 }} />
                </Box>
                <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color, mt: 0.3 }}>{pct.toFixed(1)} pts</Typography>
              </Paper>
            </Grid>
          );
        })}
      </Grid>
    </Box>
  );
}

// ── Componente principal ──────────────────────────────────────────────────────

export default function DetalleMedicos() {
  const [pais, setPais] = useState('');
  const [provincia, setProvincia] = useState('');
  const [municipio, setMunicipio] = useState('');
  const [especialidad, setEspecialidad] = useState('');
  const [representante, setRepresentante] = useState('');
  const [categoria, setCategoria] = useState('');
  const [page, setPage] = useState(0);
  const [rowsPerPage, setRowsPerPage] = useState(25);
  const [expanded, setExpanded] = useState<number | null>(null);

  // Reiniciar paginación al cambiar filtros
  useEffect(() => { setPage(0); setExpanded(null); }, [pais, provincia, municipio, especialidad, representante, categoria]);
  useEffect(() => { setProvincia(''); setMunicipio(''); }, [pais]);
  useEffect(() => { setMunicipio(''); }, [provincia]);

  // Catálogos en cascada
  const { data: filtros } = useQuery<Filtros>({
    queryKey: ['cat-filtros', pais, provincia],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (pais) p.set('pais', pais);
      if (provincia) p.set('provincia', provincia);
      const r = await api.get(`/categorizacion/filtros?${p}`);
      return r.data;
    },
    staleTime: 60_000,
  });

  // ── Estadísticas para gráficos: mismos filtros que la tabla (sin paginación) ─
  const { data: statsGlobales } = useQuery({
    queryKey: ['cat-stats-detalle', pais, provincia, municipio, especialidad, representante],
    queryFn: async () => {
      const p = new URLSearchParams();
      if (pais)          p.set('pais',           pais);
      if (provincia)     p.set('provincia',      provincia);
      if (municipio)     p.set('municipio',      municipio);
      if (especialidad)  p.set('especialidad',   especialidad);
      if (representante) p.set('representante',  representante);
      const r = await api.get(`/categorizacion/resumen?${p}`);
      return r.data as {
        total_medicos: number;
        categoria_a: number; categoria_b: number;
        categoria_c: number; categoria_d: number;
      };
    },
    staleTime: 30_000,
  });

  // Detalle paginado
  const { data: detalle, isLoading, error: detalleError } = useQuery({
    queryKey: ['cat-detalle', pais, provincia, municipio, especialidad, representante, categoria, page, rowsPerPage],
    queryFn: async () => {
      const p = new URLSearchParams({ skip: String(page * rowsPerPage), limit: String(rowsPerPage) });
      if (pais) p.set('pais', pais);
      if (provincia) p.set('provincia', provincia);
      if (municipio) p.set('municipio', municipio);
      if (especialidad) p.set('especialidad', especialidad);
      if (representante) p.set('representante', representante);
      if (categoria) p.set('categoria', categoria);
      const r = await api.get(`/categorizacion/detalle-medicos?${p}`);
      return r.data as { total: number; items: MedicoDetalle[] };
    },
    retry: false,
  });

  const items = detalle?.items ?? [];
  const total = detalle?.total ?? 0;

  // Datos para gráficos: usa totales globales, filtrados si hay categoría seleccionada
  const catCountsGlobal = (['A','B','C','D'] as const)
    .filter(cat => !categoria || cat === categoria)   // respetar filtro de categoría activo
    .map(cat => {
      const key = `categoria_${cat.toLowerCase()}` as 'categoria_a'|'categoria_b'|'categoria_c'|'categoria_d';
      return {
        name: `Cat. ${cat}`,
        value: statsGlobales ? (statsGlobales[key] ?? 0) : items.filter(i => i.CategoriaCalculada === cat).length,
        cat,
      };
    }).filter(d => d.value > 0);

  const limpiarFiltros = () => {
    setPais(''); setProvincia(''); setMunicipio('');
    setEspecialidad(''); setRepresentante(''); setCategoria('');
  };

  const hayFiltros = !!(pais || provincia || municipio || especialidad || representante || categoria);

  return (
    <Box>
      {/* ── Panel de filtros ── */}
      <Paper
        elevation={0}
        sx={{
          p: 2, mb: 3, border: '1px solid #e3e8f0', borderRadius: 3,
          background: 'linear-gradient(135deg, #f0f4ff 0%, #fafbff 100%)',
        }}
      >
        <Box display="flex" alignItems="center" gap={1} mb={1.5}>
          <FilterListIcon sx={{ color: 'primary.main', fontSize: 20 }} />
          <Typography fontWeight={700} sx={{ fontSize: '0.88rem', color: 'primary.main' }}>
            FILTROS DE BÚSQUEDA
          </Typography>
          {hayFiltros && (
            <Chip
              label="Limpiar filtros"
              size="small"
              deleteIcon={<ClearIcon />}
              onDelete={limpiarFiltros}
              onClick={limpiarFiltros}
              sx={{ ml: 'auto', bgcolor: '#fff', border: '1px solid #ccc', fontSize: '0.72rem' }}
            />
          )}
        </Box>
        <Grid container spacing={1.5}>
          <Grid item xs={12} sm={4} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>País</InputLabel>
              <Select value={pais} label="País" onChange={e => setPais(e.target.value)}>
                <MenuItem value="">Todos</MenuItem>
                {(filtros?.paises ?? []).map(p => (
                  <MenuItem key={p.CodigoPais} value={p.CodigoPais}>{p.CodigoPais} — {p.NombrePais}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Provincia</InputLabel>
              <Select value={provincia} label="Provincia" onChange={e => setProvincia(e.target.value)} disabled={!filtros?.provincias.length}>
                <MenuItem value="">Todas</MenuItem>
                {(filtros?.provincias ?? []).map(p => <MenuItem key={p} value={p}>{p}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={4} md={2}>
            <FormControl fullWidth size="small">
              <InputLabel>Municipio</InputLabel>
              <Select value={municipio} label="Municipio" onChange={e => setMunicipio(e.target.value)} disabled={!filtros?.municipios.length}>
                <MenuItem value="">Todos</MenuItem>
                {(filtros?.municipios ?? []).map(m => <MenuItem key={m} value={m}>{m}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>Especialidad</InputLabel>
              <Select value={especialidad} label="Especialidad" onChange={e => setEspecialidad(e.target.value)}>
                <MenuItem value="">Todas</MenuItem>
                {(filtros?.especialidades ?? []).map(e => <MenuItem key={e} value={e}>{e}</MenuItem>)}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={6} md={3}>
            <FormControl fullWidth size="small">
              <InputLabel>Representante</InputLabel>
              <Select value={representante} label="Representante" onChange={e => setRepresentante(e.target.value)}>
                <MenuItem value="">Todos</MenuItem>
                {(filtros?.representantes ?? []).map(r => (
                  <MenuItem key={r.CodigoRepresentante} value={r.NombreRepresentante}>{r.NombreRepresentante}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
        </Grid>
        {/* ── Filtro por categoría ── */}
        <Box mt={2} display="flex" gap={1} flexWrap="wrap" alignItems="center">
          <Typography sx={{ fontSize: '0.7rem', fontWeight: 700, color: '#90a4ae', mr: 0.5, textTransform: 'uppercase', letterSpacing: 0.8 }}>
            Categoría:
          </Typography>

          {/* ── "Todas" — activo por defecto cuando categoria='' ── */}
          <Box
            onClick={() => setCategoria('')}
            sx={{
              display: 'inline-flex', alignItems: 'center', gap: 0.7,
              px: 1.6, py: 0.6, borderRadius: '24px', cursor: 'pointer', userSelect: 'none',
              transition: 'all 0.2s ease',
              // ACTIVO cuando no hay categoría seleccionada
              ...(categoria === '' ? {
                background: 'linear-gradient(135deg, #686158 0%, #283593 50%, #3949ab 100%)',
                color: '#fff',
                border: '2px solid transparent',
                boxShadow: '0 4px 14px #3949ab50',
              } : {
                background: '#f5f7fa',
                color: '#78909c',
                border: '2px solid #e0e4ea',
                boxShadow: 'none',
                '&:hover': {
                  background: 'linear-gradient(135deg, #686158 0%, #3949ab 100%)',
                  color: '#fff',
                  borderColor: 'transparent',
                  boxShadow: '0 4px 14px #3949ab50',
                },
              }),
            }}
          >
            <Box sx={{
              width: 20, height: 20, borderRadius: '50%', flexShrink: 0,
              display: 'flex', alignItems: 'center', justifyContent: 'center',
              fontSize: '0.62rem', fontWeight: 900,
              bgcolor: categoria === '' ? 'rgba(255,255,255,0.22)' : '#e8eaf6',
              color: categoria === '' ? '#fff' : '#3949ab',
            }}>✦</Box>
            <Typography sx={{ fontSize: '0.77rem', fontWeight: 700, color: 'inherit', lineHeight: 1 }}>
              Todas
            </Typography>
          </Box>

          {/* ── Chips A / B / C / D ── */}
          {(['A','B','C','D'] as const).map(cat => {
            const pal = CAT_PAL[cat];
            const sel = categoria === cat;
            return (
              <Box
                key={cat}
                onClick={() => setCategoria(sel ? '' : cat)}
                sx={{
                  display: 'inline-flex', alignItems: 'center', gap: 0.8,
                  px: 1.6, py: 0.6, borderRadius: '24px', cursor: 'pointer', userSelect: 'none',
                  transition: 'all 0.2s ease',
                  // ── ACTIVO (seleccionado) ──
                  ...(sel ? {
                    background: `linear-gradient(135deg, ${pal.dark} 0%, ${pal.mid} 100%)`,
                    color: '#fff',
                    border: '2px solid transparent',
                    boxShadow: `0 4px 16px ${pal.glow}`,
                  } : {
                    // ── INACTIVO — gris neutro, nunca parece seleccionado ──
                    background: '#f5f7fa',
                    color: '#78909c',
                    border: '2px solid #e0e4ea',
                    boxShadow: 'none',
                    '&:hover': {
                      background: `linear-gradient(135deg, ${pal.dark} 0%, ${pal.mid} 100%)`,
                      color: '#fff',
                      borderColor: 'transparent',
                      boxShadow: `0 4px 16px ${pal.glow}`,
                    },
                  }),
                }}
              >
                {/* Letra en círculo */}
                <Box sx={{
                  width: 22, height: 22, borderRadius: '50%', flexShrink: 0,
                  display: 'flex', alignItems: 'center', justifyContent: 'center',
                  fontWeight: 900, fontSize: '0.73rem',
                  transition: 'all 0.2s ease',
                  bgcolor: sel ? 'rgba(255,255,255,0.22)' : '#e0e4ea',
                  color: sel ? '#fff' : '#546e7a',
                  border: sel ? '1.5px solid rgba(255,255,255,0.35)' : '1.5px solid #cfd8dc',
                }}>
                  {cat}
                </Box>
                <Box>
                  <Typography sx={{ fontSize: '0.77rem', fontWeight: 700, lineHeight: 1.1, color: 'inherit' }}>
                    Cat. {cat}
                  </Typography>
                  <Typography sx={{
                    fontSize: '0.6rem', fontWeight: 500, lineHeight: 1.2, mt: 0.1,
                    color: sel ? 'rgba(255,255,255,0.78)' : '#b0bec5',
                  }}>
                    {CAT_LABEL[cat]}
                  </Typography>
                </Box>
              </Box>
            );
          })}
        </Box>
      </Paper>

      {/* ── KPI mini-cards de totales ── */}
      {statsGlobales && (
        <Grid container spacing={1.5} mb={2}>
          <Grid item>
            <Box sx={{
              px: 2.5, py: 1.2, borderRadius: 2,
              bgcolor: '#f0f4ff', border: '1px solid #c5cae9',
              minWidth: 110, textAlign: 'center',
            }}>
              <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#1565c0', lineHeight: 1.2 }}>
                {statsGlobales.total_medicos.toLocaleString()}
              </Typography>
              <Typography sx={{ fontSize: '0.68rem', color: '#78909c', fontWeight: 600 }}>Total médicos</Typography>
            </Box>
          </Grid>
          {(['A','B','C','D'] as const).map(cat => {
            const key = `categoria_${cat.toLowerCase()}` as 'categoria_a'|'categoria_b'|'categoria_c'|'categoria_d';
            const pal = CAT_PAL[cat];
            const n = statsGlobales[key] ?? 0;
            const pct = statsGlobales.total_medicos > 0
              ? Math.round((n / statsGlobales.total_medicos) * 100)
              : 0;
            return (
              <Grid item key={cat}>
                <Box sx={{
                  px: 2.5, py: 1.2, borderRadius: 2,
                  background: `linear-gradient(135deg, ${pal.dark} 0%, ${pal.mid} 100%)`,
                  boxShadow: `0 2px 10px ${pal.glow}`,
                  minWidth: 110, textAlign: 'center',
                  opacity: (categoria && categoria !== cat) ? 0.4 : 1,
                  transition: 'opacity 0.2s',
                }}>
                  <Typography sx={{ fontSize: '1.25rem', fontWeight: 800, color: '#fff', lineHeight: 1.2 }}>
                    {n.toLocaleString()}
                  </Typography>
                  <Typography sx={{ fontSize: '0.68rem', color: 'rgba(255,255,255,0.8)', fontWeight: 600 }}>
                    Cat. {cat} · {pct}%
                  </Typography>
                </Box>
              </Grid>
            );
          })}
        </Grid>
      )}

      {/* ── Gráficos — usan totales globales (no solo página actual) ── */}
      {catCountsGlobal.length > 0 && (
        <Grid container spacing={2} mb={3}>
          {/* Pie — distribución global */}
          <Grid item xs={12} md={5}>
            <Paper elevation={0} sx={{ p: 2, border: '1px solid #e3e8f0', borderRadius: 3, height: 260 }}>
              <Typography fontWeight={700} sx={{ fontSize: '0.82rem', color: 'text.secondary', mb: 1, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Distribución por Categoría
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <PieChart>
                  <Pie
                    data={catCountsGlobal}
                    dataKey="value"
                    nameKey="name"
                    cx="50%" cy="50%"
                    outerRadius={75}
                    paddingAngle={3}
                    label={({ name, percent }) => `${name} ${(percent * 100).toFixed(0)}%`}
                  >
                    {catCountsGlobal.map((entry) => (
                      <Cell key={entry.cat} fill={CAT_COLORS[['A','B','C','D'].indexOf(entry.cat)]} />
                    ))}
                  </Pie>
                  <ReTooltip formatter={(v: number, name: string) => [`${v} médicos`, name]} />
                  <Legend iconSize={10} formatter={(v) => <span style={{ fontSize: '0.78rem' }}>{v}</span>} />
                </PieChart>
              </ResponsiveContainer>
            </Paper>
          </Grid>
          {/* Bar — cantidad por categoría (global) */}
          <Grid item xs={12} md={7}>
            <Paper elevation={0} sx={{ p: 2, border: '1px solid #e3e8f0', borderRadius: 3, height: 260 }}>
              <Typography fontWeight={700} sx={{ fontSize: '0.82rem', color: 'text.secondary', mb: 1, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                Médicos por Categoría
              </Typography>
              <ResponsiveContainer width="100%" height={200}>
                <BarChart
                  data={catCountsGlobal.map(d => ({
                    cat: d.name,
                    cantidad: d.value,
                    pct: statsGlobales && statsGlobales.total_medicos > 0
                      ? parseFloat(((d.value / statsGlobales.total_medicos) * 100).toFixed(1))
                      : 0,
                    catCode: d.cat,
                  }))}
                  margin={{ top: 5, right: 20, left: 0, bottom: 5 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#f0f0f0" />
                  <XAxis dataKey="cat" tick={{ fontSize: 12, fontWeight: 700 }} />
                  <YAxis tick={{ fontSize: 11 }} tickFormatter={v => v.toLocaleString()} />
                  <ReTooltip formatter={(v: number, name: string, props: any) => [
                    `${v.toLocaleString()} médicos (${props.payload.pct}%)`,
                    'Total',
                  ]} />
                  <Bar dataKey="cantidad" radius={[6,6,0,0]}>
                    {catCountsGlobal.map((entry) => (
                      <Cell key={entry.cat} fill={CAT_COLORS[['A','B','C','D'].indexOf(entry.cat)]} />
                    ))}
                  </Bar>
                </BarChart>
              </ResponsiveContainer>
            </Paper>
          </Grid>
        </Grid>
      )}

      {/* ── Tabla de médicos ── */}
      <Paper elevation={0} sx={{ border: '1px solid #e3e8f0', borderRadius: 3, overflow: 'hidden' }}>
        {/* Header degradado */}
        <Box
          sx={{
            background: 'linear-gradient(135deg, #584F46 0%, #1565c0 40%, #1976d2 100%)',
            px: 3, py: 1.5,
            display: 'flex', justifyContent: 'space-between', alignItems: 'center',
          }}
        >
          <Box>
            <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '1rem', letterSpacing: 0.3 }}>
              DETALLE POR MÉDICO
            </Typography>
            <Typography sx={{ color: 'rgba(255,255,255,0.75)', fontSize: '0.75rem' }}>
              {total.toLocaleString()} médico{total !== 1 ? 's' : ''} encontrado{total !== 1 ? 's' : ''}
              {hayFiltros ? ' con filtros aplicados' : ''}
            </Typography>
          </Box>
          <Box display="flex" gap={0.8} flexWrap="wrap">
            {(['A','B','C','D'] as const).map(cat => {
              const n = items.filter(i => i.CategoriaCalculada === cat).length;
              if (!n) return null;
              const pal = CAT_PAL[cat];
              return (
                <Box key={cat} sx={{
                  display: 'inline-flex', alignItems: 'center', gap: 0.5,
                  px: 1, py: 0.3, borderRadius: '14px',
                  background: `linear-gradient(135deg, ${pal.dark} 0%, ${pal.mid} 100%)`,
                  boxShadow: `0 2px 6px ${pal.glow}`,
                  border: '1.5px solid rgba(255,255,255,0.3)',
                }}>
                  <Box sx={{
                    width: 16, height: 16, borderRadius: '50%',
                    bgcolor: 'rgba(255,255,255,0.28)',
                    display: 'flex', alignItems: 'center', justifyContent: 'center',
                    fontSize: '0.6rem', fontWeight: 900, color: '#fff',
                  }}>{cat}</Box>
                  <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: '0.7rem' }}>
                    {n.toLocaleString()}
                  </Typography>
                </Box>
              );
            })}
          </Box>
        </Box>

        {isLoading && <LinearProgress />}

        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ bgcolor: '#1976d2' }}>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', py: 0.8, minWidth: 30 }}></TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 180 }}>MÉDICO</TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 130 }}>ESPECIALIDAD</TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 110 }}>PROVINCIA</TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 110 }}>MUNICIPIO</TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 150 }}>REPRESENTANTE</TableCell>
                <TableCell sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 160 }}>PUNTAJE TOTAL</TableCell>
                <TableCell align="center" sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 90 }}>CATEGORÍA</TableCell>
                <TableCell align="center" sx={{ color: '#fff', fontWeight: 700, fontSize: '0.73rem', minWidth: 80 }}>PERÍODO</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {items.length === 0 && !isLoading && (
                <TableRow>
                  <TableCell colSpan={9} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                    <SearchIcon sx={{ fontSize: 48, color: '#e0e0e0', display: 'block', mx: 'auto', mb: 1 }} />
                    {detalleError
                      ? <Typography color="error" variant="body2" sx={{ fontFamily: 'monospace', maxWidth: 600, mx: 'auto' }}>
                          Error del servidor: {(detalleError as {message?: string})?.message ?? String(detalleError)}
                          <br />Revisa los logs de uvicorn y el endpoint <code>/api/v1/categorizacion/diagnostico</code>
                        </Typography>
                      : <Typography>No se encontraron médicos con los filtros seleccionados</Typography>
                    }
                  </TableCell>
                </TableRow>
              )}
              {items.map((row, idx) => {
                const isExp = expanded === row.MedicoCategoriaKey;
                const pal = CAT_PAL[row.CategoriaCalculada] ?? CAT_PAL['?'];
                return (
                  <>
                    <TableRow
                      key={row.MedicoCategoriaKey}
                      hover
                      sx={{
                        bgcolor: idx % 2 === 0 ? '#fff' : '#f7f9ff',
                        borderLeft: `4px solid ${pal.mid}`,
                        cursor: 'pointer',
                        '&:hover': { bgcolor: pal.light + '80' },
                      }}
                      onClick={() => setExpanded(isExp ? null : row.MedicoCategoriaKey)}
                    >
                      <TableCell sx={{ px: 1, py: 0.5 }}>
                        <IconButton size="small" sx={{ p: 0.3 }}>
                          {isExp ? <ExpandLessIcon fontSize="small" sx={{ color: pal.mid }} /> : <ExpandMoreIcon fontSize="small" sx={{ color: '#9e9e9e' }} />}
                        </IconButton>
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: '0.82rem', py: 0.8 }}>
                        {row.NombreMedico}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', color: 'text.secondary', py: 0.8 }}>
                        {row.Especialidad}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', py: 0.8 }}>
                        {(row.Provincia && row.Provincia !== '—')
                          ? row.Provincia
                          : <Typography component="span" sx={{ fontSize: '0.72rem', color: '#bdbdbd', fontStyle: 'italic' }}>N/D</Typography>}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', py: 0.8 }}>
                        {(row.Municipio && row.Municipio !== '—')
                          ? row.Municipio
                          : <Typography component="span" sx={{ fontSize: '0.72rem', color: '#bdbdbd', fontStyle: 'italic' }}>N/D</Typography>}
                      </TableCell>
                      <TableCell sx={{ fontSize: '0.78rem', py: 0.8 }}>
                        <Box>
                          <Typography sx={{ fontSize: '0.78rem', fontWeight: 600 }}>{row.Representante}</Typography>
                          {row.Equipo && row.Equipo !== '—' && (
                            <Typography sx={{ fontSize: '0.68rem', color: 'text.secondary' }}>{row.Equipo}</Typography>
                          )}
                        </Box>
                      </TableCell>
                      <TableCell sx={{ py: 0.8, minWidth: 160 }}>
                        <ScoreBar value={row.PuntajeTotalPct} />
                      </TableCell>
                      <TableCell align="center" sx={{ py: 0.8 }}>
                        <CatChip cat={row.CategoriaCalculada} />
                        {row.CategoriaExcel && row.CategoriaExcel !== '—' && row.CategoriaExcel !== row.CategoriaCalculada && (
                          <Tooltip title={`Categoría Excel: ${row.CategoriaExcel}`}>
                            <Typography sx={{ fontSize: '0.64rem', color: '#f57c00', mt: 0.3, cursor: 'help' }}>
                              ⚠ Excel: {row.CategoriaExcel}
                            </Typography>
                          </Tooltip>
                        )}
                      </TableCell>
                      <TableCell align="center" sx={{ fontSize: '0.75rem', color: 'text.secondary', py: 0.8 }}>
                        {row.Periodo}
                      </TableCell>
                    </TableRow>
                    {isExp && (
                      <TableRow key={`exp-${row.MedicoCategoriaKey}`}>
                        <TableCell colSpan={9} sx={{ p: 0, bgcolor: '#f0f4f8' }}>
                          <Collapse in={isExp} unmountOnExit>
                            <Box sx={{ px: 2, py: 1 }}>
                              <Typography sx={{ fontSize: '0.75rem', fontWeight: 700, color: pal.mid, mb: 1, textTransform: 'uppercase', letterSpacing: 0.5 }}>
                                Desglose de componentes — {row.NombreMedico}
                              </Typography>
                              <ComponenteRow key_={row.MedicoCategoriaKey} />
                            </Box>
                          </Collapse>
                        </TableCell>
                      </TableRow>
                    )}
                  </>
                );
              })}
            </TableBody>
          </Table>
        </Box>
   
        <TablePagination
          component="div"
          count={total}
          page={page}
          onPageChange={(_, p) => setPage(p)}
          rowsPerPage={rowsPerPage}
          onRowsPerPageChange={(e) => { setRowsPerPage(parseInt(e.target.value)); setPage(0); }}
          rowsPerPageOptions={[10, 25, 50, 100]}
          labelRowsPerPage="Filas:"
          sx={{ borderTop: '1px solid #e0e0e0', bgcolor: '#fafafa' }}
        />
      </Paper>
    </Box>
  );
}
