/**
 * MiRanking.tsx — Vista del REPRESENTANTE: dónde está, no quién es quién.
 *
 * Decisión del cliente (jul-2026): el representante ve su posición ("estás 12 de 45"), no el
 * ranking completo. Un ranking con nombres y puntajes es el dato individual de cada colega
 * expuesto a los otros 44 — contradiría la regla que él mismo fijó para Productividad
 * ("no puede ver ningún dato de ningún otro visitador").
 *
 * Consume GET /ranking/mi-posicion: devuelve su fila y CONTEOS del universo, nunca una fila
 * ajena.
 */
import {
  Box, Card, CardContent, Grid, Typography, Alert, LinearProgress, Stack, Chip,
} from '@mui/material';
import { EmojiEvents, TrendingUp, TrendingDown, Remove } from '@mui/icons-material';
import { useQuery } from '@tanstack/react-query';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';
import { ERROR, EXITO, NEUTRO_400 } from '../../theme/marca';

type MiPosicion = {
  sin_datos: boolean; motivo?: string;
  ciclo: string | null; posicion: number | null; total: number | null;
  posicion_linea: number | null; total_linea: number | null; linea: string | null;
  score_total: number; percentil: number | null;
  posicion_anterior: number | null; variacion: number | null; elegible: boolean;
};

export default function MiRanking() {
  const cicloId = useCicloStore((s) => s.cicloId);
  const { data, isLoading } = useQuery<MiPosicion>({
    queryKey: ['mi-posicion', cicloId],
    queryFn: () => api.get('/ranking/mi-posicion',
      { params: cicloId ? { ciclo_id: cicloId } : {} }).then((r) => r.data),
  });

  if (isLoading) return <LinearProgress />;
  if (!data) return <Alert severity="error">No se pudo cargar tu posición.</Alert>;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <EmojiEvents color="primary" />
        <Typography variant="h5" fontWeight={700}>Mi Posición</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Tu lugar en el ranking{data.ciclo ? <> del ciclo <b>{data.ciclo}</b></> : ''}.
      </Typography>

      {data.sin_datos ? (
        <Alert severity="info">
          {data.motivo ?? 'Todavía no tienes resultados en el ranking de este ciclo.'}
        </Alert>
      ) : (
        <>
          {/* El letrero: "Estás en la posición X de Y". */}
          <Card variant="outlined" sx={{ mb: 2, borderWidth: 2, borderColor: 'primary.main',
                bgcolor: 'rgba(46,91,255,0.04)' }}>
            <CardContent sx={{ textAlign: 'center', py: 3 }}>
              <Typography variant="overline" color="text.secondary" fontWeight={700}>
                Estás en la posición
              </Typography>
              <Stack direction="row" alignItems="baseline" justifyContent="center" spacing={1}>
                <Typography variant="h2" fontWeight={800} color="primary.main">{data.posicion}</Typography>
                <Typography variant="h5" color="text.secondary">de {data.total}</Typography>
              </Stack>
              {data.percentil != null && (
                <Typography variant="body2" color="text.secondary" sx={{ mt: 0.5 }}>
                  Estás por encima del <b>{data.percentil}%</b> de los representantes
                </Typography>
              )}
            </CardContent>
          </Card>

          <Grid container spacing={2}>
            <Grid item xs={12} sm={4}>
              <Card variant="outlined"><CardContent sx={{ py: 1.75 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>TU SCORE</Typography>
                <Typography variant="h4" fontWeight={800} color="primary.main">
                  {data.score_total.toFixed(1)}
                </Typography>
                <Chip size="small" color={data.elegible ? 'success' : 'default'}
                      variant={data.elegible ? 'filled' : 'outlined'}
                      label={data.elegible ? 'Elegible para premios' : 'No elegible'} sx={{ mt: 0.5 }} />
              </CardContent></Card>
            </Grid>

            {data.posicion_linea != null && (
              <Grid item xs={12} sm={4}>
                <Card variant="outlined"><CardContent sx={{ py: 1.75 }}>
                  <Typography variant="caption" color="text.secondary" fontWeight={700}>
                    EN TU LÍNEA
                  </Typography>
                  <Stack direction="row" alignItems="baseline" spacing={0.5}>
                    <Typography variant="h4" fontWeight={800} color="primary.main">{data.posicion_linea}</Typography>
                    <Typography variant="body1" color="text.secondary">de {data.total_linea}</Typography>
                  </Stack>
                  <Typography variant="caption" color="text.secondary">{data.linea}</Typography>
                </CardContent></Card>
              </Grid>
            )}

            <Grid item xs={12} sm={4}>
              <Card variant="outlined"><CardContent sx={{ py: 1.75 }}>
                <Typography variant="caption" color="text.secondary" fontWeight={700}>
                  VS. CICLO ANTERIOR
                </Typography>
                {data.variacion == null ? (
                  <>
                    <Typography variant="h4" fontWeight={800} color="text.disabled">—</Typography>
                    <Typography variant="caption" color="text.secondary">Sin ciclo previo con el que comparar</Typography>
                  </>
                ) : (
                  <>
                    <Stack direction="row" alignItems="center" spacing={0.5}>
                      {data.variacion > 0 ? <TrendingUp sx={{ color: EXITO }} />
                        : data.variacion < 0 ? <TrendingDown sx={{ color: ERROR }} />
                        : <Remove sx={{ color: NEUTRO_400 }} />}
                      <Typography variant="h4" fontWeight={800}
                        sx={{ color: data.variacion > 0 ? EXITO : data.variacion < 0 ? ERROR : NEUTRO_400 }}>
                        {data.variacion > 0 ? `+${data.variacion}` : data.variacion}
                      </Typography>
                    </Stack>
                    <Typography variant="caption" color="text.secondary">
                      {data.variacion > 0 ? `Subiste ${data.variacion} puesto(s)`
                        : data.variacion < 0 ? `Bajaste ${Math.abs(data.variacion)} puesto(s)`
                        : 'Mantienes tu posición'} (eras {data.posicion_anterior})
                    </Typography>
                  </>
                )}
              </CardContent></Card>
            </Grid>
          </Grid>
        </>
      )}
    </Box>
  );
}
