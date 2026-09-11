/**
 * El detalle de un día de un representante, desplegado bajo su fila en «Así va el día».
 *
 * Responde a lo que la fila no dice: A QUIÉN visitó, a qué hora, si lo acompañó el
 * gerente, qué presentó y si era lo que tenía programado o fue fuera de agenda. Se pide
 * al abrir la fila (no con el monitor entero): son registros completos, y nadie los mira
 * de los cuarenta y tantos representantes a la vez.
 */
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Box, Chip, CircularProgress, Stack, Table, TableBody, TableCell, TableHead,
  TableRow, Tooltip, Typography,
} from '@mui/material';
import { Place, PhotoCamera, SupervisorAccount, LocalPharmacy, MedicalServices, RateReview } from '@mui/icons-material';
import { BORDE_SUAVE, SUPERFICIE_3 } from '../../theme/marca';
import { TEXTO_TENUE } from '../../components/layout/navTokens';
import { detalleDia, type VisitaDetalle } from '../../services/visitaDia.service';

const encabezado = { '& th': { fontWeight: 700, py: 0.5, fontSize: '0.72rem', color: TEXTO_TENUE } };

/** Ubicación y foto: en color si están, en gris si no — las dos cosas que se auditan. */
function Evidencia({ gps, foto }: { gps: boolean; foto: boolean }) {
  return (
    <Stack direction="row" spacing={0.5}>
      <Tooltip title={gps ? 'Con ubicación' : 'Sin ubicación'}>
        <Place fontSize="small" color={gps ? 'success' : 'disabled'} />
      </Tooltip>
      <Tooltip title={foto ? 'Con foto' : 'Sin foto'}>
        <PhotoCamera fontSize="small" color={foto ? 'success' : 'disabled'} />
      </Tooltip>
    </Stack>
  );
}

function Tipo({ v }: { v: VisitaDetalle }) {
  if (!v.ejecutada) {
    return <Chip size="small" color="warning" variant="outlined" label="No visitado"
                 title={v.causa_no_visita ?? undefined} />;
  }
  return <Chip size="small" variant="outlined" color={v.tipo_visita === 'R' ? 'secondary' : 'primary'}
               label={v.tipo_visita === 'R' ? 'Revisita' : 'Vista'} />;
}

function Titulo({ icono, texto, n }: { icono: React.ReactNode; texto: string; n: number }) {
  return (
    <Stack direction="row" spacing={0.75} alignItems="center" sx={{ mb: 0.5 }}>
      {icono}
      <Typography variant="body2" sx={{ fontWeight: 700 }}>{texto} · {n}</Typography>
    </Stack>
  );
}

