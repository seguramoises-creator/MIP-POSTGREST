import { useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Typography, Grid, Card, CardContent,
  Table, TableBody, TableCell, TableContainer,
  TableHead, TableRow, Paper, Chip, CircularProgress,
  Button, Select, MenuItem, Divider, Tooltip,
} from '@mui/material';
import { AutoAwesome, Download } from '@mui/icons-material';
import { useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';

/* ── utilidades ───────────────────────────────────────────── */
function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontSize: 11, fontWeight: 700, color: 'text.secondary',
      textTransform: 'uppercase', letterSpacing: 0.8, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

function flagColor(v: number): string {
  if (v >= 90) return '#2e7d32';
  if (v >= 80) return '#f57f17';
  return '#c62828';
}

function Flag({ value }: { value: number }) {
  const color = flagColor(value);
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 1.4 }}>
      {/* banderín SVG */}
      <svg width="20" height="22" viewBox="0 0 14 16">
        <polygon points="2,1 13,6 2,11" fill={color} />
        <line x1="2" y1="1" x2="2" y2="16" stroke={color} strokeWidth="1.5" />
      </svg>
      <Typography sx={{ fontWeight: 800, fontSize: 18, color, lineHeight: 1, letterSpacing: '0.3px' }}>
        {value.toFixed(1)}
      </Typography>
    </Box>
  );
}

/* ── pódium ───────────────────────────────────────────────── */
const PODIUM_CFG = [
  { pos: 1, icon: '🏆', label: 'Oro',    color: '#e65100', border: '#f9a825', bg: 'linear-gradient(160deg,#fffde7,#fff8e1)', shadow: '#f9a82566', large: true },
  { pos: 2, icon: '🥈', label: 'Plata',  color: '#455a64', border: '#90a4ae', bg: 'linear-gradient(160deg,#EDE9E4,#f5f5f5)', shadow: '#90a4ae44' },
  { pos: 3, icon: '🥉', label: 'Bronce', color: '#bf360c', border: '#ff7043', bg: 'linear-gradient(160deg,#fff3e0,#fbe9e7)', shadow: '#ff704344' },
];

function PodiumCard({ cfg, rm }: { cfg: typeof PODIUM_CFG[0]; rm?: any }) {
  const large  = !!cfg.large;
  const nombre = rm?.rm_nombre ?? null;
  const score  = rm ? Number(rm.score_total ?? 0) : null;
  const linea  = rm?.linea_nombre  && rm.linea_nombre  !== '—' ? rm.linea_nombre  : null;
  const ger    = rm?.gerente_nombre && rm.gerente_nombre !== '—'
    ? (() => { const p = (rm.gerente_nombre as string).split(' ');
               return p.length > 1 ? p[p.length-1] + ', ' + p[0][0] + '.' : rm.gerente_nombre; })()
    : null;
  return (
    <Card elevation={large ? 6 : 3} sx={{
      borderRadius: 3, background: cfg.bg, border: `2px solid ${cfg.border}`,
      minHeight: large ? 220 : 176,
      display: 'flex', flexDirection: 'column', justifyContent: 'center',
      alignItems: 'center', textAlign: 'center', px: 2, py: 2,
      boxShadow: `0 ${large ? 10 : 4}px ${large ? 36 : 14}px ${cfg.shadow}`,
      transform: large ? 'scale(1.05)' : 'none',
    }}>
      <Typography sx={{ fontSize: large ? 52 : 38, lineHeight: 1, mb: 0.5 }}>{cfg.icon}</Typography>
      <Typography sx={{ fontWeight: 800, fontSize: large ? 15 : 13, color: cfg.color,
        textTransform: 'uppercase', letterSpacing: '0.8px', mb: 0.5 }}>{cfg.label}</Typography>
      {nombre ? (
        <>
          <Typography sx={{ fontWeight: 800, fontSize: large ? 15 : 13, lineHeight: 1.2,
            mb: 0.3, maxWidth: 200 }}>{nombre}</Typography>
          <Typography sx={{ fontWeight: 900, fontSize: large ? 32 : 26, color: cfg.color, lineHeight: 1, mb: 0.4 }}>
            {score!.toFixed(1)}%
          </Typography>
          {linea && <Typography sx={{ fontSize: 11, color: 'text.secondary', fontWeight: 600 }}>{linea}</Typography>}
          {ger   && <Typography sx={{ fontSize: 11, color: 'text.secondary' }}>{ger}</Typography>}
        </>
      ) : (
        <Typography sx={{ fontSize: 12, color: 'text.disabled', mt: 0.5 }}>Sin datos</Typography>
      )}
    </Card>
  );
}

