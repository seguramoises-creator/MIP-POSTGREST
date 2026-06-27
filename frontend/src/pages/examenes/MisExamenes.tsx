import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, LinearProgress, Chip, Stack,
  RadioGroup, FormControlLabel, Radio, Divider, Alert, CircularProgress,
} from '@mui/material';
import { AccessTime, CheckCircle, Cancel, Assignment } from '@mui/icons-material';
import {
  misPendientes, iniciarExamen, responder, entregar,
  type Asignacion, type IntentoIniciado, type ReporteIntento,
} from '../../services/examenes.service';

type Vista = 'lista' | 'tomando' | 'reporte';

const lsKey = (intentoId: number) => `examen_intento_${intentoId}`;

export default function MisExamenes() {
  const [vista, setVista] = useState<Vista>('lista');
  const [pendientes, setPendientes] = useState<Asignacion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [intento, setIntento] = useState<IntentoIniciado | null>(null);
  const [idx, setIdx] = useState(0);
  const [respuestas, setRespuestas] = useState<Record<number, number>>({});
  const [segRestantes, setSegRestantes] = useState<number | null>(null);
  const [reporte, setReporte] = useState<ReporteIntento | null>(null);
  const [enviando, setEnviando] = useState(false);

  const cargarPendientes = useCallback(() => {
    setCargando(true);
    misPendientes()
      .then(setPendientes)
      .catch(() => setError('No se pudieron cargar tus exámenes asignados.'))
      .finally(() => setCargando(false));
  }, []);

  useEffect(() => { cargarPendientes(); }, [cargarPendientes]);

  // Temporizador
  useEffect(() => {
    if (vista !== 'tomando' || segRestantes === null) return;
    if (segRestantes <= 0) { void handleEntregar(); return; }
    const t = setTimeout(() => setSegRestantes((s) => (s === null ? null : s - 1)), 1000);
    return () => clearTimeout(t);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [vista, segRestantes]);

  const totalPreguntas = intento?.preguntas.length ?? 0;
  const respondidas = Object.keys(respuestas).length;
  const progreso = totalPreguntas ? (respondidas / totalPreguntas) * 100 : 0;
  const preguntaActual = intento?.preguntas[idx];

  async function iniciar(examenId: number) {
    setError(null);
    try {
      const data = await iniciarExamen(examenId);
      setIntento(data);
      setIdx(0);
      setReporte(null);
      // restaurar autosave si existe
      const guardado = localStorage.getItem(lsKey(data.intento_id));
      setRespuestas(guardado ? JSON.parse(guardado) : {});
      setSegRestantes(data.tiempo_limite_min ? data.tiempo_limite_min * 60 : null);
      setVista('tomando');
    } catch {
      setError('No se pudo iniciar el examen. Verifica que tengas una asignación pendiente.');
    }
  }

  function elegir(preguntaId: number, indicePresentado: number) {
    if (!intento) return;
    const nuevas = { ...respuestas, [preguntaId]: indicePresentado };
    setRespuestas(nuevas);
    localStorage.setItem(lsKey(intento.intento_id), JSON.stringify(nuevas)); // autosave
    // envío al backend (no bloquea la UI)
    void responder(intento.intento_id, preguntaId, indicePresentado).catch(() => {});
  }

  async function handleEntregar() {
    if (!intento || enviando) return;
    const faltan = totalPreguntas - respondidas;
    if (faltan > 0 && segRestantes !== 0) {
      const ok = window.confirm(`Te faltan ${faltan} pregunta(s) por responder. ¿Entregar de todas formas?`);
      if (!ok) return;
    }
    setEnviando(true);
    try {
      const rep = await entregar(intento.intento_id);
      localStorage.removeItem(lsKey(intento.intento_id));
      setReporte(rep);
      setVista('reporte');
    } catch {
      setError('No se pudo entregar el examen. Intenta de nuevo.');
    } finally {
      setEnviando(false);
    }
  }

  const mmss = useMemo(() => {
    if (segRestantes === null) return null;
    const m = Math.floor(segRestantes / 60), s = segRestantes % 60;
    return `${m}:${s.toString().padStart(2, '0')}`;
  }, [segRestantes]);

  // ── Render ──────────────────────────────────────────────────────────
  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  if (vista === 'lista') {
    return (
      <Box sx={{ maxWidth: 760, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
        <Typography variant="h5" fontWeight={700} gutterBottom>Mis Exámenes</Typography>
        {error && <Alert severity="error" sx={{ mb: 2 }} onClose={() => setError(null)}>{error}</Alert>}
        {pendientes.length === 0 && <Alert severity="info">No tienes exámenes pendientes.</Alert>}
        <Stack spacing={1.5}>
          {pendientes.map((a) => (
            <Card key={a.id} variant="outlined">
              <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                <Assignment color="primary" />
                <Box sx={{ flex: 1, minWidth: 180 }}>
                  <Typography fontWeight={600}>Examen #{a.examen_id}</Typography>
                  <Typography variant="body2" color="text.secondary">
                    {a.fecha_limite ? `Fecha límite: ${a.fecha_limite}` : 'Sin fecha límite'}
                    {a.intentos_max != null && ` · Intentos: ${a.intentos_usados}/${a.intentos_max}`}
                  </Typography>
                </Box>
                <Button variant="contained" size="large" onClick={() => iniciar(a.examen_id)}>
                  Tomar examen
                </Button>
              </CardContent>
            </Card>
          ))}
        </Stack>
      </Box>
    );
  }

  if (vista === 'tomando' && intento && preguntaActual) {
    const elegida = respuestas[preguntaActual.pregunta_id];
    return (
      <Box sx={{ maxWidth: 680, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
        <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1 }}>
          <Typography variant="body2" color="text.secondary">
            Pregunta {idx + 1} de {totalPreguntas}
          </Typography>
          {mmss && (
            <Chip icon={<AccessTime />} label={mmss} color={segRestantes! < 60 ? 'error' : 'default'} />
          )}
        </Box>
        <LinearProgress variant="determinate" value={progreso} sx={{ mb: 2, height: 8, borderRadius: 4 }} />

        <Card variant="outlined">
          <CardContent>
            {preguntaActual.escenario && (
              <Alert severity="info" sx={{ mb: 2 }}>{preguntaActual.escenario}</Alert>
            )}
            <Typography variant="h6" sx={{ mb: 2 }}>{preguntaActual.texto}</Typography>
            <RadioGroup
              value={elegida ?? -1}
              onChange={(e) => elegir(preguntaActual.pregunta_id, Number(e.target.value))}
            >
              {preguntaActual.opciones.map((op) => (
                <FormControlLabel
                  key={op.indice_presentado}
                  value={op.indice_presentado}
                  control={<Radio />}
                  label={op.texto_opcion}
                  sx={{
                    border: '1px solid', borderColor: elegida === op.indice_presentado ? 'primary.main' : 'divider',
                    borderRadius: 2, m: 0.5, px: 1, py: 1.25, alignItems: 'flex-start',
                  }}
                />
              ))}
            </RadioGroup>
          </CardContent>
        </Card>

        <Stack direction="row" spacing={1.5} sx={{ mt: 2 }}>
          <Button variant="outlined" disabled={idx === 0} onClick={() => setIdx((i) => i - 1)} fullWidth>
            Anterior
          </Button>
          {idx < totalPreguntas - 1 ? (
            <Button variant="contained" onClick={() => setIdx((i) => i + 1)} fullWidth>Siguiente</Button>
          ) : (
            <Button variant="contained" color="success" onClick={handleEntregar} disabled={enviando} fullWidth>
              {enviando ? 'Entregando…' : 'Entregar'}
            </Button>
          )}
        </Stack>
      </Box>
    );
  }

  if (vista === 'reporte' && reporte) {
    return (
      <Box sx={{ maxWidth: 720, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent sx={{ textAlign: 'center' }}>
            <Typography variant="h6">{reporte.examen_nombre}</Typography>
            <Typography variant="h2" fontWeight={800} color={reporte.aprobado ? 'success.main' : 'error.main'}>
              {reporte.score}%
            </Typography>
            <Chip
              icon={reporte.aprobado ? <CheckCircle /> : <Cancel />}
              color={reporte.aprobado ? 'success' : 'error'}
              label={reporte.aprobado ? 'Aprobado' : 'Reprobado'}
              sx={{ mb: 1 }}
            />
            <Typography variant="body2" color="text.secondary">
              {reporte.correctas} de {reporte.total} correctas · nota mínima {reporte.nota_minima}%
            </Typography>
            <Button sx={{ mt: 1 }} onClick={() => window.print()}>Imprimir / Guardar PDF</Button>
          </CardContent>
        </Card>

        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Revisión pregunta por pregunta</Typography>
        <Stack spacing={1.5}>
          {reporte.respuestas.map((r, i) => (
            <Card key={i} variant="outlined">
              <CardContent>
                <Box sx={{ display: 'flex', gap: 1, alignItems: 'flex-start' }}>
                  {r.es_correcta ? <CheckCircle color="success" /> : <Cancel color="error" />}
                  <Typography fontWeight={600}>{r.pregunta_texto}</Typography>
                </Box>
                <Divider sx={{ my: 1 }} />
                <Typography variant="body2">Tu respuesta: {r.texto_elegido ?? '(sin responder)'}</Typography>
                {!r.es_correcta && (
                  <Typography variant="body2" color="success.main">Correcta: {r.texto_correcto}</Typography>
                )}
                {r.explicacion && (
                  <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>{r.explicacion}</Typography>
                )}
              </CardContent>
            </Card>
          ))}
        </Stack>

        <Button sx={{ mt: 2 }} variant="contained" onClick={() => { setVista('lista'); cargarPendientes(); }}>
          Volver a mis exámenes
        </Button>
      </Box>
    );
  }

  return <Box sx={{ p: 4 }}><CircularProgress /></Box>;
}
