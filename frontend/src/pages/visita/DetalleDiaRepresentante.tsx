/**
 * El detalle de un día de un representante, desplegado bajo su fila en «Así va el día».
 *
 * Responde a lo que la fila no dice: A QUIÉN visitó, a qué hora, si lo acompañó el
 * gerente, qué presentó y si era lo que tenía programado o fue fuera de agenda. Se pide
 * al abrir la fila (no con el monitor entero): son registros completos, y nadie los mira
 * de los cuarenta y tantos representantes a la vez.
 */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Alert, Box, Button, Chip, CircularProgress, Dialog, DialogActions, DialogContent, DialogTitle,
  IconButton, Link, Stack, Table, TableBody, TableCell, TableHead, TableRow, Tooltip, Typography,
} from '@mui/material';
import { Place, PhotoCamera, SupervisorAccount, LocalPharmacy, MedicalServices, RateReview, OpenInNew } from '@mui/icons-material';
import { BORDE_SUAVE, SUPERFICIE_3 } from '../../theme/marca';
import { TEXTO_TENUE } from '../../components/layout/navTokens';
import { detalleDia, fotoVisitaDia, type VisitaDetalle } from '../../services/visitaDia.service';

const encabezado = { '& th': { fontWeight: 700, py: 0.5, fontSize: '0.72rem', color: TEXTO_TENUE } };

/** Lo que se abre al pulsar 📍 o 📷: la foto y el punto en el mapa de UNA visita. */
interface Evidencia {
  tipo: 'medico' | 'farmacia'; id: number; titulo: string; subtitulo: string;
  foto: boolean; lat: number | null; lon: number | null;
}

/**
 * Ubicación y foto: en color si están, en gris si no — y las que están se PULSAN para
 * verlas. Un icono verde que no se puede abrir afirma que hay evidencia sin enseñarla.
 */
function IconosEvidencia({ gps, foto, abrir }: { gps: boolean; foto: boolean; abrir: () => void }) {
  return (
    <Stack direction="row" spacing={0}>
      <Tooltip title={gps ? 'Ver la ubicación en el mapa' : 'Sin ubicación'}>
        <span>
          <IconButton size="small" disabled={!gps} onClick={(e) => { e.stopPropagation(); abrir(); }}>
            <Place fontSize="small" color={gps ? 'success' : 'disabled'} />
          </IconButton>
        </span>
      </Tooltip>
      <Tooltip title={foto ? 'Ver la foto' : 'Sin foto'}>
        <span>
          <IconButton size="small" disabled={!foto} onClick={(e) => { e.stopPropagation(); abrir(); }}>
            <PhotoCamera fontSize="small" color={foto ? 'success' : 'disabled'} />
          </IconButton>
        </span>
      </Tooltip>
    </Stack>
  );
}

/** Mapa de OpenStreetMap con el punto marcado (no exige clave, a diferencia de Google). */
function mapaUrl(lat: number, lon: number) {
  const d = 0.004;
  return `https://www.openstreetmap.org/export/embed.html?bbox=${lon - d},${lat - d},${lon + d},${lat + d}`
    + `&layer=mapnik&marker=${lat},${lon}`;
}

