import { useEffect, useMemo, useState, useCallback, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Stack, Chip, Alert, MenuItem,
  Select, FormControl, CircularProgress, Table, TableHead, TableRow, TableCell,
  TableBody, Grid, Tooltip, TextField, Avatar, Divider,
} from '@mui/material';
import { Save, EventNote, Warning, CheckCircle, FilterList, Search, Badge, SupervisorAccount, Layers } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import {
  listarMedicos, obtenerPlaneacion, planeacionResumen, guardarPlaneacion, listarVMs, miGerente,
  type MedicoVisita, type PlaneacionItem, type PlaneacionResumen, type Catalogo, type MiGerente,
} from '../../services/visita.service';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

// Estado por médico: semana + día de la Vista, y (opcional) Revisita con su semana + día.
interface Fila { vSemana: number; vDia: string; revisita: boolean; rSemana: number; rDia: string; }
const F0: Fila = { vSemana: 0, vDia: '', revisita: false, rSemana: 0, rDia: '' };
const SEMANAS = [1, 2, 3, 4];
const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'];

// La revisita se intercala 2 semanas después (Sem 1→3, Sem 2→4); solo aplica a Vistas en Sem 1 o 2.
const revisitaPermitida = (vSemana: number) => vSemana === 1 || vSemana === 2;
const propuestaRevisita = (vSemana: number) => vSemana + 2;

