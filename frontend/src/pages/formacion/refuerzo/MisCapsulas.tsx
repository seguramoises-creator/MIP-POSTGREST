/**
 * MisCapsulas.tsx — Tab del representante (§10.5-§10.7).
 * La opción correcta NO llega con el enunciado: solo al responder. Por eso el
 * resaltado se hace con el resultado de la mutation, sin recargar la lista.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, Button, Stack, Alert, Chip,
  TextField, CircularProgress, Divider,
} from '@mui/material';
import { EmojiEvents } from '@mui/icons-material';
import {
  misCapsulas, responderCapsula, misPuntos,
  type CapsulaPendiente, type ResultadoRespuesta,
} from '../../../services/refuerzo.service';

const ETIQUETA_FORMATO: Record<string, string> = {
  microlectura: 'Microlectura', reto: 'Reto',
  caso_breve: 'Caso breve', reflexion_abierta: 'Reflexión abierta',
};

export default function MisCapsulas() {
  const qc = useQueryClient();
  const [resultados, setResultados] = useState<Record<number, ResultadoRespuesta>>({});
  const [textos, setTextos] = useState<Record<number, string>>({});

  const pendientes = useQuery({ queryKey: ['refuerzo-mis-capsulas'], queryFn: misCapsulas });
  const puntos = useQuery({ queryKey: ['refuerzo-mis-puntos'], queryFn: () => misPuntos() });

  const responder = useMutation({
    mutationFn: (v: { capsulaId: number; opcion?: string; texto_libre?: string }) =>
      responderCapsula(v.capsulaId, { opcion: v.opcion, texto_libre: v.texto_libre }),
    onSuccess: (r) => {
      setResultados((prev) => ({ ...prev, [r.capsula_id]: r }));
      qc.invalidateQueries({ queryKey: ['refuerzo-mis-puntos'] });
    },
  });

  if (pendientes.isLoading) return <CircularProgress />;
  // 403 típico: el usuario tiene rol de representante pero no está enlazado a
  // uno en Config.DIM_RM. Se dice tal cual en vez de mostrar una lista vacía.
  if (pendientes.isError) {
    return <Alert severity="warning">
      No se pudieron cargar tus cápsulas. Si tu usuario no está enlazado a un representante,
      pídele a un administrador que lo enlace.
    </Alert>;
  }

  const lista = pendientes.data || [];
  // Se conservan en pantalla las ya respondidas en esta sesión, para que el
  // usuario vea su corrección aunque salgan de "pendientes".
  const visibles = lista.filter((c) => !resultados[c.capsula_id]);
  const respondidas = lista.filter((c) => resultados[c.capsula_id]);

  return (
    <Box>
      <Stack direction="row" spacing={1} alignItems="center" mb={2}>
        <EmojiEvents color="warning" />
        <Typography fontWeight={700}>{puntos.data?.puntos ?? 0} puntos de Refuerzo</Typography>
      </Stack>

      {visibles.length === 0 && respondidas.length === 0 && (
        <Alert severity="info">No tienes cápsulas pendientes.</Alert>
      )}

      {[...respondidas, ...visibles].map((c) => (
        <TarjetaCapsula key={c.capsula_id} capsula={c}
          resultado={resultados[c.capsula_id]}
          texto={textos[c.capsula_id] || ''}
          onTexto={(v) => setTextos((p) => ({ ...p, [c.capsula_id]: v }))}
          enviando={responder.isPending && responder.variables?.capsulaId === c.capsula_id}
          onResponder={(opcion, texto_libre) =>
            responder.mutate({ capsulaId: c.capsula_id, opcion, texto_libre })} />
      ))}
    </Box>
  );
}

function TarjetaCapsula({ capsula, resultado, texto, onTexto, enviando, onResponder }: {
  capsula: CapsulaPendiente;
  resultado?: ResultadoRespuesta;
  texto: string;
  onTexto: (v: string) => void;
  enviando: boolean;
  onResponder: (opcion?: string, texto_libre?: string) => void;
}) {
  const opciones = capsula.opciones || {};
  const esReto = capsula.formato === 'reto';
  const esAbierta = capsula.formato === 'reflexion_abierta';

  return (
    <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
      <CardContent>
        <Stack direction="row" spacing={1} alignItems="center" mb={1}>
          <Chip size="small" color="primary" label={ETIQUETA_FORMATO[capsula.formato] || capsula.formato} />
          <Typography variant="caption" color="text.secondary">
            {capsula.campana} · Ronda {capsula.ronda}
          </Typography>
        </Stack>
        <Typography sx={{ mb: 2 }}>{capsula.enunciado}</Typography>

        {esReto && (
          <Stack spacing={1}>
            {Object.entries(opciones).map(([k, v]) => {
              const esCorrecta = resultado && k === resultado.opcion_correcta;
              const elegidaMal = resultado && k === resultado.opcion_seleccionada && !esCorrecta;
              return (
                <Button key={k} fullWidth
                  variant={resultado ? 'outlined' : 'contained'}
                  color={esCorrecta ? 'success' : elegidaMal ? 'error' : 'primary'}
                  disabled={!!resultado || enviando}
                  onClick={() => onResponder(k, undefined)}
                  sx={{ justifyContent: 'flex-start', textTransform: 'none' }}>
                  <strong style={{ marginRight: 8 }}>{k}.</strong> {v}
                </Button>
              );
            })}
          </Stack>
        )}

        {esAbierta && !resultado && (
          <Stack spacing={1}>
            <TextField multiline minRows={3} fullWidth value={texto}
              onChange={(e) => onTexto(e.target.value)} placeholder="Escribe tu reflexión…" />
            <Button variant="contained" disabled={!texto.trim() || enviando}
              onClick={() => onResponder(undefined, texto)}>Enviar</Button>
          </Stack>
        )}

        {!esReto && !esAbierta && !resultado && (
          <Button variant="contained" disabled={enviando}
            onClick={() => onResponder(undefined, undefined)}>Marcar como leída</Button>
        )}

        {enviando && <CircularProgress size={20} sx={{ mt: 1 }} />}

        {resultado && (
          <>
            <Divider sx={{ my: 2 }} />
            {resultado.repetida && (
              <Alert severity="info" sx={{ mb: 1 }}>Ya habías respondido esta cápsula.</Alert>
            )}
            {/* es_acierto null = no hay correcta que medir (§10.5): solo acuse. */}
            {resultado.es_acierto !== null && (
              <Alert severity={resultado.es_acierto ? 'success' : 'error'} sx={{ mb: 1 }}>
                {resultado.es_acierto ? '¡Correcto!' : `La opción correcta era la ${resultado.opcion_correcta}.`}
              </Alert>
            )}
            {resultado.explicacion && (
              <Alert severity="info" sx={{ mb: 1 }}>{resultado.explicacion}</Alert>
            )}
            <Typography variant="caption" color="text.secondary">
              +{resultado.puntos_obtenidos} puntos · participación {resultado.pct_participacion}% ·
              respondida en {resultado.tiempo_respuesta_seg}s
            </Typography>
          </>
        )}
      </CardContent>
    </Card>
  );
}
