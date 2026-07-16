/**
 * SaludCiclo — panel de salud/completitud del ciclo vigente.
 * Muestra ventana temporal (días/estado), completitud de planeación, cobertura del
 * panel, configuración (parrilla/costo) y alerta de ciclos vencidos sin cerrar.
 * Consume GET /admin/ciclos/{id}/salud. Usa el ciclo EN CONSULTA del contexto global.
 */
import { useQuery } from '@tanstack/react-query';
import {
  Paper, Typography, Box, Grid, LinearProgress, Chip, Stack, Alert,
} from '@mui/material';
import {
  EventAvailable, FactCheck, TrackChanges, Campaign, Paid, Warning, CheckCircle, Cancel,
} from '@mui/icons-material';
import { api } from '../services/api';
import { useCicloStore } from '../store/ciclo.store';

type Salud = {
  nombre: string; estado: string; vencido: boolean;
  fecha_inicio: string; fecha_fin: string;
  dias_totales: number; dias_transcurridos: number; dias_restantes: number; progreso_pct: number;
  vm_total: number; vm_con_planeacion: number; vm_sin_planeacion: number; pct_planeacion: number;
  medicos_panel: number; medicos_registrados: number; medicos_fuera_de_ciclo: number;
  medicos_visitados: number; medicos_sin_visitar: number; pct_cobertura: number;
  visitas_registradas: number; parrilla_publicada: boolean; costo_configurado: boolean;
  ciclos_vencidos_sin_cerrar: number;
};

const ESTADO_COLOR: Record<string, 'success' | 'warning' | 'default' | 'info'> = {
  VIGENTE: 'success', POR_CERRAR: 'warning', PLANIFICADO: 'info', CERRADO: 'default',
};

function Metrica({ icon, label, valor, sub, color = 'text.primary', pct }:
  { icon: React.ReactNode; label: string; valor: string; sub?: string; color?: string; pct?: number }) {
  return (
    <Box sx={{ p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 2, height: '100%' }}>
      <Stack direction="row" spacing={0.75} alignItems="center" sx={{ color: 'text.secondary', mb: 0.25 }}>
        {icon}<Typography variant="caption" fontWeight={700}>{label}</Typography>
      </Stack>
      <Typography variant="h6" fontWeight={800} sx={{ color }}>{valor}</Typography>
      {typeof pct === 'number' && (
        <LinearProgress variant="determinate" value={Math.min(100, pct)}
          sx={{ height: 6, borderRadius: 3, my: 0.5,
            '& .MuiLinearProgress-bar': { bgcolor: pct >= 80 ? '#2e7d32' : pct >= 50 ? '#f57c00' : '#c62828' } }} />
      )}
      {sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}
    </Box>
  );
}

