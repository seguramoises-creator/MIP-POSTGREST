/**
 * PlanBrechas.tsx — Plan de Cierre de Brechas (§12).
 *
 * Vista consolidada de las alertas que el motor de reglas deriva del KPI de
 * Refuerzo. No captura datos: muestra las 5 causas ya distinguidas (contenido,
 * equipo, material, escalamiento, operación) priorizadas, y desde cada una
 * ofrece el salto a la acción concreta (Refuerzo, Coaching, Biblioteca, LSII).
 *
 * País y ciclo vienen del encabezado global (useCicloStore); la página no los
 * duplica. Las acciones de escritura (generar, atender, umbrales) se muestran
 * solo a los roles de Capacitación —el backend igual las rechaza al resto—.
 */
import { useMemo, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, Chip, Button, Stack, Alert,
  CircularProgress, FormControlLabel, Switch, Divider, Tooltip,
  Dialog, DialogTitle, DialogContent, DialogActions, TextField, MenuItem,
} from '@mui/material';
import {
  AutoAwesome, CheckCircleOutline, ArrowForward, Tune, Refresh,
  ReportProblem, Groups, MenuBook, School,
} from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import {
  listarBrechas, generarPlanBrechas, atenderBrecha,
  obtenerUmbralesBrechas, fijarUmbralBrecha,
  type AlertaBrechaPersistida, type PrioridadBrecha, type ReglaBrecha,
} from '../../services/formacion.service';
import { AVISO, AVISO_TENUE, ERROR, SUPERFICIE_3, TAUPE_MEDIO } from '../../theme/marca';

// Roles que operan el plan (coincide con RequireCapacitacion del backend).
const ROLES_ESCRITURA = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION'];

const PRIORIDAD: Record<PrioridadBrecha, { label: string; color: string; bg: string; orden: number }> = {
  alta:        { label: 'Alta',        color: ERROR, bg: '#ffebee', orden: 0 },
  media:       { label: 'Media',       color: AVISO, bg: AVISO_TENUE, orden: 1 },
  informativa: { label: 'Informativa', color: TAUPE_MEDIO, bg: SUPERFICIE_3, orden: 2 },
};

// Etiqueta legible + ícono por regla. El texto explica en una línea qué causa
// distingue la regla, que es justo lo que no se ve en el KPI crudo.
const REGLA: Record<ReglaBrecha, { titulo: string; icono: React.ReactNode }> = {
  contenido_generalizado:  { titulo: 'Vacío de contenido (a todo el equipo)', icono: <MenuBook fontSize="small" /> },
  concentrada_equipo_pais: { titulo: 'Problema localizado (un equipo/país)',  icono: <Groups fontSize="small" /> },
  material_no_personas:    { titulo: 'Material mal escrito (no las personas)', icono: <MenuBook fontSize="small" /> },
  escalamiento_individual: { titulo: 'Escalamiento individual a Coaching',     icono: <ReportProblem fontSize="small" /> },
  operativa_gestion:       { titulo: 'Adopción / operación (no contenido)',    icono: <School fontSize="small" /> },
};

const ORDEN_PRIORIDAD = (a: AlertaBrechaPersistida, b: AlertaBrechaPersistida) =>
  PRIORIDAD[a.prioridad].orden - PRIORIDAD[b.prioridad].orden;

function TarjetaResumen({ label, valor, color }: { label: string; valor: number; color: string }) {
  return (
    <Card elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, borderTop: `3px solid ${color}` }}>
      <CardContent sx={{ py: 1.5, px: 2, '&:last-child': { pb: 1.5 } }}>
        <Typography variant="caption" color="text.secondary"
          sx={{ fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', fontSize: '0.65rem' }}>
          {label}
        </Typography>
        <Typography variant="h4" fontWeight={800} sx={{ color, lineHeight: 1.1, mt: 0.5 }}>{valor}</Typography>
      </CardContent>
    </Card>
  );
}

