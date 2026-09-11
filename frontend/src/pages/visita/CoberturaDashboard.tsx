import { useEffect, useMemo, useState, useCallback, type MouseEvent, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Grid, Chip, Alert, Stack, LinearProgress,
  IconButton, Popover, CircularProgress, Divider, TextField, MenuItem, Button,
} from '@mui/material';
import { InfoOutlined, FilterList } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import SaludCiclo from '../../components/SaludCiclo';
import {
  coberturaResumen, coberturaRanking, listarVMs, listarGerentesVisita, listarLineasVisita,
  type CoberturaResumen, type RankingVM, type Catalogo,
} from '../../services/visita.service';
import { AVISO, BORDE_SUAVE, ERROR, EXITO_MEDIO } from '../../theme/marca';
import { marcaViva } from '../../theme/marcaViva';
// Función y no constante: en ámbito de módulo se evaluaría antes de que
// `cargarMarca()` traiga la identidad, y el color quedaría en el de fábrica.
const catColor = (): Record<string, string> =>
  ({ A: '#1b5e20', B: marcaViva.taupeMedio, C: AVISO });

// M1: con un panel entero marcado TOP, concatenar todos los nombres vuelve la
// alerta una cadena de miles de caracteres. Se capa igual que las listas
// vecinas de esta pantalla (`.slice(0, 30)`).
function formatearNombres(nombres: string[], tope = 30): string {
  if (nombres.length <= tope) return nombres.join(', ');
  return `${nombres.slice(0, tope).join(', ')} y ${nombres.length - tope} más`;
}

// ── Lista de pendientes POR SEMANA del ciclo ──
interface MedicoSemana {
  id: number; nombre: string; categoria: string | null; es_top: boolean;
  semana?: number | null; dia?: string | null;
}
/** Alto fijo de la lista: las dos tarjetas (sin visita / falta revisita) miden lo mismo. */
const ALTO_LISTA = 300;
const TOPE_FILAS = 300;
const SEMANAS = ['1', '2', '3', '4'];

/**
 * Pendientes agrupados por la semana del ciclo en que estaban planeados. Una lista plana
 * de 2.730 nombres no dice qué urge: lo de la semana 1 ya está vencido y lo de la 4 aún
 * no toca. Arriba, un botón por semana con cuántos quedan sin visitar hasta hoy.
 */
