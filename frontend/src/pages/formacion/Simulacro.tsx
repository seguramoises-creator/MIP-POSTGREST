/**
 * Simulacro.tsx — Simulacro de Venta con IA (§9).
 * Sesión guiada por rondas: el médico simulado plantea una objeción (hablada por
 * TTS del backend o Web Speech del navegador), el RM elige la respuesta, se revela
 * correcto/incorrecto + retro, y al final el resultado D/P/A/E por fase.
 */
import { useState } from 'react';
import { useMutation, useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Button, Stack, Alert, Chip, Divider,
  CircularProgress, LinearProgress, Table, TableBody, TableCell, TableHead, TableRow,
} from '@mui/material';
import { RecordVoiceOver, VolumeUp } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  iniciarSimulacro, responderRonda, finalizarSimulacro, vozRonda,
  misSesionesSimulacro, resumenSimulacro, detalleSimulacro,
  type SimulacroIniciado, type RondaSimulacro, type ResultadoSimulacro,
} from '../../services/formacion.service';

const DPAE: Record<number, { label: string; color: string }> = {
  4: { label: 'Excelente (E)', color: '#2e7d32' }, 3: { label: 'Adecuado (A)', color: '#584F46' },
  2: { label: 'En proceso (P)', color: '#e65100' }, 1: { label: 'Deficiente (D)', color: '#c62828' },
};

function hablarNavegador(texto: string) {
  try {
    const u = new SpeechSynthesisUtterance(texto);
    u.lang = 'es-DO';
    window.speechSynthesis.cancel();
    window.speechSynthesis.speak(u);
  } catch { /* sin Web Speech: el texto igual se ve en pantalla */ }
}

