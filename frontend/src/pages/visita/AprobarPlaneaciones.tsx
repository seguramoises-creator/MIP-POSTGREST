/**
 * Aprobar planeaciones — la bandeja del Gerente de Distrito.
 *
 * El representante arma su planeación del ciclo (en la app o en la web) y la ENVÍA. Aquí
 * su gerente la lee médico por médico y decide: APROBAR (queda publicada y congelada:
 * es el denominador de la cobertura del ciclo) o DEVOLVER con lo que hay que corregir.
 *
 * Decisiones:
 * 1. SE LISTA TODO EL EQUIPO, no solo lo pendiente. Quien aún no envió nada también es
 *    información: esconderlo haría creer que el distrito está completo.
 * 2. PRIMERO LO QUE ESPERA RESPUESTA (enviadas), después lo devuelto, lo no enviado y lo
 *    aprobado — el orden de la atención, no el alfabético.
 * 3. DEVOLVER EXIGE MOTIVO. Sin él, el representante adivina qué corregir y la siguiente
 *    versión llega con el mismo problema.
 * 4. LOS MÉDICOS QUE QUEDARON FUERA se muestran, con los TOP primero: lo que falta en un
 *    plan pesa tanto como lo que tiene.
 */
import { useEffect, useState } from 'react';
import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, Stack, Chip, Table, TableHead, TableRow, TableCell,
  TableBody, Button, Dialog, DialogTitle, DialogContent, DialogActions, TextField, Alert,
  CircularProgress, MenuItem,
} from '@mui/material';
import { FactCheck, CheckCircle, Undo, HourglassTop, Star } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { TEXTO_TENUE } from '../../components/layout/navTokens';
import { BORDE_SUAVE } from '../../theme/marca';
import {
  planeacionEquipo, planeacionDetalle, aprobarPlaneacion, devolverPlaneacion, listarGerentesVisita,
  type PlaneacionEquipoFila, type EstadoPlaneacion, type Catalogo,
} from '../../services/visita.service';

const ESTADOS: Record<EstadoPlaneacion, { texto: string; color: 'info' | 'success' | 'warning' | 'default'; orden: number }> = {
  ENVIADA: { texto: 'Por aprobar', color: 'info', orden: 0 },
  DEVUELTA: { texto: 'Devuelta', color: 'warning', orden: 1 },
  BORRADOR: { texto: 'Sin enviar', color: 'default', orden: 2 },
  PUBLICADA: { texto: 'Aprobada', color: 'success', orden: 3 },
};

/** «Lunes» → «Lun». Las columnas de semana tienen que caber en un renglón. */
const diaCorto = (d: string | null) => (d ? d.slice(0, 3) : '');
const semanaTxt = (s: number | null, d: string | null) =>
  s ? `S${s}${d ? ` · ${diaCorto(d)}` : ''}` : '—';
/** Las fechas llegan en UTC sin huso: se les pone la Z para que el navegador las traduzca. */
const fechaLocal = (iso: string | null) => (iso ? new Date(`${iso}Z`).toLocaleDateString() : '');

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  return typeof d === 'string' ? d : fallback;
}

function ChipEstado({ fila }: { fila: Pick<PlaneacionEquipoFila, 'estado' | 'medicos_planeados'> }) {
  const e = ESTADOS[fila.estado];
  const texto = fila.estado === 'BORRADOR' && fila.medicos_planeados === 0 ? 'Sin planear' : e.texto;
  return <Chip size="small" color={e.color} variant={fila.estado === 'BORRADOR' ? 'outlined' : 'filled'}
               icon={fila.estado === 'ENVIADA' ? <HourglassTop /> : undefined} label={texto} />;
}

