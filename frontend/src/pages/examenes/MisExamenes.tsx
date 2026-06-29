import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, LinearProgress, Chip, Stack,
  RadioGroup, FormControlLabel, Radio, Divider, Alert, CircularProgress, TextField,
} from '@mui/material';
import { AccessTime, CheckCircle, Cancel, Assignment } from '@mui/icons-material';
import { History } from '@mui/icons-material';
import {
  misPendientes, iniciarExamen, responder, responderTexto, entregar, miHistorial,
  type Asignacion, type IntentoIniciado, type ReporteIntento,
} from '../../services/examenes.service';

interface IntentoHistorial {
  intento_id: number; fecha_fin: string | null;
  score: number | null; aprobado: boolean | null; tiempo_usado_seg: number | null;
}

type Vista = 'lista' | 'tomando' | 'reporte';

const lsKey = (intentoId: number) => `examen_intento_${intentoId}`;

export default function MisExamenes() {
  const [vista, setVista] = useState<Vista>('lista');
  const [pendientes, setPendientes] = useState<Asignacion[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [noEvaluado, setNoEvaluado] = useState(false);

  const [intento, setIntento] = useState<IntentoIniciado | null>(null);
  const [idx, setIdx] = useState(0);
  const [respuestas, setRespuestas] = useState<Record<number, number>>({});
  const [respuestasTexto, setRespuestasTexto] = useState<Record<number, string>>({});
  const [segRestantes, setSegRestantes] = useState<number | null>(null);
  const [reporte, setReporte] = useState<ReporteIntento | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [historial, setHistorial] = useState<IntentoHistorial[] | null>(null);

  const cargarPendientes = useCallback(() => {
    setCargando(true);
    setNoEvaluado(false);
    misPendientes()
      .then(setPendientes)
      .catch((err: { response?: { status?: number } }) => {
        if (err?.response?.status === 403) setNoEvaluado(true);
        else setError('No se pudieron cargar tus exámenes asignados.');
      })
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
  const respondidas = Object.keys(respuestas).length
    + Object.keys(respuestasTexto).filter((k) => respuestasTexto[Number(k)]?.trim()).length;
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
    } catch (err: unknown) {
      const detalle = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(detalle || 'No se pudo iniciar el examen. Verifica que tengas una asignación pendiente.');
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
  function escribirTexto(preguntaId: number, texto: string) {
    setRespuestasTexto((prev) => ({ ...prev, [preguntaId]: texto }));
  }
  function guardarTexto(preguntaId: number) {
    if (!intento) return;
    const texto = respuestasTexto[preguntaId] ?? '';
    void responderTexto(intento.intento_id, preguntaId, texto).catch(() => {});
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
        {noEvaluado ? (
          <Alert severity="info">
            Esta sección es para <strong>visitadores médicos</strong> o <strong>gerentes</strong> evaluados.
            Tu usuario no está vinculado a un representante (rm_id) ni a un gerente, por lo que no tiene
            exámenes asignados. Inicia sesión con un usuario evaluado para tomar exámenes.
          </Alert>
        ) : (
          pendientes.length === 0 && <Alert severity="info">No tienes exámenes pendientes.</Alert>
        )}
        <Stack spacing={1.5}>
          {pendientes.map((a) => {
            const hoy = new Date(); hoy.setHours(0, 0, 0, 0);
            const vencido = a.fecha_limite ? new Date(a.fecha_limite) < hoy : false;
            const fechaTxt = a.fecha_limite ? new Date(a.fecha_limite).toLocaleDateString() : null;
            return (
              <Card key={a.id} variant="outlined" sx={vencido ? { opacity: 0.7 } : undefined}>
                <CardContent sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                  <Assignment color={vencido ? 'disabled' : 'primary'} />
                  <Box sx={{ flex: 1, minWidth: 180 }}>
                    <Stack direction="row" spacing={1} alignItems="center">
                      <Typography fontWeight={600}>Examen #{a.examen_id}</Typography>
                      {vencido && <Chip size="small" color="error" label="Vencido" />}
                    </Stack>
                    <Typography variant="body2" color="text.secondary">
                      {fechaTxt ? `Fecha límite: ${fechaTxt}` : 'Sin fecha límite'}
                      {a.intentos_max != null && ` · Intentos: ${a.intentos_usados}/${a.intentos_max}`}
                    </Typography>
                  </Box>
                  <Button variant="contained" size="large" disabled={vencido}
                          onClick={() => iniciar(a.examen_id)}>
                    {vencido ? 'Vencido' : 'Tomar examen'}
                  </Button>
                </CardContent>
              </Card>
            );
          })}
        </Stack>

        {!noEvaluado && (
          <Box sx={{ mt: 3 }}>
            <Button startIcon={<History />} onClick={() => {
              if (historial === null) miHistorial().then(setHistorial).catch(() => setHistorial([]));
              else setHistorial(null);
            }}>
              {historial === null ? 'Ver mi historial' : 'Ocultar historial'}
            </Button>
            {historial !== null && (
              <Stack spacing={1} sx={{ mt: 1.5 }}>
                {historial.length === 0 && <Alert severity="info">Aún no has tomado exámenes.</Alert>}
                {historial.map((h) => (
                  <Card key={h.intento_id} variant="outlined">
                    <CardContent sx={{ py: 1, display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
                      <Chip
                        label={h.score != null ? `${h.score}%` : '—'}
                        color={h.aprobado ? 'success' : h.aprobado === false ? 'error' : 'default'}
                      />
                      <Typography variant="body2" sx={{ flex: 1 }}>
                        Intento #{h.intento_id} · {h.aprobado ? 'Aprobado' : h.aprobado === false ? 'Reprobado' : 'En curso'}
                      </Typography>
                      <Typography variant="caption" color="text.secondary">
                        {h.fecha_fin ? new Date(h.fecha_fin).toLocaleString() : 'sin entregar'}
                      </Typography>
                    </CardContent>
                  </Card>
                ))}
              </Stack>
            )}
          </Box>
        )}
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
            {preguntaActual.opciones.length === 0 ? (
              <TextField
                fullWidth multiline minRows={4} placeholder="Escribe tu respuesta…"
                value={respuestasTexto[preguntaActual.pregunta_id] ?? ''}
                onChange={(e) => escribirTexto(preguntaActual.pregunta_id, e.target.value)}
                onBlur={() => guardarTexto(preguntaActual.pregunta_id)}
              />
            ) : (
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
            )}
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
