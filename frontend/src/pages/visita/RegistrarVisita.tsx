import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, ToggleButton, ToggleButtonGroup, CircularProgress, Avatar, Checkbox,
  Select, FormControl, Divider,
} from '@mui/material';
import { CheckCircle, Save, EventBusy, AccessAlarm, Medication, ChatBubbleOutline, Assignment, FiberManualRecord, SupervisorAccount, History, ExpandMore, ExpandLess, Lock } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  agendaHoy, listarCausas, misVisitasHoy, registrarVisita, registrarNoVisita, listarVMs, obtenerParrilla, miGerente, subirFotoVisita, historialVisitas, registrarMuestras,
  type AgendaMedico, type VisitaHoy, type Catalogo, type ParrillaItem, type ProductoDetalle, type MiGerente,
} from '../../services/visita.service';

// ── Paleta profesional (médica / farmacéutica) ───────────────────────────────
const NAVY = '#0d1b4c';       // azul corporativo profundo
const TEAL = '#0f9b8e';       // acento clínico (teal-verde)
const INK = '#1e293b';        // texto principal
const SOFT_SHADOW = '0 1px 3px rgba(16,24,40,0.06), 0 6px 20px rgba(16,24,40,0.05)';
// Tarjeta base: sombra suave en vez de bordes marcados (menos saturación visual).
const cardSx = { borderRadius: 3, border: '1px solid #eef1f6', boxShadow: SOFT_SHADOW } as const;
// Encabezado de sección uniforme (ícono + título en mayúsculas discretas).
const secHeadSx = { fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase', color: 'text.secondary', fontSize: '0.72rem' } as const;

const CAT_AV: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#FBE7A1', fg: '#8A6D0B' }, B: { bg: '#D6E4FF', fg: '#1E52C7' },
  C: { bg: '#E8EAF0', fg: '#5A6472' }, D: { bg: '#F3D6D6', fg: '#B23B3B' },
};
const INICIAL_COLORS = ['#2E5BFF', '#7A5AF8', '#0F9B8E', '#E8833A', '#D6409F', '#2AA76A', '#C0392B', '#3B82C4'];
const MENCIONES = [1, 2, 3];

function iniciales(n: string): string {
  const p = n.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase();
}
function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}
function hhmm(d: Date): string { return d.toTimeString().slice(0, 5); }

// Estado de sincronización local de una visita del feed "Registradas hoy".
type SyncEstado = 'local' | 'sincronizado' | 'error';
interface Registrada extends VisitaHoy { sync: SyncEstado; }

