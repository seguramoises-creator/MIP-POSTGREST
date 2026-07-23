/**
 * BandejaAprobacionFarmacias.tsx — Bandeja del Gerente de Distrito: altas de
 * farmacia pendientes (Acción A/B del VM). Aprobar / Rechazar (motivo obligatorio) /
 * Editar y aprobar. Espejo de la bandeja de aprobación de PanelMedico.tsx, en
 * pantalla propia (web responsive) — Tarea 8 del plan `2026-07-22-modulo-farmacias.md`.
 */
import { useCallback, useEffect, useState } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  CircularProgress, Divider, Dialog, DialogTitle, DialogContent, DialogActions, Grid,
} from '@mui/material';
import { HowToReg, ThumbUp, ThumbDown, Edit, Warning } from '@mui/icons-material';
import {
  aprobacionPendientesFarmacias, aprobarFarmacia, rechazarFarmacia, editarYAprobarFarmacia,
  type FarmaciaPendiente, type FarmaciaEditarAprobar,
} from '../../services/farmacias.service';

function mensajeError(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data ?? {};
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  return fallback;
}

const TIPO: Record<string, { label: string; color: 'success' | 'info' }> = {
  NUEVA: { label: 'Farmacia nueva', color: 'success' },
  AGREGAR: { label: 'Del maestro', color: 'info' },
};

