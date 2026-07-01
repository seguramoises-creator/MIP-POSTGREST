import { useEffect, useState, useCallback, useMemo } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  MenuItem, ToggleButton, ToggleButtonGroup, CircularProgress, Autocomplete, Divider,
} from '@mui/material';
import { CheckCircle, Cancel, Save, EventBusy, Warning, Place, LocalHospital } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarMedicos, listarCausas, misVisitasHoy, registrarVisita, registrarNoVisita, listarVMs,
  type MedicoVisita, type VisitaHoy, type Catalogo,
} from '../../services/visita.service';

const CAT_COLOR: Record<string, 'success' | 'primary' | 'warning'> = { A: 'success', B: 'primary', C: 'warning' };

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

export default function RegistrarVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';

  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmId, setVmId] = useState<number | ''>('');       // solo ADMIN/GERENTE
  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [causas, setCausas] = useState<string[]>([]);
  const [hoy, setHoy] = useState<VisitaHoy[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [medico, setMedico] = useState<MedicoVisita | null>(null);
  const [tipo, setTipo] = useState<'V' | 'R'>('V');
  const [comentario, setComentario] = useState('');
  const [haceMin, setHaceMin] = useState('0');
  const [modoNoVisita, setModoNoVisita] = useState(false);
  const [causa, setCausa] = useState('');
  const [guardando, setGuardando] = useState(false);

  // El RM va contra su propio panel (backend fuerza rm_id); ADMIN/GERENTE deben elegir un VM.
  const vmParam = esVM ? undefined : (vmId || undefined);
  const listo = esVM || !!vmId;

  const cargarFeed = useCallback(() => {
    if (!listo) { setHoy([]); return; }
    misVisitasHoy(vmParam).then(setHoy).catch(() => setHoy([]));
  }, [listo, vmParam]);

  // Catálogos estáticos (una vez).
  useEffect(() => {
    listarCausas().then(setCausas).catch(() => {});
    if (!esVM) listarVMs().then(setVms).catch(() => {});
    setCargando(false);
  }, [esVM]);

  // Médicos + feed cuando cambia el VM elegido (o al entrar como RM).
  useEffect(() => {
    setMedico(null);
    if (!listo) { setMedicos([]); setHoy([]); return; }
    listarMedicos(vmParam).then(setMedicos).catch(() => setMedicos([]));
    misVisitasHoy(vmParam).then(setHoy).catch(() => setHoy([]));
  }, [listo, vmParam]);

  const visitadosHoy = useMemo(
    () => new Set(hoy.filter((h) => h.ejecutada).map((h) => h.medico_id)),
    [hoy],
  );
  const yaVisitado = medico ? visitadosHoy.has(medico.id) : false;

  const limpiar = () => { setMedico(null); setTipo('V'); setComentario(''); setHaceMin('0'); setModoNoVisita(false); setCausa(''); };

  async function guardar() {
    if (!medico) { setMsg({ tipo: 'error', texto: 'Selecciona el médico.' }); return; }
    setGuardando(true); setMsg(null);
    try {
      if (modoNoVisita) {
        if (!causa) { setMsg({ tipo: 'error', texto: 'Selecciona la causa.' }); setGuardando(false); return; }
        await registrarNoVisita(medico.id, causa, comentario || undefined, vmParam);
        setMsg({ tipo: 'success', texto: 'No-visita registrada.' });
      } else {
        await registrarVisita(medico.id, tipo, comentario, Number(haceMin) || 0, vmParam);
        setMsg({ tipo: 'success', texto: 'Visita registrada.' });
      }
      limpiar(); cargarFeed();
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo registrar.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ maxWidth: 560, mx: 'auto', p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Registrar Visita</Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* Selector de visitador: solo ADMIN/GERENTE. El RM opera sobre su propio panel. */}
      {!esVM && (
        <TextField select fullWidth size="small" label="Visitador (VM)" value={vmId} sx={{ mb: 2 }}
                   helperText="Elige el visitador para ver y registrar sobre su panel"
                   onChange={(e) => setVmId(e.target.value === '' ? '' : Number(e.target.value))}>
          <MenuItem value=""><em>— Selecciona un visitador —</em></MenuItem>
          {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
        </TextField>
      )}

      {!listo ? (
        <Alert severity="info">Selecciona un visitador para cargar su panel de médicos.</Alert>
      ) : (
      <Card variant="outlined" sx={{ mb: 2 }}>
        <CardContent>
          <Stack spacing={2}>
            <Autocomplete
              options={medicos}
              value={medico}
              onChange={(_, v) => setMedico(v)}
              getOptionLabel={(m) => m.nombre_completo}
              isOptionEqualToValue={(a, b) => a.id === b.id}
              noOptionsText={medicos.length === 0 ? 'No hay médicos en este panel' : 'Sin coincidencias'}
              renderInput={(params) => (
                <TextField {...params} label="Médico visitado" required
                           placeholder="Escribe para buscar en tu panel…" />
              )}
              renderOption={(props, m) => (
                <Box component="li" {...props} key={m.id}
                     sx={{ display: 'flex', justifyContent: 'space-between', gap: 1 }}>
                  <Box sx={{ minWidth: 0 }}>
                    <Typography variant="body2" noWrap>{m.nombre_completo}</Typography>
                    <Typography variant="caption" color="text.secondary" noWrap>
                      {m.especialidad_nombre || 'Sin especialidad'}
                    </Typography>
                  </Box>
                  <Stack direction="row" spacing={0.5} alignItems="center">
                    {visitadosHoy.has(m.id) && <CheckCircle color="success" fontSize="small" />}
                    <Chip size="small" label={m.categoria} color={CAT_COLOR[m.categoria] ?? 'default'} />
                  </Stack>
                </Box>
              )}
            />

            {/* Ficha del médico elegido: contexto para el representante en el momento de la visita. */}
            {medico && (
              <Box sx={{ bgcolor: 'action.hover', borderRadius: 1, p: 1.5 }}>
                <Stack direction="row" spacing={1} flexWrap="wrap" alignItems="center" sx={{ mb: 0.5 }}>
                  <Chip size="small" label={`Cat. ${medico.categoria}`} color={CAT_COLOR[medico.categoria] ?? 'default'} />
                  <Chip size="small" variant="outlined" icon={<LocalHospital />} label={medico.especialidad_nombre || 'Sin especialidad'} />
                  {medico.tipo_consultorio && <Chip size="small" variant="outlined" label={medico.tipo_consultorio} />}
                </Stack>
                {medico.direccion && (
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                    <Place fontSize="inherit" /> {medico.direccion}
                  </Typography>
                )}
                {medico.ciclos_sin_visita > 0 && (
                  <Typography variant="caption" color="warning.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                    <Warning fontSize="inherit" /> {medico.ciclos_sin_visita} ciclo(s) sin visita — riesgo de ruptura
                  </Typography>
                )}
                {yaVisitado && (
                  <Typography variant="caption" color="success.main" sx={{ display: 'flex', alignItems: 'center', gap: 0.5, mt: 0.5 }}>
                    <CheckCircle fontSize="inherit" /> Ya registraste una visita a este médico hoy
                  </Typography>
                )}
              </Box>
            )}

            <Divider />

            {!modoNoVisita ? (
              <>
                <Box>
                  <Typography variant="caption" color="text.secondary">Tipo de visita</Typography>
                  <ToggleButtonGroup exclusive fullWidth value={tipo} onChange={(_, v) => v && setTipo(v)} sx={{ mt: 0.5 }}>
                    <ToggleButton value="V" color="primary">Vista</ToggleButton>
                    <ToggleButton value="R" color="secondary">Revisita</ToggleButton>
                  </ToggleButtonGroup>
                </Box>
                <TextField label="Comentario de la visita (mín. 10, no genérico)" multiline minRows={3}
                           value={comentario} onChange={(e) => setComentario(e.target.value)}
                           helperText='Ej: "MEDICO PREGUNTO POR INTERACCION CON METFORMINA"' />
                <TextField select label="¿Hace cuánto ocurrió?" value={haceMin} sx={{ maxWidth: 220 }}
                           onChange={(e) => setHaceMin(e.target.value)} helperText="Ventana máx. 60 min">
                  {['0', '10', '20', '30', '45', '60'].map((n) => (
                    <MenuItem key={n} value={n}>{n === '0' ? 'Ahora' : `Hace ${n} min`}</MenuItem>
                  ))}
                </TextField>
              </>
            ) : (
              <>
                <TextField select label="Causa de no-visita" value={causa} required
                           onChange={(e) => setCausa(e.target.value)}>
                  {causas.map((c) => <MenuItem key={c} value={c}>{c}</MenuItem>)}
                </TextField>
                <TextField label="Nota (opcional)" value={comentario} onChange={(e) => setComentario(e.target.value)} />
              </>
            )}

            <Stack direction="row" spacing={1.5}>
              <Button variant="contained" fullWidth startIcon={<Save />} disabled={guardando || !medico} onClick={guardar}>
                {guardando ? 'Guardando…' : (modoNoVisita ? 'Registrar no-visita' : 'Guardar visita')}
              </Button>
              <Button variant="outlined" color={modoNoVisita ? 'primary' : 'warning'} startIcon={<EventBusy />}
                      onClick={() => { setModoNoVisita(!modoNoVisita); setMsg(null); }}>
                {modoNoVisita ? 'Fue visita' : 'No pude'}
              </Button>
            </Stack>
          </Stack>
        </CardContent>
      </Card>
      )}

      {listo && (
        <>
          <Typography variant="subtitle1" fontWeight={700} sx={{ mb: 1 }}>Visitas de hoy ({hoy.length})</Typography>
          {hoy.length === 0 ? (
            <Alert severity="info">Aún no hay visitas registradas hoy.</Alert>
          ) : (
            <Stack spacing={1}>
              {hoy.map((v) => (
                <Card key={v.id} variant="outlined">
                  <CardContent sx={{ py: 1, display: 'flex', alignItems: 'center', gap: 1.5 }}>
                    {v.ejecutada ? <CheckCircle color="success" /> : <Cancel color="disabled" />}
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Typography variant="body2" fontWeight={600}>{v.medico}</Typography>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
                        {v.ejecutada ? (v.comentario || '') : `No-visita: ${v.causa_no_visita}`}
                      </Typography>
                    </Box>
                    <Chip size="small" color={v.ejecutada ? (v.tipo_visita === 'R' ? 'secondary' : 'primary') : 'default'}
                          label={v.ejecutada ? (v.tipo_visita === 'R' ? 'Revisita' : 'Vista') : 'No-visita'} />
                  </CardContent>
                </Card>
              ))}
            </Stack>
          )}
        </>
      )}
    </Box>
  );
}
