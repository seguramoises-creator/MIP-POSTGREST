import { useEffect, useState, useCallback, useMemo, useRef } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, ToggleButton, ToggleButtonGroup, CircularProgress, Avatar, Checkbox, Switch, FormControlLabel,
  Select, FormControl, Divider, Autocomplete,
} from '@mui/material';
import { CheckCircle, Save, EventBusy, AccessAlarm, Medication, ChatBubbleOutline, Assignment, FiberManualRecord, SupervisorAccount, History, ExpandMore, ExpandLess, Lock, LocalPharmacy, MedicalServices } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import {
  agendaHoy, listarCausas, misVisitasHoy, registrarVisita, registrarNoVisita, listarVMs, obtenerParrilla, miGerente, subirFotoVisita, historialVisitas, registrarMuestras, listarMedicos,
  type AgendaMedico, type VisitaHoy, type Catalogo, type ParrillaItem, type ProductoDetalle, type MiGerente, type MedicoVisita,
} from '../../services/visita.service';
import {
  listarPanelFarmacias, registrarVisitaFarmacia, subirFotoVisitaFarmacia,
  type FarmaciaPanelItem,
} from '../../services/farmacias.service';

// ── Paleta profesional (médica / farmacéutica) ───────────────────────────────
const NAVY = '#2A2622';       // azul corporativo profundo
const AZUL_VISTA = '#686158'; // azul de VISTA (primary.main) — titulo y borde de tarjeta
const TEAL = '#0f9b8e';       // acento clínico (teal-verde)
const INK = '#1e293b';        // texto principal
const SOFT_SHADOW = '0 1px 3px rgba(16,24,40,0.06), 0 6px 20px rgba(16,24,40,0.05)';
// Tarjeta base: sombra suave en vez de bordes marcados (menos saturación visual).
const cardSx = { borderRadius: 3, border: '1px solid #EFEBE6', boxShadow: SOFT_SHADOW } as const;
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

// Normaliza cualquier foto (incluida HEIC de iPhone que el navegador pueda decodificar)
// a JPEG redimensionado y comprimido: garantiza formato válido y tamaño subible, con
// buena calidad. Si algo falla, devuelve el archivo original (el backend tiene margen).
async function comprimirImagen(file: File, maxLado = 2200, calidad = 0.85): Promise<File> {
  try {
    const dataUrl = await new Promise<string>((res, rej) => {
      const fr = new FileReader();
      fr.onload = () => res(fr.result as string);
      fr.onerror = () => rej(new Error('read'));
      fr.readAsDataURL(file);
    });
    const img = await new Promise<HTMLImageElement>((res, rej) => {
      const i = new Image();
      i.onload = () => res(i);
      i.onerror = () => rej(new Error('decode'));
      i.src = dataUrl;
    });
    let { width, height } = img;
    if (!width || !height) return file;
    const mayor = Math.max(width, height);
    if (mayor > maxLado) { const f = maxLado / mayor; width = Math.round(width * f); height = Math.round(height * f); }
    const canvas = document.createElement('canvas');
    canvas.width = width; canvas.height = height;
    const ctx = canvas.getContext('2d');
    if (!ctx) return file;
    ctx.drawImage(img, 0, 0, width, height);
    const blob = await new Promise<Blob | null>((res) => canvas.toBlob(res, 'image/jpeg', calidad));
    if (!blob) return file;
    const nombre = (file.name.replace(/\.[^.]+$/, '') || 'foto') + '.jpg';
    return new File([blob], nombre, { type: 'image/jpeg' });
  } catch {
    return file;
  }
}

// Estado de sincronización local de una visita del feed "Registradas hoy".
type SyncEstado = 'local' | 'sincronizado' | 'error';
interface Registrada extends VisitaHoy { sync: SyncEstado; }

// Sub-proyecto 3 (integración Mallén): el registro manual de visitas quedó
// cerrado — las visitas ahora llegan del SFA de Mallén y se integran
// automáticamente (POST /visita/registrar, /visita/no-visita,
// /visita/muestras y /farmacias/visitar devuelven 409). Los controles de
// escritura (registrar, no-visita, GPS, foto) se ocultan en ambos
// formularios (médico y farmacia); lo ya registrado —"Registradas hoy",
// "Visitas anteriores" y el panel de farmacias— se sigue mostrando tal cual.
const CAPTURA_VISITAS_CERRADA = true;