export default function RegistrarVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  // Sin contexto de ciclo: el registro SIEMPRE opera sobre el ciclo abierto del
  // país del visitador (el backend lo resuelve y lo protege con su guard).

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');
  const [agenda, setAgenda] = useState<AgendaMedico[]>([]);
  const [causas, setCausas] = useState<string[]>([]);
  const [registradas, setRegistradas] = useState<Registrada[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [sel, setSel] = useState<AgendaMedico | null>(null);
  const [tipo, setTipo] = useState<'V' | 'R'>('V');
  const [hora, setHora] = useState(hhmm(new Date()));
  const [comentario, setComentario] = useState('');
  const [modoNoVisita, setModoNoVisita] = useState(false);
  const [causa, setCausa] = useState('');
  const [productos, setProductos] = useState<ParrillaItem[]>([]);
  // producto → { mencion, muestras }. Ambos se PROPONEN desde la parrilla y son
  // editables: la mención según el orden de prioridad (1º producto → 1ª mención…)
  // y las muestras según la meta del producto (el VM puede entregar más o menos).
  const [detallados, setDetallados] = useState<Record<string, { mencion: number; muestras: number }>>({});
  const [guardando, setGuardando] = useState(false);
  const [gd, setGd] = useState<MiGerente | null>(null);
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [foto, setFoto] = useState<File | null>(null);
  const [fotoPreview, setFotoPreview] = useState<string | null>(null);
  // Visitas anteriores (SOLO LECTURA): el RM consulta lo registrado y su
  // comentario; no hay forma de editarlas (el registro es inmutable).
  const [verHistorial, setVerHistorial] = useState(false);
  const [historial, setHistorial] = useState<VisitaHoy[]>([]);
  const [historialCargando, setHistorialCargando] = useState(false);

  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  const cargarAgenda = useCallback(() => {
    if (!listo) return;
    agendaHoy(vmParam).then(setAgenda).catch(() => setAgenda([]));
  }, [listo, vmParam]);

  const cargarRegistradas = useCallback(() => {
    if (!listo) { setRegistradas([]); return; }
    // Todo lo que devuelve el servidor está CONFIRMADO en BD → verde.
    misVisitasHoy(vmParam).then((vs) => setRegistradas(vs.map((v) => ({ ...v, sync: 'sincronizado' as SyncEstado }))))
      .catch(() => setRegistradas([]));
  }, [listo, vmParam]);

  useEffect(() => {
    listarCausas().then(setCausas).catch(() => {});
    if (!esVM) listarVMs().then(setVms).catch(() => {});
    setCargando(false);
  }, [esVM]);

  useEffect(() => { setSel(null); cargarAgenda(); cargarRegistradas(); }, [cargarAgenda, cargarRegistradas]);
  // Historial: carga perezosa al abrir la sección (y se refresca si cambia el VM).
  useEffect(() => {
    if (!verHistorial || !listo) return;
    setHistorialCargando(true);
    historialVisitas(vmParam, 30).then(setHistorial).catch(() => setHistorial([]))
      .finally(() => setHistorialCargando(false));
  }, [verHistorial, listo, vmParam]);
  useEffect(() => {
    if (listo) miGerente(vmParam).then(setGd).catch(() => setGd(null));
    else setGd(null);
  }, [listo, vmParam]);

  // Al seleccionar un médico: precarga tipo, hora actual y la parrilla de productos.
  function seleccionar(m: AgendaMedico) {
    if (m.estado === 'registrada') return;
    setSel(m); setTipo((m.tipo_visita === 'R' ? 'R' : 'V')); setHora(hhmm(new Date()));
    setComentario(''); setModoNoVisita(false); setCausa(''); setDetallados({}); setMsg(null);
    // Parrilla de la LÍNEA DEL REPRESENTANTE (no la del médico), del ciclo abierto
    // de su país — la misma parrilla contra la que promociona y entrega muestras.
    obtenerParrilla(undefined, undefined, vmParam).then(setProductos).catch(() => setProductos([]));
  }

  // Minutos transcurridos desde la hora indicada (para la ventana de 60 min).
  const haceMin = useMemo(() => {
    const [h, mi] = hora.split(':').map(Number);
    const now = new Date();
    const sel2 = new Date(now); sel2.setHours(h, mi, 0, 0);
    return Math.round((now.getTime() - sel2.getTime()) / 60000);
  }, [hora]);
  const horaOk = haceMin >= 0 && haceMin <= 60;

  const toggleProd = (p: ParrillaItem, idx: number) => setDetallados((d) => {
    const n = { ...d };
    if (n[p.producto]) delete n[p.producto];
    else n[p.producto] = { mencion: Math.min(idx + 1, 3), muestras: p.meta_muestras || 0 };
    return n;
  });

  async function guardar() {
    if (!sel) return;
    if (modoNoVisita) {
      if (!causa) { setMsg({ tipo: 'error', texto: 'Selecciona la causa.' }); return; }
    } else if (!horaOk) {
      setMsg({ tipo: 'error', texto: 'La hora está fuera de la ventana de 60 minutos.' }); return;
    }
    setGuardando(true); setMsg(null);
    // Entrada optimista AMARILLA en "Registradas hoy" (aún sin confirmar en servidor).
    const prods: ProductoDetalle[] = Object.entries(detallados).map(([producto, v]) => ({ producto, mencion: v.mencion }));
    // Muestras entregadas por producto (propuestas por la parrilla, editadas por el VM).
    const entregas = Object.entries(detallados)
      .filter(([, v]) => v.muestras > 0)
      .map(([producto, v]) => ({ producto, cantidad: v.muestras }));
    const optimista: Registrada = {
      id: -Date.now(), medico_id: sel.medico_id, medico: sel.nombre, tipo_visita: modoNoVisita ? tipo : tipo,
      ejecutada: !modoNoVisita, causa_no_visita: modoNoVisita ? causa : null, comentario,
      productos: prods.map((p) => p.producto), hora: new Date().toISOString(), sync: 'local',
    };
    setRegistradas((r) => [optimista, ...r]);
    try {
      if (modoNoVisita) {
        await registrarNoVisita(sel.medico_id, causa, comentario || undefined, vmParam);
      } else {
        const r = await registrarVisita(sel.medico_id, tipo, comentario, Math.max(0, Math.min(60, haceMin)), prods, vmParam, gps?.lat ?? null, gps?.lng ?? null);
        // Muestras entregadas: alimentan el reporte de penetración/muestras vs meta.
        if (entregas.length) {
          try { await registrarMuestras(sel.medico_id, entregas, vmParam); }
          catch { setMsg({ tipo: 'error', texto: 'Visita registrada, pero las muestras no se pudieron registrar.' }); }
        }
        if (foto && r?.id) {
          try { await subirFotoVisita(r.id, foto); }
          catch { setMsg({ tipo: 'error', texto: 'Visita registrada, pero la foto no se pudo subir.' }); }
        }
      }
      setMsg((m) => m ?? { tipo: 'success', texto: modoNoVisita ? 'No-visita registrada.' : 'Visita registrada y confirmada en el servidor.' });
      setSel(null); setGps(null); setFoto(null); setFotoPreview(null);
      // Confirmación real: re-consultamos el servidor → pasan a VERDE.
      cargarRegistradas(); cargarAgenda();
    } catch (e) {
      setRegistradas((r) => r.map((x) => x.id === optimista.id ? { ...x, sync: 'error' } : x));
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo registrar.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const pendientes = agenda.filter((a) => a.estado === 'pendiente').length;

  const avatar = (nombre: string, categoria: string, mid: number, size = 40) => {
    const color = INICIAL_COLORS[mid % INICIAL_COLORS.length];
    const av = CAT_AV[categoria] ?? CAT_AV.C;
    return (
      <Stack direction="row" spacing={0.5} alignItems="center">
        <Avatar sx={{ bgcolor: 'transparent', color, fontWeight: 700, fontSize: 13, width: size, height: size, border: `2px solid ${color}22` }}>{iniciales(nombre)}</Avatar>
        <Avatar sx={{ bgcolor: av.bg, color: av.fg, fontWeight: 700, fontSize: 12, width: 24, height: 24 }}>{categoria}</Avatar>
      </Stack>
    );
  };

  return (
    <Box sx={{ maxWidth: 620, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
      {/* HERO — encabezado corporativo: título + fecha + Gerente de Distrito, con el
          contexto País/Ciclo y el visitador integrados en un panel interior. Todo
          con flex-wrap: se reacomoda solo en iPhone/iPad/Android. */}
      <Box sx={{
        background: `linear-gradient(130deg, ${NAVY} 0%, #17307a 55%, #1f6f8f 100%)`,
        borderRadius: 4, p: { xs: 2, sm: 2.5 }, mb: 2.5, color: '#fff',
        boxShadow: '0 12px 30px rgba(13,27,76,0.30)', position: 'relative', overflow: 'hidden',
      }}>
        {/* Acento decorativo sutil (círculo teal difuminado) */}
        <Box sx={{ position: 'absolute', top: -40, right: -30, width: 150, height: 150, borderRadius: '50%',
                   background: `radial-gradient(circle, ${TEAL}55 0%, transparent 70%)`, pointerEvents: 'none' }} />
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" rowGap={1}>
          <Avatar sx={{ bgcolor: 'rgba(255,255,255,0.16)', width: { xs: 40, sm: 48 }, height: { xs: 40, sm: 48 },
                        border: '1px solid rgba(255,255,255,0.3)' }}>
            <Assignment sx={{ color: '#fff', fontSize: { xs: 22, sm: 26 } }} />
          </Avatar>
          <Box sx={{ flex: 1, minWidth: 170 }}>
            <Typography fontWeight={900} sx={{ color: '#fff', letterSpacing: '-0.3px', lineHeight: 1.15,
                                               fontSize: { xs: '1.25rem', sm: '1.55rem' } }}>
              Registrar Visita
            </Typography>
            <Typography variant="caption" sx={{ color: 'rgba(255,255,255,0.82)', display: 'block' }}>
              {(() => { const f = new Date().toLocaleDateString('es-DO', { weekday: 'long', day: 'numeric', month: 'long' });
                        return f.charAt(0).toUpperCase() + f.slice(1); })()} · Captura en campo
            </Typography>
          </Box>
          {gd?.gerente && (
            <Chip icon={<SupervisorAccount sx={{ color: '#fff !important' }} />}
                  label={`GD: ${gd.gerente}${gd.linea ? ` · ${gd.linea}` : ''}`}
                  sx={{ bgcolor: 'rgba(255,255,255,0.14)', color: '#fff', fontWeight: 700,
                        border: '1px solid rgba(255,255,255,0.28)', maxWidth: '100%' }} />
          )}
        </Stack>

        {/* Sin contexto País/Ciclo: el registro SIEMPRE va al ciclo abierto del país
            del visitador (el backend lo impone) — mostrarlo aquí era redundante.
            El panel interior solo aparece para gestión (selector de visitador). */}
        {!esVM && (
          <Box sx={{ mt: 2, bgcolor: 'rgba(255,255,255,0.97)', borderRadius: 2, p: { xs: 1.25, sm: 1.5 } }}>
            <TextField select fullWidth size="small" label="Visitador (VM)" value={vmId}
                       helperText="Elige el visitador para ver su agenda del día"
                       onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
              <MenuItem value=""><em>— Selecciona un visitador —</em></MenuItem>
              {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
            </TextField>
          </Box>
        )}
      </Box>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {!listo ? (
        <Alert severity="info">Selecciona un visitador para ver su agenda.</Alert>
      ) : (
      <>
        {/* Médicos de hoy (agenda) */}
        <Card elevation={0} sx={{ ...cardSx, mb: 2 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Box sx={{ width: 30, height: 30, borderRadius: 1.5, bgcolor: `${NAVY}0f`, display: 'grid', placeItems: 'center' }}>
                <Assignment sx={{ fontSize: 17, color: NAVY }} />
              </Box>
              <Typography variant="subtitle1" fontWeight={800} sx={{ color: INK }}>Médicos de hoy</Typography>
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color={pendientes ? 'warning' : 'success'} variant={pendientes ? 'filled' : 'outlined'}
                    label={pendientes ? `${pendientes} pendiente${pendientes > 1 ? 's' : ''}` : 'Al día'} sx={{ fontWeight: 700 }} />
            </Stack>
            {agenda.length === 0 ? (
              <Alert severity="info">No hay médicos programados. Puedes registrar desde el panel.</Alert>
            ) : (
              <Stack divider={<Divider />}>
                {agenda.map((a) => {
                  const activa = sel?.medico_id === a.medico_id;
                  const reg = a.estado === 'registrada';
                  return (
                    <Stack key={a.medico_id} direction="row" alignItems="center" spacing={1.5}
                           onClick={() => seleccionar(a)}
                           sx={{ py: 1, px: 0.5, cursor: reg ? 'default' : 'pointer', borderRadius: 1,
                                 bgcolor: activa ? 'rgba(255,193,7,0.14)' : reg ? 'transparent' : 'transparent',
                                 opacity: reg ? 0.7 : 1, '&:hover': { bgcolor: reg ? 'transparent' : 'action.hover' } }}>
                      {avatar(a.nombre, a.categoria, a.medico_id, 36)}
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        {/* Tipografía fluida: la letra se encoge con el ancho (clamp) y
                            solo cae a 2 líneas cuando ya no puede achicarse más. */}
                        <Typography fontWeight={700} sx={{ fontSize: 'clamp(0.72rem, 2.6vw, 0.875rem)', lineHeight: 1.25,
                                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {a.nombre}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                          {[a.especialidad, a.tipo_visita === 'R' ? 'Revisita' : 'Vista programada', a.hora_estimada].filter(Boolean).join(' · ')}
                        </Typography>
                      </Box>
                      {reg ? (
                        <Chip size="small" color={a.no_visita ? 'default' : 'success'}
                              label={a.no_visita ? 'No-visita' : 'Registrada ✓'} />
                      ) : (
                        <Typography variant="caption" sx={{ color: 'warning.main', fontWeight: 700 }}>Pendiente</Typography>
                      )}
                    </Stack>
                  );
                })}
              </Stack>
            )}
          </CardContent>
        </Card>

        {/* Formulario de la visita seleccionada */}
        {sel && (
          <>
          <Card elevation={0} sx={{ ...cardSx, mb: 2 }}>
            <Box sx={{ background: `linear-gradient(120deg, ${NAVY}0d 0%, ${TEAL}0d 100%)`,
                       borderBottom: '1px solid #eef1f6', px: 2, py: 1.5, display: 'flex', alignItems: 'center',
                       gap: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
              {avatar(sel.nombre, sel.categoria, sel.medico_id, 42)}
              <Box sx={{ flex: 1, minWidth: 120 }}>
                {/* Tipografía fluida: encoge con clamp; a 2 líneas solo si no cabe. */}
                <Typography fontWeight={800} sx={{ color: INK, fontSize: 'clamp(0.82rem, 3.2vw, 1.05rem)', lineHeight: 1.2,
                            display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                  {sel.nombre}
                </Typography>
                <Typography variant="caption" color="text.secondary" sx={{ display: 'block',
                            overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                  {[sel.especialidad, sel.centro_trabajo, sel.provincia].filter(Boolean).join(' · ') || 'Sin datos'}
                </Typography>
              </Box>
              <ToggleButtonGroup exclusive size="small" value={tipo} onChange={(_, v) => v && setTipo(v)}
                                 sx={{ bgcolor: '#fff', borderRadius: 2, '& .MuiToggleButton-root': { border: '1px solid #e2e8f0', fontWeight: 700, px: 1.5,
                                       '&.Mui-selected': { bgcolor: NAVY, color: '#fff', '&:hover': { bgcolor: NAVY } } } }}>
                <ToggleButton value="V">Vista</ToggleButton>
                <ToggleButton value="R">Revisita</ToggleButton>
              </ToggleButtonGroup>
            </Box>
            <CardContent>
              <Stack spacing={2}>
                {!modoNoVisita && (
                  <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
                    {/* Columna 1: hora real */}
                    <Box sx={{ minWidth: { sm: 190 } }}>
                      <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
                        <AccessAlarm sx={{ fontSize: 18, color: '#e11d48' }} />
                        <Typography variant="caption" sx={secHeadSx}>Hora real de la visita</Typography>
                      </Stack>
                      <TextField type="time" size="small" value={hora} onChange={(e) => setHora(e.target.value)}
                                 sx={{ width: { xs: '100%', sm: 160 } }} />
                      <Typography variant="caption" sx={{ display: 'block', mt: 0.5, fontWeight: 600, color: horaOk ? 'success.main' : 'error.main' }}>
                        Ahora {hhmm(new Date())} · {horaOk ? 'dentro de 60 min ✓' : 'fuera de 60 min ✗'}
                      </Typography>
                    </Box>

                    {/* Columna 2: RESUMEN EN VIVO — aprovecha el espacio con datos útiles */}
                    <Box sx={{ flex: 1, borderRadius: 2, p: 1.25,
                               background: `linear-gradient(135deg, ${NAVY}0a 0%, ${TEAL}0f 100%)`,
                               border: '1px solid #eef1f6' }}>
                      <Typography variant="caption" sx={{ ...secHeadSx, display: 'block', mb: 0.75 }}>
                        Resumen de la visita
                      </Typography>
                      {(() => {
                        const nProd = Object.keys(detallados).length;
                        const nMuestras = Object.values(detallados).reduce((s, v) => s + (v.muestras || 0), 0);
                        const stat = (label: string, value: string, color: string) => (
                          <Box sx={{ textAlign: 'center', flex: 1, minWidth: 62 }}>
                            <Typography sx={{ fontWeight: 900, fontSize: '1.15rem', lineHeight: 1.1, color }}>{value}</Typography>
                            <Typography variant="caption" color="text.secondary" sx={{ fontSize: '0.62rem' }}>{label}</Typography>
                          </Box>
                        );
                        return (
                          <>
                            <Stack direction="row" spacing={0.5} divider={<Divider orientation="vertical" flexItem sx={{ borderColor: '#e2e8f0' }} />}>
                              {stat('Tipo', tipo === 'R' ? 'Revisita' : 'Vista', NAVY)}
                              {stat('Productos', String(nProd), TEAL)}
                              {stat('Muestras', String(nMuestras), TEAL)}
                            </Stack>
                            <Stack direction="row" spacing={0.75} sx={{ mt: 1 }} flexWrap="wrap" rowGap={0.5}>
                              <Chip size="small" label={gps ? 'Ubicación ✓' : 'Sin ubicación'} variant={gps ? 'filled' : 'outlined'}
                                    color={gps ? 'success' : 'default'} sx={{ fontWeight: 600, height: 22, fontSize: '0.66rem' }} />
                              <Chip size="small" label={foto ? 'Foto ✓' : 'Sin foto'} variant={foto ? 'filled' : 'outlined'}
                                    color={foto ? 'success' : 'default'} sx={{ fontWeight: 600, height: 22, fontSize: '0.66rem' }} />
                            </Stack>
                          </>
                        );
                      })()}
                    </Box>
                  </Stack>
                )}

                {!modoNoVisita && (
                  <Box>
                    {/* La parrilla llega ordenada por PRIORIDAD desde el backend. */}
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
                      <Medication sx={{ fontSize: 18, color: TEAL }} />
                      <Typography variant="caption" sx={{ fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase', color: 'text.secondary' }}>
                        Productos y muestras
                      </Typography>
                    </Stack>
                    {productos.length > 0 && (
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.75 }}>
                        Propuestos por prioridad de la parrilla promocional
                      </Typography>
                    )}
                    {productos.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">No hay parrilla de productos para esta línea.</Typography>
                    ) : (
                      <Box sx={{ border: '1px solid #eef1f6', borderRadius: 2, bgcolor: '#fafbfd', px: 1, py: 0.25 }}>
                        <Stack divider={<Divider sx={{ borderColor: '#f0f3f8' }} />}>
                          {productos.map((p, idx) => {
                            const det = detallados[p.producto];
                            const on = det !== undefined;
                            const base = { mencion: Math.min(idx + 1, 3), muestras: p.meta_muestras || 0 };
                            return (
                              <Stack key={p.producto} direction="row" alignItems="center" spacing={1}
                                     sx={{ py: 0.9, px: 0.5, borderRadius: 1, flexWrap: 'wrap', rowGap: 0.75,
                                           bgcolor: on ? 'rgba(46,91,255,0.05)' : 'transparent' }}>
                                <Checkbox size="small" checked={on} onChange={() => toggleProd(p, idx)} sx={{ p: 0.5 }} />
                                <Avatar sx={{ width: 22, height: 22, fontSize: 11, fontWeight: 800,
                                              bgcolor: p.prioridad === 1 ? '#1a237e' : p.prioridad === 2 ? '#1565c0' : '#90a4ae' }}>
                                  {p.prioridad}
                                </Avatar>
                                <Box sx={{ flex: 1, minWidth: 110 }}>
                                  <Typography variant="body2" fontWeight={700} noWrap>{p.producto}</Typography>
                                  <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                                    Propuesto: {p.meta_muestras} muestra{p.meta_muestras === 1 ? '' : 's'} · {Math.min(idx + 1, 3)}ª mención
                                  </Typography>
                                </Box>
                                {/* Cantidad de muestras al lado del producto: propuesta por la
                                    parrilla, editable si se entrega más o menos al médico. */}
                                <TextField size="small" type="number" label="Muestras" disabled={!on}
                                           value={det?.muestras ?? p.meta_muestras}
                                           onChange={(e) => {
                                             const q = Math.max(0, Math.min(999, Number(e.target.value) || 0));
                                             setDetallados((d) => ({ ...d, [p.producto]: { ...(d[p.producto] ?? base), muestras: q } }));
                                           }}
                                           inputProps={{ min: 0, max: 999 }} sx={{ width: 88 }} />
                                <FormControl size="small" sx={{ minWidth: { xs: 104, sm: 118 } }}>
                                  <Select value={det?.mencion ?? base.mencion} disabled={!on}
                                          onChange={(e) => setDetallados((d) => ({ ...d, [p.producto]: { ...(d[p.producto] ?? base), mencion: Number(e.target.value) } }))}>
                                    {MENCIONES.map((m) => <MenuItem key={m} value={m}>{m}ª mención</MenuItem>)}
                                  </Select>
                                </FormControl>
                              </Stack>
                            );
                          })}
                        </Stack>
                      </Box>
                    )}
                  </Box>
                )}

                {modoNoVisita ? (
                  <TextField select label="Causa de no-visita" value={causa} required
                             onChange={(e) => setCausa(e.target.value)}>
                    {causas.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                  </TextField>
                ) : null}

                <Box>
                  <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
                    <ChatBubbleOutline sx={{ fontSize: 18, color: TEAL }} />
                    <Typography variant="caption" sx={secHeadSx}>
                      Comentario de visita <span style={{ color: '#d32f2f' }}>*</span>
                    </Typography>
                  </Stack>
                  <TextField fullWidth multiline minRows={2} maxRows={4} value={comentario}
                             onChange={(e) => setComentario(e.target.value)}
                             placeholder="Describe algo relevante que ocurrió en la visita…"
                             helperText='Mínimo 10 caracteres · No escribas solo "Visita OK"' />
                </Box>

                {!modoNoVisita && (
                  <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" rowGap={1}>
                    <Button size="small" variant="outlined" startIcon={<span>📍</span>}
                            color={gps ? 'success' : 'primary'}
                            sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, borderWidth: 1.5 }}
                            onClick={() => {
                              if (!navigator.geolocation) { setMsg({ tipo: 'error', texto: 'Este dispositivo no soporta geolocalización.' }); return; }
                              navigator.geolocation.getCurrentPosition(
                                (pos) => setGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
                                () => setMsg({ tipo: 'error', texto: 'No se pudo obtener la ubicación (permiso denegado o sin señal).' }),
                                { enableHighAccuracy: true, timeout: 8000 });
                            }}>
                      {gps ? 'Ubicación capturada' : 'Capturar ubicación'}
                    </Button>
                    {gps && <Typography variant="caption" color="text.secondary">📍 {gps.lat.toFixed(5)}, {gps.lng.toFixed(5)}</Typography>}
                    <Button size="small" variant="outlined" component="label" startIcon={<span>📷</span>}
                            color={foto ? 'success' : 'primary'}
                            sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, borderWidth: 1.5 }}>
                      {foto ? 'Cambiar foto' : 'Foto del centro'}
                      <input hidden type="file" accept="image/*" capture="environment"
                             onChange={(e) => { const f = e.target.files?.[0] || null; setFoto(f); setFotoPreview(f ? URL.createObjectURL(f) : null); }} />
                    </Button>
                    {fotoPreview && <Box component="img" src={fotoPreview} alt="foto" sx={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 1, border: '1px solid #ddd' }} />}
                  </Stack>
                )}

                {/* En móvil los botones se apilan (columna); en pantallas medianas+ van en fila. */}
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ pt: 0.5 }}>
                  <Button variant="contained" fullWidth startIcon={<Save />}
                          disabled={guardando || (!modoNoVisita && comentario.trim().length < 10)}
                          onClick={guardar}
                          sx={{ py: 1.25, borderRadius: 2.5, fontWeight: 800, textTransform: 'none', fontSize: '0.95rem',
                                boxShadow: '0 8px 18px rgba(15,155,142,0.30)',
                                background: `linear-gradient(120deg, ${TEAL} 0%, #0b7d72 100%)`,
                                '&:hover': { background: `linear-gradient(120deg, #0d8a7f 0%, #0a6f66 100%)` },
                                '&.Mui-disabled': { background: '#cbd5e1', color: '#fff', boxShadow: 'none' } }}>
                    {guardando ? 'Guardando…' : (modoNoVisita ? 'Registrar no-visita' : 'Guardar visita')}
                  </Button>
                  <Button variant="outlined" color={modoNoVisita ? 'primary' : 'error'} startIcon={<EventBusy />}
                          onClick={() => { setModoNoVisita(!modoNoVisita); setMsg(null); }}
                          sx={{ py: 1.25, borderRadius: 2.5, fontWeight: 700, textTransform: 'none', borderWidth: 1.5 }}>
                    {modoNoVisita ? 'Fue visita' : 'No visité'}
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
          </>
        )}

        {/* Registradas hoy */}
        <Card elevation={0} sx={cardSx}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Box sx={{ width: 30, height: 30, borderRadius: 1.5, bgcolor: '#e8f5ee', display: 'grid', placeItems: 'center' }}>
                <CheckCircle sx={{ fontSize: 17, color: '#2e7d32' }} />
              </Box>
              <Typography variant="subtitle1" fontWeight={800} sx={{ color: INK }}>Registradas hoy</Typography>
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color="success" variant="outlined" label={`${registradas.length} visita${registradas.length === 1 ? '' : 's'}`} sx={{ fontWeight: 700 }} />
            </Stack>
            {registradas.length === 0 ? (
              <Alert severity="info">Aún no hay visitas registradas hoy.</Alert>
            ) : (
              <Stack divider={<Divider />}>
                {registradas.map((v) => {
                  const verde = v.sync === 'sincronizado';
                  const rojo = v.sync === 'error';
                  return (
                    <Stack key={v.id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                      <FiberManualRecord sx={{ fontSize: 12, color: rojo ? 'error.main' : verde ? 'success.main' : 'warning.main' }} />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography fontWeight={600} sx={{ fontSize: 'clamp(0.75rem, 2.6vw, 0.875rem)', lineHeight: 1.25,
                                    display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                          {v.medico}
                          {v.tiene_gps && <span title="Con ubicación" style={{ marginLeft: 6 }}>📍</span>}
                          {v.tiene_foto && <span title="Con foto del centro" style={{ marginLeft: 4 }}>📷</span>}
                        </Typography>
                        <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                          {[v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : `No-visita: ${v.causa_no_visita ?? ''}`,
                            v.hora ? new Date(v.hora).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' }) : null,
                            v.productos && v.productos.length ? v.productos.join(', ') : null].filter(Boolean).join(' · ')}
                        </Typography>
                      </Box>
                      <Chip size="small" color={rojo ? 'error' : verde ? 'success' : 'warning'}
                            variant={verde ? 'filled' : 'outlined'}
                            label={rojo ? 'Error' : verde ? 'Sincronizado ✓' : 'Registrada'} />
                    </Stack>
                  );
                })}
              </Stack>
            )}
          </CardContent>
        </Card>

        {/* Visitas anteriores — SOLO LECTURA: el RM consulta lo registrado (incluido
            su comentario) pero no puede modificarlo; no existen acciones de edición. */}
        <Card elevation={0} sx={{ ...cardSx, mt: 2 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1}
                   onClick={() => setVerHistorial((v) => !v)} sx={{ cursor: 'pointer' }}>
              <Box sx={{ width: 30, height: 30, borderRadius: 1.5, bgcolor: '#eef1f6', display: 'grid', placeItems: 'center' }}>
                <History sx={{ fontSize: 17, color: '#64748b' }} />
              </Box>
              <Typography variant="subtitle1" fontWeight={800} sx={{ color: INK }}>Visitas anteriores</Typography>
              <Chip size="small" icon={<Lock sx={{ fontSize: 13 }} />} label="Solo lectura" variant="outlined" sx={{ fontWeight: 600 }} />
              <Box sx={{ flex: 1 }} />
              {verHistorial ? <ExpandLess sx={{ color: '#64748b' }} /> : <ExpandMore sx={{ color: '#64748b' }} />}
            </Stack>
            {verHistorial && (
              historialCargando ? (
                <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box>
              ) : historial.length === 0 ? (
                <Alert severity="info" sx={{ mt: 1 }}>Sin visitas registradas en los últimos 30 días.</Alert>
              ) : (
                <Stack divider={<Divider />} sx={{ mt: 1 }}>
                  {historial.map((v) => (
                    <Box key={v.id} sx={{ py: 1 }}>
                      <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" rowGap={0.3}>
                        <Typography variant="body2" fontWeight={700} noWrap sx={{ flex: 1, minWidth: 140 }}>{v.medico}</Typography>
                        <Chip size="small" variant="outlined"
                              color={v.ejecutada ? (v.tipo_visita === 'R' ? 'info' : 'success') : 'default'}
                              label={v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : 'No-visita'} />
                        <Typography variant="caption" color="text.secondary">
                          {v.hora ? `${new Date(v.hora).toLocaleDateString()} ${new Date(v.hora).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}` : ''}
                        </Typography>
                      </Stack>
                      {(v.productos?.length ?? 0) > 0 && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {v.productos.join(' · ')}
                        </Typography>
                      )}
                      {!v.ejecutada && v.causa_no_visita && (
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          Causa: {v.causa_no_visita}
                        </Typography>
                      )}
                      {v.comentario && (
                        <Typography variant="caption" sx={{ display: 'block', mt: 0.3, fontStyle: 'italic',
                                                            bgcolor: '#f6f8fc', borderRadius: 1, px: 1, py: 0.5 }}>
                          “{v.comentario}”
                        </Typography>
                      )}
                    </Box>
                  ))}
                </Stack>
              )
            )}
          </CardContent>
        </Card>
      </>
      )}
    </Box>
  );
}
