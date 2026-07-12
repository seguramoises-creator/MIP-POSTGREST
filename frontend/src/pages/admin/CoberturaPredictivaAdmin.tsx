/**
 * CoberturaPredictivaAdmin.tsx — Mantenimiento del módulo
 * "Cobertura Predictiva y Ritmo de Ejecución" (4DX).
 *
 * El dashboard se calcula EN VIVO desde el módulo Visita:
 *   - Programado (J) = Vistas planeadas en Planeación del Ciclo (Visita.PlaneacionCiclo)
 *   - Realizado (L/M) = visitas registradas en Registrar Visita (Visita.FactVisita)
 *   - Días hábiles (N) = Ciclo.dias_laborables (configuración del ciclo)
 * Por eso NO hay carga por Excel ni gestión de feriados aquí: esos flujos
 * (target/visitas por importación y DIM_Feriado) eran del 4DX legacy y se retiraron.
 *
 * Lo único configurable aquí es la Meta de Cobertura (% objetivo) por
 * país/línea/ciclo → DIM_ParametroCobertura (POST /cobertura-predictiva/parametros).
 */
import { useEffect, useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, Grid, Button, TextField, MenuItem,
  Select, FormControl, InputLabel, Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, Alert, Divider, Stack, CircularProgress,
} from '@mui/material';
import { Save, TrendingUp } from '@mui/icons-material';
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
// Componente principal — solo la Meta de Cobertura. El "programado" y el
// "realizado" se alimentan EN VIVO de Planeación + Registrar Visita; los días
// hábiles salen de la configuración del ciclo. Se retiraron las tarjetas de
// carga por Excel (target/visitas) y de feriados (legacy 4DX por importación).
// ─────────────────────────────────────────────────────────────────────────
export default function CoberturaPredictivaAdmin() {
  return (
    <Box>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Mantenimiento del módulo Cobertura Predictiva (4DX). Configura la meta de cobertura.
        El "programado" y el "realizado" se alimentan EN VIVO de Planeación del Ciclo y de
        Registrar Visita; los días hábiles salen de la configuración del ciclo (dias_laborables).
      </Typography>

      <ParametrosCoberturaCard />
    </Box>
  );
}
