import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, Grid,
  MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress,
  Avatar, InputAdornment, Divider,
} from '@mui/material';
import { Add, PersonAddAlt1, Warning, Search, FiberManualRecord } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarMedicos, listarEspecialidades, listarVMs, crearMedico,
  type MedicoVisita, type Catalogo, type PosibleDuplicado, type MedicoCrear,
} from '../../services/visita.service';

const TIPOS = ['Clínica privada', 'Hospital público', 'Hospital privado', 'Consultorio independiente'];
const vacio: MedicoCrear = { vm_id: 0, nombre_completo: '', especialidad_id: null, categoria: 'A', tipo_consultorio: '', direccion: '', telefono: '' };

// Avatar de categoría (círculo) — A dorado, B azul, C gris (como el prototipo).
const CAT_AV: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#FBE7A1', fg: '#8A6D0B' },
  B: { bg: '#D6E4FF', fg: '#1E52C7' },
  C: { bg: '#E8EAF0', fg: '#5A6472' },
};
// Paleta rotativa para las iniciales del médico.
const INICIAL_COLORS = ['#2E5BFF', '#7A5AF8', '#0F9B8E', '#E8833A', '#D6409F', '#2AA76A', '#C0392B', '#3B82C4'];

// Estado de visita del ciclo → etiqueta + color de punto.
const ESTADO: Record<string, { label: string; color: string }> = {
  vr:  { label: 'Vista + Revisita', color: '#2E7D32' },
  v:   { label: 'Vista realizada',  color: '#ED6C02' },
  sin: { label: 'Sin visitar',      color: '#D32F2F' },
};

function iniciales(nombre: string): string {
  const p = nombre.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase();
}

