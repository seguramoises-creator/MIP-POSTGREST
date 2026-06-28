import { useEffect, useState, Fragment } from 'react';
import {
  Box, Typography, Card, CardContent, Table, TableHead, TableRow, TableCell,
  TableBody, Chip, Alert, CircularProgress, Stack, Collapse, IconButton, Button,
} from '@mui/material';
import { KeyboardArrowDown, KeyboardArrowRight, CheckCircle, Cancel, FileDownload } from '@mui/icons-material';
import { resumenEquipo, exportarEquipoExcel, type EquipoRM } from '../../services/examenes.service';

export default function EquipoExamenes() {
  const [equipo, setEquipo] = useState<EquipoRM[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [abierto, setAbierto] = useState<Record<number, boolean>>({});

  useEffect(() => {
    resumenEquipo()
      .then(setEquipo)
      .catch((e: { response?: { status?: number; data?: { detail?: string } } }) => {
        if (e?.response?.status === 403) setError(e.response.data?.detail || 'Tu usuario no está vinculado a un gerente.');
        else setError('No se pudieron cargar los resultados del equipo.');
        setEquipo([]);
      });
  }, []);

  if (equipo === null && !error) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const totalRm = equipo?.length ?? 0;
  const conPromedio = (equipo ?? []).filter((r) => r.promedio != null);
  const promedioEquipo = conPromedio.length
    ? Math.round((conPromedio.reduce((s, r) => s + (r.promedio ?? 0), 0) / conPromedio.length) * 100) / 100
    : null;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>Exámenes — Mi Equipo</Typography>
        {equipo && equipo.length > 0 && (
          <Button startIcon={<FileDownload />} variant="outlined" onClick={() => exportarEquipoExcel()}>
            Exportar a Excel
          </Button>
        )}
      </Box>
      {error && <Alert severity="info" sx={{ mb: 2 }}>{error}</Alert>}

      {equipo && equipo.length > 0 && (
        <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: 'wrap' }}>
          <Kpi label="Visitadores" valor={`${totalRm}`} />
          <Kpi label="Promedio del equipo" valor={promedioEquipo != null ? `${promedioEquipo}%` : '—'} />
        </Stack>
      )}

      {equipo && equipo.length === 0 && !error && (
        <Alert severity="info">No hay visitadores en tu equipo o aún no tienen exámenes.</Alert>
      )}

      {equipo && equipo.length > 0 && (
        <Card variant="outlined">
          <CardContent>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell />
                  <TableCell>Visitador</TableCell>
                  <TableCell>Asignados</TableCell>
                  <TableCell>Completados</TableCell>
                  <TableCell>Promedio</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {equipo.map((rm) => (
                  <Fragment key={rm.rm_id}>
                    <TableRow hover sx={{ cursor: 'pointer' }}
                              onClick={() => setAbierto((a) => ({ ...a, [rm.rm_id]: !a[rm.rm_id] }))}>
                      <TableCell>
                        <IconButton size="small">
                          {abierto[rm.rm_id] ? <KeyboardArrowDown /> : <KeyboardArrowRight />}
                        </IconButton>
                      </TableCell>
                      <TableCell>{rm.nombre}</TableCell>
                      <TableCell>{rm.asignados}</TableCell>
                      <TableCell>{rm.completados}</TableCell>
                      <TableCell>{rm.promedio != null ? `${rm.promedio}%` : '—'}</TableCell>
                    </TableRow>
                    <TableRow>
                      <TableCell colSpan={5} sx={{ py: 0, borderBottom: abierto[rm.rm_id] ? undefined : 'none' }}>
                        <Collapse in={abierto[rm.rm_id]} unmountOnExit>
                          <Box sx={{ py: 1 }}>
                            {rm.examenes.length === 0 && (
                              <Typography variant="body2" color="text.secondary">Sin exámenes asignados.</Typography>
                            )}
                            {rm.examenes.map((ex) => (
                              <Stack key={ex.examen_id} direction="row" spacing={1} alignItems="center" sx={{ py: 0.25 }}>
                                {ex.aprobado ? <CheckCircle color="success" fontSize="small" /> : <Cancel color="disabled" fontSize="small" />}
                                <Typography variant="body2" sx={{ flex: 1 }}>{ex.examen_nombre}</Typography>
                                <Chip size="small" label={ex.ultimo_score != null ? `${ex.ultimo_score}%` : 'pendiente'}
                                      color={ex.aprobado ? 'success' : 'default'} />
                                <Typography variant="caption" color="text.secondary">{ex.estado}</Typography>
                              </Stack>
                            ))}
                          </Box>
                        </Collapse>
                      </TableCell>
                    </TableRow>
                  </Fragment>
                ))}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}
    </Box>
  );
}

function Kpi({ label, valor }: { label: string; valor: string }) {
  return (
    <Card variant="outlined" sx={{ minWidth: 150 }}>
      <CardContent sx={{ py: 1.5 }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h6" fontWeight={700}>{valor}</Typography>
      </CardContent>
    </Card>
  );
}
