import { useEffect, useState, type MouseEvent } from 'react';
import {
  Box, Typography, Card, CardContent, Grid, Chip, Stack, Slider, LinearProgress,
  IconButton, Popover, CircularProgress, Divider, Table, TableHead, TableRow, TableCell, TableBody,
} from '@mui/material';
import { InfoOutlined, TrendingUp, Flag } from '@mui/icons-material';
import { proyeccionVisita, proyeccionRanking, type Proyeccion, type RankingVM } from '../../services/visita.service';

function DetalleProyeccion({ diaActual }: { diaActual: number }) {
  const [anchor, setAnchor] = useState<HTMLElement | null>(null);
  const [data, setData] = useState<RankingVM | null>(null);
  const abrir = (e: MouseEvent<HTMLElement>) => { setAnchor(e.currentTarget); setData(null); proyeccionRanking(diaActual).then(setData).catch(() => setData(null)); };
  const open = Boolean(anchor);
  return (
    <>
      <IconButton size="small" onClick={abrir} color={open ? 'primary' : 'default'} sx={{ p: 0.25 }}><InfoOutlined sx={{ fontSize: 16 }} /></IconButton>
      <Popover open={open} anchorEl={anchor} onClose={() => setAnchor(null)} anchorOrigin={{ vertical: 'bottom', horizontal: 'left' }}>
        <Box sx={{ p: 2, width: 340 }}>
          <Typography variant="subtitle2" fontWeight={700}>Proyección al cierre — por visitador</Typography>
          {!data ? <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box> : (
            <>
              <Typography variant="caption" color="text.secondary">Objetivo ≥ {data.objetivo}% · <b>{data.no_cumplen} de {data.total}</b> no alcanzarán</Typography>
              <Divider sx={{ my: 1 }} />
              <Stack spacing={0.5} sx={{ maxHeight: 300, overflow: 'auto' }}>
                {data.items.map((it) => (
                  <Stack key={it.vm_id} direction="row" justifyContent="space-between" sx={{ bgcolor: it.cumple ? 'transparent' : 'rgba(244,67,54,0.06)', borderRadius: 1, px: 0.5 }}>
                    <Typography variant="body2" sx={{ flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>{it.cumple ? '✅' : '🔴'} {it.nombre}{it.zona ? ` · ${it.zona}` : ''}</Typography>
                    <Typography variant="body2" fontWeight={700} sx={{ color: it.cumple ? 'success.main' : 'error.main' }}>{it.valor}%</Typography>
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

export default function ProyeccionVisita() {
  const [p, setP] = useState<Proyeccion | null>(null);
  const [dia, setDia] = useState<number | null>(null);

  useEffect(() => { proyeccionVisita().then((d) => { setP(d); setDia(d.dia_actual); }).catch(() => setP(null)); }, []);
  const recargar = (d: number) => proyeccionVisita(d).then(setP).catch(() => {});

  if (!p || dia === null) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;
  const progreso = Math.round((p.dia_actual / p.ciclo_dias) * 100);

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Proyección y Plan de Acción — Visita <DetalleProyeccion diaActual={p.dia_actual} /></Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>Panel {p.panel} · objetivo {p.obj_medicos} médicos ({p.objetivo_pct}%)</Typography>

      {/* Simulador de día */}
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack direction="row" justifyContent="space-between" alignItems="center">
            <Typography variant="subtitle2" fontWeight={700}>Día {p.dia_actual} de {p.ciclo_dias}</Typography>
            <Chip size="small" label={`${p.dias_restantes} días restantes`} />
          </Stack>
          <LinearProgress variant="determinate" value={progreso} sx={{ my: 1, height: 8, borderRadius: 4 }} />
          <Typography variant="caption" color="text.secondary">Simula otro día del ciclo:</Typography>
          <Slider value={dia} min={1} max={p.ciclo_dias} step={1} valueLabelDisplay="auto"
                  onChange={(_, v) => setDia(v as number)} onChangeCommitted={(_, v) => recargar(v as number)} />
        </CardContent>
      </Card>

      {/* Escenarios */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%', borderColor: p.cumple_proyeccion ? 'success.main' : 'error.main' }}>
            <CardContent>
              <Typography fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><TrendingUp fontSize="small" /> Si sigues al ritmo actual</Typography>
              <Typography variant="h3" fontWeight={800} sx={{ my: 1, color: p.cumple_proyeccion ? 'success.main' : 'error.main' }}>{p.proyeccion_final}</Typography>
              <Typography variant="body2" color="text.secondary">médicos proyectados al cierre (ritmo {p.ritmo_actual}/día)</Typography>
              <Chip size="small" sx={{ mt: 1 }} color={p.gap_al_objetivo > 0 ? 'error' : 'success'}
                    label={p.gap_al_objetivo > 0 ? `Gap: ${p.gap_al_objetivo} médicos bajo el objetivo` : `Supera el objetivo por ${-p.gap_al_objetivo}`} />
            </CardContent>
          </Card>
        </Grid>
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%', bgcolor: 'rgba(26,35,126,0.04)' }}>
            <CardContent>
              <Typography fontWeight={700} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><Flag fontSize="small" /> Para cumplir el objetivo</Typography>
              <Typography variant="h3" fontWeight={800} sx={{ my: 1, color: 'primary.main' }}>
                {p.ritmo_requerido === null ? '—' : p.ritmo_requerido}<Typography component="span" variant="h6">/día</Typography>
              </Typography>
              <Typography variant="body2" color="text.secondary">nuevo ritmo diario requerido (te faltan {Math.max(0, p.obj_medicos - p.visitados)} médicos en {p.dias_restantes} días)</Typography>
              <Stack direction="row" spacing={1} sx={{ mt: 1 }} alignItems="center">
                <Chip size="small" variant="outlined" label={`Actual: ${p.ritmo_actual}/día`} />
                <Typography variant="body2">→</Typography>
                <Chip size="small" color={(p.ritmo_requerido ?? 0) > p.ritmo_actual ? 'warning' : 'success'} label={`Requerido: ${p.ritmo_requerido ?? '—'}/día`} />
              </Stack>
            </CardContent>
          </Card>
        </Grid>
      </Grid>

      {/* Proyección por categoría */}
      <Card variant="outlined">
        <CardContent>
          <Typography fontWeight={700} gutterBottom>Proyección por categoría</Typography>
          <Table size="small">
            <TableHead><TableRow>
              <TableCell>Categoría</TableCell><TableCell align="center">Panel</TableCell>
              <TableCell align="center">Visitados hoy</TableCell><TableCell align="center">Proyección cierre</TableCell>
            </TableRow></TableHead>
            <TableBody>
              {(['A', 'B', 'C'] as const).map((c) => {
                const cat = p.categorias[c] || { panel: 0, visitados: 0, proyeccion: 0 };
                return (
                  <TableRow key={c} hover>
                    <TableCell sx={{ fontWeight: 700 }}>Categoría {c}</TableCell>
                    <TableCell align="center">{cat.panel}</TableCell>
                    <TableCell align="center">{cat.visitados}</TableCell>
                    <TableCell align="center" sx={{ fontWeight: 700 }}>{cat.proyeccion}</TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </Box>
  );
}
