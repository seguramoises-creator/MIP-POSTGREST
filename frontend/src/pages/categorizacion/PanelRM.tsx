/**
 * PanelRM.tsx — Categorización DEL PANEL del representante.
 *
 * Son dos categorías distintas por diseño (ver §14b de CLAUDE.md):
 *   · La GENERAL la calcula el motor de 5 criterios (cat.*), por período, y es un proceso
 *     aparte del administrador — es lo que ve la gerencia en Categorizacion.tsx.
 *   · La DEL PANEL es la del médico dentro del panel de ESE representante: al darlo de alta
 *     el sistema le propone la calculada y él la ajusta a su criterio. Sobre este panel
 *     programa sus visitas y revisitas. Ajustarla NO altera la categorización general.
 *
 * Por eso esta vista no tiene selector de período: la categoría del panel es estable entre
 * ciclos. Consume GET /categorizacion/mi-panel.
 */
import {
  Box, Card, CardContent, Grid, Typography, Chip, Alert, LinearProgress, Stack,
  Table, TableHead, TableBody, TableRow, TableCell, Paper, Tooltip,
} from '@mui/material';
import MedicalServicesIcon from '@mui/icons-material/MedicalServices';
import { useQuery } from '@tanstack/react-query';
import { PieChart, Pie, Cell, Tooltip as ReTooltip, Legend, ResponsiveContainer } from 'recharts';
import { api } from '../../services/api';
import { CAT_PAL, CATS } from './paleta';

type MedicoPanel = {
  id: number; nombre: string; especialidad: string | null;
  categoria: string | null; centro_trabajo: string | null;
  frecuencia_visita: number | null; estado_aprobacion: string | null;
};
type PanelRMData = {
  total_medicos: number;
  categoria_a: number; categoria_b: number; categoria_c: number; categoria_d: number;
  sin_categoria: number;
  medicos: MedicoPanel[];
};

function KpiCat({ cat, valor, total }: { cat: string; valor: number; total: number }) {
  const pal = CAT_PAL[cat];
  const pct = total ? Math.round((valor / total) * 100) : 0;
  return (
    <Grid item xs={6} sm={4} md={2.4}>
      <Card variant="outlined" sx={{ borderColor: pal.light, borderWidth: 2 }}>
        <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
          <Stack direction="row" alignItems="center" spacing={1}>
            <Box sx={{
              width: 28, height: 28, borderRadius: '50%', bgcolor: pal.mid, color: pal.text,
              display: 'flex', alignItems: 'center', justifyContent: 'center', fontWeight: 800,
            }}>{cat}</Box>
            <Typography variant="h5" fontWeight={800} sx={{ color: pal.dark }}>{valor}</Typography>
          </Stack>
          <LinearProgress variant="determinate" value={pct}
            sx={{ height: 5, borderRadius: 3, mt: 1, bgcolor: pal.light,
                  '& .MuiLinearProgress-bar': { bgcolor: pal.mid } }} />
          <Typography variant="caption" color="text.secondary">{pct}% del panel</Typography>
        </CardContent>
      </Card>
    </Grid>
  );
}

