import { useEffect, useMemo, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, Grid,
  Menu, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress,
  Avatar, InputAdornment, Divider, Switch, FormControlLabel, IconButton, Tooltip,
} from '@mui/material';
import { Add, PersonAddAlt1, Warning, Search, FiberManualRecord, Edit, Block, Restore, HowToReg, ThumbUp, ThumbDown } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarMedicos, listarMedicosExistentes, listarEspecialidades, listarVMs, crearMedico, actualizarMedico,
  solicitarBajaMedico, reactivarMedico, listarAprobaciones, aprobarMedico, rechazarMedico,
  type MedicoVisita, type MedicoExistente, type Catalogo, type PosibleDuplicado, type MedicoCrear, type AprobacionPendiente,
} from '../../services/visita.service';

const TIPOS = ['Clínica privada', 'Hospital público', 'Hospital privado', 'Consultorio independiente'];
const FRECUENCIAS = ['Semanal', 'Quincenal', 'Mensual', 'Bimestral', 'Trimestral'];
const POTENCIAL = ['Alto', 'Medio', 'Bajo'];
const INSTITUCION = ['Pública', 'Privada'];
const vacio: MedicoCrear = {
  vm_id: 0, nombre_completo: '', especialidad_id: null, categoria: 'A',
  tipo_consultorio: '', direccion: '', telefono: '', acepta_visita: true, kol: false,
};

// Avatar de categoría (círculo) — A dorado, B azul, C gris (como el prototipo).
const CAT_AV: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#FBE7A1', fg: '#8A6D0B' },
  B: { bg: '#D6E4FF', fg: '#1E52C7' },
  C: { bg: '#E8EAF0', fg: '#5A6472' },
  D: { bg: '#F3D6D6', fg: '#B23B3B' },
};
// Paleta rotativa para las iniciales del médico.
const INICIAL_COLORS = ['#2E5BFF', '#7A5AF8', '#0F9B8E', '#E8833A', '#D6409F', '#2AA76A', '#C0392B', '#3B82C4'];

