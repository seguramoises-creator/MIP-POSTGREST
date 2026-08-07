/**
 * RutasAdmin.tsx — Gestión de rutas de inducción (§4).
 * Crear la ruta estándar de 10 pasos por línea, asignarla y consultar el avance.
 * Los botones «Nueva ruta estándar» (RequireContenido) y «Asignar a un
 * representante» (RequireCapacitacion) se ocultan por lista blanca de rol —
 * en vez de deducir "no es GERENTE_MEDICO" — porque desde que GERENTE_DISTRITO
 * también entra a este tab (para marcar su hito de campo, §4.6) necesitaría
 * quedar fuera de ambos igual que GERENTE_MEDICO queda fuera de «Asignar».
 */
import { useState } from 'react';
import { useMutation } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  CircularProgress, Snackbar,
} from '@mui/material';
import { Add, PersonAdd, Search } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import { useAuthStore } from '../../../store/auth.store';
import {
  crearPlantilla, pasosDePlantilla, asignarRuta, estadoRuta, completarPaso,
  type Paso, type EstadoRuta,
} from '../../../services/onboarding.service';
import ListaPasos from './ListaPasos';

function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

// RequireContenido en el backend — controla el botón «Nueva ruta estándar».
const ROLES_CONTENIDO = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
// RequireCapacitacion en el backend — controla el botón «Asignar a un representante».
const ROLES_CAPACITACION = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION'];

