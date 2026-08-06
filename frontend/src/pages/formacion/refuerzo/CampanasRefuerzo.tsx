/**
 * CampanasRefuerzo.tsx — Tab de Capacitación (§10.2-§10.4).
 * VISTA sugiere el calendario; nada sale publicado hasta que alguien lo
 * confirma y publica explícitamente (§10.3).
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions,
  TextField, MenuItem, FormControl, InputLabel, Select, CircularProgress, Snackbar,
} from '@mui/material';
import { Add, CalendarMonth, Publish, Check } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import {
  listarCampanas, crearCampana, generarCalendario, programarRonda,
  agregarCapsula, publicarRonda,
  DURACIONES, MODOS_ESPACIADO, FORMATOS,
  type Campana, type Ronda, type ModoEspaciado, type FormatoCapsula,
} from '../../../services/refuerzo.service';

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o string.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

export default function CampanasRefuerzo() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const [sel, setSel] = useState<Campana | null>(null);
  const [rondas, setRondas] = useState<Ronda[]>([]);
  const [nueva, setNueva] = useState(false);
  const [capsulaEn, setCapsulaEn] = useState<Ronda | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const campanas = useQuery({
    queryKey: ['refuerzo-campanas', paisCodigo],
    queryFn: () => listarCampanas(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const calendario = useMutation({
    mutationFn: (campanaId: number) => generarCalendario(campanaId),
    onSuccess: (r) => { setRondas(r); setAviso({ sev: 'success', msg: `${r.length} ronda(s) sugeridas.` }); },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo generar el calendario.') }),
  });

  const confirmar = useMutation({
    mutationFn: (rondaId: number) => programarRonda(rondaId),
    onSuccess: (r) => {
      setRondas((prev) => prev.map((x) => x.id === r.id
        ? { ...x, fecha_hora_programada: r.fecha_hora_programada } : x));
      setAviso({ sev: 'success', msg: 'Ronda confirmada.' });
    },
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo confirmar.') }),
  });

  const publicar = useMutation({
    mutationFn: (rondaId: number) => publicarRonda(rondaId),
    onSuccess: (r) => {
      setRondas((prev) => prev.map((x) => x.id === r.id ? { ...x, publicada: r.publicada } : x));
      setAviso({ sev: 'success', msg: 'Ronda publicada y notificada.' });
    },
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo publicar la ronda.') }),
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" alignItems="center" mb={2}>
        <Typography variant="subtitle1" fontWeight={700} sx={{ flex: 1 }}>Campañas de {paisCodigo}</Typography>
        <Button variant="contained" startIcon={<Add />} onClick={() => setNueva(true)}>Nueva campaña</Button>
      </Stack>

      {campanas.isLoading ? <CircularProgress /> : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 3 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Nombre</TableCell><TableCell>Duración</TableCell>
                <TableCell>Espaciado</TableCell><TableCell>Estado</TableCell>
                <TableCell>GM</TableCell><TableCell align="right">Rondas</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(campanas.data || []).length === 0 ? (
                <TableRow><TableCell colSpan={6}>
                  <Typography variant="body2" color="text.secondary">Sin campañas en este país.</Typography>
                </TableCell></TableRow>
              ) : (campanas.data || []).map((c) => (
                <TableRow key={c.id} selected={sel?.id === c.id}>
                  <TableCell>{c.nombre}</TableCell>
                  <TableCell>{c.duracion_dias} días</TableCell>
                  <TableCell>{c.modo_espaciado}</TableCell>
                  <TableCell><Chip size="small" label={c.estado} /></TableCell>
                  <TableCell>
                    <Chip size="small" color={c.aprobado_por_gm ? 'success' : 'default'}
                      label={c.aprobado_por_gm ? 'Aprobada' : 'Sin aprobar'} />
                  </TableCell>
                  <TableCell align="right">
                    <Button size="small" startIcon={<CalendarMonth />}
                      onClick={() => { setSel(c); setRondas([]); calendario.mutate(c.id); }}
                      disabled={calendario.isPending}>Calendario</Button>
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      {sel && (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2 }}>
          <Typography variant="subtitle1" fontWeight={700} mb={1}>Rondas de «{sel.nombre}»</Typography>
          {rondas.length === 0 ? (
            <Typography variant="body2" color="text.secondary">
              Pulsa «Calendario» para generar las rondas sugeridas.
            </Typography>
          ) : (
            <Table size="small">
              <TableHead>
                <TableRow>
                  <TableCell>#</TableCell><TableCell>Sugerida</TableCell>
                  <TableCell>Programada</TableCell><TableCell>Estado</TableCell>
                  <TableCell align="right">Acciones</TableCell>
                </TableRow>
              </TableHead>
              <TableBody>
                {rondas.map((r) => (
                  <TableRow key={r.id}>
                    <TableCell>{r.numero_ronda}</TableCell>
                    <TableCell>{r.fecha_hora_sugerida ? new Date(r.fecha_hora_sugerida).toLocaleString() : '—'}</TableCell>
                    <TableCell>{r.fecha_hora_programada ? new Date(r.fecha_hora_programada).toLocaleString() : '—'}</TableCell>
                    <TableCell>
                      <Chip size="small" color={r.publicada ? 'success' : 'default'}
                        label={r.publicada ? 'Publicada' : 'Borrador'} />
                    </TableCell>
                    <TableCell align="right">
                      <Button size="small" startIcon={<Check />} onClick={() => confirmar.mutate(r.id)}
                        disabled={confirmar.isPending || r.publicada}>Confirmar</Button>
                      <Button size="small" startIcon={<Add />} onClick={() => setCapsulaEn(r)}
                        disabled={r.publicada}>Cápsula</Button>
                      <Button size="small" startIcon={<Publish />} onClick={() => publicar.mutate(r.id)}
                        disabled={publicar.isPending || r.publicada}>Publicar</Button>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </Paper>
      )}

      <DialogoCampana abierto={nueva} paisCodigo={paisCodigo}
        onClose={() => setNueva(false)}
        onCreada={() => { setNueva(false); qc.invalidateQueries({ queryKey: ['refuerzo-campanas', paisCodigo] }); setAviso({ sev: 'success', msg: 'Campaña creada.' }); }} />

      <DialogoCapsula ronda={capsulaEn} onClose={() => setCapsulaEn(null)}
        onCreada={() => { setCapsulaEn(null); setAviso({ sev: 'success', msg: 'Cápsula agregada.' }); }} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoCampana({ abierto, paisCodigo, onClose, onCreada }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onCreada: () => void;
}) {
  const [nombre, setNombre] = useState('');
  const [duracion, setDuracion] = useState(30);
  const [modo, setModo] = useState<ModoEspaciado>('creciente');
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => crearCampana({ pais_codigo: paisCodigo, nombre, duracion_dias: duracion, modo_espaciado: modo }),
    onSuccess: () => { setNombre(''); setError(null); onCreada(); },
    onError: (e) => setError(detalleError(e, 'No se pudo crear la campaña.')),
  });

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Nueva campaña de Refuerzo</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Nombre" value={nombre} onChange={(e) => setNombre(e.target.value)}
            fullWidth required inputProps={{ maxLength: 200 }} />
          <FormControl fullWidth>
            <InputLabel>Duración</InputLabel>
            <Select label="Duración" value={duracion} onChange={(e) => setDuracion(Number(e.target.value))}>
              {DURACIONES.map((d) => <MenuItem key={d} value={d}>{d} días</MenuItem>)}
            </Select>
          </FormControl>
          <FormControl fullWidth>
            <InputLabel>Modo de espaciado</InputLabel>
            <Select label="Modo de espaciado" value={modo} onChange={(e) => setModo(e.target.value as ModoEspaciado)}>
              {MODOS_ESPACIADO.map((m) => <MenuItem key={m} value={m}>{m}</MenuItem>)}
            </Select>
          </FormControl>
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!nombre.trim() || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Creando…' : 'Crear'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoCapsula({ ronda, onClose, onCreada }: {
  ronda: Ronda | null; onClose: () => void; onCreada: () => void;
}) {
  const [formato, setFormato] = useState<FormatoCapsula>('microlectura');
  const [enunciado, setEnunciado] = useState('');
  const [orden, setOrden] = useState(1);
  const [opcionesTxt, setOpcionesTxt] = useState('A: \nB: ');
  const [correcta, setCorrecta] = useState('');
  const [explicacion, setExplicacion] = useState('');
  const [error, setError] = useState<string | null>(null);

  const esReto = formato === 'reto';

  // "A: texto" por línea → {A: "texto"}. Formato simple y explícito para el
  // usuario; el backend espera un objeto clave→texto.
  const parseOpciones = (): Record<string, string> => {
    const out: Record<string, string> = {};
    opcionesTxt.split('\n').forEach((linea) => {
      const i = linea.indexOf(':');
      if (i > 0) {
        const k = linea.slice(0, i).trim();
        const v = linea.slice(i + 1).trim();
        if (k && v) out[k] = v;
      }
    });
    return out;
  };

  const crear = useMutation({
    mutationFn: () => agregarCapsula(ronda!.id, {
      formato, enunciado, orden,
      opciones: esReto ? parseOpciones() : null,
      opcion_correcta: esReto ? correcta.trim() : null,
      explicacion: explicacion || null,
    }),
    onSuccess: () => { setEnunciado(''); setCorrecta(''); setError(null); onCreada(); },
    onError: (e) => setError(detalleError(e, 'No se pudo agregar la cápsula.')),
  });

  // El backend rechaza un reto sin correcta (422): se exige antes de enviar.
  const opciones = esReto ? parseOpciones() : {};
  const puedeGuardar = enunciado.trim() &&
    (!esReto || (correcta.trim() && Object.keys(opciones).length >= 2 && opciones[correcta.trim()] !== undefined));

  return (
    <Dialog open={!!ronda} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Agregar cápsula {ronda ? `a la ronda ${ronda.numero_ronda}` : ''}</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <FormControl fullWidth>
            <InputLabel>Formato</InputLabel>
            <Select label="Formato" value={formato} onChange={(e) => setFormato(e.target.value as FormatoCapsula)}>
              {FORMATOS.map((f) => <MenuItem key={f} value={f}>{f}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField label="Enunciado" value={enunciado} onChange={(e) => setEnunciado(e.target.value)}
            fullWidth required multiline minRows={2} />
          <TextField label="Orden" type="number" value={orden}
            onChange={(e) => setOrden(Number(e.target.value) || 1)} fullWidth />
          {esReto && (
            <>
              <TextField label="Opciones (una por línea, formato «A: texto»)" value={opcionesTxt}
                onChange={(e) => setOpcionesTxt(e.target.value)} fullWidth multiline minRows={3} />
              <TextField label="Opción correcta (la clave, ej. A)" value={correcta}
                onChange={(e) => setCorrecta(e.target.value)} fullWidth required
                helperText="Un reto necesita su opción correcta para corregirse al instante." />
            </>
          )}
          <TextField label="Explicación (opcional)" value={explicacion}
            onChange={(e) => setExplicacion(e.target.value)} fullWidth multiline minRows={2} />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!puedeGuardar || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Guardando…' : 'Agregar'}</Button>
      </DialogActions>
    </Dialog>
  );
}
