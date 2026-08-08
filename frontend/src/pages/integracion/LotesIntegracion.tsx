/**
 * LotesIntegracion.tsx — Lotes que Mallén deja en el esquema `ext`.
 * Pantalla de TI: ver qué llegó, validarlo y obtener el informe de qué corregir
 * para mandárselo al integrador.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Card, CardContent, Grid, CircularProgress, Snackbar,
  Dialog, DialogTitle, DialogContent, DialogActions, Tooltip,
} from '@mui/material';
import { FactCheck, Visibility } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  listarLotes, detalleLote, validarLote, resumenLotes,
  type EstadoLote, type LoteIntegracion,
} from '../../services/integracion.service';

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

const COLOR_ESTADO: Record<EstadoLote, 'default' | 'primary' | 'success' | 'error'> = {
  RECIBIDO: 'default', VALIDADO: 'primary', INTEGRADO: 'success', RECHAZADO: 'error',
};
const ESTADOS: EstadoLote[] = ['RECIBIDO', 'VALIDADO', 'INTEGRADO', 'RECHAZADO'];

export default function LotesIntegracion() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const [verLote, setVerLote] = useState<number | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const lotes = useQuery({
    queryKey: ['integracion-lotes', paisCodigo],
    queryFn: () => listarLotes(paisCodigo ? { pais_codigo: paisCodigo } : {}),
  });
  const resumen = useQuery({
    queryKey: ['integracion-resumen', paisCodigo],
    queryFn: () => resumenLotes(paisCodigo || undefined),
  });

  const validar = useMutation({
    mutationFn: (loteId: number) => validarLote(loteId),
    onSuccess: (r) => setAviso({
      sev: r.errores > 0 ? 'warning' : 'success',
      msg: `Lote ${r.lote_id}: ${r.estado}. ${r.mensaje}`,
    }),
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo validar el lote.') }),
    onSettled: () => {
      qc.invalidateQueries({ queryKey: ['integracion-lotes'] });
      qc.invalidateQueries({ queryKey: ['integracion-resumen'] });
    },
  });

  const filas = lotes.data || [];

  return (
    <Box sx={{ p: 3, maxWidth: 1200, mx: 'auto' }}>
      <Typography variant="h5" fontWeight={800} mb={2}>Lotes de Mallén</Typography>

      <Grid container spacing={2} mb={3}>
        {ESTADOS.map((e) => (
          <Grid item xs={6} md={3} key={e}>
            <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <CardContent>
                <Typography variant="caption" color="text.secondary">{e}</Typography>
                <Typography variant="h5" fontWeight={800}>{resumen.data?.[e] ?? 0}</Typography>
              </CardContent>
            </Card>
          </Grid>
        ))}
      </Grid>

      {lotes.isLoading ? <CircularProgress /> : lotes.isError ? (
        <Alert severity="warning">No se pudieron cargar los lotes.</Alert>
      ) : filas.length === 0 ? (
        <Alert severity="info">Aún no se ha recibido ningún lote de Mallén.</Alert>
      ) : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Lote</TableCell><TableCell>Origen</TableCell>
                <TableCell>Módulo</TableCell><TableCell>País</TableCell>
                <TableCell>Ciclo / Período</TableCell><TableCell>Recibido</TableCell>
                <TableCell align="right">Filas</TableCell>
                <TableCell>Estado</TableCell>
                <TableCell align="right">Hallazgos</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {filas.map((l: LoteIntegracion) => (
                <TableRow key={l.lote_id}>
                  <TableCell>{l.lote_id}</TableCell>
                  <TableCell>{l.sistema_origen}</TableCell>
                  <TableCell>{l.modulo}</TableCell>
                  <TableCell>{l.pais_codigo}</TableCell>
                  <TableCell>{l.ciclo_codigo || l.periodo || '—'}</TableCell>
                  <TableCell>{new Date(l.fecha_recepcion).toLocaleString()}</TableCell>
                  <TableCell align="right">{l.filas_enviadas}</TableCell>
                  <TableCell><Chip size="small" color={COLOR_ESTADO[l.estado]} label={l.estado} /></TableCell>
                  <TableCell align="right">{l.hallazgos || '—'}</TableCell>
                  <TableCell align="right">
                    <Tooltip title={l.estado === 'INTEGRADO'
                      ? 'Un lote ya integrado no se re-valida: sus datos ya están en VISTA'
                      : 'Validar el lote'}>
                      <span>
                        <Button size="small" startIcon={<FactCheck />}
                          disabled={l.estado === 'INTEGRADO' ||
                            (validar.isPending && validar.variables === l.lote_id)}
                          onClick={() => validar.mutate(l.lote_id)}>Validar</Button>
                      </span>
                    </Tooltip>
                    <Button size="small" startIcon={<Visibility />}
                      onClick={() => setVerLote(l.lote_id)}>Hallazgos</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <DialogoHallazgos loteId={verLote} onClose={() => setVerLote(null)} />

      <Snackbar open={!!aviso} autoHideDuration={8000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoHallazgos({ loteId, onClose }: { loteId: number | null; onClose: () => void }) {
  const datos = useQuery({
    queryKey: ['integracion-detalle', loteId],
    queryFn: () => detalleLote(loteId as number),
    enabled: loteId != null,
  });

  return (
    <Dialog open={loteId != null} onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle>Hallazgos del lote {loteId}</DialogTitle>
      <DialogContent>
        {datos.isLoading ? <CircularProgress /> : (datos.data?.hallazgos || []).length === 0 ? (
          <Alert severity="success">Sin hallazgos: el lote está limpio.</Alert>
        ) : (
          <>
            <Alert severity="info" sx={{ mb: 2 }}>
              Este detalle es lo que hay que enviarle al equipo técnico de Mallén para corregir.
            </Alert>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Tabla</TableCell><TableCell>Registro</TableCell>
                  <TableCell>Campo</TableCell><TableCell>Problema</TableCell>
                  <TableCell>Severidad</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {(datos.data?.hallazgos || []).map((h) => (
                  <TableRow key={h.id}>
                    <TableCell>{h.tabla}</TableCell>
                    <TableCell>{h.origen_id || '—'}</TableCell>
                    <TableCell>{h.campo || '—'}</TableCell>
                    <TableCell>{h.problema}</TableCell>
                    <TableCell>
                      <Chip size="small" color={h.severidad === 'error' ? 'error' : 'warning'}
                        label={h.severidad} />
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