export default function PlaneacionVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');        // solo ADMIN/GERENTE
  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [plan, setPlan] = useState<Record<number, Fila>>({});
  const [resumen, setResumen] = useState<PlaneacionResumen | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [catFiltro, setCatFiltro] = useState('');   // '' = todas
  const [busqueda, setBusqueda] = useState('');
  // Ficha del representante (Gerente de Distrito + Línea) — viene de la dim del RM.
  const [infoRep, setInfoRep] = useState<MiGerente | null>(null);

  // Filtro visual (no afecta el guardado: se persiste TODO el plan, no solo lo visible).
  const medicosVisibles = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return medicos.filter((m) =>
      (!catFiltro || m.categoria === catFiltro) &&
      (!q || (m.nombre_completo ?? '').toUpperCase().includes(q)));
  }, [medicos, catFiltro, busqueda]);

  // El RM planifica su propio panel (backend fuerza rm_id); ADMIN/GERENTE eligen un VM.
  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  // Lista de visitadores (solo para ADMIN/GERENTE).
  useEffect(() => { if (!esVM) listarVMs().then(setVms).catch(() => {}); }, [esVM]);

  // Ficha del representante: el VM ve la suya; ADMIN/GERENTE la del VM seleccionado.
  useEffect(() => {
    if (esVM) miGerente().then(setInfoRep).catch(() => setInfoRep(null));
    else if (vmId) miGerente(Number(vmId)).then(setInfoRep).catch(() => setInfoRep(null));
    else setInfoRep(null);
  }, [esVM, vmId]);

  const cargar = useCallback(async () => {
    if (!listo) { setMedicos([]); setPlan({}); setResumen(null); setCargando(false); return; }
    setCargando(true);
    try {
      const [m, p, r] = await Promise.all([
        listarMedicos(vmParam), obtenerPlaneacion(vmParam), planeacionResumen(vmParam)]);
      setMedicos(m);
      setResumen(r);
      const mapa: Record<number, Fila> = {};
      m.forEach((med) => { mapa[med.id] = { ...F0 }; });
      p.forEach((it: PlaneacionItem) => {
        if (!mapa[it.medico_id]) mapa[it.medico_id] = { ...F0 };
        if (it.tipo_visita === 'V') {
          mapa[it.medico_id].vSemana = it.semana;
          mapa[it.medico_id].vDia = it.dia_semana ?? '';
        } else {
          mapa[it.medico_id].revisita = true;
          mapa[it.medico_id].rSemana = it.semana;
          mapa[it.medico_id].rDia = it.dia_semana ?? '';
        }
      });
      setPlan(mapa);
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo cargar la planeación.' });
    } finally { setCargando(false); }
  }, [listo, vmParam]);
  useEffect(() => { cargar(); }, [cargar]);

  // Semana de la Vista. Si pasa a 0 (sin Vista) o a una semana sin revisita permitida (3/4),
  // apaga la Revisita. Si sigue permitida, re-propone la semana intercalada.
  const setVSemana = (id: number, v: number) => setPlan((p) => {
    const cur = p[id] ?? F0;
    if (v === 0) return { ...p, [id]: { ...F0 } };
    const revisita = cur.revisita && revisitaPermitida(v);
    return { ...p, [id]: {
      ...cur, vSemana: v, revisita,
      rSemana: revisita ? propuestaRevisita(v) : 0,
      rDia: revisita ? cur.vDia : '',
    } };
  });
  // Día de la Vista. El día de la Revisita queda espejado (debe ser el mismo día).
  const setVDia = (id: number, dia: string) => setPlan((p) => {
    const cur = p[id] ?? F0;
    return { ...p, [id]: { ...cur, vDia: dia, rDia: cur.revisita ? dia : cur.rDia } };
  });
  // Revisita Sí/No. Al activar, auto-propone semana intercalada + mismo día de la Vista.
  const toggleRevisita = (id: number, on: boolean) => setPlan((p) => {
    const cur = p[id] ?? F0;
    if (on && revisitaPermitida(cur.vSemana)) {
      return { ...p, [id]: { ...cur, revisita: true, rSemana: propuestaRevisita(cur.vSemana), rDia: cur.vDia } };
    }
    return { ...p, [id]: { ...cur, revisita: false, rSemana: 0, rDia: '' } };
  });
  // La semana de la Revisita es una propuesta editable (debe ser posterior a la Vista).
  const setRSemana = (id: number, s: number) => setPlan((p) => ({ ...p, [id]: { ...(p[id] ?? F0), rSemana: s } }));

  // Métricas en vivo (previa a guardar) para feedback inmediato.
  const vivo = useMemo(() => {
    const filas = Object.values(plan);
    const conVista = filas.filter((f) => f.vSemana > 0).length;
    const conR = filas.filter((f) => f.revisita && f.rSemana > 0).length;
    const catA = medicos.filter((m) => m.categoria === 'A');
    const catASinRe = catA.filter((m) => !plan[m.id]?.revisita).length;
    const panel = medicos.length;
    return {
      conVista, total: conVista + conR, catASinRe, panel,
      cobertura: panel ? Math.round((conVista / panel) * 1000) / 10 : 0,
    };
  }, [plan, medicos]);

  async function guardar() {
    setGuardando(true); setMsg(null);
    const items: PlaneacionItem[] = [];
    for (const [idStr, f] of Object.entries(plan)) {
      const id = Number(idStr);
      if (f.vSemana > 0) items.push({ medico_id: id, tipo_visita: 'V', semana: f.vSemana, dia_semana: f.vDia || null });
      if (f.revisita && f.rSemana > 0) {
        items.push({ medico_id: id, tipo_visita: 'R', semana: f.rSemana, dia_semana: (f.rDia || f.vDia) || null });
      }
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
  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  const infoDato = (icono: ReactNode, label: string, valor: string) => (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
      <Avatar sx={{ bgcolor: 'primary.main', color: '#fff', width: 32, height: 32 }}>{icono}</Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.1, fontWeight: 600, letterSpacing: 0.3 }}>{label}</Typography>
        <Typography variant="body2" fontWeight={700} noWrap>{valor}</Typography>
      </Box>
    </Stack>
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <EventNote color="primary" />
        <Typography variant="h5" fontWeight={700}>Planeación del Ciclo</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Ciclo de 4 semanas. Asigna a cada médico la <b>semana</b> (1-4) y el <b>día</b> (Lun-Vie) de la Vista.
        Si marcas <b>Revisita = Sí</b>, se propone la semana intercalada (Sem 1→3, Sem 2→4) el mismo día.
        Máximo 1 Vista + 1 Revisita por médico.
      </Typography>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}
      {esSoloLectura && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Ciclo en solo lectura — el registro de visitas solo está disponible en el ciclo abierto.
        </Alert>
      )}

      {/* El representante (VM) se ELIGE aquí; su Gerente de Distrito y Línea se
          muestran automáticamente (de la dim del RM). Un VM ve su ficha fija. */}
      {(!esVM || (infoRep && (infoRep.vm || infoRep.gerente || infoRep.linea))) && (
        <Card variant="outlined" sx={{ mb: 2, borderColor: 'primary.light', bgcolor: 'rgba(46,91,255,0.05)' }}>
          <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
            <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1.25, sm: 4 }} alignItems={{ sm: 'center' }}
                   flexWrap="wrap"
                   divider={<Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />}>
              <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                <Avatar sx={{ bgcolor: 'primary.main', color: '#fff', width: 32, height: 32 }}><Badge fontSize="small" /></Avatar>
                {esVM ? (
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.1, fontWeight: 600, letterSpacing: 0.3 }}>Representante médico</Typography>
                    <Typography variant="body2" fontWeight={700} noWrap>{infoRep?.vm ?? '—'}</Typography>
                  </Box>
                ) : (
                  <TextField select variant="standard" label="Visitador (VM)" value={vmId} sx={{ minWidth: 240 }}
                             onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
                    <MenuItem value=""><em>— Selecciona un visitador —</em></MenuItem>
                    {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
                  </TextField>
                )}
              </Stack>
              {infoRep?.gerente && infoDato(<SupervisorAccount fontSize="small" />,
                infoRep.gerente_tipo ? `Gerente de ${cap(infoRep.gerente_tipo)}` : 'Gerente de Distrito', infoRep.gerente)}
              {infoRep?.linea && infoDato(<Layers fontSize="small" />, 'Línea', infoRep.linea)}
            </Stack>
          </CardContent>
        </Card>
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

      {/* Filtros (solo afectan lo mostrado; el guardado persiste TODO el panel) */}
      <Card variant="outlined" sx={{ mb: 2, bgcolor: '#f5f8ff', borderColor: '#bbdefb' }}>
        <Box sx={{ p: 1.5 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ color: 'primary.main' }}>
            <FilterList fontSize="small" />
            <Typography variant="body2" fontWeight={700}>Filtrar</Typography>
          </Stack>
          <TextField size="small" label="Buscar médico" value={busqueda} sx={{ minWidth: 240, bgcolor: '#fff' }}
                     onChange={(e) => setBusqueda(e.target.value)} placeholder="Nombre del médico…"
                     InputProps={{ startAdornment: <Search fontSize="small" sx={{ mr: 0.5, color: 'text.disabled' }} /> }} />
          <TextField select size="small" label="Categoría" value={catFiltro} sx={{ minWidth: 160, bgcolor: '#fff' }}
                     onChange={(e) => setCatFiltro(e.target.value)}>
            <MenuItem value="">Todas las categorías</MenuItem>
            {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>Categoría {c}</MenuItem>)}
          </TextField>
          {(busqueda || catFiltro) && (
            <Button size="small" onClick={() => { setBusqueda(''); setCatFiltro(''); }}>Limpiar</Button>
          )}
          <Box sx={{ flex: 1 }} />
          {(busqueda || catFiltro) && (
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              Mostrando {medicosVisibles.length} de {medicos.length}
            </Typography>
          )}
        </Stack>
        </Box>
      </Card>

      <Card variant="outlined" sx={{ mb: 2 }}>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                <TableCell>Médico</TableCell>
                <TableCell align="center">Cat.</TableCell>
                <TableCell align="center">Semana visita</TableCell>
                <TableCell align="center">Día visita</TableCell>
                <TableCell align="center">Revisita</TableCell>
                <TableCell align="center">Semana revisita</TableCell>
                <TableCell align="center">Día revisita</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {medicos.length === 0 && (
                <TableRow><TableCell colSpan={7}>
                  <Alert severity="info" sx={{ my: 1 }}>No hay médicos en tu panel. Regístralos en Panel Médico.</Alert>
                </TableCell></TableRow>
              )}
              {medicos.length > 0 && medicosVisibles.length === 0 && (
                <TableRow><TableCell colSpan={7}>
                  <Alert severity="info" sx={{ my: 1 }}>Ningún médico coincide con el filtro.</Alert>
                </TableCell></TableRow>
              )}
              {medicosVisibles.map((m) => {
                const f = plan[m.id] ?? F0;
                const rOk = revisitaPermitida(f.vSemana);
                return (
                  <TableRow key={m.id} hover>
                    <TableCell>{m.nombre_completo}</TableCell>
                    <TableCell align="center">
                      <Chip size="small" label={m.categoria}
                            color={m.categoria === 'A' ? 'error' : m.categoria === 'B' ? 'warning' : 'default'} />
                    </TableCell>
                    {/* Semana de la Vista */}
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 92 }}>
                        <Select value={f.vSemana} onChange={(e) => setVSemana(m.id, Number(e.target.value))}>
                          <MenuItem value={0}><em>—</em></MenuItem>
                          {SEMANAS.map((s) => <MenuItem key={s} value={s}>Sem {s}</MenuItem>)}
                        </Select>
                      </FormControl>
                    </TableCell>
                    {/* Día de la Vista */}
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 110 }}>
                        <Select value={f.vDia} displayEmpty disabled={f.vSemana === 0}
                                onChange={(e) => setVDia(m.id, String(e.target.value))}>
                          <MenuItem value=""><em>— día —</em></MenuItem>
                          {DIAS.map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
                        </Select>
                      </FormControl>
                    </TableCell>
                    {/* Revisita Sí / No */}
                    <TableCell align="center">
                      <Tooltip title={f.vSemana === 0 ? 'Primero asigna la Vista'
                        : rOk ? '' : 'La revisita solo aplica a Vistas en Sem 1 o 2'}>
                        <FormControl size="small" sx={{ minWidth: 80 }}>
                          <Select value={f.revisita ? 'Si' : 'No'} disabled={!rOk}
                                  onChange={(e) => toggleRevisita(m.id, e.target.value === 'Si')}>
                            <MenuItem value="No">No</MenuItem>
                            <MenuItem value="Si">Sí</MenuItem>
                          </Select>
                        </FormControl>
                      </Tooltip>
                    </TableCell>
                    {/* Semana de la Revisita (propuesta editable, posterior a la Vista) */}
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 92 }}>
                        <Select value={f.revisita ? f.rSemana : 0} disabled={!f.revisita}
                                onChange={(e) => setRSemana(m.id, Number(e.target.value))}>
                          <MenuItem value={0}><em>—</em></MenuItem>
                          {SEMANAS.filter((s) => s > f.vSemana).map((s) => (
                            <MenuItem key={s} value={s}>Sem {s}</MenuItem>
                          ))}
                        </Select>
                      </FormControl>
                    </TableCell>
                    {/* Día de la Revisita (fijo = día de la Vista) */}
                    <TableCell align="center">
                      {f.revisita
                        ? <Chip size="small" variant="outlined" label={f.rDia || f.vDia || '—'} />
                        : <Typography variant="body2" color="text.disabled">—</Typography>}
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
      </Card>

      <Stack direction="row" spacing={2} alignItems="center">
        <Button variant="contained" startIcon={<Save />} disabled={guardando || esSoloLectura || medicos.length === 0} onClick={guardar}>
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
