/**
 * RankingFormacion.tsx — El podio del módulo de Formación (§8).
 * Muestra de dónde salen los puntos (los 4 componentes por separado) para que la
 * posición sea explicable, no un número opaco.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Card, CardContent, Grid, CircularProgress, Snackbar,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField,
} from '@mui/material';
import { Refresh, Tune, EmojiEvents, LocalFireDepartment } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import {
  listarRankingFormacion, misPuntosFormacion, recalcularRankingFormacion,
  pesosRankingFormacion, fijarPesoRankingFormacion,
  type FilaRankingFormacion, type PesosRanking,
} from '../../services/rankingFormacion.service';

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o string.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

const ROLES_GESTION = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION'];
const MEDALLA = ['🥇', '🥈', '🥉'];

export default function RankingFormacion() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const rol = useAuthStore((s) => s.rol);
  const puedeGestionar = !!rol && ROLES_GESTION.includes(rol);
  const [pesos, setPesos] = useState(false);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const tabla = useQuery({
    queryKey: ['ranking-formacion', cicloId],
    queryFn: () => listarRankingFormacion(cicloId as number),
    enabled: cicloId != null,
  });
  // Si el usuario no está enlazado a un representante el backend da 403: la
  // tarjeta simplemente no se muestra, no es un error que interrumpa la pantalla.
  const mios = useQuery({
    queryKey: ['ranking-formacion-mis-puntos', cicloId],
    queryFn: () => misPuntosFormacion(cicloId as number),
    enabled: cicloId != null,
    retry: false,
  });

  const recalcular = useMutation({
    mutationFn: () => recalcularRankingFormacion(cicloId as number, paisCodigo as string),
    onSuccess: (r) => {
      setAviso({ sev: 'success', msg: `Recalculado: ${r.rms_procesados} representante(s), ${r.puntos_totales} puntos.` });
      qc.invalidateQueries({ queryKey: ['ranking-formacion'] });
      qc.invalidateQueries({ queryKey: ['ranking-formacion-mis-puntos'] });
    },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo recalcular.') }),
  });

  if (!paisCodigo || cicloId == null) {
    return <Box sx={{ p: 3 }}><Alert severity="info">Selecciona país y ciclo en el encabezado.</Alert></Box>;
  }

  const filas = tabla.data || [];
  const podio = filas.slice(0, 3);

  return (
    <Box sx={{ p: 3, maxWidth: 1100, mx: 'auto' }}>
      <Stack direction="row" alignItems="center" mb={2}>
        <Typography variant="h5" fontWeight={800} sx={{ flex: 1 }}>Ranking de Formación</Typography>
        {puedeGestionar && (
          <>
            <Button startIcon={<Tune />} onClick={() => setPesos(true)} sx={{ mr: 1 }}>Pesos</Button>
            <Button variant="contained" startIcon={<Refresh />}
              disabled={recalcular.isPending} onClick={() => recalcular.mutate()}>
              {recalcular.isPending ? 'Recalculando…' : 'Recalcular'}
            </Button>
          </>
        )}
      </Stack>

      {mios.data && (
        <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} mb={1}>
              <EmojiEvents color="warning" />
              <Typography fontWeight={700}>Mis puntos: {mios.data.puntos_total}</Typography>
              <Chip size="small" label={`Posición ${mios.data.posicion}`} />
              {mios.data.racha_ciclos > 0 && (
                <Chip size="small" color="warning" icon={<LocalFireDepartment />}
                  label={`${mios.data.racha_ciclos} ciclo(s) seguidos`} />
              )}
            </Stack>
            <Grid container spacing={1}>
              <Componente titulo="Certificaciones" valor={mios.data.puntos_certificacion} />
              <Componente titulo="Exámenes" valor={mios.data.puntos_examenes} />
              <Componente titulo="Refuerzo" valor={mios.data.puntos_refuerzo} />
              <Componente titulo="Onboarding" valor={mios.data.puntos_onboarding} />
            </Grid>
          </CardContent>
        </Card>
      )}

      {tabla.isLoading ? <CircularProgress /> : tabla.isError ? (
        <Alert severity="warning">No se pudo cargar el ranking.</Alert>
      ) : filas.length === 0 ? (
        <Alert severity="info">
          Este ciclo aún no tiene puntos calculados.{puedeGestionar ? ' Pulsa «Recalcular».' : ''}
        </Alert>
      ) : (
        <>
          <Grid container spacing={2} mb={3}>
            {podio.map((f, i) => (
              <Grid item xs={12} md={4} key={f.rm_id}>
                <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
                  <CardContent sx={{ textAlign: 'center' }}>
                    <Typography variant="h4">{MEDALLA[i]}</Typography>
                    <Typography fontWeight={700}>{f.rm_nombre}</Typography>
                    <Typography variant="h5" fontWeight={800}>{f.puntos_total}</Typography>
                    <Typography variant="caption" color="text.secondary">puntos</Typography>
                  </CardContent>
                </Card>
              </Grid>
            ))}
          </Grid>

          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell><TableCell>Representante</TableCell>
                  <TableCell align="right">Certif.</TableCell>
                  <TableCell align="right">Exám.</TableCell>
                  <TableCell align="right">Refuerzo</TableCell>
                  <TableCell align="right">Onboard.</TableCell>
                  <TableCell align="right">Total</TableCell>
                  <TableCell align="right">Racha</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {filas.map((f) => (
                  <TableRow key={f.rm_id}>
                    <TableCell>{f.posicion}</TableCell>
                    <TableCell>{f.rm_nombre}</TableCell>
                    <TableCell align="right">{f.puntos_certificacion}</TableCell>
                    <TableCell align="right">{f.puntos_examenes}</TableCell>
                    <TableCell align="right">{f.puntos_refuerzo}</TableCell>
                    <TableCell align="right">{f.puntos_onboarding}</TableCell>
                    <TableCell align="right"><strong>{f.puntos_total}</strong></TableCell>
                    <TableCell align="right">{f.racha_ciclos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>
        </>
      )}

      <DialogoPesos abierto={pesos} paisCodigo={paisCodigo}
        onClose={() => setPesos(false)}
        onGuardado={() => setAviso({ sev: 'success', msg: 'Peso actualizado. Recalcula para aplicarlo.' })} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function Componente({ titulo, valor }: { titulo: string; valor: number }) {
  return (
    <Grid item xs={6} md={3}>
      <Typography variant="caption" color="text.secondary">{titulo}</Typography>
      <Typography variant="h6" fontWeight={700}>{valor}</Typography>
    </Grid>
  );
}

const ETIQUETA_PESO: Record<keyof PesosRanking, string> = {
  ranking_puntos_certificacion: 'Puntos por certificación aprobada',
  ranking_puntos_examen: 'Puntos por examen aprobado',
  ranking_puntos_paso_onboarding: 'Puntos por paso de ruta completado',
  ranking_bono_ruta_completa: 'Bono por completar la ruta',
};

function DialogoPesos({ abierto, paisCodigo, onClose, onGuardado }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onGuardado: () => void;
}) {
  const qc = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const datos = useQuery({
    queryKey: ['ranking-formacion-pesos', paisCodigo],
    queryFn: () => pesosRankingFormacion(paisCodigo),
    enabled: abierto,
  });
  const [borrador, setBorrador] = useState<Record<string, string>>({});

  const guardar = useMutation({
    mutationFn: async () => {
      for (const [clave, valor] of Object.entries(borrador)) {
        if (valor.trim() && !Number.isNaN(Number(valor))) {
          await fijarPesoRankingFormacion({ pais_codigo: paisCodigo, clave, valor: Number(valor) });
        }
      }
    },
    onSuccess: () => {
      setBorrador({}); setError(null);
      qc.invalidateQueries({ queryKey: ['ranking-formacion-pesos', paisCodigo] });
      onGuardado(); onClose();
    },
    onError: (e) => setError(detalleError(e, 'No se pudo guardar el peso.')),
  });

  // Cerrar (Cancelar o clic fuera) descarta cualquier valor sin guardar: si no,
  // reabrir el diálogo más tarde muestra el borrador viejo como si fuera el
  // valor vigente, y un "Guardar" sin tocar nada lo persistiría igual.
  const cerrar = () => { setBorrador({}); setError(null); onClose(); };

  return (
    <Dialog open={abierto} onClose={cerrar} maxWidth="sm" fullWidth>
      <DialogTitle>Pesos del Ranking de Formación</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info">
            Los puntos de Refuerzo no llevan peso: ya vienen calculados por la participación
            en las cápsulas. Tras cambiar un peso hay que recalcular el ciclo.
          </Alert>
          {datos.isLoading ? <CircularProgress /> : (Object.keys(ETIQUETA_PESO) as (keyof PesosRanking)[]).map((k) => (
            <TextField key={k} label={ETIQUETA_PESO[k]} type="number"
              value={borrador[k] ?? String(datos.data?.[k] ?? '')}
              onChange={(e) => setBorrador((p) => ({ ...p, [k]: e.target.value }))}
              fullWidth />
          ))}
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={cerrar}>Cancelar</Button>
        <Button variant="contained" disabled={guardar.isPending}
          onClick={() => guardar.mutate()}>{guardar.isPending ? 'Guardando…' : 'Guardar'}</Button>
      </DialogActions>
    </Dialog>
  );
}
