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
  Dialog, DialogTitle, DialogContent, DialogActions, Tooltip, TextField,
} from '@mui/material';
import { FactCheck, Visibility, Sync } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  listarLotes, detalleLote, validarLote, resumenLotes,
  sincronizarDimensiones, resumenDimensiones,
  integrarVisitas, resumenVisitas,
  sincronizarIR, diagnosticoIR,
  type EstadoLote, type LoteIntegracion,
  type ConteoDimension, type ResultadoSincronizacion,
  type ResultadoIntegracionVisitas,
  type DiagnosticoIR, type ResultadoSincronizacionIR,
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

      <SeccionDimensiones paisCodigo={paisCodigo} />

      <SeccionVisitas paisCodigo={paisCodigo} />

      <SeccionIR paisCodigo={paisCodigo} />

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

function SeccionDimensiones({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [resultado, setResultado] = useState<ResultadoSincronizacion | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resumen = useQuery({
    queryKey: ['integracion-dimensiones', paisCodigo],
    queryFn: () => resumenDimensiones(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const sincronizar = useMutation({
    mutationFn: () => sincronizarDimensiones(paisCodigo as string),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-dimensiones'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron sincronizar las dimensiones.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para ver las dimensiones.
    </Alert>;
  }

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>Dimensiones</Typography>
        <Button variant="contained" startIcon={<Sync />}
          disabled={sincronizar.isPending} onClick={() => sincronizar.mutate()}>
          {sincronizar.isPending ? 'Sincronizando…' : 'Sincronizar dimensiones'}
        </Button>
      </Box>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Dimensión</TableCell>
              <TableCell align="right">En Mallén</TableCell>
              <TableCell align="right">Mapeadas</TableCell>
              <TableCell align="right">Pendientes</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(resumen.data || []).map((f) => (
              <TableRow key={f.entidad}>
                <TableCell sx={{ textTransform: 'capitalize' }}>{f.entidad}</TableCell>
                <TableCell align="right">{f.en_ext}</TableCell>
                <TableCell align="right">{f.mapeadas}</TableCell>
                <TableCell align="right">{Math.max(0, f.en_ext - f.mapeadas) || '—'}</TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>

      {resultado && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>
            Sincronización completada. «Adoptados» son los registros que ya existían
            en VISTA y se emparejaron en vez de duplicarse.
          </Alert>
          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Dimensión</TableCell>
                  <TableCell align="right">Creados</TableCell>
                  <TableCell align="right">Adoptados</TableCell>
                  <TableCell align="right">Actualizados</TableCell>
                  <TableCell align="right">Omitidos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultado.dimensiones.map((d: ConteoDimension) => (
                  <TableRow key={d.entidad}>
                    <TableCell sx={{ textTransform: 'capitalize' }}>{d.entidad}</TableCell>
                    <TableCell align="right">{d.creados}</TableCell>
                    <TableCell align="right"><strong>{d.adoptados}</strong></TableCell>
                    <TableCell align="right">{d.actualizados}</TableCell>
                    <TableCell align="right">{d.omitidos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {resultado.hallazgos.length > 0 && (
            <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <Box sx={{ p: 2 }}>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Esto es lo que hay que enviarle al equipo técnico de Mallén para corregir.
                </Alert>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Dimensión</TableCell><TableCell>Código</TableCell>
                      <TableCell>Problema</TableCell><TableCell>Severidad</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.hallazgos.map((h, i) => (
                      <TableRow key={`${h.entidad}-${h.codigo_externo}-${i}`}>
                        <TableCell sx={{ textTransform: 'capitalize' }}>{h.entidad}</TableCell>
                        <TableCell>{h.codigo_externo}</TableCell>
                        <TableCell>{h.problema}</TableCell>
                        <TableCell>
                          <Chip size="small" label={h.severidad}
                            color={h.severidad === 'error' ? 'error' : 'warning'} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}

function SeccionVisitas({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [cicloCodigo, setCicloCodigo] = useState('');
  const [resultado, setResultado] = useState<ResultadoIntegracionVisitas | null>(null);
  const [error, setError] = useState<string | null>(null);

  const resumen = useQuery({
    queryKey: ['integracion-visitas', paisCodigo, cicloCodigo],
    queryFn: () => resumenVisitas(paisCodigo as string, cicloCodigo),
    enabled: !!paisCodigo && !!cicloCodigo.trim(),
  });

  const integrar = useMutation({
    mutationFn: () => integrarVisitas(paisCodigo as string, cicloCodigo),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-visitas'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron integrar las visitas.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para integrar visitas.
    </Alert>;
  }

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>Visitas</Typography>
        <TextField size="small" label="Ciclo (código de Mallén)" value={cicloCodigo}
          onChange={(e) => setCicloCodigo(e.target.value)} sx={{ width: 220 }} />
        <Button variant="contained" startIcon={<Sync />}
          disabled={!cicloCodigo.trim() || integrar.isPending}
          onClick={() => integrar.mutate()}>
          {integrar.isPending ? 'Integrando…' : 'Integrar visitas'}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Integrar deja el ciclo completo: los cinco hechos entran (panel médico,
        visitas médico, target farmacia, visitas farmacia y ventas), los
        indicadores COB_MD_F1, COB_MD_F2, PROM_DIARIO, COB_FARMACIAS y VENTAS
        se calculan desde ellos, se recalculan Score y ranking, y los lotes
        quedan marcados como integrados.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {resumen.data && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Hecho</TableCell>
                <TableCell align="right">En Mallén</TableCell>
                <TableCell align="right">Integradas</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {resumen.data.map((f) => (
                <TableRow key={f.hecho}>
                  <TableCell>{f.hecho}</TableCell>
                  <TableCell align="right">{f.en_ext}</TableCell>
                  <TableCell align="right">{f.integradas}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {resultado && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>
            Integración completada. Indicadores calculados para {resultado.indicadores.rms}
            {' '}representante(s): {resultado.indicadores.filas} valor(es).
            {resultado.lotes_cerrados.length > 0 &&
              ` Lote(s) marcados como integrados: ${resultado.lotes_cerrados.join(', ')}.`}
          </Alert>
          {/* El recálculo es lo que hace visible la integración en el Score y el
              ranking. Si se abortó, el operador tiene que saberlo: los hechos
              entraron pero los tableros siguen mostrando el cálculo anterior. */}
          {resultado.recalculo.abortado ? (
            <Alert severity="warning" sx={{ mb: 2 }}>
              Los hechos se integraron, pero el Score y el ranking <b>no</b> se
              recalcularon: {resultado.recalculo.motivo ?? 'el ciclo está cerrado.'}
            </Alert>
          ) : (
            <Alert severity="info" sx={{ mb: 2 }}>
              Score y ranking recalculados: {resultado.recalculo.rankings_generados ?? 0}
              {' '}posición(es) de ranking generadas.
            </Alert>
          )}
          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Hecho</TableCell>
                  <TableCell align="right">Integrados</TableCell>
                  <TableCell align="right">Actualizados</TableCell>
                  <TableCell align="right">Omitidos</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultado.hechos.map((h) => (
                  <TableRow key={h.hecho}>
                    <TableCell>{h.hecho}</TableCell>
                    <TableCell align="right">{h.integrados}</TableCell>
                    <TableCell align="right">{h.actualizados}</TableCell>
                    <TableCell align="right">{h.omitidos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {resultado.hallazgos.length > 0 && (
            <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
              <Alert severity="info" sx={{ mb: 2 }}>
                Esto es lo que hay que enviarle al equipo técnico de Mallén para corregir.
              </Alert>
              <Table size="small">
                <TableHead>
                  <TableRow>
                    <TableCell>Hecho</TableCell><TableCell>Registro</TableCell>
                    <TableCell>Problema</TableCell><TableCell>Severidad</TableCell>
                  </TableRow>
                </TableHead>
                <TableBody>
                  {resultado.hallazgos.map((h, i) => (
                    <TableRow key={`${h.hecho}-${h.origen_id}-${i}`}>
                      <TableCell>{h.hecho}</TableCell>
                      <TableCell>{h.origen_id || '—'}</TableCell>
                      <TableCell>{h.problema}</TableCell>
                      <TableCell>
                        <Chip size="small" label={h.severidad}
                          color={h.severidad === 'error' ? 'error' : 'warning'} />
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}

function SeccionIR({ paisCodigo }: { paisCodigo: string | null }) {
  const qc = useQueryClient();
  const [resultado, setResultado] = useState<ResultadoSincronizacionIR | null>(null);
  const [error, setError] = useState<string | null>(null);

  const diag = useQuery<DiagnosticoIR>({
    queryKey: ['integracion-ir', paisCodigo],
    queryFn: () => diagnosticoIR(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const sincronizar = useMutation({
    mutationFn: () => sincronizarIR(paisCodigo as string),
    onSuccess: (r) => {
      setResultado(r); setError(null);
      qc.invalidateQueries({ queryKey: ['integracion-ir'] });
    },
    onError: (e) => setError(detalleError(e, 'No se pudieron resolver las equivalencias.')),
  });

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ mt: 4 }}>
      Selecciona un país en el encabezado para revisar el módulo IR.
    </Alert>;
  }

  const d = diag.data;

  return (
    <Box sx={{ mt: 5 }}>
      <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, mb: 2 }}>
        <Typography variant="h6" fontWeight={700} sx={{ flex: 1 }}>
          Prescripción IR
        </Typography>
        <Button variant="contained" startIcon={<Sync />}
          disabled={sincronizar.isPending}
          onClick={() => sincronizar.mutate()}>
          {sincronizar.isPending ? 'Resolviendo…' : 'Resolver equivalencias'}
        </Button>
      </Box>

      <Alert severity="info" sx={{ mb: 2 }}>
        Enlaza el prescriptor (por exequátur), el producto y el período de
        Close-Up con los catálogos de VISTA. <b>No crea médicos</b>: un
        prescriptor que ningún representante trabaja se cuenta para el
        mercado y no se atribuye a nadie. Esta pantalla solo mide qué tan
        bien enlaza — <b>el indicador EVO_IR todavía no se calcula</b> a
        partir de esto.
      </Alert>

      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

      {d && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Qué</TableCell>
                <TableCell align="right">En Mallén</TableCell>
                <TableCell align="right">Enlazados</TableCell>
                <TableCell align="right">Sin enlazar</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              <TableRow>
                <TableCell>Prescriptores (con panel: {d.prescriptores.con_panel})</TableCell>
                <TableCell align="right">{d.prescriptores.en_ext}</TableCell>
                <TableCell align="right">{d.prescriptores.enlazados}</TableCell>
                <TableCell align="right">
                  {d.prescriptores.huerfanos}
                  {d.prescriptores.casi_enlazados > 0 &&
                    ` (+${d.prescriptores.casi_enlazados} mal escritos)`}
                </TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Productos (propios: {d.productos.propios})</TableCell>
                <TableCell align="right">{d.productos.en_ext}</TableCell>
                <TableCell align="right">{d.productos.enlazados}</TableCell>
                <TableCell align="right">{d.productos.propios_sin_equivalencia}</TableCell>
              </TableRow>
              <TableRow>
                <TableCell>Períodos</TableCell>
                <TableCell align="right">{d.periodos.en_ext}</TableCell>
                <TableCell align="right">{d.periodos.con_ciclo}</TableCell>
                <TableCell align="right">{d.periodos.sin_ciclo}</TableCell>
              </TableRow>
            </TableBody>
          </Table>
        </Paper>
      )}

      {d && d.recetas.total > 0 && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 2 }}>
          <Typography variant="subtitle2" fontWeight={700} sx={{ mb: 1 }}>
            Recetas atribuibles ({d.recetas.total} en total)
          </Typography>
          <Typography variant="body2" color="text.secondary">
            {d.recetas.directas} traen representante de Mallén ·{' '}
            {d.recetas.por_cadena} se atribuyen por el panel ·{' '}
            {d.recetas.ambiguas} ambiguas ·{' '}
            {d.recetas.huerfanas} sin dueño (cuentan para el mercado)
          </Typography>
          {d.recetas.huerfanas > 0 && (d.recetas.sin_ciclo > 0 || d.recetas.rm_no_enlazado > 0) && (
            <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mt: 0.5 }}>
              De las {d.recetas.huerfanas} sin dueño, se sabe la causa de{' '}
              {d.recetas.sin_ciclo + d.recetas.rm_no_enlazado}:{' '}
              {d.recetas.sin_ciclo > 0 &&
                `${d.recetas.sin_ciclo} porque su período no tiene ciclo mapeado`}
              {d.recetas.sin_ciclo > 0 && d.recetas.rm_no_enlazado > 0 && ' y '}
              {d.recetas.rm_no_enlazado > 0 &&
                `${d.recetas.rm_no_enlazado} porque Mallén reporta un representante que VISTA aún no tiene sincronizado (corre primero la sincronización de dimensiones)`}
              . El resto no tiene un prescriptor o panel vigente que las reclame.
            </Typography>
          )}
        </Paper>
      )}

      {resultado && (
        <>
          <Alert severity="success" sx={{ mb: 2 }}>
            Sincronización completada. «Ya enlazados» son los que venían de una
            corrida anterior; «casi enlazados» y «omitidos» no cuentan como
            fallo — ver la tabla.
          </Alert>
          <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 2 }}>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>Entidad</TableCell>
                  <TableCell align="right">En Mallén</TableCell>
                  <TableCell align="right">Enlazados</TableCell>
                  <TableCell align="right">Ya enlazados</TableCell>
                  <TableCell align="right">Sin enlazar</TableCell>
                  <TableCell align="right">Casi enlazados</TableCell>
                  <TableCell align="right">Omitidos (esperado)</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {resultado.entidades.map((e) => (
                  <TableRow key={e.entidad}>
                    <TableCell sx={{ textTransform: 'capitalize' }}>{e.entidad}</TableCell>
                    <TableCell align="right">{e.en_ext}</TableCell>
                    <TableCell align="right"><strong>{e.enlazados}</strong></TableCell>
                    <TableCell align="right">{e.ya_enlazados}</TableCell>
                    <TableCell align="right">{e.no_enlazados || '—'}</TableCell>
                    <TableCell align="right">{e.casi_enlazados || '—'}</TableCell>
                    <TableCell align="right">{e.omitidos || '—'}</TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Paper>

          {resultado.hallazgos.length > 0 && (
            <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
              <Box sx={{ p: 2 }}>
                <Alert severity="info" sx={{ mb: 2 }}>
                  Esto es lo que hay que enviarle al equipo técnico de Mallén para corregir.
                </Alert>
                <Table size="small">
                  <TableHead>
                    <TableRow>
                      <TableCell>Entidad</TableCell><TableCell>Código</TableCell>
                      <TableCell>Problema</TableCell><TableCell>Severidad</TableCell>
                    </TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.hallazgos.map((h, i) => (
                      <TableRow key={`${h.entidad}-${h.codigo_externo}-${i}`}>
                        <TableCell sx={{ textTransform: 'capitalize' }}>{h.entidad}</TableCell>
                        <TableCell>{h.codigo_externo}</TableCell>
                        <TableCell>{h.problema}</TableCell>
                        <TableCell>
                          <Chip size="small" label={h.severidad}
                            color={h.severidad === 'error' ? 'error' : 'warning'} />
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </Box>
            </Paper>
          )}
        </>
      )}
    </Box>
  );
}
