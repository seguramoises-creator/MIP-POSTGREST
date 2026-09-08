/**
 * ListaPasos.tsx — Lista de pasos de una ruta con su estado y bloqueos (§4).
 * Compartido por «Mi ruta» y por la consulta de asignaciones de «Rutas y plantillas».
 *
 * Los bloqueos se muestran TODOS: el backend los informa juntos a propósito, para
 * que nadie descubra el segundo motivo justo después de resolver el primero.
 */
import {
  Box, Card, CardContent, Typography, Chip, Stack, LinearProgress, Button, Alert,
} from '@mui/material';
import type { EstadoRuta, PasoEstado } from '../../../services/onboarding.service';

const COLOR_ESTADO: Record<PasoEstado['estado'], 'success' | 'primary' | 'default'> = {
  completado: 'success', disponible: 'primary', bloqueado: 'default',
};
const ETIQUETA_ESTADO: Record<PasoEstado['estado'], string> = {
  completado: 'Completado', disponible: 'Disponible', bloqueado: 'Bloqueado',
};

export default function ListaPasos({ estado, onCompletar, completando }: {
  estado: EstadoRuta;
  onCompletar?: (pasoId: number) => void;
  completando?: number | null;
}) {
  return (
    <Box>
      <Stack direction="row" alignItems="center" spacing={2} mb={1}>
        <Typography variant="body2" color="text.secondary">
          {estado.completados} de {estado.total_pasos} pasos
        </Typography>
        <Typography variant="body2" fontWeight={700}>{estado.progreso_pct}%</Typography>
      </Stack>
      <LinearProgress variant="determinate" value={Math.min(100, estado.progreso_pct)}
        sx={{ mb: 2, height: 8, borderRadius: 4 }} />

      {estado.pasos.map((p) => (
        <Card key={p.paso_id} elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5}>
              <Chip size="small" label={`${p.orden}`} />
              <Typography sx={{ flex: 1 }} fontWeight={600}>{p.titulo}</Typography>
              <Chip size="small" color={COLOR_ESTADO[p.estado]} label={ETIQUETA_ESTADO[p.estado]} />
            </Stack>
            <Typography variant="caption" color="text.secondary">
              {p.tipo} · lo marca: {p.quien_lo_marca}
            </Typography>

            {p.bloqueos.length > 0 && (
              <Alert severity="warning" sx={{ mt: 1 }}>
                {p.bloqueos.map((b, i) => <div key={i}>{b}</div>)}
              </Alert>
            )}

            {p.material && p.material.total > 0 && (
              <Typography variant="caption" display="block" sx={{ mt: 1 }}>
                Lectura obligatoria: {p.material.confirmados} de {p.material.total} confirmados
                {p.material.pendientes.length > 0 &&
                  ` — falta: ${p.material.pendientes.map((m) => m.titulo).join(', ')}`}
              </Typography>
            )}

            {onCompletar && p.estado === 'disponible' && (
              <Button size="small" variant="contained" sx={{ mt: 1 }}
                disabled={completando === p.paso_id}
                onClick={() => onCompletar(p.paso_id)}>
                {completando === p.paso_id ? 'Marcando…' : 'Marcar completado'}
              </Button>
            )}
          </CardContent>
        </Card>
      ))}
    </Box>
  );
}
