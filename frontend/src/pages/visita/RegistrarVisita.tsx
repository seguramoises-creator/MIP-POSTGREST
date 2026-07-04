import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, ToggleButton, ToggleButtonGroup, CircularProgress, Avatar, Checkbox,
  Select, FormControl, Divider,
} from '@mui/material';
import { CheckCircle, Save, EventBusy, AccessAlarm, Medication, ChatBubbleOutline, Assignment, FiberManualRecord, SupervisorAccount } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  agendaHoy, listarCausas, misVisitasHoy, registrarVisita, registrarNoVisita, listarVMs, obtenerParrilla, miGerente, subirFotoVisita,
  type AgendaMedico, type VisitaHoy, type Catalogo, type ParrillaItem, type ProductoDetalle, type MiGerente,
} from '../../services/visita.service';

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
  const [detallados, setDetallados] = useState<Record<string, number>>({});   // producto → mención (0 = no marcado)
  const [guardando, setGuardando] = useState(false);
  const [gd, setGd] = useState<MiGerente | null>(null);
  const [gps, setGps] = useState<{ lat: number; lng: number } | null>(null);
  const [foto, setFoto] = useState<File | null>(null);
  const [fotoPreview, setFotoPreview] = useState<string | null>(null);

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
  useEffect(() => {
    if (listo) miGerente(vmParam).then(setGd).catch(() => setGd(null));
    else setGd(null);
  }, [listo, vmParam]);

  // Al seleccionar un médico: precarga tipo, hora actual y la parrilla de productos.
  function seleccionar(m: AgendaMedico) {
    if (m.estado === 'registrada') return;
    setSel(m); setTipo((m.tipo_visita === 'R' ? 'R' : 'V')); setHora(hhmm(new Date()));
    setComentario(''); setModoNoVisita(false); setCausa(''); setDetallados({}); setMsg(null);
    obtenerParrilla(m.linea_id ?? undefined).then(setProductos).catch(() => setProductos([]));
  }

  // Minutos transcurridos desde la hora indicada (para la ventana de 60 min).
  const haceMin = useMemo(() => {
    const [h, mi] = hora.split(':').map(Number);
    const now = new Date();
    const sel2 = new Date(now); sel2.setHours(h, mi, 0, 0);
    return Math.round((now.getTime() - sel2.getTime()) / 60000);
  }, [hora]);
  const horaOk = haceMin >= 0 && haceMin <= 60;

  const toggleProd = (p: string) => setDetallados((d) => {
    const n = { ...d };
    if (n[p]) delete n[p]; else n[p] = 1;
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
    const prods: ProductoDetalle[] = Object.entries(detallados).map(([producto, mencion]) => ({ producto, mencion }));
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
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
        <Typography variant="h5" fontWeight={700}>Registrar Visita</Typography>
        {gd?.gerente && (
          <Chip color="primary" variant="outlined" icon={<SupervisorAccount />}
                label={`Gerente de Distrito: ${gd.gerente}${gd.linea ? ` · ${gd.linea}` : ''}`} sx={{ fontWeight: 600 }} />
        )}
      </Stack>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {!esVM && (
        <TextField select fullWidth size="small" label="Visitador (VM)" value={vmId} sx={{ mb: 2 }}
                   helperText="Elige el visitador para ver su agenda del día"
                   onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
          <MenuItem value=""><em>— Selecciona un visitador —</em></MenuItem>
          {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
        </TextField>
      )}

      {!listo ? (
        <Alert severity="info">Selecciona un visitador para ver su agenda.</Alert>
      ) : (
      <>
        {/* Médicos de hoy (agenda) */}
        <Card variant="outlined" sx={{ mb: 2 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Assignment fontSize="small" color="action" />
              <Typography variant="subtitle1" fontWeight={700}>Médicos de hoy</Typography>
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color={pendientes ? 'warning' : 'success'} label={pendientes ? `${pendientes} pendiente${pendientes > 1 ? 's' : ''}` : 'Al día'} />
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
                        <Typography variant="body2" fontWeight={700} noWrap>{a.nombre}</Typography>
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
          <Card variant="outlined" sx={{ mb: 2 }}>
            <Box sx={{ bgcolor: 'rgba(46,91,255,0.06)', px: 2, py: 1.5, display: 'flex', alignItems: 'center', gap: 1.5 }}>
              {avatar(sel.nombre, sel.categoria, sel.medico_id, 40)}
              <Box sx={{ flex: 1, minWidth: 0 }}>
                <Typography variant="body1" fontWeight={700} noWrap>{sel.nombre}</Typography>
                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                  {[sel.especialidad, sel.centro_trabajo, sel.provincia].filter(Boolean).join(' · ') || 'Sin datos'}
                </Typography>
              </Box>
              <ToggleButtonGroup exclusive size="small" value={tipo} onChange={(_, v) => v && setTipo(v)}>
                <ToggleButton value="V">Vista</ToggleButton>
                <ToggleButton value="R">Revisita</ToggleButton>
              </ToggleButtonGroup>
            </Box>
            <CardContent>
              <Stack spacing={2}>
                {!modoNoVisita && (
                  <Box>
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                      <AccessAlarm fontSize="small" color="error" />
                      <Typography variant="body2" fontWeight={600}>Hora real de la visita</Typography>
                    </Stack>
                    <TextField type="time" size="small" value={hora} onChange={(e) => setHora(e.target.value)} sx={{ width: 180 }} />
                    <Typography variant="caption" sx={{ display: 'block', mt: 0.5, color: horaOk ? 'success.main' : 'error.main' }}>
                      Hora actual: {hhmm(new Date())} · {horaOk ? 'Dentro del rango de 60 min ✓' : 'Fuera del rango de 60 min ✗'}
                    </Typography>
                  </Box>
                )}

                {!modoNoVisita && (
                  <Box>
                    <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                      <Medication fontSize="small" color="primary" />
                      <Typography variant="body2" fontWeight={600}>Productos detallados</Typography>
                    </Stack>
                    {productos.length === 0 ? (
                      <Typography variant="caption" color="text.secondary">No hay parrilla de productos para esta línea.</Typography>
                    ) : (
                      <Stack divider={<Divider />}>
                        {productos.map((p) => {
                          const on = detallados[p.producto] !== undefined;
                          return (
                            <Stack key={p.producto} direction="row" alignItems="center" spacing={1}
                                   sx={{ py: 0.5, bgcolor: on ? 'rgba(46,91,255,0.06)' : 'transparent', borderRadius: 1, px: 0.5 }}>
                              <Checkbox size="small" checked={on} onChange={() => toggleProd(p.producto)} />
                              <Typography variant="body2" sx={{ flex: 1 }}>{p.producto}</Typography>
                              <FormControl size="small" sx={{ minWidth: 120 }}>
                                <Select value={detallados[p.producto] ?? 1} disabled={!on}
                                        onChange={(e) => setDetallados((d) => ({ ...d, [p.producto]: Number(e.target.value) }))}>
                                  {MENCIONES.map((m) => <MenuItem key={m} value={m}>{m}ª mención</MenuItem>)}
                                </Select>
                              </FormControl>
                            </Stack>
                          );
                        })}
                      </Stack>
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
                  <Stack direction="row" alignItems="center" spacing={0.5} sx={{ mb: 0.5 }}>
                    <ChatBubbleOutline fontSize="small" color="secondary" />
                    <Typography variant="body2" fontWeight={600}>Comentario de visita <span style={{ color: '#d32f2f' }}>*</span></Typography>
                  </Stack>
                  <TextField fullWidth multiline minRows={3} value={comentario}
                             onChange={(e) => setComentario(e.target.value)}
                             placeholder="Describe algo relevante que ocurrió en la visita…"
                             helperText='Mínimo 10 caracteres · No escribas solo "Visita OK"' />
                </Box>

                {!modoNoVisita && (
                  <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
                    <Button size="small" variant="outlined" startIcon={<span>📍</span>}
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
                    <Button size="small" variant="outlined" component="label" startIcon={<span>📷</span>}>
                      {foto ? 'Cambiar foto' : 'Foto del centro'}
                      <input hidden type="file" accept="image/*" capture="environment"
                             onChange={(e) => { const f = e.target.files?.[0] || null; setFoto(f); setFotoPreview(f ? URL.createObjectURL(f) : null); }} />
                    </Button>
                    {fotoPreview && <Box component="img" src={fotoPreview} alt="foto" sx={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 1, border: '1px solid #ddd' }} />}
                  </Stack>
                )}

                <Stack direction="row" spacing={1.5}>
                  <Button variant="contained" color="success" fullWidth startIcon={<Save />}
                          disabled={guardando || (!modoNoVisita && comentario.trim().length < 10)}
                          onClick={guardar}>
                    {guardando ? 'Guardando…' : (modoNoVisita ? 'Registrar no-visita' : 'Guardar Visita')}
                  </Button>
                  <Button variant="outlined" color={modoNoVisita ? 'primary' : 'error'} startIcon={<EventBusy />}
                          onClick={() => { setModoNoVisita(!modoNoVisita); setMsg(null); }}>
                    {modoNoVisita ? 'Fue visita' : 'No visité'}
                  </Button>
                </Stack>
              </Stack>
            </CardContent>
          </Card>
        )}

        {/* Registradas hoy */}
        <Card variant="outlined">
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <CheckCircle fontSize="small" color="success" />
              <Typography variant="subtitle1" fontWeight={700}>Registradas hoy</Typography>
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color="success" variant="outlined" label={`${registradas.length} visita${registradas.length === 1 ? '' : 's'}`} />
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
                        <Typography variant="body2" fontWeight={600} noWrap>
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
      </>
      )}
    </Box>
  );
}