export default function Simulacro() {
  const [sesion, setSesion] = useState<SimulacroIniciado | null>(null);
  const [idx, setIdx] = useState(0);
  const [feedback, setFeedback] = useState<{ correcta: string; retro: string; acerto: boolean } | null>(null);
  const [resultado, setResultado] = useState<ResultadoSimulacro | null>(null);
  const [seleccion, setSeleccion] = useState<string | null>(null);

  const iniciar = useMutation({
    mutationFn: () => iniciarSimulacro(),
    onSuccess: (d) => {
      setSesion(d); setIdx(0); setFeedback(null); setResultado(null); setSeleccion(null);
      reproducir(d.rondas[0]);
    },
  });
  const responder = useMutation({
    mutationFn: (v: { rondaId: number; opcion: string }) => responderRonda(v.rondaId, v.opcion),
    onSuccess: (r) => setFeedback({ correcta: r.opcion_correcta, retro: r.retroalimentacion, acerto: r.es_correcta }),
  });
  const finalizar = useMutation({
    mutationFn: (sid: number) => finalizarSimulacro(sid),
    onSuccess: (r) => setResultado(r),
  });
  const abrir = useMutation({
    mutationFn: (id: number) => detalleSimulacro(id),
    onSuccess: (d) => {
      // Finalizada: el detalle trae el resultado → pantalla de resultado.
      if (d.resultado) {
        setResultado(d.resultado);
        return;
      }
      // En curso: hidratar y caer en la primera ronda pendiente.
      const pendiente = d.rondas.findIndex((r) => r.opcion_seleccionada === null);
      if (pendiente === -1) {
        // Todas respondidas pero sin finalizar: cerrar la práctica directo.
        finalizar.mutate(d.sesion.id);
        return;
      }
      setSesion({ sesion: d.sesion, rondas: d.rondas });
      setIdx(pendiente);
      setFeedback(null);
      setSeleccion(null);
      reproducir(d.rondas[pendiente]);
    },
  });

  async function reproducir(ronda: RondaSimulacro) {
    try {
      const v = await vozRonda(ronda.id);
      if (v.en_navegador && v.texto) hablarNavegador(v.texto);
    } catch { hablarNavegador(ronda.objecion_texto); }
  }

  const ronda = sesion?.rondas[idx];
  const esUltima = sesion ? idx === sesion.rondas.length - 1 : false;

  function siguiente() {
    if (!sesion) return;
    if (esUltima) { finalizar.mutate(sesion.sesion.id); return; }
    const n = idx + 1;
    setIdx(n); setFeedback(null); setSeleccion(null); reproducir(sesion.rondas[n]);
  }

  // --- Pantalla de resultado ---
  if (resultado) {
    return (
      <Box sx={{ p: 3, maxWidth: 640, mx: 'auto' }}>
        <Typography variant="h5" fontWeight={800} mb={2}>Resultado de la práctica</Typography>
        {(['apertura', 'desarrollo', 'cierre'] as const).map((f) => {
          const v = resultado[f]; const info = DPAE[v];
          return (
            <Card key={f} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1 }}>
              <CardContent sx={{ py: 1.25, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                <Typography sx={{ textTransform: 'capitalize' }}>{f}</Typography>
                <Chip label={info.label} sx={{ bgcolor: info.color, color: '#fff', fontWeight: 700 }} />
              </CardContent>
            </Card>
          );
        })}
        <Alert severity="info" sx={{ my: 2 }}>Calificación general: <strong>{resultado.general}</strong> / 4</Alert>
        <Button variant="contained" startIcon={<RecordVoiceOver />} onClick={() => iniciar.mutate()}>
          Nueva práctica
        </Button>
      </Box>
    );
  }

  // --- Pantalla de inicio (con historial del RM / resumen del equipo) ---
  if (!sesion) {
    return <PantallaInicio iniciar={iniciar} abrir={abrir} />;
  }

  // --- Pantalla de ronda ---
  return (
    <Box sx={{ p: 3, maxWidth: 640, mx: 'auto' }}>
      <Stack direction="row" spacing={1} alignItems="center" mb={1}>
        <Chip color="primary" label={ronda!.fase_more} />
        {ronda!.tecnica_objecion && <Chip variant="outlined" label={ronda!.tecnica_objecion} />}
        <Box sx={{ flex: 1 }} />
        <Typography variant="caption" color="text.secondary">
          {sesion.sesion.medico} · {sesion.sesion.estilo}
        </Typography>
      </Stack>
      <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
        <CardContent>
          <Stack direction="row" spacing={1} alignItems="center">
            <Typography variant="body1" sx={{ flex: 1 }}>«{ronda!.objecion_texto}»</Typography>
            <Button size="small" startIcon={<VolumeUp />} onClick={() => reproducir(ronda!)}>Escuchar</Button>
          </Stack>
        </CardContent>
      </Card>

      <Stack spacing={1}>
        {Object.entries(ronda!.opciones).map(([k, v]) => {
          const elegido = feedback && k === seleccion;
          const esCorrecta = feedback && k === feedback.correcta;
          const color = feedback
            ? (esCorrecta ? 'success' : (elegido ? 'error' : 'inherit'))
            : 'primary';
          return (
            <Button key={k} fullWidth variant={feedback ? 'outlined' : 'contained'} color={color as any}
              disabled={!!feedback || responder.isPending}
              onClick={() => { setSeleccion(k); responder.mutate({ rondaId: ronda!.id, opcion: k }); }}
              sx={{ justifyContent: 'flex-start', textTransform: 'none' }}>
              <strong style={{ marginRight: 8 }}>{k}.</strong> {v}
            </Button>
          );
        })}
      </Stack>

      {feedback && (
        <>
          <Alert severity={feedback.acerto ? 'success' : 'error'} sx={{ mt: 2 }}>
            {feedback.acerto ? '¡Correcto!' : `La mejor opción era la ${feedback.correcta}.`} {feedback.retro}
          </Alert>
          <Divider sx={{ my: 2 }} />
          <Button variant="contained" onClick={siguiente} disabled={finalizar.isPending}>
            {esUltima ? 'Ver resultado' : 'Siguiente'}
          </Button>
        </>
      )}
      {responder.isPending && <CircularProgress size={20} sx={{ mt: 2 }} />}
    </Box>
  );
}

