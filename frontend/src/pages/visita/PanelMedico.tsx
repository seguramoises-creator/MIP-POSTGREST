import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert,
  Table, TableHead, TableRow, TableCell, TableBody, MenuItem, Dialog, DialogTitle,
  DialogContent, DialogActions, CircularProgress,
} from '@mui/material';
import { Add, PersonAddAlt1, Warning } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarMedicos, listarEspecialidades, listarVMs, crearMedico,
  type MedicoVisita, type Catalogo, type PosibleDuplicado, type MedicoCrear,
} from '../../services/visita.service';

const CAT_COLOR: Record<string, 'success' | 'primary' | 'warning'> = { A: 'success', B: 'primary', C: 'warning' };
const TIPOS = ['Clínica privada', 'Hospital público', 'Hospital privado', 'Consultorio independiente'];

const vacio: MedicoCrear = { vm_id: 0, nombre_completo: '', especialidad_id: null, categoria: 'A', tipo_consultorio: '', direccion: '', telefono: '' };

export default function PanelMedico() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';

  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [especialidades, setEspecialidades] = useState<Catalogo[]>([]);
  const [vms, setVms] = useState<Catalogo[]>([]);
  const [vmFiltro, setVmFiltro] = useState<number | ''>('');
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

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Panel Médico — Visita</Typography>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Catálogo de médicos del universo de visita.
      </Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Stack direction="row" spacing={1.5} sx={{ mb: 2, flexWrap: 'wrap' }} alignItems="center">
        {!esVM && (
          <TextField select size="small" label="Visitador (VM)" value={vmFiltro} sx={{ minWidth: 240 }}
                     onChange={(e) => setVmFiltro(e.target.value === '' ? '' : Number(e.target.value))}>
            <MenuItem value="">Todos</MenuItem>
            {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
          </TextField>
        )}
        <Button variant="contained" startIcon={<PersonAddAlt1 />} onClick={abrirNuevo}>Nuevo médico</Button>
        <Chip label={`${medicos.length} médicos`} variant="outlined" />
      </Stack>

      <Card variant="outlined">
        <CardContent sx={{ p: 0 }}>
          {cargando ? (
            <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
          ) : medicos.length === 0 ? (
            <Alert severity="info" sx={{ m: 2 }}>No hay médicos en el panel. Agrega el primero con "Nuevo médico".</Alert>
          ) : (
            <Table size="small" sx={{ '& thead th': { fontWeight: 700, bgcolor: 'rgba(26,35,126,0.04)' } }}>
              <TableHead><TableRow>
                <TableCell>Nombre</TableCell><TableCell>Especialidad</TableCell>
                <TableCell align="center">Cat.</TableCell><TableCell>Consultorio</TableCell>
                <TableCell>Dirección</TableCell><TableCell align="center">Ciclos sin visita</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {medicos.map((m) => {
                  const ruptura = m.ciclos_sin_visita >= 3;
                  return (
                    <TableRow key={m.id} hover sx={ruptura ? { bgcolor: 'rgba(244,67,54,0.06)' } : undefined}>
                      <TableCell sx={{ fontWeight: 600 }}>{m.nombre_completo}</TableCell>
                      <TableCell>{m.especialidad_nombre || '—'}</TableCell>
                      <TableCell align="center">
                        <Chip size="small" color={CAT_COLOR[m.categoria] || 'default'} label={m.categoria} />
                      </TableCell>
                      <TableCell>{m.tipo_consultorio || '—'}</TableCell>
                      <TableCell sx={{ maxWidth: 240, whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>{m.direccion || '—'}</TableCell>
                      <TableCell align="center">
                        {m.ciclos_sin_visita === 0 ? (
                          <Chip size="small" color="success" variant="outlined" label="Al día" />
                        ) : (
                          <Chip size="small" color={ruptura ? 'error' : m.ciclos_sin_visita === 2 ? 'warning' : 'default'}
                                label={ruptura ? `🔴 ${m.ciclos_sin_visita} — Ruptura` : `${m.ciclos_sin_visita}`} />
                        )}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Alta de médico */}
      <Dialog open={abierto} onClose={() => !guardando && setAbierto(false)} maxWidth="sm" fullWidth>
        <DialogTitle><Add sx={{ verticalAlign: 'middle', mr: 1 }} />Nuevo médico</DialogTitle>
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