export default function AprobarPlaneaciones() {
  const rol = useAuthStore((s) => s.rol);
  const esAdmin = rol === 'ADMIN';
  const qc = useQueryClient();
  const [gerenteId, setGerenteId] = useState<number | ''>('');
  const [gerentes, setGerentes] = useState<Catalogo[]>([]);
  const [abierta, setAbierta] = useState<PlaneacionEquipoFila | null>(null);
  const [devolviendo, setDevolviendo] = useState(false);
  const [motivo, setMotivo] = useState('');
  const [ocupado, setOcupado] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // Solo el ADMIN elige gerente: al GD el servidor le fija su propio equipo.
  useEffect(() => {
    if (esAdmin) listarGerentesVisita().then(setGerentes).catch(() => setGerentes([]));
  }, [esAdmin]);

  const { data: equipo, isLoading, error } = useQuery({
    queryKey: ['planeacion-equipo', gerenteId],
    queryFn: () => planeacionEquipo(gerenteId || undefined),
  });
  const { data: detalle, isLoading: cargandoDetalle } = useQuery({
    queryKey: ['planeacion-detalle', abierta?.vm_id],
    queryFn: () => planeacionDetalle(abierta!.vm_id),
    enabled: !!abierta,
  });

  const filas = [...(equipo ?? [])].sort((a, b) =>
    ESTADOS[a.estado].orden - ESTADOS[b.estado].orden || a.codigo.localeCompare(b.codigo));
  const cuenta = (e: EstadoPlaneacion) => filas.filter((f) => f.estado === e).length;

  function cerrar() { setAbierta(null); setDevolviendo(false); setMotivo(''); }

  async function decidir(accion: 'aprobar' | 'devolver') {
    if (!abierta) return;
    setOcupado(true); setMsg(null);
    try {
      if (accion === 'aprobar') {
        const r = await aprobarPlaneacion(abierta.vm_id);
        setMsg({ tipo: 'success', texto: `Planeación de ${abierta.nombre} aprobada (${r.items} visitas). Queda publicada para el ciclo.` });
      } else {
        await devolverPlaneacion(abierta.vm_id, motivo.trim());
        setMsg({ tipo: 'success', texto: `Planeación devuelta a ${abierta.nombre} con tus observaciones.` });
      }
      cerrar();
      await qc.invalidateQueries({ queryKey: ['planeacion-equipo'] });
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo completar la acción.') });
    } finally { setOcupado(false); }
  }

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="overline" sx={{ color: TEXTO_TENUE, letterSpacing: 1 }}>
        Maestros y planeación
      </Typography>
      <Stack direction="row" spacing={1} alignItems="center">
        <FactCheck color="primary" />
        <Typography variant="h5" fontWeight={800}>Aprobar planeaciones</Typography>
      </Stack>
      <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 1.5 }}>
        La planeación del ciclo que te envía cada representante. Al aprobarla queda publicada y es
        la base con la que se mide su cobertura; si algo no está bien, devuélvesela con tus observaciones.
      </Typography>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 1.5 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Stack direction="row" spacing={1} sx={{ mb: 1.5, flexWrap: 'wrap' }} useFlexGap alignItems="center">
        {esAdmin && (
          <TextField select size="small" label="Gerente de Distrito" value={gerenteId}
                     onChange={(e) => setGerenteId(e.target.value === '' ? '' : Number(e.target.value))}
                     sx={{ minWidth: 240 }}>
            <MenuItem value="">Todos los distritos</MenuItem>
            {gerentes.map((g) => <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>)}
          </TextField>
        )}
        {(['ENVIADA', 'DEVUELTA', 'BORRADOR', 'PUBLICADA'] as EstadoPlaneacion[]).map((e) => (
          <Chip key={e} size="small" variant="outlined" color={ESTADOS[e].color}
                label={`${ESTADOS[e].texto}: ${cuenta(e)}`} />
        ))}
      </Stack>

      <Card variant="outlined" sx={{ borderRadius: 2 }}>
        {isLoading ? <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
         : error ? <Alert severity="error" sx={{ m: 2 }}>No se pudo cargar la planeación de tu equipo.</Alert>
         : filas.length === 0 ? (
          <CardContent>
            <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>
              No hay representantes activos en este equipo.
            </Typography>
          </CardContent>
        ) : (
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead>
                <TableRow sx={{ '& th': { borderBottom: `2px solid ${BORDE_SUAVE}`, fontWeight: 700 } }}>
                  <TableCell>Representante</TableCell>
                  <TableCell>Estado</TableCell>
                  <TableCell align="right">Médicos planeados</TableCell>
                  <TableCell align="right">Vistas</TableCell>
                  <TableCell align="right">Revisitas</TableCell>
                  <TableCell>Fecha</TableCell>
                  <TableCell />
                </TableRow>
              </TableHead>
              <TableBody>
                {filas.map((f) => (
                  <TableRow key={f.vm_id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>{f.codigo} · {f.nombre}</Typography>
                      {f.estado === 'DEVUELTA' && f.motivo && (
                        <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>«{f.motivo}»</Typography>
                      )}
                    </TableCell>
                    <TableCell><ChipEstado fila={f} /></TableCell>
                    <TableCell align="right">
                      {f.medicos_planeados} <Typography component="span" variant="caption" sx={{ color: TEXTO_TENUE }}>
                        / {f.panel}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{f.vistas}</TableCell>
                    <TableCell align="right">{f.revisitas}</TableCell>
                    <TableCell>{fechaLocal(f.fecha_estado)}</TableCell>
                    <TableCell align="right">
                      <Button size="small" variant={f.estado === 'ENVIADA' ? 'contained' : 'text'}
                              onClick={() => setAbierta(f)} sx={{ textTransform: 'none' }}>
                        {f.estado === 'ENVIADA' ? 'Revisar' : 'Ver'}
                      </Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        )}
      </Card>

      <Dialog open={!!abierta} onClose={cerrar} maxWidth="md" fullWidth>
        <DialogTitle sx={{ pb: 0.5 }}>
          {abierta?.codigo} · {abierta?.nombre}
          <Box sx={{ mt: 0.5 }}>{abierta && <ChipEstado fila={abierta} />}</Box>
        </DialogTitle>
        <DialogContent dividers>
          {cargandoDetalle || !detalle ? <Box sx={{ p: 3, textAlign: 'center' }}><CircularProgress /></Box> : (
            <>
              <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 1 }}>
                {detalle.medicos.length} médicos planeados de {detalle.medicos.length + detalle.sin_planear.length} del
                panel · {detalle.medicos.filter((m) => m.semana_r).length} con revisita.
              </Typography>
              <Box sx={{ overflowX: 'auto', mb: 2 }}>
                <Table size="small">
                  <TableHead>
                    <TableRow sx={{ '& th': { fontWeight: 700 } }}>
                      <TableCell>Médico</TableCell>
                      <TableCell>Cat.</TableCell>
                      <TableCell>Especialidad</TableCell>
                      <TableCell>Vista</TableCell>
                      <TableCell>Revisita</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {detalle.medicos.map((m) => (
                      <TableRow key={m.medico_id}>
                        <TableCell>
                          {m.top && <Star fontSize="inherit" color="warning" titleAccess="Médico TOP" sx={{ mr: 0.5, verticalAlign: 'middle' }} />}
                          {m.nombre}
                        </TableCell>
                        <TableCell>{m.categoria ?? '—'}</TableCell>
                        <TableCell>{m.especialidad ?? '—'}</TableCell>
                        <TableCell>{semanaTxt(m.semana_v, m.dia_v)}</TableCell>
                        <TableCell>{semanaTxt(m.semana_r, m.dia_r)}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
              {detalle.sin_planear.length > 0 && (
                <Alert severity={detalle.sin_planear.some((m) => m.top) ? 'warning' : 'info'}>
                  <b>{detalle.sin_planear.length} médico{detalle.sin_planear.length === 1 ? '' : 's'} del panel sin planear:</b>{' '}
                  {detalle.sin_planear.slice(0, 30).map((m) => `${m.top ? '★ ' : ''}${m.nombre}${m.categoria ? ` (${m.categoria})` : ''}`).join(', ')}
                  {detalle.sin_planear.length > 30 ? ` y ${detalle.sin_planear.length - 30} más` : ''}
                </Alert>
              )}
              {devolviendo && (
                <TextField fullWidth autoFocus multiline minRows={2} sx={{ mt: 2 }}
                           label="¿Qué debe corregir? *" value={motivo} inputProps={{ maxLength: 300 }}
                           onChange={(e) => setMotivo(e.target.value)}
                           placeholder="Ej: falta la revisita de los médicos categoría A" />
              )}
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={cerrar}>Cerrar</Button>
          {abierta?.estado === 'ENVIADA' && (devolviendo ? (
            <Button color="warning" variant="contained" startIcon={<Undo />}
                    disabled={ocupado || !motivo.trim()} onClick={() => decidir('devolver')}>
              Devolver con observaciones
            </Button>
          ) : (
            <>
              <Button color="warning" startIcon={<Undo />} disabled={ocupado} onClick={() => setDevolviendo(true)}>
                Devolver
              </Button>
              <Button color="success" variant="contained" startIcon={<CheckCircle />}
                      disabled={ocupado || !detalle} onClick={() => decidir('aprobar')}>
                Aprobar
              </Button>
            </>
          ))}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
