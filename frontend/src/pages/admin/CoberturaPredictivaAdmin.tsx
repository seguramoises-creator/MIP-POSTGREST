/**
 * CoberturaPredictivaAdmin.tsx — Mantenimiento de datos del módulo
 * "Cobertura Predictiva y Ritmo de Ejecución" (4DX).
 *
 * Reemplaza el flujo manual por Swagger para:
 * - Configurar la Meta de Cobertura (% objetivo) por país/línea/ciclo
 *   → DIM_ParametroCobertura (POST /cobertura-predictiva/parametros, upsert)
 * - Configurar Feriados (afectan días laborables si Ciclo.dias_laborables=0)
 *   → DIM_Feriado (POST /cobertura-predictiva/feriados)
 * - Cargar el universo de médicos target (Target_Medicos)
 *   → POST /cobertura-predictiva/cargar/target-medicos (idempotente)
 * - Cargar la bitácora de visitas (Fact_Visitas)
 *   → POST /cobertura-predictiva/cargar/visitas (NO idempotente, append-only)
 * - Cargar Excel combinado (todas las hojas en un archivo)
 *   → POST /cobertura-predictiva/cat/cargar-excel
 * - Limpiar datos del país para recargar desde cero
 *   → DELETE /cobertura-predictiva/cat/datos
 *
 * Sigue el mismo patrón visual/estructural que Admin.tsx (PaisSelector,
 * usePaises) y ETL.tsx (selector de ciclo + modo SIMULACION/PRODUCCION +
 * archivo, con resultado detallado).
 */
import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, Button, TextField, MenuItem,
  Select, FormControl, InputLabel, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Alert, Divider, Stack, CircularProgress,
} from '@mui/material';
import { CloudUpload, Save, EventBusy, TrendingUp, DeleteForever, UploadFile } from '@mui/icons-material';
import { api } from '../../services/api';

type Pais = { id: number; codigo: string; nombre: string };
type Linea = { id: number; pais_id: number; codigo: string; nombre: string };
type Ciclo = { id: number; pais_id: number; anio: number; numero: number; nombre: string; nombre_canonico: string | null; cerrado: boolean };

// ── Hooks compartidos (mismo patrón que Admin.tsx / ETL.tsx) ────────────
function usePaises() {
  return useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then((r) => {
      const d = r.data;
      return (Array.isArray(d) ? d : (d?.items ?? [])) as Pais[];
    }),
    staleTime: 0,
  });
}

/** Líneas reales (Config.DIM_Linea) filtradas por país — para mostrar nombre, nunca ID crudo. */
function useLineas(paisId: string | '') {
  return useQuery({
    queryKey: ['lineas', paisId],
    queryFn: () => api.get('/admin/lineas', { params: { pais_codigo: paisId } }).then((r) => {
      const d = r.data;
      return (Array.isArray(d) ? d : (d?.items ?? [])) as Linea[];
    }),
    enabled: paisId !== '',
  });
}

function useCiclos(paisId: string | '') {
  return useQuery({
    queryKey: ['ciclos', paisId],
    queryFn: () => api.get('/admin/ciclos', { params: { pais_codigo: paisId } }).then((r) => r.data as Ciclo[]),
    enabled: paisId !== '',
  });
}

/** Auto-selecciona República Dominicana al cargar (mismo patrón repetido en todo el proyecto). */
function useAutoSelectRD(paises: Pais[] | undefined, paisId: string | '', setPaisId: (id: string) => void) {
  useEffect(() => {
    if (!(paises || []).length || paisId) return;
    const rd = paises!.find((p) => p.codigo?.toUpperCase() === 'RD' || p.nombre?.toLowerCase().includes('dominicana'));
    if (rd) setPaisId(rd.codigo);
  }, [paises]); // eslint-disable-line react-hooks/exhaustive-deps
}

