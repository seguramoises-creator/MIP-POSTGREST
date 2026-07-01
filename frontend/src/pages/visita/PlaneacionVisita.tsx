import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Stack, Chip, Alert, MenuItem,
  Select, FormControl, CircularProgress, Table, TableHead, TableRow, TableCell,
  TableBody, Grid, Tooltip, TextField,
} from '@mui/material';
import { Save, EventNote, Warning, CheckCircle } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarMedicos, obtenerPlaneacion, planeacionResumen, guardarPlaneacion, listarVMs,
  type MedicoVisita, type PlaneacionItem, type PlaneacionResumen, type Catalogo,
} from '../../services/visita.service';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

// Estado por médico: semana de Vista (0 = no planeada) y semana de Revisita (0 = ninguna).
interface Fila { vSemana: number; rSemana: number; }
const SEMANAS = [1, 2, 3, 4];

export default function PlaneacionVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');        // solo ADMIN/GERENTE
  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [plan, setPlan] = useState<Record<number, Fila>>({});
  const [resumen, setResumen] = useState<PlaneacionResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // El RM planifica su propio panel (backend fuerza rm_id); ADMIN/GERENTE eligen un VM.
  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  // Lista de visitadores (solo para ADMIN/GERENTE).
  useEffect(() => { if (!esVM) listarVMs().then(setVms).catch(() => {}); }, [esVM]);

  const cargar = useCallback(async () => {
    if (!listo) { setMedicos([]); setPlan({}); setResumen(null); setCargando(false); return; }
    setCargando(true);
    try {
      const [m, p, r] = await Promise.all([
        listarMedicos(vmParam), obtenerPlaneacion(vmParam), planeacionResumen(vmParam)]);
      setMedicos(m);
      setResumen(r);
      const mapa: Record<number, Fila> = {};
      m.forEach((med) => { mapa[med.id] = { vSemana: 0, rSemana: 0 }; });
      p.forEach((it: PlaneacionItem) => {
        if (!mapa[it.medico_id]) mapa[it.medico_id] = { vSemana: 0, rSemana: 0 };
        if (it.tipo_visita === 'V') mapa[it.medico_id].vSemana = it.semana;
        else mapa[it.medico_id].rSemana = it.semana;
      });
      setPlan(mapa);
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo cargar la planeación.' });
    } finally { setCargando(false); }
  }, [listo, vmParam]);
  useEffect(() => { cargar(); }, [cargar]);

  const setV = (id: number, v: number) =>
    setPlan((p) => ({ ...p, [id]: { vSemana: v, rSemana: v === 0 ? 0 : p[id]?.rSemana ?? 0 } }));
  const setR = (id: number, r: number) =>
    setPlan((p) => ({ ...p, [id]: { ...p[id], rSemana: r } }));

  // Métricas en vivo (previa a guardar) para feedback inmediato.
  const vivo = useMemo(() => {
    const filas = Object.values(plan);
    const conVista = filas.filter((f) => f.vSemana > 0).length;
    const total = filas.reduce((s, f) => s + (f.vSemana > 0 ? 1 : 0) + (f.rSemana > 0 ? 1 : 0), 0);
    const catA = medicos.filter((m) => m.categoria === 'A');
    const catASinRe = catA.filter((m) => (plan[m.id]?.rSemana ?? 0) === 0).length;
    const panel = medicos.length;
    return {
      conVista, total, catASinRe, panel,
      cobertura: panel ? Math.round((conVista / panel) * 1000) / 10 : 0,
    };
  }, [plan, medicos]);

  async function guardar() {
    setGuardando(true); setMsg(null);
    const items: PlaneacionItem[] = [];
    for (const [idStr, f] of Object.entries(plan)) {
      const id = Number(idStr);
      if (f.vSemana > 0) items.push({ medico_id: id, tipo_visita: 'V', semana: f.vSemana });
      if (f.rSemana > 0) items.push({ medico_id: id, tipo_visita: 'R', semana: f.rSemana });
    }
    try {
      const res = await guardarPlaneacion(items, vmParam);
      setMsg({ tipo: 'success', texto: `Planeación guardada (${res.guardadas} ítems).` });
      const r = await planeacionResumen(vmParam);
      setResumen(r);
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo guardar la planeación.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const kpi = (label: string, valor: string | number, color = 'text.primary') => (
    <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
      <Typography variant="caption" color="text.secondary">{label}</Typography>
      <Typography variant="h5" fontWeight={700} sx={{ color }}>{valor}</Typography>
    </CardContent></Card>
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <EventNote color="primary" />
        <Typography variant="h5" fontWeight={700}>Planeación del Ciclo</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Asigna a cada médico su semana de Vista (V) y, opcionalmente, una Revisita (R) en la misma
        semana o posterior. La Revisita requiere una Vista. Máximo 1 V + 1 R por médico.
      </Typography>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* Selector de visitador: solo ADMIN/GERENTE. El RM planifica su propio panel. */}
      {!esVM && (
        <TextField select fullWidth size="small" label="Visitador (VM)" value={vmId} sx={{ mb: 2, maxWidth: 420 }}
                   helperText="Elige el visitador cuyo ciclo vas a planificar"
                   onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
          <MenuItem value=""><em>— Selecciona un visitador —</em></MenuItem>
          {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
        </TextField>
      )}

      {!listo ? (
        <Alert severity="info">Selecciona un visitador para planificar su ciclo.</Alert>
      ) : (
      <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} sm={3}>{kpi('Panel', vivo.panel)}</Grid>
        <Grid item xs={6} sm={3}>{kpi('Cobertura planeada', `${vivo.cobertura}%`, 'primary.main')}</Grid>
        <Grid item xs={6} sm={3}>{kpi('Visitas planeadas', vivo.total)}</Grid>
        <Grid item xs={6} sm={3}>
          {kpi('Cat. A sin Revisita', vivo.catASinRe, vivo.catASinRe > 0 ? 'warning.main' : 'success.main')}
        </Grid>
      </Grid>

      {vivo.catASinRe > 0 && (
        <Alert severity="warning" icon={<Warning />} sx={{ mb: 2 }}>
          Hay {vivo.catASinRe} médico(s) categoría A sin Revisita planeada. Los A deberían llevar V+R.
        </Alert>
      )}

      <Card variant="outlined" sx={{ mb: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Médico</TableCell>
                <TableCell align="center">Cat.</TableCell>
                <TableCell align="center">Vista (semana)</TableCell>
                <TableCell align="center">Revisita (semana)</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {medicos.length === 0 && (
                <TableRow><TableCell colSpan={4}>
                  <Alert severity="info" sx={{ my: 1 }}>No hay médicos en tu panel. Regístralos en Panel Médico.</Alert>
                </TableCell></TableRow>
              )}
              {medicos.map((m) => {
                const f = plan[m.id] ?? { vSemana: 0, rSemana: 0 };
                return (
                  <TableRow key={m.id} hover>
                    <TableCell>{m.nombre_completo}</TableCell>
                    <TableCell align="center">
                      <Chip size="small" label={m.categoria}
                            color={m.categoria === 'A' ? 'error' : m.categoria === 'B' ? 'warning' : 'default'} />
                    </TableCell>
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 90 }}>
                        <Select value={f.vSemana} onChange={(e) => setV(m.id, Number(e.target.value))}>
                          <MenuItem value={0}><em>—</em></MenuItem>
                          {SEMANAS.map((s) => <MenuItem key={s} value={s}>Sem {s}</MenuItem>)}
                        </Select>
                      </FormControl>
                    </TableCell>
                    <TableCell align="center">
                      <Tooltip title={f.vSemana === 0 ? 'Primero asigna la Vista' : `Debe ir en semana ≥ ${f.vSemana}`}>
                        <FormControl size="small" sx={{ minWidth: 90 }}>
                          <Select value={f.rSemana} disabled={f.vSemana === 0}
                                  onChange={(e) => setR(m.id, Number(e.target.value))}>
                            <MenuItem value={0}><em>Sin R</em></MenuItem>
                            {SEMANAS.filter((s) => s >= f.vSemana).map((s) => (
                              <MenuItem key={s} value={s}>Sem {s}</MenuItem>
                            ))}
                          </Select>
                        </FormControl>
                      </Tooltip>
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </Card>

      <Stack direction="row" spacing={2} alignItems="center">
        <Button variant="contained" startIcon={<Save />} disabled={guardando || medicos.length === 0} onClick={guardar}>
          {guardando ? 'Guardando…' : 'Guardar planeación'}
        </Button>
        {resumen && (
          <Stack direction="row" spacing={1} alignItems="center" color="text.secondary">
            <CheckCircle fontSize="small" color="success" />
            <Typography variant="body2">
              Guardado: {resumen.total_planeadas} visitas · {resumen.cobertura_planeada_pct}% cobertura · {resumen.carga_por_dia}/día
            </Typography>
          </Stack>
        )}
      </Stack>
      </>
      )}
    </Box>
  );
}
