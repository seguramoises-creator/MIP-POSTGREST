/**
 * LsiiAdmin.tsx — Administración de la Matriz LSII (Liderazgo Situacional II)
 *
 * Permite a un ADMIN / GERENTE_PRODUCTIVIDAD, sin tocar la base de datos:
 *  - Editar el umbral de corte D1-D4 (eje Desempeño / eje Receptividad)
 *  - Crear, editar y desactivar dimensiones de Receptividad/Compromiso
 *  - Editar el texto visible, el puntaje oculto y el peso de cada opción
 *
 * Importante: estos endpoints (/lsii/admin/*) SÍ devuelven score_oculto y
 * peso_dimension — a diferencia de /lsii/catalogo, que es la vista del GD
 * evaluador y nunca expone esos campos.
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, TextField, Button, Alert,
  CircularProgress, Accordion, AccordionSummary, AccordionDetails, Chip,
  IconButton, Switch, FormControlLabel, Divider, Tooltip as MuiTooltip,
} from '@mui/material';
import {
  ExpandMore, Add, Delete, Save, Refresh, VisibilityOff, Lock,
} from '@mui/icons-material';
import { api } from '../../services/api';
import type { ReceptividadDimensionAdmin, ReceptividadOpcionAdmin, ConfiguracionLsii } from '../../types';
import { BORDE_SUAVE, ERROR_TENUE, NEUTRO_300, SUPERFICIE_2, SUPERFICIE_3, TAUPE_MEDIO } from '../../theme/marca';

// ── helpers ──────────────────────────────────────────────────────────────
let tempIdSeq = -1;
function nuevaOpcion(orden: number): ReceptividadOpcionAdmin {
  return { id: tempIdSeq--, orden_opcion: orden, texto_comportamiento: '', score_oculto: 5, activo: true };
}
function nuevaDimension(orden: number): ReceptividadDimensionAdmin {
  return {
    dimension_codigo: '',
    dimension_nombre: '',
    dimension_descripcion: '',
    orden_dimension: orden,
    peso_dimension: 0.1,
    activo: true,
    opciones: [nuevaOpcion(1), nuevaOpcion(2)],
  };
}

function validarDimension(d: ReceptividadDimensionAdmin): string | null {
  if (!d.dimension_codigo.trim()) return 'El código de la dimensión es obligatorio.';
  if (!/^[A-Z0-9_]+$/.test(d.dimension_codigo.trim())) return 'El código solo puede tener mayúsculas, números y guion bajo (ej: ACTITUD_CAMBIO).';
  if (!d.dimension_nombre.trim()) return 'El nombre de la dimensión es obligatorio.';
  if (!(d.peso_dimension > 0 && d.peso_dimension <= 1)) return 'El peso debe ser mayor a 0% y menor o igual a 100%.';
  if (d.opciones.length < 2) return 'Cada dimensión necesita al menos 2 opciones de comportamiento.';
  const ordenes = d.opciones.map(o => o.orden_opcion);
  if (new Set(ordenes).size !== ordenes.length) return 'El orden de las opciones no puede repetirse.';
  for (const o of d.opciones) {
    if (!o.texto_comportamiento.trim()) return 'Todas las opciones necesitan un texto de comportamiento.';
    if (!(o.score_oculto >= 1 && o.score_oculto <= 10)) return 'El puntaje oculto debe estar entre 1 y 10.';
  }
  return null;
}

// ════════════════════════════════════════════════════════════════════════
export default function LsiiAdmin() {
  const qc = useQueryClient();
  const [incluirInactivas, setIncluirInactivas] = useState(false);
  const [dims, setDims] = useState<ReceptividadDimensionAdmin[]>([]);
  const [expandido, setExpandido] = useState<string | false>(false);
  const [errores, setErrores] = useState<Record<string, string>>({});
  const [confirmarBorrado, setConfirmarBorrado] = useState<string | null>(null);

  const dimsQuery = useQuery({
    queryKey: ['lsii-admin-dimensiones', incluirInactivas],
    queryFn: () => api.get('/lsii/admin/dimensiones', { params: { incluir_inactivas: incluirInactivas } })
      .then(r => r.data as ReceptividadDimensionAdmin[]),
  });

  // sincroniza el borrador local solo cuando llegan datos nuevos del servidor
  useEffect(() => {
    if (dimsQuery.data) {
      setDims(dimsQuery.data.map(d => ({ ...d, opciones: d.opciones.map(o => ({ ...o })) })));
    }
  }, [dimsQuery.data]);

  const configQuery = useQuery({
    queryKey: ['lsii-admin-configuracion'],
    queryFn: () => api.get('/lsii/admin/configuracion').then(r => r.data as ConfiguracionLsii),
  });
  const [corteDesempeno, setCorteDesempeno] = useState('80');
  const [corteReceptividad, setCorteReceptividad] = useState('80');
  useEffect(() => {
    if (configQuery.data) {
      setCorteDesempeno(String(configQuery.data.corte_desempeno));
      setCorteReceptividad(String(configQuery.data.corte_receptividad));
    }
  }, [configQuery.data]);

  const mutConfig = useMutation({
    mutationFn: () => api.put('/lsii/admin/configuracion', {
      corte_desempeno: Number(corteDesempeno),
      corte_receptividad: Number(corteReceptividad),
    }).then(r => r.data as ConfiguracionLsii),
    onSuccess: (data) => {
      qc.setQueryData(['lsii-admin-configuracion'], data);
    },
  });

  const mutGuardarDimension = useMutation({
    mutationFn: (payload: ReceptividadDimensionAdmin) => {
      const body = {
        ...payload,
        opciones: payload.opciones.map(o => ({
          ...o,
          id: o.id != null && o.id > 0 ? o.id : null,
        })),
      };
      return api.post('/lsii/admin/dimensiones', body).then(r => r.data as ReceptividadDimensionAdmin);
    },
    onSuccess: (data, payload) => {
      setDims(prev => prev.map(d => (d === payload || d.dimension_codigo === payload.dimension_codigo) ? data : d));
      setErrores(prev => ({ ...prev, [payload.dimension_codigo || '__nueva__']: '' }));
      qc.invalidateQueries({ queryKey: ['lsii-catalogo'] });
    },
  });

  const mutDesactivarDimension = useMutation({
    mutationFn: (codigo: string) => api.delete(`/lsii/admin/dimensiones/${codigo}`).then(r => r.data),
    onSuccess: () => {
      setConfirmarBorrado(null);
      dimsQuery.refetch();
      qc.invalidateQueries({ queryKey: ['lsii-catalogo'] });
    },
  });

  const mutToggleOpcion = useMutation({
    mutationFn: (vars: { id: number; activo: boolean }) =>
      api.patch(`/lsii/admin/opciones/${vars.id}`, { activo: vars.activo }).then(r => r.data as ReceptividadOpcionAdmin),
  });

  // ── mutadores del borrador local ─────────────────────────────────────
  function actualizarDim(idx: number, cambios: Partial<ReceptividadDimensionAdmin>) {
    setDims(prev => prev.map((d, i) => i === idx ? { ...d, ...cambios } : d));
  }
  function actualizarOpcion(idx: number, opIdx: number, cambios: Partial<ReceptividadOpcionAdmin>) {
    setDims(prev => prev.map((d, i) => {
      if (i !== idx) return d;
      return { ...d, opciones: d.opciones.map((o, j) => j === opIdx ? { ...o, ...cambios } : o) };
    }));
  }
  function agregarOpcion(idx: number) {
    setDims(prev => prev.map((d, i) => {
      if (i !== idx) return d;
      const maxOrden = d.opciones.reduce((m, o) => Math.max(m, o.orden_opcion), 0);
      return { ...d, opciones: [...d.opciones, nuevaOpcion(maxOrden + 1)] };
    }));
  }
  function quitarOpcion(idx: number, opIdx: number) {
    setDims(prev => prev.map((d, i) => {
      if (i !== idx) return d;
      return { ...d, opciones: d.opciones.filter((_, j) => j !== opIdx) };
    }));
  }
  function agregarDimension() {
    const maxOrden = dims.reduce((m, d) => Math.max(m, d.orden_dimension), 0);
    setDims(prev => [...prev, nuevaDimension(maxOrden + 1)]);
    setExpandido(`__nueva_${dims.length}`);
  }
  function descartarDimensionNueva(idx: number) {
    setDims(prev => prev.filter((_, i) => i !== idx));
  }

  function guardarDimension(idx: number) {
    const d = dims[idx];
    const err = validarDimension(d);
    const key = d.dimension_codigo || '__nueva__';
    if (err) {
      setErrores(prev => ({ ...prev, [key]: err }));
      return;
    }
    setErrores(prev => ({ ...prev, [key]: '' }));
    mutGuardarDimension.mutate(d);
  }

  const loading = dimsQuery.isLoading || configQuery.isLoading;

  return (
    <Box>
      <Typography variant="body2" color="text.secondary" sx={{ mb: 2.5 }}>
        Aquí se edita la Matriz LSII completa: el umbral de los cuadrantes D1-D4, las dimensiones de
        Receptividad/Compromiso y el puntaje oculto de cada opción. El representante médico y el GD evaluador
        nunca ven el puntaje ni el peso — solo el texto de comportamiento.
      </Typography>

      {/* ── Umbral de corte D1-D4 ──────────────────────────────────────── */}
      <Card elevation={0} sx={{ mb: 3, border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <CardContent>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1.5 }}>
            <Lock fontSize="small" sx={{ color: TAUPE_MEDIO }} />
            <Typography variant="subtitle1" fontWeight={700}>Umbral de Corte de Cuadrantes</Typography>
          </Box>
          <Typography variant="body2" color="text.secondary" sx={{ mb: 2 }}>
            Define dónde se separan los cuadrantes D1/D2 de D3/D4 (eje Desempeño) y D1/D3 de D2/D4 (eje Receptividad).
            Por defecto ambos están en 80. Solo afecta evaluaciones nuevas; las ya registradas conservan su clasificación original.
          </Typography>
          {configQuery.isLoading ? (
            <CircularProgress size={24} />
          ) : (
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={3}>
                <TextField fullWidth size="small" type="number" label="Corte Desempeño (eje Y)"
                  value={corteDesempeno} onChange={e => setCorteDesempeno(e.target.value)}
                  inputProps={{ min: 0.01, max: 100, step: 0.5 }} />
              </Grid>
              <Grid item xs={12} sm={3}>
                <TextField fullWidth size="small" type="number" label="Corte Receptividad (eje X)"
                  value={corteReceptividad} onChange={e => setCorteReceptividad(e.target.value)}
                  inputProps={{ min: 0.01, max: 100, step: 0.5 }} />
              </Grid>
              <Grid item xs={12} sm={3}>
                <Button variant="contained" startIcon={<Save fontSize="small" />}
                  disabled={mutConfig.isPending}
                  onClick={() => mutConfig.mutate()}>
                  {mutConfig.isPending ? 'Guardando...' : 'Guardar Umbral'}
                </Button>
              </Grid>
              <Grid item xs={12} sm={3}>
                {configQuery.data?.actualizado_en && (
                  <Typography variant="caption" color="text.secondary">
                    Última actualización: {new Date(configQuery.data.actualizado_en).toLocaleString()}
                    {configQuery.data.actualizado_por ? ` · ${configQuery.data.actualizado_por}` : ''}
                  </Typography>
                )}
              </Grid>
            </Grid>
          )}
          {mutConfig.isError && (
            <Alert severity="error" sx={{ mt: 2 }}>
              {(mutConfig.error as any)?.response?.data?.detail || 'No se pudo actualizar el umbral.'}
            </Alert>
          )}
          {mutConfig.isSuccess && (
            <Alert severity="success" sx={{ mt: 2 }}>Umbral actualizado correctamente.</Alert>
          )}
        </CardContent>
      </Card>

      {/* ── Dimensiones y opciones ─────────────────────────────────────── */}
      <Box sx={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', mb: 1.5, flexWrap: 'wrap', gap: 1 }}>
        <Typography variant="subtitle1" fontWeight={700}>Dimensiones de Receptividad/Compromiso</Typography>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
          <FormControlLabel
            control={<Switch size="small" checked={incluirInactivas} onChange={e => setIncluirInactivas(e.target.checked)} />}
            label={<Typography variant="caption">Mostrar desactivadas</Typography>}
          />
          <MuiTooltip title="Recargar desde el servidor (descarta cambios sin guardar)">
            <IconButton size="small" onClick={() => dimsQuery.refetch()}><Refresh fontSize="small" /></IconButton>
          </MuiTooltip>
          <Button size="small" variant="outlined" startIcon={<Add fontSize="small" />} onClick={agregarDimension}>
            Nueva Dimensión
          </Button>
        </Box>
      </Box>

      {loading && !dims.length ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', py: 4 }}><CircularProgress /></Box>
      ) : !dims.length ? (
        <Alert severity="info">No hay dimensiones configuradas.</Alert>
      ) : (
        [...dims].sort((a, b) => a.orden_dimension - b.orden_dimension).map((d) => {
          const idx = dims.indexOf(d);
          const key = d.dimension_codigo || `__nueva_${idx}`;
          const error = errores[d.dimension_codigo || '__nueva__'];
          const activeOptions = d.opciones.filter(o => o.activo).length;
          return (
            <Accordion
              key={idx}
              expanded={expandido === key}
              onChange={(_, exp) => setExpandido(exp ? key : false)}
              elevation={0}
              sx={{ border: '1px solid #e0e7ef', borderRadius: 2, mb: 1.5, '&:before': { display: 'none' } }}
            >
              <AccordionSummary expandIcon={<ExpandMore />}>
                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5, width: '100%', flexWrap: 'wrap' }}>
                  <Typography fontWeight={700} fontSize="0.9rem">
                    {d.dimension_nombre || <span style={{ color: NEUTRO_300 }}>(nueva dimensión sin nombre)</span>}
                  </Typography>
                  <Chip label={d.dimension_codigo || 'SIN CÓDIGO'} size="small" variant="outlined" />
                  <Chip label={`Peso ${(d.peso_dimension * 100).toFixed(0)}%`} size="small" sx={{ bgcolor: SUPERFICIE_3, color: TAUPE_MEDIO, fontWeight: 700 }} />
                  <Chip label={`${activeOptions} opción(es) activa(s)`} size="small" variant="outlined" />
                  {!d.activo && <Chip label="Desactivada" size="small" color="default" sx={{ bgcolor: BORDE_SUAVE }} />}
                </Box>
              </AccordionSummary>
              <AccordionDetails>
                {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}

                <Grid container spacing={2} sx={{ mb: 2 }}>
                  <Grid item xs={12} sm={4}>
                    <TextField fullWidth size="small" label="Código (único, MAYÚSCULAS_GUION_BAJO)"
                      value={d.dimension_codigo}
                      disabled={!!dimsQuery.data?.some(orig => orig.dimension_codigo === d.dimension_codigo)}
                      onChange={e => actualizarDim(idx, { dimension_codigo: e.target.value.toUpperCase().replace(/\s+/g, '_') })}
                    />
                  </Grid>
                  <Grid item xs={12} sm={5}>
                    <TextField fullWidth size="small" label="Nombre visible"
                      value={d.dimension_nombre}
                      onChange={e => actualizarDim(idx, { dimension_nombre: e.target.value })}
                    />
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <TextField fullWidth size="small" type="number" label="Orden"
                      value={d.orden_dimension}
                      onChange={e => actualizarDim(idx, { orden_dimension: Number(e.target.value) })}
                      inputProps={{ min: 1 }}
                    />
                  </Grid>
                  <Grid item xs={6} sm={1.5}>
                    <TextField fullWidth size="small" type="number" label="Peso %"
                      value={Math.round(d.peso_dimension * 100)}
                      onChange={e => actualizarDim(idx, { peso_dimension: Math.min(100, Math.max(0, Number(e.target.value))) / 100 })}
                      inputProps={{ min: 1, max: 100 }}
                    />
                  </Grid>
                  <Grid item xs={12}>
                    <TextField fullWidth size="small" label="Descripción (opcional)"
                      value={d.dimension_descripcion || ''}
                      onChange={e => actualizarDim(idx, { dimension_descripcion: e.target.value })}
                    />
                  </Grid>
                </Grid>

                <Divider sx={{ mb: 2 }} />

                <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
                  <VisibilityOff fontSize="small" sx={{ color: NEUTRO_300 }} />
                  <Typography variant="caption" color="text.secondary">
                    El texto se muestra al evaluador. El puntaje oculto (1-10) y el peso de la dimensión nunca se exponen al GD ni al RM.
                  </Typography>
                </Box>

                {d.opciones.map((o, opIdx) => (
                  <Box key={o.id ?? opIdx} sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1, p: 1, borderRadius: 1.5, bgcolor: o.activo ? SUPERFICIE_2 : ERROR_TENUE }}>
                    <TextField size="small" type="number" label="Orden" sx={{ width: 80 }}
                      value={o.orden_opcion}
                      onChange={e => actualizarOpcion(idx, opIdx, { orden_opcion: Number(e.target.value) })}
                      inputProps={{ min: 1 }}
                    />
                    <TextField size="small" label="Texto de comportamiento (visible al GD)" fullWidth
                      value={o.texto_comportamiento}
                      onChange={e => actualizarOpcion(idx, opIdx, { texto_comportamiento: e.target.value })}
                    />
                    <TextField size="small" type="number" label="Puntaje oculto" sx={{ width: 110 }}
                      value={o.score_oculto}
                      onChange={e => actualizarOpcion(idx, opIdx, { score_oculto: Number(e.target.value) })}
                      inputProps={{ min: 1, max: 10 }}
                    />
                    <MuiTooltip title={o.activo ? 'Activa' : 'Desactivada'}>
                      <Switch size="small" checked={o.activo} onChange={e => {
                        const activo = e.target.checked;
                        actualizarOpcion(idx, opIdx, { activo });
                        if (o.id != null && o.id > 0) mutToggleOpcion.mutate({ id: o.id, activo });
                      }} />
                    </MuiTooltip>
                    <MuiTooltip title="Quitar del formulario (se desactivará al guardar)">
                      <IconButton size="small" onClick={() => quitarOpcion(idx, opIdx)}>
                        <Delete fontSize="small" />
                      </IconButton>
                    </MuiTooltip>
                  </Box>
                ))}

                <Button size="small" startIcon={<Add fontSize="small" />} onClick={() => agregarOpcion(idx)} sx={{ mb: 2 }}>
                  Agregar opción
                </Button>

                {mutGuardarDimension.isError && expandido === key && (
                  <Alert severity="error" sx={{ mb: 2 }}>
                    {(mutGuardarDimension.error as any)?.response?.data?.detail || 'No se pudo guardar la dimensión.'}
                  </Alert>
                )}

                <Box sx={{ display: 'flex', gap: 1.5, flexWrap: 'wrap' }}>
                  <Button variant="contained" startIcon={<Save fontSize="small" />}
                    disabled={mutGuardarDimension.isPending}
                    onClick={() => guardarDimension(idx)}>
                    {mutGuardarDimension.isPending ? 'Guardando...' : 'Guardar Dimensión'}
                  </Button>

                  {!d.dimension_codigo ? (
                    <Button color="inherit" onClick={() => descartarDimensionNueva(idx)}>Descartar</Button>
                  ) : confirmarBorrado === d.dimension_codigo ? (
                    <>
                      <Button color="error" variant="contained"
                        disabled={mutDesactivarDimension.isPending}
                        onClick={() => mutDesactivarDimension.mutate(d.dimension_codigo)}>
                        Confirmar desactivación
                      </Button>
                      <Button color="inherit" onClick={() => setConfirmarBorrado(null)}>Cancelar</Button>
                    </>
                  ) : (
                    <Button color="error" startIcon={<Delete fontSize="small" />}
                      onClick={() => setConfirmarBorrado(d.dimension_codigo)}>
                      Desactivar Dimensión
                    </Button>
                  )}
                </Box>
              </AccordionDetails>
            </Accordion>
          );
        })
      )}
    </Box>
  );
}
