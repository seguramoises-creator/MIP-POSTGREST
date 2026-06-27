import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Button, Grid,
  Table, TableBody, TableCell, TableContainer, TableHead,
  TableRow, Paper, Chip, Alert, LinearProgress,
  TextField, MenuItem, Step, Stepper, StepLabel,
} from '@mui/material';
import { CloudUpload, Refresh, PlayArrow, RocketLaunch, Calculate } from '@mui/icons-material';
import { api } from '../../services/api';

const ESTADOS: Record<string, { color: 'success' | 'warning' | 'error' | 'info' | 'default'; label: string }> = {
  EXITOSO: { color: 'success', label: 'Exitoso' },
  PROCESANDO: { color: 'info', label: 'Procesando' },
  PENDIENTE: { color: 'warning', label: 'Pendiente' },
  ERROR: { color: 'error', label: 'Error' },
};

// Pasos del flujo ETL
const PASOS = ['Seleccionar archivo', 'Validar (Simulación)', 'Cargar a Producción'];

export default function ETL() {
  const [file, setFile] = useState<File | null>(null);
  const [tipo, setTipo] = useState('KPI_RM');
  const [paso, setPaso] = useState(0);
  const [simMsg, setSimMsg] = useState('');
  const [prodMsg, setProdMsg] = useState('');
  const [simOk, setSimOk] = useState(false);
  const [paisRecalc, setPaisRecalc] = useState<string | ''>('');
  const [cicloRecalc, setCicloRecalc] = useState<number | ''>('');
  const [recalcMsg, setRecalcMsg] = useState('');
  const qc = useQueryClient();

  const { data: historial, isLoading, refetch } = useQuery({
    queryKey: ['etl-historial'],
    queryFn: () => api.get('/etl/historial').then((r) => r.data),
    refetchInterval: 5000,
  });

  // Catálogos para el selector de recálculo: el usuario elige país y ciclo
  // por su nombre legible (ej. "C01-2026"); el backend recibe los IDs internos.
  const { data: paises } = useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then((r) => r.data as { id: number; codigo: string; nombre: string }[]),
  });

  const { data: ciclos } = useQuery({
    queryKey: ['ciclos', paisRecalc],
    queryFn: () => api.get('/admin/ciclos', { params: { pais_codigo: paisRecalc } })
      .then((r) => r.data as { id: number; pais_codigo: string; anio: number; numero: number; nombre: string; nombre_canonico: string  | null; cerrado: boolean }[]),
    enabled: paisRecalc !== '',
  });

  const cicloSeleccionado = (ciclos || []).find((c) => c.id === cicloRecalc);

  // ── Auto-seleccionar República Dominicana al cargar ───────────────────
  useEffect(() => {
    if (!(paises || []).length || paisRecalc) return;
    const rd = (paises as any[]).find((p: any) =>
      p.codigo?.toUpperCase() === 'RD' ||
      p.nombre?.toLowerCase().includes('dominicana')
    );
    if (rd) setPaisRecalc(rd.codigo);
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps

  // Obtener el último ciclo con datos reales
  const { data: _cicloEf } = useQuery({
    queryKey: ['ciclo-ef', paisRecalc],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisRecalc && { pais_codigo: paisRecalc }), size: 1, page: 1 },
    }).then(r => r.data?.ciclo_efectivo ?? null),
    enabled: !!paisRecalc,
    staleTime: 60_000,
  });
  // ── Auto-seleccionar el último ciclo CON DATOS ─────────────────────
  useEffect(() => {
    if (!_cicloEf || cicloRecalc) return;
    setCicloRecalc(_cicloEf);
  }, [_cicloEf]); // eslint-disable-line react-hooks/exhaustive-deps


  const enviar = async (modo: 'SIMULACION' | 'PRODUCCION') => {
    if (!file) return;
    const form = new FormData();
    form.append('archivo', file);
    form.append('tipo_archivo', tipo);
    form.append('modo', modo);
    return api.post('/etl/cargar', form, {
      headers: { 'Content-Type': 'multipart/form-data' },
    }).then((r) => r.data);
  };

  const simMutation = useMutation({
    mutationFn: () => enviar('SIMULACION'),
    onSuccess: (data) => {
      const id = data.id || data.job_id;
      setSimMsg(`✅ Simulación exitosa — Job ID: ${id}. Archivo validado correctamente.`);
      setSimOk(true);
      setPaso(1);
      qc.invalidateQueries({ queryKey: ['etl-historial'] });
    },
    onError: (e: any) => {
      setSimMsg(`❌ Error en simulación: ${e.response?.data?.detail || e.message}`);
      setSimOk(false);
    },
  });

  const prodMutation = useMutation({
    mutationFn: () => enviar('PRODUCCION'),
    onSuccess: (data) => {
      const id = data.id || data.job_id;
      setProdMsg(`✅ Carga a producción iniciada — Job ID: ${id}. Revisa el historial para ver el resultado.`);
      setPaso(2);
      setFile(null);
      setSimOk(false);
      qc.invalidateQueries({ queryKey: ['etl-historial'] });
    },
    onError: (e: any) => {
      setProdMsg(`❌ Error en producción: ${e.response?.data?.detail || e.message}`);
    },
  });

  const resetear = () => {
    setFile(null);
    setPaso(0);
    setSimMsg('');
    setProdMsg('');
    setSimOk(false);
  };

  const recalcMutation = useMutation({
    mutationFn: () =>
      api.post(`/etl/recalcular/${cicloRecalc}`, null, { params: { pais_codigo: paisRecalc } }).then((r) => r.data),
    onSuccess: (data) => {
      const nombreCiclo = cicloSeleccionado?.nombre_canonico || cicloSeleccionado?.nombre || `#${cicloRecalc}`;
      setRecalcMsg(`✅ Recálculo de ${nombreCiclo} completado — ${data.filas_kpi_actualizadas} KPIs actualizados, ${data.rankings_generados} rankings generados`);
      qc.invalidateQueries({ queryKey: ['etl-historial'] });
    },
    onError: (e: any) => setRecalcMsg(`❌ Error: ${e.response?.data?.detail || e.message}`),
  });

  const items: any[] = historial || [];

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Carga Excel — ETL</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Carga el archivo FACT_KPI_RM con los KPIs de los Representantes Médicos
      </Typography>

      {/* Stepper */}
      <Card elevation={2} sx={{ mb: 3, borderRadius: 3 }}>
        <CardContent>
          <Stepper activeStep={paso} sx={{ mb: 3 }}>
            {PASOS.map((label) => (
              <Step key={label}><StepLabel>{label}</StepLabel></Step>
            ))}
          </Stepper>

          {/* Paso 0: Seleccionar archivo */}
          {paso === 0 && (
            <Grid container spacing={2} alignItems="center">
              <Grid item xs={12} sm={3}>
                <TextField
                  select fullWidth size="small" label="Tipo de archivo"
                  value={tipo} onChange={(e) => setTipo(e.target.value)}
                >
                  {[
                    { value: 'KPI_RM', label: 'KPI_RM — Fact principal' },
                    { value: 'PRODUCTIVIDAD', label: 'PRODUCTIVIDAD (legacy)' },
                    { value: 'COMERCIAL', label: 'COMERCIAL (legacy)' },
                    { value: 'COACHING', label: 'COACHING (legacy)' },
                    { value: 'CAPACITACION', label: 'CAPACITACION (legacy)' },
                  ].map((t) => (
                    <MenuItem key={t.value} value={t.value}>{t.label}</MenuItem>
                  ))}
                </TextField>
              </Grid>
              <Grid item xs={12} sm={5}>
                <Button variant="outlined" component="label" startIcon={<CloudUpload />} fullWidth>
                  {file ? file.name : 'Seleccionar archivo .xlsx'}
                  <input
                    type="file" accept=".xlsx,.xls" hidden
                    onChange={(e) => {
                      setFile(e.target.files?.[0] || null);
                      setSimMsg(''); setProdMsg(''); setSimOk(false);
                    }}
                  />
                </Button>
              </Grid>
              <Grid item xs={12} sm={4}>
                <Button
                  variant="contained" color="warning" fullWidth
                  startIcon={<PlayArrow />}
                  disabled={!file || simMutation.isPending}
                  onClick={() => simMutation.mutate()}
                >
                  {simMutation.isPending ? 'Validando...' : 'Validar (Simulación)'}
                </Button>
              </Grid>
              {simMsg && (
                <Grid item xs={12}>
                  <Alert severity={simMsg.startsWith('❌') ? 'error' : 'success'}>{simMsg}</Alert>
                </Grid>
              )}
            </Grid>
          )}

          {/* Paso 1: Simulación OK — confirmar producción */}
          {paso === 1 && (
            <Box>
              <Alert severity="success" sx={{ mb: 2 }}>{simMsg}</Alert>
              <Alert severity="warning" sx={{ mb: 2 }}>
                ⚠️ Estás a punto de cargar <strong>{file?.name}</strong> a PRODUCCIÓN.
                Los datos se escribirán en la base de datos. Esta acción no se puede deshacer.
              </Alert>
              <Box sx={{ display: 'flex', gap: 2 }}>
                <Button variant="outlined" onClick={resetear}>
                  Cancelar / Nuevo archivo
                </Button>
                <Button
                  variant="contained" color="error"
                  startIcon={<RocketLaunch />}
                  disabled={prodMutation.isPending}
                  onClick={() => prodMutation.mutate()}
                >
                  {prodMutation.isPending ? 'Cargando...' : 'Confirmar carga a Producción'}
                </Button>
              </Box>
              {prodMsg && (
                <Alert severity={prodMsg.startsWith('❌') ? 'error' : 'success'} sx={{ mt: 2 }}>
                  {prodMsg}
                </Alert>
              )}
            </Box>
          )}

          {/* Paso 2: Producción completada */}
          {paso === 2 && (
            <Box>
              <Alert severity="success" sx={{ mb: 2 }}>{prodMsg}</Alert>
              <Button variant="contained" onClick={resetear}>
                Nueva carga
              </Button>
            </Box>
          )}
        </CardContent>
      </Card>

      {/* Recálculo */}
      <Card elevation={2} sx={{ mb: 3, borderRadius: 3 }}>
        <CardContent>
          <Typography variant="h6" fontWeight={600} mb={1}>Calcular IUP y Ranking</Typography>
          <Typography variant="body2" color="text.secondary" mb={2}>
            Después de cargar FACT_KPI_RM, selecciona el país y el ciclo (por su nombre) para calcular
            puntajes, IUP y generar el ranking. El sistema traduce internamente el nombre al ID del ciclo.
          </Typography>
          <Box sx={{ display: 'flex', alignItems: 'center', gap: 2, flexWrap: 'wrap' }}>
            <TextField
              select size="small" label="País" sx={{ minWidth: 200 }}
              value={paisRecalc}
              onChange={(e) => { setPaisRecalc(e.target.value); setCicloRecalc(''); setRecalcMsg(''); }}
            >
              {(paises || []).map((p) => (
                <MenuItem key={p.id} value={p.codigo}>{p.nombre}</MenuItem>
              ))}
            </TextField>
            <TextField
              select size="small" label="Ciclo" sx={{ minWidth: 200 }}
              value={cicloRecalc}
              disabled={paisRecalc === ''}
              onChange={(e) => { setCicloRecalc(e.target.value === '' ? '' : Number(e.target.value)); setRecalcMsg(''); }}
            >
              {paisRecalc === '' && <MenuItem value="" disabled>Primero selecciona un país</MenuItem>}
              {(ciclos || []).map((c) => (
                <MenuItem key={c.id} value={c.id}>
                  {(c.nombre_canonico || c.nombre)} {c.cerrado ? '(cerrado)' : ''}
                </MenuItem>
              ))}
            </TextField>
            <Button
              variant="contained" color="success" startIcon={<Calculate />}
              disabled={paisRecalc === '' || cicloRecalc === '' || recalcMutation.isPending}
              onClick={() => { setRecalcMsg(''); recalcMutation.mutate(); }}
            >
              {recalcMutation.isPending ? 'Calculando...' : 'Calcular IUP y Ranking'}
            </Button>
          </Box>
          {cicloSeleccionado?.cerrado && (
            <Alert severity="warning" sx={{ mt: 2 }}>
              ⚠️ El ciclo {cicloSeleccionado.nombre_canonico || cicloSeleccionado.nombre} está cerrado — el recálculo se abortará sin escribir cambios.
            </Alert>
          )}
          {recalcMsg && (
            <Alert severity={recalcMsg.startsWith('❌') ? 'error' : 'success'} sx={{ mt: 2 }}>
              {recalcMsg}
            </Alert>
          )}
        </CardContent>
      </Card>

      {/* Historial */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', mb: 2 }}>
        <Typography variant="h6" fontWeight={600}>Historial de cargas</Typography>
        <Button startIcon={<Refresh />} size="small" onClick={() => refetch()}>Actualizar</Button>
      </Box>

      {isLoading && <LinearProgress sx={{ mb: 2 }} />}

      <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
        <Table size="small">
          <TableHead sx={{ bgcolor: 'grey.100' }}>
            <TableRow>
              {['ID', 'Tipo', 'Modo', 'Estado', 'Total', 'Exitosas', 'Errores', 'Inicio', 'Fin'].map((h) => (
                <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
              ))}
            </TableRow>
          </TableHead>
          <TableBody>
            {items.length === 0 ? (
              <TableRow>
                <TableCell colSpan={9} align="center" sx={{ py: 4, color: 'text.secondary' }}>
                  Sin cargas registradas
                </TableCell>
              </TableRow>
            ) : (
              items.map((row: any) => {
                const estado = ESTADOS[row.estado] || { color: 'default', label: row.estado };
                return (
                  <TableRow key={row.id} hover>
                    <TableCell>{row.id}</TableCell>
                    <TableCell>{row.tipo_archivo}</TableCell>
                    <TableCell>
                      <Chip label={row.modo || '—'} size="small"
                        color={row.modo === 'PRODUCCION' ? 'primary' : 'warning'} />
                    </TableCell>
                    <TableCell>
                      <Chip label={estado.label} color={estado.color} size="small" />
                    </TableCell>
                    <TableCell>{row.total_filas ?? '—'}</TableCell>
                    <TableCell sx={{ color: 'success.main' }}>{row.filas_exitosas ?? '—'}</TableCell>
                    <TableCell sx={{ color: row.filas_error > 0 ? 'error.main' : 'inherit' }}>
                      {row.filas_error ?? '—'}
                    </TableCell>
                    <TableCell>{row.fecha_inicio ? new Date(row.fecha_inicio).toLocaleString() : '—'}</TableCell>
                    <TableCell>{row.fecha_fin ? new Date(row.fecha_fin).toLocaleString() : '—'}</TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </TableContainer>
    </Box>
  );
}
