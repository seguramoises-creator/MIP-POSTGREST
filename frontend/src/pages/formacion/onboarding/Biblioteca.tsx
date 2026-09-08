/**
 * Biblioteca.tsx — Material de formación (§5).
 * El representante solo ve lo APROBADO por Gerencia Médica: lo filtra el backend
 * según el rol (firewall PhRMA), no esta pantalla.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Paper, Typography, Button, Stack, Alert, Chip, Table, TableHead, TableBody,
  TableRow, TableCell, Dialog, DialogTitle, DialogContent, DialogActions, TextField,
  MenuItem, FormControl, InputLabel, Select, CircularProgress, Snackbar,
  FormControlLabel, Switch, Link,
} from '@mui/material';
import { Add, CheckCircle, Visibility, DoneAll } from '@mui/icons-material';
import { useCicloStore } from '../../../store/ciclo.store';
import { useAuthStore } from '../../../store/auth.store';
import {
  listarMateriales, subirMaterial, aprobarMaterial, confirmarLectura,
  confirmacionesDeMaterial, TIPOS_MATERIAL,
  type Material, type TipoMaterial,
} from '../../../services/onboarding.service';

function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

const ROLES_CONTENIDO = ['ADMIN', 'GERENTE_PRODUCTIVIDAD', 'CAPACITACION', 'GERENTE_MEDICO'];
const ROLES_APRUEBA = ['ADMIN', 'GERENTE_MEDICO'];

export default function Biblioteca() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const rol = useAuthStore((s) => s.rol);
  const esRM = rol === 'REPRESENTANTE_MEDICO';
  const puedeSubir = !!rol && ROLES_CONTENIDO.includes(rol);
  const puedeAprobar = !!rol && ROLES_APRUEBA.includes(rol);

  const [productoId, setProductoId] = useState<string>('');
  const [subir, setSubir] = useState(false);
  const [verConfirmaciones, setVerConfirmaciones] = useState<Material | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const filtroProducto = productoId.trim() && !Number.isNaN(Number(productoId))
    ? Number(productoId) : undefined;

  const materiales = useQuery({
    queryKey: ['onb-biblioteca', paisCodigo, filtroProducto],
    queryFn: () => listarMateriales(paisCodigo as string, filtroProducto),
    enabled: !!paisCodigo,
  });
  const invalidar = () => qc.invalidateQueries({ queryKey: ['onb-biblioteca'] });

  const aprobar = useMutation({
    mutationFn: (id: number) => aprobarMaterial(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Material aprobado.' }),
    onError: (e) => setAviso({ sev: 'error', msg: detalleError(e, 'No se pudo aprobar.') }),
    onSettled: invalidar,
  });

  const confirmar = useMutation({
    mutationFn: (id: number) => confirmarLectura(id),
    onSuccess: () => setAviso({ sev: 'success', msg: 'Lectura confirmada.' }),
    // 409 = material sin aprobar: no se puede confirmar lo que no pasó el firewall.
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo confirmar la lectura.') }),
    onSettled: invalidar,
  });

  if (!paisCodigo) return <Alert severity="info">Selecciona un país en el encabezado.</Alert>;

  return (
    <Box>
      <Stack direction="row" spacing={2} alignItems="center" mb={2}>
        <TextField size="small" label="Filtrar por producto (id)" value={productoId}
          onChange={(e) => setProductoId(e.target.value)} sx={{ width: 220 }} />
        <Box sx={{ flex: 1 }} />
        {puedeSubir && (
          <Button variant="contained" startIcon={<Add />} onClick={() => setSubir(true)}>
            Subir material
          </Button>
        )}
      </Stack>

      {materiales.isLoading ? <CircularProgress /> : materiales.isError ? (
        <Alert severity="warning">No se pudo cargar la biblioteca.</Alert>
      ) : (
        <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
          <Table size="small">
            <TableHead>
              <TableRow>
                <TableCell>Título</TableCell><TableCell>Tipo</TableCell>
                <TableCell>Obligatorio</TableCell><TableCell>Aprobación</TableCell>
                <TableCell align="right">Acciones</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {(materiales.data || []).length === 0 ? (
                <TableRow><TableCell colSpan={5}>
                  <Typography variant="body2" color="text.secondary">Sin material para este filtro.</Typography>
                </TableCell></TableRow>
              ) : (materiales.data || []).map((m) => (
                <TableRow key={m.id}>
                  <TableCell>
                    <Link href={m.archivo_url} target="_blank" rel="noopener noreferrer">{m.titulo}</Link>
                  </TableCell>
                  <TableCell>{m.tipo}</TableCell>
                  <TableCell>
                    <Chip size="small" color={m.obligatorio ? 'primary' : 'default'}
                      label={m.obligatorio ? 'Obligatorio' : 'Opcional'} />
                  </TableCell>
                  <TableCell>
                    <Chip size="small" color={m.aprobado_por_gm ? 'success' : 'default'}
                      label={m.aprobado_por_gm ? 'Aprobado' : 'Pendiente de aprobación'} />
                  </TableCell>
                  <TableCell align="right">
                    {puedeAprobar && !m.aprobado_por_gm && (
                      <Button size="small" startIcon={<CheckCircle />}
                        disabled={aprobar.isPending && aprobar.variables === m.id}
                        onClick={() => aprobar.mutate(m.id)}>Aprobar</Button>
                    )}
                    {esRM && (
                      <Button size="small" startIcon={<DoneAll />}
                        disabled={confirmar.isPending && confirmar.variables === m.id}
                        onClick={() => confirmar.mutate(m.id)}>Confirmar lectura</Button>
                    )}
                    {puedeSubir && (
                      <Button size="small" startIcon={<Visibility />}
                        onClick={() => setVerConfirmaciones(m)}>Quién confirmó</Button>
                    )}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </Paper>
      )}

      <DialogoMaterial abierto={subir} paisCodigo={paisCodigo}
        onClose={() => setSubir(false)}
        onCreado={() => { setSubir(false); invalidar(); setAviso({ sev: 'success', msg: 'Material subido.' }); }} />

      <DialogoConfirmaciones material={verConfirmaciones} onClose={() => setVerConfirmaciones(null)} />

      <Snackbar open={!!aviso} autoHideDuration={6000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}

function DialogoMaterial({ abierto, paisCodigo, onClose, onCreado }: {
  abierto: boolean; paisCodigo: string; onClose: () => void; onCreado: () => void;
}) {
  const [titulo, setTitulo] = useState('');
  const [tipo, setTipo] = useState<TipoMaterial>('manual');
  const [url, setUrl] = useState('');
  const [producto, setProducto] = useState('');
  const [obligatorio, setObligatorio] = useState(true);   // §5.3: activado por defecto
  const [error, setError] = useState<string | null>(null);

  const crear = useMutation({
    mutationFn: () => subirMaterial({
      pais_codigo: paisCodigo, titulo, tipo, archivo_url: url,
      producto_id: producto.trim() && !Number.isNaN(Number(producto)) ? Number(producto) : null,
      obligatorio,
    }),
    onSuccess: () => {
      setTitulo(''); setUrl(''); setProducto(''); setTipo('manual');
      setObligatorio(true); setError(null); onCreado();
    },
    onError: (e) => setError(detalleError(e, 'No se pudo subir el material.')),
  });

  return (
    <Dialog open={abierto} onClose={onClose} maxWidth="sm" fullWidth>
      <DialogTitle>Subir material</DialogTitle>
      <DialogContent>
        <Stack spacing={2} sx={{ mt: 1 }}>
          {error && <Alert severity="error">{error}</Alert>}
          <TextField label="Título" value={titulo} onChange={(e) => setTitulo(e.target.value)}
            fullWidth required inputProps={{ maxLength: 250 }} />
          <FormControl fullWidth>
            <InputLabel>Tipo</InputLabel>
            <Select label="Tipo" value={tipo} onChange={(e) => setTipo(e.target.value as TipoMaterial)}>
              {TIPOS_MATERIAL.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
            </Select>
          </FormControl>
          <TextField label="URL del archivo" value={url} onChange={(e) => setUrl(e.target.value)}
            fullWidth required />
          <TextField label="Producto (id, opcional)" value={producto}
            onChange={(e) => setProducto(e.target.value)} fullWidth />
          <FormControlLabel control={
            <Switch checked={obligatorio} onChange={(e) => setObligatorio(e.target.checked)} />
          } label="Lectura obligatoria" />
        </Stack>
      </DialogContent>
      <DialogActions>
        <Button onClick={onClose}>Cancelar</Button>
        <Button variant="contained" disabled={!titulo.trim() || !url.trim() || crear.isPending}
          onClick={() => crear.mutate()}>{crear.isPending ? 'Subiendo…' : 'Subir'}</Button>
      </DialogActions>
    </Dialog>
  );
}

function DialogoConfirmaciones({ material, onClose }: {
  material: Material | null; onClose: () => void;
}) {
  const datos = useQuery({
    queryKey: ['onb-confirmaciones', material?.id],
    queryFn: () => confirmacionesDeMaterial(material!.id),
    enabled: !!material,
  });

  return (
    <Dialog open={!!material} onClose={onClose} maxWidth="xs" fullWidth>
      <DialogTitle>Confirmaciones de «{material?.titulo}»</DialogTitle>
      <DialogContent>
        {datos.isLoading ? <CircularProgress /> : (datos.data || []).length === 0 ? (
          <Typography variant="body2" color="text.secondary">Nadie ha confirmado todavía.</Typography>
        ) : (
          <Table size="small">
            <TableHead>
              <TableRow><TableCell>RM</TableCell><TableCell>Confirmado</TableCell></TableRow>
            </TableHead>
            <TableBody>
              {(datos.data || []).map((c) => (
                <TableRow key={`${c.rm_id}-${c.confirmado_en}`}>
                  <TableCell>#{c.rm_id}</TableCell>
                  <TableCell>{new Date(c.confirmado_en).toLocaleString()}</TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        )}
      </DialogContent>
      <DialogActions><Button onClick={onClose}>Cerrar</Button></DialogActions>
    </Dialog>
  );
}