// ─────────────────────────────────────────────────────────────────────────
// Bloque 1 — Meta de Cobertura (DIM_ParametroCobertura)
// ─────────────────────────────────────────────────────────────────────────
function ParametrosCoberturaCard() {
  const qc = useQueryClient();
  const { data: paises } = usePaises();
  const [paisId, setPaisId] = useState<string | ''>('');
  const [lineaId, setLineaId] = useState('');
  const [cicloId, setCicloId] = useState<number | ''>('');
  const [metaPct, setMetaPct] = useState('90');
  const [msg, setMsg] = useState('');

  useAutoSelectRD(paises, paisId, setPaisId);
  const { data: ciclos } = useCiclos(paisId);
  const { data: lineas } = useLineas(paisId);

  const { data: parametros, isLoading } = useQuery({
    queryKey: ['cobertura-parametros', paisId],
    queryFn: () => api.get('/cobertura-predictiva/parametros', { params: { pais_codigo: paisId } }).then((r) => r.data as any[]),
    enabled: paisId !== '',
  });

  const guardar = useMutation({
    mutationFn: () => api.post('/cobertura-predictiva/parametros', {
      pais_codigo: paisId,
      linea_id: lineaId ? Number(lineaId) : null,
      ciclo_id: cicloId === '' ? null : cicloId,
      meta_cobertura: Number(metaPct) / 100,
    }).then((r) => r.data),
    onSuccess: (data) => {
      setMsg(`✅ Meta ${data.accion === 'creado' ? 'creada' : 'actualizada'} — ${(data.meta_cobertura * 100).toFixed(0)}%`);
      qc.invalidateQueries({ queryKey: ['cobertura-parametros'] });
    },
    onError: (e: any) => setMsg(`❌ ${e.response?.data?.detail || e.message}`),
  });

  const cargarEnFormulario = (p: any) => {
    setPaisId(p.pais_codigo);
    setLineaId(p.linea_id != null ? String(p.linea_id) : '');
    setCicloId(p.ciclo_id ?? '');
    setMetaPct(String(Math.round(p.meta_cobertura * 100)));
    setMsg('');
  };

  const cicloNombre = (id: number | null) => {
    if (!id) return <Chip label="Todos los ciclos" size="small" variant="outlined" />;
    const c = (ciclos || []).find((x) => x.id === id);
    return c ? (c.nombre_canonico || c.nombre) : `#${id}`;
  };

  const lineaNombre = (id: number | null) => {
    if (id == null) return <Chip label="Todas" size="small" variant="outlined" />;
    const l = (lineas || []).find((x) => x.id === id);
    return l ? `${l.codigo} — ${l.nombre}` : `#${id}`;
  };

  return (
    <Card elevation={2} sx={{ borderRadius: 3, mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <TrendingUp color="primary" />
          <Typography variant="h6" fontWeight={600}>Meta de Cobertura</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>
          % objetivo de médicos a cubrir (K = J × Meta). Deja Línea y/o Ciclo en blanco para una meta
          más general — el sistema busca primero la combinación más específica. Si no hay nada
          configurado se usa 90% por defecto.
        </Typography>

        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>País</InputLabel>
              <Select
                label="País" value={paisId}
                onChange={(e) => { setPaisId(e.target.value); setLineaId(''); setCicloId(''); setMsg(''); }}
              >
                {(paises || []).map((p) => (
                  <MenuItem key={p.id} value={p.codigo}>{p.codigo} — {p.nombre}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={2.5}>
            <FormControl fullWidth size="small" disabled={paisId === ''}>
              <InputLabel>Línea (opcional)</InputLabel>
              <Select
                label="Línea (opcional)" value={lineaId}
                onChange={(e) => { setLineaId(e.target.value); setMsg(''); }}
              >
                <MenuItem value="">Todas las líneas</MenuItem>
                {(lineas || []).map((l) => (
                  <MenuItem key={l.id} value={String(l.id)}>{l.codigo} — {l.nombre}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3}>
            <TextField
              select fullWidth size="small" label="Ciclo (opcional)"
              value={cicloId} disabled={paisId === ''}
              onChange={(e) => setCicloId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              <MenuItem value="">Todos los ciclos</MenuItem>
              {(ciclos || []).map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid item xs={12} sm={2}>
            <TextField
              fullWidth size="small" type="number" label="Meta %"
              value={metaPct} onChange={(e) => setMetaPct(e.target.value)}
              inputProps={{ min: 1, max: 100 }}
            />
          </Grid>
          <Grid item xs={12} sm={1.5}>
            <Button
              fullWidth variant="contained" startIcon={<Save />}
              disabled={paisId === '' || !metaPct || guardar.isPending}
              onClick={() => { setMsg(''); guardar.mutate(); }}
            >
              Guardar
            </Button>
          </Grid>
        </Grid>

        {msg && <Alert severity={msg.startsWith('❌') ? 'error' : 'success'} sx={{ mt: 2 }}>{msg}</Alert>}

        <Divider sx={{ my: 2 }} />

        <TableContainer component={Paper} variant="outlined">
          <Table size="small">
            <TableHead sx={{ bgcolor: 'grey.100' }}>
              <TableRow>
                {['Línea', 'Ciclo', 'Meta', ''].map((h) => (
                  <TableCell key={h} sx={{ fontWeight: 700 }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {paisId === '' ? (
                <TableRow><TableCell colSpan={4} align="center" sx={{ color: 'text.secondary', py: 3 }}>Selecciona un país para ver sus metas configuradas</TableCell></TableRow>
              ) : isLoading ? (
                <TableRow><TableCell colSpan={4} align="center">Cargando…</TableCell></TableRow>
              ) : (parametros || []).length === 0 ? (
                <TableRow><TableCell colSpan={4} align="center" sx={{ color: 'text.secondary', py: 3 }}>Sin metas configuradas — se usará el valor por defecto (90%)</TableCell></TableRow>
              ) : (
                (parametros || []).map((p: any) => (
                  <TableRow key={p.id} hover>
                    <TableCell>{lineaNombre(p.linea_id)}</TableCell>
                    <TableCell>{cicloNombre(p.ciclo_id)}</TableCell>
                    <TableCell><Chip label={`${(p.meta_cobertura * 100).toFixed(0)}%`} color="primary" size="small" /></TableCell>
                    <TableCell><Button size="small" onClick={() => cargarEnFormulario(p)}>Editar</Button></TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Bloque 2 — Feriados (DIM_Feriado)
// ─────────────────────────────────────────────────────────────────────────
function FeriadosCard() {
  const qc = useQueryClient();
  const { data: paises } = usePaises();
  const [paisId, setPaisId] = useState<string | ''>('');
  const [fecha, setFecha] = useState('');
  const [nombre, setNombre] = useState('');
  const [msg, setMsg] = useState('');

  useAutoSelectRD(paises, paisId, setPaisId);

  const { data: feriados, isLoading } = useQuery({
    queryKey: ['cobertura-feriados', paisId],
    queryFn: () => api.get('/cobertura-predictiva/feriados', { params: { pais_codigo: paisId } }).then((r) => r.data as any[]),
    enabled: paisId !== '',
  });

  const crear = useMutation({
    mutationFn: () => api.post('/cobertura-predictiva/feriados', {
      pais_codigo: paisId, fecha, nombre: nombre || null,
    }).then((r) => r.data),
    onSuccess: () => {
      setMsg('✅ Feriado agregado');
      setFecha(''); setNombre('');
      qc.invalidateQueries({ queryKey: ['cobertura-feriados'] });
    },
    onError: (e: any) => setMsg(`❌ ${e.response?.data?.detail || e.message}`),
  });

  return (
    <Card elevation={2} sx={{ borderRadius: 3, mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <EventBusy color="primary" />
          <Typography variant="h6" fontWeight={600}>Feriados</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Días no laborables usados para calcular el ritmo diario cuando el ciclo no tiene un número
          fijo de días laborables (Ciclo.dias_laborables = 0).
        </Typography>

        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={3}>
            <FormControl fullWidth size="small">
              <InputLabel>País</InputLabel>
              <Select
                label="País" value={paisId}
                onChange={(e) => { setPaisId(e.target.value); setMsg(''); }}
              >
                {(paises || []).map((p) => (
                  <MenuItem key={p.id} value={p.codigo}>{p.codigo} — {p.nombre}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={3}>
            <TextField
              fullWidth size="small" type="date" label="Fecha" InputLabelProps={{ shrink: true }}
              value={fecha} onChange={(e) => setFecha(e.target.value)}
            />
          </Grid>
          <Grid item xs={12} sm={4}>
            <TextField fullWidth size="small" label="Nombre (opcional)" value={nombre} onChange={(e) => setNombre(e.target.value)} />
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button
              fullWidth variant="contained" startIcon={<Save />}
              disabled={paisId === '' || !fecha || crear.isPending}
              onClick={() => { setMsg(''); crear.mutate(); }}
            >
              Agregar
            </Button>
          </Grid>
        </Grid>

        {msg && <Alert severity={msg.startsWith('❌') ? 'error' : 'success'} sx={{ mt: 2 }}>{msg}</Alert>}

        <Divider sx={{ my: 2 }} />

        <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 280 }}>
          <Table size="small" stickyHeader>
            <TableHead>
              <TableRow>
                {['Fecha', 'Nombre'].map((h) => (
                  <TableCell key={h} sx={{ fontWeight: 700, bgcolor: 'grey.100' }}>{h}</TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {paisId === '' ? (
                <TableRow><TableCell colSpan={2} align="center" sx={{ color: 'text.secondary', py: 3 }}>Selecciona un país</TableCell></TableRow>
              ) : isLoading ? (
                <TableRow><TableCell colSpan={2} align="center">Cargando…</TableCell></TableRow>
              ) : (feriados || []).length === 0 ? (
                <TableRow><TableCell colSpan={2} align="center" sx={{ color: 'text.secondary', py: 3 }}>Sin feriados registrados</TableCell></TableRow>
              ) : (
                (feriados || []).map((f: any) => (
                  <TableRow key={f.id} hover>
                    <TableCell>{f.fecha}</TableCell>
                    <TableCell>{f.nombre || '—'}</TableCell>
                  </TableRow>
                ))
              )}
            </TableBody>
          </Table>
        </TableContainer>
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Bloque 3 — Carga de Excel individual (Target_Medicos / Fact_Visitas)
// ─────────────────────────────────────────────────────────────────────────
function CargaArchivoCard({
  titulo, descripcion, endpoint, columnasInfo, mostrarOmitidos, advertenciaNoIdempotente,
}: {
  titulo: string;
  descripcion: string;
  endpoint: string;
  columnasInfo: string;
  mostrarOmitidos: boolean;
  advertenciaNoIdempotente?: boolean;
}) {
  const { data: paises } = usePaises();
  const [paisId, setPaisId] = useState<string | ''>('');
  const [cicloId, setCicloId] = useState<number | ''>('');
  const [modo, setModo] = useState<'SIMULACION' | 'PRODUCCION'>('SIMULACION');
  const [file, setFile] = useState<File | null>(null);
  const [resultado, setResultado] = useState<any>(null);
  const [msg, setMsg] = useState('');

  useAutoSelectRD(paises, paisId, setPaisId);
  const { data: ciclos } = useCiclos(paisId);

  const enviar = useMutation({
    mutationFn: () => {
      const form = new FormData();
      form.append('ciclo_id', String(cicloId));
      form.append('modo', modo);
      form.append('archivo', file as File);
      return api.post(`/cobertura-predictiva/${endpoint}`, form, {
        headers: { 'Content-Type': 'multipart/form-data' },
      }).then((r) => r.data);
    },
    onSuccess: (data) => {
      setResultado(data);
      setMsg(
        modo === 'PRODUCCION'
          ? `✅ Carga a producción completada — ${data.insertados} insertados`
          : `✅ Simulación completada — ${data.insertados} se insertarían`
      );
    },
    onError: (e: any) => { setMsg(`❌ ${e.response?.data?.detail || e.message}`); setResultado(null); },
  });

  return (
    <Card elevation={2} sx={{ borderRadius: 3, mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <CloudUpload color="primary" />
          <Typography variant="h6" fontWeight={600}>{titulo}</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={1}>{descripcion}</Typography>
        <Typography variant="caption" color="text.secondary" display="block" mb={2}>
          Columnas reconocidas: {columnasInfo}
        </Typography>
        {advertenciaNoIdempotente && (
          <Alert severity="warning" sx={{ mb: 2 }}>
            Esta carga NO es idempotente: es una bitácora de eventos. Cargar el mismo archivo dos veces duplica las filas.
          </Alert>
        )}

        <Grid container spacing={2} alignItems="center">
          <Grid item xs={12} sm={2.5}>
            <FormControl fullWidth size="small">
              <InputLabel>País</InputLabel>
              <Select
                label="País" value={paisId}
                onChange={(e) => { setPaisId(e.target.value); setCicloId(''); }}
              >
                {(paises || []).map((p) => (
                  <MenuItem key={p.id} value={p.codigo}>{p.codigo} — {p.nombre}</MenuItem>
                ))}
              </Select>
            </FormControl>
          </Grid>
          <Grid item xs={12} sm={2.5}>
            <TextField
              select fullWidth size="small" label="Ciclo" value={cicloId} disabled={paisId === ''}
              onChange={(e) => setCicloId(e.target.value === '' ? '' : Number(e.target.value))}
            >
              {(ciclos || []).map((c) => (
                <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre} {c.cerrado ? '(cerrado)' : ''}</MenuItem>
              ))}
            </TextField>
          </Grid>
          <Grid item xs={12} sm={2}>
            <TextField select fullWidth size="small" label="Modo" value={modo} onChange={(e) => setModo(e.target.value as any)}>
              <MenuItem value="SIMULACION">Simulación</MenuItem>
              <MenuItem value="PRODUCCION">Producción</MenuItem>
            </TextField>
          </Grid>
          <Grid item xs={12} sm={3}>
            <Button variant="outlined" component="label" startIcon={<CloudUpload />} fullWidth size="small">
              {file ? file.name : 'Seleccionar .xlsx'}
              <input
                type="file" accept=".xlsx,.xls" hidden
                onChange={(e) => { setFile(e.target.files?.[0] || null); setResultado(null); setMsg(''); }}
              />
            </Button>
          </Grid>
          <Grid item xs={12} sm={2}>
            <Button
              fullWidth variant="contained" color={modo === 'PRODUCCION' ? 'error' : 'warning'}
              disabled={!file || cicloId === '' || enviar.isPending}
              onClick={() => { setMsg(''); enviar.mutate(); }}
            >
              {enviar.isPending ? 'Cargando…' : (modo === 'PRODUCCION' ? 'Cargar' : 'Validar')}
            </Button>
          </Grid>
        </Grid>

        {msg && <Alert severity={msg.startsWith('❌') ? 'error' : 'success'} sx={{ mt: 2 }}>{msg}</Alert>}

        {resultado && (
          <Box sx={{ mt: 2 }}>
            <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', mb: 1 }}>
              <Chip label={`Total filas: ${resultado.total_filas}`} />
              <Chip label={`Insertados: ${resultado.insertados}`} color="success" />
              {mostrarOmitidos && <Chip label={`Omitidos: ${resultado.omitidos}`} />}
              <Chip label={`Errores: ${resultado.total_errores}`} color={resultado.total_errores > 0 ? 'error' : 'default'} />
              {resultado.total_advertencias > 0 && (
                <Chip label={`Advertencias: ${resultado.total_advertencias}`} color="warning" />
              )}
            </Box>
            {resultado.errores?.length > 0 && (
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 220, mb: resultado.advertencias?.length ? 1 : 0 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow><TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100' }}>Detalle de errores (máx. 50)</TableCell></TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.errores.map((e: string, i: number) => (
                      <TableRow key={i}><TableCell sx={{ color: 'error.main' }}>{e}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
            {resultado.advertencias?.length > 0 && (
              <TableContainer component={Paper} variant="outlined" sx={{ maxHeight: 220 }}>
                <Table size="small" stickyHeader>
                  <TableHead>
                    <TableRow><TableCell sx={{ fontWeight: 700, bgcolor: 'grey.100' }}>Advertencias de consistencia PAIS_ID/LINEA_ID (máx. 50)</TableCell></TableRow>
                  </TableHead>
                  <TableBody>
                    {resultado.advertencias.map((a: string, i: number) => (
                      <TableRow key={i}><TableCell sx={{ color: 'warning.main' }}>{a}</TableCell></TableRow>
                    ))}
                  </TableBody>
                </Table>
              </TableContainer>
            )}
          </Box>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Bloque 4 — Carga Excel combinada (todas las hojas en un solo archivo)
// ─────────────────────────────────────────────────────────────────────────
function CargaExcelCombinadaCard() {
  const [file, setFile] = useState<File | null>(null);
  const [paisCodigo, setPaisCodigo] = useState('DO');
  const [cicloCodigo, setCicloCodigo] = useState('');
  const [calcular, setCalcular] = useState(true);
  const [resultado, setResultado] = useState<any>(null);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // Ciclos existentes en cat.DimCiclo para el país seleccionado
  const { data: ciclosCat } = useQuery({
    queryKey: ['ciclos-cat', paisCodigo],
    queryFn: () =>
      api.get('/cobertura-predictiva/cat/ciclos', { params: { pais_codigo: paisCodigo } })
        .then(r => r.data as { codigo_ciclo: string; fecha_inicio: string; fecha_fin: string }[]),
    enabled: !!paisCodigo,
  });

  const handleUpload = async () => {
    if (!file) return;
    setUploading(true); setError(null); setResultado(null);
    try {
      const fd = new FormData();
      fd.append('archivo', file);
      fd.append('pais_codigo', paisCodigo);
      if (cicloCodigo) fd.append('ciclo_codigo', cicloCodigo);
      fd.append('calcular_al_cargar', String(calcular));
      const res = await api.post('/cobertura-predictiva/cat/cargar-excel', fd, {
        headers: { 'Content-Type': 'multipart/form-data' },
      });
      setResultado(res.data);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Error al cargar el archivo');
    } finally {
      setUploading(false);
    }
  };

  return (
    <Card sx={{ mb: 3 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <UploadFile color="primary" />
          <Typography variant="h6" fontWeight={700}>Cargar Excel de Cobertura Predictiva</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Sube el archivo Excel con los datos de cobertura. Puede contener hojas:{' '}
          <b>COB_DIM_CICLO</b>, <b>COB_DIM_CALENDARIO</b>, <b>Target_Medicos</b> y <b>Fact_Visitas</b>.
          Si el archivo no incluye la hoja de ciclo, selecciona el ciclo de referencia.
        </Typography>
        <Stack spacing={2} maxWidth={520}>
          <Stack direction="row" spacing={2}>
            <FormControl size="small" sx={{ flex: 1 }}>
              <InputLabel>País</InputLabel>
              <Select value={paisCodigo} label="País"
                onChange={e => { setPaisCodigo(e.target.value); setCicloCodigo(''); }}>
                <MenuItem value="DO">DO — República Dominicana</MenuItem>
                <MenuItem value="CR">CR — Costa Rica</MenuItem>
                <MenuItem value="GT">GT — Guatemala</MenuItem>
                <MenuItem value="PA">PA — Panamá</MenuItem>
              </Select>
            </FormControl>
            <TextField
              size="small" sx={{ flex: 1 }}
              label="Ciclo de referencia"
              placeholder="ej. C06-2026 (opcional)"
              value={cicloCodigo}
              onChange={e => setCicloCodigo(e.target.value)}
              helperText={(ciclosCat || []).length > 0
                ? `Ciclos disponibles: ${(ciclosCat || []).map(c => c.codigo_ciclo).join(', ')}`
                : 'Déjalo vacío si el Excel incluye la hoja COB_DIM_CICLO'
              }
            />
          </Stack>
          <Box
            sx={{
              border: '2px dashed #90caf9', borderRadius: 2, p: 3, textAlign: 'center',
              bgcolor: file ? '#e8f5e9' : '#f8f9fa', cursor: 'pointer',
              '&:hover': { bgcolor: '#e3f2fd' },
            }}
            onClick={() => document.getElementById('cob-admin-upload-input')?.click()}
          >
            <UploadFile sx={{ fontSize: 40, color: file ? '#2e7d32' : '#90caf9', mb: 1 }} />
            <Typography variant="body2" fontWeight={600} color={file ? '#2e7d32' : 'text.secondary'}>
              {file ? file.name : 'Haz clic o arrastra el archivo .xlsx aquí'}
            </Typography>
            {file && (
              <Typography variant="caption" color="text.secondary">
                {(file.size / 1024).toFixed(1)} KB
              </Typography>
            )}
            <input
              id="cob-admin-upload-input" type="file" accept=".xlsx"
              style={{ display: 'none' }}
              onChange={e => setFile(e.target.files?.[0] ?? null)}
            />
          </Box>
          <Box display="flex" alignItems="center" gap={1}>
            <input
              type="checkbox" id="admin-calc-al-cargar"
              checked={calcular} onChange={e => setCalcular(e.target.checked)}
            />
            <label htmlFor="admin-calc-al-cargar">
              <Typography variant="body2">Calcular KPIs automáticamente tras cargar</Typography>
            </label>
          </Box>
          <Button
            variant="contained"
            startIcon={uploading ? <CircularProgress size={18} color="inherit" /> : <CloudUpload />}
            onClick={handleUpload}
            disabled={!file || uploading}
            sx={{ alignSelf: 'flex-start' }}
          >
            {uploading ? 'Cargando…' : 'Cargar y procesar'}
          </Button>
        </Stack>
        {error && <Alert severity="error" sx={{ mt: 2 }}>{error}</Alert>}
        {resultado && (
          <Alert severity={resultado.ok ? 'success' : 'error'} sx={{ mt: 2 }}>
            <Typography variant="body2" fontWeight={700}>{resultado.mensaje}</Typography>
            {resultado.ok && (
              <Box mt={1}>
                {[
                  ['Ciclos', resultado.ciclos ?? 0],
                  ['Fechas de calendario', resultado.calendario ?? 0],
                  ['Médicos programados', resultado.target ?? 0],
                  ['Visitas', resultado.visitas ?? 0],
                ].map(([k, v]) => (
                  <Typography key={String(k)} variant="caption" display="block">• {k}: {v}</Typography>
                ))}
                {resultado.calculo_sp?.length > 0 && (
                  <Typography variant="caption" display="block">
                    • KPIs calculados para {resultado.calculo_sp.length} ciclo(s)
                  </Typography>
                )}
                {resultado.errores?.length > 0 && (
                  <Typography variant="caption" color="warning.main" display="block">
                    {resultado.errores.length} advertencia(s)
                  </Typography>
                )}
              </Box>
            )}
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────────────────
// Bloque 5 — Reset / Limpiar datos del país
// ─────────────────────────────────────────────────────────────────────────
function ResetDatosCard() {
  const [paisCodigo, setPaisCodigo] = useState('DO');
  const [incluirDims, setIncluirDims] = useState(false);
  const [confirm, setConfirm] = useState(false);
  const [resetting, setResetting] = useState(false);
  const [result, setResult] = useState<any>(null);
  const [error, setError] = useState<string | null>(null);

  const handleReset = async () => {
    setResetting(true); setError(null); setResult(null);
    try {
      const p = new URLSearchParams({ pais_codigo: paisCodigo, incluir_dims: String(incluirDims) });
      const res = await api.delete(`/cobertura-predictiva/cat/datos?${p}`);
      setResult(res.data);
      setConfirm(false);
    } catch (e: any) {
      setError(e.response?.data?.detail ?? 'Error al limpiar los datos');
    } finally {
      setResetting(false);
    }
  };

  return (
    <Card sx={{ mb: 3, border: '1px solid #ffcdd2', bgcolor: '#fff8f8' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 0.5 }}>
          <DeleteForever sx={{ color: '#b71c1c' }} />
          <Typography variant="h6" fontWeight={700} color="#b71c1c">
            Limpiar datos para recargar desde cero
          </Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>
          Elimina todos los registros de Cobertura Predictiva del país seleccionado
          (KPIs, visitas, médicos programados) para cargar información nueva sin duplicados.
        </Typography>
        <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" mb={2}>
          <FormControl size="small" sx={{ minWidth: 200 }}>
            <InputLabel>País a limpiar</InputLabel>
            <Select
              value={paisCodigo} label="País a limpiar"
              onChange={e => { setPaisCodigo(e.target.value); setConfirm(false); }}
            >
              <MenuItem value="DO">DO — República Dominicana</MenuItem>
              <MenuItem value="CR">CR — Costa Rica</MenuItem>
              <MenuItem value="GT">GT — Guatemala</MenuItem>
              <MenuItem value="PA">PA — Panamá</MenuItem>
            </Select>
          </FormControl>
          <Box display="flex" alignItems="center" gap={0.5}>
            <input
              type="checkbox" id="incl-dims-admin"
              checked={incluirDims} onChange={e => setIncluirDims(e.target.checked)}
            />
            <label htmlFor="incl-dims-admin">
              <Typography variant="body2" color="text.secondary">
                También limpiar dimensiones (médicos, ciclos, VMs, especialidades)
              </Typography>
            </label>
          </Box>
        </Stack>

        {!confirm ? (
          <Button
            variant="outlined" color="error" size="small"
            startIcon={<DeleteForever />}
            onClick={() => setConfirm(true)}
          >
            Eliminar datos del país {paisCodigo}…
          </Button>
        ) : (
          <Alert
            severity="warning" sx={{ mb: 1 }}
            action={
              <Stack direction="row" spacing={1}>
                <Button
                  color="error" size="small" variant="contained"
                  onClick={handleReset} disabled={resetting}
                  startIcon={resetting ? <CircularProgress size={14} color="inherit" /> : undefined}
                >
                  {resetting ? 'Eliminando…' : 'Confirmar borrado'}
                </Button>
                <Button size="small" onClick={() => setConfirm(false)}>Cancelar</Button>
              </Stack>
            }
          >
            <b>Esta acción es irreversible.</b> Se borrarán todos los datos del país <b>{paisCodigo}</b>
            {incluirDims ? ' incluyendo dimensiones' : ' (dimensiones conservadas)'}.
          </Alert>
        )}
        {error && <Alert severity="error" sx={{ mt: 1 }}>{error}</Alert>}
        {result?.ok && (
          <Alert severity="success" sx={{ mt: 1 }}>
            <Typography variant="body2" fontWeight={700}>Datos eliminados correctamente</Typography>
            <Box mt={0.5}>
              {Object.entries(result.filas_eliminadas as Record<string, number>).map(([tabla, n]) => (
                <Typography key={tabla} variant="caption" display="block">• {tabla}: {n} filas</Typography>
              ))}
            </Box>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

// ── Componente principal ──────────────────────────────────────────
export default function CoberturaPredictivaAdmin() {
  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Mantenimiento del módulo Cobertura Predictiva (4DX). Configura la meta y feriados,
        luego sube el Excel con todos los datos en un solo paso.
      </Typography>

      <ParametrosCoberturaCard />
      <FeriadosCard />
      <CargaExcelCombinadaCard />
      <ResetDatosCard />
    </Box>
  );
}
