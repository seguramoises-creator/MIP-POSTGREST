import { useEffect, useMemo, useRef, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, MenuItem, Stack, Chip, Alert, Grid,
  Divider, CircularProgress, Dialog, DialogTitle, DialogContent, DialogActions, Radio,
  FormControlLabel, IconButton, Tooltip,
} from '@mui/material';
import { RateReview, Save, CheckCircle, Lock, Visibility, Search } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import {
  cmCatalogo, cmVms, cmCrear, cmListar, cmDetalle, cmKpi, cmConsolidar, cmAcompanadasHoy,
  type CatalogoItem, type VMItem, type HojaResumen, type HojaDetalle, type CoachingKpi, type ItemCalif,
  type AcompanadasHoy,
} from '../../services/coachingMore.service';

const ESCALA = [
  { v: 1, l: 'D', label: 'Desarrollar', color: '#e53935' },
  { v: 2, l: 'P', label: 'Perfeccionar', color: '#f59e0b' },
  { v: 3, l: 'A', label: 'Adecuado', color: '#0057A8' },
  { v: 4, l: 'E', label: 'Excelente', color: '#00A86B' },
];
const colorProm = (a: number) => (a >= 3.5 ? '#00A86B' : a >= 2.5 ? '#0057A8' : a >= 1.5 ? '#f59e0b' : '#e53935');
const r2 = (x: number) => Math.round(x * 100) / 100;

function errMsg(e: unknown, fb: string): string {
  const d = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof d === 'string' ? d : fb;
}

