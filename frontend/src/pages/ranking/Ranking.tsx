import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent,
  Table, TableBody, TableCell, TableContainer, TableFooter,
  TableHead, TableRow, Paper, Chip, CircularProgress,
  Alert, Tabs, Tab, Select, MenuItem, Button,
  TablePagination, Divider,
} from '@mui/material';
import { Download } from '@mui/icons-material';
import { useMemo, useEffect, useState } from 'react';
import { api } from '../../services/api';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import MiRanking from './MiRanking';
import type { RankingItem } from '../../types';

/* ── utilidades ───────────────────────────────────────────── */
function flagColor(v: number): string {
  const r = Math.round(v * 10) / 10;  // mismo redondeo que toFixed(1)
  if (r >= 90) return '#00897b';   // verde   ≥ 90
  if (r >= 80) return '#f9a825';   // ámbar   80–89
  return '#e53935';                // rojo    < 80
}

function Flag({ value, small }: { value: number; small?: boolean }) {
  const color = flagColor(value);
  const fs = small ? 13 : 18;
  const sw = small ? 16 : 20;
  const sh = small ? 18 : 22;
  return (
    <Box sx={{ display: 'inline-flex', alignItems: 'center', gap: 0.8 }}>
      <svg width={sw} height={sh} viewBox="0 0 14 16">
        <polygon points="2,1 13,6 2,11" fill={color} />
        <line x1="2" y1="1" x2="2" y2="16" stroke={color} strokeWidth="1.5" />
      </svg>
      <Typography sx={{ fontWeight: 800, fontSize: fs, color, lineHeight: 1 }}>
        {value.toFixed(1)}
      </Typography>
    </Box>
  );
}

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontSize: 11, fontWeight: 700, color: 'text.secondary',
      textTransform: 'uppercase', letterSpacing: 0.8, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

/* ── filas tabla simple (Regional / Anual) ────────────────── */
function SimpleRow({ row, i }: { row: any; i: number }) {
  const pos   = row.posicion ?? i + 1;
  const score = Number(row.score_total ?? 0);
  return (
    <TableRow hover>
      <TableCell sx={{ fontWeight: 700, textAlign: 'center', fontSize: 13 }}>{pos}</TableCell>
      <TableCell sx={{ fontSize: 13 }}>{row.linea_nombre || '—'}</TableCell>
      <TableCell sx={{ fontWeight: 700, fontSize: 13 }}>{row.rm_nombre || 'RM #' + row.rm_id}</TableCell>
      {row.pais_nombre !== undefined && <TableCell sx={{ fontSize: 13 }}>{row.pais_nombre}</TableCell>}
      <TableCell align="center"><Flag value={score} /></TableCell>
    </TableRow>
  );
}

/* ── página principal ─────────────────────────────────────── */
/** El representante ve SU POSICIÓN ("estás 12 de 45"), no el ranking completo: publicar la
 *  tabla con nombres y puntajes expondría el dato individual de cada colega a los otros 44.
 *  La gerencia sí ve el mapa integral. Wrapper porque los hooks no admiten return temprano. */
export default function Ranking() {
  const rolActual = useAuthStore((s) => s.rol);
  return rolActual === 'REPRESENTANTE_MEDICO' ? <MiRanking /> : <RankingGerencia />;
}

