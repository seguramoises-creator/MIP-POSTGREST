import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Stack, Chip, Alert, Grid,
  CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, Divider,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { Warning, ErrorOutline, ReportProblem, LockClock, HistoryToggleOff } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import {
  estadoRuptura, previsualizarCierre, cerrarCiclo, historialCierres,
  type RupturaEstado, type RupturaMedico, type CierrePreview, type CierreHist,
} from '../../services/visita.service';

const CAT_COLOR: Record<string, 'success' | 'primary' | 'warning'> = { A: 'success', B: 'primary', C: 'warning' };

function errMsg(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: { mensaje?: string } | string } } })?.response?.data?.detail;
  if (d && typeof d === 'object' && d.mensaje) return d.mensaje;
  if (typeof d === 'string') return d;
  return fallback;
}

const SEVERIDADES: { key: 'critica' | 'grave' | 'alerta'; label: string; color: 'error' | 'warning'; icon: React.ReactNode; ayuda: string }[] = [
  { key: 'critica', label: 'Ruptura crítica (≥3 ciclos)', color: 'error', icon: <ReportProblem />, ayuda: 'Riesgo real de pérdida del médico. Priorizar recuperación.' },
  { key: 'grave', label: 'Grave (2 ciclos)', color: 'warning', icon: <ErrorOutline />, ayuda: 'Dos ciclos sin visita. Reprogramar cuanto antes.' },
  { key: 'alerta', label: 'Alerta (1 ciclo)', color: 'warning', icon: <Warning />, ayuda: 'Un ciclo sin visita. Vigilar en la planeación.' },
];

