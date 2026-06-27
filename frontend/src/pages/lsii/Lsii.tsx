/**
 * Lsii.tsx — Módulo Matriz de Desarrollo LSII
 * Liderazgo Situacional II: cruza Desempeño × Receptividad/Compromiso
 * para ubicar cada VM en D1/D2/D3/D4 y sugerir el estilo de liderazgo del GD.
 *
 * Ejes (corte = 80):
 *   X = Receptividad / Compromiso  (0-100)
 *   Y = Desempeño   / Competencia  (0-100, alto arriba — sin reversed)
 *
 * Cuadrantes:
 *   D1 br → bajo desempeño + alta receptividad   → Dirigir
 *   D2 bl → bajo desempeño + baja receptividad   → Entrenar
 *   D3 tl → alto desempeño + baja receptividad   → Apoyar
 *   D4 tr → alto desempeño + alta receptividad   → Delegar
 */
import { useMemo, useState, useEffect } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, Chip, CircularProgress,
  TextField, MenuItem, Alert, Tabs, Tab, Button, Divider,
  LinearProgress,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Tooltip,
} from '@mui/material';
import {
  Groups, Star, CheckCircle, PersonSearch,
} from '@mui/icons-material';
import {
  ScatterChart, Scatter, XAxis, YAxis, CartesianGrid,
  Tooltip as RTooltip, ResponsiveContainer, ReferenceLine, ReferenceArea,
  PieChart, Pie, Cell, Legend, BarChart, Bar, LabelList,
} from 'recharts';
import { api } from '../../services/api';
import { useAuthStore } from '../../store/auth.store';
import type {
  ReceptividadDimension, SeleccionReceptividad, MatrizLsiiItem, NivelLsii,
} from '../../types';

// ── roles evaluadores ─────────────────────────────────────────────────────────
const ROLES_EVALUADOR = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO', 'GERENTE_MARCA'];

const CORTE = 80;

// ── paleta LSII — alineada a la carta de colores del sistema ─────────────────
// D1 Dirigir  = Ambar   → tiene actitud, necesita guia
// D2 Entrenar = Rojo    → critico, necesita entrenamiento + motivacion
// D3 Apoyar   = Azul    → alto desempeno, necesita apoyo emocional
// D4 Delegar  = Teal    → estrella, alta autonomia
type PalEntry = { color: string; light: string; grad: string; label: string };
const NIVEL_PAL: Record<string, PalEntry> = {
  D1: { color: '#ef6c00', light: '#fff3e0', grad: 'linear-gradient(135deg,#e65100,#ef6c00)', label: 'D1 · Dirigir' },
  D2: { color: '#c62828', light: '#ffebee', grad: 'linear-gradient(135deg,#b71c1c,#c62828)', label: 'D2 · Entrenar' },
  D3: { color: '#1565c0', light: '#e3f2fd', grad: 'linear-gradient(135deg,#1a237e,#1565c0)', label: 'D3 · Apoyar' },
  D4: { color: '#00695c', light: '#e0f2f1', grad: 'linear-gradient(135deg,#004d40,#00695c)', label: 'D4 · Delegar' },
};
function nivPal(nivel: string): PalEntry {
  return NIVEL_PAL[nivel]
    ?? { color: '#546e7a', light: '#eceff1', grad: 'linear-gradient(135deg,#37474f,#546e7a)', label: nivel };
}

// ── descripciones de cuadrante ────────────────────────────────────────────────
const CUAD: Record<NivelLsii, { perfil: string; foco: string; rec: string; accion: string }> = {
  D1: {
    perfil: 'Bajo desempeno + Alta receptividad',
    foco: 'Actitud positiva, necesita estructura y guia clara.',
    rec: 'Dirigir de cerca',
    accion: 'Dar objetivos claros, instrucciones paso a paso y seguimiento estrecho.',
  },
  D2: {
    perfil: 'Bajo desempeno + Baja receptividad',
    foco: 'Requiere entrenamiento tecnico y refuerzo motivacional.',
    rec: 'Entrenar y motivar',
    accion: 'Acompanamiento cercano, explicar el por que y reforzar habilidades.',
  },
  D3: {
    perfil: 'Alto desempeno + Baja receptividad',
    foco: 'Capaz pero necesita reconocimiento y apoyo emocional.',
    rec: 'Apoyar y reconocer',
    accion: 'Escuchar barreras, reforzar confianza y acordar proximos pasos.',
  },
  D4: {
    perfil: 'Alto desempeno + Alta receptividad',
    foco: 'Listo para mayor autonomia y responsabilidad.',
    rec: 'Delegar y empoderar',
    accion: 'Dar autonomia, empoderar con confianza y monitorear por hitos.',
  },
};

// ── utilidades ─────────────────────────────────────────────────────────────────
function initials(nombre: string) {
  const parts = (nombre || '').trim().split(/\s+/).filter(Boolean);
  if (!parts.length) return '..';
  if (parts.length === 1) return parts[0].slice(0, 2).toUpperCase();
  return (parts[0][0] + parts[1][0]).toUpperCase();
}

// ── etiquetas de esquina SVG ──────────────────────────────────────────────────
function cornerLabel(corner: 'tl' | 'tr' | 'bl' | 'br', title: string, sub: string, color: string) {
  return (props: Record<string, unknown>) => {
    const vb = props.viewBox as { x: number; y: number; width: number; height: number } | undefined;
    if (!vb) return null;
    const pad = 12;
    const isRight = corner === 'tr' || corner === 'br';
    const isBottom = corner === 'bl' || corner === 'br';
    const x = isRight ? vb.x + vb.width - pad : vb.x + pad;
    const anchor = isRight ? 'end' : 'start';
    const y1 = isBottom ? vb.y + vb.height - pad - 16 : vb.y + pad + 12;
    const y2 = isBottom ? vb.y + vb.height - pad : vb.y + pad + 27;
    return (
      <g>
        <text x={x} y={y1} textAnchor={anchor} fontSize={11.5} fontWeight={900} fill={color}>{title}</text>
        <text x={x} y={y2} textAnchor={anchor} fontSize={9} fill={color} fillOpacity={0.72}>{sub}</text>
      </g>
    );
  };
}