function DialogoEvidencia({ ev, cerrar }: { ev: Evidencia | null; cerrar: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [fallo, setFallo] = useState(false);

  // La foto va con la sesión del usuario: se pide como blob y se muestra desde memoria.
  useEffect(() => {
    setUrl(null); setFallo(false);
    if (!ev?.foto) return;
    let vivo = true;
    let objeto: string | null = null;
    fotoVisitaDia(ev.tipo, ev.id)
      .then((b) => { if (vivo) { objeto = URL.createObjectURL(b); setUrl(objeto); } })
      .catch(() => { if (vivo) setFallo(true); });
    return () => { vivo = false; if (objeto) URL.revokeObjectURL(objeto); };
  }, [ev]);

  const conPunto = ev && ev.lat !== null && ev.lon !== null;
  return (
    <Dialog open={!!ev} onClose={cerrar} maxWidth="md" fullWidth>
      <DialogTitle sx={{ pb: 0.5 }}>
        {ev?.titulo}
        <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>{ev?.subtitulo}</Typography>
      </DialogTitle>
      <DialogContent dividers>
        <Stack direction={{ xs: 'column', md: 'row' }} spacing={2}>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>📷 Foto</Typography>
            {!ev?.foto ? (
              <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>Esta visita no tiene foto.</Typography>
            ) : fallo ? (
              <Alert severity="error">No se pudo cargar la foto.</Alert>
            ) : !url ? (
              <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress size={24} /></Box>
            ) : (
              <Box component="a" href={url} target="_blank" rel="noopener" title="Abrir la foto en tamaño completo">
                <Box component="img" src={url} alt={`Foto de la visita a ${ev.titulo}`}
                     sx={{ width: '100%', maxHeight: 380, objectFit: 'contain', borderRadius: 1,
                           border: `1px solid ${BORDE_SUAVE}`, bgcolor: '#000' }} />
              </Box>
            )}
          </Box>
          <Box sx={{ flex: 1, minWidth: 0 }}>
            <Typography variant="body2" sx={{ fontWeight: 700, mb: 0.5 }}>📍 Georreferencia</Typography>
            {!conPunto ? (
              <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>La visita se registró sin ubicación.</Typography>
            ) : (
              <>
                <Box component="iframe" title="Mapa de la visita" src={mapaUrl(ev!.lat!, ev!.lon!)} loading="lazy"
                     sx={{ width: '100%', height: 300, border: `1px solid ${BORDE_SUAVE}`, borderRadius: 1 }} />
                <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 0.5 }} flexWrap="wrap">
                  <Typography variant="caption" sx={{ fontFamily: 'monospace' }}>
                    {ev!.lat!.toFixed(6)}, {ev!.lon!.toFixed(6)}
                  </Typography>
                  <Link variant="caption" href={`https://www.google.com/maps?q=${ev!.lat},${ev!.lon}`}
                        target="_blank" rel="noopener" sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.3 }}>
                    Abrir en Google Maps <OpenInNew sx={{ fontSize: 13 }} />
                  </Link>
                </Stack>
              </>
            )}
          </Box>
        </Stack>
      </DialogContent>
      <DialogActions><Button onClick={cerrar}>Cerrar</Button></DialogActions>
    </Dialog>
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
  const [evidencia, setEvidencia] = useState<Evidencia | null>(null);

  if (isLoading) return <Box sx={{ p: 2, textAlign: 'center' }}><CircularProgress size={22} /></Box>;
  if (error || !data) return <Alert severity="error" sx={{ m: 1.5 }}>No se pudo cargar el detalle del día.</Alert>;

  const vacio = data.visitas.length + data.farmacias.length + data.more.length === 0;
  return (
    <Box sx={{ px: { xs: 1.5, md: 3 }, py: 1.5, bgcolor: SUPERFICIE_3, borderTop: `1px solid ${BORDE_SUAVE}` }}
         onClick={(e) => e.stopPropagation()}>
      <DialogoEvidencia ev={evidencia} cerrar={() => setEvidencia(null)} />
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
                    <TableCell>
                      <IconosEvidencia gps={v.tiene_gps} foto={v.tiene_foto} abrir={() => setEvidencia({
                        tipo: 'medico', id: v.id, titulo: v.medico,
                        subtitulo: `${v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : 'No visitado'} · ${v.hora ?? ''}`,
                        foto: v.tiene_foto, lat: v.latitud, lon: v.longitud,
                      })} />
                    </TableCell>
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
                    <TableCell>
                      <IconosEvidencia gps={f.tiene_gps} foto={f.tiene_foto} abrir={() => setEvidencia({
                        tipo: 'farmacia', id: f.id, titulo: f.farmacia,
                        subtitulo: `Farmacia · ${f.hora ?? ''}`,
                        foto: f.tiene_foto, lat: f.latitud, lon: f.longitud,
                      })} />
                    </TableCell>
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