export default function RegistrarVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  // Ciclo abierto del contexto global — solo lo usa la pestaña Farmacia, para pedirle
  // al panel el estado de visita (hoy/ciclo) + último comentario, como la de Médico
  // (que resuelve el ciclo del lado del servidor vía `ciclo_por_defecto`).
  const cicloAbiertoId = useCicloStore((s) => s.cicloAbiertoId);
  // País del contexto global — aislamiento multipaís en el selector de VM (ADMIN/GERENTE).
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  // Sin contexto de ciclo: el registro SIEMPRE opera sobre el ciclo abierto del
  // país del visitador (el backend lo resuelve y lo protege con su guard).

  // Selector Médico / Farmacia: la visita a farmacia se registra en esta MISMA pantalla
  // (tabla paralela Visita.FactVisitaFarmacia en el backend, Opción A — cero regresión
  // sobre el flujo de médicos existente).
  const [tipoEntidad, setTipoEntidad] = useState<'medico' | 'farmacia'>('medico');

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');
  const [agenda, setAgenda] = useState<AgendaMedico[]>([]);
  // Requerimiento Mallén (Item 1): panel completo del VM para buscar médicos FUERA de la
  // agenda del día (visita no programada) — se registran igual, sin salir de la pantalla.
  const [panel, setPanel] = useState<MedicoVisita[]>([]);
  const [causas, setCausas] = useState<string[]>([]);
  const [registradas, setRegistradas] = useState<Registrada[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [sel, setSel] = useState<AgendaMedico | null>(null);
  const [catFiltro, setCatFiltro] = useState('');   // filtro de la agenda: '' = todas
  const [busqueda, setBusqueda] = useState('');
  const formRef = useRef<HTMLDivElement>(null);       // para enfocar el formulario al seleccionar
  const [tipo, setTipo] = useState<'V' | 'R'>('V');
  const [hora, setHora] = useState(hhmm(new Date()));
  const [comentario, setComentario] = useState('');
  const [acompanado, setAcompanado] = useState(false);  // visita acompañada por el Gerente
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

  // ── Farmacia (AD-HOC, sin planeación): panel APROBADO del VM + registro simple ──
  const [farmacias, setFarmacias] = useState<FarmaciaPanelItem[]>([]);
  const [farmBusqueda, setFarmBusqueda] = useState('');
  const [selFarmacia, setSelFarmacia] = useState<FarmaciaPanelItem | null>(null);
  const formRefFarmacia = useRef<HTMLDivElement>(null);
  const [farmComentario, setFarmComentario] = useState('');
  const [farmModoNoVisita, setFarmModoNoVisita] = useState(false);
  const [farmCausa, setFarmCausa] = useState('');
  const [farmGps, setFarmGps] = useState<{ lat: number; lng: number } | null>(null);
  const [farmFoto, setFarmFoto] = useState<File | null>(null);
  const [farmFotoPreview, setFarmFotoPreview] = useState<string | null>(null);
  const [farmGuardando, setFarmGuardando] = useState(false);

  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  const cargarAgenda = useCallback(() => {
    if (!listo) { setAgenda([]); setPanel([]); return; }
    agendaHoy(vmParam).then(setAgenda).catch(() => setAgenda([]));
    listarMedicos(vmParam, false, true).then(setPanel).catch(() => setPanel([]));
  }, [listo, vmParam]);

  const cargarRegistradas = useCallback(() => {
    if (!listo) { setRegistradas([]); return; }
    // Todo lo que devuelve el servidor está CONFIRMADO en BD → verde.
    misVisitasHoy(vmParam).then((vs) => setRegistradas(vs.map((v) => ({ ...v, sync: 'sincronizado' as SyncEstado }))))
      .catch(() => setRegistradas([]));
  }, [listo, vmParam]);

  useEffect(() => {
    listarCausas().then(setCausas).catch(() => {});
    if (!esVM) listarVMs(paisCodigo).then(setVms).catch(() => {});
    setCargando(false);
  }, [esVM, paisCodigo]);

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

  // Farmacias del panel — solo cuentan las APROBADO (F22: pendientes no aparecen aquí).
  // Con `cicloAbiertoId` el backend agrega estado de visita (hoy/ciclo) + último
  // comentario (`visita_farmacia_service.estado_visita_panel`), igual que la pestaña
  // de Médico (que resuelve el ciclo del lado del servidor).
  const cargarFarmacias = useCallback(() => {
    if (tipoEntidad !== 'farmacia' || !listo) { setFarmacias([]); return; }
    listarPanelFarmacias(vmParam, false, cicloAbiertoId ?? undefined)
      .then((r) => setFarmacias(r.filter((f) => f.estado_aprobacion === 'APROBADO')))
      .catch(() => setFarmacias([]));
  }, [tipoEntidad, listo, vmParam, cicloAbiertoId]);
  useEffect(() => { cargarFarmacias(); }, [cargarFarmacias]);

  const farmaciasFiltradas = useMemo(() => {
    const q = farmBusqueda.trim().toUpperCase();
    return farmacias.filter((f) => !q || (f.nombre_completo ?? '').toUpperCase().includes(q));
  }, [farmacias, farmBusqueda]);

  // Dos grupos, como médico (día/ciclo) pero adaptado AD-HOC: Pendientes (sin
  // registro en el ciclo abierto) vs Visitadas (hoy o en algún momento del ciclo).
  const farmaciasPendientes = useMemo(
    () => farmaciasFiltradas.filter((f) => !f.visitada_hoy && !f.visitada_ciclo), [farmaciasFiltradas]);
  const farmaciasVisitadas = useMemo(
    () => farmaciasFiltradas.filter((f) => f.visitada_hoy || f.visitada_ciclo), [farmaciasFiltradas]);

  function seleccionarFarmacia(f: FarmaciaPanelItem) {
    setSelFarmacia(f); setFarmComentario(''); setFarmModoNoVisita(false); setFarmCausa('');
    setFarmGps(null); setFarmFoto(null); setFarmFotoPreview(null); setMsg(null);
    setTimeout(() => formRefFarmacia.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  }

  async function guardarFarmacia() {
    if (!selFarmacia) return;
    if (farmModoNoVisita && !farmCausa) { setMsg({ tipo: 'error', texto: 'Selecciona la causa.' }); return; }
    setFarmGuardando(true); setMsg(null);
    try {
      const r = await registrarVisitaFarmacia(selFarmacia.panel_id, {
        comentario: farmComentario || undefined,
        ejecutada: !farmModoNoVisita,
        causa_no_visita: farmModoNoVisita ? farmCausa : undefined,
        latitud: farmGps?.lat ?? null,
        longitud: farmGps?.lng ?? null,
      }, vmParam);
      if (farmFoto && r?.id) {
        try {
          const fotoLista = await comprimirImagen(farmFoto);
          await subirFotoVisitaFarmacia(r.id, fotoLista);
        } catch { setMsg({ tipo: 'error', texto: 'Visita registrada, pero la foto no se pudo subir.' }); }
      }
      setMsg((m) => m ?? { tipo: 'success', texto: farmModoNoVisita ? 'No-visita a farmacia registrada.' : 'Visita a farmacia registrada.' });
      setSelFarmacia(null); setFarmGps(null); setFarmFoto(null); setFarmFotoPreview(null);
      setFarmComentario(''); setFarmModoNoVisita(false); setFarmCausa('');
      // Refresca el panel para que la farmacia pase a "Registrada hoy" / grupo Visitadas.
      cargarFarmacias();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo registrar la visita a la farmacia.') });
    } finally { setFarmGuardando(false); }
  }

  // Al seleccionar un médico: precarga tipo, hora actual y la parrilla de productos.
  function seleccionar(m: AgendaMedico) {
    if (m.estado === 'registrada') return;
    setSel(m); setTipo((m.tipo_visita === 'R' ? 'R' : 'V')); setHora(hhmm(new Date()));
    setComentario(''); setAcompanado(false); setModoNoVisita(false); setCausa(''); setDetallados({}); setMsg(null);
    // Parrilla de la LÍNEA DEL REPRESENTANTE (no la del médico), del ciclo abierto
    // de su país — la misma parrilla contra la que promociona y entrega muestras.
    obtenerParrilla(undefined, undefined, vmParam).then(setProductos).catch(() => setProductos([]));
    // Enfocar el formulario del médico seleccionado (queda justo a la vista).
    setTimeout(() => formRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' }), 80);
  }

  // Agenda filtrada por categoría y nombre (el filtro va en la parte superior del formulario).
  const agendaVisible = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return agenda.filter((a) =>
      (!catFiltro || a.categoria === catFiltro) &&
      (!q || (a.nombre ?? '').toUpperCase().includes(q)));
  }, [agenda, catFiltro, busqueda]);

  // Requerimiento Mallén (Item 1): médicos FUERA de la agenda del día (aprobados y activos
  // del panel, que no están programados para hoy) — para registrar una visita no programada.
  const fueraDeAgenda = useMemo(() => {
    const enAgenda = new Set(agenda.map((a) => a.medico_id));
    return panel.filter((m) =>
      m.activo && m.estado_aprobacion === 'APROBADO' && !enAgenda.has(m.id));
  }, [panel, agenda]);

  // Dos grupos: los del DÍA (día de la semana del tipo pendiente cae hoy) y los del CICLO (otro día).
  const delDia = useMemo(() => agendaVisible.filter((a) => a.grupo === 'dia'), [agendaVisible]);
  const delCiclo = useMemo(() => agendaVisible.filter((a) => a.grupo !== 'dia'), [agendaVisible]);

  // Registrar un médico fuera de la agenda: se trata como Vista no programada.
  function seleccionarFuera(m: MedicoVisita | null) {
    if (!m) return;
    seleccionar({
      medico_id: m.id, nombre: m.nombre_completo, especialidad: m.especialidad_nombre,
      categoria: m.categoria, centro_trabajo: m.centro_trabajo, provincia: m.provincia,
      linea_id: m.linea_id ?? null, tipo_visita: 'V', hora_estimada: null,
      estado: 'pendiente', no_visita: false,
    });
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
    } else {
      if (!horaOk) {
        setMsg({ tipo: 'error', texto: 'La hora está fuera de la ventana de 60 minutos.' }); return;
      }
      // Requerimiento Mallén: no se puede registrar una visita sin marcar ≥1 producto.
      if (Object.keys(detallados).length === 0) {
        setMsg({ tipo: 'error', texto: 'Marca al menos un producto promocionado para poder registrar la visita.' }); return;
      }
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
        const r = await registrarVisita(sel.medico_id, tipo, comentario, Math.max(0, Math.min(60, haceMin)), prods, vmParam, gps?.lat ?? null, gps?.lng ?? null, acompanado);
        // Muestras entregadas: alimentan el reporte de penetración/muestras vs meta.
        if (entregas.length) {
          try { await registrarMuestras(sel.medico_id, entregas, vmParam); }
          catch { setMsg({ tipo: 'error', texto: 'Visita registrada, pero las muestras no se pudieron registrar.' }); }
        }
        if (foto && r?.id) {
          try {
            // Convertir/comprimir a JPEG antes de subir (evita HEIC y exceso de tamaño del iPhone).
            const fotoLista = await comprimirImagen(foto);
            await subirFotoVisita(r.id, fotoLista);
          } catch { setMsg({ tipo: 'error', texto: 'Visita registrada, pero la foto no se pudo subir.' }); }
        }
      }
      setMsg((m) => m ?? { tipo: 'success', texto: modoNoVisita ? 'No-visita registrada.' : 'Visita registrada y confirmada en el servidor.' });
      setSel(null); setGps(null); setFoto(null); setFotoPreview(null); setAcompanado(false);
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

  // Formulario de registro — se renderiza INLINE, justo debajo del médico seleccionado.
  const formulario = sel ? (
    <div ref={formRef}>
      <Card elevation={0} sx={{ ...cardSx, mb: 1 }}>
        <Box sx={{ background: `linear-gradient(120deg, ${NAVY}0d 0%, ${TEAL}0d 100%)`,
                   borderBottom: '1px solid #EFEBE6', px: 2, py: 1.5, display: 'flex', alignItems: 'center',
                   gap: 1.5, flexWrap: 'wrap', rowGap: 1 }}>
          {avatar(sel.nombre, sel.categoria, sel.medico_id, 42)}
          <Box sx={{ flex: 1, minWidth: 120 }}>
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
                             sx={{ bgcolor: '#fff', borderRadius: 2, '& .MuiToggleButton-root': { border: '1px solid #E0DAD3', fontWeight: 700, px: 1.5,
                                   '&.Mui-selected': { bgcolor: NAVY, color: '#fff', '&:hover': { bgcolor: NAVY } } } }}>
            <ToggleButton value="V" disabled={sel?.tipo_visita === 'R'}
                          title={sel?.tipo_visita === 'R' ? 'La Vista de este médico ya fue registrada' : ''}>Vista</ToggleButton>
            <ToggleButton value="R" disabled={sel?.tipo_visita !== 'R'}
                          title={sel?.tipo_visita !== 'R' ? 'Primero registra la Vista (o el médico no tiene Revisita planeada)' : ''}>Revisita</ToggleButton>
          </ToggleButtonGroup>
        </Box>
        <CardContent>
          <Stack spacing={2}>
            {!modoNoVisita && (
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={2} alignItems="stretch">
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
                <Box sx={{ flex: 1, borderRadius: 2, p: 1.25,
                           background: `linear-gradient(135deg, ${NAVY}0a 0%, ${TEAL}0f 100%)`,
                           border: '1px solid #EFEBE6' }}>
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
                        <Stack direction="row" spacing={0.5} divider={<Divider orientation="vertical" flexItem sx={{ borderColor: '#E0DAD3' }} />}>
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
                  <Box sx={{ border: '1px solid #EFEBE6', borderRadius: 2, bgcolor: '#F9F8F6', px: 1, py: 0.25 }}>
                    <Stack divider={<Divider sx={{ borderColor: '#f0f3f8' }} />}>
                      {productos.map((p, idx) => {
                        const det = detallados[p.producto];
                        const on = det !== undefined;
                        const base = { mencion: Math.min(idx + 1, 3), muestras: p.meta_muestras || 0 };
                        return (
                          <Box key={p.producto}
                               sx={{ py: 1, px: 0.5, borderRadius: 1.5, bgcolor: on ? 'rgba(46,91,255,0.05)' : 'transparent',
                                     display: 'flex', flexWrap: 'wrap', alignItems: 'center', columnGap: 1, rowGap: 1 }}>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, minWidth: 0,
                                       flex: { xs: '1 1 100%', sm: '1 1 40%' } }}>
                              <Checkbox size="small" checked={on} onChange={() => toggleProd(p, idx)} sx={{ p: 0.5 }} />
                              <Avatar sx={{ width: 22, height: 22, fontSize: 11, fontWeight: 800, flexShrink: 0,
                                            bgcolor: p.prioridad === 1 ? '#686158' : p.prioridad === 2 ? '#584F46' : '#90a4ae' }}>
                                {p.prioridad}
                              </Avatar>
                              <Box sx={{ minWidth: 0, flex: 1 }}>
                                <Typography fontWeight={700} noWrap sx={{ fontSize: 'clamp(0.78rem, 3vw, 0.9rem)', lineHeight: 1.2 }}>
                                  {p.nombre || p.producto}
                                </Typography>
                                <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block', fontSize: '0.66rem' }}>
                                  Propuesto: {p.meta_muestras} muestra{p.meta_muestras === 1 ? '' : 's'} · {Math.min(idx + 1, 3)}ª mención
                                </Typography>
                              </Box>
                            </Box>
                            <Box sx={{ display: 'flex', alignItems: 'center', gap: 1,
                                       pl: { xs: 4.5, sm: 0 }, width: { xs: '100%', sm: 'auto' }, ml: { sm: 'auto' } }}>
                              <TextField size="small" type="number" label="Muestras" disabled={!on}
                                         value={det?.muestras ?? p.meta_muestras}
                                         onChange={(e) => {
                                           const q = Math.max(0, Math.min(999, Number(e.target.value) || 0));
                                           setDetallados((d) => ({ ...d, [p.producto]: { ...(d[p.producto] ?? base), muestras: q } }));
                                         }}
                                         inputProps={{ min: 0, max: 999 }}
                                         sx={{ width: 72, flexShrink: 0, '& input': { textAlign: 'center', fontWeight: 700 } }} />
                              <FormControl size="small" sx={{ minWidth: 108, flex: { xs: 1, sm: 'none' } }}>
                                <Select value={det?.mencion ?? base.mencion} disabled={!on}
                                        onChange={(e) => setDetallados((d) => ({ ...d, [p.producto]: { ...(d[p.producto] ?? base), mencion: Number(e.target.value) } }))}>
                                  {MENCIONES.map((m) => <MenuItem key={m} value={m}>{m}ª mención</MenuItem>)}
                                </Select>
                              </FormControl>
                            </Box>
                          </Box>
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
              <FormControlLabel
                control={<Switch checked={acompanado} onChange={(e) => setAcompanado(e.target.checked)} color="primary" />}
                label="Visita acompañada por el Gerente de Distrito"
                sx={{ '& .MuiFormControlLabel-label': { fontWeight: 600, fontSize: 14 } }}
              />
            )}

            {!CAPTURA_VISITAS_CERRADA && !modoNoVisita && (
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

            {!CAPTURA_VISITAS_CERRADA && (
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
            )}
          </Stack>
        </CardContent>
      </Card>
    </div>
  ) : null;

  // Renderiza un grupo titulado; el formulario aparece INLINE bajo el médico seleccionado.
  const renderGrupo = (titulo: string, lista: AgendaMedico[]) => (
    lista.length === 0 ? null : (
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="caption" sx={{ fontWeight: 800, letterSpacing: 0.6, textTransform: 'uppercase',
                    color: 'text.secondary', display: 'block', mb: 0.5 }}>
          {titulo} · {lista.length}
        </Typography>
        <Stack divider={<Divider />}>
          {lista.map((a) => {
            const activa = sel?.medico_id === a.medico_id;
            const reg = a.estado === 'registrada';
            return (
              <Box key={a.medico_id}>
                <Stack direction="row" alignItems="center" spacing={1.5}
                       onClick={() => seleccionar(a)}
                       sx={{ py: 1, px: 0.5, cursor: reg ? 'default' : 'pointer', borderRadius: 1,
                             bgcolor: activa ? 'rgba(255,193,7,0.14)' : 'transparent',
                             opacity: reg ? 0.7 : 1, '&:hover': { bgcolor: reg ? 'transparent' : 'action.hover' } }}>
                  {avatar(a.nombre, a.categoria, a.medico_id, 36)}
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontWeight={700} sx={{ fontSize: 'clamp(0.72rem, 2.6vw, 0.875rem)', lineHeight: 1.25,
                                display: '-webkit-box', WebkitLineClamp: 2, WebkitBoxOrient: 'vertical', overflow: 'hidden' }}>
                      {a.nombre}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                      {[a.especialidad, a.tipo_visita === 'R' ? 'Revisita' : 'Vista', a.dia_semana, a.hora_estimada].filter(Boolean).join(' · ')}
                    </Typography>
                  </Box>
                  {reg ? (
                    <Chip size="small" variant={a.no_visita ? 'filled' : 'outlined'}
                          color={a.no_visita ? 'error' : 'success'}
                          label={a.no_visita ? 'No visitado' : 'Registrada ✓'} />
                  ) : (
                    <Typography variant="caption" sx={{ color: 'warning.main', fontWeight: 700 }}>Pendiente</Typography>
                  )}
                </Stack>
                {activa && <Box sx={{ mt: 1 }}>{formulario}</Box>}
              </Box>
            );
          })}
        </Stack>
      </Box>
    )
  );

  // Badge Cadena/Independiente — igual criterio para la fila del panel y el
  // encabezado del formulario (deriva de `es_cadena` del maestro).
  const badgeCadena = (esCadena: boolean | undefined, size: 'tiny' | 'normal' = 'normal') => (
    <Chip size="small" variant="outlined" color={esCadena ? 'info' : 'default'}
          label={esCadena ? 'Cadena' : 'Independiente'}
          sx={{ height: size === 'tiny' ? 18 : 20, fontSize: size === 'tiny' ? '0.6rem' : '0.66rem', fontWeight: 700 }} />
  );

  // Formulario de registro de visita a farmacia — INLINE bajo la farmacia
  // seleccionada (mismo patrón que el formulario de médico, `formulario` arriba).
  const formularioFarmacia = selFarmacia ? (
    <div ref={formRefFarmacia}>
      <Card elevation={0} sx={{ ...cardSx, mb: 1 }}>
        <Box sx={{ background: `linear-gradient(120deg, ${NAVY}0d 0%, ${TEAL}0d 100%)`,
                   borderBottom: '1px solid #EFEBE6', px: 2, py: 1.5 }}>
          <Stack direction="row" alignItems="center" spacing={1} flexWrap="wrap" rowGap={0.3}>
            <Typography fontWeight={800} sx={{ color: INK, fontSize: 'clamp(0.82rem, 3.2vw, 1.05rem)' }}>
              {selFarmacia.nombre_completo}
            </Typography>
            {badgeCadena(selFarmacia.es_cadena)}
          </Stack>
          <Typography variant="caption" color="text.secondary">
            {[selFarmacia.direccion, selFarmacia.encargado ? `Encargado: ${selFarmacia.encargado}` : null].filter(Boolean).join(' · ')}
          </Typography>
        </Box>
        <CardContent>
          <Stack spacing={2}>
            {farmModoNoVisita && (
              <TextField select label="Causa de no-visita" value={farmCausa} required
                         onChange={(e) => setFarmCausa(e.target.value)}>
                {causas.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
            )}
            <Box>
              <Stack direction="row" alignItems="center" spacing={0.75} sx={{ mb: 0.75 }}>
                <ChatBubbleOutline sx={{ fontSize: 18, color: TEAL }} />
                <Typography variant="caption" sx={secHeadSx}>Comentario de visita</Typography>
              </Stack>
              <TextField fullWidth multiline minRows={2} maxRows={4} value={farmComentario}
                         onChange={(e) => setFarmComentario(e.target.value)}
                         placeholder="Describe algo relevante que ocurrió en la visita… (opcional)" />
            </Box>
            {!CAPTURA_VISITAS_CERRADA && !farmModoNoVisita && (
              <Stack direction="row" spacing={1.25} alignItems="center" flexWrap="wrap" rowGap={1}>
                <Button size="small" variant="outlined" startIcon={<span>📍</span>}
                        color={farmGps ? 'success' : 'primary'}
                        sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, borderWidth: 1.5 }}
                        onClick={() => {
                          if (!navigator.geolocation) { setMsg({ tipo: 'error', texto: 'Este dispositivo no soporta geolocalización.' }); return; }
                          navigator.geolocation.getCurrentPosition(
                            (pos) => setFarmGps({ lat: pos.coords.latitude, lng: pos.coords.longitude }),
                            () => setMsg({ tipo: 'error', texto: 'No se pudo obtener la ubicación (permiso denegado o sin señal).' }),
                            { enableHighAccuracy: true, timeout: 8000 });
                        }}>
                  {farmGps ? 'Ubicación capturada' : 'Capturar ubicación'}
                </Button>
                {farmGps && <Typography variant="caption" color="text.secondary">📍 {farmGps.lat.toFixed(5)}, {farmGps.lng.toFixed(5)}</Typography>}
                <Button size="small" variant="outlined" component="label" startIcon={<span>📷</span>}
                        color={farmFoto ? 'success' : 'primary'}
                        sx={{ borderRadius: 2, textTransform: 'none', fontWeight: 700, borderWidth: 1.5 }}>
                  {farmFoto ? 'Cambiar foto' : 'Foto de la farmacia'}
                  <input hidden type="file" accept="image/*" capture="environment"
                         onChange={(e) => { const f = e.target.files?.[0] || null; setFarmFoto(f); setFarmFotoPreview(f ? URL.createObjectURL(f) : null); }} />
                </Button>
                {farmFotoPreview && <Box component="img" src={farmFotoPreview} alt="foto" sx={{ width: 56, height: 56, objectFit: 'cover', borderRadius: 1, border: '1px solid #ddd' }} />}
              </Stack>
            )}
            {!CAPTURA_VISITAS_CERRADA && (
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ pt: 0.5 }}>
                <Button variant="contained" fullWidth startIcon={<Save />}
                        disabled={farmGuardando}
                        onClick={guardarFarmacia}
                        sx={{ py: 1.25, borderRadius: 2.5, fontWeight: 800, textTransform: 'none', fontSize: '0.95rem',
                              boxShadow: '0 8px 18px rgba(15,155,142,0.30)',
                              background: `linear-gradient(120deg, ${TEAL} 0%, #0b7d72 100%)`,
                              '&:hover': { background: `linear-gradient(120deg, #0d8a7f 0%, #0a6f66 100%)` },
                              '&.Mui-disabled': { background: '#cbd5e1', color: '#fff', boxShadow: 'none' } }}>
                  {farmGuardando ? 'Guardando…' : (farmModoNoVisita ? 'Registrar no-visita' : 'Guardar visita')}
                </Button>
                <Button variant="outlined" color={farmModoNoVisita ? 'primary' : 'error'} startIcon={<EventBusy />}
                        onClick={() => { setFarmModoNoVisita(!farmModoNoVisita); setMsg(null); }}
                        sx={{ py: 1.25, borderRadius: 2.5, fontWeight: 700, textTransform: 'none', borderWidth: 1.5 }}>
                  {farmModoNoVisita ? 'Fue visita' : 'No visité'}
                </Button>
              </Stack>
            )}
          </Stack>
        </CardContent>
      </Card>
    </div>
  ) : null;

  // Renderiza un grupo de farmacias (Pendientes/Visitadas); el formulario aparece
  // INLINE bajo la farmacia seleccionada — mismo patrón que `renderGrupo` (médico).
  const renderGrupoFarmacia = (titulo: string, lista: FarmaciaPanelItem[]) => (
    lista.length === 0 ? null : (
      <Box sx={{ mb: 1.5 }}>
        <Typography variant="caption" sx={{ ...secHeadSx, display: 'block', mb: 0.5 }}>
          {titulo} · {lista.length}
        </Typography>
        <Stack divider={<Divider />}>
          {lista.map((f) => {
            const activa = selFarmacia?.panel_id === f.panel_id;
            return (
              <Box key={f.panel_id}>
                <Stack direction="row" alignItems="center" spacing={1.5}
                       onClick={() => seleccionarFarmacia(f)}
                       sx={{ py: 1, px: 0.5, cursor: 'pointer', borderRadius: 1,
                             bgcolor: activa ? 'rgba(255,193,7,0.14)' : 'transparent',
                             '&:hover': { bgcolor: 'action.hover' } }}>
                  <Avatar sx={{ bgcolor: `${TEAL}1a`, color: TEAL, width: 36, height: 36 }}><LocalPharmacy fontSize="small" /></Avatar>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Stack direction="row" alignItems="center" spacing={0.6} flexWrap="wrap" rowGap={0.2}>
                      <Typography fontWeight={700} noWrap sx={{ fontSize: 'clamp(0.78rem, 3vw, 0.9rem)' }}>
                        {f.nombre_completo ?? '—'}
                      </Typography>
                      {badgeCadena(f.es_cadena, 'tiny')}
                    </Stack>
                    <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                      {f.direccion ?? 'Sin dirección'}
                    </Typography>
                    {f.ultimo_comentario && (
                      <Typography variant="caption" title={f.ultimo_comentario}
                                  sx={{ display: 'block', mt: 0.2, fontStyle: 'italic', color: 'text.secondary',
                                        overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        “{f.ultimo_comentario}”
                      </Typography>
                    )}
                  </Box>
                  {f.visitada_hoy ? (
                    <Chip size="small" variant="filled" color="success" label="Registrada hoy ✓" />
                  ) : f.visitada_ciclo ? (
                    <Chip size="small" variant="outlined" color="info" label="Visitada" />
                  ) : (
                    <Typography variant="caption" sx={{ color: 'warning.main', fontWeight: 700 }}>Pendiente</Typography>
                  )}
                </Stack>
                {activa && <Box sx={{ mt: 1 }}>{formularioFarmacia}</Box>}
              </Box>
            );
          })}
        </Stack>
      </Box>
    )
  );

  return (
    <Box sx={{ maxWidth: 620, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
      <Alert severity="info" sx={{ mb: 2 }}>
        El registro de visitas está cerrado: las visitas provienen del SFA de Mallén
        y se integran automáticamente. Lo ya registrado sigue disponible para consulta.
      </Alert>
      {/* Encabezado de la pantalla.
          ANTES era un bloque con degradado azul oscuro y un halo teal difuminado.
          Dejó de funcionar cuando la navegación pasó a barras azules: la pestaña
          de arriba ya dice "Registrar Visita" sobre azul, así que este bloque
          repetía el mismo título en un segundo azul, más pesado, y las dos masas
          competían. Ahora es una tarjeta clara: el azul se queda en el marco de la
          app y aquí manda el contenido. Fuera también el halo decorativo — no
          decía nada. */}
      <Box sx={{
        bgcolor: '#fff', borderRadius: 3, p: { xs: 2, sm: 2.5 }, mb: 2.5,
        // Borde en el azul de VISTA — es lo que ata la tarjeta al marco de la app
        // ahora que ya no lleva el degradado dentro.
        border: `1.5px solid ${AZUL_VISTA}`, boxShadow: '0 1px 2px rgba(16,20,58,0.04)',
      }}>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap" rowGap={1}>
          {/* Cuadrado con tinte de marca en vez de círculo sobre degradado: pesa
              menos y deja el acento azul donde se necesita, no de fondo. */}
          <Box sx={{
            width: 44, height: 44, borderRadius: 2, flexShrink: 0,
            bgcolor: 'rgba(104,97,88,0.08)', display: 'grid', placeItems: 'center',
          }}>
            <Assignment sx={{ color: AZUL_VISTA, fontSize: 24 }} />
          </Box>
          <Box sx={{ flex: 1, minWidth: 170 }}>
            <Typography sx={{ fontWeight: 700, color: AZUL_VISTA, letterSpacing: '-0.02em',
                              lineHeight: 1.2, fontSize: { xs: '1.15rem', sm: '1.35rem' } }}>
              Registrar Visita
            </Typography>
            <Typography sx={{ color: '#6B7183', fontSize: 13, display: 'block' }}>
              {(() => { const f = new Date().toLocaleDateString('es-DO', { weekday: 'long', day: 'numeric', month: 'long' });
                        return f.charAt(0).toUpperCase() + f.slice(1); })()} · Captura en campo
            </Typography>
          </Box>
          {gd?.gerente && (
            <Chip size="small" variant="outlined"
                  icon={<SupervisorAccount sx={{ color: `${AZUL_VISTA} !important` }} />}
                  label={`GD: ${gd.gerente}${gd.linea ? ` · ${gd.linea}` : ''}`}
                  sx={{ color: AZUL_VISTA, borderColor: 'rgba(104,97,88,0.35)', fontWeight: 600, maxWidth: '100%' }} />
          )}
        </Stack>

        {/* Sin contexto País/Ciclo: el registro SIEMPRE va al ciclo abierto del país
            del visitador (el backend lo impone) — mostrarlo aquí era redundante.
            El selector solo aparece para gestión; el VM ya es él mismo.
            Va directo sobre la tarjeta: el panel dentro del panel que había antes
            solo existía para despegarlo del degradado. */}
        {!esVM && (
          <Box sx={{ mt: 2, pt: 2, borderTop: '1px solid #EDE9E4' }}>
            <TextField select fullWidth size="small" label="Visitador (VM)" value={vmId}
                       helperText="Elige el visitador para ver su agenda del día"
                       onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
              <MenuItem value=""><span style={{ opacity: 0.7 }}>— Selecciona un visitador —</span></MenuItem>
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
        {/* Selector Médico / Farmacia — la visita a farmacia usa la MISMA pantalla
            (tabla paralela en el backend, Opción A). */}
        <ToggleButtonGroup exclusive size="small" value={tipoEntidad}
                           onChange={(_, v) => { if (v) { setTipoEntidad(v); setMsg(null); } }}
                           sx={{ mb: 2, bgcolor: '#fff', borderRadius: 2, boxShadow: SOFT_SHADOW,
                                 '& .MuiToggleButton-root': { border: '1px solid #E0DAD3', fontWeight: 700, px: 2, textTransform: 'none',
                                       '&.Mui-selected': { bgcolor: NAVY, color: '#fff', '&:hover': { bgcolor: NAVY } } } }}>
          <ToggleButton value="medico"><MedicalServices sx={{ fontSize: 18, mr: 0.75 }} />Médico</ToggleButton>
          <ToggleButton value="farmacia"><LocalPharmacy sx={{ fontSize: 18, mr: 0.75 }} />Farmacia</ToggleButton>
        </ToggleButtonGroup>

        {tipoEntidad === 'farmacia' ? (
        <>
        {/* Panel de farmacias (solo APROBADO — F22) — agrupado Pendientes/Visitadas,
            con badge Cadena/Independiente, estado de visita y último comentario,
            igual criterio que la pestaña de Médico. */}
        <Card elevation={0} sx={{ ...cardSx, mb: 2 }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <Box sx={{ width: 30, height: 30, borderRadius: 1.5, bgcolor: `${NAVY}0f`, display: 'grid', placeItems: 'center' }}>
                <LocalPharmacy sx={{ fontSize: 17, color: NAVY }} />
              </Box>
              <Typography variant="subtitle1" fontWeight={800} sx={{ color: INK }}>Mis farmacias</Typography>
              <Box sx={{ flex: 1 }} />
              <Chip size="small" color="success" variant="outlined" label={`${farmacias.length} activa${farmacias.length === 1 ? '' : 's'}`} sx={{ fontWeight: 700 }} />
            </Stack>
            <TextField size="small" fullWidth placeholder="Buscar farmacia…" value={farmBusqueda} sx={{ mb: 1 }}
                       onChange={(e) => setFarmBusqueda(e.target.value)} />
            {farmacias.length === 0 ? (
              <Alert severity="info">No tienes farmacias activas en tu panel. Agrégalas primero en «Panel Farmacia».</Alert>
            ) : farmaciasFiltradas.length === 0 ? (
              <Alert severity="info">Ninguna farmacia coincide con el filtro.</Alert>
            ) : (
              <>
                {renderGrupoFarmacia('Pendientes', farmaciasPendientes)}
                {renderGrupoFarmacia('Visitadas', farmaciasVisitadas)}
              </>
            )}
          </CardContent>
        </Card>
        </>
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
            {/* Filtro por categoría y nombre (parte superior de la lista a visitar) */}
            <Stack direction="row" spacing={1} sx={{ mb: 1 }}>
              <TextField size="small" fullWidth placeholder="Buscar médico…" value={busqueda}
                         onChange={(e) => setBusqueda(e.target.value)} />
              <TextField select size="small" label="Cat." value={catFiltro} sx={{ minWidth: 96 }}
                         onChange={(e) => setCatFiltro(e.target.value)}>
                <MenuItem value="">Todas</MenuItem>
                {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
            </Stack>
            {/* Requerimiento Mallén (Item 1): registrar un médico que NO está en la agenda de hoy. */}
            {fueraDeAgenda.length > 0 && (
              <Autocomplete
                size="small" fullWidth sx={{ mb: 1 }}
                options={fueraDeAgenda}
                value={null} blurOnSelect clearOnBlur
                onChange={(_e, m) => seleccionarFuera(m)}
                getOptionLabel={(m) => `${m.nombre_completo} · Cat ${m.categoria}${m.especialidad_nombre ? ` · ${m.especialidad_nombre}` : ''}`}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                noOptionsText="Sin coincidencias en tu panel."
                renderInput={(params) => (
                  <TextField {...params} label="Registrar médico fuera de agenda (visita no programada)"
                             placeholder="Escribe el nombre…" />
                )}
              />
            )}
            {agenda.length === 0 ? (
              <Alert severity="info">Aún no has planeado el ciclo. Programa las Vistas/Revisitas en «Planeación del Ciclo» para que aparezcan aquí.</Alert>
            ) : agendaVisible.length === 0 ? (
              <Alert severity="info">Ningún médico coincide con el filtro.</Alert>
            ) : (
              <>
                {renderGrupo('Visita / Revisita del día', delDia)}
                {renderGrupo('Visita / Revisita del ciclo', delCiclo)}
              </>
            )}
          </CardContent>
        </Card>


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
                          {v.acompanado && <span title="Acompañada por el Gerente" style={{ marginLeft: 4 }}>👥</span>}
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
              <Box sx={{ width: 30, height: 30, borderRadius: 1.5, bgcolor: '#EFEBE6', display: 'grid', placeItems: 'center' }}>
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
                        <Chip size="small" variant={v.ejecutada ? 'outlined' : 'filled'}
                              color={v.ejecutada ? (v.tipo_visita === 'R' ? 'info' : 'success') : 'error'}
                              label={v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : 'NO-Visita'} />
                        {v.acompanado && <Chip size="small" variant="outlined" color="secondary" label="Acompañada" />}
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
      </>
      )}
    </Box>
  );
}