// Pantalla de arranque: botón "Nueva práctica" + historial (RM) o resumen (roles
// gerenciales). Reutiliza los endpoints /mis-sesiones y /resumen ya existentes.
function PantallaInicio({ iniciar, abrir }: {
  iniciar: { isPending: boolean; isError: boolean; mutate: () => void };
  abrir: { isPending: boolean; isError: boolean; variables?: number; mutate: (id: number) => void; reset: () => void };
}) {
  const rol = useAuthStore((s) => s.rol);
  const esRM = rol === 'REPRESENTANTE_MEDICO';
  const historial = useQuery({ queryKey: ['sim-mis-sesiones'], queryFn: misSesionesSimulacro, enabled: esRM });
  const resumen = useQuery({ queryKey: ['sim-resumen'], queryFn: resumenSimulacro, enabled: !esRM });

  return (
    <Box sx={{ p: 3, maxWidth: 720, mx: 'auto' }}>
      <Box sx={{ textAlign: 'center' }}>
        <Typography variant="h5" fontWeight={800}>Simulacro de Venta</Typography>
        <Typography color="text.secondary" mb={3}>
          Practica el manejo de objeciones contra un médico simulado por IA, con el modelo MORE.
        </Typography>
        {iniciar.isError && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            No se pudo iniciar. Verifica que haya una conexión de IA de texto activa en Conexiones de IA.
          </Alert>
        )}
        <Button variant="contained" size="large" startIcon={<RecordVoiceOver />}
          disabled={iniciar.isPending} onClick={() => { abrir.reset(); iniciar.mutate(); }}>
          {iniciar.isPending ? 'Generando escenario…' : 'Nueva práctica'}
        </Button>
        {iniciar.isPending && <LinearProgress sx={{ mt: 2 }} />}
      </Box>

      {esRM ? (
        <Box sx={{ mt: 4 }}>
          {abrir.isError && (
            <Alert severity="warning" sx={{ mb: 2 }}>No se pudo abrir la práctica.</Alert>
          )}
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Mis prácticas</Typography>
          {(historial.data || []).length === 0 ? (
            <Typography color="text.secondary" variant="body2">Aún no has practicado.</Typography>
          ) : (historial.data || []).map((s) => {
            const abriendoEsta = abrir.isPending && abrir.variables === s.id;
            return (
              <Card key={s.id} elevation={0} role="button" tabIndex={0}
                onClick={() => { if (!abrir.isPending) abrir.mutate(s.id); }}
                onKeyDown={(e) => {
                  if ((e.key === 'Enter' || e.key === ' ') && !abrir.isPending) {
                    e.preventDefault();
                    abrir.mutate(s.id);
                  }
                }}
                sx={{
                  border: '1px solid #e0e7ef', borderRadius: 2, mb: 1,
                  cursor: abrir.isPending ? 'default' : 'pointer',
                  opacity: abrir.isPending && !abriendoEsta ? 0.6 : 1,
                  '&:hover': { borderColor: abrir.isPending ? '#e0e7ef' : '#90a4c4' },
                }}>
                <CardContent sx={{ py: 1, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <span>{s.medico} · {s.estilo}</span>
                  <Stack direction="row" spacing={1} alignItems="center">
                    {abriendoEsta && <CircularProgress size={16} />}
                    <Chip size="small" label={s.finalizada ? 'Finalizada' : 'En curso'}
                      color={s.finalizada ? 'success' : 'default'} />
                  </Stack>
                </CardContent>
              </Card>
            );
          })}
        </Box>
      ) : (
        <Box sx={{ mt: 4 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Resumen del equipo</Typography>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>RM</TableCell>
                <TableCell align="right">Prácticas</TableCell>
                <TableCell align="right">Última general</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(resumen.data || []).map((r) => (
                <TableRow key={r.rm_id}>
                  <TableCell>RM #{r.rm_id}</TableCell>
                  <TableCell align="right">{r.practicas}</TableCell>
                  <TableCell align="right">{r.ultima_general ?? '—'}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Box>
      )}
    </Box>
  );
}