export default function PanelMedico() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';

  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [especialidades, setEspecialidades] = useState<Catalogo[]>([]);
  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmFiltro, setVmFiltro] = useState<number | ''>('');
  const [busqueda, setBusqueda] = useState('');
  const [catFiltro, setCatFiltro] = useState('');
  const [lineaFiltro, setLineaFiltro] = useState('');
  const [espFiltro, setEspFiltro] = useState('');
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [form, setForm] = useState<MedicoCrear>(vacio);
  const [abierto, setAbierto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [duplicados, setDuplicados] = useState<PosibleDuplicado[] | null>(null);

  const cargar = useCallback(() => {
    setCargando(true);
    listarMedicos(esVM ? undefined : (vmFiltro || undefined))
      .then(setMedicos).catch(() => setMedicos([])).finally(() => setCargando(false));
  }, [esVM, vmFiltro]);

  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    listarEspecialidades().then(setEspecialidades).catch(() => {});
    if (!esVM) listarVMs().then(setVms).catch(() => {});
  }, [esVM]);

  // KPIs del panel (del ciclo actual).
  const kpis = useMemo(() => {
    const total = medicos.length;
    const visitados = medicos.filter((m) => m.estado_visita && m.estado_visita !== 'sin').length;
    const ruptura = medicos.filter((m) => m.ciclos_sin_visita >= 3).length;
    return { total, visitados, sin: total - visitados, ruptura };
  }, [medicos]);

  // Opciones de los selectores, derivadas de los médicos presentes.
  const opcLineas = useMemo(
    () => Array.from(new Set(medicos.map((m) => m.linea_nombre).filter(Boolean) as string[])).sort(),
    [medicos]);
  const opcEspecialidades = useMemo(
    () => Array.from(new Set(medicos.map((m) => m.especialidad_nombre).filter(Boolean) as string[])).sort(),
    [medicos]);

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return medicos.filter((m) =>
      (!catFiltro || m.categoria === catFiltro) &&
      (!lineaFiltro || m.linea_nombre === lineaFiltro) &&
      (!espFiltro || m.especialidad_nombre === espFiltro) &&
      (!q || m.nombre_completo.toUpperCase().includes(q)
          || (m.especialidad_nombre ?? '').toUpperCase().includes(q)
          || (m.linea_nombre ?? '').toUpperCase().includes(q)));
  }, [medicos, busqueda, catFiltro, lineaFiltro, espFiltro]);

  const abrirNuevo = () => { setForm({ ...vacio, vm_id: esVM ? 0 : (vmFiltro || 0) }); setDuplicados(null); setAbierto(true); };

  async function guardar(confirmar = false) {
    if (!esVM && !form.vm_id) { setMsg({ tipo: 'error', texto: 'Selecciona el visitador (VM).' }); return; }
    setGuardando(true); setDuplicados(null);
    try {
      const res = await crearMedico({ ...form, confirmar_duplicado: confirmar });
      if (res.duplicados && res.duplicados.length) { setDuplicados(res.duplicados); return; }
      setMsg({ tipo: 'success', texto: 'Médico registrado.' });
      setAbierto(false); cargar();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo registrar (revisa nombre en MAYÚSCULAS, ≥2 palabras, categoría A/B/C).' });
    } finally { setGuardando(false); }
  }

  const kpiCard = (label: string, valor: number, sub: string, color: string, alerta = false) => (
    <Card variant="outlined" sx={{ borderColor: alerta ? 'error.main' : 'divider', borderWidth: alerta ? 1.5 : 1 }}>
      <CardContent sx={{ py: 1.75 }}>
        <Stack direction="row" alignItems="center" spacing={0.75}>
          {alerta && <FiberManualRecord sx={{ fontSize: 12, color: 'error.main' }} />}
          <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.4, fontWeight: 600 }}>
            {label}
          </Typography>
        </Stack>
        <Typography variant="h4" fontWeight={700} sx={{ color, lineHeight: 1.2 }}>{valor}</Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </CardContent>
    </Card>
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      {/* Cabecera */}
      <Stack direction={{ xs: 'column', md: 'row' }} justifyContent="space-between" alignItems={{ md: 'center' }} spacing={1.5} sx={{ mb: 2 }}>
        <Box>
          <Typography variant="h5" fontWeight={700}>Panel Médico</Typography>
          <Typography variant="body2" color="text.secondary">
            {filtrados.length === medicos.length
              ? `${medicos.length} médicos registrados · Ciclo actual`
              : `${filtrados.length} de ${medicos.length} médicos · filtro activo`}
          </Typography>
        </Box>
        <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center">
          {!esVM && (
            <TextField select size="small" label="Visitador (VM)" value={vmFiltro} sx={{ minWidth: 200 }}
                       onChange={(e) => setVmFiltro(e.target.value === '' ? '' : Number(e.target.value))}>
              <MenuItem value="">Todos</MenuItem>
              {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
            </TextField>
          )}
          <TextField size="small" placeholder="Buscar médico…" value={busqueda} sx={{ minWidth: 200 }}
                     onChange={(e) => setBusqueda(e.target.value)}
                     InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
          <TextField select size="small" label="Línea" value={lineaFiltro} sx={{ minWidth: 160 }}
                     onChange={(e) => setLineaFiltro(e.target.value)}>
            <MenuItem value="">Todas las líneas</MenuItem>
            {opcLineas.map((l) => <MenuItem key={l} value={l}>{l}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Especialidad" value={espFiltro} sx={{ minWidth: 180 }}
                     onChange={(e) => setEspFiltro(e.target.value)}>
            <MenuItem value="">Todas las especialidades</MenuItem>
            {opcEspecialidades.map((e) => <MenuItem key={e} value={e}>{e}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Categoría" value={catFiltro} sx={{ minWidth: 150 }}
                     onChange={(e) => setCatFiltro(e.target.value)}>
            <MenuItem value="">Todas</MenuItem>
            {['A', 'B', 'C'].map((c) => <MenuItem key={c} value={c}>Categoría {c}</MenuItem>)}
          </TextField>
          <Button variant="contained" startIcon={<PersonAddAlt1 />} onClick={abrirNuevo}>Agregar Médico</Button>
        </Stack>
      </Stack>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* KPIs */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>{kpiCard('TOTAL PANEL', kpis.total, 'médicos registrados', 'text.primary')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('VISITADOS', kpis.visitados, 'en el ciclo actual', 'success.main')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('SIN VISITAR', kpis.sin, 'requieren atención', 'error.main')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('RUPTURA SECUENCIA', kpis.ruptura, '3+ ciclos sin visitar', 'error.main', true)}</Grid>
      </Grid>

      {/* Lista de médicos (tarjetas) */}
      <Card variant="outlined">
        {cargando ? (
          <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
        ) : filtrados.length === 0 ? (
          <Alert severity="info" sx={{ m: 2 }}>
            {medicos.length === 0 ? 'No hay médicos en el panel. Agrega el primero con "Agregar Médico".' : 'Sin médicos que coincidan con el filtro.'}
          </Alert>
        ) : (
          <Box>
            {filtrados.map((m, i) => {
              const ruptura = m.ciclos_sin_visita >= 3;
              const est = ESTADO[m.estado_visita ?? 'sin'];
              const av = CAT_AV[m.categoria] ?? CAT_AV.C;
              const color = INICIAL_COLORS[m.id % INICIAL_COLORS.length];
              return (
                <Box key={m.id}>
                  {i > 0 && <Divider />}
                  <Stack direction="row" alignItems="center" spacing={1.5}
                         sx={{ px: 2, py: 1.5, bgcolor: ruptura ? 'rgba(211,47,47,0.06)' : 'transparent' }}>
                    <Avatar sx={{ bgcolor: 'transparent', color, fontWeight: 700, fontSize: 14, width: 40, height: 40, border: `2px solid ${color}22` }}>
                      {iniciales(m.nombre_completo)}
                    </Avatar>
                    <Avatar sx={{ bgcolor: av.bg, color: av.fg, fontWeight: 700, fontSize: 13, width: 26, height: 26 }}>
                      {m.categoria}
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        <Typography variant="body2" fontWeight={700} noWrap>{m.nombre_completo}</Typography>
                        {ruptura && (
                          <Chip size="small" color="error" icon={<FiberManualRecord sx={{ fontSize: '10px !important' }} />}
                                label={`${m.ciclos_sin_visita} ciclos sin visitar — Ruptura de secuencia`}
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                        {[m.especialidad_nombre, m.tipo_consultorio, m.direccion].filter(Boolean).join(' · ') || 'Sin datos de contacto'}
                      </Typography>
                    </Box>
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ flexShrink: 0 }}>
                      <FiberManualRecord sx={{ fontSize: 11, color: est.color }} />
                      <Typography variant="caption" sx={{ color: est.color, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {est.label}
                      </Typography>
                      <Typography variant="caption" color="text.disabled" sx={{ ml: 1 }}>#{m.id}</Typography>
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      {/* Alta de médico */}
      <Dialog open={abierto} onClose={() => !guardando && setAbierto(false)} maxWidth="sm" fullWidth>
        <DialogTitle><Add sx={{ verticalAlign: 'middle', mr: 1 }} />Agregar médico</DialogTitle>
        <DialogContent>
          <Stack spacing={1.75} sx={{ mt: 1 }}>
            {!esVM && (
              <TextField select label="Visitador (VM)" value={form.vm_id || ''} required
                         onChange={(e) => setForm({ ...form, vm_id: Number(e.target.value) })}>
                {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
              </TextField>
            )}
            <TextField label="Nombre completo (MAYÚSCULAS, ≥2 palabras)" value={form.nombre_completo} required
                       onChange={(e) => setForm({ ...form, nombre_completo: e.target.value.toUpperCase() })}
                       helperText="Ej: MANUEL ANTONIO PEREZ GARCIA — sin abreviaciones con punto" />
            <TextField select label="Especialidad" value={form.especialidad_id ?? ''}
                       onChange={(e) => setForm({ ...form, especialidad_id: e.target.value === '' ? null : Number(e.target.value) })}
                       helperText={especialidades.length === 0 ? 'No hay especialidades cargadas (catálogo vacío)' : ' '}>
              <MenuItem value="">—</MenuItem>
              {especialidades.map((e) => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
            </TextField>
            <Stack direction="row" spacing={1.5}>
              <TextField select label="Categoría" value={form.categoria} sx={{ minWidth: 120 }}
                         onChange={(e) => setForm({ ...form, categoria: e.target.value })}>
                {['A', 'B', 'C'].map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
              </TextField>
              <TextField select label="Tipo de consultorio" value={form.tipo_consultorio ?? ''} fullWidth
                         onChange={(e) => setForm({ ...form, tipo_consultorio: e.target.value })}>
                <MenuItem value="">—</MenuItem>
                {TIPOS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </TextField>
            </Stack>
            <TextField label="Dirección" value={form.direccion ?? ''} onChange={(e) => setForm({ ...form, direccion: e.target.value })} />
            <TextField label="Teléfono (opcional)" value={form.telefono ?? ''} onChange={(e) => setForm({ ...form, telefono: e.target.value })} />

            {duplicados && (
              <Alert severity="warning" icon={<Warning />}>
                <Typography variant="subtitle2" fontWeight={700}>Posible duplicidad — verificar</Typography>
                <Typography variant="caption">Ya existe(n) médico(s) con nombre similar:</Typography>
                {duplicados.map((d) => (
                  <Typography key={d.id} variant="body2">• {d.nombre_completo}{d.direccion ? ` — ${d.direccion}` : ''}</Typography>
                ))}
              </Alert>
            )}
          </Stack>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)} disabled={guardando}>Cancelar</Button>
          {duplicados ? (
            <Button color="warning" variant="contained" disabled={guardando} onClick={() => guardar(true)}>
              Registrar de todos modos
            </Button>
          ) : (
            <Button variant="contained" disabled={guardando || !form.nombre_completo} onClick={() => guardar(false)}>
              {guardando ? 'Guardando…' : 'Guardar'}
            </Button>
          )}
        </DialogActions>
      </Dialog>
    </Box>
  );
}
