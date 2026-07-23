/**
 * PanelFarmacia.tsx — Panel de Farmacias del VM (móvil).
 * Buscar en el maestro (anti-dup F25/F09) → Acción A (agregar existente) o Acción B
 * (crear nueva, bloqueantes F23/F24) → "Mi panel" con estado de aprobación.
 * Espejo de PanelMedico.tsx, alcance reducido a lo que pide la Tarea 8 del plan
 * `2026-07-22-modulo-farmacias.md`.
 */
import { useCallback, useEffect, useState, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, CircularProgress, Avatar, Divider, Switch, FormControlLabel, Tooltip,
} from '@mui/material';
import { LocalPharmacy, Search, Add, FiberManualRecord, HowToReg, Badge, SupervisorAccount, Layers } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import { listarVMs, miGerente, type Catalogo, type MiGerente } from '../../services/visita.service';
import {
  buscarFarmaciaMaestro, panelAgregarFarmacia, panelCrearFarmacia, listarPanelFarmacias,
  coberturaFarmaciaVM,
  type FarmaciaDuro, type FarmaciaPanelItem, type FarmaciaDatos, type CoberturaFarmacia,
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

  // ── Búsqueda anti-dup (F25/F09) ──
  const [esCadena, setEsCadena] = useState(false);
  const [qCadena, setQCadena] = useState('');
  const [qSucursal, setQSucursal] = useState('');
  const [qNombre, setQNombre] = useState('');
  const [buscando, setBuscando] = useState(false);
  const [buscado, setBuscado] = useState(false);
  const [resultados, setResultados] = useState<FarmaciaDuro[]>([]);
  const [agregandoId, setAgregandoId] = useState<number | null>(null);

  // ── Formulario de creación (Acción B, F25: solo tras búsqueda sin resultado) ──
  const [form, setForm] = useState<FarmaciaDatos>(formVacio);
  const [guardando, setGuardando] = useState(false);

  const cargarPanel = useCallback(() => {
    if (!listo) { setPanel([]); setCober(null); setCargando(false); return; }
    setCargando(true);
    listarPanelFarmacias(vmParam, true).then(setPanel).catch(() => setPanel([])).finally(() => setCargando(false));
    // KPIs del ciclo abierto (Total / Visitadas / Sin visitar). Ad-hoc, no toca el Score.
    if (cicloAbiertoId) coberturaFarmaciaVM(cicloAbiertoId, vmParam).then(setCober).catch(() => setCober(null));
    else setCober(null);
  }, [listo, vmParam, cicloAbiertoId]);

  useEffect(() => { cargarPanel(); }, [cargarPanel]);
  useEffect(() => { if (!esVM) listarVMs().then(setVms).catch(() => {}); }, [esVM]);
  // El VM se ELIGE arriba; su Gerente de Distrito y Línea se muestran solos (de la dim del RM).
  useEffect(() => {
    if (esVM) miGerente().then(setInfoRep).catch(() => setInfoRep(null));
    else if (vmFiltro) miGerente(Number(vmFiltro)).then(setInfoRep).catch(() => setInfoRep(null));
    else setInfoRep(null);
  }, [esVM, vmFiltro]);

  const reiniciarBusqueda = () => {
    setBuscado(false); setResultados([]); setForm(formVacio);
    setQCadena(''); setQSucursal(''); setQNombre('');
  };

  async function buscar() {
    if (esCadena && !qCadena.trim()) { setMsg({ tipo: 'error', texto: 'Ingresa el nombre de la cadena.' }); return; }
    if (!esCadena && !qNombre.trim()) { setMsg({ tipo: 'error', texto: 'Ingresa el nombre de la farmacia.' }); return; }
    setBuscando(true); setMsg(null);
    try {
      const r = await buscarFarmaciaMaestro({
        cadena: esCadena ? qCadena.trim() : undefined,
        sucursal: esCadena ? qSucursal.trim() : undefined,
        nombre: !esCadena ? qNombre.trim() : undefined,
        pais_codigo: paisCodigo || undefined,
      });
      setResultados(r.duros); setBuscado(true);
      // F25: prepara el formulario con lo ya escrito, editable antes de guardar.
      setForm({ ...formVacio, es_cadena: esCadena, cadena: qCadena.trim(), sucursal: qSucursal.trim(), nombre: qNombre.trim() });
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo buscar en el maestro.') });
    } finally { setBuscando(false); }
  }

  async function agregarExistente(f: FarmaciaDuro) {
    if (!esVM && !vmFiltro) { setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM).' }); return; }
    setAgregandoId(f.id); setMsg(null);
    try {
      await panelAgregarFarmacia(f.id, vmParam);
      setMsg({ tipo: 'success', texto: `${f.nombre_completo} agregada a tu panel — pendiente de aprobación del Gerente de Distrito.` });
      reiniciarBusqueda(); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo agregar la farmacia.') });
    } finally { setAgregandoId(null); }
  }

  const setF = (k: keyof FarmaciaDatos, v: unknown) => setForm((f) => ({ ...f, [k]: v }));

  // Guardar deshabilitado hasta completar dirección + encargado (F23/F24), patrón PanelMedico.
  const faltantes: string[] = [];
  if (!form.direccion.trim()) faltantes.push('dirección');
  if (!form.encargado.trim()) faltantes.push('encargado');
  const puedeGuardar = faltantes.length === 0 && (esCadena ? !!form.cadena?.trim() : !!form.nombre?.trim());

  async function crear() {
    if (!esVM && !vmFiltro) { setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM).' }); return; }
    if (!puedeGuardar) return;
    setGuardando(true); setMsg(null);
    try {
      await panelCrearFarmacia({ ...form, es_cadena: esCadena }, vmParam);
      setMsg({ tipo: 'success', texto: 'Farmacia registrada — pendiente de aprobación del Gerente de Distrito.' });
      reiniciarBusqueda(); cargarPanel();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err, 'No se pudo registrar la farmacia.') });
    } finally { setGuardando(false); }
  }

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 }, maxWidth: 720, mx: 'auto' }}>
      <Box sx={{ mb: 2 }}>
        <Stack direction="row" spacing={1.5} alignItems="center">
          <Avatar sx={{ bgcolor: 'primary.main' }}><LocalPharmacy /></Avatar>
          <Box>
            <Typography variant="h5" fontWeight={700}>Panel Farmacia</Typography>
            <Typography variant="body2" color="text.secondary">
              {panel.length} farmacia{panel.length === 1 ? '' : 's'} en tu panel
            </Typography>
          </Box>
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

          {puedeGestionar && (
            <Card variant="outlined" sx={{ mb: 2 }}>
              <CardContent>
                <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1.5 }}>
                  Agregar farmacia
                </Typography>
                <FormControlLabel
                  sx={{ mb: 1 }}
                  control={<Switch checked={esCadena} onChange={(e) => { setEsCadena(e.target.checked); reiniciarBusqueda(); }} />}
                  label={esCadena ? 'Es cadena' : 'No es cadena (farmacia independiente)'}
                />
                <Stack direction={{ xs: 'column', sm: 'row' }} spacing={1.5} sx={{ mb: 1.5 }}>
                  {esCadena ? (
                    <>
                      <TextField size="small" fullWidth label="Cadena" value={qCadena}
                                 autoCapitalize="none"
                                 onChange={(e) => setQCadena(e.target.value)} />
                      <TextField size="small" fullWidth label="Sucursal" value={qSucursal}
                                 autoCapitalize="none"
                                 onChange={(e) => setQSucursal(e.target.value)} />
                    </>
                  ) : (
                    <TextField size="small" fullWidth label="Nombre de la farmacia" value={qNombre}
                               autoCapitalize="none"
                               onChange={(e) => setQNombre(e.target.value)} />
                  )}
                  <Button variant="contained" startIcon={<Search />} disabled={buscando} onClick={buscar}
                          sx={{ whiteSpace: 'nowrap' }}>
                    {buscando ? 'Buscando…' : 'Buscar'}
                  </Button>
                </Stack>
                {/* Vista previa del nombre compuesto (F20) mientras se escribe */}
                {esCadena && (qCadena || qSucursal) && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 1 }}>
                    Se mostrará como: <b>{`${qCadena} ${qSucursal}`.trim().toUpperCase() || '—'}</b>
                  </Typography>
                )}

                {buscando ? (
                  <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box>
                ) : buscado && (
                  <Box sx={{ mt: 1.5 }}>
                    {resultados.length > 0 ? (
                      <>
                        <Alert severity="warning" sx={{ mb: 1 }}>
                          Ya existe{resultados.length > 1 ? 'n' : ''} en el maestro. Agrégala a tu panel en vez de duplicarla.
                        </Alert>
                        <Stack divider={<Divider />}>
                          {resultados.map((f) => (
                            <Stack key={f.id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                              <Box sx={{ flex: 1, minWidth: 0 }}>
                                <Typography fontWeight={700} noWrap>{f.nombre_completo}</Typography>
                                <Typography variant="caption" color="text.secondary">Estado: {f.estado}</Typography>
                              </Box>
                              <Button size="small" variant="contained" startIcon={<HowToReg />}
                                      disabled={agregandoId === f.id}
                                      onClick={() => agregarExistente(f)}>
                                {agregandoId === f.id ? 'Agregando…' : 'Agregar a mi panel'}
                              </Button>
                            </Stack>
                          ))}
                        </Stack>
                      </>
                    ) : (
                      <>
                        <Alert severity="info" sx={{ mb: 1.5 }}>
                          Sin resultados — completa los datos para dar de alta la farmacia.
                        </Alert>
                        <Stack spacing={1.5}>
                          {!esCadena && (
                            <TextField size="small" fullWidth label="Nombre de la farmacia" value={form.nombre ?? ''}
                                       autoCapitalize="none"
                                       onChange={(e) => setF('nombre', e.target.value)} />
                          )}
                          <TextField size="small" fullWidth required label="Dirección" value={form.direccion}
                                     error={!form.direccion.trim()}
                                     autoCapitalize="none"
                                     onChange={(e) => setF('direccion', e.target.value)} />
                          <TextField size="small" fullWidth required label="Encargado" value={form.encargado}
                                     error={!form.encargado.trim()}
                                     autoCapitalize="none"
                                     onChange={(e) => setF('encargado', e.target.value)} />
                          <Stack direction="row" spacing={1.5}>
                            <TextField size="small" fullWidth label="Teléfono (opcional)" value={form.telefono ?? ''}
                                       onChange={(e) => setF('telefono', e.target.value)} />
                            <TextField size="small" fullWidth label="Sector (opcional)" value={form.sector ?? ''}
                                       autoCapitalize="none"
                                       onChange={(e) => setF('sector', e.target.value)} />
                          </Stack>
                          {faltantes.length > 0 && (
                            <Typography variant="caption" color="error">
                              Falta: {faltantes.join(', ')}.
                            </Typography>
                          )}
                          <Button variant="contained" startIcon={<Add />} disabled={!puedeGuardar || guardando}
                                  onClick={crear}>
                            {guardando ? 'Guardando…' : 'Guardar'}
                          </Button>
                        </Stack>
                      </>
                    )}
                  </Box>
                )}
              </CardContent>
            </Card>
          )}

          <Card variant="outlined">
            <CardContent sx={{ py: 1.5 }}>
              <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Mi panel</Typography>
              {cargando ? (
                <Box sx={{ textAlign: 'center', py: 2 }}><CircularProgress size={22} /></Box>
              ) : panel.length === 0 ? (
                <Alert severity="info">Aún no hay farmacias en el panel.</Alert>
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
    </Box>
  );
}