// ── Canvas de firma ───────────────────────────────────────────────────────────
function FirmaCanvas({ valor, onConfirmar, onLimpiar }:
  { valor: string; onConfirmar: (dataUrl: string) => void; onLimpiar: () => void }) {
  const ref = useRef<HTMLCanvasElement>(null);
  const dib = useRef(false);
  const [trazo, setTrazo] = useState(false);
  const confirmada = !!valor;

  const resize = useCallback(() => {
    const c = ref.current; if (!c) return;
    const w = c.parentElement?.getBoundingClientRect().width ?? 300;
    c.width = w; c.height = 170;
    const ctx = c.getContext('2d')!; ctx.strokeStyle = '#003f7a'; ctx.lineWidth = 2.4; ctx.lineCap = 'round';
  }, []);
  useEffect(() => { resize(); window.addEventListener('resize', resize); return () => window.removeEventListener('resize', resize); }, [resize]);

  const pos = (e: React.MouseEvent | React.TouchEvent) => {
    const c = ref.current!; const r = c.getBoundingClientRect();
    const p = 'touches' in e ? e.touches[0] : (e as React.MouseEvent);
    return { x: p.clientX - r.left, y: p.clientY - r.top };
  };
  const start = (e: React.MouseEvent | React.TouchEvent) => { if (confirmada) return; dib.current = true; const ctx = ref.current!.getContext('2d')!; const p = pos(e); ctx.beginPath(); ctx.moveTo(p.x, p.y); };
  const move = (e: React.MouseEvent | React.TouchEvent) => { if (!dib.current || confirmada) return; const ctx = ref.current!.getContext('2d')!; const p = pos(e); ctx.lineTo(p.x, p.y); ctx.stroke(); setTrazo(true); e.preventDefault(); };
  const stop = () => { dib.current = false; };
  const limpiar = () => { const c = ref.current!; c.getContext('2d')!.clearRect(0, 0, c.width, c.height); setTrazo(false); onLimpiar(); };
  const confirmar = () => { if (!trazo) return; onConfirmar(ref.current!.toDataURL('image/png')); };

  return (
    <Box>
      <Box sx={{ border: confirmada ? '2px solid #00A86B' : '2px dashed #d1d5db', borderRadius: 2, bgcolor: '#fdfdfd', position: 'relative', touchAction: 'none' }}>
        <canvas ref={ref} style={{ display: 'block', width: '100%', height: 170, cursor: confirmada ? 'default' : 'crosshair' }}
          onMouseDown={start} onMouseMove={move} onMouseUp={stop} onMouseLeave={stop}
          onTouchStart={start} onTouchMove={move} onTouchEnd={stop} />
        {!trazo && !confirmada && (
          <Typography sx={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', color: '#d1d5db', fontSize: 13, pointerEvents: 'none' }}>
            firme aquí con el dedo o el mouse
          </Typography>
        )}
      </Box>
      <Stack direction="row" spacing={1} alignItems="center" sx={{ mt: 1 }}>
        <Typography variant="body2" fontWeight={700} sx={{ color: confirmada ? '#00A86B' : '#f59e0b' }}>
          {confirmada ? '✅ Firma confirmada' : '✍️ Firma pendiente'}
        </Typography>
        <Box sx={{ flex: 1 }} />
        <Button size="small" onClick={limpiar}>Limpiar</Button>
        <Button size="small" variant="outlined" disabled={confirmada || !trazo} onClick={confirmar}>Confirmar firma</Button>
      </Stack>
    </Box>
  );
}

// Chip de calificación D/P/A/E (solo lectura) — mismo código de color que el formulario.
function CalifChip({ cal }: { cal: number }) {
  const e = ESCALA.find((x) => x.v === cal);
  if (!e) return <Chip size="small" label="—" variant="outlined" />;
  return <Chip size="small" label={`${e.v} · ${e.l}`} sx={{ bgcolor: e.color, color: '#fff', fontWeight: 800 }} />;
}

// ── Detalle solo-lectura (reusado por GD y RM) ──────────────────────────────────
// Muestra la hoja COMPLETA tal como se llenó (secciones con cada ítem y su D/P/A/E, plan,
// firma), en solo lectura. Una hoja guardada NUNCA se modifica ni se corrige.
function DetalleHoja({ id, onClose }: { id: number; onClose: () => void }) {
  const [d, setD] = useState<HojaDetalle | null>(null);
  useEffect(() => { cmDetalle(id).then(setD).catch(() => setD(null)); }, [id]);
  return (
    <Dialog open onClose={onClose} maxWidth="md" fullWidth>
      <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
        <Lock fontSize="small" sx={{ color: '#00A86B' }} />
        Hoja de Coaching {d ? `— ${d.fecha_coaching}` : ''}
        <Chip size="small" label="Solo lectura" variant="outlined" sx={{ ml: 'auto' }} />
      </DialogTitle>
      <DialogContent dividers>
        {!d ? <Box sx={{ textAlign: 'center', py: 3 }}><CircularProgress /></Box> : (
          <Stack spacing={1.5}>
            {/* Encabezado */}
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Row k="Representante" v={d.rm_nombre ?? '—'} />
              <Row k="Gerente de Distrito" v={d.gd_nombre ?? '—'} />
              <Row k="Médicos vistos ese día" v={String(d.medicos_vistos)} />
            </CardContent></Card>

            {/* Escala */}
            <Stack direction="row" spacing={0.75} flexWrap="wrap" useFlexGap>
              {ESCALA.map((e) => (
                <Chip key={e.v} size="small" label={`${e.v} · ${e.l} — ${e.label}`}
                      sx={{ bgcolor: e.color, color: '#fff', fontWeight: 700 }} />
              ))}
            </Stack>

            {/* Secciones con cada ítem y su calificación */}
            {d.secciones.map((s) => (
              <Card key={s.seccion} variant="outlined"><CardContent sx={{ py: 1.5 }}>
                <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 0.5 }}>
                  <Typography variant="subtitle1" fontWeight={700}>{s.seccion}</Typography>
                  <Chip size="small" label={s.promedio != null ? s.promedio.toFixed(2) : '—'}
                        sx={{ bgcolor: s.promedio != null ? colorProm(s.promedio) : '#f3f4f6',
                              color: s.promedio != null ? '#fff' : '#6b7280', fontWeight: 800 }} />
                </Stack>
                {s.items.map((it, i) => (
                  <Stack key={i} direction="row" alignItems="center" spacing={1}
                         sx={{ py: 0.6, borderBottom: '1px solid #f3f4f6' }}>
                    <Typography variant="body2" sx={{ flex: 1 }}>{it.texto}</Typography>
                    <CalifChip cal={it.calificacion} />
                  </Stack>
                ))}
              </CardContent></Card>
            ))}

            <Card variant="outlined" sx={{ bgcolor: '#F7F5F2' }}><CardContent sx={{ py: 1.5 }}>
              <Row k="Evaluación promedio general" v={d.evaluacion_promedio.toFixed(2)} bold />
            </CardContent></Card>

            {/* Plan de desarrollo y acción */}
            <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
              <Row k="Fortalezas" v={d.fortalezas} />
              <Row k="Áreas a perfeccionar" v={d.areas_perfeccionar} />
              <Row k="¿Qué harás?" v={d.plan_que_haras} />
              <Row k="¿Cómo lo harás?" v={d.plan_como_haras} />
              <Row k="¿Cómo te darás cuenta?" v={d.plan_como_veras} />
              <Row k="Fecha de seguimiento" v={d.plan_fecha_seguimiento} />
              <Row k="Acuerdo del representante" v={d.rm_acuerdo === 'de_acuerdo' ? 'De acuerdo' : 'No de acuerdo'} />
              {d.rm_justificacion_desacuerdo && (
                <Box sx={{ bgcolor: '#fdecea', borderLeft: '4px solid #e53935', borderRadius: 1, p: 1.2, mt: 0.5 }}>
                  <Typography variant="body2"><b>Justificación:</b> {d.rm_justificacion_desacuerdo}</Typography>
                </Box>
              )}
            </CardContent></Card>

            {/* Firma */}
            <Box>
              <Typography variant="caption" color="text.secondary">Firma del representante:</Typography>
              {d.rm_firma_imagen
                ? <Box component="img" src={d.rm_firma_imagen} alt="firma"
                       sx={{ display: 'block', maxWidth: 320, border: '1px solid #e5e7eb', borderRadius: 1, bgcolor: '#fff', mt: 0.5 }} />
                : <Typography variant="body2" color="text.secondary">— sin firma —</Typography>}
            </Box>
          </Stack>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
function Row({ k, v, bold }: { k: string; v: string; bold?: boolean }) {
  return (
    <Stack direction="row" justifyContent="space-between" sx={{ py: 0.5, borderBottom: '1px solid #f3f4f6' }}>
      <Typography variant="body2" color="text.secondary">{k}</Typography>
      <Typography variant="body2" fontWeight={bold ? 800 : 700} sx={{ color: bold ? '#0057A8' : undefined, textAlign: 'right', maxWidth: '60%' }}>{v}</Typography>
    </Stack>
  );
}

// ── Página ──────────────────────────────────────────────────────────────────
export default function CoachingMore() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const puedeConsolidar = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD';
  const cicloId = useCicloStore((s) => s.cicloId);
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloAbiertoId = useCicloStore((s) => s.cicloAbiertoId);
  const [consolidando, setConsolidando] = useState<string | null>(null);

  const [catalogo, setCatalogo] = useState<CatalogoItem[]>([]);
  const [vms, setVms] = useState<VMItem[]>([]);
  const [hojas, setHojas] = useState<HojaResumen[]>([]);
  const [kpi, setKpi] = useState<CoachingKpi | null>(null);
  const [verId, setVerId] = useState<number | null>(null);
  const [cargando, setCargando] = useState(true);

  // Estado del formulario (solo GD)
  const [rmId, setRmId] = useState<number | ''>('');
  const [medicos, setMedicos] = useState('');
  const [acompHoy, setAcompHoy] = useState<AcompanadasHoy | null>(null);
  const [ratings, setRatings] = useState<Record<number, number>>({});
  const [fortalezas, setFortalezas] = useState('');
  const [areas, setAreas] = useState('');
  const [planQue, setPlanQue] = useState('');
  const [planComo, setPlanComo] = useState('');
  const [planVeras, setPlanVeras] = useState('');
  const [fechaSeg, setFechaSeg] = useState('');
  const [acuerdo, setAcuerdo] = useState<'de_acuerdo' | 'no_de_acuerdo' | ''>('');
  const [justif, setJustif] = useState('');
  const [firma, setFirma] = useState('');
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const [okDialog, setOkDialog] = useState(false);

  // Al elegir un RM: trae la suma de visitas ACOMPAÑADAS de hoy. "Médicos vistos ese día" pasa
  // a ser esa suma (solo lectura); la hoja se habilita si suma >= el mínimo del RM.
  useEffect(() => {
    if (!rmId) { setAcompHoy(null); setMedicos(''); return; }
    cmAcompanadasHoy(Number(rmId))
      .then((r) => { setAcompHoy(r); setMedicos(String(r.acompanadas)); })
      .catch(() => { setAcompHoy(null); });
  }, [rmId]);
  const hojaHabilitada = !!acompHoy?.habilitado;

  const recargar = useCallback(() => {
    cmListar().then(setHojas).catch(() => setHojas([]));
    if (!esVM) cmKpi(cicloId || undefined, paisCodigo).then(setKpi).catch(() => setKpi(null));
  }, [esVM, cicloId, paisCodigo]);

  useEffect(() => {
    setCargando(true);
    Promise.all([cmCatalogo().catch(() => []), esVM ? Promise.resolve([]) : cmVms(paisCodigo).catch(() => [])])
      .then(([cat, v]) => { setCatalogo(cat); setVms(v as VMItem[]); })
      .finally(() => setCargando(false));
    recargar();
  }, [esVM, recargar, paisCodigo]);

  const secciones = useMemo(() => {
    const map = new Map<string, CatalogoItem[]>();
    [...catalogo].sort((a, b) => a.orden_seccion - b.orden_seccion || a.orden_item - b.orden_item)
      .forEach((it) => { if (!map.has(it.seccion)) map.set(it.seccion, []); map.get(it.seccion)!.push(it); });
    return Array.from(map.entries());
  }, [catalogo]);

  const secAvg = (items: CatalogoItem[]) => {
    const vals = items.map((i) => ratings[i.id]).filter((v) => v != null) as number[];
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  };
  const todosCalificados = catalogo.length > 0 && catalogo.every((i) => ratings[i.id] != null);
  const general = useMemo(() => {
    if (!todosCalificados) return null;
    const avgs = secciones.map(([, items]) => secAvg(items)!).filter((v) => v != null) as number[];
    return avgs.length ? r2(avgs.reduce((a, b) => a + b, 0) / avgs.length) : null;
  }, [ratings, secciones, todosCalificados]);

  const resetForm = () => {
    setRmId(''); setMedicos(''); setRatings({}); setFortalezas(''); setAreas('');
    setPlanQue(''); setPlanComo(''); setPlanVeras(''); setFechaSeg('');
    setAcuerdo(''); setJustif(''); setFirma('');
  };


  const guardar = async () => {
    setMsg(null);
    if (!rmId) { setMsg({ tipo: 'error', texto: 'Selecciona el representante (RM).' }); return; }
    const items: ItemCalif[] = catalogo.filter((i) => ratings[i.id] != null)
      .map((i) => ({ item_catalogo_id: i.id, seccion: i.seccion, item_texto: i.texto, calificacion: ratings[i.id] }));
    const payload = {
      rm_id: Number(rmId), medicos_vistos: Number(medicos || 0), items,
      fortalezas, areas_perfeccionar: areas,
      plan_que_haras: planQue, plan_como_haras: planComo, plan_como_veras: planVeras,
      plan_fecha_seguimiento: fechaSeg, rm_acuerdo: acuerdo,
      rm_justificacion_desacuerdo: acuerdo === 'no_de_acuerdo' ? justif : null,
      rm_firma_imagen: firma,
    };
    setGuardando(true);
    try {
      await cmCrear(payload);
      setOkDialog(true); resetForm(); recargar();
    } catch (e) {
      setMsg({ tipo: 'error', texto: errMsg(e, 'No se pudo guardar la hoja.') });
    } finally { setGuardando(false); }
  };

  const consolidar = async (destino: 'coaching' | 'indicador') => {
    if (!cicloAbiertoId || !paisCodigo) { setMsg({ tipo: 'error', texto: 'Falta ciclo abierto o país en el contexto.' }); return; }
    setConsolidando(destino); setMsg(null);
    try {
      const r = await cmConsolidar(destino, cicloAbiertoId, paisCodigo);
      setMsg({ tipo: 'success', texto: `Consolidado a ${r.destino}: ${r.rms_consolidados} RM(s). El Score del ciclo se recalculó.` });
      recargar();
    } catch (e) {
      setMsg({ tipo: 'error', texto: errMsg(e, 'No se pudo consolidar.') });
    } finally { setConsolidando(null); }
  };

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  // ── Vista RM: solo lectura ──
  if (esVM) {
    return (
      <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <RateReview color="primary" /><Typography variant="h5" fontWeight={700}>Mis Hojas de Coaching</Typography>
        </Stack>
        <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
          Registradas por tu Gerente de Distrito — solo lectura, nunca editables.
        </Typography>
        <VistaRM hojas={hojas} onVer={setVerId} />
        {verId != null && <DetalleHoja id={verId} onClose={() => setVerId(null)} />}
      </Box>
    );
  }

  // ── Vista GD/gerencia ──
  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
        <RateReview color="primary" /><Typography variant="h5" fontWeight={700}>Coaching (Modelo MORE)</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Hoja de acompañamiento GD→RM. Se completa al final del día de campo y queda inmutable al guardar.
      </Typography>

      {kpi && (
        <Grid container spacing={2} sx={{ mb: 2 }}>
          <KpiCard label="Hojas completadas (ciclo)" valor={String(kpi.hojas_completadas)} />
          <KpiCard label="RMs con coaching" valor={`${kpi.rms_con_coaching} / ${kpi.total_rms}`} />
          <KpiCard label="Avance de la meta" valor={`${kpi.pct_avance}%`} color="#00A86B" />
        </Grid>
      )}

      {puedeConsolidar && (
        <Card variant="outlined" sx={{ mb: 2, bgcolor: '#F7F5F2', borderColor: '#D8D2CB' }}><CardContent sx={{ py: 1.5 }}>
          <Typography variant="subtitle2" fontWeight={700}>Consolidar al KPI Coaching del Score</Typography>
          <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
            Vuelca los promedios MORE del <b>ciclo abierto</b> hacia el flujo que alimenta el Score Integral
            (idempotente; recalcula el ciclo). Úsalo cuando el cliente decida dejar su Excel de coaching.
          </Typography>
          <Stack direction="row" spacing={1.5} flexWrap="wrap">
            <Button size="small" variant="outlined" disabled={!!consolidando} onClick={() => consolidar('coaching')}>
              {consolidando === 'coaching' ? 'Consolidando…' : 'Consolidar a Coaching (FACT_Coaching)'}
            </Button>
            <Button size="small" variant="outlined" disabled={!!consolidando} onClick={() => consolidar('indicador')}>
              {consolidando === 'indicador' ? 'Consolidando…' : 'Consolidar a EVAL_COACHING'}
            </Button>
          </Stack>
        </CardContent></Card>
      )}

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}


      {/* Encabezado */}
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>Encabezado del Coaching</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={4}>
            <TextField fullWidth size="small" label="Fecha del coaching" value={new Date().toISOString().slice(0, 10)} disabled
                       helperText="La fija el servidor — no editable" />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField select fullWidth size="small" label="Representante (RM)" value={rmId}
                       onChange={(e) => setRmId(e.target.value === '' ? '' : Number(e.target.value))}>
              <MenuItem value="">Seleccionar…</MenuItem>
              {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
            </TextField>
          </Grid>
          <Grid item xs={12} sm={4}>
            {/* Leyenda de solo lectura: suma de visitas ACOMPAÑADAS de hoy (no editable). */}
            <Box sx={{ border: '1px solid #E0DAD3', borderRadius: 1, px: 1.5, py: 0.75, minHeight: 56 }}>
              <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                Médicos vistos ese día (visitas acompañadas)
              </Typography>
              <Typography variant="h6" fontWeight={800}
                          color={acompHoy ? (hojaHabilitada ? 'success.main' : 'error.main') : 'text.disabled'}>
                {acompHoy ? acompHoy.acompanadas : (rmId ? '…' : '—')}
                {acompHoy && (
                  <Typography component="span" variant="caption" color="text.secondary" sx={{ ml: 0.5 }}>
                    / mínimo {acompHoy.minimo}
                  </Typography>
                )}
              </Typography>
            </Box>
          </Grid>
        </Grid>
      </CardContent></Card>

      {/* Habilitación de la hoja según el mínimo de visitas acompañadas del RM */}
      {rmId !== '' && acompHoy && !hojaHabilitada && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          Para generar la hoja de Coaching se requieren al menos <b>{acompHoy.minimo}</b> visitas
          acompañadas hoy. Este representante tiene <b>{acompHoy.acompanadas}</b> — la hoja se
          activará al alcanzar el mínimo.
        </Alert>
      )}
      {rmId !== '' && hojaHabilitada && (
        <Alert severity="success" sx={{ mb: 2 }}>
          Hoja habilitada — {acompHoy?.acompanadas} visitas acompañadas hoy (mínimo {acompHoy?.minimo}).
        </Alert>
      )}

      {/* Escala */}
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
        <Stack direction="row" spacing={1} flexWrap="wrap" useFlexGap>
          {ESCALA.map((e) => (
            <Chip key={e.v} label={`${e.v} · ${e.l} — ${e.label}`} sx={{ bgcolor: e.color, color: '#fff', fontWeight: 700 }} />
          ))}
        </Stack>
      </CardContent></Card>

      {/* Secciones MORE */}
      {secciones.map(([sec, items]) => {
        const avg = secAvg(items);
        return (
          <Card variant="outlined" sx={{ mb: 2 }} key={sec}><CardContent>
            <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ mb: 1 }}>
              <Typography variant="subtitle1" fontWeight={700}>{sec}</Typography>
              <Chip size="small" label={avg != null ? avg.toFixed(2) : '— sin calificar —'}
                    sx={{ bgcolor: avg != null ? colorProm(avg) : '#f3f4f6', color: avg != null ? '#fff' : '#6b7280', fontWeight: 800 }} />
            </Stack>
            {items.map((it) => (
              <Stack key={it.id} direction="row" alignItems="center" spacing={1} sx={{ py: 0.75, borderBottom: '1px solid #f3f4f6' }}>
                <Typography variant="body2" sx={{ flex: 1 }}>{it.texto}</Typography>
                <Stack direction="row" spacing={0.5}>
                  {ESCALA.map((e) => {
                    const sel = ratings[it.id] === e.v;
                    return (
                      <Button key={e.v} size="small" onClick={() => setRatings((r) => ({ ...r, [it.id]: e.v }))}
                              sx={{ minWidth: 36, px: 0, fontWeight: 800,
                                    bgcolor: sel ? e.color : '#fff', color: sel ? '#fff' : '#9ca3af',
                                    border: `1.5px solid ${sel ? e.color : '#e5e7eb'}`, '&:hover': { borderColor: e.color } }}>
                        {e.l}
                      </Button>
                    );
                  })}
                </Stack>
              </Stack>
            ))}
          </CardContent></Card>
        );
      })}

      {/* Promedio general */}
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
        <Stack direction="row" spacing={3} alignItems="center">
          <Box sx={{ width: 110, height: 110, borderRadius: '50%', border: `7px solid ${general != null ? colorProm(general) : '#d1d5db'}`, display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center' }}>
            <Typography variant="h4" fontWeight={800} color="primary.main">{general != null ? general.toFixed(2) : '—'}</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ maxWidth: 420 }}>
            Evaluación promedio general = promedio simple de los 7 promedios de sección.
            {general == null && ' Faltan ítems por calificar.'}
          </Typography>
        </Stack>
      </CardContent></Card>

      {/* Plan de desarrollo */}
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>Plan de Desarrollo</Typography>
        <Grid container spacing={2}>
          <Grid item xs={12} sm={6}><TextField fullWidth size="small" multiline minRows={2} label="Fortalezas *" value={fortalezas} onChange={(e) => setFortalezas(e.target.value)} /></Grid>
          <Grid item xs={12} sm={6}><TextField fullWidth size="small" multiline minRows={2} label="Áreas a perfeccionar *" value={areas} onChange={(e) => setAreas(e.target.value)} /></Grid>
        </Grid>
      </CardContent></Card>

      {/* Plan de acción */}
      <Card variant="outlined" sx={{ mb: 2, borderColor: 'primary.main' }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>Plan de Acción — obligatorio</Typography>
        <Stack spacing={2}>
          <TextField fullWidth size="small" multiline label="¿Qué harás? *" value={planQue} onChange={(e) => setPlanQue(e.target.value)} />
          <TextField fullWidth size="small" multiline label="¿Cómo lo harás? *" value={planComo} onChange={(e) => setPlanComo(e.target.value)} />
          <TextField fullWidth size="small" multiline label="¿Cómo te darás cuenta que estás perfeccionando la habilidad? *" value={planVeras} onChange={(e) => setPlanVeras(e.target.value)} />
          <TextField size="small" type="date" label="Fecha de seguimiento *" InputLabelProps={{ shrink: true }} sx={{ maxWidth: 240 }} value={fechaSeg} onChange={(e) => setFechaSeg(e.target.value)} />
        </Stack>
      </CardContent></Card>

      {/* Acuerdo + firma */}
      <Card variant="outlined" sx={{ mb: 2 }}><CardContent>
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Acuerdo del Representante</Typography>
        <Stack spacing={1}>
          <FormControlLabel control={<Radio checked={acuerdo === 'de_acuerdo'} onChange={() => setAcuerdo('de_acuerdo')} />} label="Estoy de acuerdo con esta evaluación" />
          <FormControlLabel control={<Radio checked={acuerdo === 'no_de_acuerdo'} onChange={() => setAcuerdo('no_de_acuerdo')} />} label="No estoy de acuerdo con esta evaluación" />
          {acuerdo === 'no_de_acuerdo' && (
            <TextField fullWidth size="small" multiline label="Justificación del desacuerdo *" value={justif} onChange={(e) => setJustif(e.target.value)}
                       helperText="Obligatorio si eliges No estoy de acuerdo." />
          )}
        </Stack>
        <Divider sx={{ my: 2 }} />
        <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Firma del Representante *</Typography>
        <FirmaCanvas valor={firma} onConfirmar={setFirma} onLimpiar={() => setFirma('')} />
      </CardContent></Card>

      <Button fullWidth size="large" variant="contained" color="primary"
              startIcon={<Save />} disabled={guardando || !rmId || !hojaHabilitada} onClick={guardar} sx={{ py: 1.5 }}>
        {guardando ? 'Guardando…' : 'Guardar Hoja de Coaching (queda inmutable — no se puede modificar)'}
      </Button>

      {/* Historial del equipo */}
      <Typography variant="subtitle1" fontWeight={700} sx={{ mt: 4, mb: 1 }}>Historial de mi equipo</Typography>
      <ListaHojas hojas={hojas} onVer={setVerId} filtrable />

      {verId != null && <DetalleHoja id={verId} onClose={() => setVerId(null)} />}

      <Dialog open={okDialog} onClose={() => setOkDialog(false)} maxWidth="xs" fullWidth>
        <DialogTitle sx={{ display: 'flex', alignItems: 'center', gap: 1 }}><CheckCircle color="success" /> Hoja guardada</DialogTitle>
        <DialogContent><Typography variant="body2">Se envió una copia en PDF al correo corporativo del representante y el KPI Coaching se actualizó. Esta hoja ya no podrá modificarse por ningún rol.</Typography></DialogContent>
        <DialogActions><Button variant="contained" onClick={() => setOkDialog(false)}>Entendido</Button></DialogActions>
      </Dialog>
    </Box>
  );
}

