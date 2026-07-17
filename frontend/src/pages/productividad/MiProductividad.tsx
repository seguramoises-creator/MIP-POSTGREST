/**
 * MiProductividad.tsx — Vista del REPRESENTANTE.
 *
 * Regla del cliente (jul-2026): el representante solo ve SUS datos; nunca los de otro
 * visitador. Sí puede ver el ACUMULADO de su línea de negocio, para saber si va bien o mal
 * — pero como agregado (promedio + nº de representantes), nunca fila a fila.
 *
 * La vista de gerencia (Productividad.tsx) no le sirve: consulta /admin/lineas,
 * /admin/indicadores y /ranking, endpoints que su rol no puede tocar. Por eso tiene la suya.
 *
 * Consume GET /productividad/mi-linea (auto-scoped en backend): trae lo suyo, el agregado de
 * su línea y sus indicadores en una sola respuesta.
 */
import {
  Box, Card, CardContent, Grid, Typography, Alert, LinearProgress, Stack, Chip,
  Table, TableHead, TableBody, TableRow, TableCell, Paper,
} from '@mui/material';
import { TrendingUp, TrendingDown, Insights } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';

type MiLinea = {
  rm: { nombre: string; codigo: string | null; linea: string | null;
        cumplimiento_pct: number; puntos: number; sin_datos: boolean };
  linea: { nombre: string | null; rms: number; cumplimiento_pct: number; puntos_promedio: number } | null;
  linea_oculta_motivo: string | null;
  indicadores: Indicador[];
};
type Indicador = { codigo: string; nombre: string; valor: number; cumplimiento_pct: number; puntaje: number };

const color = (p: number) => (p >= 90 ? '#2e7d32' : p >= 70 ? '#0057A8' : p >= 50 ? '#f57c00' : '#c62828');

function Tarjeta({ titulo, valor, sub, col }:
  { titulo: string; valor: string; sub?: string; col?: string }) {
  return (
    <Card variant="outlined" sx={{ height: '100%' }}>
      <CardContent sx={{ py: 1.75 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={700}>{titulo}</Typography>
        <Typography variant="h4" fontWeight={800} sx={{ color: col ?? 'primary.main' }}>{valor}</Typography>
        {sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}
      </CardContent>
    </Card>
  );
}

export default function MiProductividad() {
  const cicloId = useCicloStore((s) => s.cicloId);

  const { data, isLoading } = useQuery<MiLinea>({
    queryKey: ['mi-linea', cicloId],
    queryFn: () => api.get('/productividad/mi-linea',
      { params: cicloId ? { ciclo_id: cicloId } : {} }).then((r) => r.data),
  });
  if (isLoading) return <LinearProgress />;
  if (!data) return <Alert severity="error">No se pudo cargar tu productividad.</Alert>;

  const mio = data.rm.cumplimiento_pct;
  const dela = data.linea?.cumplimiento_pct ?? null;
  const dif = dela != null ? Math.round((mio - dela) * 10) / 10 : null;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <Insights color="primary" />
        <Typography variant="h5" fontWeight={700}>Mi Productividad</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Tus resultados del ciclo{data.rm.linea ? <> y el promedio de tu línea <b>{data.rm.linea}</b></> : ''}.
      </Typography>

      {data.rm.sin_datos && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Todavía no hay resultados cargados para ti en este ciclo. Aparecerán cuando
          Productividad cargue los KPIs del período.
        </Alert>
      )}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={4}>
          <Tarjeta titulo="TU CUMPLIMIENTO" valor={`${mio}%`} col={color(mio)}
                   sub={`${data.rm.puntos} puntos acumulados`} />
        </Grid>
        <Grid item xs={12} sm={4}>
          {data.linea ? (
            <Tarjeta titulo={`PROMEDIO DE TU LÍNEA`} valor={`${dela}%`} col={color(dela!)}
                     sub={`${data.linea.nombre} · ${data.linea.rms} representantes`} />
          ) : (
            <Card variant="outlined" sx={{ height: '100%' }}>
              <CardContent sx={{ py: 1.75 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  PROMEDIO DE TU LÍNEA
                </Typography>
                <Typography variant="h4" fontWeight={800} color="text.disabled">—</Typography>
                <Typography variant="caption" color="text.secondary">
                  {data.linea_oculta_motivo ?? 'No disponible'}
                </Typography>
              </CardContent>
            </Card>
          )}
        </Grid>
        <Grid item xs={12} sm={4}>
          {dif != null ? (
            <Card variant="outlined" sx={{ height: '100%',
                  borderColor: dif >= 0 ? '#2e7d32' : '#c62828', borderWidth: 2 }}>
              <CardContent sx={{ py: 1.75 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  TU DIFERENCIA
                </Typography>
                <Stack direction="row" alignItems="center" spacing={0.5}>
                  {dif >= 0 ? <TrendingUp sx={{ color: '#2e7d32' }} /> : <TrendingDown sx={{ color: '#c62828' }} />}
                  <Typography variant="h4" fontWeight={800} sx={{ color: dif >= 0 ? '#2e7d32' : '#c62828' }}>
                    {dif > 0 ? '+' : ''}{dif}
                  </Typography>
                  <Typography variant="body2" color="text.secondary">pts %</Typography>
                </Stack>
                <Typography variant="caption" color="text.secondary">
                  {dif >= 0 ? 'Por encima del promedio de tu línea' : 'Por debajo del promedio de tu línea'}
                </Typography>
              </CardContent>
            </Card>
          ) : <Tarjeta titulo="TU DIFERENCIA" valor="—" sub="Sin promedio de línea con el que comparar" />}
        </Grid>
      </Grid>

      {data.linea && (
        <Alert severity="info" sx={{ mb: 2 }}>
          El promedio de <b>{data.linea.nombre}</b> es un <b>agregado de {data.linea.rms} representantes</b>.
          No muestra —ni permite deducir— el resultado de ningún compañero en particular.
        </Alert>
      )}

      {data.indicadores.length > 0 && (
        <Paper variant="outlined" sx={{ p: 2 }}>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Mis indicadores</Typography>
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><b>Indicador</b></TableCell>
                  <TableCell align="right"><b>Valor</b></TableCell>
                  <TableCell align="right"><b>Cumplimiento</b></TableCell>
                  <TableCell align="right"><b>Puntos</b></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.indicadores.map((k) => (
                  <TableRow key={k.codigo} hover>
                    <TableCell>{k.nombre}</TableCell>
                    <TableCell align="right">{k.valor.toFixed(1)}</TableCell>
                    <TableCell align="right">
                      <Chip size="small" label={`${k.cumplimiento_pct.toFixed(1)}%`}
                            sx={{ bgcolor: color(k.cumplimiento_pct), color: '#fff', fontWeight: 700 }} />
                    </TableCell>
                    <TableCell align="right"><b>{k.puntaje.toFixed(1)}</b></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Paper>
      )}
    </Box>
  );
}
