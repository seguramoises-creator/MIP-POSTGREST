import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Grid, Card, CardContent, Button, Divider, TextField,
  MenuItem, Chip,
} from '@mui/material';
import { PictureAsPdf, TableChart, Download } from '@mui/icons-material';
import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';

interface FiltrosReporte {
  paisId: string;
  cicloId: string;
  tipoRanking: string;
}

function ReporteCard({
  title, desc, endpoint, tipo, filtros, extraParams,
}: {
  title: string; desc: string; endpoint: string; tipo: 'pdf' | 'excel';
  filtros: FiltrosReporte; extraParams?: Record<string, any>;
}) {
  const [exportando, setExportando] = useState(false);

  const handleExport = async () => {
    setExportando(true);
    try {
      const r = await api.get(endpoint, {
        responseType: 'blob',
        params: {
          ...(filtros.paisId && { pais_codigo: filtros.paisId }),
          ...(filtros.cicloId && { ciclo_id: filtros.cicloId }),
          ...extraParams,
        },
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = `${title.replace(/\s+/g, '_').toLowerCase()}.${tipo === 'pdf' ? 'pdf' : 'xlsx'}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      alert('No se pudo generar el archivo. Verifique que existan datos para los filtros seleccionados.');
    } finally {
      setExportando(false);
    }
  };

  return (
    <Card elevation={2} sx={{ borderRadius: 2, height: '100%' }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          {tipo === 'pdf' ? <PictureAsPdf color="error" /> : <TableChart color="success" />}
          <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>{desc}</Typography>
        <Button variant="outlined" size="small" startIcon={<Download />} onClick={handleExport} disabled={exportando}>
          {exportando ? 'Generando…' : `Exportar ${tipo.toUpperCase()}`}
        </Button>
      </CardContent>
    </Card>
  );
}

function ProximamenteCard({ title, desc }: { title: string; desc: string }) {
  return (
    <Card elevation={1} sx={{ borderRadius: 2, height: '100%', opacity: 0.7 }}>
      <CardContent>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mb: 1 }}>
          <TableChart color="disabled" />
          <Typography variant="subtitle1" fontWeight={600}>{title}</Typography>
        </Box>
        <Typography variant="body2" color="text.secondary" mb={2}>{desc}</Typography>
        <Chip label="Próximamente" size="small" variant="outlined" />
      </CardContent>
    </Card>
  );
}

export default function Reportes() {
  const paisId = useCicloStore((s) => s.paisCodigo) || '';
  const [cicloId, setCicloId] = useState('');
  const [tipoRanking, setTipoRanking] = useState('MENSUAL');

  const { data: paises } = useQuery({
    queryKey: ['paises'],
    queryFn: () => api.get('/admin/paises').then((r) => r.data),
  });
  const { data: ciclos } = useQuery({
    queryKey: ['ciclos', paisId],
    queryFn: () => api.get('/admin/ciclos', { params: { ...(paisId && { pais_codigo: paisId }) } }).then((r) => r.data),
  });
  const paisNombrePorId: Record<number, string> = Object.fromEntries((paises || []).map((p: any) => [p.id, p.nombre]));
  const cicloLabel = (c: any) => paisId ? c.nombre : `${c.nombre} — ${paisNombrePorId[c.pais_codigo] || 'País desconocido'}`;

  // El país ahora viene del contexto global (CicloPaisHeader) — al cambiar, se limpia el
  // ciclo seleccionado para que el efecto de más abajo elija el último ciclo con datos del país nuevo.
  useEffect(() => {
    setCicloId('');
  }, [paisId]);

  // Obtener el último ciclo con datos reales
  const { data: _cicloEf } = useQuery({
    queryKey: ['ciclo-ef', paisId],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisId && { pais_codigo: paisId }), size: 1, page: 1 },
    }).then(r => r.data?.ciclo_efectivo ?? null),
    enabled: !!paisId,
    staleTime: 60_000,
  });
  // ── Auto-seleccionar el último ciclo CON DATOS ─────────────────────
  useEffect(() => {
    if (!_cicloEf || cicloId) return;
    setCicloId(String(_cicloEf));
  }, [_cicloEf]); // eslint-disable-line react-hooks/exhaustive-deps


  const filtros: FiltrosReporte = { paisId, cicloId, tipoRanking };

  return (
    <Box>
      <Typography variant="h5" fontWeight={700} mb={0.5}>Reportes</Typography>
      <Typography variant="body2" color="text.secondary" mb={3}>
        Exportación de datos en PDF y Excel — los reportes se generan con los filtros seleccionados abajo
      </Typography>

      {/* Filtros globales aplicados a todas las exportaciones */}
      <Card elevation={1} sx={{ mb: 3, borderRadius: 2 }}>
        <CardContent>
          <Grid container spacing={2} alignItems="center">
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Ciclo" value={cicloId} onChange={(e) => setCicloId(e.target.value)}>
                <MenuItem value="">Todos los ciclos</MenuItem>
                {(ciclos || []).map((c: any) => <MenuItem key={c.id} value={c.id}>{cicloLabel(c)}</MenuItem>)}
              </TextField>
            </Grid>
            <Grid item xs={12} sm={4}>
              <TextField select fullWidth size="small" label="Tipo de ranking" value={tipoRanking} onChange={(e) => setTipoRanking(e.target.value)}>
                {['MENSUAL', 'TRIMESTRAL', 'ANUAL', 'REGIONAL'].map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
              </TextField>
            </Grid>
          </Grid>
        </CardContent>
      </Card>

      <Typography variant="h6" fontWeight={600} mb={2}>Rankings</Typography>
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} sm={6} md={3}>
          <ReporteCard title="Ranking — Excel" desc="Listado completo con posiciones y scores" endpoint="/exportacion/ranking/excel" tipo="excel" filtros={filtros} extraParams={{ tipo_ranking: tipoRanking }} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <ReporteCard title="Ranking — PDF" desc="Reporte imprimible de posiciones" endpoint="/exportacion/ranking/pdf" tipo="pdf" filtros={filtros} extraParams={{ tipo_ranking: tipoRanking }} />
        </Grid>
      </Grid>

      <Divider sx={{ my: 2 }} />
      <Typography variant="h6" fontWeight={600} mb={2}>Reconocimiento</Typography>
      <Grid container spacing={2} mb={3}>
        <Grid item xs={12} sm={6} md={3}>
          <ReporteCard title="Reconocimientos — Excel" desc="Premios otorgados y certificados" endpoint="/exportacion/reconocimientos/excel" tipo="excel" filtros={filtros} />
        </Grid>
        <Grid item xs={12} sm={6} md={3}>
          <ReporteCard title="Reconocimientos — PDF" desc="Reporte imprimible de premiados" endpoint="/exportacion/reconocimientos/pdf" tipo="pdf" filtros={filtros} />
        </Grid>
      </Grid>

      <Divider sx={{ my: 2 }} />
      <Typography variant="h6" fontWeight={600} mb={1}>Productividad, Cobertura Predictiva y Capacitación</Typography>
      <Typography variant="body2" color="text.secondary" mb={2}>
        Estos módulos aún no cuentan con un endpoint de exportación dedicado — por ahora puede consultarlos
        en sus respectivas vistas (Productividad, Cobertura Predictiva, Capacitación).
      </Typography>
      <Grid container spacing={2}>
        <Grid item xs={12} sm={6} md={3}><ProximamenteCard title="Productividad — Excel" desc="KPIs detallados por RM y ciclo" /></Grid>
        <Grid item xs={12} sm={6} md={3}><ProximamenteCard title="Cobertura Predictiva — Excel" desc="Cobertura médica, ritmo de visitas y PSP (4DX)" /></Grid>
        <Grid item xs={12} sm={6} md={3}><ProximamenteCard title="Capacitación — Excel" desc="Asistencia, calificaciones y aprobación" /></Grid>
      </Grid>
    </Box>
  );
}