// Estado de aprobación → chip (solo si no está APROBADO).
const APROB: Record<string, { label: string; color: 'warning' | 'info' | 'default' }> = {
  PENDIENTE_ALTA: { label: 'Pendiente aprobación', color: 'warning' },
  PENDIENTE_BAJA: { label: 'Baja pendiente', color: 'warning' },
  RECHAZADO: { label: 'Rechazado', color: 'default' },
};

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
  const esAprobador = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD' || rol === 'GERENTE_DISTRITO';

  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [especialidades, setEspecialidades] = useState<Catalogo[]>([]);
  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmFiltro, setVmFiltro] = useState<number | ''>('');
  const [busqueda, setBusqueda] = useState('');
  const [catFiltro, setCatFiltro] = useState('');
  const [lineaFiltro, setLineaFiltro] = useState('');
  const [espFiltro, setEspFiltro] = useState('');
  const [estadoFiltro, setEstadoFiltro] = useState<'activos' | 'inactivos' | 'todos'>('activos');
  const [editId, setEditId] = useState<number | null>(null);
  const [pendientes, setPendientes] = useState<AprobacionPendiente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [form, setForm] = useState<MedicoCrear>(vacio);
  const [abierto, setAbierto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [duplicados, setDuplicados] = useState<PosibleDuplicado[] | null>(null);
  // "Agregar médico existente": copiar la ficha de un médico ya registrado por otro VM.
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [modoExistente, setModoExistente] = useState(false);
  const [existentes, setExistentes] = useState<MedicoExistente[]>([]);
  const [existenteSel, setExistenteSel] = useState<number | ''>('');

  const cargar = useCallback(() => {
    setCargando(true);
    listarMedicos(esVM ? undefined : (vmFiltro || undefined), estadoFiltro !== 'activos')
      .then(setMedicos).catch(() => setMedicos([])).finally(() => setCargando(false));
  }, [esVM, vmFiltro, estadoFiltro]);

  const cargarPendientes = useCallback(() => {
    if (esAprobador) listarAprobaciones().then(setPendientes).catch(() => setPendientes([]));
  }, [esAprobador]);

  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    listarEspecialidades().then(setEspecialidades).catch(() => {});
    if (!esVM) listarVMs().then(setVms).catch(() => {});
    cargarPendientes();
  }, [esVM, cargarPendientes]);

  // KPIs del panel (del ciclo actual) — solo sobre médicos activos.
  const kpis = useMemo(() => {
    const act = medicos.filter((m) => m.activo);
    const total = act.length;
    const visitados = act.filter((m) => m.estado_visita && m.estado_visita !== 'sin').length;
    const ruptura = act.filter((m) => m.ciclos_sin_visita >= 3).length;
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
      (estadoFiltro === 'todos' || (estadoFiltro === 'activos' ? m.activo : !m.activo)) &&
      (!catFiltro || m.categoria === catFiltro) &&
      (!lineaFiltro || m.linea_nombre === lineaFiltro) &&
      (!espFiltro || m.especialidad_nombre === espFiltro) &&
      (!q || m.nombre_completo.toUpperCase().includes(q)
          || (m.especialidad_nombre ?? '').toUpperCase().includes(q)
          || (m.linea_nombre ?? '').toUpperCase().includes(q)));
  }, [medicos, busqueda, catFiltro, lineaFiltro, espFiltro, estadoFiltro]);

  const abrirNuevo = () => {
    setMenuAnchor(null); setModoExistente(false); setExistenteSel('');
    setEditId(null); setForm({ ...vacio, vm_id: esVM ? 0 : (vmFiltro || 0) }); setDuplicados(null); setAbierto(true);
  };
  // "Médico existente": carga los médicos ya registrados por otros VM del país y abre el
  // formulario con un selector arriba para copiar la ficha del elegido.
  const abrirExistente = async () => {
    setMenuAnchor(null);
    const targetVm = esVM ? undefined : (vmFiltro || undefined);
    if (!esVM && !targetVm) {
      setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM) para copiar el médico a su panel.' });
      return;
    }
    try {
      const lista = await listarMedicosExistentes(targetVm);
      setExistentes(lista);
      setModoExistente(true); setExistenteSel(''); setEditId(null); setDuplicados(null);
      setForm({ ...vacio, vm_id: esVM ? 0 : (vmFiltro || 0) });
      setAbierto(true);
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudieron cargar los médicos existentes.' });
    }
  };
  // Precarga la ficha del médico existente elegido (editable antes de guardar la copia).
  const elegirExistente = (id: number) => {
    setExistenteSel(id);
    const m = existentes.find((x) => x.id === id);
    if (!m) return;
    setForm({
      vm_id: esVM ? 0 : (vmFiltro || 0),
      codigo: m.codigo, nombre_completo: m.nombre_completo, nombre: m.nombre, apellidos: m.apellidos,
      especialidad_id: m.especialidad_id, subespecialidad: m.subespecialidad, categoria: m.categoria,
      centro_trabajo: m.centro_trabajo, institucion_tipo: m.institucion_tipo, tipo_consultorio: m.tipo_consultorio,
      provincia: m.provincia, municipio: m.municipio, sector: m.sector, direccion: m.direccion,
      latitud: m.latitud, longitud: m.longitud, telefono: m.telefono, email: m.email, exequatur: m.exequatur,
      dias_consulta: m.dias_consulta, horario_consulta: m.horario_consulta, frecuencia_visita: m.frecuencia_visita,
      acepta_visita: m.acepta_visita ?? true, potencial_prescripcion: m.potencial_prescripcion, kol: m.kol ?? false,
      segmento: m.segmento, observaciones: m.observaciones,
    });
  };
  const abrirEditar = (m: MedicoVisita) => {
    setModoExistente(false); setExistenteSel('');
    setEditId(m.id); setDuplicados(null);
    setForm({
      vm_id: m.vm_id, codigo: m.codigo, nombre_completo: m.nombre_completo, nombre: m.nombre,
      apellidos: m.apellidos, especialidad_id: m.especialidad_id, subespecialidad: m.subespecialidad,
      categoria: m.categoria, centro_trabajo: m.centro_trabajo, institucion_tipo: m.institucion_tipo,
      tipo_consultorio: m.tipo_consultorio, provincia: m.provincia, municipio: m.municipio, sector: m.sector,
      direccion: m.direccion, latitud: m.latitud, longitud: m.longitud, telefono: m.telefono, email: m.email,
      exequatur: m.exequatur, dias_consulta: m.dias_consulta, horario_consulta: m.horario_consulta,
      frecuencia_visita: m.frecuencia_visita, acepta_visita: m.acepta_visita ?? true,
      potencial_prescripcion: m.potencial_prescripcion, kol: m.kol ?? false, segmento: m.segmento,
      observaciones: m.observaciones, fecha_alta: m.fecha_alta,
    });
    setAbierto(true);
  };
  const toggleActivo = async (m: MedicoVisita) => {
    try {
      if (m.activo) {
        await solicitarBajaMedico(m.id);
        setMsg({ tipo: 'success', texto: 'Solicitud de baja enviada — requiere aprobación del Gerente de Distrito (efectiva el próximo ciclo).' });
      } else {
        await reactivarMedico(m.id);
        setMsg({ tipo: 'success', texto: 'Solicitud de alta enviada — requiere aprobación del Gerente de Distrito.' });
      }
      cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo procesar la solicitud.' });
    }
  };

  const resolver = async (id: number, accion: 'aprobar' | 'rechazar') => {
    try {
      if (accion === 'aprobar') { await aprobarMedico(id); setMsg({ tipo: 'success', texto: 'Solicitud aprobada.' }); }
      else { await rechazarMedico(id); setMsg({ tipo: 'success', texto: 'Solicitud rechazada.' }); }
      cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo procesar (¿es de tu distrito?).' });
    }
  };
  const set = (k: keyof MedicoCrear, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  async function guardar(confirmar = false) {
    if (editId === null && !esVM && !form.vm_id) { setMsg({ tipo: 'error', texto: 'Selecciona el visitador (VM).' }); return; }
    setGuardando(true); setDuplicados(null);
    try {
      if (editId !== null) {
        const { confirmar_duplicado: _c, vm_id: _v, ...cambios } = form;
        await actualizarMedico(editId, cambios);
        setMsg({ tipo: 'success', texto: 'Médico actualizado.' });
      } else {
        // Al copiar un médico existente, la duplicidad es intencional → se confirma directo.
        const res = await crearMedico({ ...form, confirmar_duplicado: confirmar || modoExistente });
        if (res.duplicados && res.duplicados.length) { setDuplicados(res.duplicados); return; }
        setMsg({ tipo: 'success', texto: 'Médico registrado — pendiente de aprobación del Gerente de Distrito (contará desde el próximo ciclo).' });
      }
      setAbierto(false); cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo guardar (revisa nombre en MAYÚSCULAS, ≥2 palabras, categoría A/B/C/D).' });
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
          <TextField select size="small" label="Categoría" value={catFiltro} sx={{ minWidth: 140 }}
                     onChange={(e) => setCatFiltro(e.target.value)}>
            <MenuItem value="">Todas</MenuItem>
            {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>Categoría {c}</MenuItem>)}
          </TextField>
          <TextField select size="small" label="Estado" value={estadoFiltro} sx={{ minWidth: 130 }}
                     onChange={(e) => setEstadoFiltro(e.target.value as 'activos' | 'inactivos' | 'todos')}>
            <MenuItem value="activos">Activos</MenuItem>
            <MenuItem value="inactivos">Inactivos</MenuItem>
            <MenuItem value="todos">Todos</MenuItem>
          </TextField>
          <Button variant="contained" startIcon={<PersonAddAlt1 />}
                  onClick={(e) => setMenuAnchor(e.currentTarget)}>Agregar Médico</Button>
          <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
            <MenuItem onClick={abrirNuevo}>
              <PersonAddAlt1 fontSize="small" style={{ marginRight: 8 }} /> Médico nuevo
            </MenuItem>
            <MenuItem onClick={abrirExistente}>
              <HowToReg fontSize="small" style={{ marginRight: 8 }} /> Médico existente (copiar al panel)
            </MenuItem>
          </Menu>
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

      {/* Solicitudes pendientes de aprobación (Gerente de Distrito) */}
      {esAprobador && pendientes.length > 0 && (
        <Card variant="outlined" sx={{ mb: 2, borderColor: 'warning.main' }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <HowToReg color="warning" />
              <Typography variant="subtitle1" fontWeight={700}>Solicitudes pendientes de aprobación</Typography>
              <Chip size="small" color="warning" label={pendientes.length} />
            </Stack>
            <Stack divider={<Divider />} spacing={0}>
              {pendientes.map((p) => (
                <Stack key={p.id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                  <Chip size="small" color={p.tipo_solicitud === 'ALTA' ? 'success' : 'error'} label={p.tipo_solicitud} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={700} noWrap>{p.nombre_completo} · Cat. {p.categoria}</Typography>
                    <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                      {[p.especialidad_nombre, p.linea_nombre, `VM: ${p.vm_nombre}`].filter(Boolean).join(' · ')}
                    </Typography>
                  </Box>
                  <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />} onClick={() => resolver(p.id, 'aprobar')}>Aprobar</Button>
                  <Button size="small" variant="outlined" color="error" startIcon={<ThumbDown />} onClick={() => resolver(p.id, 'rechazar')}>Rechazar</Button>
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

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
                         sx={{ px: 2, py: 1.5, bgcolor: ruptura ? 'rgba(211,47,47,0.06)' : 'transparent', opacity: m.activo ? 1 : 0.55 }}>
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
                        {!m.activo && <Chip size="small" variant="outlined" label="Inactivo" sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />}
                        {m.estado_aprobacion && m.estado_aprobacion !== 'APROBADO' && APROB[m.estado_aprobacion] && (
                          <Chip size="small" variant="outlined" color={APROB[m.estado_aprobacion].color}
                                label={APROB[m.estado_aprobacion].label}
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                        {m.estado_aprobacion === 'APROBADO' && m.ciclo_baja_id && (
                          <Chip size="small" variant="outlined" color="info" label="Baja próx. ciclo"
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                        {[m.especialidad_nombre, m.provincia, m.municipio, m.tipo_consultorio].filter(Boolean).join(' · ') || 'Sin datos de contacto'}
                      </Typography>
                    </Box>
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ flexShrink: 0 }}>
                      <FiberManualRecord sx={{ fontSize: 11, color: est.color }} />
                      <Typography variant="caption" sx={{ color: est.color, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {est.label}
                      </Typography>
                      <Typography variant="caption" color="text.disabled" sx={{ ml: 1 }}>#{m.id}</Typography>
                      <Tooltip title="Editar médico">
                        <IconButton size="small" color="primary" onClick={() => abrirEditar(m)}><Edit fontSize="small" /></IconButton>
                      </Tooltip>
                      <Tooltip title={m.activo ? 'Solicitar baja (requiere aprobación)' : 'Solicitar alta (requiere aprobación)'}>
                        <IconButton size="small" color={m.activo ? 'error' : 'success'} onClick={() => toggleActivo(m)}>
                          {m.activo ? <Block fontSize="small" /> : <Restore fontSize="small" />}
                        </IconButton>
                      </Tooltip>
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
          </Box>
        )}
      </Card>

      {/* Alta de médico */}
      <Dialog open={abierto} onClose={() => !guardando && setAbierto(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {editId !== null
            ? <><Edit sx={{ verticalAlign: 'middle', mr: 1 }} />Editar médico</>
            : modoExistente
              ? <><HowToReg sx={{ verticalAlign: 'middle', mr: 1 }} />Copiar médico existente al panel</>
              : <><Add sx={{ verticalAlign: 'middle', mr: 1 }} />Agregar médico</>}
        </DialogTitle>
        <DialogContent dividers>
          {modoExistente && (
            <Box sx={{ mb: 1.5 }}>
              <TextField select fullWidth size="small" label="Copiar de médico existente"
                         value={existenteSel} onChange={(e) => elegirExistente(Number(e.target.value))}
                         helperText={existentes.length
                           ? 'Elige un médico ya registrado; se precargan sus datos (puedes ajustarlos antes de guardar).'
                           : 'No hay médicos de otros visitadores para copiar.'}>
                {existentes.map((m) => (
                  <MenuItem key={m.id} value={m.id}>
                    {m.nombre_completo} · Cat {m.categoria}{m.especialidad_nombre ? ` · ${m.especialidad_nombre}` : ''}{m.vm_nombre ? ` — ${m.vm_nombre}` : ''}
                  </MenuItem>
                ))}
              </TextField>
            </Box>
          )}
          {(() => {
            const seccion = (t: string) => (
              <Grid item xs={12}><Typography variant="overline" color="primary" fontWeight={700}>{t}</Typography></Grid>
            );
            return (
              <Grid container spacing={1.75} sx={{ mt: 0 }}>
                {seccion('Identificación')}
                {!esVM && (
                  <Grid item xs={12} sm={6}>
                    <TextField select fullWidth size="small" label="Visitador (VM) — Representante asignado" value={form.vm_id || ''} required
                               onChange={(e) => set('vm_id', Number(e.target.value))}>
                      {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
                    </TextField>
                  </Grid>
                )}
                <Grid item xs={12} sm={esVM ? 6 : 6}>
                  <TextField fullWidth size="small" label="Código del médico" value={form.codigo ?? ''}
                             onChange={(e) => set('codigo', e.target.value)} />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth size="small" label="Nombre completo (MAYÚSCULAS, ≥2 palabras)" value={form.nombre_completo} required
                             onChange={(e) => set('nombre_completo', e.target.value.toUpperCase())}
                             helperText="Ej: MANUEL ANTONIO PEREZ GARCIA — sin abreviaciones con punto" />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Nombre" value={form.nombre ?? ''} onChange={(e) => set('nombre', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Apellidos" value={form.apellidos ?? ''} onChange={(e) => set('apellidos', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Especialidad" value={form.especialidad_id ?? ''}
                             onChange={(e) => set('especialidad_id', e.target.value === '' ? null : Number(e.target.value))}
                             helperText={especialidades.length === 0 ? 'Catálogo vacío' : ' '}>
                    <MenuItem value="">—</MenuItem>
                    {especialidades.map((e) => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Subespecialidad" value={form.subespecialidad ?? ''} onChange={(e) => set('subespecialidad', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Categoría" value={form.categoria}
                             onChange={(e) => set('categoria', e.target.value)}>
                    {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                  </TextField>
                </Grid>

                {seccion('Ubicación / Zonificación')}
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Centro de trabajo principal" value={form.centro_trabajo ?? ''} onChange={(e) => set('centro_trabajo', e.target.value)} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField select fullWidth size="small" label="Institución" value={form.institucion_tipo ?? ''} onChange={(e) => set('institucion_tipo', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {INSTITUCION.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField select fullWidth size="small" label="Tipo de consultorio" value={form.tipo_consultorio ?? ''} onChange={(e) => set('tipo_consultorio', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {TIPOS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Provincia" value={form.provincia ?? ''} onChange={(e) => set('provincia', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Ciudad / Municipio" value={form.municipio ?? ''} onChange={(e) => set('municipio', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Sector" value={form.sector ?? ''} onChange={(e) => set('sector', e.target.value)} />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth size="small" label="Dirección" value={form.direccion ?? ''} onChange={(e) => set('direccion', e.target.value)} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField fullWidth size="small" type="number" label="Latitud (GPS)" value={form.latitud ?? ''} onChange={(e) => set('latitud', e.target.value === '' ? null : Number(e.target.value))} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField fullWidth size="small" type="number" label="Longitud (GPS)" value={form.longitud ?? ''} onChange={(e) => set('longitud', e.target.value === '' ? null : Number(e.target.value))} />
                </Grid>

                {seccion('Contacto')}
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Teléfono" value={form.telefono ?? ''} onChange={(e) => set('telefono', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Correo electrónico" value={form.email ?? ''} onChange={(e) => set('email', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Exequátur / colegiación" value={form.exequatur ?? ''} onChange={(e) => set('exequatur', e.target.value)} />
                </Grid>

                {seccion('Consulta y visita')}
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Días de consulta" value={form.dias_consulta ?? ''} placeholder="Lun, Mié, Vie" onChange={(e) => set('dias_consulta', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Horario de consulta" value={form.horario_consulta ?? ''} placeholder="8:00–12:00" onChange={(e) => set('horario_consulta', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Frecuencia de visita" value={form.frecuencia_visita ?? ''} onChange={(e) => set('frecuencia_visita', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {FRECUENCIAS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>

                {seccion('Comercial')}
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Potencial de prescripción" value={form.potencial_prescripcion ?? ''} onChange={(e) => set('potencial_prescripcion', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {POTENCIAL.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Segmento" value={form.segmento ?? ''} onChange={(e) => set('segmento', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" type="date" label="Fecha de alta" InputLabelProps={{ shrink: true }}
                             value={form.fecha_alta ?? ''} onChange={(e) => set('fecha_alta', e.target.value || null)} />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <FormControlLabel control={<Switch checked={!!form.kol} onChange={(e) => set('kol', e.target.checked)} />} label="Influenciador (KOL)" />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <FormControlLabel control={<Switch checked={form.acepta_visita !== false} onChange={(e) => set('acepta_visita', e.target.checked)} />} label="Acepta visita" />
                </Grid>

                {seccion('Estado y observaciones')}
                <Grid item xs={12}>
                  <TextField fullWidth size="small" multiline minRows={2} label="Observaciones" value={form.observaciones ?? ''} onChange={(e) => set('observaciones', e.target.value)} />
                </Grid>

                {duplicados && (
                  <Grid item xs={12}>
                    <Alert severity="warning" icon={<Warning />}>
                      <Typography variant="subtitle2" fontWeight={700}>Posible duplicidad — verificar</Typography>
                      <Typography variant="caption">Ya existe(n) médico(s) con nombre similar:</Typography>
                      {duplicados.map((d) => (
                        <Typography key={d.id} variant="body2">• {d.nombre_completo}{d.direccion ? ` — ${d.direccion}` : ''}</Typography>
                      ))}
                    </Alert>
                  </Grid>
                )}
              </Grid>
            );
          })()}
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