function RankingGerencia() {
  const [tab,        setTab]        = useState(0);
  // País y ciclo salen del CONTEXTO GLOBAL (barra superior); el ranking sigue al ciclo
  // elegido arriba (por defecto el ABIERTO) en vez de auto-elegir el "último con datos" (Item 8).
  const paisCodigo  = useCicloStore((s) => s.paisCodigo);
  const cicloGlobal = useCicloStore((s) => s.cicloId);
  const setPais     = useCicloStore((s) => s.setPais);
  const setCicloVer = useCicloStore((s) => s.setCicloVer);
  const paisId  = paisCodigo ?? '';
  const cicloId = cicloGlobal ?? '';
  const [busqueda,   setBusqueda]   = useState('');
  const [soloConRegistro, setSoloConRegistro] = useState(false);  // Item 8: todos / con registro
  const [page,       setPage]       = useState(0);
  const [size,       setSize]       = useState(200);
  const [exportando, setExportando] = useState(false);

  // Al cambiar el país (aquí o desde la barra global), vuelve a la primera página.
  useEffect(() => { setPage(0); }, [paisCodigo]);
  const handlePaisChange = (val: string | '') => { if (val) void setPais(val); setPage(0); };

  const { data: catalogos } = useQuery({
    queryKey: ['ranking-catalogos', paisId],
    queryFn: () => api.get('/dashboard/catalogos', {
      params: paisId ? { pais_codigo: paisId } : {},
    }).then(r => r.data),
  });
  const paises: any[] = catalogos?.paises ?? [];
  const ciclos: any[] = catalogos?.ciclos  ?? [];

  // País y ciclo por defecto los fija el contexto global (store.init) — sin auto-selección local.


  const endpoints  = ['/ranking', '/ranking/regional'];
  const tabLabels  = ['Ranking Actual', 'Regional'];
  const esPaginado = tab === 0;
  // Regional es una vista en vivo global (no se filtra por país/ciclo — combina
  // el resultado acumulado, ya correcto, de cada representante en su propio país).
  const esRegional = tab === 1;

  const { data, isLoading, error } = useQuery({
    queryKey: ['ranking', tab, paisId, cicloId, page, size],
    queryFn: () => api.get(endpoints[tab], {
      params: esRegional ? { top: 100 } : {
        ...(paisId  && { pais_codigo: paisId }),
        ...(cicloId && { ciclo_id: Number(cicloId) }),
        ...(esPaginado && { page: page + 1, size }),
      },
    }).then(r => r.data),
    retry: 1,
  });

  const items: RankingItem[] = data?.items || data || [];
  const total: number        = data?.total ?? items.length;
  const cicloEfectivo        = data?.ciclo_efectivo ?? null;
  const ciclosNums: number[] = data?.ciclos_numeros ?? [];

  // Último ciclo con datos reales (al menos un RM tiene valor != null)
  const ultimoCicloConDatos = useMemo(() => {
    if (!ciclosNums.length || !items.length) return null;
    const sorted = [...ciclosNums].sort((a, b) => b - a);
    return sorted.find(n =>
      items.some((r: any) => r[`score_c${n}`] != null)
    ) ?? null;
  }, [ciclosNums, items]);

  // Ordenar por el último ciclo con datos desc
  const itemsOrdenados = useMemo(() => {
    const key = ultimoCicloConDatos != null ? `score_c${ultimoCicloConDatos}` : 'score_total';
    return [...items].sort((a: any, b: any) =>
      Number(b[key] ?? 0) - Number(a[key] ?? 0)
    );
  }, [items, ultimoCicloConDatos]);

  const itemsFiltrados = useMemo(() => {
    let base = itemsOrdenados;
    // Item 8 (Mallén): "con registro" = RM con score en el ciclo vigente (score > 0).
    if (soloConRegistro) {
      const key = ultimoCicloConDatos != null ? `score_c${ultimoCicloConDatos}` : 'score_total';
      base = base.filter((row: any) => row[key] != null && Number(row[key]) > 0);
    }
    if (!busqueda.trim()) return base;
    const q = busqueda.trim().toLowerCase();
    return base.filter((row: any) =>
      String(row.rm_nombre || '').toLowerCase().includes(q) ||
      String(row.rm_codigo || '').toLowerCase().includes(q)
    );
  }, [itemsOrdenados, busqueda, soloConRegistro, ultimoCicloConDatos]);

  const elegibles = itemsFiltrados.filter((r: any) => {
    const score = ultimoCicloConDatos != null
      ? Number(r[`score_c${ultimoCicloConDatos}`] ?? 0)
      : Number(r.score_total ?? 0);
    return score >= 90;
  }).length;

  // Promedios por columna para la fila de totales
  const promedios = useMemo(() => {
    if (!itemsFiltrados.length) return null;
    const res: Record<string, number | null> = {};
    ciclosNums.forEach(n => {
      const vals = itemsFiltrados
        .map((r: any) => r[`score_c${n}`])
        .filter((v: any) => v != null)
        .map(Number);
      res[`c${n}`] = vals.length ? vals.reduce((a: number, b: number) => a + b, 0) / vals.length : null;
    });
    const acumVals = itemsFiltrados.map((r: any) => Number(r.score_total ?? 0));
    res.acum = acumVals.reduce((a: number, b: number) => a + b, 0) / acumVals.length;
    return res;
  }, [itemsFiltrados, ciclosNums]);

  const cicloObj = (() => {
    const cid = cicloId || cicloEfectivo;
    if (!cid) return null;
    return ciclos.find((c: any) => c.id === cid) ?? null;
  })();
  const cicloNombre = cicloObj ? (cicloObj.nombre_canonico || cicloObj.nombre) : null;
  const cicloNum    = cicloObj?.numero ?? '';
  const cicloAnio   = cicloObj?.anio   ?? new Date().getFullYear();

  const handleExportar = async () => {
    setExportando(true);
    try {
      const r = await api.get('/exportacion/ranking/excel', {
        responseType: 'blob',
        params: {
          ...(paisId  && { pais_codigo: paisId }),
          ...(cicloId && { ciclo_id: Number(cicloId) }),
          tipo_ranking: tab === 1 ? 'REGIONAL' : 'MENSUAL',
        },
      });
      const url = URL.createObjectURL(r.data);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'ranking_' + tabLabels[tab].replace(/\s+/g, '_').toLowerCase() + '.xlsx';
      a.click();
      URL.revokeObjectURL(url);
    } catch { alert('No se pudo generar el archivo.'); }
    finally { setExportando(false); }
  };

  return (
    <Box>
      {/* Encabezado */}
      <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', flexWrap: 'wrap', gap: 1, mb: 0.5 }}>
        <Box>
          <Typography variant="h5" fontWeight={800}>Ranking General de Representantes</Typography>
          <Typography variant="body2" color="text.secondary" sx={{ mt: 0.3 }}>
            {cicloNombre
              ? cicloNombre + (ultimoCicloConDatos ? ` — Ordenado por Ciclo ${ultimoCicloConDatos}` : '')
              : 'Ranking'}
          </Typography>
        </Box>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 1.5 }}>
          {total > 0 && (
            <Chip label={total + ' RMs'} variant="outlined"
              sx={{ fontWeight: 700, fontSize: 13, color: '#1565c0', borderColor: '#1565c0' }} />
          )}
          {elegibles > 0 && (
            <Chip label={elegibles + ' elegibles'} variant="outlined"
              sx={{ fontWeight: 700, fontSize: 13, color: '#00897b', borderColor: '#00897b' }} />
          )}
          <Button variant="outlined" size="small" startIcon={<Download />}
            onClick={handleExportar} disabled={exportando}>
            {exportando ? 'Generando...' : 'Exportar'}
          </Button>
        </Box>
      </Box>

      <Divider sx={{ my: 1.5 }} />

      <Tabs value={tab} onChange={(_, v) => { setTab(v); setPage(0); }} sx={{ mb: 2 }}>
        {tabLabels.map((l) => <Tab key={l} label={l} />)}
      </Tabs>

      {/* Filtros */}
      <Card elevation={1} sx={{ mb: 2.5, borderRadius: 2 }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', gap: 3, alignItems: 'center', flexWrap: 'wrap' }}>
            {esRegional ? (
              <Typography variant="body2" color="text.secondary">
                Vista en vivo: combina el resultado acumulado de todos los representantes
                elegibles de todos los países, sin filtro de país/ciclo.
              </Typography>
            ) : (
              <>
                <Box sx={{ width: 200 }}>
                  <FilterLabel>País</FilterLabel>
                  <Select size="small" fullWidth value={paisId}
                    onChange={(e) => handlePaisChange(e.target.value as string | '')} displayEmpty>
                    <MenuItem value=""><em>Todos los países</em></MenuItem>
                    {paises.map((p: any) => <MenuItem key={p.id} value={p.codigo}>{p.nombre}</MenuItem>)}
                  </Select>
                </Box>
                <Box sx={{ width: 200 }}>
                  <FilterLabel>Ciclo</FilterLabel>
                  <Select size="small" fullWidth value={cicloId}
                    onChange={(e) => { const v = e.target.value; if (v !== '') setCicloVer(Number(v)); setPage(0); }}
                    displayEmpty disabled={!paisId}>
                    <MenuItem value="">
                      <em>{paisId ? 'Último ciclo con datos' : 'Seleccione un país'}</em>
                    </MenuItem>
                    {ciclos.map((c: any) => (
                      <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>
                    ))}
                  </Select>
                </Box>
                {tab === 0 && (
                  <Box sx={{ flex: 1, minWidth: 180 }}>
                    <FilterLabel>Buscar representante</FilterLabel>
                    <input
                      style={{ width: '100%', height: 40, padding: '0 12px',
                        border: '1px solid rgba(0,0,0,0.23)', borderRadius: 4,
                        fontSize: 14, fontFamily: 'inherit', boxSizing: 'border-box' }}
                      placeholder="Nombre o código"
                      value={busqueda}
                      onChange={(e) => setBusqueda(e.target.value)}
                    />
                  </Box>
                )}
                {/* Item 8 (Mallén): alterna entre todos los RM y solo los que tienen registro. */}
                <Chip label={soloConRegistro ? 'Solo con registro' : 'Todos'} clickable
                      color={soloConRegistro ? 'primary' : 'default'}
                      variant={soloConRegistro ? 'filled' : 'outlined'}
                      onClick={() => setSoloConRegistro((v) => !v)}
                      sx={{ ml: 1, fontWeight: 700, height: 32 }} />
                {cicloNombre && (
                  <Box sx={{ ml: 'auto' }}>
                    <Chip label={'Mostrando: ' + cicloNombre}
                      sx={{ bgcolor: '#686158', color: '#fff', fontWeight: 700, fontSize: 13, height: 32, px: 1 }} />
                  </Box>
                )}
              </>
            )}
          </Box>
        </CardContent>
      </Card>

      {isLoading ? (
        <Box sx={{ display: 'flex', justifyContent: 'center', mt: 6 }}><CircularProgress /></Box>
      ) : error ? (
        <Alert severity="info">No hay datos de ranking. Genere un ranking primero.</Alert>
      ) : tab === 0 ? (
        /* ── TABLA MIP ─────────────────────────────────────────── */
        <Paper elevation={3} sx={{ borderRadius: 2, overflow: 'hidden' }}>
          {/* Barra granate */}
          <Box sx={{ bgcolor: '#686158', py: 1.8, textAlign: 'center' }}>
            <Typography sx={{ color: '#fff', fontWeight: 800, fontSize: 16,
              letterSpacing: '1.5px', textTransform: 'uppercase' }}>
              Mapa Integral de Productividad
            </Typography>
            <Typography sx={{ color: '#c5cae9', fontWeight: 700, fontSize: 16,
              letterSpacing: '1px', textTransform: 'uppercase', mt: 0.3 }}>
              Resultados Acumulados{cicloNum ? ` Ciclo ${cicloNum} ${cicloAnio}` : ''}
            </Typography>
          </Box>

          {/* Leyenda */}
          <Box sx={{ display: 'flex', justifyContent: 'flex-end', gap: 3,
            px: 3, py: 1.4, bgcolor: '#fafafa', borderBottom: '1px solid #e0e0e0' }}>
            {[{ color: '#00897b', label: '≥ 90' },
              { color: '#f9a825', label: '80 – 89' },
              { color: '#e53935', label: '< 80'   }].map(({ color, label }) => (
              <Box key={label} sx={{ display: 'flex', alignItems: 'center', gap: 0.8 }}>
                <svg width="20" height="22" viewBox="0 0 14 16">
                  <polygon points="2,1 13,6 2,11" fill={color} />
                  <line x1="2" y1="1" x2="2" y2="16" stroke={color} strokeWidth="1.5" />
                </svg>
                <Typography sx={{ fontSize: 18, color, fontWeight: 700 }}>{label}</Typography>
              </Box>
            ))}
          </Box>

          <TableContainer>
            <Table size="small" sx={{ '& .MuiTableCell-root': { py: '2px', px: '6px' } }}>
              <TableHead>
                <TableRow sx={{ bgcolor: '#f5f7fa' }}>
                  {[
                    { label: 'Rk',    align: 'center' as const, w: 36 },
                    { label: 'Linea', align: 'left'   as const        },
                    { label: 'RM',    align: 'left'   as const        },
                    ...(ciclosNums.length > 0
                      ? ciclosNums.map(n => ({ label: `C${n}`, align: 'left' as const }))
                      : [{ label: 'Pts', align: 'left' as const }]
                    ),
                    { label: 'Acum',  align: 'left'   as const        },
                  ].map(({ label, align, w }) => (
                    <TableCell key={label} align={align}
                      sx={{ fontWeight: 800, fontSize: 11, color: '#686158',
                            borderBottom: '2px solid #686158',
                            ...(w ? { width: w, minWidth: w } : {}) }}>
                      {label}
                    </TableCell>
                  ))}
                </TableRow>
              </TableHead>
              <TableBody>
                {itemsFiltrados.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={3 + Math.max(ciclosNums.length, 1) + 1} align="center"
                      sx={{ py: 4, color: 'text.secondary' }}>
                      No hay ranking generado aún
                    </TableCell>
                  </TableRow>
                ) : itemsFiltrados.map((row: any, i: number) => {
                  const pos     = i + 1;
                  const ptsAcum = Number(row.score_total ?? 0);
                  const rowBg   = pos === 1 ? '#fffde7' : pos % 2 === 0 ? '#f4f6fa' : '#fff';
                  return (
                    <TableRow key={String(row.rm_id) + '-' + i} sx={{ bgcolor: rowBg }}>
                      <TableCell align="center"
                        sx={{ fontWeight: 700, fontSize: 11, color: '#686158' }}>{pos}</TableCell>
                      <TableCell sx={{ fontSize: 11, fontWeight: 600, textTransform: 'uppercase' }}>
                        {row.linea_nombre && row.linea_nombre !== '—' ? row.linea_nombre : 'GENERAL'}
                      </TableCell>
                      <TableCell sx={{ fontWeight: 700, fontSize: 11, textTransform: 'uppercase', whiteSpace: 'nowrap' }}>
                        {row.rm_nombre || 'RM #' + row.rm_id}
                      </TableCell>
                      {ciclosNums.length > 0
                        ? ciclosNums.map(n => {
                            const v = row[`score_c${n}`];
                            return (
                              <TableCell key={n} align="left" sx={{ whiteSpace: 'nowrap' }}>
                                {v != null ? <Flag value={Number(v)} small /> : null}
                              </TableCell>
                            );
                          })
                        : <TableCell align="left">
                            <Flag value={Number(row.score_ciclo_actual ?? row.score_total ?? 0)} small />
                          </TableCell>
                      }
                      <TableCell align="left" sx={{ whiteSpace: 'nowrap' }}>
                        <Flag value={ptsAcum} small />
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>

              {/* ── Fila de promedios ───────────────────────── */}
              {promedios && (
                <TableFooter>
                  <TableRow sx={{ bgcolor: '#c5cae9', borderTop: '4px solid #686158' }}>
                    <TableCell align="center"
                      sx={{ fontWeight: 900, fontSize: 10, color: '#686158', lineHeight: 1.1 }}>
                      Ø
                    </TableCell>
                    <TableCell colSpan={2}
                      sx={{ fontWeight: 800, fontSize: 10, color: '#686158', whiteSpace: 'nowrap' }}>
                      PROMEDIO · {itemsFiltrados.length} RMs
                    </TableCell>
                    {ciclosNums.length > 0
                      ? ciclosNums.map(n => (
                          <TableCell key={n} align="left" sx={{ whiteSpace: 'nowrap' }}>
                            {promedios[`c${n}`] != null
                              ? <Flag value={promedios[`c${n}`] as number} small />
                              : <Typography sx={{ fontSize: 10, color: '#bdbdbd' }}>—</Typography>}
                          </TableCell>
                        ))
                      : <TableCell />
                    }
                    <TableCell align="left" sx={{ whiteSpace: 'nowrap' }}>
                      <Flag value={promedios.acum as number} small />
                    </TableCell>
                  </TableRow>
                </TableFooter>
              )}
            </Table>
          </TableContainer>

          {esPaginado && total > size && !busqueda && (
            <Box sx={{ textAlign: 'center', py: 1, borderTop: '1px solid #e0e0e0' }}>
              <Typography variant="caption" color="text.secondary">
                {'... ' + Math.max(0, total - itemsFiltrados.length) + ' representantes adicionales ...'}
              </Typography>
            </Box>
          )}
          {esPaginado && (
            <TablePagination component="div" count={total} page={page}
              onPageChange={(_, p) => setPage(p)} rowsPerPage={size}
              onRowsPerPageChange={(e) => { setSize(parseInt(e.target.value, 10)); setPage(0); }}
              rowsPerPageOptions={[10, 25, 50, 100]}
              labelRowsPerPage="Filas por página"
              labelDisplayedRows={({ from, to, count }) => from + '–' + to + ' de ' + count}
            />
          )}
        </Paper>
      ) : (
        /* ── TABLA SIMPLE (Regional / Anual) ───────────────────── */
        <TableContainer component={Paper} elevation={2} sx={{ borderRadius: 2 }}>
          <Table size="small">
            <TableHead sx={{ bgcolor: '#f5f7fa' }}>
              <TableRow>
                {['#', 'Linea', 'RM', ...(tab === 1 ? ['País'] : []), 'Score'].map(h => (
                  <TableCell key={h}
                    align={h === '#' || h === 'Score' ? 'center' : 'left'}
                    sx={{ fontWeight: 800, fontSize: 13, color: '#37474f',
                          borderBottom: '2px solid #b0bec5', py: 1.4, textTransform: 'uppercase' }}>
                    {h}
                  </TableCell>
                ))}
              </TableRow>
            </TableHead>
            <TableBody>
              {items.length === 0 ? (
                <TableRow>
                  <TableCell colSpan={tab === 1 ? 5 : 4} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                    No hay datos
                  </TableCell>
                </TableRow>
              ) : items.map((row: any, i: number) => <SimpleRow key={i} row={row} i={i} />)}
            </TableBody>
          </Table>
        </TableContainer>
      )}
    </Box>
  );
}