export default function RupturaVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esGestor = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD';
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);

  const [estado, setEstado] = useState<RupturaEstado | null>(null);
  const [preview, setPreview] = useState<CierrePreview | null>(null);
  const [hist, setHist] = useState<CierreHist[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error' | 'info'; texto: string } | null>(null);
  const [confirmar, setConfirmar] = useState(false);
  const [cerrando, setCerrando] = useState(false);

  const cargar = useCallback(() => {
    setCargando(true);
    const tareas: Promise<unknown>[] = [estadoRuptura().then(setEstado).catch(() => setEstado(null))];
    if (esGestor) {
      tareas.push(previsualizarCierre().then(setPreview).catch(() => setPreview(null)));
      tareas.push(historialCierres().then(setHist).catch(() => setHist([])));
    }
    Promise.all(tareas).finally(() => setCargando(false));
  }, [esGestor]);
  useEffect(() => { cargar(); }, [cargar]);

  async function confirmarCierre() {
    setCerrando(true); setMsg(null);
    try {
      const r = await cerrarCiclo();
      setMsg({ tipo: 'success', texto: `Ciclo cerrado: ${r.visitados} visitados, ${r.sin_visitar} sin visita (${r.ruptura_critica} en ruptura crítica).` });
      setConfirmar(false); cargar();
    } catch (e) {
      setMsg({ tipo: 'error', texto: errMsg(e, 'No se pudo cerrar el ciclo.') });
      setConfirmar(false);
    } finally { setCerrando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const listaSev = (medicos: RupturaMedico[], color: 'error' | 'warning') => (
    medicos.length === 0 ? (
      <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>Sin médicos en este nivel.</Typography>
    ) : (
      <Table size="small">
        <TableHead><TableRow>
          <TableCell>Médico</TableCell><TableCell align="center">Cat.</TableCell>
          {esGestor && <TableCell>Visitador</TableCell>}
          <TableCell align="center">Ciclos sin visita</TableCell>
        </TableRow></TableHead>
        <TableBody>
          {medicos.map((m) => (
            <TableRow key={m.id} hover>
              <TableCell>{m.nombre}</TableCell>
              <TableCell align="center"><Chip size="small" label={m.categoria} color={CAT_COLOR[m.categoria] ?? 'default'} /></TableCell>
              {esGestor && <TableCell>{m.vm_nombre}</TableCell>}
              <TableCell align="center"><Chip size="small" color={color} label={m.ciclos_sin_visita} /></TableCell>
            </TableRow>
          ))}
        </TableBody>
      </Table>
    )
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <ReportProblem color="error" />
        <Typography variant="h5" fontWeight={700}>Ruptura de Secuencia</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Médicos que acumulan ciclos sin visita. La cuenta avanza al cerrar cada ciclo.
      </Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Grid container spacing={2} sx={{ mb: 2 }}>
        {SEVERIDADES.map((s) => (
          <Grid item xs={12} sm={4} key={s.key}>
            <Card variant="outlined" sx={{ borderColor: `${s.color}.main` }}>
              <CardContent sx={{ py: 1.5 }}>
                <Stack direction="row" alignItems="center" spacing={1}>
                  <Box sx={{ color: `${s.color}.main`, display: 'flex' }}>{s.icon}</Box>
                  <Box>
                    <Typography variant="h5" fontWeight={700}>{estado ? estado[s.key] : 0}</Typography>
                    <Typography variant="caption" color="text.secondary">{s.label}</Typography>
                  </Box>
                </Stack>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {estado && estado.total === 0 && <Alert severity="success" sx={{ mb: 2 }}>No hay médicos en ruptura. 🎯</Alert>}

      {estado && SEVERIDADES.map((s) => (
        (estado[s.key] > 0) && (
          <Card variant="outlined" sx={{ mb: 2 }} key={s.key}>
            <CardContent>
              <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
                <Box sx={{ color: `${s.color}.main`, display: 'flex' }}>{s.icon}</Box>
                <Typography variant="subtitle1" fontWeight={700}>{s.label}</Typography>
              </Stack>
              <Typography variant="caption" color="text.secondary">{s.ayuda}</Typography>
              <Box sx={{ mt: 1, overflowX: 'auto' }}>{listaSev(estado.medicos[s.key], s.color)}</Box>
            </CardContent>
          </Card>
        )
      ))}

      {/* Cierre de ciclo — solo gestión (ADMIN / Gerente de Productividad). */}
      {esGestor && (
        <>
          <Divider sx={{ my: 3 }} />
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <LockClock color="primary" />
            <Typography variant="h6" fontWeight={700}>Cierre de Ciclo de Visita</Typography>
          </Stack>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Hace rodar el contador de ruptura: resetea a los médicos visitados e incrementa a los ausentes.
            Solo puede hacerse una vez por ciclo.
          </Typography>

          {esSoloLectura && (
            <Alert severity="info" sx={{ mb: 2 }}>
              Ciclo en solo lectura — el registro de visitas solo está disponible en el ciclo abierto.
            </Alert>
          )}

          {preview && (
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Grid container spacing={2}>
                  <Grid item xs={6} sm={3}><Typography variant="caption" color="text.secondary">Panel</Typography><Typography variant="h6" fontWeight={700}>{preview.panel}</Typography></Grid>
                  <Grid item xs={6} sm={3}><Typography variant="caption" color="text.secondary">Se resetean (visitados)</Typography><Typography variant="h6" fontWeight={700} color="success.main">{preview.visitados}</Typography></Grid>
                  <Grid item xs={6} sm={3}><Typography variant="caption" color="text.secondary">Incrementan (sin visita)</Typography><Typography variant="h6" fontWeight={700} color="warning.main">{preview.sin_visitar}</Typography></Grid>
                  <Grid item xs={6} sm={3}><Typography variant="caption" color="text.secondary">Quedan en crítica</Typography><Typography variant="h6" fontWeight={700} color="error.main">{preview.ruptura_critica}</Typography></Grid>
                </Grid>
                <Box sx={{ mt: 2 }}>
                  {preview.ya_cerrado ? (
                    <Alert severity="info">
                      Este ciclo ya fue cerrado{preview.fecha_cierre ? ` el ${new Date(preview.fecha_cierre).toLocaleString()}` : ''}. No puede cerrarse de nuevo.
                    </Alert>
                  ) : (
                    <Button variant="contained" color="primary" startIcon={<LockClock />} disabled={esSoloLectura} onClick={() => setConfirmar(true)}>
                      Cerrar ciclo ahora
                    </Button>
                  )}
                </Box>
              </CardContent>
            </Card>
          )}

          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
            <HistoryToggleOff fontSize="small" color="action" />
            <Typography variant="subtitle1" fontWeight={700}>Historial de cierres</Typography>
          </Stack>
          {hist.length === 0 ? (
            <Alert severity="info">Aún no se ha cerrado ningún ciclo.</Alert>
          ) : (
            <Card variant="outlined">
              <Box sx={{ overflowX: 'auto' }}>
                <Table size="small">
                  <TableHead><TableRow>
                    <TableCell>Ciclo</TableCell><TableCell>Fecha</TableCell>
                    <TableCell align="center">Panel</TableCell><TableCell align="center">Visitados</TableCell>
                    <TableCell align="center">Sin visita</TableCell><TableCell align="center">Crítica</TableCell>
                  </TableRow></TableHead>
                  <TableBody>
                    {hist.map((h) => (
                      <TableRow key={h.id} hover>
                        <TableCell>{h.ciclo_nombre}</TableCell>
                        <TableCell>{h.fecha_cierre ? new Date(h.fecha_cierre).toLocaleDateString() : '—'}</TableCell>
                        <TableCell align="center">{h.panel}</TableCell>
                        <TableCell align="center" style={{ color: 'green' }}>{h.visitados}</TableCell>
                        <TableCell align="center">{h.sin_visitar}</TableCell>
                        <TableCell align="center"><Chip size="small" color="error" label={h.ruptura_critica} /></TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Card>
          )}
        </>
      )}

      <Dialog open={confirmar} onClose={() => setConfirmar(false)}>
        <DialogTitle>Confirmar cierre de ciclo</DialogTitle>
        <DialogContent>
          <Typography variant="body2">
            Vas a cerrar el ciclo de visita. Esto actualizará el contador de ruptura de todos los médicos
            y no puede deshacerse. ¿Continuar?
          </Typography>
          {preview && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              {preview.sin_visitar} médico(s) sin visita incrementarán su contador; {preview.ruptura_critica} quedarán en ruptura crítica.
            </Alert>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmar(false)} disabled={cerrando}>Cancelar</Button>
          <Button variant="contained" color="primary" onClick={confirmarCierre} disabled={cerrando || esSoloLectura}>
            {cerrando ? 'Cerrando…' : 'Sí, cerrar ciclo'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