export default function BandejaAprobacionFarmacias() {
  const [pendientes, setPendientes] = useState<FarmaciaPendiente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [procesando, setProcesando] = useState<number | null>(null);

  // Rechazo (motivo obligatorio)
  const [rechazando, setRechazando] = useState<FarmaciaPendiente | null>(null);
  const [motivo, setMotivo] = useState('');

  // Editar y aprobar
  const [editando, setEditando] = useState<FarmaciaPendiente | null>(null);
  const [cambios, setCambios] = useState<FarmaciaEditarAprobar>({});

  const cargar = useCallback(() => {
    setCargando(true);
    aprobacionPendientesFarmacias().then(setPendientes).catch(() => setPendientes([])).finally(() => setCargando(false));
  }, []);
  useEffect(() => { cargar(); }, [cargar]);

  async function aprobar(p: FarmaciaPendiente) {
    setProcesando(p.id); setMsg(null);
    try {
      await aprobarFarmacia(p.id);
      setMsg({ tipo: 'success', texto: `${p.nombre_completo ?? 'Farmacia'} aprobada.` });
      cargar();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo aprobar.') });
    } finally { setProcesando(null); }
  }

  function abrirRechazo(p: FarmaciaPendiente) { setRechazando(p); setMotivo(''); }
  async function confirmarRechazo() {
    if (!rechazando || !motivo.trim()) return;
    setProcesando(rechazando.id); setMsg(null);
    try {
      await rechazarFarmacia(rechazando.id, motivo.trim());
      setMsg({ tipo: 'success', texto: 'Solicitud rechazada.' });
      setRechazando(null); cargar();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo rechazar.') });
    } finally { setProcesando(null); }
  }

  function abrirEditar(p: FarmaciaPendiente) {
    setEditando(p);
    setCambios({ direccion: p.direccion ?? '', encargado: p.encargado ?? '' });
  }
  async function confirmarEditarAprobar() {
    if (!editando) return;
    if (!cambios.direccion?.trim() || !cambios.encargado?.trim()) {
      setMsg({ tipo: 'error', texto: 'Dirección y encargado son obligatorios.' }); return;
    }
    setProcesando(editando.id); setMsg(null);
    try {
      await editarYAprobarFarmacia(editando.id, cambios);
      setMsg({ tipo: 'success', texto: `${editando.nombre_completo ?? 'Farmacia'} corregida y aprobada.` });
      setEditando(null); cargar();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo guardar.') });
    } finally { setProcesando(null); }
  }

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Box sx={{ mb: 2 }}>
        <Typography variant="h5" fontWeight={700}>Aprobación de Farmacias</Typography>
        <Typography variant="body2" color="text.secondary">
          Altas de farmacia solicitadas por los visitadores de tu distrito
        </Typography>
      </Box>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Card variant="outlined">
        {cargando ? (
          <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
        ) : pendientes.length === 0 ? (
          <Alert severity="info" sx={{ m: 2 }}>No hay solicitudes pendientes.</Alert>
        ) : (
          <CardContent sx={{ py: 1 }}>
            <Stack divider={<Divider />}>
              {pendientes.map((p) => {
                const tipo = TIPO[p.tipo_solicitud] ?? { label: p.tipo_solicitud, color: 'info' as const };
                return (
                  <Stack key={p.id} direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} spacing={1.5} sx={{ py: 1.5 }}>
                    <Chip size="small" color={tipo.color} label={tipo.label} sx={{ alignSelf: 'flex-start' }} />
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight={700} noWrap>{p.nombre_completo ?? '—'}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                        {[p.direccion, p.encargado ? `Encargado: ${p.encargado}` : null,
                          `VM: ${p.vm_nombre}`,
                          p.fecha_solicitud ? new Date(p.fecha_solicitud).toLocaleDateString() : null]
                          .filter(Boolean).join(' · ')}
                      </Typography>
                      {/* Alerta de posible duplicado — solo se pinta si el backend la trae */}
                      {p.posible_duplicado && p.posible_duplicado.length > 0 && (
                        <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                          <Warning fontSize="small" color="warning" />
                          <Typography variant="caption" color="warning.dark">
                            Posible duplicado: {p.posible_duplicado.map((d) => d.nombre_completo).join(', ')}
                          </Typography>
                        </Stack>
                      )}
                    </Box>
                    <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                      <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />}
                              disabled={procesando === p.id} onClick={() => aprobar(p)}>Aprobar</Button>
                      <Button size="small" variant="outlined" startIcon={<Edit />}
                              disabled={procesando === p.id} onClick={() => abrirEditar(p)}>Editar y aprobar</Button>
                      <Button size="small" variant="outlined" color="error" startIcon={<ThumbDown />}
                              disabled={procesando === p.id} onClick={() => abrirRechazo(p)}>Rechazar</Button>
                    </Stack>
                  </Stack>
                );
              })}
            </Stack>
          </CardContent>
        )}
      </Card>

      {/* Rechazar — motivo obligatorio */}
      <Dialog open={!!rechazando} onClose={() => setRechazando(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Rechazar solicitud</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>{rechazando?.nombre_completo}</Typography>
          <TextField fullWidth multiline minRows={2} required label="Motivo del rechazo" value={motivo}
                     error={!motivo.trim()}
                     helperText={!motivo.trim() ? 'El motivo es obligatorio.' : ' '}
                     onChange={(e) => setMotivo(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRechazando(null)}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={!motivo.trim() || procesando === rechazando?.id}
                  onClick={confirmarRechazo}>
            {procesando === rechazando?.id ? 'Rechazando…' : 'Rechazar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Editar y aprobar */}
      <Dialog open={!!editando} onClose={() => setEditando(null)} maxWidth="sm" fullWidth>
        <DialogTitle><HowToReg sx={{ verticalAlign: 'middle', mr: 1 }} />Corregir y aprobar</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>{editando?.nombre_completo}</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Dirección" value={cambios.direccion ?? ''}
                         error={!cambios.direccion?.trim()}
                         onChange={(e) => setCambios((c) => ({ ...c, direccion: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Encargado" value={cambios.encargado ?? ''}
                         error={!cambios.encargado?.trim()}
                         onChange={(e) => setCambios((c) => ({ ...c, encargado: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Teléfono" value={cambios.telefono ?? ''}
                         onChange={(e) => setCambios((c) => ({ ...c, telefono: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Email" value={cambios.email ?? ''}
                         onChange={(e) => setCambios((c) => ({ ...c, email: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditando(null)}>Cancelar</Button>
          <Button variant="contained" color="success"
                  disabled={!cambios.direccion?.trim() || !cambios.encargado?.trim() || procesando === editando?.id}
                  onClick={confirmarEditarAprobar}>
            {procesando === editando?.id ? 'Guardando…' : 'Guardar y aprobar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
