/**
 * CalendarioCoaching.tsx — Calendario de Coaching (§7).
 * Cuadrícula RM × semanas alimentada por el cuadrante LSII vigente. El GD ve su
 * equipo; ADMIN/GERPROD eligen GD. Editable y publicable; solo-lectura si el
 * ciclo está cerrado. La config de frecuencias va en un diálogo (patrón Umbrales
 * de la Fase 7).
 */
import { useEffect, useMemo, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Chip, Button, Stack, Alert, CircularProgress,
  Table, TableBody, TableCell, TableHead, TableRow, TextField, MenuItem,
  Dialog, DialogTitle, DialogContent, DialogActions, Divider,
} from '@mui/material';
import { AutoAwesome, Tune, PublishedWithChanges } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import {
  generarCalendario, listarCalendario, moverCelda, publicarCalendario,
  obtenerFrecuenciasLSII, fijarFrecuenciaLSII,
  type CeldaCalendario, type GenerarCalendarioResp,
} from '../../services/formacion.service';
import { api } from '../../services/api';

const DIAS = ['lunes', 'martes', 'miercoles', 'jueves', 'viernes'];
const ROLES_ESCRITURA = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'GERENTE_DISTRITO'];
// PUT /formacion/calendario-coaching/frecuencias está gateado en backend a
// ADMIN y GERENTE_PRODUCTIVIDAD (RequireConfig) — el GD NO puede fijar frecuencias,
// solo consultarlas (GET, RequireLectura).
const ROLES_CONFIG = ['ADMIN', 'GERENTE_PRODUCTIVIDAD'];
const CUAD_COLOR: Record<string, string> = {
  D1: '#c62828', D2: '#e65100', D3: '#1565c0', D4: '#2e7d32',
};

