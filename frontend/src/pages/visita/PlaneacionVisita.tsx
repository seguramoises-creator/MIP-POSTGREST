import { useEffect, useMemo, useState, useCallback, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Button, Stack, Chip, Alert, MenuItem,
  Select, FormControl, CircularProgress, Table, TableHead, TableRow, TableCell,
  TableBody, Grid, Tooltip, TextField, Avatar, Divider, TablePagination,
  Dialog, DialogTitle, DialogContent, DialogActions,
} from '@mui/material';
import { Save, EventNote, Warning, CheckCircle, FilterList, Search, Badge, SupervisorAccount, Layers,
         Lock, LockOpen, PublishedWithChanges } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import { usePuede } from '../../store/permisos.store';
import { catChipSx } from './categoriaColores';
import {
  listarMedicos, obtenerPlaneacion, planeacionResumen, guardarPlaneacion, listarVMs, miGerente,
  planeacionEstado, publicarPlaneacion, desbloquearPlaneacion,
  type MedicoVisita, type PlaneacionItem, type PlaneacionResumen, type Catalogo, type MiGerente,
  type PlaneacionEstado,
} from '../../services/visita.service';
import { TAUPE } from '../../theme/marca';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

// M1: con un panel entero marcado TOP, concatenar todos los nombres vuelve la
// alerta una cadena de miles de caracteres. Se capa igual que las listas
// vecinas de esta pantalla (`.slice(0, 30)`).
function formatearNombres(nombres: string[], tope = 30): string {
  if (nombres.length <= tope) return nombres.join(', ');
  return `${nombres.slice(0, tope).join(', ')} y ${nombres.length - tope} más`;
}

// Estado por médico: semana + día de la Vista, y (opcional) Revisita con su semana + día.
interface Fila { vSemana: number; vDia: string; revisita: boolean; rSemana: number; rDia: string; }
const F0: Fila = { vSemana: 0, vDia: '', revisita: false, rSemana: 0, rDia: '' };
const SEMANAS = [1, 2, 3, 4];
const DIAS = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'];
// Item 6: frecuencia como etiqueta corta (2 toques = V+R, 1 = V, 0 = —).
const freqLabel = (n: number) => (n >= 2 ? 'V+R' : n === 1 ? 'V' : '—');

// La revisita se intercala 2 semanas después (Sem 1→3, Sem 2→4); solo aplica a Vistas en Sem 1 o 2.
const revisitaPermitida = (vSemana: number) => vSemana === 1 || vSemana === 2;
const propuestaRevisita = (vSemana: number) => vSemana + 2;