function ListaPorSemana({ titulo, color, items, semanaActual, textoSinSemana, extra }: {
  titulo: string; color: 'error' | 'warning'; items: MedicoSemana[]; semanaActual: number | null | undefined;
  textoSinSemana: string; extra?: ReactNode;
}) {
  const grupos = useMemo(() => {
    const g: Record<string, MedicoSemana[]> = { 1: [], 2: [], 3: [], 4: [], sin: [] };
    items.forEach((m) => g[m.semana && m.semana >= 1 && m.semana <= 4 ? String(m.semana) : 'sin'].push(m));
    return g;
  }, [items]);
  const porDefecto = semanaActual && grupos[String(semanaActual)].length
    ? String(semanaActual)
    : ([...SEMANAS, 'sin'].find((k) => grupos[k].length) ?? '1');
  const [elegida, setElegida] = useState<string | null>(null);
  const actual = elegida && grupos[elegida] ? elegida : porDefecto;
  const lista = grupos[actual];
  const n = Number(actual);
  const explicacion = actual === 'sin'
    ? `${textoSinSemana}: no están en la planeación del ciclo.`
    : semanaActual && n < semanaActual ? `Planeados para la semana ${n}, ya pasada, y todavía sin visitar.`
    : n === semanaActual ? 'Planeados para esta semana, todavía sin visitar.'
    : `Planeados para la semana ${n}; aún no llega.`;

  return (
    <Card variant="outlined" sx={{ height: '100%', width: '100%' }}>
      <CardContent>
        <Typography fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
          {titulo} {extra}
          <Chip size="small" color={color} label={`${items.length} médicos`} sx={{ ml: 'auto' }} />
        </Typography>
        <Stack direction="row" spacing={0.5} useFlexGap flexWrap="wrap" sx={{ mt: 1 }}>
          {SEMANAS.map((k) => {
            const s = Number(k);
            const vencida = !!semanaActual && s < semanaActual;
            const enCurso = s === semanaActual;
            return (
              <Chip key={k} size="small" clickable onClick={() => setElegida(k)}
                    color={actual === k ? (vencida ? 'error' : 'primary') : vencida ? 'error' : 'default'}
                    variant={actual === k ? 'filled' : 'outlined'}
                    label={`Sem ${k}${enCurso ? ' · en curso' : vencida ? ' · vencida' : ''} · ${grupos[k].length}`} />
            );
          })}
          <Chip size="small" clickable onClick={() => setElegida('sin')}
                variant={actual === 'sin' ? 'filled' : 'outlined'}
                label={`${textoSinSemana} · ${grupos.sin.length}`} />
        </Stack>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.75 }}>
          {explicacion}
        </Typography>
        <Box sx={{ mt: 0.5, height: ALTO_LISTA, overflow: 'auto', borderTop: `1px solid ${BORDE_SUAVE}`, pt: 0.5 }}>
          {lista.length === 0 ? (
            <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>Nadie pendiente aquí.</Typography>
          ) : lista.slice(0, TOPE_FILAS).map((m) => (
            <Typography key={m.id} variant="body2" color="text.secondary">
              • {m.nombre} <Chip size="small" variant="outlined" label={m.categoria ?? '?'} sx={{ ml: 0.5, height: 16 }} />
              {m.dia && <Typography component="span" variant="caption" sx={{ ml: 0.5 }}>{m.dia}</Typography>}
              {m.es_top && <Chip size="small" color="error" label="TOP" sx={{ ml: 0.5, height: 16, fontWeight: 700 }} />}
            </Typography>
          ))}
          {lista.length > TOPE_FILAS && (
            <Typography variant="caption" color="text.secondary">
              … y {lista.length - TOPE_FILAS} más.
            </Typography>
          )}
        </Box>
      </CardContent>
    </Card>
  );
}

// ── Botón "i" + panel de ranking por visitador (detalle desplegable) ──
function DetalleVisitador({ metrica, titulo, paisCodigo }: { metrica: string; titulo: string; paisCodigo?: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [data, setData] = useState<RankingVM | null>(null);
  const abrir = (e: MouseEvent<HTMLElement>) => {
    setAnchor(e.currentTarget); setData(null);
    coberturaRanking(metrica, paisCodigo).then(setData).catch(() => setData(null));
  };
  const open = Boolean(anchor);
  const unidad = metrica === 'sin_visitar' ? '' : '%';
  return (
    <>
      <IconButton size="small" onClick={abrir} color={open ? 'primary' : 'default'} sx={{ p: 0.25 }}>
        <InfoOutlined sx={{ fontSize: 16 }} />
      </IconButton>
      <Popover open={open} anchorEl={anchor} onClose={() => setAnchor(null)}
               anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box sx={{ p: 2, width: 340 }}>
          <Typography variant="subtitle2" fontWeight={700}>{titulo} — por visitador</Typography>
          {!data ? <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box> : (
            <>
              <Typography variant="caption" color="text.secondary">
                Objetivo {metrica === 'sin_visitar' ? '≤' : '≥'} {data.objetivo}{unidad} · <b>{data.no_cumplen} de {data.total}</b> no cumplen
              </Typography>
              <Divider sx={{ my: 1 }} />
              <Stack spacing={0.5} sx={{ maxHeight: 300, overflow: 'auto' }}>
                {data.items.map((it) => (
                  <Stack key={it.vm_id} direction="row" justifyContent="space-between" alignItems="center"
                         sx={{ bgcolor: it.cumple ? 'transparent' : 'rgba(244,67,54,0.06)', borderRadius: 1, px: 0.5 }}>
                    <Typography variant="body2" sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                      {it.cumple ? '✅' : '🔴'} {it.nombre}{it.zona ? ` · ${it.zona}` : ''}
                    </Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: it.cumple ? 'success.main' : 'error.main' }}>
                      {it.valor}{unidad}
                    </Typography>
                  </Stack>
                ))}
              </Stack>
            </>
          )}
        </Box>
      </Popover>
    </>
  );
}