export default function SaludCiclo() {
  const cicloId = useCicloStore((s) => s.cicloId);
  const { data } = useQuery<Salud>({
    queryKey: ['ciclo-salud', cicloId],
    queryFn: () => api.get(`/admin/ciclos/${cicloId}/salud`).then((r) => r.data),
    enabled: !!cicloId,
    staleTime: 60000,
  });
  if (!cicloId || !data) return null;

  const chip = (ok: boolean, si: string, no: string) =>
    <Chip size="small" icon={ok ? <CheckCircle /> : <Cancel />} color={ok ? 'success' : 'default'}
          variant={ok ? 'filled' : 'outlined'} label={ok ? si : no} />;

  return (
    <Paper variant="outlined" sx={{ p: 2, borderRadius: 2, mb: 2 }}>
      <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }} flexWrap="wrap" useFlexGap>
        <FactCheck fontSize="small" color="action" />
        <Typography variant="subtitle1" fontWeight={700}>Salud del Ciclo</Typography>
        <Chip size="small" label={data.nombre} variant="outlined" />
        <Chip size="small" color={ESTADO_COLOR[data.estado] ?? 'default'} label={data.estado} />
        <Typography variant="caption" color="text.secondary" sx={{ ml: 'auto' }}>
          {data.fecha_inicio} a {data.fecha_fin}
        </Typography>
      </Stack>

      {data.ciclos_vencidos_sin_cerrar > 0 && (
        <Alert severity="warning" sx={{ mb: 1.5 }}>
          Hay <b>{data.ciclos_vencidos_sin_cerrar}</b> ciclo(s) vencido(s) sin cerrar en este país.
          Ciérralos para mantener un único ciclo vigente.
        </Alert>
      )}
      {data.medicos_fuera_de_ciclo > 0 && (
        <Alert severity={data.medicos_panel === 0 ? 'error' : 'warning'} sx={{ mb: 1.5 }}>
          <b>{data.medicos_fuera_de_ciclo.toLocaleString()}</b> de {data.medicos_registrados.toLocaleString()} médicos
          del panel <b>no están vigentes en este ciclo</b> (su ciclo de alta es posterior).
          {data.medicos_panel === 0
            ? ' El panel efectivo es 0: la cobertura saldrá en 0% aunque haya visitas registradas. Corrige el ciclo de alta de los médicos.'
            : ' No cuentan para la cobertura de este ciclo.'}
        </Alert>
      )}
      {data.pct_planeacion < 100 && data.estado !== 'CERRADO' && (
        <Alert severity={data.pct_planeacion < 50 ? 'warning' : 'info'} sx={{ mb: 1.5 }}>
          Planeación incompleta: <b>{data.vm_sin_planeacion}</b> de {data.vm_total} representantes aún no
          cargan su planeación del ciclo.
        </Alert>
      )}

      <Grid container spacing={1.5}>
        <Grid item xs={6} sm={4} md={2.4}>
          <Metrica icon={<EventAvailable sx={{ fontSize: 16 }} />} label="DÍAS HÁBILES"
            valor={`${data.dias_transcurridos}/${data.dias_totales}`} pct={data.progreso_pct}
            sub={`${data.dias_restantes} restantes`} color="#1a237e" />
        </Grid>
        <Grid item xs={6} sm={4} md={2.4}>
          <Metrica icon={<FactCheck sx={{ fontSize: 16 }} />} label="PLANEACIÓN VM"
            valor={`${data.pct_planeacion}%`} pct={data.pct_planeacion}
            sub={`${data.vm_con_planeacion}/${data.vm_total} representantes`}
            color={data.pct_planeacion >= 80 ? '#2e7d32' : '#f57c00'} />
        </Grid>
        <Grid item xs={6} sm={4} md={2.4}>
          <Metrica icon={<TrackChanges sx={{ fontSize: 16 }} />} label="COBERTURA PANEL"
            valor={`${data.pct_cobertura}%`} pct={data.pct_cobertura}
            sub={data.medicos_fuera_de_ciclo > 0
              ? `${data.medicos_visitados}/${data.medicos_panel} vigentes (de ${data.medicos_registrados} cargados)`
              : `${data.medicos_visitados}/${data.medicos_panel} médicos`}
            color={data.medicos_panel === 0 ? '#c62828' : '#00897b'} />
        </Grid>
        <Grid item xs={6} sm={4} md={2.4}>
          <Metrica icon={<Warning sx={{ fontSize: 16 }} />} label="SIN VISITAR"
            valor={data.medicos_sin_visitar.toLocaleString()} sub="médicos pendientes" color="#c62828" />
        </Grid>
        <Grid item xs={12} sm={4} md={2.4}>
          <Box sx={{ p: 1.25, border: '1px solid', borderColor: 'divider', borderRadius: 2, height: '100%' }}>
            <Stack direction="row" spacing={0.75} alignItems="center" sx={{ color: 'text.secondary', mb: 0.75 }}>
              <Campaign sx={{ fontSize: 16 }} /><Typography variant="caption" fontWeight={700}>CONFIGURACIÓN</Typography>
            </Stack>
            <Stack spacing={0.5}>
              {chip(data.parrilla_publicada, 'Parrilla publicada', 'Sin parrilla')}
              <Box><Paid sx={{ fontSize: 0 }} />{chip(data.costo_configurado, 'Costo configurado', 'Sin costo')}</Box>
            </Stack>
          </Box>
        </Grid>
      </Grid>
    </Paper>
  );
}
