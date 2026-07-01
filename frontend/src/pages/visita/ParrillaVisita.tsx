import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, MenuItem,
  CircularProgress, Table, TableHead, TableRow, TableCell, TableBody, IconButton, Divider,
  LinearProgress, Autocomplete,
} from '@mui/material';
import { Add, Delete, Save, Inventory2, Campaign, LocalPharmacy } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  listarLineasVisita, obtenerParrilla, guardarParrilla, listarMedicos,
  registrarMuestras, muestrasResumen,
  type Catalogo, type ParrillaItem, type MuestrasResumen, type MedicoVisita,
} from '../../services/visita.service';

function msgError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

const filaVacia = (): ParrillaItem => ({ producto: '', mensaje_clave: '', prioridad: 1, meta_muestras: 0 });

export default function ParrillaVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esGestor = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD';
  const esVM = rol === 'REPRESENTANTE_MEDICO';

  const [lineas, setLineas] = useState<Catalogo[]>([]);
  const [lineaId, setLineaId] = useState<number | ''>('');
  const [parrilla, setParrilla] = useState<ParrillaItem[]>([]);
  const [resumen, setResumen] = useState<MuestrasResumen | null>(null);
  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  // Registro de muestras (solo VM)
  const [medicoSel, setMedicoSel] = useState<number | ''>('');
  const [entregas, setEntregas] = useState<{ producto: string; cantidad: number }[]>([{ producto: '', cantidad: 1 }]);

  const cargarParrilla = useCallback((lid?: number) => {
    obtenerParrilla(lid).then(setParrilla).catch(() => setParrilla([]));
  }, []);

  useEffect(() => {
    const tareas: Promise<unknown>[] = [muestrasResumen().then(setResumen).catch(() => setResumen(null))];
    if (esGestor) {
      tareas.push(listarLineasVisita().then((ls) => {
        setLineas(ls);
        if (ls.length) { setLineaId(ls[0].id); cargarParrilla(ls[0].id); }
      }).catch(() => {}));
    } else {
      tareas.push(Promise.resolve(cargarParrilla()));           // VM: su propia línea
      if (esVM) tareas.push(listarMedicos().then(setMedicos).catch(() => {}));
    }
    Promise.all(tareas).finally(() => setCargando(false));
  }, [esGestor, esVM, cargarParrilla]);

  const onLinea = (v: number) => { setLineaId(v); cargarParrilla(v); };

  // ── Edición de parrilla (gestor) ──
  const setCampo = (i: number, campo: keyof ParrillaItem, valor: string | number) =>
    setParrilla((p) => p.map((it, idx) => idx === i ? { ...it, [campo]: valor } : it));
  const addFila = () => setParrilla((p) => [...p, filaVacia()]);
  const delFila = (i: number) => setParrilla((p) => p.filter((_, idx) => idx !== i));

  async function guardar() {
    if (!lineaId) { setMsg({ tipo: 'error', texto: 'Selecciona la línea.' }); return; }
    const items = parrilla.filter((p) => p.producto.trim());
    setGuardando(true); setMsg(null);
    try {
      const r = await guardarParrilla(Number(lineaId), items);
      setMsg({ tipo: 'success', texto: `Parrilla guardada (${r.guardados} productos).` });
      cargarParrilla(Number(lineaId));
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudo guardar la parrilla.') });
    } finally { setGuardando(false); }
  }

  // ── Registro de muestras (VM) ──
  const productosParrilla = parrilla.map((p) => p.producto);
  const setEntrega = (i: number, campo: 'producto' | 'cantidad', v: string | number) =>
    setEntregas((e) => e.map((it, idx) => idx === i ? { ...it, [campo]: v } : it));
  const addEntrega = () => setEntregas((e) => [...e, { producto: '', cantidad: 1 }]);
  const delEntrega = (i: number) => setEntregas((e) => e.filter((_, idx) => idx !== i));

  async function guardarMuestras() {
    if (!medicoSel) { setMsg({ tipo: 'error', texto: 'Selecciona el médico.' }); return; }
    const items = entregas.filter((e) => e.producto.trim() && e.cantidad > 0)
                          .map((e) => ({ producto: e.producto.trim(), cantidad: Number(e.cantidad) }));
    if (!items.length) { setMsg({ tipo: 'error', texto: 'Agrega al menos un producto.' }); return; }
    setGuardando(true); setMsg(null);
    try {
      const r = await registrarMuestras(Number(medicoSel), items);
      setMsg({ tipo: 'success', texto: `${r.registradas} muestra(s) registrada(s).` });
      setMedicoSel(''); setEntregas([{ producto: '', cantidad: 1 }]);
      muestrasResumen().then(setResumen).catch(() => {});
    } catch (e) {
      setMsg({ tipo: 'error', texto: msgError(e, 'No se pudieron registrar las muestras.') });
    } finally { setGuardando(false); }
  }

  if (cargando) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Campaign color="primary" />
        <Typography variant="h5" fontWeight={700}>Parrilla Promocional & Muestras</Typography>
      </Stack>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
        Productos a promover en el ciclo y muestras entregadas frente a la meta.
      </Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* Parrilla */}
      <Card variant="outlined" sx={{ mb: 3 }}>
        <CardContent>
          <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }} flexWrap="wrap">
            <Inventory2 fontSize="small" color="action" />
            <Typography variant="subtitle1" fontWeight={700}>Parrilla del ciclo</Typography>
            <Box sx={{ flex: 1 }} />
            {esGestor && (
              <TextField select size="small" label="Línea" value={lineaId} sx={{ minWidth: 200 }}
                         onChange={(e) => onLinea(Number(e.target.value))}>
                {lineas.map((l) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
              </TextField>
            )}
          </Stack>

          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell width={70} align="center">Prior.</TableCell>
                <TableCell>Producto</TableCell>
                <TableCell>Mensaje clave</TableCell>
                <TableCell width={110} align="center">Meta muestras</TableCell>
                {esGestor && <TableCell width={48} />}
              </TableRow></TableHead>
              <TableBody>
                {parrilla.length === 0 && (
                  <TableRow><TableCell colSpan={esGestor ? 5 : 4}>
                    <Typography variant="body2" color="text.secondary" sx={{ py: 1 }}>
                      {esGestor ? 'Sin productos. Agrega filas y guarda.' : 'La parrilla de tu línea aún no está configurada.'}
                    </Typography>
                  </TableCell></TableRow>
                )}
                {parrilla.map((it, i) => (
                  <TableRow key={it.id ?? `n${i}`}>
                    <TableCell align="center">
                      {esGestor ? (
                        <TextField size="small" type="number" value={it.prioridad} sx={{ width: 60 }}
                                   inputProps={{ min: 1, max: 20 }}
                                   onChange={(e) => setCampo(i, 'prioridad', Number(e.target.value))} />
                      ) : <Chip size="small" label={it.prioridad} />}
                    </TableCell>
                    <TableCell>
                      {esGestor ? (
                        <TextField size="small" fullWidth value={it.producto} placeholder="Producto"
                                   onChange={(e) => setCampo(i, 'producto', e.target.value)} />
                      ) : <Typography variant="body2" fontWeight={600}>{it.producto}</Typography>}
                    </TableCell>
                    <TableCell>
                      {esGestor ? (
                        <TextField size="small" fullWidth value={it.mensaje_clave ?? ''} placeholder="Mensaje clave"
                                   onChange={(e) => setCampo(i, 'mensaje_clave', e.target.value)} />
                      ) : <Typography variant="body2" color="text.secondary">{it.mensaje_clave || '—'}</Typography>}
                    </TableCell>
                    <TableCell align="center">
                      {esGestor ? (
                        <TextField size="small" type="number" value={it.meta_muestras} sx={{ width: 90 }}
                                   inputProps={{ min: 0 }}
                                   onChange={(e) => setCampo(i, 'meta_muestras', Number(e.target.value))} />
                      ) : (it.meta_muestras || '—')}
                    </TableCell>
                    {esGestor && (
                      <TableCell><IconButton size="small" color="error" onClick={() => delFila(i)}><Delete fontSize="small" /></IconButton></TableCell>
                    )}
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>

          {esGestor && (
            <Stack direction="row" spacing={1.5} sx={{ mt: 1.5 }}>
              <Button size="small" startIcon={<Add />} onClick={addFila}>Agregar producto</Button>
              <Button size="small" variant="contained" startIcon={<Save />} disabled={guardando} onClick={guardar}>
                {guardando ? 'Guardando…' : 'Guardar parrilla'}
              </Button>
            </Stack>
          )}
        </CardContent>
      </Card>

      {/* Registro de muestras (solo VM) */}
      {esVM && (
        <Card variant="outlined" sx={{ mb: 3 }}>
          <CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}>
              <LocalPharmacy fontSize="small" color="action" />
              <Typography variant="subtitle1" fontWeight={700}>Registrar muestras entregadas</Typography>
            </Stack>
            <Stack spacing={2}>
              <TextField select label="Médico" value={medicoSel} sx={{ maxWidth: 420 }} required
                         onChange={(e) => setMedicoSel(e.target.value === '' ? '' : Number(e.target.value))}>
                {medicos.length === 0 && <MenuItem value="" disabled>No hay médicos en tu panel</MenuItem>}
                {medicos.map((m) => <MenuItem key={m.id} value={m.id}>{m.nombre_completo} · Cat. {m.categoria}</MenuItem>)}
              </TextField>

              {entregas.map((e, i) => (
                <Stack key={i} direction="row" spacing={1.5} alignItems="center">
                  <Autocomplete freeSolo options={productosParrilla} value={e.producto} sx={{ flex: 1, maxWidth: 320 }}
                                onInputChange={(_, v) => setEntrega(i, 'producto', v)}
                                renderInput={(p) => <TextField {...p} size="small" label="Producto" placeholder="De la parrilla o libre" />} />
                  <TextField size="small" type="number" label="Cantidad" value={e.cantidad} sx={{ width: 110 }}
                             inputProps={{ min: 1 }} onChange={(ev) => setEntrega(i, 'cantidad', Number(ev.target.value))} />
                  <IconButton size="small" color="error" disabled={entregas.length === 1} onClick={() => delEntrega(i)}>
                    <Delete fontSize="small" />
                  </IconButton>
                </Stack>
              ))}
              <Stack direction="row" spacing={1.5}>
                <Button size="small" startIcon={<Add />} onClick={addEntrega}>Otro producto</Button>
                <Button size="small" variant="contained" startIcon={<Save />} disabled={guardando} onClick={guardarMuestras}>
                  {guardando ? 'Guardando…' : 'Registrar muestras'}
                </Button>
              </Stack>
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Resumen de muestras */}
      <Divider sx={{ my: 2 }} />
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
        <Inventory2 color="primary" />
        <Typography variant="h6" fontWeight={700}>Muestras entregadas</Typography>
        {resumen && <Chip size="small" label={`${resumen.total_entregadas} uds`} color="primary" />}
      </Stack>
      {!resumen || resumen.productos.length === 0 ? (
        <Alert severity="info">Aún no hay muestras registradas ni metas de parrilla.</Alert>
      ) : (
        <Card variant="outlined">
          <Box sx={{ overflowX: 'auto' }}>
            <Table size="small">
              <TableHead><TableRow>
                <TableCell>Producto</TableCell>
                <TableCell align="center">Entregadas</TableCell>
                <TableCell align="center">Médicos</TableCell>
                <TableCell align="center">Meta</TableCell>
                <TableCell width={180}>Cobertura vs meta</TableCell>
              </TableRow></TableHead>
              <TableBody>
                {resumen.productos.map((p) => (
                  <TableRow key={p.producto} hover>
                    <TableCell>
                      <Typography variant="body2" fontWeight={600}>{p.producto}</Typography>
                      {!p.en_parrilla && <Chip size="small" variant="outlined" color="warning" label="fuera de parrilla" sx={{ mt: 0.3 }} />}
                    </TableCell>
                    <TableCell align="center">{p.entregadas}</TableCell>
                    <TableCell align="center">{p.medicos_alcanzados}</TableCell>
                    <TableCell align="center">{p.meta || '—'}</TableCell>
                    <TableCell>
                      {p.cobertura_meta_pct === null ? (
                        <Typography variant="caption" color="text.secondary">sin meta</Typography>
                      ) : (
                        <Stack spacing={0.3}>
                          <LinearProgress variant="determinate" value={p.cobertura_meta_pct}
                                          color={p.cobertura_meta_pct >= 100 ? 'success' : p.cobertura_meta_pct >= 60 ? 'primary' : 'warning'} />
                          <Typography variant="caption" color="text.secondary">{p.cobertura_meta_pct}%</Typography>
                        </Stack>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </Box>
        </Card>
      )}
    </Box>
  );
}
