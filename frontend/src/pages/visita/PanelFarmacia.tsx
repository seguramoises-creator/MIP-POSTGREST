/**
 * PanelFarmacia.tsx — Panel de Farmacias del VM (móvil) + aprobación inline (GD/ADMIN).
 * Espejo de PanelMedico.tsx: botón "AGREGAR FARMACIA" con menú de 2 opciones (Farmacia
 * nueva / Farmacia existente — copiar al panel) y la bandeja de aprobación EMBEBIDA en
 * esta misma pantalla (ya no existe una pantalla separada "Aprobación Farmacias").
 */
import { useCallback, useEffect, useMemo, useState, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, CircularProgress, Avatar, Divider, Switch, FormControlLabel, Tooltip,
  Menu, Dialog, DialogTitle, DialogContent, DialogActions, Grid, InputAdornment,
} from '@mui/material';
import {
  LocalPharmacy, Search, Add, FiberManualRecord, HowToReg, Badge, SupervisorAccount, Layers,
  ThumbUp, ThumbDown, Edit, Warning,
} from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import { listarVMs, miGerente, type Catalogo, type MiGerente } from '../../services/visita.service';
import {
  panelAgregarFarmacia, panelCrearFarmacia, listarPanelFarmacias, listarMaestroFarmacias,
  coberturaFarmaciaVM, aprobacionPendientesFarmacias, aprobarFarmacia, rechazarFarmacia, editarYAprobarFarmacia,
  type FarmaciaPanelItem, type FarmaciaDatos, type CoberturaFarmacia, type FarmaciaMaestro,
  type FarmaciaPendiente, type FarmaciaEditarAprobar,
} from '../../services/farmacias.service';

const formVacio: FarmaciaDatos = {
  es_cadena: false, cadena: '', sucursal: '', nombre: '', direccion: '',
  provincia: '', municipio: '', sector: '', encargado: '', telefono: '', email: '',
};

// Estado de aprobación del panel → chip.
const ESTADO: Record<string, { label: string; color: 'success' | 'warning' | 'error' | 'default' }> = {
  APROBADO: { label: 'Activa', color: 'success' },
  PENDIENTE_ALTA: { label: 'Pendiente GD', color: 'warning' },
  RECHAZADO: { label: 'Rechazada', color: 'error' },
};

// Tipo de solicitud pendiente → chip (bandeja de aprobación).
const TIPO: Record<string, { label: string; color: 'success' | 'info' }> = {
  NUEVA: { label: 'Farmacia nueva', color: 'success' },
  AGREGAR: { label: 'Del maestro', color: 'info' },
};

function mensajeError(err: unknown, fallback: string): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data ?? {};
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  const lista = (Array.isArray(data.detalle) ? data.detalle : Array.isArray(detail) ? detail : []) as Array<Record<string, any>>;
  if (lista.length) {
    const msgs = lista.map((d) => d?.ctx?.error ?? (d?.msg ?? '').replace(/^Value error,\s*/i, '')).filter(Boolean);
    if (msgs.length) return msgs.join(' · ');
  }
  return fallback;
}

// Nombre visible en vivo (F20): cadena+sucursal si es cadena, si no nombre.
function nombreVistaPrevia(f: FarmaciaDatos): string {
  const s = f.es_cadena ? `${f.cadena ?? ''} ${f.sucursal ?? ''}`.trim() : (f.nombre ?? '').trim();
  return s.toUpperCase();
}

const cap = (s: string) => (s ? s.charAt(0).toUpperCase() + s.slice(1).toLowerCase() : s);

// Dato con ícono + etiqueta, para la ficha del representante (mismo estilo que Panel Médico).
function infoDato(icon: ReactNode, label: string, value: string) {
  return (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
      <Box sx={{ color: 'text.secondary', display: 'flex' }}>{icon}</Box>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.1, fontWeight: 600, letterSpacing: 0.3 }}>{label}</Typography>
        <Typography variant="body2" fontWeight={700} noWrap>{value}</Typography>
      </Box>
    </Stack>
  );
}