function Gauge({ pct, color, label, metrica, titulo, sub, paisCodigo }: { pct: number; color: string; label: string; metrica: string; titulo: string; sub: string; paisCodigo?: string }) {
  const r = 54, circ = 2 * Math.PI * r, off = circ - (Math.min(pct, 100) / 100) * circ;
  return (
    <Card variant="outlined">
      <CardContent sx={{ textAlign: 'center' }}>
        <Box sx={{ position: 'relative', width: 130, height: 130, mx: 'auto' }}>
          <svg viewBox="0 0 130 130" width={130} height={130} style={{ transform: 'rotate(-90deg)' }}>
            <circle cx={65} cy={65} r={r} fill="none" stroke={BORDE_SUAVE} strokeWidth={11} />
            <circle cx={65} cy={65} r={r} fill="none" stroke={color} strokeWidth={11} strokeLinecap="round"
                    strokeDasharray={circ} strokeDashoffset={off} />
          </svg>
          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="h5" fontWeight={800} sx={{ color }}>{pct}%</Typography>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
          </Box>
        </Box>
        <Typography variant="body2" fontWeight={700} sx={{ mt: 1 }}>
          {titulo} <DetalleVisitador metrica={metrica} titulo={titulo} paisCodigo={paisCodigo} />
        </Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </CardContent>
    </Card>
  );
}