// ── Vista del representante: sus hojas por ciclo + promedios ──────────────────
const promedioDe = (hs: HojaResumen[]) =>
  hs.length ? r2(hs.reduce((a, h) => a + h.evaluacion_promedio, 0) / hs.length) : null;

function VistaRM({ hojas, onVer }: { hojas: HojaResumen[]; onVer: (id: number) => void }) {
  const cicloIdCtx = useCicloStore((s) => s.cicloId);
  // Una hoja de corrección enmienda a su original (que queda inmutable, nunca se edita):
  // para los promedios cuenta solo la vigente — igual que el KPI del GD, así los dos
  // números del sistema coinciden.
  const vigentes = useMemo(() => hojas.filter((h) => !h.tiene_correccion), [hojas]);

  const ciclos = useMemo(() => {
    const m = new Map<number, string>();
    vigentes.forEach((h) => {
      if (h.ciclo_id != null) m.set(h.ciclo_id, h.ciclo_nombre ?? `Ciclo ${h.ciclo_id}`);
    });
    return [...m.entries()].sort((a, b) => b[1].localeCompare(a[1]));  // más reciente primero
  }, [vigentes]);

  // 'auto' = el ciclo del contexto global si tiene hojas; si no, el más reciente con hojas.
  const [filtro, setFiltro] = useState<number | 'todos' | 'auto'>('auto');
  const sel: number | 'todos' = filtro !== 'auto' ? filtro
    : (cicloIdCtx && ciclos.some(([id]) => id === cicloIdCtx) ? cicloIdCtx : (ciclos[0]?.[0] ?? 'todos'));

  const delCiclo = sel === 'todos' ? vigentes : vigentes.filter((h) => h.ciclo_id === sel);
  const promCiclo = promedioDe(delCiclo);
  const promAcum = promedioDe(vigentes);
  const nombreSel = sel === 'todos' ? 'todos los ciclos' : (ciclos.find(([id]) => id === sel)?.[1] ?? '—');

  if (!vigentes.length) return <Alert severity="info">No hay hojas de coaching todavía.</Alert>;

  return (
    <>
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={12} sm={4}>
          <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              PROMEDIO · {nombreSel.toUpperCase()}
            </Typography>
            <Typography variant="h4" fontWeight={800}
                        sx={{ color: promCiclo != null ? colorProm(promCiclo) : 'text.disabled' }}>
              {promCiclo != null ? promCiclo.toFixed(2) : '—'}
              <Typography component="span" variant="body2" color="text.secondary"> / 4.00</Typography>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {delCiclo.length} {delCiclo.length === 1 ? 'hoja' : 'hojas'}
            </Typography>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
            <Typography variant="caption" color="text.secondary" fontWeight={600}>
              ACUMULADO A LA FECHA
            </Typography>
            <Typography variant="h4" fontWeight={800}
                        sx={{ color: promAcum != null ? colorProm(promAcum) : 'text.disabled' }}>
              {promAcum != null ? promAcum.toFixed(2) : '—'}
              <Typography component="span" variant="body2" color="text.secondary"> / 4.00</Typography>
            </Typography>
            <Typography variant="caption" color="text.secondary">
              {vigentes.length} {vigentes.length === 1 ? 'hoja' : 'hojas'} · {ciclos.length}{' '}
              {ciclos.length === 1 ? 'ciclo' : 'ciclos'}
            </Typography>
          </CardContent></Card>
        </Grid>
        <Grid item xs={12} sm={4}>
          <TextField select fullWidth size="small" label="Ciclo" value={sel}
                     onChange={(e) => setFiltro(e.target.value === 'todos' ? 'todos' : Number(e.target.value))}
                     sx={{ mt: 0.5 }}>
            <MenuItem value="todos">Todos los ciclos</MenuItem>
            {ciclos.map(([id, nombre]) => <MenuItem key={id} value={id}>{nombre}</MenuItem>)}
          </TextField>
          <Stack direction="row" spacing={0.5} sx={{ mt: 1 }} flexWrap="wrap" useFlexGap>
            {ESCALA.map((e) => (
              <Chip key={e.v} size="small" label={`${e.v} ${e.l}`}
                    sx={{ bgcolor: e.color, color: '#fff', fontWeight: 700, height: 20, fontSize: 11 }} />
            ))}
          </Stack>
        </Grid>
      </Grid>
      <ListaHojas hojas={delCiclo} onVer={onVer} filtrable />
    </>
  );
}