export default function RutasAdmin() {
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const rol = useAuthStore((s) => s.rol);
  const puedeCrear = !!rol && ROLES_CONTENIDO.includes(rol);
  const puedeAsignar = !!rol && ROLES_CAPACITACION.includes(rol);

  const [nueva, setNueva] = useState(false);
  const [asignar, setAsignar] = useState(false);
  const [plantillaId, setPlantillaId] = useState('');
  const [pasos, setPasos] = useState<Paso[] | null>(null);
  const [asignacionId, setAsignacionId] = useState('');
  const [estado, setEstado] = useState<EstadoRuta | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const verPasos = useMutation({
    mutationFn: (id: number) => pasosDePlantilla(id),
    onSuccess: (r) => setPasos(r),
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudieron cargar los pasos.') }),
  });

  const verAsignacion = useMutation({
    mutationFn: (id: number) => estadoRuta(id),
    onSuccess: (r) => setEstado(r),
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo cargar la asignación.') }),
  });

  const completar = useMutation({
    mutationFn: (pasoId: number) => completarPaso(Number(asignacionId), pasoId),
    onSuccess: () => {
      setAviso({ sev: 'success', msg: 'Paso completado.' });
      verAsignacion.mutate(Number(asignacionId));
    },
    // El backend decide si a este rol le toca marcar el paso (§4.6) y devuelve
    // 403 con el motivo; 409 si todavía está bloqueado. Se muestran tal cual.
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo completar el paso.') }),
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" spacing={2} mb={2}>
        {puedeCrear && (
          <Button variant="contained" startIcon={<Add />} onClick={() => setNueva(true)}>
            Nueva ruta estándar
          </Button>
        )}
        {puedeAsignar && (
          <Button variant="outlined" startIcon={<PersonAdd />} onClick={() => setAsignar(true)}>
            Asignar a un representante
          </Button>
        )}
      </Stack>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 3 }}>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Pasos de una plantilla</Typography>
        <Stack direction="row" spacing={1} alignItems="center" mb={2}>
          <TextField size="small" label="ID de plantilla" value={plantillaId}
            onChange={(e) => setPlantillaId(e.target.value)} sx={{ width: 180 }} />
          <Button startIcon={<Search />} disabled={!plantillaId.trim() || verPasos.isPending}
            onClick={() => verPasos.mutate(Number(plantillaId))}>Consultar</Button>
          {verPasos.isPending && <CircularProgress size={20} />}
        </Stack>
        {pasos && (pasos.length === 0 ? (
          <Typography variant="body2" color="text.secondary">Esa plantilla no tiene pasos.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>#</TableCell><TableCell>Título</TableCell><TableCell>Tipo</TableCell>
                <TableCell>Plazo</TableCell><TableCell>Bloqueante</TableCell><TableCell>Lo marca</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {pasos.map((p) => (
                <TableRow key={p.id}>
                  <TableCell>{p.orden}</TableCell>
                  <TableCell>{p.titulo}</TableCell>
                  <TableCell>{p.tipo}</TableCell>
                  <TableCell>{p.plazo_sugerido ?? '—'}</TableCell>
                  <TableCell>
                    <Chip size="small" color={p.bloqueante ? 'warning' : 'default'}
                      label={p.bloqueante ? 'Sí' : 'No'} />
                  </TableCell>
                  <TableCell>{p.quien_lo_marca}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        ))}
      </Paper>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
        <Typography variant="subtitle1" fontWeight={700} mb={1}>Avance de una asignación</Typography>
        <Stack direction="row" spacing={1} alignItems="center" mb={2}>
          <TextField size="small" label="ID de asignación" value={asignacionId}
            onChange={(e) => setAsignacionId(e.target.value)} sx={{ width: 180 }} />
          <Button startIcon={<Search />} disabled={!asignacionId.trim() || verAsignacion.isPending}
            onClick={() => verAsignacion.mutate(Number(asignacionId))}>Consultar</Button>
          {verAsignacion.isPending && <CircularProgress size={20} />}
        </Stack>
        {/* El backend decide quién puede marcar cada paso (§4.6): el botón
            aparece para todos, pero solo funciona si al rol le toca. */}
        {estado && (
          <ListaPasos estado={estado}
            onCompletar={(pasoId) => completar.mutate(pasoId)}
            completando={completar.isPending ? (completar.variables as number) : null} />
        )}
      </Paper>

      <DialogoPlantilla abierto={nueva} paisCodigo={paisCodigo} onClose={() => setNueva(false)}
        onCreada={(r) => {
          setNueva(false); setPasos(r.pasos); setPlantillaId(String(r.id));
          setAviso({ sev: 'success', msg: `Ruta «${r.nombre_plantilla}» creada con ${r.pasos.length} pasos.` });
        }} />

      <DialogoAsignar abierto={asignar} onClose={() => setAsignar(false)}
        onAsignada={(id) => {
          setAsignar(false); setAsignacionId(String(id));
          setAviso({ sev: 'success', msg: `Ruta asignada (asignación #${id}).` });
        }} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoPlantilla({ abierto, paisCodigo, onClose, onCreada }: {
  abierto: boolean; paisCodigo: string; onClose: () => void;
  onCreada: (r: { id: number; nombre_plantilla: string; pasos: Paso[] }) => void;
}) {
  const [nombre, setNombre] = useState('');
  const [lineaId, setLineaId] = useState('');
  const [duracion, setDuracion] = useState('30');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => crearPlantilla({
      pais_codigo: paisCodigo, linea_id: Number(lineaId),
      nombre_plantilla: nombre, duracion_dias: Number(duracion) || 30,
    }),
    onSuccess: (r) => { setNombre(''); setLineaId(''); setError(null); onCreada(r); },
    onError: (e) => setError(detalleError(e, 'No se pudo crear la ruta.')),
  });

  const valido = nombre.trim() && lineaId.trim() && !Number.isNaN(Number(lineaId));

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Nueva ruta estándar</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <Alert severity="info">Se crearán automáticamente los 10 pasos estándar de la ruta.</Alert>
          <TextField label="Nombre de la ruta" value={nombre} onChange={(e) => setNombre(e.target.value)}
            fullWidth required inputProps={{ maxLength: 200 }} />
          <TextField label="ID de línea" value={lineaId} onChange={(e) => setLineaId(e.target.value)}
            fullWidth required />
          <TextField label="Duración (días)" value={duracion} onChange={(e) => setDuracion(e.target.value)}
            fullWidth />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!valido || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Creando…' : 'Crear'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoAsignar({ abierto, onClose, onAsignada }: {
  abierto: boolean; onClose: () => void; onAsignada: (id: number) => void;
}) {
  const [plantilla, setPlantilla] = useState('');
  const [rm, setRm] = useState('');
  const [fecha, setFecha] = useState('');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => asignarRuta({
      plantilla_id: Number(plantilla), rm_id: Number(rm),
      fecha_inicio: fecha || null,
    }),
    onSuccess: (r) => { setPlantilla(''); setRm(''); setFecha(''); setError(null); onAsignada(r.id); },
    onError: (e) => setError(detalleError(e, 'No se pudo asignar la ruta.')),
  });

  const valido = plantilla.trim() && rm.trim()
    && !Number.isNaN(Number(plantilla)) && !Number.isNaN(Number(rm));

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Asignar ruta a un representante</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="ID de plantilla" value={plantilla}
            onChange={(e) => setPlantilla(e.target.value)} fullWidth required />
          <TextField label="ID del representante" value={rm}
            onChange={(e) => setRm(e.target.value)} fullWidth required />
          <TextField label="Fecha de inicio (opcional)" type="date" value={fecha}
            onChange={(e) => setFecha(e.target.value)} fullWidth
            InputLabelProps={{ shrink: true }} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!valido || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Asignando…' : 'Asignar'}</Button>
      </DialogActions>
    </Dialog>
  );
}