// ── tooltip del scatter ────────────────────────────────────────────────────────
const MatrizTooltip = ({ active, payload }: { active?: boolean; payload?: { payload: MatrizLsiiItem }[] }) => {
  if (!active || !payload?.length) return null;
  const d = payload[0].payload;
  const pal = nivPal(d.nivel_lsii);
  const desc = CUAD[d.nivel_lsii];
  return (
    <Box sx={{ bgcolor: 'white', border: `1.5px solid ${pal.color}40`, borderRadius: 2, p: 1.5, boxShadow: 4, minWidth: 240, maxWidth: 280 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.8 }}>
        <Box sx={{ width: 30, height: 30, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.65rem' }}>{initials(d.rm_nombre)}</Typography>
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography fontWeight={800} fontSize="0.82rem" sx={{ overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{d.rm_nombre}</Typography>
          {d.gerente_nombre && <Typography fontSize="0.68rem" color="text.secondary">GD: <b>{d.gerente_nombre}</b></Typography>}
        </Box>
      </Box>
      <Box sx={{ display: 'flex', gap: 2, mb: 0.8 }}>
        <Box>
          <Typography fontSize="0.66rem" color="text.secondary">Desempeno</Typography>
          <Typography fontWeight={800} fontSize="0.88rem" color="#00695c">{Number(d.score_desempeno).toFixed(1)}</Typography>
        </Box>
        <Box>
          <Typography fontSize="0.66rem" color="text.secondary">Receptividad</Typography>
          <Typography fontWeight={800} fontSize="0.88rem" color="#1565c0">{Number(d.score_receptividad).toFixed(1)}</Typography>
        </Box>
      </Box>
      <Chip label={pal.label} size="small" sx={{ bgcolor: pal.light, color: pal.color, fontWeight: 800, fontSize: '0.7rem', height: 22, mb: 0.5 }} />
      <Typography fontSize="0.68rem" color="text.secondary" mt={0.3}>{desc.accion}</Typography>
    </Box>
  );
};

// ── punto custom del scatter ──────────────────────────────────────────────────
function CustomDot(props: Record<string, unknown>) {
  const { cx, cy, payload } = props as { cx?: number; cy?: number; payload: MatrizLsiiItem };
  if (cx == null || cy == null) return null;
  const pal = nivPal(payload.nivel_lsii);
  return (
    <g>
      <circle cx={cx} cy={cy} r={20} fill={pal.color} stroke="white" strokeWidth={2.5} fillOpacity={0.9} />
      <text x={cx} y={cy} textAnchor="middle" dominantBaseline="central" fontSize={8.5} fontWeight={900} fill="white">
        {initials(payload.rm_nombre)}
      </text>
    </g>
  );
}

// ── mini anillo KPI ───────────────────────────────────────────────────────────
function KpiRing({ value, color, label, caption }: { value: number; color: string; label: string; caption: string }) {
  const pct = Math.min(100, Math.max(0, value));
  return (
    <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%' }}>
      <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1.5, '&:last-child': { pb: 1.5 } }}>
        <Box sx={{ position: 'relative', width: 56, height: 56, flexShrink: 0 }}>
          <ResponsiveContainer width={56} height={56}>
            <PieChart>
              <Pie data={[{ v: pct }, { v: 100 - pct }]} dataKey="v" cx="50%" cy="50%"
                innerRadius={18} outerRadius={26} startAngle={90} endAngle={-270} stroke="none" isAnimationActive={false}>
                <Cell fill={color} />
                <Cell fill="#e8eaf6" />
              </Pie>
            </PieChart>
          </ResponsiveContainer>
          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
            <Typography fontSize="0.65rem" fontWeight={900} sx={{ color }}>{value.toFixed(0)}</Typography>
          </Box>
        </Box>
        <Box sx={{ minWidth: 0 }}>
          <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem', color: 'text.secondary', display: 'block', letterSpacing: 0.5 }}>{label}</Typography>
          <Typography fontWeight={900} fontSize="1.15rem" sx={{ color, lineHeight: 1.15 }}>{value.toFixed(1)}%</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.67rem' }}>{caption}</Typography>
        </Box>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────────
export default function Lsii() {
  const { rol } = useAuthStore();
  const puedeEvaluar = !!rol && ROLES_EVALUADOR.includes(rol);
  const qc = useQueryClient();

  const [tab, setTab] = useState(0);
  const [paisId, setPaisId] = useState('');
  const [cicloId, setCicloId] = useState('');
  const [gerenteId, setGerenteId] = useState('');

  const { data: paises } = useQuery({ queryKey: ['paises'], queryFn: () => api.get('/admin/paises').then(r => r.data) });
  const { data: ciclos } = useQuery({ queryKey: ['ciclos', paisId], queryFn: () => api.get('/admin/ciclos', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data) });
  const { data: gerentes } = useQuery({ queryKey: ['gerentes', paisId], queryFn: () => api.get('/admin/gerentes', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data), enabled: !!paisId });
  const { data: rms } = useQuery({ queryKey: ['rms', paisId, gerenteId], queryFn: () => api.get('/admin/rms', { params: { ...(paisId && { pais_codigo: paisId }), ...(gerenteId && { gerente_id: gerenteId }) } }).then(r => r.data), enabled: !!paisId });

  useEffect(() => {
    if (!(paises as unknown[])?.length || paisId) return;
    const rd = (paises as { id: number; codigo: string; nombre: string }[]).find(p => p.codigo?.toUpperCase() === 'RD' || p.nombre?.toLowerCase().includes('dominicana'));
    if (rd) setPaisId(rd.codigo);
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps

  // ── Matriz ──────────────────────────────────────────────────────────────────
  const { data: matriz, isLoading: loadMatriz } = useQuery({
    queryKey: ['lsii-matriz', paisId, cicloId, gerenteId],
    queryFn: () => api.get('/lsii/matriz', { params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: Number(cicloId) }), ...(gerenteId && { gerente_id: Number(gerenteId) }) } }).then(r => r.data as MatrizLsiiItem[]),
  });

  const resumen = useMemo(() => {
    const items = matriz || [];
    if (!items.length) return null;
    const porNivel: Record<string, number> = { D1: 0, D2: 0, D3: 0, D4: 0 };
    let sumaD = 0, sumaR = 0;
    items.forEach(i => { porNivel[i.nivel_lsii] = (porNivel[i.nivel_lsii] || 0) + 1; sumaD += Number(i.score_desempeno) || 0; sumaR += Number(i.score_receptividad) || 0; });
    const total = items.length;
    const dominante = (Object.entries(porNivel) as [NivelLsii, number][]).sort((a, b) => b[1] - a[1])[0][0];
    return { total, porNivel, promedioDesempeno: sumaD / total, promedioReceptividad: sumaR / total, dominante };
  }, [matriz]);

  const ejeMax = useMemo(() => {
    const items = matriz || [];
    const mD = items.reduce((m, d) => Math.max(m, Number(d.score_desempeno) || 0), 100);
    const mR = items.reduce((m, d) => Math.max(m, Number(d.score_receptividad) || 0), 100);
    const ceil = (v: number) => Math.ceil((v + 5) / 10) * 10;
    return { y: Math.max(ceil(mD), CORTE + 10), x: Math.max(ceil(mR), CORTE + 10) };
  }, [matriz]);

  const distribucionData = useMemo(() => {
    if (!resumen) return [];
    return (['D1', 'D2', 'D3', 'D4'] as NivelLsii[]).map(n => {
      const pal = nivPal(n);
      const count = resumen.porNivel[n] || 0;
      return { nivel: n, name: pal.label, value: count, color: pal.color, pct: resumen.total ? (count / resumen.total) * 100 : 0 };
    });
  }, [resumen]);

  // ── Formulario de evaluacion ────────────────────────────────────────────────
  const { data: catalogo, isLoading: loadCatalogo } = useQuery({
    queryKey: ['lsii-catalogo'],
    queryFn: () => api.get('/lsii/catalogo').then(r => r.data as ReceptividadDimension[]),
    enabled: puedeEvaluar && tab === 1,
  });

  const [evalRmId, setEvalRmId] = useState('');
  const [selecciones, setSelecciones] = useState<Record<string, number>>({});
  const [observaciones, setObservaciones] = useState('');
  const [resultado, setResultado] = useState<Record<string, unknown> | null>(null);

  const dimensiones = catalogo || [];
  const completadas = dimensiones.filter(d => selecciones[d.dimension_codigo] != null).length;
  const formListo = !!paisId && !!cicloId && !!evalRmId && completadas === dimensiones.length && dimensiones.length > 0;

  const mutEvaluar = useMutation({
    mutationFn: () => api.post('/lsii/evaluar', {
      pais_codigo: paisId,
      rm_id: Number(evalRmId),
      ciclo_id: Number(cicloId),
      gerente_id: gerenteId ? Number(gerenteId) : undefined,
      observaciones: observaciones || undefined,
      selecciones: Object.entries(selecciones).map(([dimension_codigo, opcion_id]) => ({ dimension_codigo, opcion_id } as SeleccionReceptividad)),
    }).then(r => r.data),
    onSuccess: (data) => {
      setResultado(data as Record<string, unknown>);
      setSelecciones({});
      setObservaciones('');
      qc.invalidateQueries({ queryKey: ['lsii-matriz'] });
    },
  });

  const ciclosArr = (ciclos as { id: number; nombre_canonico?: string; nombre?: string }[]) || [];
  const rmsArr = (rms as { id: number; nombre: string; codigo: string }[]) || [];
  const gerentesArr = (gerentes as { id: number; nombre: string }[]) || [];
  const paisesArr = (paises as { id: number; codigo: string; nombre: string }[]) || [];
  const cicloLabel = ciclosArr.find(c => String(c.id) === cicloId)?.nombre_canonico ?? ciclosArr.find(c => String(c.id) === cicloId)?.nombre ?? '';

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box>
      {/* Encabezado */}
      <Box sx={{ background: 'linear-gradient(135deg,#1a237e 0%,#1565c0 60%,#0288d1 100%)', borderRadius: 3, p: { xs: 2, md: 2.5 }, mb: 3, color: '#fff', display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
        <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: 'rgba(255,255,255,0.15)', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
          <Groups sx={{ fontSize: 28, color: '#fff' }} />
        </Box>
        <Box sx={{ flex: 1, minWidth: 200 }}>
          <Typography variant="h5" fontWeight={900} sx={{ color: '#fff', letterSpacing: '-0.3px', lineHeight: 1.2 }}>Matriz de Desarrollo LSII</Typography>
          <Typography variant="body2" sx={{ color: 'rgba(255,255,255,0.82)' }}>Liderazgo Situacional II &middot; Desempeno &times; Receptividad / Compromiso</Typography>
        </Box>
        <Box sx={{ display: 'flex', gap: 1, flexWrap: 'wrap' }}>
          {(['D1', 'D2', 'D3', 'D4'] as const).map(n => {
            const p = NIVEL_PAL[n];
            return (
              <Box key={n} sx={{ px: 1.2, py: 0.4, borderRadius: 2, bgcolor: 'rgba(255,255,255,0.12)', border: '1px solid rgba(255,255,255,0.25)', display: 'flex', alignItems: 'center', gap: 0.5 }}>
                <Box sx={{ width: 7, height: 7, borderRadius: '50%', bgcolor: p.color }} />
                <Typography sx={{ fontSize: '0.72rem', fontWeight: 700, color: '#fff' }}>{p.label.split('·')[1]?.trim()}</Typography>
              </Box>
            );
          })}
        </Box>
      </Box>

      {/* Filtros */}
      <Card elevation={0} sx={{ mb: 2.5, border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Pais" value={paisId}
                onChange={e => { setPaisId(e.target.value); setCicloId(''); setGerenteId(''); setEvalRmId(''); }}>
                {paisesArr.map(p => <MenuItem key={p.id} value={p.codigo}>{p.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Ciclo" value={cicloId} onChange={e => setCicloId(e.target.value)}>
                <MenuItem value="">Todos los ciclos</MenuItem>
                {ciclosArr.map(c => <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Gerente de Distrito" value={gerenteId} onChange={e => { setGerenteId(e.target.value); setEvalRmId(''); }}>
                <MenuItem value="">Todos los gerentes</MenuItem>
                {gerentesArr.map(g => <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>)}
              </TextField>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Tabs */}
      <Box mb={3}>
        <Tabs value={tab} onChange={(_, v) => setTab(v as number)} variant="scrollable" scrollButtons="auto"
          sx={{ borderBottom: '3px solid #1565c0', '& .MuiTab-root': { bgcolor: '#bbdefb', borderTopLeftRadius: 8, borderTopRightRadius: 8, mr: 0.5, color: '#1565c0', fontWeight: 600, minHeight: 40, fontSize: 13, textTransform: 'none', '&.Mui-selected': { bgcolor: '#1565c0', color: '#fff', fontWeight: 700 }, '&:hover:not(.Mui-selected)': { bgcolor: '#90caf9' } }, '& .MuiTabs-indicator': { display: 'none' } }}>
          <Tab label="Matriz de Desarrollo" />
          {puedeEvaluar && <Tab label="Nueva Evaluacion" />}
        </Tabs>
      </Box>

      {/* TAB 0 - MATRIZ */}
      {tab === 0 && (
        loadMatriz ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', mt: 8 }}><CircularProgress /></Box>
        ) : !matriz?.length ? (
          <Alert severity="info" sx={{ borderRadius: 2 }}>
            No hay evaluaciones LSII registradas para estos filtros. Usa la pestana "Nueva Evaluacion" para registrar la primera.
          </Alert>
        ) : (
          <>
            {/* KPI cards */}
            <Grid container spacing={2} mb={3}>
              <Grid item xs={6} sm={3}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%' }}>
                  <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: '#e3f2fd', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Groups sx={{ color: '#1565c0', fontSize: 24 }} />
                    </Box>
                    <Box>
                      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem', color: 'text.secondary', display: 'block', letterSpacing: 0.5 }}>Colaboradores</Typography>
                      <Typography fontWeight={900} fontSize="1.7rem" color="#1565c0" sx={{ lineHeight: 1.1 }}>{resumen?.total}</Typography>
                      <Typography variant="caption" color="text.secondary">Evaluados</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} sm={3}>
                <KpiRing value={resumen!.promedioDesempeno} color="#00695c" label="Desempeno Promedio" caption="Promedio del equipo" />
              </Grid>
              <Grid item xs={6} sm={3}>
                <KpiRing value={resumen!.promedioReceptividad} color="#1565c0" label="Receptividad Promedio" caption="Promedio del equipo" />
              </Grid>
              <Grid item xs={6} sm={3}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%' }}>
                  <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: nivPal(resumen!.dominante).light, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Star sx={{ color: nivPal(resumen!.dominante).color, fontSize: 24 }} />
                    </Box>
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem', color: 'text.secondary', display: 'block', letterSpacing: 0.5 }}>Nivel Dominante</Typography>
                      <Typography fontWeight={900} fontSize="1.5rem" sx={{ color: nivPal(resumen!.dominante).color, lineHeight: 1.1 }}>{resumen!.dominante}</Typography>
                      <Chip label={nivPal(resumen!.dominante).label.split('·')[1]?.trim()} size="small"
                        sx={{ bgcolor: nivPal(resumen!.dominante).light, color: nivPal(resumen!.dominante).color, fontWeight: 700, fontSize: '0.62rem', height: 19, mt: 0.2 }} />
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
            </Grid>

            {/* Scatter + Resumen por cuadrante */}
            <Grid container spacing={3} mb={3} alignItems="stretch">
              <Grid item xs={12} md={8}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <Box sx={{ background: 'linear-gradient(135deg,#1a237e,#1565c0)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8, display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
                    <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5, flexGrow: 1 }}>MATRIZ LSII - DESEMPENO x RECEPTIVIDAD</Typography>
                    <Chip label={`${resumen?.total} VMs`} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.18)', color: '#fff', fontWeight: 700, fontSize: '0.72rem' }} />
                  </Box>
                  <Box sx={{ flex: 1, p: 2, minHeight: 420 }}>
                    <ResponsiveContainer width="100%" height="100%">
                      <ScatterChart margin={{ top: 24, right: 32, left: 8, bottom: 30 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#e8eaf6" />
                        {/* Sin reversed: Y alto arriba = alto desempeno
                            D2 bl (x<80,y<80)  |  D1 br (x>=80,y<80)
                            D3 tl (x<80,y>=80) |  D4 tr (x>=80,y>=80) */}
                        <ReferenceArea x1={0} x2={CORTE} y1={0} y2={CORTE}
                          fill={NIVEL_PAL.D2.light} fillOpacity={0.7}
                          label={cornerLabel('bl', 'D2 - Entrenar', 'Bajo desempeno - Baja rec.', NIVEL_PAL.D2.color)} />
                        <ReferenceArea x1={CORTE} x2={ejeMax.x} y1={0} y2={CORTE}
                          fill={NIVEL_PAL.D1.light} fillOpacity={0.7}
                          label={cornerLabel('br', 'D1 - Dirigir', 'Bajo desempeno - Alta rec.', NIVEL_PAL.D1.color)} />
                        <ReferenceArea x1={0} x2={CORTE} y1={CORTE} y2={ejeMax.y}
                          fill={NIVEL_PAL.D3.light} fillOpacity={0.7}
                          label={cornerLabel('tl', 'D3 - Apoyar', 'Alto desempeno - Baja rec.', NIVEL_PAL.D3.color)} />
                        <ReferenceArea x1={CORTE} x2={ejeMax.x} y1={CORTE} y2={ejeMax.y}
                          fill={NIVEL_PAL.D4.light} fillOpacity={0.7}
                          label={cornerLabel('tr', 'D4 - Delegar', 'Alto desempeno - Alta rec.', NIVEL_PAL.D4.color)} />
                        <ReferenceLine x={CORTE} stroke="#78909c" strokeWidth={1.5} strokeDasharray="5 4"
                          label={{ value: `${CORTE}`, position: 'top', fontSize: 10, fill: '#78909c' }} />
                        <ReferenceLine y={CORTE} stroke="#78909c" strokeWidth={1.5} strokeDasharray="5 4"
                          label={{ value: `${CORTE}`, position: 'right', fontSize: 10, fill: '#78909c' }} />
                        <XAxis type="number" dataKey="score_receptividad" name="Receptividad" domain={[0, ejeMax.x]}
                          tick={{ fontSize: 11, fill: '#78909c' }}
                          label={{ value: 'Receptividad / Compromiso', position: 'insideBottom', offset: -16, fontSize: 12, fill: '#546e7a', fontWeight: 600 }} />
                        <YAxis type="number" dataKey="score_desempeno" name="Desempeno" domain={[0, ejeMax.y]}
                          tick={{ fontSize: 11, fill: '#78909c' }}
                          label={{ value: 'Desempeno / Competencia', angle: -90, position: 'insideLeft', offset: 10, fontSize: 12, fill: '#546e7a', fontWeight: 600 }} />
                        <RTooltip content={<MatrizTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                        <Scatter data={matriz} shape={CustomDot} />
                      </ScatterChart>
                    </ResponsiveContainer>
                  </Box>
                </Card>
              </Grid>

              <Grid item xs={12} md={4}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <Box sx={{ background: 'linear-gradient(135deg,#37474f,#546e7a)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8, flexShrink: 0 }}>
                    <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>RESUMEN POR CUADRANTE</Typography>
                  </Box>
                  <Box sx={{ flex: 1, p: 2, display: 'flex', flexDirection: 'column', gap: 1.5, overflowY: 'auto' }}>
                    {(['D4', 'D3', 'D1', 'D2'] as NivelLsii[]).map(n => {
                      const pal = nivPal(n);
                      const desc = CUAD[n];
                      const count = resumen?.porNivel[n] || 0;
                      const pct = resumen?.total ? ((count / resumen.total) * 100).toFixed(1) : '0.0';
                      return (
                        <Box key={n} sx={{ p: 1.5, borderRadius: 2, bgcolor: pal.light, border: `1.5px solid ${pal.color}30`, display: 'flex', alignItems: 'flex-start', gap: 1.5 }}>
                          <Box sx={{ width: 40, height: 40, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.82rem' }}>{n}</Typography>
                          </Box>
                          <Box sx={{ minWidth: 0, flex: 1 }}>
                            <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                              <Typography sx={{ color: pal.color, fontWeight: 800, fontSize: '0.75rem' }}>{pal.label}</Typography>
                              <Typography sx={{ color: pal.color, fontWeight: 800, fontSize: '0.75rem' }}>{count} <span style={{ opacity: 0.7 }}>({pct}%)</span></Typography>
                            </Box>
                            <Typography fontSize="0.7rem" sx={{ color: pal.color, fontWeight: 600, opacity: 0.85 }}>{desc.perfil}</Typography>
                            <Typography fontSize="0.67rem" color="text.secondary" mt={0.2}>{desc.foco}</Typography>
                          </Box>
                        </Box>
                      );
                    })}
                    <Divider />
                    <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.63rem', lineHeight: 1.5 }}>
                      Corte en <b>{CORTE} pts</b> en ambos ejes. La receptividad se calcula a partir de comportamientos observados — los puntajes son internos y no se muestran al evaluador.
                    </Typography>
                  </Box>
                </Card>
              </Grid>
            </Grid>

            {/* Distribucion + Tabla de detalle */}
            <Grid container spacing={3}>
              <Grid item xs={12} md={4}>
                <Box sx={{ display: 'flex', flexDirection: 'column', gap: 3, height: '100%' }}>
                  <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, flex: 1 }}>
                    <Box sx={{ background: 'linear-gradient(135deg,#1a237e,#283593)', px: 2.5, py: 1.2, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
                      <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.85rem', letterSpacing: 0.5 }}>DISTRIBUCION POR NIVEL</Typography>
                    </Box>
                    <Box sx={{ minHeight: 210, p: 1 }}>
                      <ResponsiveContainer width="100%" height={210}>
                        <PieChart>
                          <Pie data={distribucionData} dataKey="value" nameKey="name" cx="50%" cy="44%"
                            innerRadius="36%" outerRadius="60%" paddingAngle={3} stroke="none" isAnimationActive={false}>
                            {distribucionData.map((d, i) => <Cell key={i} fill={d.color} />)}
                          </Pie>
                          <RTooltip formatter={(v: number, _n: string, p: { payload: typeof distribucionData[0] }) => [`${v} (${p?.payload?.pct?.toFixed(1)}%)`, p?.payload?.name]} />
                          <Legend content={() => (
                            <Box sx={{ display: 'flex', flexWrap: 'wrap', justifyContent: 'center', gap: 1, pt: 0.5 }}>
                              {distribucionData.map((d, i) => (
                                <Box key={i} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                  <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: d.color }} />
                                  <Typography fontSize="0.68rem" fontWeight={700}>{d.nivel} {d.value}</Typography>
                                </Box>
                              ))}
                            </Box>
                          )} />
                        </PieChart>
                      </ResponsiveContainer>
                    </Box>
                  </Card>
                  <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, flex: 1 }}>
                    <Box sx={{ background: 'linear-gradient(135deg,#37474f,#455a64)', px: 2.5, py: 1.2, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
                      <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.85rem', letterSpacing: 0.5 }}>COLABORADORES POR CUADRANTE</Typography>
                    </Box>
                    <Box sx={{ minHeight: 190, p: 1, pt: 2 }}>
                      <ResponsiveContainer width="100%" height={190}>
                        <BarChart data={distribucionData} margin={{ top: 18, right: 8, left: -22, bottom: 0 }}>
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e8eaf6" />
                          <XAxis dataKey="nivel" tick={{ fontSize: 11, fontWeight: 700 }} />
                          <YAxis allowDecimals={false} width={28} tick={{ fontSize: 10, fill: '#78909c' }} />
                          <RTooltip formatter={(v: number, _n: string, p: { payload: typeof distribucionData[0] }) => [v, p?.payload?.name]} />
                          <Bar dataKey="value" name="Colaboradores" radius={[8, 8, 0, 0]} isAnimationActive={false}>
                            {distribucionData.map((d, i) => <Cell key={i} fill={d.color} />)}
                            <LabelList dataKey="value" position="top" style={{ fontWeight: 800, fontSize: 12, fill: '#37474f' }} />
                          </Bar>
                        </BarChart>
                      </ResponsiveContainer>
                    </Box>
                  </Card>
                </Box>
              </Grid>

              <Grid item xs={12} md={8}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%', display: 'flex', flexDirection: 'column' }}>
                  <Box sx={{ background: 'linear-gradient(135deg,#1a237e,#1565c0)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8, flexShrink: 0 }}>
                    <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>DETALLE POR COLABORADOR</Typography>
                  </Box>
                  <TableContainer sx={{ flex: 1 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow sx={{ '& th': { bgcolor: '#f5f7fa', borderBottom: '2px solid #e0e7ef', color: 'text.secondary', fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase', py: 1 } }}>
                          <TableCell>Colaborador</TableCell>
                          <TableCell>Desempeno</TableCell>
                          <TableCell>Receptividad</TableCell>
                          <TableCell align="center">Nivel</TableCell>
                          <TableCell>Accion recomendada</TableCell>
                          <TableCell align="center">Fecha</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {[...(matriz || [])].sort((a, b) => a.rm_nombre.localeCompare(b.rm_nombre)).map(r => {
                          const pal = nivPal(r.nivel_lsii);
                          const desc = CUAD[r.nivel_lsii];
                          return (
                            <TableRow key={r.rm_id} hover sx={{ '& td': { borderBottom: '1px solid #f0f2f5' }, '&:hover': { bgcolor: pal.light } }}>
                              <TableCell sx={{ py: 0.8 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                                  <Box sx={{ width: 28, height: 28, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                                    <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.6rem' }}>{initials(r.rm_nombre)}</Typography>
                                  </Box>
                                  <Typography fontWeight={600} fontSize="0.8rem">{r.rm_nombre}</Typography>
                                </Box>
                              </TableCell>
                              <TableCell sx={{ py: 0.8 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, minWidth: 90 }}>
                                  <Typography fontWeight={700} fontSize="0.76rem" sx={{ minWidth: 32, color: '#00695c' }}>{Number(r.score_desempeno).toFixed(1)}</Typography>
                                  <LinearProgress variant="determinate" value={Math.min(100, Number(r.score_desempeno))}
                                    sx={{ flex: 1, height: 5, borderRadius: 3, bgcolor: '#e0f2f1', '& .MuiLinearProgress-bar': { bgcolor: '#00695c', borderRadius: 3 } }} />
                                </Box>
                              </TableCell>
                              <TableCell sx={{ py: 0.8 }}>
                                <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.8, minWidth: 90 }}>
                                  <Typography fontWeight={700} fontSize="0.76rem" sx={{ minWidth: 32, color: '#1565c0' }}>{Number(r.score_receptividad).toFixed(1)}</Typography>
                                  <LinearProgress variant="determinate" value={Math.min(100, Number(r.score_receptividad))}
                                    sx={{ flex: 1, height: 5, borderRadius: 3, bgcolor: '#e3f2fd', '& .MuiLinearProgress-bar': { bgcolor: '#1565c0', borderRadius: 3 } }} />
                                </Box>
                              </TableCell>
                              <TableCell align="center" sx={{ py: 0.8 }}>
                                <Box sx={{ display: 'inline-flex', px: 1.2, py: 0.3, borderRadius: 2, background: pal.grad }}>
                                  <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.7rem', whiteSpace: 'nowrap' }}>{pal.label}</Typography>
                                </Box>
                              </TableCell>
                              <TableCell sx={{ py: 0.8 }}>
                                <Tooltip title={desc.accion} placement="top">
                                  <Typography fontSize="0.73rem" color="text.secondary" sx={{ maxWidth: 180, overflow: 'hidden', whiteSpace: 'nowrap', textOverflow: 'ellipsis', cursor: 'default' }}>{desc.accion}</Typography>
                                </Tooltip>
                              </TableCell>
                              <TableCell align="center" sx={{ py: 0.8, whiteSpace: 'nowrap', fontSize: '0.73rem', color: 'text.secondary' }}>
                                {new Date(r.fecha_evaluacion).toLocaleDateString()}
                              </TableCell>
                            </TableRow>
                          );
                        })}
                      </TableBody>
                    </Table>
                  </TableContainer>
                </Card>
              </Grid>
            </Grid>
          </>
        )
      )}

      {/* TAB 1 - NUEVA EVALUACION */}
      {tab === 1 && puedeEvaluar && (
        <Grid container spacing={3}>
          <Grid item xs={12} md={8}>
            <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <Box sx={{ background: 'linear-gradient(135deg,#1a237e,#1565c0)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
                <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>EVALUACION DE RECEPTIVIDAD / COMPROMISO</Typography>
                <Typography sx={{ color: 'rgba(255,255,255,0.82)', fontSize: '0.78rem', mt: 0.3 }}>Seleccione el comportamiento que mejor describe al colaborador en cada dimension</Typography>
              </Box>
              <CardContent>
                <Grid container spacing={2} mb={2.5}>
                  <Grid item xs={12} sm={6}>
                    <TextField select fullWidth size="small" label="Representante Medico" value={evalRmId}
                      onChange={e => setEvalRmId(e.target.value)} disabled={!paisId || !rmsArr.length}>
                      <MenuItem value="">Seleccionar colaborador...</MenuItem>
                      {rmsArr.map(r => <MenuItem key={r.id} value={r.id}>{r.nombre} ({r.codigo})</MenuItem>)}
                    </TextField>
                  </Grid>
                  <Grid item xs={12} sm={6}>
                    <TextField fullWidth size="small" label="Ciclo seleccionado" value={cicloLabel} disabled
                      helperText={!cicloId ? 'Selecciona un ciclo en los filtros superiores' : ' '} />
                  </Grid>
                </Grid>

                {dimensiones.length > 0 && (
                  <Box mb={2.5} sx={{ p: 1.5, bgcolor: '#f8fafd', borderRadius: 2, border: '1px solid #e0e7ef' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="caption" fontWeight={700} color="text.secondary">Progreso de evaluacion</Typography>
                      <Typography variant="caption" fontWeight={800} color={completadas === dimensiones.length ? '#00695c' : '#1565c0'}>{completadas} / {dimensiones.length}</Typography>
                    </Box>
                    <LinearProgress variant="determinate" value={(completadas / dimensiones.length) * 100}
                      sx={{ height: 8, borderRadius: 4, bgcolor: '#e3f2fd', '& .MuiLinearProgress-bar': { bgcolor: completadas === dimensiones.length ? '#00695c' : '#1565c0', borderRadius: 4 } }} />
                  </Box>
                )}

                {loadCatalogo ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress size={28} /></Box>
                ) : (
                  dimensiones.map((dim, idx) => {
                    const sel = selecciones[dim.dimension_codigo] != null;
                    const selectedOpId = selecciones[dim.dimension_codigo];
                    return (
                      <Box key={dim.dimension_codigo} sx={{ mb: 2, borderRadius: 2, border: `1.5px solid ${sel ? '#1565c040' : '#e0e7ef'}`, overflow: 'hidden', transition: 'border-color 0.2s' }}>
                        {/* Cabecera de dimensión */}
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, px: 2, py: 1.2, bgcolor: sel ? '#eef4fd' : '#f8fafd', borderBottom: '1px solid #e8eaf6' }}>
                          <Box sx={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, mt: 0.1, bgcolor: sel ? '#1565c0' : '#e0e7ef', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Typography sx={{ color: sel ? '#fff' : '#546e7a', fontWeight: 900, fontSize: '0.65rem' }}>{idx + 1}</Typography>
                          </Box>
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography fontWeight={700} fontSize="0.85rem" color="#37474f">{dim.dimension_nombre}</Typography>
                            {dim.dimension_descripcion && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.35, mt: 0.2 }}>{dim.dimension_descripcion}</Typography>
                            )}
                          </Box>
                          {sel && <CheckCircle sx={{ color: '#1565c0', fontSize: 18, flexShrink: 0, mt: 0.1 }} />}
                        </Box>
                        {/* Opciones como filas */}
                        {dim.opciones.map((op, oi) => {
                          const isSelected = selectedOpId === op.id;
                          return (
                            <Box key={op.id}
                              onClick={() => setSelecciones(s => ({ ...s, [dim.dimension_codigo]: op.id }))}
                              sx={{
                                display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 0.9,
                                cursor: 'pointer',
                                bgcolor: isSelected ? '#ddeeff' : 'transparent',
                                borderLeft: `3px solid ${isSelected ? '#1565c0' : 'transparent'}`,
                                borderBottom: oi < dim.opciones.length - 1 ? '1px solid #f0f2f5' : 'none',
                                transition: 'background 0.15s, border-color 0.15s',
                                '&:hover': { bgcolor: isSelected ? '#cce4f7' : '#f5f7fa' },
                              }}>
                              {/* Dot radio personalizado */}
                              <Box sx={{
                                width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                                border: `2px solid ${isSelected ? '#1565c0' : '#b0bec5'}`,
                                bgcolor: isSelected ? '#1565c0' : 'transparent',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                transition: 'all 0.15s',
                              }}>
                                {isSelected && <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#fff' }} />}
                              </Box>
                              <Typography fontSize="0.82rem" sx={{ lineHeight: 1.4, color: isSelected ? '#0d47a1' : '#546e7a', fontWeight: isSelected ? 600 : 400 }}>
                                {op.texto_comportamiento}
                              </Typography>
                            </Box>
                          );
                        })}
                      </Box>
                    );
                  })
                )}

                <TextField fullWidth multiline minRows={2} size="small" label="Observaciones del GD (opcional)"
                  value={observaciones} onChange={e => setObservaciones(e.target.value)} sx={{ mb: 2 }} />

                {mutEvaluar.isError && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {(mutEvaluar.error as { response?: { data?: { detail?: string } } })?.response?.data?.detail || 'No se pudo registrar la evaluacion.'}
                  </Alert>
                )}

                <Button variant="contained" disabled={!formListo || mutEvaluar.isPending} size="large" fullWidth
                  onClick={() => mutEvaluar.mutate()}
                  sx={{ borderRadius: 2, fontWeight: 700, py: 1.2, background: formListo ? 'linear-gradient(135deg,#1a237e,#1565c0)' : undefined }}>
                  {mutEvaluar.isPending ? 'Registrando...' : 'Registrar Evaluacion LSII'}
                </Button>
              </CardContent>
            </Card>
          </Grid>

          {/* Panel resultado */}
          <Grid item xs={12} md={4}>
            <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, position: 'sticky', top: 80 }}>
              <Box sx={{ background: 'linear-gradient(135deg,#37474f,#546e7a)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
                <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>RESULTADO DEL CRUCE LSII</Typography>
              </Box>
              <CardContent>
                {!resultado ? (
                  <Box sx={{ py: 4, textAlign: 'center' }}>
                    <PersonSearch sx={{ fontSize: 52, color: '#cfd8dc', mb: 1 }} />
                    <Typography variant="body2" color="text.secondary">
                      Al registrar la evaluacion, aqui se mostrara el nivel LSII y el estilo de liderazgo recomendado.
                    </Typography>
                  </Box>
                ) : (() => {
                  const pal = nivPal(String(resultado.nivel_lsii));
                  const desc = CUAD[resultado.nivel_lsii as NivelLsii];
                  const rmNombre = rmsArr.find(r => String(r.id) === evalRmId)?.nombre || '';
                  return (
                    <Box>
                      {rmNombre && (
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, mb: 2 }}>
                          <Box sx={{ width: 44, height: 44, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                            <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.78rem' }}>{initials(rmNombre)}</Typography>
                          </Box>
                          <Box>
                            <Typography fontWeight={700} fontSize="0.9rem">{rmNombre}</Typography>
                            <Typography variant="caption" color="success.main" fontWeight={700}>Evaluacion registrada</Typography>
                          </Box>
                        </Box>
                      )}
                      <Divider sx={{ mb: 2 }} />
                      <Box sx={{ p: 2, borderRadius: 2, background: pal.grad, mb: 2, textAlign: 'center' }}>
                        <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '1.6rem', lineHeight: 1.2 }}>{String(resultado.nivel_lsii)}</Typography>
                        <Typography sx={{ color: 'rgba(255,255,255,0.92)', fontWeight: 700, fontSize: '0.92rem' }}>{String(resultado.estilo_liderazgo ?? '')}</Typography>
                      </Box>
                      <Box mb={1.5}>
                        <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', fontWeight: 700, fontSize: '0.58rem', letterSpacing: 0.5 }}>Perfil detectado</Typography>
                        <Typography fontSize="0.82rem" fontWeight={600} mt={0.3}>{desc?.perfil}</Typography>
                      </Box>
                      <Grid container spacing={1.5} mb={1.5}>
                        <Grid item xs={6}>
                          <Box sx={{ p: 1, bgcolor: '#e0f2f1', borderRadius: 1.5, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem', display: 'block' }}>Desempeno</Typography>
                            <Typography fontWeight={800} color="#00695c" fontSize="1rem">
                              {resultado.score_desempeno != null ? Number(resultado.score_desempeno).toFixed(1) : '-'}
                            </Typography>
                          </Box>
                        </Grid>
                        <Grid item xs={6}>
                          <Box sx={{ p: 1, bgcolor: '#e3f2fd', borderRadius: 1.5, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem', display: 'block' }}>Receptividad</Typography>
                            <Typography fontWeight={800} color="#1565c0" fontSize="1rem">{Number(resultado.score_receptividad).toFixed(1)}</Typography>
                          </Box>
                        </Grid>
                      </Grid>
                      <Box sx={{ p: 1.2, bgcolor: pal.light, borderRadius: 2, border: `1px solid ${pal.color}20` }}>
                        <Typography variant="caption" sx={{ fontWeight: 700, color: pal.color, textTransform: 'uppercase', fontSize: '0.58rem' }}>Accion recomendada</Typography>
                        <Typography fontSize="0.8rem" mt={0.3} color="text.secondary">{desc?.accion}</Typography>
                      </Box>
                    </Box>
                  );
                })()}
              </CardContent>
            </Card>
          </Grid>
        </Grid>
      )}
    </Box>
  );
}