export default function CoberturaDashboard() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const paisCodigo = useCicloStore((s) => s.paisCodigo);

  const [data, setData] = useState<CoberturaResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  // Filtros (solo ADMIN/GERENTE; el VM ve su propia cobertura).
  const [vms, setVms] = useState<Catalogo[]>([]);
  const [gerentes, setGerentes] = useState<Catalogo[]>([]);
  const [lineas, setLineas] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');
  const [gerenteId, setGerenteId] = useState<number | ''>('');
  const [lineaId, setLineaId] = useState<number | ''>('');
  const [soloRuptura, setSoloRuptura] = useState(false);

  useEffect(() => {
    if (esVM) return;
    listarVMs(paisCodigo).then(setVms).catch(() => {});
    listarGerentesVisita(paisCodigo).then(setGerentes).catch(() => {});
    listarLineasVisita(paisCodigo).then(setLineas).catch(() => {});
  }, [esVM, paisCodigo]);

  const cargar = useCallback(() => {
    setCargando(true);
    coberturaResumen({
      vmId: vmId || undefined, gerenteId: gerenteId || undefined,
      lineaId: lineaId || undefined, soloRuptura: soloRuptura || undefined, paisCodigo,
    }).then(setData).catch(() => setData(null)).finally(() => setCargando(false));
  }, [vmId, gerenteId, lineaId, soloRuptura, paisCodigo]);
  useEffect(() => { cargar(); }, [cargar]);

  const hayFiltro = !!(vmId || gerenteId || lineaId || soloRuptura);
  const limpiar = () => { setVmId(''); setGerenteId(''); setLineaId(''); setSoloRuptura(false); };

  if (cargando && !data) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;
  if (!data) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Dashboard de Cobertura — Visita</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Panel de {data.panel} médicos · {data.visitados} visitados · {data.sin_visitar} sin visitar
        {typeof data.acompanadas === 'number' && (
          <> · <strong>{data.acompanadas}</strong> visitas acompañadas por el GD ({data.pct_acompanamiento ?? 0}% de {data.visitas_ejecutadas ?? 0})</>
        )}
      </Typography>

      {/* RM: KPIs de SU programación + cómo va su LÍNEA total (no el agregado de la empresa).
          Gerencia/Admin: salud/completitud global del ciclo. */}
      {esVM ? (
        <Grid container spacing={1.5} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={4}>
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>SIN VISITAR · MI PROGRAMACIÓN</Typography>
              <Typography variant="h4" fontWeight={800} color={ERROR}>{data.sin_visitar}</Typography>
              <Typography variant="caption" color="text.secondary">de {data.panel} médicos de mi panel</Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>MI COBERTURA</Typography>
              <Typography variant="h4" fontWeight={800} color={EXITO_MEDIO}>{data.pct_cobertura}%</Typography>
              <LinearProgress variant="determinate" value={Math.min(100, data.pct_cobertura)}
                sx={{ height: 6, borderRadius: 3, mt: 0.75 }} />
            </CardContent></Card>
          </Grid>
          {data.linea_total && (
            <Grid item xs={12} sm={4}>
              <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  MI LÍNEA · {data.linea_total.linea_nombre.toUpperCase()}
                </Typography>
                <Typography variant="h4" fontWeight={800} color={marcaViva.taupe}>{data.linea_total.pct_cobertura}%</Typography>
                <Typography variant="caption" color="text.secondary">
                  {data.linea_total.visitados}/{data.linea_total.panel} médicos · {data.linea_total.sin_visitar} sin visitar
                </Typography>
              </CardContent></Card>
            </Grid>
          )}
        </Grid>
      ) : (
        <SaludCiclo />
      )}

      {/* Filtros (solo ADMIN/GERENTE) */}
      {!esVM && (
        <Card variant="outlined" sx={{ mb: 2, bgcolor: '#fff', borderColor: marcaViva.taupe,
                                   borderWidth: 1.5, borderRadius: 3 }}>
          <Box sx={{ p: 1.5 }}>
            <Stack direction={{ xs: 'column', md: 'row' }} spacing={1.5} alignItems={{ md: 'center' }} flexWrap="wrap" useFlexGap>
              <Stack direction="row" spacing={0.75} alignItems="center"
                     sx={{ color: marcaViva.taupe, width: { xs: '100%', md: 'auto' },
                           pb: { xs: 1, md: 0 }, mb: { xs: 0.5, md: 0 },
                           borderBottom: { xs: '1px solid #EDE9E4', md: 'none' } }}>
                <FilterList fontSize="small" />
                <Typography variant="body2" sx={{ fontWeight: 700, letterSpacing: '0.02em' }}>Filtrar</Typography>
              </Stack>
              <TextField select size="small" label="Representante médico" value={vmId} sx={{ minWidth: 220, bgcolor: '#fff' }}
                         onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value="">Todos</MenuItem>
                {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
              </TextField>
              <TextField select size="small" label="Gerente de Distrito" value={gerenteId} sx={{ minWidth: 200, bgcolor: '#fff' }}
                         onChange={(e) => setGerenteId(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value="">Todos</MenuItem>
                {gerentes.map((g) => <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>)}
              </TextField>
              <TextField select size="small" label="Línea" value={lineaId} sx={{ minWidth: 180, bgcolor: '#fff' }}
                         onChange={(e) => setLineaId(e.target.value === '' ? '' : Number(e.target.value))}>
                <MenuItem value="">Todas</MenuItem>
                {lineas.map((l) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
              </TextField>
              <Chip label="Ruptura de secuencia" color={soloRuptura ? 'error' : 'default'}
                    variant={soloRuptura ? 'filled' : 'outlined'} onClick={() => setSoloRuptura((v) => !v)}
                    sx={{ bgcolor: soloRuptura ? undefined : '#fff' }} />
              {hayFiltro && <Button size="small" onClick={limpiar}>Limpiar</Button>}
            </Stack>
          </Box>
        </Card>
      )}

      {/* Gauges */}
      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_cobertura} color={EXITO_MEDIO} label="Cobertura" metrica="cobertura" titulo="Cobertura Total" sub="Médicos con al menos 1 visita" paisCodigo={paisCodigo} /></Grid>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_completa} color={marcaViva.taupe} label="V+R" metrica="completa" titulo="Vista + Revisita" sub="Médicos con ciclo completo (V+R)" paisCodigo={paisCodigo} /></Grid>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_gap} color={ERROR} label="Gap" metrica="sin_visitar" titulo="Gap de Cobertura" sub="Sin ninguna visita en el ciclo" paisCodigo={paisCodigo} /></Grid>
      </Grid>

      {/* Categorías A/B/C */}
      <Grid container spacing={2} sx={{ mb: 1 }}>
        {(['A', 'B', 'C'] as const).map((c) => {
          const cat = data.categorias[c] || { total: 0, visitados: 0, completos: 0 };
          const pctT = cat.total ? Math.round(cat.visitados / cat.total * 100) : 0;
          const pctC = cat.total ? Math.round(cat.completos / cat.total * 100) : 0;
          return (
            <Grid item xs={12} md={4} key={c}>
              <Card variant="outlined">
                <CardContent>
                  <Typography fontWeight={700} sx={{ color: catColor()[c], mb: 1 }}>Categoría {c}</Typography>
                  <Box sx={{ mb: 1 }}>
                    <Stack direction="row" justifyContent="space-between"><Typography variant="caption">Cobertura Total</Typography><Typography variant="caption" fontWeight={700}>{pctT}%</Typography></Stack>
                    <LinearProgress variant="determinate" value={pctT} sx={{ height: 7, borderRadius: 4, '& .MuiLinearProgress-bar': { bgcolor: EXITO_MEDIO } }} />
                  </Box>
                  <Box>
                    <Stack direction="row" justifyContent="space-between"><Typography variant="caption">Vista + Revisita</Typography><Typography variant="caption" fontWeight={700}>{pctC}%</Typography></Stack>
                    <LinearProgress variant="determinate" value={pctC} sx={{ height: 7, borderRadius: 4, '& .MuiLinearProgress-bar': { bgcolor: marcaViva.taupe } }} />
                  </Box>
                  <Typography variant="caption" color="text.secondary" sx={{ mt: 1, display: 'block' }}>
                    {cat.visitados} de {cat.total} médicos visitados
                  </Typography>
                </CardContent>
              </Card>
            </Grid>
          );
        })}
      </Grid>

      {/* Ruptura de secuencia */}
      {data.ruptura.length > 0 && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <Typography fontWeight={700}>🔴 Ruptura de Secuencia — {data.ruptura.length} médicos sin visitar 3+ ciclos</Typography>
          <Stack sx={{ mt: 0.5 }}>
            {data.ruptura.slice(0, 8).map((m) => (
              <Typography key={m.id} variant="body2">• {m.nombre} (Cat. {m.categoria}) — {m.ciclos_sin_visita} ciclos</Typography>
            ))}
          </Stack>
        </Alert>
      )}

      {/* Médicos TOP (SFA de Mallén) sin cubrir — aviso destacado antes de las listas generales. */}
      {(!!data?.top_sin_visita?.length || !!data?.top_falta_revisita?.length) && (
        <Alert severity="error" sx={{ mb: 2 }}>
          <strong>Médicos TOP sin cubrir:</strong>{' '}
          {data.top_sin_visita.length} sin ninguna visita
          {' · '}{data.top_falta_revisita.length} sin revisita.
          {' '}
          {formatearNombres([...data.top_sin_visita, ...data.top_falta_revisita].map((m) => m.nombre))}
        </Alert>
      )}

      {/* Listas: sin visita / falta revisita */}
      {/* Las dos del mismo tamaño (Grid estirado + lista de alto fijo) y leídas por semana. */}
      <Grid container spacing={2} alignItems="stretch">
        <Grid item xs={12} md={6} sx={{ display: 'flex' }}>
          <ListaPorSemana titulo="🔴 Sin ninguna visita" color="error" items={data.sin_visita}
                          semanaActual={data.semana_actual} textoSinSemana="Sin planear"
                          extra={<DetalleVisitador metrica="sin_visitar" titulo="Médicos sin visita" paisCodigo={paisCodigo} />} />
        </Grid>
        <Grid item xs={12} md={6} sx={{ display: 'flex' }}>
          <ListaPorSemana titulo="🟡 Falta Revisita" color="warning" items={data.falta_revisita}
                          semanaActual={data.semana_actual} textoSinSemana="Sin revisita planeada" />
        </Grid>
      </Grid>
    </Box>
  );
}
