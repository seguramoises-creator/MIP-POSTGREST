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
import { useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useCicloStore } from '../../store/ciclo.store';
import {
  Box, Typography, Card, CardContent, Grid, Chip, CircularProgress,
  TextField, MenuItem, Alert, Tabs, Tab, Button, Divider,
  LinearProgress, Popover,
  Dialog, DialogTitle, DialogContent, DialogActions,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Tooltip,
} from '@mui/material';
import {
  Groups, Star, CheckCircle, PersonSearch, Leaderboard,
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

// ── paleta LSII — carta oficial SLII (nomenclatura D) ────────────────────────
// D1 Dirigir             = Rojo     → bajo desempeno + alta receptividad
// D2 Entrenar            = Mamey    → bajo desempeno + baja receptividad
// D3 Apoyar              = Amarillo → alto desempeno + baja receptividad
// D4 Delegar/Empoderar   = Verde ⭐ → nivel estrella, alta autonomia
// `fill` = color solido del cuadrante en la matriz (como la carta SLII);
// `color`/`light` = variantes legibles para chips, textos y tarjetas.
type PalEntry = { color: string; light: string; fill: string; grad: string; label: string };
const NIVEL_PAL: Record<string, PalEntry> = {
  D1: { color: '#d32f2f', light: '#ffebee', fill: '#f04438', grad: 'linear-gradient(135deg,#b71c1c,#e53935)', label: 'D1 · Dirigir' },
  D2: { color: '#ef6c00', light: '#fff3e0', fill: '#f09d4e', grad: 'linear-gradient(135deg,#e65100,#f57c00)', label: 'D2 · Entrenar' },
  D3: { color: '#f9a825', light: '#fff8e1', fill: '#ffde59', grad: 'linear-gradient(135deg,#f9a825,#fbc02d)', label: 'D3 · Apoyar' },
  D4: { color: '#2e7d32', light: '#e8f5e9', fill: '#3dbd6d', grad: 'linear-gradient(135deg,#1b5e20,#2e7d32)', label: 'D4 · Delegar/Empoderar' },
};
function nivPal(nivel: string): PalEntry {
  return NIVEL_PAL[nivel]
    ?? { color: '#546e7a', light: '#EDE9E4', fill: '#cfd8dc', grad: 'linear-gradient(135deg,#37474f,#546e7a)', label: nivel };
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
// `onInfo` (opcional) agrega un símbolo ⓘ clicable junto al título del cuadrante:
// al hacer clic abre el detalle de los colaboradores de ese cuadrante (Popover).
function cornerLabel(corner: 'tl' | 'tr' | 'bl' | 'br', title: string, sub: string, color: string,
                     onInfo?: (e: React.MouseEvent) => void) {
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
      <g onClick={onInfo} style={onInfo ? { cursor: 'pointer' } : undefined}>
        <text x={x} y={y1} textAnchor={anchor} fontSize={11.5} fontWeight={900} fill={color}>
          {onInfo && isRight ? 'ⓘ  ' : ''}{title}{onInfo && !isRight ? '  ⓘ' : ''}
        </text>
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
          <Typography fontWeight={800} fontSize="0.88rem" color="#584F46">{Number(d.score_receptividad).toFixed(1)}</Typography>
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
                <Cell fill="#EFEBE6" />
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

  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloGlobal = useCicloStore((s) => s.cicloId);
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);
  const setCicloVer = useCicloStore((s) => s.setCicloVer);
  const paisId = paisCodigo ?? '';
  const cicloId = cicloGlobal != null ? String(cicloGlobal) : '';
  const [tab, setTab] = useState(0);
  const [gerenteId, setGerenteId] = useState('');
  // Detalle por cuadrante: clic en el ⓘ de la matriz → lista de colaboradores
  // de ese nivel (mismo dato que el tooltip de cada punto, pero en lista).
  const [cuadrantePop, setCuadrantePop] = useState<{ nivel: NivelLsii; x: number; y: number } | null>(null);
  const abrirCuadrante = (nivel: NivelLsii) => (e: React.MouseEvent) =>
    setCuadrantePop({ nivel, x: e.clientX, y: e.clientY });

  // Cortes vigentes (configurables por admin): desempeño y receptividad pueden
  // tener cortes DISTINTOS — el gráfico debe usar los mismos que el backend usa
  // al clasificar, o los puntos aparecen "fuera" de su cuadrante.
  const { data: cfgLsii } = useQuery({
    queryKey: ['lsii-config'],
    queryFn: () => api.get('/lsii/configuracion').then(r => r.data as { corte_desempeno: number; corte_receptividad: number }),
  });
  const corteD = Number(cfgLsii?.corte_desempeno ?? CORTE);
  const corteR = Number(cfgLsii?.corte_receptividad ?? CORTE);

  const { data: ciclos } = useQuery({ queryKey: ['ciclos', paisId], queryFn: () => api.get('/admin/ciclos', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data) });
  const { data: gerentes } = useQuery({ queryKey: ['gerentes', paisId], queryFn: () => api.get('/admin/gerentes', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data), enabled: !!paisId });
  const { data: rms } = useQuery({ queryKey: ['rms', paisId, gerenteId], queryFn: () => api.get('/admin/rms', { params: { ...(paisId && { pais_codigo: paisId }), ...(gerenteId && { gerente_id: gerenteId }) } }).then(r => r.data), enabled: !!paisId });

  // ── Matriz ──────────────────────────────────────────────────────────────────
  const { data: matriz, isLoading: loadMatriz } = useQuery({
    queryKey: ['lsii-matriz', paisId, cicloId, gerenteId],
    queryFn: () => api.get('/lsii/matriz', { params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: Number(cicloId) }), ...(gerenteId && { gerente_id: Number(gerenteId) }) } }).then(r => r.data as MatrizLsiiItem[]),
  });

  // Clasificación EN VIVO con los cortes vigentes: el nivel guardado en cada
  // evaluación es un snapshot de los cortes de aquel momento; si el admin los
  // cambia después, los puntos quedarían "fuera" de su cuadrante. Para la matriz
  // y sus resúmenes, el nivel se recalcula siempre con los cortes actuales —
  // una sola regla para el plano, los puntos, el resumen y el detalle.
  const matrizV = useMemo(() => {
    // Coordenadas de DIBUJO (des_plot/rec_plot): se apartan un margen mínimo de
    // las líneas de corte y de los bordes para que el círculo completo del punto
    // quede dentro de su cuadrante (un score pegado al corte, p. ej. rec 100 con
    // corte 95, derramaría medio círculo al cuadrante vecino). Los scores REALES
    // no cambian: son los que muestran el tooltip y el detalle.
    const mX = corteD * 0.2, mY = corteR * 0.2;   // 10% del dominio de cada eje —
    // mayor que el radio del punto: el círculo queda claramente DENTRO de su D.
    const aj = (v: number, corte: number, max: number, m: number) =>
      v >= corte ? Math.min(Math.max(v, corte + m), max - m)
                 : Math.max(Math.min(v, corte - m), m);
    return (matriz || []).map(m => {
      const d = Number(m.score_desempeno), r = Number(m.score_receptividad);
      const altoD = d >= corteD, altaR = r >= corteR;
      const nivel: NivelLsii = altoD ? (altaR ? 'D4' : 'D3') : (altaR ? 'D1' : 'D2');
      return { ...m, nivel_lsii: nivel,
               des_plot: aj(d, corteD, corteD * 2, mX),
               rec_plot: aj(r, corteR, corteR * 2, mY) };
    });
  }, [matriz, corteD, corteR]);

  const resumen = useMemo(() => {
    const items = matrizV;
    if (!items.length) return null;
    const porNivel: Record<string, number> = { D1: 0, D2: 0, D3: 0, D4: 0 };
    let sumaD = 0, sumaR = 0;
    items.forEach(i => { porNivel[i.nivel_lsii] = (porNivel[i.nivel_lsii] || 0) + 1; sumaD += Number(i.score_desempeno) || 0; sumaR += Number(i.score_receptividad) || 0; });
    const total = items.length;
    const dominante = (Object.entries(porNivel) as [NivelLsii, number][]).sort((a, b) => b[1] - a[1])[0][0];
    return { total, porNivel, promedioDesempeno: sumaD / total, promedioReceptividad: sumaR / total, dominante };
  }, [matrizV]);

  // Cuadrantes de igual tamaño (como la carta SLII): cada corte queda exactamente
  // al centro de su eje → los 4 cuadrados miden lo mismo, aun con cortes distintos.
  const ejeMax = useMemo(() => ({ x: corteD * 2, y: corteR * 2 }), [corteD, corteR]);

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

  // Aviso de re-evaluación: si el RM seleccionado ya tiene evaluación en el
  // ciclo, se advierte (ciclo + fecha) y se pide confirmación Sí/No antes de
  // permitir reemplazarla. "Reemplazar" = registrar una nueva evaluación; la
  // matriz siempre muestra la última por RM (el histórico se conserva).
  const [reemplazoAceptado, setReemplazoAceptado] = useState(false);
  const evalPrevia = useMemo(
    () => matrizV.find(m => String(m.rm_id) === String(evalRmId)) || null,
    [matrizV, evalRmId]);

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
  // Solo Gerentes de DISTRITO: el catálogo DIM_Gerente también trae gerentes
  // de Marca/Producto (tipo MARCA), que no evalúan LSII.
  const gerentesArr = ((gerentes as { id: number; nombre: string; tipo?: string }[]) || [])
    .filter(g => (g.tipo || '').toUpperCase() === 'DISTRITO');
  const cicloLabel = ciclosArr.find(c => String(c.id) === cicloId)?.nombre_canonico ?? ciclosArr.find(c => String(c.id) === cicloId)?.nombre ?? '';

  // ── Render ─────────────────────────────────────────────────────────────────
  return (
    <Box>
      {/* Encabezado */}
      <Box sx={{ background: 'linear-gradient(135deg,#686158 0%,#584F46 60%,#686158 100%)', borderRadius: 3, p: { xs: 2, md: 2.5 }, mb: 3, color: '#fff', display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
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

      {/* Filtros — orden: Ciclo → Gerente de Distrito → Representante Médico.
          El Ciclo escribe en el contexto global (la franja País+Ciclo del layout
          se oculta en esta página para no duplicar filtros). */}
      <Card elevation={0} sx={{ mb: 2.5, border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Ciclo" value={cicloId}
                onChange={e => { setCicloVer(Number(e.target.value)); setReemplazoAceptado(false); setResultado(null); }}>
                {ciclosArr.map(c => (
                  <MenuItem key={c.id} value={String(c.id)}>{c.nombre_canonico || c.nombre}</MenuItem>
                ))}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Gerente de Distrito" value={gerenteId} onChange={e => { setGerenteId(e.target.value); setEvalRmId(''); }}>
                <MenuItem value="">Todos los gerentes</MenuItem>
                {gerentesArr.map(g => <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Representante Medico" value={evalRmId}
                onChange={e => { setEvalRmId(e.target.value); setReemplazoAceptado(false); setResultado(null); }}
                disabled={!paisId || !rmsArr.length}>
                <MenuItem value="">Seleccionar colaborador...</MenuItem>
                {rmsArr.map(r => <MenuItem key={r.id} value={r.id}>{r.nombre} ({r.codigo})</MenuItem>)}
              </TextField>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      {/* Aviso: RM ya evaluado en este ciclo → confirmar reemplazo (Sí/No).
          "No" deselecciona al RM; "Sí" habilita el formulario para re-evaluar. */}
      <Dialog
        open={tab === 1 && !!evalPrevia && !reemplazoAceptado && !resultado}
        onClose={() => setEvalRmId('')}
        maxWidth="xs" fullWidth
      >
        <DialogTitle sx={{ color: '#e65100', fontWeight: 800, display: 'flex', alignItems: 'center', gap: 1 }}>
          ⚠️ Representante Médico ya evaluado
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            <b>{evalPrevia?.rm_nombre}</b> ya tiene una evaluación registrada en el ciclo{' '}
            <b>{cicloLabel || cicloId}</b> con fecha{' '}
            <b>{evalPrevia ? new Date(evalPrevia.fecha_evaluacion).toLocaleDateString() : ''}</b>
            {' '}(resultado: <b>{evalPrevia?.nivel_lsii}</b>).
          </Typography>
          <Typography variant="body2" mt={1.5} fontWeight={700}>
            ¿Desea reemplazar la evaluación ya realizada?
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button color="inherit" onClick={() => setEvalRmId('')}>No</Button>
          <Button variant="contained" color="warning" onClick={() => setReemplazoAceptado(true)}>
            Sí, reemplazar
          </Button>
        </DialogActions>
      </Dialog>

      {/* Tabs */}
      <Box mb={3}>
        <Tabs value={tab} onChange={(_, v) => setTab(v as number)} variant="scrollable" scrollButtons="auto"
          sx={{ borderBottom: '3px solid #584F46', '& .MuiTab-root': { bgcolor: '#D8D2CB', borderTopLeftRadius: 8, borderTopRightRadius: 8, mr: 0.5, color: '#584F46', fontWeight: 600, minHeight: 40, fontSize: 13, textTransform: 'none', '&.Mui-selected': { bgcolor: '#584F46', color: '#fff', fontWeight: 700 }, '&:hover:not(.Mui-selected)': { bgcolor: '#D8D2CB' } }, '& .MuiTabs-indicator': { display: 'none' } }}>
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
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: '#F4F1EE', display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      <Groups sx={{ color: '#584F46', fontSize: 24 }} />
                    </Box>
                    <Box>
                      <Typography variant="caption" sx={{ fontWeight: 700, textTransform: 'uppercase', fontSize: '0.58rem', color: 'text.secondary', display: 'block', letterSpacing: 0.5 }}>Colaboradores</Typography>
                      <Typography fontWeight={900} fontSize="1.7rem" color="#584F46" sx={{ lineHeight: 1.1 }}>{resumen?.total}</Typography>
                      <Typography variant="caption" color="text.secondary">Evaluados</Typography>
                    </Box>
                  </CardContent>
                </Card>
              </Grid>
              <Grid item xs={6} sm={3}>
                <KpiRing value={resumen!.promedioDesempeno} color="#00695c" label="Desempeno Promedio" caption="Promedio del equipo" />
              </Grid>
              <Grid item xs={6} sm={3}>
                <KpiRing value={resumen!.promedioReceptividad} color="#584F46" label="Receptividad Promedio" caption="Promedio del equipo" />
              </Grid>
              <Grid item xs={6} sm={3}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, height: '100%' }}>
                  <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 1.5, py: 1.5, '&:last-child': { pb: 1.5 } }}>
                    <Box sx={{ width: 48, height: 48, borderRadius: '50%', bgcolor: nivPal(resumen!.dominante).light, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                      {/* La estrella identifica a D4 (nivel meta); el dominante es un dato → Leaderboard. */}
                      <Leaderboard sx={{ color: nivPal(resumen!.dominante).color, fontSize: 24 }} />
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
                  <Box sx={{ background: 'linear-gradient(135deg,#686158,#584F46)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8, display: 'flex', alignItems: 'center', gap: 1.5, flexShrink: 0 }}>
                    <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5, flexGrow: 1 }}>MATRIZ LSII - DESEMPENO x RECEPTIVIDAD</Typography>
                    <Chip label={`${resumen?.total} VMs`} size="small" sx={{ bgcolor: 'rgba(255,255,255,0.18)', color: '#fff', fontWeight: 700, fontSize: '0.72rem' }} />
                  </Box>
                  {/* Lienzo CUADRADO (aspect 1:1) centrado: los 4 cuadrantes quedan
                      con el mismo largo que ancho, como la carta SLII. */}
                  <Box sx={{ flex: 1, p: 2, display: 'flex', justifyContent: 'center' }}>
                    <Box sx={{ width: '100%', maxWidth: 700 }}>
                      <ResponsiveContainer width="100%" aspect={1}>
                      <ScatterChart margin={{ top: 24, right: 32, left: 8, bottom: 30 }}>
                        <CartesianGrid strokeDasharray="3 3" stroke="#EFEBE6" />
                        {/* Sin reversed: Y alto arriba = alto desempeno
                            D2 bl (x<80,y<80)  |  D1 br (x>=80,y<80)
                            D3 tl (x<80,y>=80) |  D4 tr (x>=80,y>=80) */}
                        {/* Layout idéntico a la carta SLII: D3 amarillo tl, D2 mamey tr,
                            D4 verde bl, D1 rojo br. Se logra usando los ejes del LÍDER
                            (inversos de los del colaborador):
                              X = comportamiento directivo requerido = desempeño INVERTIDO
                              Y = comportamiento de apoyo requerido  = receptividad INVERTIDA
                            Así cada VM cae matemáticamente en su cuadrante correcto. */}
                        <ReferenceArea x1={corteD} x2={ejeMax.x} y1={0} y2={corteR}
                          fill={NIVEL_PAL.D3.fill} fillOpacity={0.88}
                          label={cornerLabel('tl', 'D3 - Apoyar', 'Alto desempeno - Baja rec.', '#3e2723', abrirCuadrante('D3'))} />
                        <ReferenceArea x1={0} x2={corteD} y1={0} y2={corteR}
                          fill={NIVEL_PAL.D2.fill} fillOpacity={0.88}
                          label={cornerLabel('tr', 'D2 - Entrenar', 'Bajo desempeno - Baja rec.', '#3e2723', abrirCuadrante('D2'))} />
                        <ReferenceArea x1={corteD} x2={ejeMax.x} y1={corteR} y2={ejeMax.y}
                          fill={NIVEL_PAL.D4.fill} fillOpacity={0.88}
                          label={cornerLabel('bl', 'D4 - Delegar/Empoderar ⭐', 'Alto desempeno - Alta rec.', '#1b3a1e', abrirCuadrante('D4'))} />
                        <ReferenceArea x1={0} x2={corteD} y1={corteR} y2={ejeMax.y}
                          fill={NIVEL_PAL.D1.fill} fillOpacity={0.88}
                          label={cornerLabel('br', 'D1 - Dirigir', 'Bajo desempeno - Alta rec.', '#3e2723', abrirCuadrante('D1'))} />
                        <ReferenceLine x={corteD} stroke="#ffffff" strokeWidth={2}
                          label={{ value: `${corteD}`, position: 'top', fontSize: 10, fill: '#78909c' }} />
                        <ReferenceLine y={corteR} stroke="#ffffff" strokeWidth={2}
                          label={{ value: `${corteR}`, position: 'right', fontSize: 10, fill: '#78909c' }} />
                        <XAxis type="number" dataKey="des_plot" name="Desempeno" domain={[0, ejeMax.x]} reversed
                          tick={false} axisLine={{ stroke: '#90a4ae' }}
                          label={{ value: 'Comportamiento directivo  (Bajo → Alto)', position: 'insideBottom', offset: -16,
                                   style: { textAnchor: 'middle', fontSize: 12, fill: '#546e7a', fontWeight: 600 } }} />
                        <YAxis type="number" dataKey="rec_plot" name="Receptividad" domain={[0, ejeMax.y]} reversed
                          tick={false} axisLine={{ stroke: '#90a4ae' }}
                          label={{ value: 'Comportamiento de apoyo  (Bajo → Alto)', angle: -90, position: 'insideLeft', offset: 12,
                                   style: { textAnchor: 'middle', fontSize: 12, fill: '#546e7a', fontWeight: 600 } }} />
                        <RTooltip content={<MatrizTooltip />} cursor={{ strokeDasharray: '3 3' }} />
                        <Scatter data={matrizV} shape={CustomDot} />
                      </ScatterChart>
                      </ResponsiveContainer>
                    </Box>
                  </Box>
                </Card>

                {/* Detalle por cuadrante (clic en el ⓘ): lista de colaboradores del
                    nivel con el mismo dato del tooltip — patrón del Dashboard de
                    Cobertura ("por visitador"). */}
                <Popover
                  open={!!cuadrantePop}
                  onClose={() => setCuadrantePop(null)}
                  anchorReference="anchorPosition"
                  anchorPosition={cuadrantePop ? { top: cuadrantePop.y, left: cuadrantePop.x } : undefined}
                >
                  {cuadrantePop && (() => {
                    const pal = nivPal(cuadrantePop.nivel);
                    const desc = CUAD[cuadrantePop.nivel];
                    const items = matrizV
                      .filter(m => m.nivel_lsii === cuadrantePop.nivel)
                      .sort((a, b) => Number(b.score_desempeno) - Number(a.score_desempeno));
                    return (
                      <Box sx={{ p: 1.8, minWidth: 300, maxWidth: 360 }}>
                        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.4 }}>
                          <Box sx={{ width: 30, height: 30, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.7rem' }}>{cuadrantePop.nivel}</Typography>
                          </Box>
                          <Box>
                            <Typography fontWeight={800} fontSize="0.85rem" sx={{ color: pal.color }}>{pal.label}</Typography>
                            <Typography fontSize="0.68rem" color="text.secondary">
                              {items.length} colaborador{items.length === 1 ? '' : 'es'} · {desc.rec}
                            </Typography>
                          </Box>
                        </Box>
                        <Typography fontSize="0.68rem" color="text.secondary" mb={1}>{desc.accion}</Typography>
                        <Divider sx={{ mb: 1 }} />
                        {items.length === 0 ? (
                          <Typography fontSize="0.75rem" color="text.secondary" sx={{ py: 1, textAlign: 'center' }}>
                            Sin colaboradores en este cuadrante.
                          </Typography>
                        ) : items.map(m => (
                          <Box key={m.rm_id} sx={{ display: 'flex', alignItems: 'center', gap: 1, py: 0.6,
                            borderBottom: '1px solid #f0f3f8', '&:last-child': { borderBottom: 'none' } }}>
                            <Box sx={{ width: 26, height: 26, borderRadius: '50%', background: pal.grad, display: 'flex', alignItems: 'center', justifyContent: 'center', flexShrink: 0 }}>
                              <Typography sx={{ color: '#fff', fontWeight: 900, fontSize: '0.6rem' }}>{initials(m.rm_nombre)}</Typography>
                            </Box>
                            <Typography fontSize="0.78rem" fontWeight={700} sx={{ flex: 1, minWidth: 0, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                              {m.rm_nombre}
                            </Typography>
                            <Typography fontSize="0.72rem" sx={{ color: '#00695c', fontWeight: 800 }}>
                              D {Number(m.score_desempeno).toFixed(1)}
                            </Typography>
                            <Typography fontSize="0.72rem" sx={{ color: '#584F46', fontWeight: 800 }}>
                              R {Number(m.score_receptividad).toFixed(1)}
                            </Typography>
                          </Box>
                        ))}
                      </Box>
                    );
                  })()}
                </Popover>
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
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.4 }}>
                                <Typography sx={{ color: pal.color, fontWeight: 800, fontSize: '0.75rem' }}>{pal.label}</Typography>
                                {n === 'D4' && <Star sx={{ color: '#f9a825', fontSize: 15 }} />}
                              </Box>
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
                      Cortes vigentes: desempeño ≥ <b>{corteD}</b> · receptividad ≥ <b>{corteR}</b>. La receptividad se calcula a partir de comportamientos observados — los puntajes son internos y no se muestran al evaluador.
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
                    <Box sx={{ background: 'linear-gradient(135deg,#686158,#4A433C)', px: 2.5, py: 1.2, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
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
                          <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#EFEBE6" />
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
                  <Box sx={{ background: 'linear-gradient(135deg,#686158,#584F46)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8, flexShrink: 0 }}>
                    <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>DETALLE POR COLABORADOR</Typography>
                  </Box>
                  <TableContainer sx={{ flex: 1 }}>
                    <Table size="small" stickyHeader>
                      <TableHead>
                        <TableRow sx={{ '& th': { bgcolor: '#F6F4F2', borderBottom: '2px solid #e0e7ef', color: 'text.secondary', fontWeight: 700, fontSize: '0.68rem', textTransform: 'uppercase', py: 1 } }}>
                          <TableCell>Colaborador</TableCell>
                          <TableCell>Desempeno</TableCell>
                          <TableCell>Receptividad</TableCell>
                          <TableCell align="center">Nivel</TableCell>
                          <TableCell>Accion recomendada</TableCell>
                          <TableCell align="center">Fecha</TableCell>
                        </TableRow>
                      </TableHead>
                      <TableBody>
                        {[...matrizV].sort((a, b) => a.rm_nombre.localeCompare(b.rm_nombre)).map(r => {
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
                                  <Typography fontWeight={700} fontSize="0.76rem" sx={{ minWidth: 32, color: '#584F46' }}>{Number(r.score_receptividad).toFixed(1)}</Typography>
                                  <LinearProgress variant="determinate" value={Math.min(100, Number(r.score_receptividad))}
                                    sx={{ flex: 1, height: 5, borderRadius: 3, bgcolor: '#F4F1EE', '& .MuiLinearProgress-bar': { bgcolor: '#584F46', borderRadius: 3 } }} />
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
              <Box sx={{ background: 'linear-gradient(135deg,#686158,#584F46)', px: 2.5, py: 1.5, borderTopLeftRadius: 8, borderTopRightRadius: 8 }}>
                <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: '0.92rem', letterSpacing: 0.5 }}>EVALUACION DE RECEPTIVIDAD / COMPROMISO</Typography>
                <Typography sx={{ color: 'rgba(255,255,255,0.82)', fontSize: '0.78rem', mt: 0.3 }}>Seleccione el comportamiento que mejor describe al colaborador en cada dimension</Typography>
              </Box>
              <CardContent>
                {esSoloLectura && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Estás consultando un ciclo cerrado/no abierto — solo lectura. Cambia al ciclo abierto para evaluar.
                  </Alert>
                )}

                {/* Ciclo y Representante Médico se eligen en la fila de filtros
                    de arriba (Ciclo → Gerente de Distrito → Representante Médico). */}
                {!evalRmId && (
                  <Alert severity="info" sx={{ mb: 2 }}>
                    Selecciona el <b>Representante Médico</b> en los filtros de arriba para iniciar la evaluación.
                  </Alert>
                )}
                {evalPrevia && reemplazoAceptado && !resultado && (
                  <Alert severity="warning" sx={{ mb: 2 }}>
                    Esta evaluación <b>reemplazará</b> la registrada el{' '}
                    {new Date(evalPrevia.fecha_evaluacion).toLocaleDateString()} (resultado {evalPrevia.nivel_lsii}).
                  </Alert>
                )}

                {dimensiones.length > 0 && (
                  <Box mb={2.5} sx={{ p: 1.5, bgcolor: '#F9F8F6', borderRadius: 2, border: '1px solid #e0e7ef' }}>
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', mb: 0.5 }}>
                      <Typography variant="caption" fontWeight={700} color="text.secondary">Progreso de evaluacion</Typography>
                      <Typography variant="caption" fontWeight={800} color={completadas === dimensiones.length ? '#00695c' : '#584F46'}>{completadas} / {dimensiones.length}</Typography>
                    </Box>
                    <LinearProgress variant="determinate" value={(completadas / dimensiones.length) * 100}
                      sx={{ height: 8, borderRadius: 4, bgcolor: '#F4F1EE', '& .MuiLinearProgress-bar': { bgcolor: completadas === dimensiones.length ? '#00695c' : '#584F46', borderRadius: 4 } }} />
                  </Box>
                )}

                {loadCatalogo ? (
                  <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress size={28} /></Box>
                ) : (
                  dimensiones.map((dim, idx) => {
                    const sel = selecciones[dim.dimension_codigo] != null;
                    const selectedOpId = selecciones[dim.dimension_codigo];
                    return (
                      <Box key={dim.dimension_codigo} sx={{ mb: 2, borderRadius: 2, border: `1.5px solid ${sel ? '#584F4640' : '#e0e7ef'}`, overflow: 'hidden', transition: 'border-color 0.2s' }}>
                        {/* Cabecera de dimensión */}
                        <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1.5, px: 2, py: 1.2, bgcolor: sel ? '#F4F1EE' : '#F9F8F6', borderBottom: '1px solid #EFEBE6' }}>
                          <Box sx={{ width: 24, height: 24, borderRadius: '50%', flexShrink: 0, mt: 0.1, bgcolor: sel ? '#584F46' : '#e0e7ef', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                            <Typography sx={{ color: sel ? '#fff' : '#546e7a', fontWeight: 900, fontSize: '0.65rem' }}>{idx + 1}</Typography>
                          </Box>
                          <Box sx={{ flex: 1, minWidth: 0 }}>
                            <Typography fontWeight={700} fontSize="0.85rem" color="#37474f">{dim.dimension_nombre}</Typography>
                            {dim.dimension_descripcion && (
                              <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.35, mt: 0.2 }}>{dim.dimension_descripcion}</Typography>
                            )}
                          </Box>
                          {sel && <CheckCircle sx={{ color: '#584F46', fontSize: 18, flexShrink: 0, mt: 0.1 }} />}
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
                                borderLeft: `3px solid ${isSelected ? '#584F46' : 'transparent'}`,
                                borderBottom: oi < dim.opciones.length - 1 ? '1px solid #f0f2f5' : 'none',
                                transition: 'background 0.15s, border-color 0.15s',
                                '&:hover': { bgcolor: isSelected ? '#cce4f7' : '#F6F4F2' },
                              }}>
                              {/* Dot radio personalizado */}
                              <Box sx={{
                                width: 16, height: 16, borderRadius: '50%', flexShrink: 0,
                                border: `2px solid ${isSelected ? '#584F46' : '#b0bec5'}`,
                                bgcolor: isSelected ? '#584F46' : 'transparent',
                                display: 'flex', alignItems: 'center', justifyContent: 'center',
                                transition: 'all 0.15s',
                              }}>
                                {isSelected && <Box sx={{ width: 6, height: 6, borderRadius: '50%', bgcolor: '#fff' }} />}
                              </Box>
                              <Typography fontSize="0.82rem" sx={{ lineHeight: 1.4, color: isSelected ? '#584F46' : '#546e7a', fontWeight: isSelected ? 600 : 400 }}>
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

                <Button variant="contained" disabled={!formListo || mutEvaluar.isPending || esSoloLectura} size="large" fullWidth
                  onClick={() => mutEvaluar.mutate()}
                  sx={{ borderRadius: 2, fontWeight: 700, py: 1.2, background: formListo ? 'linear-gradient(135deg,#686158,#584F46)' : undefined }}>
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
                  // String() en ambos lados: el MenuItem entrega el id numérico y
                  // el estado lo guarda tal cual — sin normalizar, el nombre no aparecía.
                  const rmNombre = rmsArr.find(r => String(r.id) === String(evalRmId))?.nombre || '';
                  return (
                    <Box>
                      <Alert severity="success" sx={{ mb: 2 }}>
                        La evaluación se ha guardado exitosamente.
                      </Alert>
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
                          <Box sx={{ p: 1, bgcolor: '#F4F1EE', borderRadius: 1.5, textAlign: 'center' }}>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.6rem', display: 'block' }}>Receptividad</Typography>
                            <Typography fontWeight={800} color="#584F46" fontSize="1rem">{Number(resultado.score_receptividad).toFixed(1)}</Typography>
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