export default function CalendarioCoaching() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const soloLectura = useCicloStore((s) => s.esSoloLectura);
  const rol = useAuthStore((s) => s.rol);
  const esGD = rol === 'GERENTE_DISTRITO';
  const puedeEscribir = !!rol && ROLES_ESCRITURA.includes(rol) && !soloLectura;
  const puedeConfig = !!rol && ROLES_CONFIG.includes(rol) && !soloLectura;
  const qc = useQueryClient();

  const [gdId, setGdId] = useState<number | ''>('');
  const [frecAbierto, setFrecAbierto] = useState(false);
  const [previa, setPrevia] = useState<GenerarCalendarioResp | null>(null);

  // ADMIN/GERPROD eligen GD; el GD no ve el selector.
  const { data: gerentes } = useQuery({
    queryKey: ['gerentes', paisCodigo],
    queryFn: () => api.get('/admin/gerentes', { params: { pais_codigo: paisCodigo } }).then((r) => r.data),
    enabled: !!paisCodigo && !esGD,
  });

  const gdParam = esGD ? undefined : (gdId === '' ? undefined : Number(gdId));
  const listo = !!cicloId && (esGD || gdParam != null);

  const { data: celdas, isLoading } = useQuery({
    queryKey: ['calendario', cicloId, gdParam],
    queryFn: () => listarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    enabled: listo,
  });

  const generar = useMutation({
    mutationFn: () => generarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    onSuccess: (r) => { setPrevia(r); qc.invalidateQueries({ queryKey: ['calendario', cicloId] }); },
  });
  const publicar = useMutation({
    mutationFn: () => publicarCalendario({ ciclo_id: cicloId!, gd_id: gdParam }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendario', cicloId] }),
  });
  const mover = useMutation({
    mutationFn: (v: { id: number; semana: number; dia: string }) => moverCelda(v.id, v.semana, v.dia),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['calendario', cicloId] }),
  });

  useEffect(() => { setPrevia(null); generar.reset(); }, [cicloId]);
  useEffect(() => { setGdId(''); setPrevia(null); generar.reset(); }, [paisCodigo]);

  const semanas = previa?.semanas ?? Math.max(8, ...(celdas || []).map((c) => c.semana));
  const porRm = useMemo(() => {
    const m = new Map<number, CeldaCalendario[]>();
    for (const c of celdas || []) { if (!m.has(c.rm_id)) m.set(c.rm_id, []); m.get(c.rm_id)!.push(c); }
    return m;
  }, [celdas]);

  if (!paisCodigo) return <Alert severity="info" sx={{ m: 3 }}>Selecciona un país en el encabezado.</Alert>;

  return (
    <Box sx={{ p: 3 }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={1}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Calendario de Coaching</Typography>
          <Typography variant="body2" color="text.secondary">
            Acompañamientos sugeridos por cuadrante LSII, repartidos en el ciclo.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1} alignItems="center">
          {!esGD && (
            <TextField select size="small" label="Gerente de Distrito" value={gdId}
              onChange={(e) => {
                setGdId(e.target.value === '' ? '' : Number(e.target.value));
                setPrevia(null);
                generar.reset();
              }} sx={{ minWidth: 200 }}>
              <MenuItem value="">—</MenuItem>
              {(gerentes || []).filter((g: any) => g.tipo === 'DISTRITO').map((g: any) => (
                <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>
              ))}
            </TextField>
          )}
          {puedeEscribir && (
            <>
              <Button variant="outlined" startIcon={<Tune />} onClick={() => setFrecAbierto(true)}>Frecuencias</Button>
              <Button variant="contained" startIcon={<AutoAwesome />} disabled={!listo || generar.isPending}
                onClick={() => generar.mutate()}>{generar.isPending ? 'Generando…' : 'Generar'}</Button>
              <Button variant="outlined" startIcon={<PublishedWithChanges />} disabled={!listo || publicar.isPending}
                onClick={() => publicar.mutate()}>Publicar</Button>
            </>
          )}
        </Stack>
      </Stack>

      {generar.isSuccess && previa && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => generar.reset()}>
          Calendario generado sobre {previa.semanas} semanas.
          {previa.sin_evaluar.length > 0 &&
            ` ${previa.sin_evaluar.length} RM sin evaluación LSII no se agendaron.`}
        </Alert>
      )}
      {generar.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => generar.reset()}>
          No se pudo generar el calendario. Revisa que el ciclo esté abierto.
        </Alert>
      )}
      {publicar.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => publicar.reset()}>
          No se pudo publicar.
        </Alert>
      )}

      {!listo ? (
        <Alert severity="info">{esGD ? 'Selecciona un ciclo.' : 'Elige un Gerente de Distrito y un ciclo.'}</Alert>
      ) : isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : (celdas || []).length === 0 ? (
        <Alert severity="info">Sin calendario para este GD y ciclo. {puedeEscribir && 'Genera uno.'}</Alert>
      ) : (
        <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, overflowX: 'auto' }}>
          <CardContent>
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>RM</TableCell>
                  {Array.from({ length: semanas }, (_, i) => (
                    <TableCell key={i} align="center">Sem {i + 1}</TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {[...porRm.entries()].map(([rmId, cs]) => {
                  const cuad = cs[0]?.cuadrante ?? '';
                  return (
                    <TableRow key={rmId}>
                      <TableCell>
                        <Stack direction="row" spacing={1} alignItems="center">
                          <Chip size="small" label={cuad}
                            sx={{ bgcolor: CUAD_COLOR[cuad] || '#777', color: '#fff', fontWeight: 700 }} />
                          <span>RM #{rmId}</span>
                        </Stack>
                      </TableCell>
                      {Array.from({ length: semanas }, (_, i) => {
                        const c = cs.find((x) => x.semana === i + 1);
                        return (
                          <TableCell key={i} align="center">
                            {c ? (
                              <TextField select size="small" variant="standard" value={c.dia_semana}
                                disabled={!puedeEscribir || c.publicado}
                                onChange={(e) => mover.mutate({ id: c.id, semana: c.semana, dia: e.target.value })}>
                                {DIAS.map((d) => <MenuItem key={d} value={d}>{d.slice(0, 3)}</MenuItem>)}
                              </TextField>
                            ) : '·'}
                          </TableCell>
                        );
                      })}
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </CardContent>
        </Card>
      )}

      {frecAbierto && paisCodigo && (
        <DialogoFrecuencias paisCodigo={paisCodigo} puedeEscribir={puedeConfig}
          onCerrar={() => setFrecAbierto(false)} />
      )}
    </Box>
  );
}

function DialogoFrecuencias({ paisCodigo, puedeEscribir, onCerrar }: {
  paisCodigo: string; puedeEscribir: boolean; onCerrar: () => void;
}) {
  // `puedeEscribir` aquí gobierna SOLO el formulario de "Fijar" (PUT /frecuencias,
  // ADMIN/GERENTE_PRODUCTIVIDAD). El GET de valores vigentes es lectura y ya
  // llegó a este diálogo para cualquier rol con RequireLectura en el backend.
  const qc = useQueryClient();
  const { data } = useQuery({
    queryKey: ['frecuencias-lsii', paisCodigo],
    queryFn: () => obtenerFrecuenciasLSII(paisCodigo),
  });
  const [cuadrante, setCuadrante] = useState('');
  const [valor, setValor] = useState('');
  const fijar = useMutation({
    mutationFn: () => fijarFrecuenciaLSII({ pais_codigo: paisCodigo, cuadrante, visitas_por_ciclo: Number(valor) }),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ['frecuencias-lsii', paisCodigo] }); setCuadrante(''); setValor(''); },
  });
  return (
    <Dialog open onClose={onCerrar} maxWidth="xs" fullWidth>
      <DialogTitle>Frecuencia por cuadrante — {paisCodigo}</DialogTitle>
      <DialogContent dividers>
        <Stack spacing={0.5} sx={{ mb: 2 }}>
          {Object.entries(data?.valores || {}).map(([k, v]) => (
            <Stack key={k} direction="row" justifyContent="space-between">
              <Typography variant="body2" fontWeight={700}>{k}</Typography>
              <Typography variant="body2">{v} visita(s)/ciclo</Typography>
            </Stack>
          ))}
        </Stack>
        {puedeEscribir && (
          <>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" spacing={1}>
              <TextField select size="small" label="Cuadrante" value={cuadrante}
                onChange={(e) => setCuadrante(e.target.value)} sx={{ flex: 1 }}>
                {(data?.cuadrantes || []).map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
              <TextField size="small" type="number" label="Visitas" value={valor}
                onChange={(e) => setValor(e.target.value)} sx={{ width: 100 }} />
              <Button variant="contained" disabled={!cuadrante || valor === '' || fijar.isPending}
                onClick={() => fijar.mutate()}>Fijar</Button>
            </Stack>
            {fijar.isError && (
              <Alert severity="error" sx={{ mt: 1 }}>No se pudo fijar la frecuencia.</Alert>
            )}
            {fijar.isSuccess && (
              <Alert severity="success" sx={{ mt: 1 }}>Frecuencia actualizada.</Alert>
            )}
          </>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onCerrar}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