function KpiCard({ label, valor, color }: { label: string; valor: string; color?: string }) {
  return (
    <Grid item xs={12} sm={4}>
      <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
        <Typography variant="caption" color="text.secondary" fontWeight={600}>{label}</Typography>
        <Typography variant="h5" fontWeight={800} sx={{ color: color ?? 'primary.main' }}>{valor}</Typography>
      </CardContent></Card>
    </Grid>
  );
}

// Lista de hojas SOLO-LECTURA. No hay corrección/edición: una hoja guardada es inmutable.
// `filtrable` añade un buscador por nombre del representante (para el GD, sobre su equipo).
function ListaHojas({ hojas, onVer, filtrable }:
  { hojas: HojaResumen[]; onVer: (id: number) => void; filtrable?: boolean }) {
  const [q, setQ] = useState('');
  const visibles = useMemo(() => {
    const t = q.trim().toLowerCase();
    return t ? hojas.filter((h) => (h.rm_nombre ?? '').toLowerCase().includes(t)) : hojas;
  }, [hojas, q]);

  if (!hojas.length) return <Alert severity="info">No hay hojas de coaching todavía.</Alert>;
  return (
    <Stack spacing={1}>
      {filtrable && (
        <TextField size="small" fullWidth placeholder="Buscar representante por nombre…"
                   value={q} onChange={(e) => setQ(e.target.value)}
                   InputProps={{ startAdornment: <Search fontSize="small" sx={{ color: 'text.disabled', mr: 1 }} /> }} />
      )}
      {!visibles.length && <Alert severity="info">Ningún representante coincide con «{q}».</Alert>}
      {visibles.map((h) => (
        <Card key={h.id} variant="outlined"><CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
          <Stack direction="row" alignItems="center" spacing={1.5} flexWrap="wrap">
            <Lock fontSize="small" sx={{ color: '#00A86B' }} />
            <Box sx={{ flex: 1, minWidth: 0 }}>
              <Typography variant="body2" fontWeight={700} noWrap>
                {h.fecha_coaching} · {h.rm_nombre} {h.gd_nombre ? `· ${h.gd_nombre}` : ''}
              </Typography>
              <Typography variant="caption" color="text.secondary">Promedio {h.evaluacion_promedio.toFixed(2)}</Typography>
            </Box>
            <Chip size="small" label={h.rm_acuerdo === 'de_acuerdo' ? 'De acuerdo' : 'No de acuerdo'}
                  color={h.rm_acuerdo === 'de_acuerdo' ? 'success' : 'error'} variant="outlined" />
            <Tooltip title="Ver hoja (solo lectura)">
              <IconButton size="small" color="primary" onClick={() => onVer(h.id)}><Visibility fontSize="small" /></IconButton>
            </Tooltip>
          </Stack>
        </CardContent></Card>
      ))}
    </Stack>
  );
}