export default function PanelRM() {
  const { data, isLoading } = useQuery<PanelRMData>({
    queryKey: ['cat-mi-panel'],
    queryFn: () => api.get('/categorizacion/mi-panel').then((r) => r.data),
  });

  if (isLoading) return <LinearProgress />;
  if (!data) return <Alert severity="error">No se pudo cargar tu panel médico.</Alert>;

  const pieData = CATS.map((c) => ({
    name: `Categoría ${c}`,
    value: data[`categoria_${c.toLowerCase()}` as keyof PanelRMData] as number,
    cat: c,
  })).filter((d) => d.value > 0);

  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <MedicalServicesIcon color="primary" />
        <Typography variant="h5" fontWeight={700}>Categorización de mi Panel</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        La categoría de cada médico <b>dentro de tu panel</b> — la que usas para programar tus
        visitas y revisitas. Se mantiene estable entre ciclos: solo cambia cuando actualizas
        un médico o cuando se hace una carga masiva.
      </Typography>

      {data.total_medicos === 0 && (
        <Alert severity="info">Todavía no tienes médicos en tu panel.</Alert>
      )}

      {data.total_medicos > 0 && (
        <>
          <Grid container spacing={2} sx={{ mb: 2 }}>
            <Grid item xs={6} sm={4} md={2.4}>
              <Card variant="outlined">
                <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={600}>
                    TOTAL EN MI PANEL
                  </Typography>
                  <Typography variant="h4" fontWeight={800} color="primary.main">
                    {data.total_medicos}
                  </Typography>
                  <Typography variant="caption" color="text.secondary">médicos activos</Typography>
                </CardContent>
              </Card>
            </Grid>
            {CATS.map((c) => (
              <KpiCat key={c} cat={c} total={data.total_medicos}
                      valor={data[`categoria_${c.toLowerCase()}` as keyof PanelRMData] as number} />
            ))}
          </Grid>

          {data.sin_categoria > 0 && (
            <Alert severity="warning" sx={{ mb: 2 }}>
              <b>{data.sin_categoria}</b> médico(s) de tu panel no tienen una categoría válida
              (A/B/C/D). Edítalos en <b>Panel Médico</b> para asignársela.
            </Alert>
          )}

          <Grid container spacing={2}>
            <Grid item xs={12} md={4}>
              <Paper variant="outlined" sx={{ p: 2, height: '100%' }}>
                <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                  Distribución
                </Typography>
                <ResponsiveContainer width="100%" height={260}>
                  <PieChart>
                    <Pie data={pieData} dataKey="value" nameKey="name" outerRadius={90} label>
                      {pieData.map((d) => <Cell key={d.cat} fill={CAT_PAL[d.cat].mid} />)}
                    </Pie>
                    <ReTooltip /><Legend />
                  </PieChart>
                </ResponsiveContainer>
              </Paper>
            </Grid>

            <Grid item xs={12} md={8}>
              <Paper variant="outlined" sx={{ p: 2 }}>
                <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>
                  Mis médicos ({data.medicos.length})
                </Typography>
                <Box sx={{ overflowX: 'auto' }}>
                  <Table size="small">
                    <TableHead>
                      <TableRow>
                        <TableCell><b>Médico</b></TableCell>
                        <TableCell><b>Especialidad</b></TableCell>
                        <TableCell><b>Centro</b></TableCell>
                        <TableCell align="center"><b>Frec.</b></TableCell>
                        <TableCell align="center"><b>Categoría</b></TableCell>
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {data.medicos.map((m) => {
                        const pal = m.categoria ? CAT_PAL[m.categoria] : null;
                        return (
                          <TableRow key={m.id} hover>
                            <TableCell>
                              {m.nombre}
                              {m.estado_aprobacion && m.estado_aprobacion !== 'APROBADO' && (
                                <Tooltip title="Pendiente de aprobación del Gerente de Distrito">
                                  <Chip size="small" label="Pendiente" color="warning"
                                        variant="outlined" sx={{ ml: 1, height: 18, fontSize: 10 }} />
                                </Tooltip>
                              )}
                            </TableCell>
                            <TableCell>{m.especialidad ?? '—'}</TableCell>
                            <TableCell>{m.centro_trabajo ?? '—'}</TableCell>
                            <TableCell align="center">{m.frecuencia_visita ?? '—'}</TableCell>
                            <TableCell align="center">
                              {pal ? (
                                <Chip size="small" label={m.categoria}
                                      sx={{ bgcolor: pal.mid, color: pal.text, fontWeight: 800, minWidth: 34 }} />
                              ) : <Chip size="small" label="—" variant="outlined" />}
                            </TableCell>
                          </TableRow>
                        );
                      })}
                    </TableBody>
                  </Table>
                </Box>
              </Paper>
            </Grid>
          </Grid>
        </>
      )}
    </Box>
  );
}