export default function PanelFarmacia() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const esAprobador = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD' || rol === 'GERENTE_DISTRITO';
  const puedeGestionar = esVM || esAprobador;
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloAbiertoId = useCicloStore((s) => s.cicloAbiertoId);

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmFiltro, setVmFiltro] = useState<number | ''>('');
  // Ficha del representante (Gerente de Distrito + Línea), igual que Panel Médico.
  const [infoRep, setInfoRep] = useState<MiGerente | null>(null);
  const vmParam = esVM ? undefined : (vmFiltro || undefined);
  const listo = esVM || !!vmFiltro;

  const [panel, setPanel] = useState<FarmaciaPanelItem[]>([]);
  const [cober, setCober] = useState<CoberturaFarmacia | null>(null);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // ── Menú "AGREGAR FARMACIA" (Farmacia nueva / Farmacia existente) ──
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);

  // ── Diálogo "Farmacia nueva" (Acción B) ──
  const [dialogNuevaOpen, setDialogNuevaOpen] = useState(false);
  const [formNueva, setFormNueva] = useState<FarmaciaDatos>(formVacio);
  const [guardandoNueva, setGuardandoNueva] = useState(false);
  const [errorNueva, setErrorNueva] = useState<string | null>(null);

  // ── Diálogo "Farmacia existente" (Acción A: copiar al panel) ──
  const [dialogExistenteOpen, setDialogExistenteOpen] = useState(false);
  const [maestroLista, setMaestroLista] = useState<FarmaciaMaestro[]>([]);
  const [cargandoMaestro, setCargandoMaestro] = useState(false);
  const [filtroMaestro, setFiltroMaestro] = useState('');
  const [agregandoId, setAgregandoId] = useState<number | null>(null);

  // ── Solicitudes pendientes de aprobación (GD/ADMIN), inline en este panel ──
  const [pendientes, setPendientes] = useState<FarmaciaPendiente[]>([]);
  const [cargandoPend, setCargandoPend] = useState(false);
  const [procesando, setProcesando] = useState<number | null>(null);
  const [rechazando, setRechazando] = useState<FarmaciaPendiente | null>(null);
  const [motivo, setMotivo] = useState('');
  const [editando, setEditando] = useState<FarmaciaPendiente | null>(null);
  const [cambiosEditar, setCambiosEditar] = useState<FarmaciaEditarAprobar>({});

  const cargarPanel = useCallback(() => {
    if (!listo) { setPanel([]); setCober(null); setCargando(false); return; }
    setCargando(true);
    listarPanelFarmacias(vmParam, true).then(setPanel).catch(() => setPanel([])).finally(() => setCargando(false));
    // KPIs del ciclo abierto (Total / Visitadas / Sin visitar). Ad-hoc, no toca el Score.
    if (cicloAbiertoId) coberturaFarmaciaVM(cicloAbiertoId, vmParam).then(setCober).catch(() => setCober(null));
    else setCober(null);
  }, [listo, vmParam, cicloAbiertoId]);

  const cargarPendientes = useCallback(() => {
    if (!esAprobador) { setPendientes([]); return; }
    setCargandoPend(true);
    aprobacionPendientesFarmacias().then(setPendientes).catch(() => setPendientes([])).finally(() => setCargandoPend(false));
  }, [esAprobador]);

  useEffect(() => { cargarPanel(); }, [cargarPanel]);
  useEffect(() => { cargarPendientes(); }, [cargarPendientes]);
  useEffect(() => { if (!esVM) listarVMs().then(setVms).catch(() => {}); }, [esVM]);
  // El VM se ELIGE arriba; su Gerente de Distrito y Línea se muestran solos (de la dim del RM).
  useEffect(() => {
    if (esVM) miGerente().then(setInfoRep).catch(() => setInfoRep(null));
    else if (vmFiltro) miGerente(Number(vmFiltro)).then(setInfoRep).catch(() => setInfoRep(null));
    else setInfoRep(null);
  }, [esVM, vmFiltro]);

  // ── Menú Agregar Farmacia ──────────────────────────────────────────────
  const abrirNueva = () => {
    setMenuAnchor(null);
    if (!esVM && !vmFiltro) { setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM).' }); return; }
    setFormNueva(formVacio); setErrorNueva(null); setDialogNuevaOpen(true);
  };

  const abrirExistente = async () => {
    setMenuAnchor(null);
    if (!esVM && !vmFiltro) { setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM) para copiar la farmacia a su panel.' }); return; }
    setDialogExistenteOpen(true); setFiltroMaestro(''); setCargandoMaestro(true);
    try {
      const lista = await listarMaestroFarmacias({ pais_codigo: paisCodigo || undefined, estado: 'ACTIVA' });
      setMaestroLista(lista);
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudieron cargar las farmacias existentes.' });
    } finally { setCargandoMaestro(false); }
  };

  // ── Farmacia nueva ──────────────────────────────────────────────────────
  const faltantesNueva: string[] = [];
  if (!formNueva.direccion.trim()) faltantesNueva.push('dirección');
  if (!formNueva.encargado.trim()) faltantesNueva.push('encargado');
  if (formNueva.es_cadena ? !formNueva.cadena?.trim() : !formNueva.nombre?.trim()) {
    faltantesNueva.push(formNueva.es_cadena ? 'cadena' : 'nombre');
  }
  const puedeGuardarNueva = faltantesNueva.length === 0;

  async function guardarNueva() {
    if (!puedeGuardarNueva) return;
    setGuardandoNueva(true); setErrorNueva(null);
    try {
      await panelCrearFarmacia({ ...formNueva }, vmParam);
      setMsg({ tipo: 'success', texto: 'Farmacia registrada — pendiente de aprobación del Gerente de Distrito.' });
      setDialogNuevaOpen(false); cargarPanel();
    } catch (err: unknown) {
      const status = (err as { response?: { status?: number } })?.response?.status;
      if (status === 409) {
        // Duplicado: sugiere usar "Farmacia existente" en vez de crear una fila nueva.
        setErrorNueva(mensajeError(err, 'Ya existe una farmacia similar en el maestro.'));
      } else {
        setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo registrar la farmacia.') });
      }
    } finally { setGuardandoNueva(false); }
  }

  // ── Farmacia existente (copiar al panel) ────────────────────────────────
  const maestroFiltrado = useMemo(() => {
    const q = filtroMaestro.trim().toUpperCase();
    return maestroLista.filter((f) => !q || f.nombre_completo.toUpperCase().includes(q));
  }, [maestroLista, filtroMaestro]);

  async function agregarExistente(f: FarmaciaMaestro) {
    setAgregandoId(f.id); setMsg(null);
    try {
      await panelAgregarFarmacia(f.id, vmParam);
      setMsg({ tipo: 'success', texto: `${f.nombre_completo} agregada a tu panel — pendiente de aprobación del Gerente de Distrito.` });
      setDialogExistenteOpen(false); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo agregar la farmacia.') });
    } finally { setAgregandoId(null); }
  }

  // ── Solicitudes pendientes (GD/ADMIN) ───────────────────────────────────
  async function aprobarSolicitud(p: FarmaciaPendiente) {
    setProcesando(p.id); setMsg(null);
    try {
      await aprobarFarmacia(p.id);
      setMsg({ tipo: 'success', texto: `${p.nombre_completo ?? 'Farmacia'} aprobada.` });
      cargarPendientes(); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo aprobar.') });
    } finally { setProcesando(null); }
  }

  function abrirRechazo(p: FarmaciaPendiente) { setRechazando(p); setMotivo(''); }
  async function confirmarRechazo() {
    if (!rechazando || !motivo.trim()) return;
    setProcesando(rechazando.id); setMsg(null);
    try {
      await rechazarFarmacia(rechazando.id, motivo.trim());
      setMsg({ tipo: 'success', texto: 'Solicitud rechazada.' });
      setRechazando(null); cargarPendientes(); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo rechazar.') });
    } finally { setProcesando(null); }
  }

  function abrirEditar(p: FarmaciaPendiente) {
    setEditando(p);
    setCambiosEditar({ direccion: p.direccion ?? '', encargado: p.encargado ?? '' });
  }
  async function confirmarEditarAprobar() {
    if (!editando) return;
    if (!cambiosEditar.direccion?.trim() || !cambiosEditar.encargado?.trim()) {
      setMsg({ tipo: 'error', texto: 'Dirección y encargado son obligatorios.' }); return;
    }
    setProcesando(editando.id); setMsg(null);
    try {
      await editarYAprobarFarmacia(editando.id, cambiosEditar);
      setMsg({ tipo: 'success', texto: `${editando.nombre_completo ?? 'Farmacia'} corregida y aprobada.` });
      setEditando(null); cargarPendientes(); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo guardar.') });
    } finally { setProcesando(null); }
  }

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 }, maxWidth: 760, mx: 'auto' }}>
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center" justifyContent="space-between" flexWrap="wrap" useFlexGap>
          <Stack direction="row" spacing={1.5} alignItems="center">
            <Avatar sx={{ bgcolor: 'primary.main' }}><LocalPharmacy /></Avatar>
            <Box>
              <Typography variant="h5" fontWeight={700}>Panel Farmacia</Typography>
              <Typography variant="body2" color="text.secondary">
                {panel.length} farmacia{panel.length === 1 ? '' : 's'} en tu panel
              </Typography>
            </Box>
          </Stack>
          {puedeGestionar && (
            <Button variant="contained" startIcon={<Add />} onClick={(e) => setMenuAnchor(e.currentTarget)}>
              Agregar Farmacia
            </Button>
          )}
          <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
            <MenuItem onClick={abrirNueva}>
              <Add fontSize="small" style={{ marginRight: 8 }} /> Farmacia nueva
            </MenuItem>
            <MenuItem onClick={abrirExistente}>
              <HowToReg fontSize="small" style={{ marginRight: 8 }} /> Farmacia existente (copiar al panel)
            </MenuItem>
          </Menu>
        </Stack>
      </Box>

      {/* Ficha del representante: se ELIGE el VM aquí; su Gerente de Distrito y Línea salen
          solos (de la dim del RM). Un VM ve su ficha fija. Mismo patrón que Panel Médico. */}
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
                  <TextField select variant="standard" label="Representante médico (VM)" value={vmFiltro} sx={{ minWidth: 240 }}
                             onChange={(e) => setVmFiltro(e.target.value === '' ? '' : Number(e.target.value))}>
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

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* Solicitudes pendientes de aprobación (Gerente de Distrito / ADMIN) — INLINE,
          reemplaza la pantalla separada "Aprobación Farmacias". No depende de tener un
          VM seleccionado: el GD revisa las de todo su distrito. */}
      {esAprobador && (
        <Card variant="outlined" sx={{ mb: 2, borderColor: pendientes.length ? 'warning.main' : 'divider' }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <HowToReg color={pendientes.length ? 'warning' : 'disabled'} />
              <Typography variant="subtitle1" fontWeight={700}>Solicitudes pendientes de aprobación</Typography>
              {pendientes.length > 0 && <Chip size="small" color="warning" label={pendientes.length} />}
            </Stack>
            {cargandoPend ? (
              <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box>
            ) : pendientes.length === 0 ? (
              <Typography variant="body2" color="text.secondary">No hay solicitudes pendientes.</Typography>
            ) : (
              <Stack divider={<Divider />} spacing={0}>
                {pendientes.map((p) => {
                  const tipo = TIPO[p.tipo_solicitud] ?? { label: p.tipo_solicitud, color: 'info' as const };
                  return (
                    <Stack key={p.id} direction={{ xs: 'column', sm: 'row' }} alignItems={{ sm: 'center' }} spacing={1.5} sx={{ py: 1.5 }}>
                      <Chip size="small" color={tipo.color} label={tipo.label} sx={{ alignSelf: 'flex-start' }} />
                      <Box sx={{ flex: 1, minWidth: 0 }}>
                        <Typography variant="body2" fontWeight={700} noWrap>{p.nombre_completo ?? '—'}</Typography>
                        <Typography variant="caption" color="text.secondary" sx={{ display: 'block' }}>
                          {[p.direccion, p.encargado ? `Encargado: ${p.encargado}` : null, `VM: ${p.vm_nombre}`,
                            p.fecha_solicitud ? new Date(p.fecha_solicitud).toLocaleDateString() : null]
                            .filter(Boolean).join(' · ')}
                        </Typography>
                        {p.posible_duplicado && p.posible_duplicado.length > 0 && (
                          <Stack direction="row" spacing={0.5} alignItems="center" sx={{ mt: 0.5 }}>
                            <Warning fontSize="small" color="warning" />
                            <Typography variant="caption" color="warning.dark">
                              Posible duplicado: {p.posible_duplicado.map((d) => d.nombre_completo).join(', ')}
                            </Typography>
                          </Stack>
                        )}
                      </Box>
                      <Stack direction="row" spacing={1} sx={{ flexShrink: 0 }}>
                        <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />}
                                disabled={procesando === p.id} onClick={() => aprobarSolicitud(p)}>Aprobar</Button>
                        <Button size="small" variant="outlined" startIcon={<Edit />}
                                disabled={procesando === p.id} onClick={() => abrirEditar(p)}>Editar y aprobar</Button>
                        <Button size="small" variant="outlined" color="error" startIcon={<ThumbDown />}
                                disabled={procesando === p.id} onClick={() => abrirRechazo(p)}>Rechazar</Button>
                      </Stack>
                    </Stack>
                  );
                })}
              </Stack>
            )}
          </CardContent>
        </Card>
      )}

      {!listo ? (
        <Alert severity="info">Selecciona un visitador para gestionar su panel de farmacias.</Alert>
      ) : (
        <>
          {/* KPIs del ciclo abierto. Aplican a farmacias (ad-hoc, sin F1/F2): Total activas,
              Visitadas y Sin visitar. NO se cablean al Score (COB_FARMACIAS viene del SFA). */}
          <Stack direction="row" spacing={1.5} sx={{ mb: 2 }} flexWrap="wrap">
            {[
              { label: 'Total panel', valor: cober?.universo ?? 0, sub: 'farmacias activas', color: 'text.primary' },
              { label: 'Visitadas', valor: cober?.visitadas ?? 0, sub: 'en el ciclo actual', color: 'success.main' },
              { label: 'Sin visitar', valor: cober ? Math.max(0, cober.universo - cober.visitadas) : 0, sub: 'requieren atención', color: 'warning.main' },
            ].map((k) => (
              <Card key={k.label} variant="outlined" sx={{ flex: '1 1 140px', minWidth: 130 }}>
                <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
                  <Typography variant="caption" color="text.secondary" sx={{ textTransform: 'uppercase', letterSpacing: 0.3, fontWeight: 600, display: 'block' }}>{k.label}</Typography>
                  <Typography variant="h4" fontWeight={700} sx={{ color: k.color, lineHeight: 1.15, my: 0.25 }}>{k.valor}</Typography>
                  <Typography variant="caption" color="text.secondary">{k.sub}</Typography>
                </CardContent>
              </Card>
            ))}
          </Stack>

          <Card variant="outlined">
            <CardContent sx={{ py: 1.5 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Mi panel</Typography>
              {cargando ? (
                <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box>
              ) : panel.length === 0 ? (
                <Alert severity="info">Aún no hay farmacias en el panel. Agrégala con "Agregar Farmacia".</Alert>
              ) : (
                <Stack divider={<Divider />}>
                  {panel.map((f) => {
                    const est = ESTADO[f.estado_aprobacion] ?? { label: f.estado_aprobacion, color: 'default' as const };
                    return (
                      <Stack key={f.panel_id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                        <FiberManualRecord sx={{ fontSize: 11, color: `${est.color}.main` }} />
                        <Box sx={{ flex: 1, minWidth: 0 }}>
                          <Typography fontWeight={700} noWrap>{f.nombre_completo ?? '—'}</Typography>
                          <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                            {[f.direccion, f.encargado ? `Encargado: ${f.encargado}` : null].filter(Boolean).join(' · ')}
                          </Typography>
                        </Box>
                        <Tooltip title={f.motivo ?? ''} disableHoverListener={!f.motivo}>
                          <Chip size="small" color={est.color === 'default' ? undefined : est.color}
                                variant={est.color === 'success' ? 'filled' : 'outlined'} label={est.label} />
                        </Tooltip>
                      </Stack>
                    );
                  })}
                </Stack>
              )}
            </CardContent>
          </Card>
        </>
      )}

      {/* Farmacia nueva (Acción B) */}
      <Dialog open={dialogNuevaOpen} onClose={() => !guardandoNueva && setDialogNuevaOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle><Add sx={{ verticalAlign: 'middle', mr: 1 }} />Farmacia nueva</DialogTitle>
        <DialogContent dividers>
          <FormControlLabel
            sx={{ mb: 1.5 }}
            control={<Switch checked={formNueva.es_cadena}
                             onChange={(e) => setFormNueva((f) => ({ ...f, es_cadena: e.target.checked }))} />}
            label={formNueva.es_cadena ? 'Es cadena' : 'No es cadena (farmacia independiente)'}
          />
          <Grid container spacing={1.5}>
            {formNueva.es_cadena ? (
              <>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Cadena" value={formNueva.cadena ?? ''}
                             onChange={(e) => setFormNueva((f) => ({ ...f, cadena: e.target.value }))} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Sucursal" value={formNueva.sucursal ?? ''}
                             onChange={(e) => setFormNueva((f) => ({ ...f, sucursal: e.target.value }))} />
                </Grid>
                <Grid item xs={12}>
                  <Typography variant="caption" color="text.secondary">
                    Se mostrará como: <b>{nombreVistaPrevia(formNueva) || '—'}</b>
                  </Typography>
                </Grid>
              </>
            ) : (
              <Grid item xs={12}>
                <TextField fullWidth size="small" label="Nombre de la farmacia" value={formNueva.nombre ?? ''}
                           onChange={(e) => setFormNueva((f) => ({ ...f, nombre: e.target.value }))} />
              </Grid>
            )}
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Dirección" value={formNueva.direccion}
                         error={!formNueva.direccion.trim()}
                         onChange={(e) => setFormNueva((f) => ({ ...f, direccion: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Encargado" value={formNueva.encargado}
                         error={!formNueva.encargado.trim()}
                         onChange={(e) => setFormNueva((f) => ({ ...f, encargado: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Teléfono (opcional)" value={formNueva.telefono ?? ''}
                         onChange={(e) => setFormNueva((f) => ({ ...f, telefono: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Sector (opcional)" value={formNueva.sector ?? ''}
                         onChange={(e) => setFormNueva((f) => ({ ...f, sector: e.target.value }))} />
            </Grid>
            {faltantesNueva.length > 0 && (
              <Grid item xs={12}>
                <Typography variant="caption" color="error">Falta: {faltantesNueva.join(', ')}.</Typography>
              </Grid>
            )}
            {errorNueva && (
              <Grid item xs={12}>
                <Alert severity="warning" icon={<Warning />}>
                  {errorNueva} Si ya existe, usa <b>«Farmacia existente (copiar al panel)»</b> en vez de crear una nueva.
                </Alert>
              </Grid>
            )}
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogNuevaOpen(false)} disabled={guardandoNueva}>Cancelar</Button>
          <Button variant="contained" disabled={!puedeGuardarNueva || guardandoNueva} onClick={guardarNueva}>
            {guardandoNueva ? 'Guardando…' : 'Guardar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Farmacia existente (Acción A: copiar al panel) */}
      <Dialog open={dialogExistenteOpen} onClose={() => setDialogExistenteOpen(false)} maxWidth="sm" fullWidth>
        <DialogTitle><HowToReg sx={{ verticalAlign: 'middle', mr: 1 }} />Copiar farmacia existente al panel</DialogTitle>
        <DialogContent dividers>
          <TextField fullWidth size="small" placeholder="Buscar por nombre…" value={filtroMaestro} sx={{ mb: 1.5 }}
                     onChange={(e) => setFiltroMaestro(e.target.value)}
                     InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
          {cargandoMaestro ? (
            <Box sx={{ textAlign: 'center', py: 3 }}><CircularProgress size={24} /></Box>
          ) : maestroFiltrado.length === 0 ? (
            <Alert severity="info">Sin farmacias activas que coincidan.</Alert>
          ) : (
            <Stack divider={<Divider />}>
              {maestroFiltrado.map((f) => (
                <Stack key={f.id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography fontWeight={700} noWrap>{f.nombre_completo}</Typography>
                    <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                      {f.direccion}
                    </Typography>
                  </Box>
                  <Button size="small" variant="contained" disabled={agregandoId === f.id} onClick={() => agregarExistente(f)}>
                    {agregandoId === f.id ? 'Agregando…' : 'Agregar'}
                  </Button>
                </Stack>
              ))}
            </Stack>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setDialogExistenteOpen(false)}>Cerrar</Button>
        </DialogActions>
      </Dialog>

      {/* Rechazar solicitud — motivo obligatorio */}
      <Dialog open={!!rechazando} onClose={() => setRechazando(null)} maxWidth="sm" fullWidth>
        <DialogTitle>Rechazar solicitud</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>{rechazando?.nombre_completo}</Typography>
          <TextField fullWidth multiline minRows={2} required label="Motivo del rechazo" value={motivo}
                     error={!motivo.trim()}
                     helperText={!motivo.trim() ? 'El motivo es obligatorio.' : ' '}
                     onChange={(e) => setMotivo(e.target.value)} />
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRechazando(null)}>Cancelar</Button>
          <Button color="error" variant="contained" disabled={!motivo.trim() || procesando === rechazando?.id}
                  onClick={confirmarRechazo}>
            {procesando === rechazando?.id ? 'Rechazando…' : 'Rechazar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Editar y aprobar */}
      <Dialog open={!!editando} onClose={() => setEditando(null)} maxWidth="sm" fullWidth>
        <DialogTitle><HowToReg sx={{ verticalAlign: 'middle', mr: 1 }} />Corregir y aprobar</DialogTitle>
        <DialogContent>
          <Typography variant="body2" sx={{ mb: 1.5 }}>{editando?.nombre_completo}</Typography>
          <Grid container spacing={1.5}>
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Dirección" value={cambiosEditar.direccion ?? ''}
                         error={!cambiosEditar.direccion?.trim()}
                         onChange={(e) => setCambiosEditar((c) => ({ ...c, direccion: e.target.value }))} />
            </Grid>
            <Grid item xs={12}>
              <TextField fullWidth size="small" required label="Encargado" value={cambiosEditar.encargado ?? ''}
                         error={!cambiosEditar.encargado?.trim()}
                         onChange={(e) => setCambiosEditar((c) => ({ ...c, encargado: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Teléfono" value={cambiosEditar.telefono ?? ''}
                         onChange={(e) => setCambiosEditar((c) => ({ ...c, telefono: e.target.value }))} />
            </Grid>
            <Grid item xs={12} sm={6}>
              <TextField fullWidth size="small" label="Email" value={cambiosEditar.email ?? ''}
                         onChange={(e) => setCambiosEditar((c) => ({ ...c, email: e.target.value }))} />
            </Grid>
          </Grid>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setEditando(null)}>Cancelar</Button>
          <Button variant="contained" color="success"
                  disabled={!cambiosEditar.direccion?.trim() || !cambiosEditar.encargado?.trim() || procesando === editando?.id}
                  onClick={confirmarEditarAprobar}>
            {procesando === editando?.id ? 'Guardando…' : 'Guardar y aprobar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
