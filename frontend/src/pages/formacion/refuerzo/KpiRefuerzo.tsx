/**
 * KpiRefuerzo.tsx — Reporte de KPI del Refuerzo (§11): 3 métricas por 4 desgloses.
 *
 * Participación y aciertos NO se mezclan (§10.8): se calculan sobre universos
 * distintos y se muestran en columnas separadas. `pct_aciertos` puede ser null
 * (nada calificable en el segmento) y eso NO es 0.
 * El alcance lo recorta el backend por rol (§11.5); `por_gd` puede no venir.
 */
import { useQuery } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Table, TableHead, TableBody, TableRow, TableCell,
  Grid, Card, CardContent, Alert, CircularProgress, Stack,
} from '@mui/material';
import { useCicloStore } from '../../../store/ciclo.store';
import { reporteKpi, type Metricas, type PreguntaExtremo } from '../../../services/refuerzo.service';

const fmtTiempo = (seg: number) =>
  seg >= 60 ? `${Math.floor(seg / 60)} min ${seg % 60}s` : `${seg}s`;
const pct = (v: number | null) => (v === null || v === undefined ? '—' : `${v}%`);

export default function KpiRefuerzo() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const kpi = useQuery({
    queryKey: ['refuerzo-kpi', paisCodigo],
    queryFn: () => reporteKpi(paisCodigo ? { pais_codigo: paisCodigo } : {}),
  });

  if (kpi.isLoading) return <CircularProgress />;
  if (kpi.isError) return <Alert severity="warning">No se pudo cargar el KPI de Refuerzo.</Alert>;
  const d = kpi.data;
  if (!d) return null;

  if (d.total_respuestas === 0) {
    return <Alert severity="info">Todavía no hay respuestas de Refuerzo para este alcance.</Alert>;
  }

  return (
    <Box>
      <Grid container spacing={2} mb={2}>
        <Tarjeta titulo="Participación" valor={pct(d.general.pct_participacion)} />
        <Tarjeta titulo="Aciertos" valor={pct(d.general.pct_aciertos)} />
        <Tarjeta titulo="Tiempo promedio" valor={fmtTiempo(d.general.tiempo_promedio_seg)} />
        <Tarjeta titulo="Respuestas" valor={String(d.total_respuestas)} />
      </Grid>

      {(d.general.pregunta_mas_acertada || d.general.pregunta_menos_acertada) && (
        <Grid container spacing={2} mb={2}>
          <Extremo titulo="Pregunta más acertada" p={d.general.pregunta_mas_acertada} />
          <Extremo titulo="Pregunta menos acertada" p={d.general.pregunta_menos_acertada} />
        </Grid>
      )}

      <TablaDesglose titulo="Por representante" clave="rm_id" etiqueta="RM" filas={d.por_representante} />
      <TablaDesglose titulo="Por producto" clave="producto_id" etiqueta="Producto" filas={d.por_producto} />
      <TablaDesglose titulo="Por país" clave="pais_codigo" etiqueta="País" filas={d.por_pais} />
      {/* El backend omite `por_gd` para GD y RM (§11.3.c): no se inventa la tabla. */}
      {d.por_gd && (
        <TablaDesglose titulo="Por gerente de distrito" clave="gerente_id" etiqueta="GD" filas={d.por_gd} />
      )}
    </Box>
  );
}

function Tarjeta({ titulo, valor }: { titulo: string; valor: string }) {
  return (
    <Grid item xs={6} md={3}>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent>
          <Typography variant="caption" color="text.secondary">{titulo}</Typography>
          <Typography variant="h5" fontWeight={800}>{valor}</Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}

function Extremo({ titulo, p }: { titulo: string; p: PreguntaExtremo | null }) {
  if (!p) return null;
  return (
    <Grid item xs={12} md={6}>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent>
          <Typography variant="caption" color="text.secondary">{titulo}</Typography>
          <Typography variant="body2" sx={{ my: 1 }}>{p.enunciado}</Typography>
          <Stack direction="row" spacing={2}>
            <Typography variant="caption">Aciertos: <strong>{p.pct_aciertos}%</strong></Typography>
            <Typography variant="caption">Respuestas: <strong>{p.respuestas}</strong></Typography>
          </Stack>
        </CardContent>
      </Card>
    </Grid>
  );
}

function TablaDesglose<T extends Metricas>({ titulo, clave, etiqueta, filas }: {
  titulo: string; clave: string; etiqueta: string;
  filas: T[];
}) {
  return (
    <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3, p: 2 }}>
      <Typography variant="subtitle1" fontWeight={700} mb={1}>{titulo}</Typography>
      {filas.length === 0 ? (
        <Typography variant="body2" color="text.secondary">Sin datos.</Typography>
      ) : (
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>{etiqueta}</TableCell>
              <TableCell align="right">Respuestas</TableCell>
              <TableCell align="right">Participación</TableCell>
              <TableCell align="right">Aciertos</TableCell>
              <TableCell align="right">Tiempo prom.</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {filas.map((f, i) => {
              const valorClave = (f as unknown as Record<string, unknown>)[clave];
              return (
              <TableRow key={`${String(valorClave)}-${i}`}>
                <TableCell>{valorClave === null || valorClave === undefined ? '—' : String(valorClave)}</TableCell>
                <TableCell align="right">{f.respuestas}</TableCell>
                <TableCell align="right">{pct(f.pct_participacion)}</TableCell>
                <TableCell align="right">{pct(f.pct_aciertos)}</TableCell>
                <TableCell align="right">{fmtTiempo(f.tiempo_promedio_seg)}</TableCell>
              </TableRow>
              );
            })}
          </TableBody>
        </Table>
      )}
    </Paper>
  );
}