export default function PlanBrechas() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const rol = useAuthStore((s) => s.rol);
  const puedeEscribir = !!rol && ROLES_ESCRITURA.includes(rol);

  const qc = useQueryClient();
  const [incluirAtendidas, setIncluirAtendidas] = useState(false);
  const [umbralesAbierto, setUmbralesAbierto] = useState(false);

  const clave = ['brechas', paisCodigo, cicloId, incluirAtendidas] as const;
  const { data: alertas, isLoading, isError } = useQuery({
    queryKey: clave,
    queryFn: () => listarBrechas({
      pais_codigo: paisCodigo!, ciclo_id: cicloId, incluir_atendidas: incluirAtendidas,
    }),
    enabled: !!paisCodigo,
  });

  const generar = useMutation({
    mutationFn: () => generarPlanBrechas({ pais_codigo: paisCodigo!, ciclo_id: cicloId }),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['brechas', paisCodigo] }),
  });

  const atender = useMutation({
    mutationFn: (id: number) => atenderBrecha(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ['brechas', paisCodigo] }),
  });

  const ordenadas = useMemo(() => [...(alertas || [])].sort(ORDEN_PRIORIDAD), [alertas]);
  const conteo = useMemo(() => {
    const c: Record<PrioridadBrecha, number> = { alta: 0, media: 0, informativa: 0 };
    for (const a of alertas || []) if (!a.atendida) c[a.prioridad]++;
    return c;
  }, [alertas]);

  if (!paisCodigo) {
    return <Alert severity="info" sx={{ m: 3 }}>Selecciona un país en el encabezado para ver el plan.</Alert>;
  }

  return (
    <Box sx={{ p: 3 }}>
      {/* Encabezado */}
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={2} mb={1}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Plan de Cierre de Brechas</Typography>
          <Typography variant="body2" color="text.secondary">
            Alertas priorizadas del KPI de Refuerzo — cada una distingue una causa distinta y lleva a su acción.
          </Typography>
        </Box>
        <Stack direction="row" spacing={1}>
          <Tooltip title="Recalcular alertas desde el KPI vigente">
            <span>
              <Button variant="outlined" startIcon={<Refresh />}
                onClick={() => qc.invalidateQueries({ queryKey: ['brechas', paisCodigo] })}>
                Refrescar
              </Button>
            </span>
          </Tooltip>
          {puedeEscribir && (
            <>
              <Button variant="outlined" startIcon={<Tune />} onClick={() => setUmbralesAbierto(true)}>
                Umbrales
              </Button>
              <Button variant="contained" startIcon={<AutoAwesome />}
                disabled={generar.isPending} onClick={() => generar.mutate()}>
                {generar.isPending ? 'Generando…' : 'Generar plan'}
              </Button>
            </>
          )}
        </Stack>
      </Stack>

      {generar.isSuccess && (
        <Alert severity="success" sx={{ mb: 2 }} onClose={() => generar.reset()}>
          Plan regenerado: {generar.data.total} alerta(s). Es una foto del estado actual — reemplaza la anterior.
        </Alert>
      )}
      {generar.isError && (
        <Alert severity="error" sx={{ mb: 2 }} onClose={() => generar.reset()}>
          No se pudo generar el plan. Revisa que el ciclo esté abierto y haya datos de Refuerzo.
        </Alert>
      )}

      {/* Resumen por prioridad */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={4}><TarjetaResumen label="Prioridad alta" valor={conteo.alta} color={PRIORIDAD.alta.color} /></Grid>
        <Grid item xs={4}><TarjetaResumen label="Prioridad media" valor={conteo.media} color={PRIORIDAD.media.color} /></Grid>
        <Grid item xs={4}><TarjetaResumen label="Informativas" valor={conteo.informativa} color={PRIORIDAD.informativa.color} /></Grid>
      </Grid>

      <FormControlLabel
        control={<Switch checked={incluirAtendidas} onChange={(e) => setIncluirAtendidas(e.target.checked)} />}
        label="Incluir atendidas"
        sx={{ mb: 1 }}
      />

      {/* Lista de alertas */}
      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 6 }}><CircularProgress /></Box>
      ) : isError ? (
        <Alert severity="error">No se pudieron cargar las alertas.</Alert>
      ) : ordenadas.length === 0 ? (
        <Alert severity="success" icon={<CheckCircleOutline />}>
          Sin brechas detectadas para este país y ciclo.
          {puedeEscribir && ' Genera el plan si acabas de cargar respuestas de Refuerzo.'}
        </Alert>
      ) : (
        <Stack spacing={1.5}>
          {ordenadas.map((a) => (
            <TarjetaAlerta key={a.id} alerta={a} puedeEscribir={puedeEscribir}
              onAtender={() => atender.mutate(a.id)} atendiendo={atender.isPending} />
          ))}
        </Stack>
      )}

      {umbralesAbierto && paisCodigo && (
        <DialogoUmbrales paisCodigo={paisCodigo} onCerrar={() => setUmbralesAbierto(false)} />
      )}
    </Box>
  );
}