export default function PlaneacionVisita() {
  const rol = useAuthStore((s) => s.rol);
  const puede = usePuede();
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);
  // País del contexto global — aislamiento multipaís en el selector de VM (ADMIN/GERENTE).
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  // Editar la planeación = REGISTRAR (matriz planeacion.ciclo): solo el representante (su panel)
  // y el ADMIN. Los demás (GD, CONSULTA, Analista, Dirección…) la ven en SOLO LECTURA.
  const puedeEditar = rol === 'ADMIN' || puede('planeacion.ciclo', 'register') === true;

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
  const [pagina, setPagina] = useState(0);          // paginación de la tabla (rendimiento)
  const POR_PAGINA = 25;
  // Ficha del representante (Gerente de Distrito + Línea) — viene de la dim del RM.
  const [infoRep, setInfoRep] = useState<MiGerente | null>(null);
  // La planeación es el DENOMINADOR de la cobertura: publicada = congelada.
  const [estado, setEstado] = useState<PlaneacionEstado | null>(null);
  const [confirmarPublicar, setConfirmarPublicar] = useState(false);
  const [dlgDesbloqueo, setDlgDesbloqueo] = useState(false);
  const [motivoDesbloqueo, setMotivoDesbloqueo] = useState('');
  const [publicando, setPublicando] = useState(false);
  const congelada = !!estado?.publicada;
  // Bloquea la edición: ciclo en consulta, planeación publicada, o el usuario no puede REGISTRAR
  // (roles de solo lectura como CONSULTA/GD/Analista/Dirección la ven pero no la modifican).
  const bloqueado = esSoloLectura || congelada || !puedeEditar;
  const esAdmin = rol === 'ADMIN';

  // Filtro visual (no afecta el guardado: se persiste TODO el plan, no solo lo visible).
  const medicosVisibles = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return medicos.filter((m) =>
      (!catFiltro || m.categoria === catFiltro) &&
      (!q || (m.nombre_completo ?? '').toUpperCase().includes(q)));
  }, [medicos, catFiltro, busqueda]);

  // Rendimiento: renderizar solo la página actual (cada fila trae 5 selects; 200+ de golpe
  // pone lentísima la tabla). El plan guardado es TODO el panel, no solo lo visible.
  useEffect(() => { setPagina(0); }, [catFiltro, busqueda, vmId]);
  const medicosPagina = useMemo(
    () => medicosVisibles.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA),
    [medicosVisibles, pagina],
  );

  // El RM planifica su propio panel (backend fuerza rm_id); ADMIN/GERENTE eligen un VM.
  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  // Lista de visitadores (solo para ADMIN/GERENTE). Autoselecciona el primero para que los
  // roles de consulta no aterricen en una pantalla vacía ("Selecciona un visitador").
  useEffect(() => {
    if (esVM) return;
    listarVMs(paisCodigo).then((vs) => { setVms(vs); if (vs.length && !vmId) setVmId(vs[0].id); }).catch(() => {});
  }, [esVM, paisCodigo]);   // eslint-disable-line react-hooks/exhaustive-deps

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
      const [m, p, r, e] = await Promise.all([
        listarMedicos(vmParam, false, true), obtenerPlaneacion(vmParam), planeacionResumen(vmParam),
        planeacionEstado(vmParam).catch(() => null)]);
      setMedicos(m);
      setResumen(r);
      setEstado(e);
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

  // Publicar CONGELA la planeación: a partir de aquí el denominador de la cobertura no se
  // mueve. Irreversible salvo desbloqueo del ADMIN.
  async function publicar() {
    setPublicando(true); setMsg(null);
    try {
      const r = await publicarPlaneacion(vmParam);
      setConfirmarPublicar(false);
      setMsg({ tipo: 'success', texto: `Planeación publicada (${r.items} visitas). Ya no puede modificarse.` });
      setEstado(await planeacionEstado(vmParam));
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo publicar la planeación.') });
    } finally { setPublicando(false); }
  }

  async function desbloquear() {
    if (!vmParam) { setMsg({ tipo: 'error', texto: 'Selecciona el representante a desbloquear.' }); return; }
    setPublicando(true); setMsg(null);
    try {
      await desbloquearPlaneacion(vmParam, motivoDesbloqueo.trim());
      setDlgDesbloqueo(false);
      setMsg({ tipo: 'success', texto: 'Planeación desbloqueada. El motivo quedó registrado.' });
      setEstado(await planeacionEstado(vmParam));
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo desbloquear.') });
    } finally { setPublicando(false); }
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
      {congelada && (
        <Alert severity="success" icon={<Lock />} sx={{ mb: 2 }}
               action={esAdmin ? (
                 <Button color="inherit" size="small" startIcon={<LockOpen />}
                         onClick={() => { setMotivoDesbloqueo(''); setDlgDesbloqueo(true); }}>
                   Desbloquear
                 </Button>
               ) : undefined}>
          <b>Planeación publicada</b>{estado?.publicada_en ? ` el ${estado.publicada_en.slice(0, 10)}` : ''} —
          ya no puede modificarse. Es el dato base con el que se calcula tu cobertura del ciclo.
          {!esAdmin && ' Si hay un error, un administrador debe desbloquearla.'}
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
                    <MenuItem value=""><span style={{ opacity: 0.7 }}>— Selecciona un visitador —</span></MenuItem>
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

      {/* Médicos TOP (SFA de Mallén): sin planear BLOQUEA publicar (error); sin Revisita
          solo AVISA (warning) — publicar sigue permitido. */}
      {!!resumen?.top_sin_planear?.length && (
        <Alert severity="error" sx={{ mb: 2 }}>
          No podrás publicar hasta incluir {resumen.top_sin_planear.length} médico(s){' '}
          <strong>TOP</strong>: {formatearNombres(resumen.top_sin_planear.map((m) => m.nombre))}.
        </Alert>
      )}
      {!!resumen?.top_sin_revisita?.length && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          {resumen.top_sin_revisita.length} médico(s) <strong>TOP</strong> están planeados sin
          Revisita: {formatearNombres(resumen.top_sin_revisita.map((m) => m.nombre))}. Un TOP no debería
          cerrar el ciclo sin visita y revisita.
        </Alert>
      )}

      {/* Filtros (solo afectan lo mostrado; el guardado persiste TODO el panel) */}
      <Card variant="outlined" sx={{ mb: 2, bgcolor: '#fff', borderColor: TAUPE,
                                   borderWidth: 1.5, borderRadius: 3 }}>
        <Box sx={{ p: 1.5 }}>
        <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} alignItems={{ sm: 'center' }}>
          <Stack direction="row" spacing={0.75} alignItems="center"
                 sx={{ color: TAUPE, width: { xs: '100%', md: 'auto' },
                       pb: { xs: 1, md: 0 }, mb: { xs: 0.5, md: 0 },
                       borderBottom: { xs: '1px solid #EDE9E4', md: 'none' } }}>
            <FilterList fontSize="small" />
            <Typography variant="body2" sx={{ fontWeight: 700, letterSpacing: '0.02em' }}>Filtrar</Typography>
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
                <TableCell align="center">Frecuencia<br />plan / logrado</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {medicos.length === 0 && (
                <TableRow><TableCell colSpan={8}>
                  <Alert severity="info" sx={{ my: 1 }}>No hay médicos en tu panel. Regístralos en Panel Médico.</Alert>
                </TableCell></TableRow>
              )}
              {medicos.length > 0 && medicosVisibles.length === 0 && (
                <TableRow><TableCell colSpan={8}>
                  <Alert severity="info" sx={{ my: 1 }}>Ningún médico coincide con el filtro.</Alert>
                </TableCell></TableRow>
              )}
              {medicosPagina.map((m) => {
                const f = plan[m.id] ?? F0;
                const rOk = revisitaPermitida(f.vSemana);
                // Item 6 — coherencia: frecuencia PLANEADA (lo creado) vs LOGRADA (visitas del ciclo).
                const planeado = (f.vSemana > 0 ? 1 : 0) + (f.revisita && f.rSemana > 0 ? 1 : 0);
                const logrado = m.estado_visita === 'vr' ? 2 : m.estado_visita === 'v' ? 1 : 0;
                const coherente = logrado >= planeado;
                return (
                  <TableRow key={m.id} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={600}>{m.nombre_completo}</Typography>
                      {/* Requerimiento Mallén (Item 6): indica en el panel si el médico ya fue visitado este ciclo. */}
                      <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.3 }}>
                        {m.estado_visita === 'vr' || m.estado_visita === 'v' ? (
                          <Chip size="small" color="success" variant="outlined" sx={{ height: 18, fontSize: 11 }}
                                label={m.estado_visita === 'vr' ? 'Visitado (V+R)' : 'Visitado'} />
                        ) : (
                          <Chip size="small" color="default" variant="outlined" sx={{ height: 18, fontSize: 11 }}
                                label="Sin visitar" />
                        )}
                        {m.es_top && <Chip label="TOP" size="small" color="error" sx={{ ml: 0.5, fontWeight: 700 }} />}
                      </Stack>
                    </TableCell>
                    <TableCell align="center">
                      <Chip size="small" label={m.categoria} sx={catChipSx(m.categoria)} />
                    </TableCell>
                    {/* Semana de la Vista */}
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 92 }}>
                        <Select value={f.vSemana} disabled={bloqueado} onChange={(e) => setVSemana(m.id, Number(e.target.value))}>
                          <MenuItem value={0}><span style={{ opacity: 0.7 }}>—</span></MenuItem>
                          {SEMANAS.map((s) => <MenuItem key={s} value={s}>Sem {s}</MenuItem>)}
                        </Select>
                      </FormControl>
                    </TableCell>
                    {/* Día de la Vista */}
                    <TableCell align="center">
                      <FormControl size="small" sx={{ minWidth: 110 }}>
                        <Select value={f.vDia} displayEmpty disabled={bloqueado || f.vSemana === 0}
                                onChange={(e) => setVDia(m.id, String(e.target.value))}>
                          <MenuItem value=""><span style={{ opacity: 0.7 }}>— día —</span></MenuItem>
                          {DIAS.map((d) => <MenuItem key={d} value={d}>{d}</MenuItem>)}
                        </Select>
                      </FormControl>
                    </TableCell>
                    {/* Revisita Sí / No */}
                    <TableCell align="center">
                      <Tooltip title={f.vSemana === 0 ? 'Primero asigna la Vista'
                        : rOk ? '' : 'La revisita solo aplica a Vistas en Sem 1 o 2'}>
                        <FormControl size="small" sx={{ minWidth: 80 }}>
                          <Select value={f.revisita ? 'Si' : 'No'} disabled={bloqueado || !rOk}
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
                        <Select value={f.revisita ? f.rSemana : 0} disabled={bloqueado || !f.revisita}
                                onChange={(e) => setRSemana(m.id, Number(e.target.value))}>
                          <MenuItem value={0}><span style={{ opacity: 0.7 }}>—</span></MenuItem>
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
                    {/* Frecuencia planeada vs. lograda: verde si va al día, ámbar si va detrás. */}
                    <TableCell align="center">
                      <Chip size="small" variant="outlined"
                            color={planeado === 0 ? 'default' : coherente ? 'success' : 'warning'}
                            label={`${freqLabel(planeado)} / ${freqLabel(logrado)}`} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
          {medicosVisibles.length > POR_PAGINA && (
            <TablePagination
              component="div"
              count={medicosVisibles.length}
              page={pagina}
              onPageChange={(_e, p) => setPagina(p)}
              rowsPerPage={POR_PAGINA}
              rowsPerPageOptions={[POR_PAGINA]}
              labelDisplayedRows={({ from, to, count }) => `${from}–${to} de ${count}`}
            />
          )}
        </Box>
      </Card>

      <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" useFlexGap>
        {/* Controles de edición: solo para quien puede REGISTRAR (RM + ADMIN). Roles de solo
            lectura ven la planeación pero no estos botones. */}
        {puedeEditar && (
          <>
            <Button variant="contained" startIcon={<Save />} disabled={guardando || bloqueado || medicos.length === 0} onClick={guardar}>
              {guardando ? 'Guardando…' : 'Guardar planeación'}
            </Button>
            {/* Publicar CONGELA la planeación. Solo tiene sentido sobre un borrador con datos. */}
            {!congelada && (
              <Button variant="outlined" color="success" startIcon={<PublishedWithChanges />}
                      disabled={publicando || bloqueado || !resumen?.total_planeadas}
                      onClick={() => setConfirmarPublicar(true)}>
                Publicar planeación del ciclo
              </Button>
            )}
          </>
        )}
        {resumen && (
          <Stack direction="row" spacing={1} alignItems="center" color="text.secondary">
            <CheckCircle fontSize="small" color="success" />
            <Typography variant="body2">
              Guardado: {resumen.total_planeadas} visitas · {resumen.cobertura_planeada_pct}% cobertura · {resumen.carga_por_dia}/día
            </Typography>
          </Stack>
        )}
      </Stack>

      {/* Confirmación de publicación: es irreversible, así que se dice sin rodeos. */}
      <Dialog open={confirmarPublicar} onClose={() => setConfirmarPublicar(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <Lock color="success" /> Publicar la planeación
        </DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>
            Vas a congelar <b>{resumen?.total_planeadas} visitas planeadas</b> ({resumen?.cobertura_planeada_pct}% de
            cobertura) para este ciclo.
          </Typography>
          <Alert severity="warning" sx={{ mb: 1 }}>
            <b>No podrás modificarla después.</b> Es el dato base con el que se calcula tu cobertura:
            si cambiara a mitad de ciclo, el porcentaje dejaría de ser comparable. Solo un
            administrador puede desbloquearla, dejando constancia del motivo.
          </Alert>
          <Typography variant="caption" color="text.secondary">
            Revisa la parrilla antes de continuar.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmarPublicar(false)}>Cancelar</Button>
          <Button variant="contained" color="success" disabled={publicando} onClick={publicar}>
            {publicando ? 'Publicando…' : 'Sí, publicar y congelar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Desbloqueo — solo ADMIN. El motivo es obligatorio y queda registrado. */}
      <Dialog open={dlgDesbloqueo} onClose={() => setDlgDesbloqueo(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <LockOpen color="warning" /> Desbloquear la planeación
        </DialogTitle>
        <DialogContent>
          <Alert severity="warning" sx={{ mb: 2 }}>
            La planeación volverá a ser editable y su cobertura podrá cambiar. Queda registrado
            quién desbloqueó, cuándo y por qué.
          </Alert>
          <TextField fullWidth autoFocus multiline minRows={2} label="Motivo del desbloqueo *"
                     value={motivoDesbloqueo} onChange={(e) => setMotivoDesbloqueo(e.target.value)}
                     placeholder="Ej: el representante planeó al médico equivocado" />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDlgDesbloqueo(false)}>Cancelar</Button>
          <Button variant="contained" color="warning" disabled={publicando || !motivoDesbloqueo.trim()}
                  onClick={desbloquear}>
            Desbloquear
          </Button>
        </DialogActions>
      </Dialog>
      </>
      )}
    </Box>
  );
}
