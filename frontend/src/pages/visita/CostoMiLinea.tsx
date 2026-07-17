/**
 * CostoMiLinea.tsx — Vista del REPRESENTANTE en Costo & ROI.
 *
 * Regla del cliente (jul-2026): "este dato es meramente gerencial, no debe ser visto por el
 * representante. De esta pantalla solo deben tener acceso a las unidades que hay que producir
 * por contacto por producto de su línea para lograr el 100% de su presupuesto, y al impacto
 * económico que la cobertura está teniendo en el presupuesto de su línea".
 *
 * NO ve salarios, costos, ROI de la fuerza de venta, presupuesto total ni headcount.
 * Consume GET /visita/costo/mi-linea (auto-scoped a su línea en el backend).
 */
import {
  Box, Card, CardContent, Grid, Typography, Alert, LinearProgress, Stack,
  Table, TableHead, TableBody, TableRow, TableCell, Paper, Chip,
} from '@mui/material';
import { Inventory2, Warning } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { costoMiLinea } from '../../services/visita.service';
import { useCicloStore } from '../../store/ciclo.store';

const nf = (n: number) => n.toLocaleString('es-DO', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
const cumplColor = (p: number) => (p >= 100 ? '#2e7d32' : p >= 80 ? '#f57c00' : '#c62828');

export default function CostoMiLinea() {
  const cicloId = useCicloStore((s) => s.cicloId);
  const { data, isLoading } = useQuery({
    queryKey: ['costo-mi-linea', cicloId],
    queryFn: () => costoMiLinea(cicloId || undefined),
  });

  if (isLoading) return <LinearProgress />;
  if (!data) return <Alert severity="error">No se pudo cargar tu meta de línea.</Alert>;

  const mon = data.moneda || 'RD$';

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <Inventory2 color="primary" />
        <Typography variant="h5" fontWeight={700}>Mi Meta de Línea</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Lo que necesitas producir por contacto para llegar al 100% de tu presupuesto, y el
        impacto que tu cobertura está teniendo en el presupuesto de tu línea.
      </Typography>

      {!data.configurado && (
        <Alert severity="info" sx={{ mb: 2 }}>
          La meta de tu línea aún no está configurada para este ciclo.
        </Alert>
      )}

      {/* 1. Unidades a producir por contacto/producto para el 100%. */}
      <Paper variant="outlined" sx={{ p: 2, mb: 2 }}>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
          Unidades a producir por contacto
        </Typography>
        {data.unidades_por_contacto.length === 0 ? (
          <Typography variant="body2" color="text.secondary">
            No hay productos configurados para tu línea en este ciclo.
          </Typography>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell><b>Producto</b></TableCell>
                  <TableCell align="right"><b>Unidades / contacto (meta 100%)</b></TableCell>
                  <TableCell align="right"><b>Cumplimiento</b></TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.unidades_por_contacto.map((p) => (
                  <TableRow key={p.producto} hover>
                    <TableCell>{p.producto}</TableCell>
                    <TableCell align="right">
                      <Typography variant="h6" fontWeight={800} color="primary.main" component="span">
                        {nf(p.unidades_obj_contacto)}
                      </Typography>
                      <Typography variant="caption" color="text.secondary"> uds</Typography>
                    </TableCell>
                    <TableCell align="right">
                      <Chip size="small" label={`${p.cumplimiento_pct}%`}
                            sx={{ bgcolor: cumplColor(p.cumplimiento_pct), color: '#fff', fontWeight: 700 }} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Paper>

      {/* 2. Impacto económico de la cobertura en el presupuesto de la línea. */}
      <Paper variant="outlined" sx={{ p: 2 }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
          <Warning color="warning" fontSize="small" />
          <Typography variant="subtitle1" fontWeight={700}>
            Impacto de tu cobertura en el presupuesto
          </Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
          Los médicos que aún no has visitado representan una venta en riesgo para tu línea.
          Visitarlos protege ese presupuesto.
        </Typography>

        <Grid container spacing={2} sx={{ mb: 2 }}>
          <Grid item xs={12} sm={4}>
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>MÉDICOS SIN VISITAR</Typography>
              <Typography variant="h4" fontWeight={800} color="#c62828">
                {data.impacto_cobertura.total_medicos_sin_visitar.toLocaleString('es-DO')}
              </Typography>
            </CardContent></Card>
          </Grid>
          <Grid item xs={12} sm={4}>
            <Card variant="outlined" sx={{ borderColor: '#c62828', borderWidth: 2 }}><CardContent sx={{ py: 1.5 }}>
              <Typography variant="caption" color="text.secondary" fontWeight={700}>VENTA EN RIESGO</Typography>
              <Typography variant="h5" fontWeight={800} color="#c62828">
                {mon} {nf(data.impacto_cobertura.venta_riesgo_bajo)}
              </Typography>
              <Typography variant="caption" color="text.secondary">
                hasta {mon} {nf(data.impacto_cobertura.venta_riesgo_alto)}
              </Typography>
            </CardContent></Card>
          </Grid>
        </Grid>

        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell><b>Categoría</b></TableCell>
                <TableCell align="right"><b>Médicos sin visitar</b></TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {data.impacto_cobertura.categorias.map((c) => (
                <TableRow key={c.categoria} hover>
                  <TableCell><b>{c.categoria}</b></TableCell>
                  <TableCell align="right">{c.medicos_sin_visitar.toLocaleString('es-DO')}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      </Paper>
    </Box>
  );
}