export default function DetalleDiaRepresentante({ rmId, fecha }: { rmId: number; fecha: string }) {
  const { data, isLoading, error } = useQuery({
    queryKey: ['dia-detalle', rmId, fecha],
    queryFn: () => detalleDia(rmId, fecha),
  });

  if (isLoading) return <Box sx={{ p: 2, textAlign: 'center' }}><CircularProgress size={22} /></Box>;
  if (error || !data) return <Alert severity="error" sx={{ m: 1.5 }}>No se pudo cargar el detalle del día.</Alert>;

  const vacio = data.visitas.length + data.farmacias.length + data.more.length === 0;
  return (
    <Box sx={{ px: { xs: 1.5, md: 3 }, py: 1.5, bgcolor: SUPERFICIE_3, borderTop: `1px solid ${BORDE_SUAVE}` }}>
      {vacio && (
        <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>
          Sin registros recibidos este día. Puede no haber sincronizado todavía.
        </Typography>
      )}

      {data.visitas.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Titulo icono={<MedicalServices fontSize="small" color="primary" />} texto="Visitas médicas" n={data.visitas.length} />
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={encabezado}>
                  <TableCell>Hora</TableCell>
                  <TableCell>Médico</TableCell>
                  <TableCell>Tipo</TableCell>
                  <TableCell>Agenda</TableCell>
                  <TableCell>Gerente</TableCell>
                  <TableCell>Productos</TableCell>
                  <TableCell>Evidencia</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.visitas.map((v) => (
                  <TableRow key={v.id}>
                    <TableCell sx={{ whiteSpace: 'nowrap', fontWeight: 700 }}>{v.hora ?? '—'}</TableCell>
                    <TableCell sx={{ maxWidth: 320 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{v.medico}</Typography>
                      <Typography variant="caption" sx={{ color: TEXTO_TENUE, display: 'block' }}>
                        {[v.especialidad, v.categoria ? `Cat. ${v.categoria}` : null].filter(Boolean).join(' · ')}
                      </Typography>
                      {(v.comentario || v.causa_no_visita) && (
                        <Typography variant="caption" noWrap title={v.comentario ?? v.causa_no_visita ?? ''}
                                    sx={{ color: TEXTO_TENUE, fontStyle: 'italic', display: 'block' }}>
                          «{v.comentario ?? v.causa_no_visita}»
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell><Tipo v={v} /></TableCell>
                    <TableCell>
                      {v.programada_hoy
                        ? <Chip size="small" color="success" variant="outlined" label="Programada hoy" />
                        : <Chip size="small" color="warning" variant="outlined" label="Fuera de agenda" />}
                    </TableCell>
                    <TableCell>
                      {v.acompanado
                        ? <Chip size="small" color="primary" icon={<SupervisorAccount />} label="Con GD" />
                        : <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>—</Typography>}
                    </TableCell>
                    <TableCell sx={{ maxWidth: 220 }}>
                      <Typography variant="caption">{v.productos.length ? v.productos.join(', ') : '—'}</Typography>
                    </TableCell>
                    <TableCell><Evidencia gps={v.tiene_gps} foto={v.tiene_foto} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Box>
      )}

      {data.farmacias.length > 0 && (
        <Box sx={{ mb: 1.5 }}>
          <Titulo icono={<LocalPharmacy fontSize="small" color="secondary" />} texto="Farmacias" n={data.farmacias.length} />
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={encabezado}>
                  <TableCell>Hora</TableCell>
                  <TableCell>Farmacia</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell>Evidencia</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {data.farmacias.map((f) => (
                  <TableRow key={f.id}>
                    <TableCell sx={{ whiteSpace: 'nowrap', fontWeight: 700 }}>{f.hora ?? '—'}</TableCell>
                    <TableCell sx={{ maxWidth: 360 }}>
                      <Typography variant="body2" sx={{ fontWeight: 600 }}>{f.farmacia}</Typography>
                      {(f.comentario || f.causa_no_visita) && (
                        <Typography variant="caption" noWrap title={f.comentario ?? f.causa_no_visita ?? ''}
                                    sx={{ color: TEXTO_TENUE, fontStyle: 'italic', display: 'block' }}>
                          «{f.comentario ?? f.causa_no_visita}»
                        </Typography>
                      )}
                    </TableCell>
                    <TableCell>
                      {f.ejecutada
                        ? <Chip size="small" color="success" variant="outlined" label="Visitada" />
                        : <Chip size="small" color="warning" variant="outlined" label="No visitada" />}
                    </TableCell>
                    <TableCell><Evidencia gps={f.tiene_gps} foto={f.tiene_foto} /></TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Box>
      )}

      {data.more.length > 0 && (
        <Box>
          <Titulo icono={<RateReview fontSize="small" color="action" />} texto="Hojas MORE" n={data.more.length} />
          {data.more.map((m) => (
            <Typography key={m.id} variant="body2">
              {m.gerente ?? 'Gerente'} · {m.medicos_vistos} médicos vistos
              {m.evaluacion_promedio !== null ? ` · evaluación ${m.evaluacion_promedio.toFixed(1)}` : ''}
            </Typography>
          ))}
        </Box>
      )}
    </Box>
  );
}