function TarjetaAlerta({ alerta, puedeEscribir, onAtender, atendiendo }: {
  alerta: AlertaBrechaPersistida; puedeEscribir: boolean;
  onAtender: () => void; atendiendo: boolean;
}) {
  const navigate = useNavigate();
  const p = PRIORIDAD[alerta.prioridad];
  const r = REGLA[alerta.regla_aplicada];

  return (
    <Card elevation={0} sx={{
      border: '1px solid #e0e7ef', borderRadius: 2, borderLeft: `4px solid ${p.color}`,
      opacity: alerta.atendida ? 0.6 : 1,
    }}>
      <CardContent sx={{ py: 1.75, px: 2 }}>
        <Stack direction="row" justifyContent="space-between" alignItems="flex-start" gap={2} flexWrap="wrap">
          <Box sx={{ flex: 1, minWidth: 260 }}>
            <Stack direction="row" spacing={1} alignItems="center" mb={0.5} flexWrap="wrap">
              <Chip size="small" label={p.label} sx={{ bgcolor: p.bg, color: p.color, fontWeight: 700 }} />
              <Chip size="small" variant="outlined" icon={r.icono as any} label={r.titulo} />
              <Chip size="small" variant="outlined" label={alerta.alcance} />
              {alerta.atendida && <Chip size="small" color="success" label="Atendida" />}
            </Stack>
            <Typography variant="body2" sx={{ mb: 0.75 }}>{alerta.descripcion}</Typography>
            <Typography variant="body2" sx={{ color: 'text.secondary' }}>
              <strong>Acción sugerida:</strong> {alerta.accion_sugerida}
            </Typography>
          </Box>
          <Stack spacing={1} sx={{ minWidth: 160 }}>
            {alerta.link_accion && (
              <Button size="small" variant="contained" endIcon={<ArrowForward />}
                onClick={() => navigate(alerta.link_accion!)}>
                Ir a la acción
              </Button>
            )}
            {puedeEscribir && !alerta.atendida && (
              <Button size="small" variant="outlined" startIcon={<CheckCircleOutline />}
                disabled={atendiendo} onClick={onAtender}>
                Marcar atendida
              </Button>
            )}
          </Stack>
        </Stack>
      </CardContent>
    </Card>
  );
}

function DialogoUmbrales({ paisCodigo, onCerrar }: { paisCodigo: string; onCerrar: () => void }) {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ['brechas-umbrales', paisCodigo],
    queryFn: () => obtenerUmbralesBrechas(paisCodigo),
  });
  const [clave, setClave] = useState('');
  const [valor, setValor] = useState('');

  const fijar = useMutation({
    mutationFn: () => fijarUmbralBrecha({ pais_codigo: paisCodigo, clave, valor: Number(valor) }),
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ['brechas-umbrales', paisCodigo] });
      setClave(''); setValor('');
    },
  });

  return (
    <Dialog open onClose={onCerrar} maxWidth="sm" fullWidth>
      <DialogTitle>Umbrales de las reglas — {paisCodigo}</DialogTitle>
      <DialogContent dividers>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Valores de arranque del §12.2, ajustables por país sin tocar código. Cambiar uno
          reevalúa las reglas en la próxima generación.
        </Typography>
        {isLoading ? (
          <Box sx={{ display: 'flex', justifyContent: 'center', py: 3 }}><CircularProgress /></Box>
        ) : (
          <>
            <Stack spacing={0.5} sx={{ mb: 2 }}>
              {Object.entries(data?.valores || {}).map(([k, v]) => (
                <Stack key={k} direction="row" justifyContent="space-between">
                  <Typography variant="body2" sx={{ fontFamily: 'monospace' }}>{k}</Typography>
                  <Typography variant="body2" fontWeight={700}>{v}</Typography>
                </Stack>
              ))}
            </Stack>
            <Divider sx={{ mb: 2 }} />
            <Stack direction="row" spacing={1} alignItems="flex-start">
              <TextField select size="small" label="Umbral" value={clave}
                onChange={(e) => setClave(e.target.value)} sx={{ flex: 1 }}>
                {(data?.claves_validas || []).map((k) => (
                  <MenuItem key={k} value={k}>{k}</MenuItem>
                ))}
              </TextField>
              <TextField size="small" label="Valor" type="number" value={valor}
                onChange={(e) => setValor(e.target.value)} sx={{ width: 120 }} />
              <Button variant="contained" disabled={!clave || valor === '' || fijar.isPending}
                onClick={() => fijar.mutate()} sx={{ mt: 0.25 }}>
                Fijar
              </Button>
            </Stack>
            {fijar.isError && <Alert severity="error" sx={{ mt: 1 }}>No se pudo fijar el umbral.</Alert>}
            {fijar.isSuccess && <Alert severity="success" sx={{ mt: 1 }}>Umbral actualizado.</Alert>}
          </>
        )}
      </DialogContent>
      <DialogActions>
        <Button onClick={onCerrar}>Cerrar</Button>
      </DialogActions>
    </Dialog>
  );
}
