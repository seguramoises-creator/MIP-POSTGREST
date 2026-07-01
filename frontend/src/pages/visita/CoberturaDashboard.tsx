import { useEffect, useState, type MouseEvent } from 'react';
import {
  Box, Typography, Card, CardContent, Grid, Chip, Alert, Stack, LinearProgress,
  IconButton, Popover, CircularProgress, Divider,
} from '@mui/material';
import { InfoOutlined } from '@mui/icons-material';
import { coberturaResumen, coberturaRanking, type CoberturaResumen, type RankingVM } from '../../services/visita.service';

const CAT_COLOR: Record<string, string> = { A: '#1b5e20', B: '#0d47a1', C: '#e65100' };

// ── Botón "i" + panel de ranking por visitador (detalle desplegable) ──
function DetalleVisitador({ metrica, titulo }: { metrica: string; titulo: string }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [data, setData] = useState<RankingVM | null>(null);
  const abrir = (e: MouseEvent<HTMLElement>) => {
    setAnchor(e.currentTarget); setData(null);
    coberturaRanking(metrica).then(setData).catch(() => setData(null));
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

function Gauge({ pct, color, label, metrica, titulo, sub }: { pct: number; color: string; label: string; metrica: string; titulo: string; sub: string }) {
  const r = 54, circ = 2 * Math.PI * r, off = circ - (Math.min(pct, 100) / 100) * circ;
  return (
    <Card variant="outlined">
      <CardContent sx={{ textAlign: 'center' }}>
        <Box sx={{ position: 'relative', width: 130, height: 130, mx: 'auto' }}>
          <svg viewBox="0 0 130 130" width={130} height={130} style={{ transform: 'rotate(-90deg)' }}>
            <circle cx={65} cy={65} r={r} fill="none" stroke="#eceff1" strokeWidth={11} />
            <circle cx={65} cy={65} r={r} fill="none" stroke={color} strokeWidth={11} strokeLinecap="round"
                    strokeDasharray={circ} strokeDashoffset={off} />
          </svg>
          <Box sx={{ position: 'absolute', inset: 0, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="h5" fontWeight={800} sx={{ color }}>{pct}%</Typography>
            <Typography variant="caption" color="text.secondary">{label}</Typography>
          </Box>
        </Box>
        <Typography variant="body2" fontWeight={700} sx={{ mt: 1 }}>
          {titulo} <DetalleVisitador metrica={metrica} titulo={titulo} />
        </Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </CardContent>
    </Card>
  );
}

export default function CoberturaDashboard() {
  const [data, setData] = useState<CoberturaResumen | null>(null);
  useEffect(() => { coberturaResumen().then(setData).catch(() => setData(null)); }, []);

  if (!data) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Dashboard de Cobertura — Visita</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Panel de {data.panel} médicos · {data.visitados} visitados · {data.sin_visitar} sin visitar
      </Typography>

      {/* Gauges */}
      <Grid container spacing={2} sx={{ mb: 1 }}>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_cobertura} color="#00897b" label="Cobertura" metrica="cobertura" titulo="Cobertura Total" sub="Médicos con al menos 1 visita" /></Grid>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_completa} color="#1a237e" label="V+R" metrica="completa" titulo="Vista + Revisita" sub="Médicos con ciclo completo (V+R)" /></Grid>
        <Grid item xs={12} md={4}><Gauge pct={data.pct_gap} color="#c62828" label="Gap" metrica="sin_visitar" titulo="Gap de Cobertura" sub="Sin ninguna visita en el ciclo" /></Grid>
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
                  <Typography fontWeight={700} sx={{ color: CAT_COLOR[c], mb: 1 }}>Categoría {c}</Typography>
                  <Box sx={{ mb: 1 }}>
                    <Stack direction="row" justifyContent="space-between"><Typography variant="caption">Cobertura Total</Typography><Typography variant="caption" fontWeight={700}>{pctT}%</Typography></Stack>
                    <LinearProgress variant="determinate" value={pctT} sx={{ height: 7, borderRadius: 4, '& .MuiLinearProgress-bar': { bgcolor: '#00897b' } }} />
                  </Box>
                  <Box>
                    <Stack direction="row" justifyContent="space-between"><Typography variant="caption">Vista + Revisita</Typography><Typography variant="caption" fontWeight={700}>{pctC}%</Typography></Stack>
                    <LinearProgress variant="determinate" value={pctC} sx={{ height: 7, borderRadius: 4, '& .MuiLinearProgress-bar': { bgcolor: '#1a237e' } }} />
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

      {/* Listas: sin visita / falta revisita */}
      <Grid container spacing={2}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                🔴 Sin ninguna visita <DetalleVisitador metrica="sin_visitar" titulo="Médicos sin visita" />
                <Chip size="small" color="error" label={`${data.sin_visita.length} médicos`} sx={{ ml: 'auto' }} />
              </Typography>
              <Stack sx={{ mt: 1, maxHeight: 220, overflow: 'auto' }}>
                {data.sin_visita.slice(0, 30).map((m) => (
                  <Typography key={m.id} variant="body2" color="text.secondary">• {m.nombre} <Chip size="small" variant="outlined" label={m.categoria} sx={{ ml: 0.5, height: 16 }} /></Typography>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined">
            <CardContent>
              <Typography fontWeight={700} sx={{ display: 'flex', alignItems: 'center' }}>
                🟡 Falta Revisita
                <Chip size="small" color="warning" label={`${data.falta_revisita.length} médicos`} sx={{ ml: 'auto' }} />
              </Typography>
              <Stack sx={{ mt: 1, maxHeight: 220, overflow: 'auto' }}>
                {data.falta_revisita.slice(0, 30).map((m) => (
                  <Typography key={m.id} variant="body2" color="text.secondary">• {m.nombre} <Chip size="small" variant="outlined" label={m.categoria} sx={{ ml: 0.5, height: 16 }} /></Typography>
                ))}
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>
    </Box>
  );
}
