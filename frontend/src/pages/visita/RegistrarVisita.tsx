import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, ToggleButton, ToggleButtonGroup, Divider, CircularProgress,
} from '@mui/material';
import { CheckCircle, Cancel, Save, EventBusy } from '@mui/icons-material';
import {
  listarMedicos, listarCausas, misVisitasHoy, registrarVisita, registrarNoVisita,
  type MedicoVisita, type VisitaHoy,
} from '../../services/visita.service';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

export default function RegistrarVisita() {
  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [causas, setCausas] = useState<string[]>([]);
  const [hoy, setHoy] = useState<VisitaHoy[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [medicoId, setMedicoId] = useState<number | ''>('');
  const [tipo, setTipo] = useState<'V' | 'R'>('V');
  const [comentario, setComentario] = useState('');
  const [haceMin, setHaceMin] = useState('0');
  const [modoNoVisita, setModoNoVisita] = useState(false);
  const [causa, setCausa] = useState('');
  const [guardando, setGuardando] = useState(false);

  const cargarFeed = useCallback(() => { misVisitasHoy().then(setHoy).catch(() => setHoy([])); }, []);
  useEffect(() => {
    Promise.all([listarMedicos(), listarCausas(), misVisitasHoy()])
      .then(([m, c, h]) => { setMedicos(m); setCausas(c); setHoy(h); })
      .catch(() => {}).finally(() => setCargando(false));
  }, []);

  const limpiar = () => { setMedicoId(''); setTipo('V'); setComentario(''); setHaceMin('0'); setModoNoVisita(false); setCausa(''); };

  async function guardar() {
    if (!medicoId) { setMsg({ tipo: 'error', texto: 'Selecciona el médico.' }); return; }
    setGuardando(true); setMsg(null);
    try {
      if (modoNoVisita) {
        if (!causa) { setMsg({ tipo: 'error', texto: 'Selecciona la causa.' }); setGuardando(false); return; }
        await registrarNoVisita(Number(medicoId), causa, comentario || undefined);
        setMsg({ tipo: 'success', texto: 'No-visita registrada.' });
      } else {
        await registrarVisita(Number(medicoId), tipo, comentario, Number(haceMin) || 0);
        setMsg({ tipo: 'success', texto: 'Visita registrada.' });
      }
      limpiar(); cargarFeed();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo registrar.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Registrar Visita</Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack spacing={2}>
            <TextField select label="Médico visitado" value={medicoId} required
                       onChange={(e) => setMedicoId(e.target.value === '' ? '' : Number(e.target.value))}>
              {medicos.length === 0 && <MenuItem value="" disabled>No hay médicos en tu panel</MenuItem>}
              {medicos.map((m) => <MenuItem key={m.id} value={m.id}>{m.nombre_completo} · Cat. {m.categoria}</MenuItem>)}
            </TextField>

            {!modoNoVisita ? (
              <>
                <Box>
                  <Typography variant="caption" color="text.secondary">Tipo de visita</Typography>
                  <ToggleButtonGroup exclusive fullWidth value={tipo} onChange={(_, v) => v && setTipo(v)} sx={{ mt: 0.5 }}>
                    <ToggleButton value="V" color="primary">Vista</ToggleButton>
                    <ToggleButton value="R" color="secondary">Revisita</ToggleButton>
                  </ToggleButtonGroup>
                </Box>
                <TextField label="Comentario de la visita (mín. 10, no genérico)" multiline minRows={3}
                           value={comentario} onChange={(e) => setComentario(e.target.value)}
                           helperText='Ej: "MEDICO PREGUNTO POR INTERACCION CON METFORMINA"' />
                <TextField select label="¿Hace cuánto ocurrió?" value={haceMin} sx={{ maxWidth: 220 }}
                           onChange={(e) => setHaceMin(e.target.value)} helperText="Ventana máx. 60 min">
                  {['0', '10', '20', '30', '45', '60'].map((n) => (
                    <MenuItem key={n} value={n}>{n === '0' ? 'Ahora' : `Hace ${n} min`}</MenuItem>
                  ))}
                </TextField>
              </>
            ) : (
              <>
                <TextField select label="Causa de no-visita" value={causa} required
                           onChange={(e) => setCausa(e.target.value)}>
                  {causas.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                </TextField>
                <TextField label="Nota (opcional)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
              </>
            )}

            <Stack direction="row" spacing={1.5}>
              <Button variant="contained" fullWidth startIcon={<Save />} disabled={guardando} onClick={guardar}>
                {guardando ? 'Guardando…' : (modoNoVisita ? 'Registrar no-visita' : 'Guardar visita')}
              </Button>
              <Button variant="outlined" color={modoNoVisita ? 'primary' : 'warning'} startIcon={<EventBusy />}
                      onClick={() => { setModoNoVisita(!modoNoVisita); setMsg(null); }}>
                {modoNoVisita ? 'Fue visita' : 'No pude'}
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>

      <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Visitas de hoy ({hoy.length})</Typography>
      {hoy.length === 0 ? (
        <Alert severity="info">Aún no has registrado visitas hoy.</Alert>
      ) : (
        <Stack spacing={1}>
          {hoy.map((v) => (
            <Card key={v.id} variant="outlined">
              <CardContent sx={{ py: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                {v.ejecutada ? <CheckCircle color="success" /> : <Cancel color="disabled" />}
                <Box sx={{ flex: 1, minWidth: 0 }}>
                  <Typography variant="body2" fontWeight={600}>{v.medico}</Typography>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                    {v.ejecutada ? (v.comentario || '') : `No-visita: ${v.causa_no_visita}`}
                  </Typography>
                </Box>
                <Chip size="small" color={v.ejecutada ? (v.tipo_visita === 'R' ? 'secondary' : 'primary') : 'default'}
                      label={v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : 'No-visita'} />
              </CardContent>
            </Card>
          ))}
        </Stack>
      )}
    </Box>
  );
}