/* ── página principal ─────────────────────────────────────── */
export default function Reconocimiento() {
  const queryClient = useQueryClient();
  const paisId = useCicloStore((s) => s.paisCodigo) || '';
  const [cicloId,     setCicloId]     = useState<number | ''>('');
  const [descargando, setDescargando] = useState<number | null>(null);
  const [generando,   setGenerando]   = useState(false);
  const [mensaje,     setMensaje]     = useState<string | null>(null);

  const { data: catalogos } = useQuery({
    queryKey: ['rec-catalogos', paisId],
    queryFn: () => api.get('/dashboard/catalogos', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data),
  });
  const ciclos: any[] = catalogos?.ciclos  ?? [];

  // El país ahora viene del contexto global (CicloPaisHeader) — al cambiar, se limpia el
  // ciclo seleccionado para que el efecto de más abajo elija el último ciclo con datos del país nuevo.
  useEffect(() => {
    setCicloId('');
  }, [paisId]);



  /* Top 10 del ranking */
  const { data: rankData, isLoading: loadingRank } = useQuery({
    queryKey: ['rec-ranking-top10', paisId, cicloId],
    queryFn: () => api.get('/ranking', {
      params: {
        ...(paisId  && { pais_codigo: paisId  }),
        ...(cicloId && { ciclo_id: Number(cicloId) }),
        size: 10, page: 1,
      },
    }).then(r => r.data),
    retry: 1,
  });
  // ── Auto-seleccionar el último ciclo CON DATOS (ciclo_efectivo del ranking) ─
  useEffect(() => {
    if (!rankData?.ciclo_efectivo || cicloId) return;
    setCicloId(rankData.ciclo_efectivo);
  }, [rankData?.ciclo_efectivo]); // eslint-disable-line react-hooks/exhaustive-deps

  const top10: any[] = rankData?.items?.slice(0, 10) ?? [];
  const top3          = top10.slice(0, 3);

  const cicloEfectivo = rankData?.ciclo_efectivo ?? null;
  const cicloObj = (() => {
    const cid = cicloId || cicloEfectivo;
    if (!cid) return null;
    return ciclos.find((c: any) => c.id === cid) ?? null;
  })();
  const cicloNombre = cicloObj ? (cicloObj.nombre_canonico || cicloObj.nombre) : null;
  const cicloAnio   = cicloObj?.anio ?? new Date().getFullYear();
  const cicloNum    = cicloObj?.numero ?? '';

  /* Reconocimientos formales */
  const { data: recData, isLoading: loadingRec } = useQuery({
    queryKey: ['reconocimientos', paisId, cicloId],
    queryFn: () => api.get('/reconocimiento', {
      params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: cicloId }) },
    }).then(r => r.data),
    retry: 1,
  });
  const recItems: any[] = recData || [];

  const handleGenerar = async () => {
    if (!paisId) { setMensaje('Selecciona un país primero.'); return; }
    setGenerando(true); setMensaje(null);
    try {
      await api.post('/reconocimiento/generar-automatico', null, {
        params: { pais_codigo: paisId, ...(cicloId && { ciclo_id: cicloId }) },
      });
      setMensaje('Generación iniciada. La lista se actualizará en unos momentos.');
      setTimeout(() => queryClient.invalidateQueries({ queryKey: ['reconocimientos'] }), 4000);
    } catch (e: any) {
      setMensaje(e?.response?.data?.detail || 'No se pudo iniciar la generación automática.');
    } finally { setGenerando(false); }
  };

  const handleDescargar = async (id: number) => {
    setDescargando(id);
    try {
      const r = await api.get(`/reconocimiento/${id}/certificado`, { responseType: 'blob' });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a'); a.href = url;
      a.download = `certificado_${id}.pdf`; a.click();
      URL.revokeObjectURL(url);
    } catch { alert('El certificado aún no está disponible.'); }
    finally { setDescargando(null); }
  };

  const rmByPos = (pos: number) => top3.find((r: any) => (r.posicion ?? 0) === pos) ?? top3[pos - 1];

  return (
    <Box>
      {/* Encabezado */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 1, mb: 0.5 }}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Reconocimiento</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.3 }}>
            Mapa Integral de Productividad — Top 10 YTD
          </Typography>
        </Box>
        <Tooltip title={!paisId ? 'Selecciona un país primero' : 'Genera reconocimientos para los RMs elegibles'}>
          <span>
            <Button variant="contained" startIcon={<AutoAwesome />}
              onClick={handleGenerar} disabled={generando || !paisId}>
              {generando ? 'Generando…' : 'Generar automáticamente'}
            </Button>
          </span>
        </Tooltip>
      </Box>

      <Divider sx={{ my: 1.5 }} />

      {/* Filtros */}
      <Card elevation={1} sx={{ mb: 3, borderRadius: 2 }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', gap: 3, alignItems: 'center', flexWrap: 'wrap' }}>
            <Box sx={{ width: 200 }}>
              <FilterLabel>Ciclo</FilterLabel>
              <Select size="small" fullWidth value={cicloId}
                onChange={(e) => setCicloId(e.target.value as number | '')}
                displayEmpty disabled={!paisId}>
                <MenuItem value=""><span style={{ opacity: 0.7 }}>{paisId ? 'Último ciclo con datos' : 'Seleccione un país'}</span></MenuItem>
                {ciclos.map((c: any) => <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>)}
              </Select>
            </Box>
            {cicloNombre && (
              <Box sx={{ ml: 'auto' }}>
                <Chip label={'Mostrando: ' + cicloNombre}
                  sx={{ bgcolor: '#686158', color: '#fff', fontWeight: 700, fontSize: 13, height: 32, px: 1 }} />
              </Box>
            )}
          </Box>
        </CardContent>
      </Card>

      {mensaje && (
        <Card elevation={0} sx={{ mb: 2, borderRadius: 2, bgcolor: '#F4F1EE', border: '1px solid #D8D2CB' }}>
          <CardContent sx={{ py: 1.5, '&:last-child': { pb: 1.5 } }}>
            <Typography variant="body2">{mensaje}</Typography>
          </CardContent>
        </Card>
      )}

      {loadingRank ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', my: 6 }}><CircularProgress /></Box>
      ) : (
        <>
          {/* Pódium */}
          <Grid container spacing={4} alignItems="flex-end" justifyContent="center" sx={{ mb: 4, mt: 0.5, px: 2 }}>
            {PODIUM_CFG.map((cfg) => (
              <Grid item xs={12} sm={4} key={cfg.pos}>
                <PodiumCard cfg={cfg} rm={rmByPos(cfg.pos)} />
              </Grid>
            ))}
          </Grid>

          {/* ── MIP TABLE ────────────────────────────────────── */}
          <Paper elevation={3} sx={{ borderRadius: 2, overflow: 'hidden', mb: 4 }}>
            {/* Título granate */}
            <Box sx={{ bgcolor: '#686158', py: 1.8, textAlign: 'center' }}>
              <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: 16, letterSpacing: '1.5px', textTransform: 'uppercase' }}>
                Mapa Integral de Productividad
              </Typography>
              <Typography sx={{ color: '#D8D2CB', fontWeight: 700, fontSize: 16, letterSpacing: '1px', textTransform: 'uppercase', mt: 0.3 }}>
                Resultados Acumulados{cicloNum ? ` Ciclo ${cicloNum} ${cicloAnio}` : ''}
              </Typography>
            </Box>

            {/* Leyenda de banderines */}
            <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 4, px: 3, py: 1.6, bgcolor: '#fafafa', borderBottom: '1px solid #e0e0e0' }}>
              {[{ color: '#2e7d32', label: '> 90' }, { color: '#f57f17', label: 'Entre 80 y 89' }, { color: '#c62828', label: '< 79' }]
                .map(({ color, label }) => (
                  <Box key={label} sx={{ display: 'flex', alignItems: 'center', gap: 1.4 }}>
                    <svg width="20" height="22" viewBox="0 0 14 16">
                      <polygon points="2,1 13,6 2,11" fill={color} />
                      <line x1="2" y1="1" x2="2" y2="16" stroke={color} strokeWidth="1.5" />
                    </svg>
                    <Typography sx={{ fontSize: 14, color, fontWeight: 700, letterSpacing: '0.3px' }}>{label}</Typography>
                  </Box>
                ))}
            </Box>

            {/* Tabla */}
            <TableContainer>
              <Table size="small">
                <TableHead>
                  <TableRow sx={{ bgcolor: '#F6F4F2' }}>
                    {[
                      { label: 'Rk Ciclo', align: 'center' as const, w: 80 },
                      { label: 'Linea',    align: 'left'   as const },
                      { label: 'RM',       align: 'left'   as const },
                      { label: 'Puntos Ciclo', align: 'center' as const },
                      { label: 'Puntos Acum',  align: 'center' as const },
                    ].map(({ label, align, w }) => (
                      <TableCell key={label} align={align}
                        sx={{ fontWeight: 800, fontSize: 13, color: '#686158',
                              borderBottom: '2px solid #686158', py: 1.2,
                              ...(w ? { width: w } : {}) }}>
                        {label}
                      </TableCell>
                    ))}
                  </TableRow>
                </TableHead>
                <TableBody>
                  {top10.length === 0 ? (
                    <TableRow>
                      <TableCell colSpan={5} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                        No hay datos. Selecciona un país o genera el ranking primero.
                      </TableCell>
                    </TableRow>
                  ) : top10.map((row: any, i: number) => {
                    const pos       = row.posicion ?? i + 1;
                    const ptsCiclo  = Number(row.score_ciclo_actual ?? row.score_total ?? 0);
                    const ptsAcum   = Number(row.score_total ?? 0);
                    const rowBg     = pos === 1 ? '#fffde7' : pos % 2 === 0 ? '#f9f9f9' : '#fff';
                    return (
                      <TableRow key={row.rm_id} sx={{ bgcolor: rowBg }}>
                        <TableCell align="center" sx={{ fontWeight: 700, fontSize: 14, color: '#686158', py: 1.4 }}>
                          {pos}
                        </TableCell>
                        <TableCell sx={{ fontSize: 13, fontWeight: 600, textTransform: 'uppercase', py: 1.4 }}>
                          {row.linea_nombre && row.linea_nombre !== '—' ? row.linea_nombre : 'GENERAL'}
                        </TableCell>
                        <TableCell sx={{ fontWeight: 700, fontSize: 13, textTransform: 'uppercase', py: 1.4 }}>
                          {row.rm_nombre || 'RM #' + row.rm_id}
                        </TableCell>
                        <TableCell align="center" sx={{ py: 1.4 }}>
                          <Flag value={ptsCiclo} />
                        </TableCell>
                        <TableCell align="center" sx={{ py: 1.4 }}>
                          <Flag value={ptsAcum} />
                        </TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </TableContainer>
          </Paper>

          {/* Reconocimientos formales (si existen) */}
          {recItems.length > 0 && (
            <>
              <Typography variant="subtitle1" fontWeight={700} mb={1}>
                Reconocimientos registrados
              </Typography>
              {loadingRec ? <CircularProgress /> : (
                <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
                  <Table size="small">
                    <TableHead sx={{ bgcolor: '#686158' }}>
                      <TableRow>
                        {['RM', 'Premio', 'Score (%)', 'Posición', 'Fecha', 'Certificado'].map(h => (
                          <TableCell key={h} sx={{ color: 'white', fontWeight: 700, fontSize: 13 }}>{h}</TableCell>
                        ))}
                      </TableRow>
                    </TableHead>
                    <TableBody>
                      {recItems.map((r: any) => (
                        <TableRow key={r.id} hover>
                          <TableCell sx={{ fontWeight: 600 }}>{r.rm_nombre || `RM #${r.rm_id}`}</TableCell>
                          <TableCell><Chip label={r.premio_nombre || `Premio #${r.premio_id}`} color="warning" size="small" /></TableCell>
                          <TableCell sx={{ fontWeight: 700 }}>{Number(r.score_total || 0).toFixed(1)}%</TableCell>
                          <TableCell>{r.posicion_ranking ?? '—'}</TableCell>
                          <TableCell>{r.fecha_calculo ? new Date(r.fecha_calculo).toLocaleDateString() : '—'}</TableCell>
                          <TableCell>
                            {r.certificado_generado ? (
                              <Button size="small" startIcon={<Download />}
                                onClick={() => handleDescargar(r.id)} disabled={descargando === r.id}>
                                {descargando === r.id ? 'Descargando…' : 'Descargar'}
                              </Button>
                            ) : <Chip label="Pendiente" size="small" />}
                          </TableCell>
                        </TableRow>
                      ))}
                    </TableBody>
                  </Table>
                </TableContainer>
              )}
            </>
          )}
        </>
      )}
    </Box>
  );
}
