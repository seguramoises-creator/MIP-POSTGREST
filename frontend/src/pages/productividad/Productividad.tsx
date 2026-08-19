import { useQuery } from '@tanstack/react-query';
import {
  Box, Typography, Card, CardContent, CircularProgress, Alert,
  Table, TableBody, TableCell, TableContainer, TableHead, TableRow,
  Paper, Chip, Select, MenuItem, Divider,
} from '@mui/material';
import {
  BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip as RTooltip,
  ResponsiveContainer, Legend,
} from 'recharts';
import { useMemo, useState, useEffect } from 'react';
import { api } from '../../services/api';
import { KPI_ORDEN, kpiNombre } from '../../constants/kpi';
import { useCicloStore } from '../../store/ciclo.store';
import { useAuthStore } from '../../store/auth.store';
import MiProductividad from './MiProductividad';

function FilterLabel({ children }: { children: React.ReactNode }) {
  return (
    <Typography sx={{ fontSize: 11, fontWeight: 700, color: 'text.secondary',
      textTransform: 'uppercase', letterSpacing: 0.8, mb: 0.5 }}>
      {children}
    </Typography>
  );
}

function pctColor(v: number) {
  if (v >= 90) return '#2e7d32';
  if (v >= 80) return '#f57f17';
  return '#c62828';
}

const TH_BASE = {
  fontWeight: 800, fontSize: 10, color: '#fff',
  borderRight: '1px solid rgba(255,255,255,0.2)',
  textAlign: 'center' as const, lineHeight: 1.1, py: 0.5, px: 0.4,
};
const TH_META = {
  fontSize: 10, fontWeight: 600, color: '#37474f',
  borderRight: '1px solid #e0e0e0', py: 0.3, px: 0.4,
  textAlign: 'center' as const, bgcolor: '#EDE9E4',
};
const TD = {
  fontSize: 11, borderRight: '1px solid #e8e8e8', py: 0.4, px: 0.4,
  textAlign: 'center' as const,
};

const CICLO_COLORS = [
  '#584F46','#2e7d32','#6a1b9a','#e65100','#00838f',
  '#c62828','#f9a825','#37474f','#ad1457','#558b2f','#004d40',
];

// KPI_ORDEN y kpiNombre importados desde ../../constants/kpi

/** El representante ve SOLO lo suyo + el agregado de su línea (MiProductividad); la gerencia
 *  ve el mapa integral. Son pantallas distintas porque la de gerencia consulta
 *  /admin/lineas, /admin/indicadores y /ranking — endpoints que su rol no puede tocar, así
 *  que al representante le salía vacía. La bifurcación va en un wrapper: los hooks no
 *  admiten un return temprano. */
export default function Productividad() {
  const rolActual = useAuthStore((s) => s.rol);
  return rolActual === 'REPRESENTANTE_MEDICO' ? <MiProductividad /> : <ProductividadGerencia />;
}

function ProductividadGerencia() {
  // País y ciclo salen del CONTEXTO GLOBAL (barra superior). Así la página y su gráfico
  // siguen al ciclo elegido arriba (por defecto el ABIERTO), en vez de auto-elegir el
  // "último ciclo con datos" por su cuenta (Item 7 Mallén).
  const paisCodigo  = useCicloStore((s) => s.paisCodigo);
  const cicloGlobal = useCicloStore((s) => s.cicloId);
  const setPais     = useCicloStore((s) => s.setPais);
  const setCicloVer = useCicloStore((s) => s.setCicloVer);
  const paisId  = paisCodigo ?? '';
  const cicloId = cicloGlobal ?? '';
  const [lineaId,  setLineaId]  = useState<number | ''>('');
  const [busqueda, setBusqueda] = useState('');

  // Al cambiar el país (aquí o desde la barra global), limpia la línea.
  useEffect(() => { setLineaId(''); }, [paisCodigo]);
  const handlePaisChange = (val: string | '') => { if (val) void setPais(val); };

  const { data: catalogos } = useQuery({
    queryKey: ['prod-catalogos', paisId],
    queryFn: () => api.get('/dashboard/catalogos', { params: paisId ? { pais_codigo: paisId } : {} }).then(r => r.data),
  });
  const paises: any[] = catalogos?.paises ?? [];
  const ciclos: any[] = catalogos?.ciclos  ?? [];

  // El país por defecto lo fija el contexto global (store.init) — sin auto-selección local.

  const { data: lineas } = useQuery({
    queryKey: ['lineas', paisId],
    queryFn: () => api.get('/admin/lineas', { params: { pais_codigo: paisId } }).then(r => r.data),
    enabled: !!paisId,
  });

  /* Datos del ciclo seleccionado */
  const { data, isLoading, error } = useQuery({
    queryKey: ['productividad', paisId, cicloId, lineaId],
    queryFn: () => api.get('/productividad', {
      params: {
        ...(paisId  && { pais_codigo: paisId  }),
        ...(cicloId && { ciclo_id: Number(cicloId) }),
        ...(lineaId && { linea_id: Number(lineaId) }),
        page: 1, size: 500,
      },
    }).then(r => r.data),
    retry: 1,
  });
  const items: any[] = data?.items || [];

  /* Auto-detectar pais_id desde los datos cuando no hay filtro seleccionado */
  const inferredPaisId = useMemo(() => {
    if (paisId) return paisId;
    const first = items.find((r: any) => r.pais_id);
    return (first?.pais_id as number) || null;
  }, [paisId, items]);

  const { data: indicadoresCfg } = useQuery({
    queryKey: ['indicadores-cfg', inferredPaisId],
    queryFn: () => api.get('/admin/indicadores', { params: { pais_id: Number(inferredPaisId), size: 50 } }).then(r => r.data?.items ?? r.data ?? []),
    enabled: !!inferredPaisId,
  });
  const cfgByCode: Record<string, any> = useMemo(() => {
    const m: Record<string, any> = {};
    for (const ind of (indicadoresCfg || [])) m[ind.codigo] = ind;
    return m;
  }, [indicadoresCfg]);

  /* Datos de todos los ciclos para el gráfico */
  const { data: chartRaw } = useQuery({
    queryKey: ['prod-chart', paisId, lineaId],
    queryFn: () => api.get('/productividad', {
      params: { ...(paisId && { pais_codigo: paisId }), ...(lineaId && { linea_id: Number(lineaId) }), page: 1, size: 5000 },
    }).then(r => r.data),
    retry: 1, enabled: !!paisId,
  });
  const chartItems: any[] = chartRaw?.items || [];

  /* Ranking → RK ACUM + gerente */
  const { data: rankData } = useQuery({
    queryKey: ['prod-ranking', paisId, cicloId],
    queryFn: () => api.get('/ranking', {
      params: { ...(paisId && { pais_codigo: paisId }), ...(cicloId && { ciclo_id: Number(cicloId) }), size: 500, page: 1 },
    }).then(r => r.data),
    retry: 1, enabled: !!paisId,
  });
  // El ciclo lo fija el contexto global (default = abierto); sin auto-selección local.

  const rankPorRm  = useMemo(() => {
    const m: Record<number, { pos: number; mip: number; gerente: string }> = {};
    for (const r of rankData?.items ?? []) {
      m[r.rm_id] = { pos: r.posicion ?? 0, mip: Number(r.score_total ?? 0), gerente: r.gerente_nombre || '—' };
    }
    return m;
  }, [rankData]);

  /* Acumulado: promedio de ciclos desde ranking (igual lógica que página Ranking) */
  const accumByRm = useMemo(() => {
    const m: Record<number, number> = {};
    for (const r of rankData?.items ?? []) {
      m[r.rm_id] = Number(r.score_total ?? 0);
    }
    return m;
  }, [rankData]);

  /* ── Pivot tabla ──────────────────────────────────────────── */
  const { pivotRows, indicadores } = useMemo(() => {
    const rmMap: Record<string, any> = {};
    const indSet: string[] = [];
    const indSeen = new Set<string>();

    for (const row of items) {
      const rmKey  = String(row.rm_id);
      const indKey = row.indicador_codigo || '?';
      if (!indSeen.has(indKey)) { indSeen.add(indKey); indSet.push(indKey); }
      if (!rmMap[rmKey]) rmMap[rmKey] = {
        rm_id: row.rm_id, rm_nombre: row.rm_nombre || 'RM #' + row.rm_id,
        rm_codigo: row.rm_codigo || '', linea_nombre: row.linea_nombre || '—',
        gerente_nombre: row.gerente_nombre || '—', inds: {},
      };
      rmMap[rmKey].inds[indKey] = {
        pct: row.cumplimiento_pct ?? row.porcentaje_cumplimiento ?? null,
        pts: row.puntaje != null ? Number(row.puntaje) : null,
      };
    }
    // Orden canónico desde kpi.ts (ignora campo `orden` de la BD para evitar conflictos)
    indSet.sort((a, b) => (KPI_ORDEN[a] ?? 99) - (KPI_ORDEN[b] ?? 99));

    let rows = Object.values(rmMap).map(row => {
      // TOTAL = suma de puntos del ciclo
      const total = indSet.reduce((s, ind) => s + (row.inds[ind]?.pts ?? 0), 0);
      return { ...row, total };
    });

    // RK MES = posición por total de puntos del ciclo
    const sorted = [...rows].sort((a, b) => b.total - a.total);
    const rkMes: Record<string, number> = {};
    sorted.forEach((r, i) => { rkMes[r.rm_id] = i + 1; });

    // Filtro
    if (busqueda.trim()) {
      const q = busqueda.trim().toLowerCase();
      rows = rows.filter(r => r.rm_nombre.toLowerCase().includes(q) || r.rm_codigo.toLowerCase().includes(q));
    }

    // Ordenar por RK ACUM
    rows.sort((a, b) => (rankPorRm[a.rm_id]?.pos ?? 999) - (rankPorRm[b.rm_id]?.pos ?? 999));
    rows.forEach(r => { r.rkMes = rkMes[r.rm_id] ?? '—'; });

    return { pivotRows: rows, indicadores: indSet };
  }, [items, busqueda, rankPorRm, cfgByCode]);

  /* ── Datos gráfico: indicador × ciclo ──────────────────────── */
  const { grafData, cicloKeys } = useMemo(() => {
    const mapa: Record<string, Record<string, number[]>> = {};
    const cicloMap = new Map<number, string>();
    for (const row of chartItems) {
      const indKey  = row.indicador_codigo || '?';
      const cid     = row.ciclo_id;
      if (!cid) continue;
      const cicloObj = ciclos.find((c: any) => c.id === cid);
      const ck = cicloObj ? (cicloObj.nombre_canonico || cicloObj.nombre) : `C${cid}`;
      cicloMap.set(cid, ck);
      const pct = row.cumplimiento_pct ?? row.porcentaje_cumplimiento;
      if (pct == null) continue;
      if (!mapa[indKey]) mapa[indKey] = {};
      if (!mapa[indKey][ck]) mapa[indKey][ck] = [];
      mapa[indKey][ck].push(Number(pct));
    }
    const cicloKeys = [...new Set(cicloMap.values())].sort();
    // Orden canónico + nombre de presentación en el eje X
    const grafData = Object.entries(mapa)
      .sort(([a],[b]) => (KPI_ORDEN[a] ?? 99) - (KPI_ORDEN[b] ?? 99))
      .map(([ind, byCiclo]) => {
        const entry: any = { ind: kpiNombre(ind, ind) };
        for (const ck of cicloKeys) {
          const v = byCiclo[ck];
          entry[ck] = v?.length ? Math.round((v.reduce((s,x)=>s+x,0)/v.length)*10)/10 : 0;
        }
        return entry;
      });
    return { grafData, cicloKeys };
  }, [chartItems, ciclos]);

  const cicloEfectivo = rankData?.ciclo_efectivo ?? null;
  const cicloObj = (() => {
    const cid = cicloId || cicloEfectivo;
    return cid ? (ciclos.find((c: any) => c.id === cid) ?? null) : null;
  })();
  const cicloNombre = cicloObj ? (cicloObj.nombre_canonico || cicloObj.nombre) : null;
  const cicloNum    = cicloObj?.numero ?? '';
  const cicloAnio   = cicloObj?.anio ?? new Date().getFullYear();
  const numIndCols  = indicadores.length * 2;

  return (
    <Box>
      <Box sx={{ mb: 0.5 }}>
        <Typography variant="h5" fontWeight={800}>Productividad Comercial</Typography>
        <Typography variant="body2" color="text.secondary" sx={{ mt: 0.3 }}>
          Resultados por indicador — ciclo seleccionado y acumulado
        </Typography>
      </Box>

      <Divider sx={{ my: 1.5 }} />

      {/* ── Filtros ─────────────────────────────────────────── */}
      <Card elevation={1} sx={{ mb: 2.5, borderRadius: 2 }}>
        <CardContent sx={{ py: '12px !important' }}>
          <Box sx={{ display: 'flex', gap: 3, alignItems: 'center', flexWrap: 'wrap' }}>
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
                onChange={(e) => { const v = e.target.value; if (v !== '') setCicloVer(Number(v)); }}
                displayEmpty disabled={!paisId}>
                <MenuItem value=""><em>{paisId ? 'Último ciclo con datos' : 'Seleccione un país'}</em></MenuItem>
                {ciclos.map((c: any) => <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>)}
              </Select>
            </Box>
            <Box sx={{ width: 200 }}>
              <FilterLabel>Línea</FilterLabel>
              <Select size="small" fullWidth value={lineaId}
                onChange={(e) => setLineaId(e.target.value as number | '')}
                displayEmpty disabled={!paisId}>
                <MenuItem value=""><em>Todas las líneas</em></MenuItem>
                {(lineas||[]).map((l: any) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
              </Select>
            </Box>
            <Box sx={{ flex: 1, minWidth: 180 }}>
              <FilterLabel>Buscar RM</FilterLabel>
              <input style={{ width:'100%', height:40, padding:'0 12px',
                border:'1px solid rgba(0,0,0,0.23)', borderRadius:4,
                fontSize:14, fontFamily:'inherit', boxSizing:'border-box' }}
                placeholder="Nombre o código" value={busqueda}
                onChange={(e) => setBusqueda(e.target.value)} />
            </Box>
            {cicloNombre && (
              <Box sx={{ ml:'auto' }}>
                <Chip label={'Mostrando: ' + cicloNombre}
                  sx={{ bgcolor:'#686158', color:'#fff', fontWeight:700, fontSize:13, height:32, px:1 }} />
              </Box>
            )}
          </Box>
        </CardContent>
      </Card>

      {/* ── Gráfico: indicadores × ciclos ─────────────────────── */}
      {grafData.length > 0 && (
        <Card elevation={2} sx={{ mb: 3, borderRadius: 2, overflow: 'hidden' }}>
          <Box sx={{ bgcolor: '#686158', px: 3, py: 1.2 }}>
            <Typography sx={{ color: '#fff', fontWeight: 700, fontSize: 14,
              textTransform: 'uppercase', letterSpacing: '0.8px' }}>
              Comparativo por Indicador y Ciclo — % Cumplimiento Promedio
            </Typography>
          </Box>
          <CardContent sx={{ pt: 2, pb: '8px !important' }}>
            <ResponsiveContainer width="100%" height={420}>
              <BarChart data={grafData} margin={{ top: 8, right: 20, bottom: 80, left: 0 }} barCategoryGap="18%">
                <CartesianGrid strokeDasharray="3 3" vertical={false} />
                <XAxis dataKey="ind" tick={{ fontSize: 10, fontWeight: 600, fill: '#37474f' }}
                  angle={-55} textAnchor="end" interval={0} height={55} />
                <YAxis domain={[0, 100]} tickFormatter={(v) => `${v}%`} tick={{ fontSize: 11 }} />
                <RTooltip formatter={(val: number, name: string) => [`${val.toFixed(1)}%`, name]}
                  contentStyle={{ fontSize: 12, borderRadius: 6 }} />
                <Legend verticalAlign="bottom" layout="horizontal" align="center"
                  wrapperStyle={{ fontSize: 12, position: 'relative', marginTop: 28 }} />
                {cicloKeys.map((ck, i) => (
                  <Bar key={ck} dataKey={ck} name={ck}
                    fill={CICLO_COLORS[i % CICLO_COLORS.length]}
                    radius={[3,3,0,0]} maxBarSize={36} />
                ))}
              </BarChart>
            </ResponsiveContainer>
          </CardContent>
        </Card>
      )}

      {/* ── Tabla MIP multi-nivel ──────────────────────────────── */}
      {isLoading ? (
        <Box sx={{ display:'flex', justifyContent:'center', mt:6 }}><CircularProgress /></Box>
      ) : error ? (
        <Alert severity="info">Sin datos de productividad para los filtros seleccionados.</Alert>
      ) : (
        <Paper elevation={3} sx={{ borderRadius: 2, overflow: 'hidden' }}>
          {/* Barra azul MIP */}
          <Box sx={{ bgcolor: '#686158', py: 1.5, textAlign: 'center' }}>
            <Typography sx={{ color:'#fff', fontWeight:800, fontSize:15, letterSpacing:'1.5px', textTransform:'uppercase' }}>
              Mapa Integral de Productividad
            </Typography>
            <Typography sx={{ color:'#D8D2CB', fontWeight:700, fontSize:15, letterSpacing:'1px', textTransform:'uppercase', mt:0.3 }}>
              Resultados{cicloNum ? ` Ciclo ${cicloNum} ${cicloAnio}` : ''}
            </Typography>
          </Box>

          <TableContainer sx={{ overflowX: 'auto' }}>
            <Table size="small" sx={{ minWidth: 600, borderCollapse: 'collapse' }}>
              <TableHead>
                {/* ── Fila 1: grupos ─────────────────────── */}
                <TableRow sx={{ bgcolor: '#2e7d32' }}>
                  {/* RK ACUM */}
                  <TableCell rowSpan={3} sx={{ ...TH_BASE, minWidth: 38, whiteSpace:'pre-line', bgcolor:'#584F46' }}>
                    {'RK\nACUM'}
                  </TableCell>
                  {/* RK CICLO */}
                  <TableCell rowSpan={3} sx={{ ...TH_BASE, minWidth: 38, whiteSpace:'pre-line', bgcolor:'#584F46' }}>
                    {'RK\nCICLO'}
                  </TableCell>
                  {[
                    { h: 'GERENTE DE\nDISTRITO', mw: 100 },
                    { h: 'LINEA',              mw: 80 },
                    { h: 'REPRESENTANTE',      mw: 100 },
                  ].map(({ h, mw }) => (
                    <TableCell key={h} rowSpan={3} sx={{ ...TH_BASE, minWidth: mw, whiteSpace:'pre-line' }}>
                      {h}
                    </TableCell>
                  ))}
                  {/* "CICLO N" spanning indicator columns + TOTAL */}
                  <TableCell colSpan={numIndCols + 1}
                    sx={{ ...TH_BASE, bgcolor: '#584F46', fontSize: 11, letterSpacing: '1px' }}>
                    {cicloNum ? `CICLO ${cicloNum}` : 'CICLO ACTUAL'}
                  </TableCell>
                  {/* TOTAL ACUM — columna fija fuera del span de ciclo */}
                  <TableCell rowSpan={3}
                    sx={{ ...TH_BASE, bgcolor: '#4a148c', minWidth: 52, fontSize: 10, whiteSpace:'pre-line' }}>
                    {'TOTAL\nACUM'}
                  </TableCell>
                </TableRow>

                {/* ── Fila 2: nombres indicadores ────────── */}
                <TableRow sx={{ bgcolor: '#584F46' }}>
                  {indicadores.map(ind => {
                    const cfg = cfgByCode[ind];
                    const nombre = kpiNombre(ind, cfg?.nombre);
                    return (
                      <TableCell key={ind} colSpan={2}
                        sx={{ ...TH_BASE, bgcolor: '#584F46', minWidth: 76, textTransform:'uppercase', fontSize: 9 }}>
                        {nombre}
                      </TableCell>
                    );
                  })}
                  <TableCell rowSpan={2}
                    sx={{ ...TH_BASE, bgcolor: '#584F46', minWidth: 36, fontSize: 10 }}>
                    TOTAL
                  </TableCell>
                </TableRow>

                {/* ── Fila 3: Resul / Ptos ───────────────── */}
                <TableRow sx={{ bgcolor: '#686158' }}>
                  {indicadores.map(ind => (
                    [['Resul', ind+'-r'], ['Ptos', ind+'-p']].map(([label, key]) => (
                      <TableCell key={key} sx={{ ...TH_BASE, bgcolor: '#686158', fontSize: 11 }}>
                        {label}
                      </TableCell>
                    ))
                  ))}
                </TableRow>

                {/* ── Fila meta: Puntos máx ──────────────── */}
                <TableRow>
                  <TableCell colSpan={5} sx={{ ...TH_META, textAlign:'right', fontStyle:'italic', color:'#546e7a' }}>
                    Puntos
                  </TableCell>
                  {indicadores.map(ind => {
                    const cfg = cfgByCode[ind];
                    const pts = cfg?.ponderacion_pct != null ? Number(cfg.ponderacion_pct).toFixed(0) : '—';
                    return (
                      <TableCell key={ind+'-pm'} colSpan={2} sx={{ ...TH_META, fontWeight:700 }}>{pts}</TableCell>
                    );
                  })}
                  <TableCell sx={{ ...TH_META, bgcolor: '#c8e6c9', fontWeight: 800, color:'#1b5e20' }}>
                    {indicadores.reduce((s, ind) => s + (Number(cfgByCode[ind]?.ponderacion_pct) || 0), 0).toFixed(0) || '—'}
                  </TableCell>
                  <TableCell sx={{ ...TH_META, bgcolor: '#E9E4DD' }} />
                </TableRow>

                {/* ── Fila meta: Máximo % ────────────────── */}
                <TableRow>
                  <TableCell colSpan={5} sx={{ ...TH_META, textAlign:'right', fontStyle:'italic', color:'#546e7a' }}>
                    Máximo (%)
                  </TableCell>
                  {indicadores.map(ind => {
                    const cfg = cfgByCode[ind];
                    const v = cfg?.valor_max != null ? Number(cfg.valor_max).toFixed(0) : '—';
                    return <TableCell key={ind+'-mx'} colSpan={2} sx={{ ...TH_META }}>{v}</TableCell>;
                  })}
                  <TableCell sx={{ ...TH_META }} />
                  <TableCell sx={{ ...TH_META, bgcolor: '#E9E4DD' }} />
                </TableRow>

                {/* ── Fila meta: Mínimo % ────────────────── */}
                <TableRow>
                  <TableCell colSpan={5} sx={{ ...TH_META, textAlign:'right', fontStyle:'italic', color:'#546e7a' }}>
                    Mínimo (%)
                  </TableCell>
                  {indicadores.map(ind => {
                    const cfg = cfgByCode[ind];
                    const v = cfg?.valor_min != null ? Number(cfg.valor_min).toFixed(0) : '—';
                    return <TableCell key={ind+'-mn'} colSpan={2} sx={{ ...TH_META }}>{v}</TableCell>;
                  })}
                  <TableCell sx={{ ...TH_META }} />
                  <TableCell sx={{ ...TH_META, bgcolor: '#E9E4DD' }} />
                </TableRow>
              </TableHead>

              <TableBody>
                {pivotRows.length === 0 ? (
                  <TableRow>
                    <TableCell colSpan={6 + numIndCols} align="center" sx={{ py: 6, color: 'text.secondary' }}>
                      No hay datos. Selecciona un país o genera datos primero.
                    </TableCell>
                  </TableRow>
                ) : pivotRows.map((row, i) => {
                  const rk      = rankPorRm[row.rm_id];
                  const rkAcum  = rk?.pos ?? '—';
                  const rkMes   = row.rkMes ?? '—';
                  const gerente = rk?.gerente || row.gerente_nombre || '—';
                  const rowBg   = i % 2 === 0 ? '#f9f9f9' : '#fff';

                  // Shading for cycle rank top 3 (no medals)
                  const top3Bg: Record<number, string>     = { 1: '#FFF59D', 2: '#E0E0E0', 3: '#FFCCBC' };
                  const top3Border: Record<number, string> = { 1: '#F9A825', 2: '#9E9E9E', 3: '#E64A19' };
                  const top3Color: Record<number, string>  = { 1: '#E65100', 2: '#424242', 3: '#BF360C' };
                  const mesNum = typeof rkMes === 'number' ? rkMes : 0;
                  const isMedal = mesNum >= 1 && mesNum <= 3;

                  return (
                    <TableRow key={row.rm_id} sx={{ bgcolor: rowBg, '&:hover': { bgcolor: '#e8f5e9' } }}>
                      {/* RK ACUM — prominente, celda propia */}
                      <TableCell sx={{ ...TD, p: 0.5 }}>
                        <Box sx={{
                          display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
                          bgcolor: '#686158', color: '#fff', borderRadius: '50%',
                          width: 28, height: 28, fontWeight: 900, fontSize: 13,
                        }}>
                          {rkAcum}
                        </Box>
                      </TableCell>
                      {/* RK CICLO — sombreado top 3, sin emojis */}
                      <TableCell sx={{
                        ...TD, p: 0.5,
                        bgcolor: isMedal ? top3Bg[mesNum] : undefined,
                        borderLeft: isMedal ? `3px solid ${top3Border[mesNum]}` : undefined,
                      }}>
                        <Typography sx={{ fontSize: 11, fontWeight: isMedal ? 800 : 700, color: isMedal ? top3Color[mesNum] : '#37474f' }}>
                          {rkMes}
                        </Typography>
                      </TableCell>
                      <TableCell sx={{ ...TD, textAlign: 'left', fontWeight: 600, fontSize: 10, textTransform: 'uppercase', maxWidth: 100, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}
                        title={gerente !== '—' ? gerente : ''}>
                        {gerente !== '—' ? gerente : '—'}
                      </TableCell>
                      <TableCell sx={{ ...TD, textAlign:'left', fontSize:10, textTransform:'uppercase', maxWidth: 80, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}
                        title={row.linea_nombre}>
                        {row.linea_nombre !== '—' ? row.linea_nombre : '—'}
                      </TableCell>
                      <TableCell sx={{ ...TD, textAlign:'left', fontWeight:700, fontSize:10, textTransform:'uppercase', maxWidth:100, overflow:'hidden', textOverflow:'ellipsis', whiteSpace:'nowrap' }}
                        title={row.rm_nombre}>
                        {row.rm_nombre}
                      </TableCell>
                      {indicadores.map(ind => {
                        const cell = row.inds[ind];
                        const pct  = cell?.pct != null ? Number(cell.pct) : null;
                        const pts  = cell?.pts != null ? Number(cell.pts) : null;
                        const col  = pct != null ? pctColor(pct) : 'text.disabled';
                        return [
                          <TableCell key={ind+'-r'} sx={{ ...TD }}>
                            {pct != null
                              ? <Typography sx={{ fontSize:11, fontWeight:700, color:col }}>{pct.toFixed(1)}%</Typography>
                              : <Typography sx={{ color:'text.disabled', fontSize:12 }}>—</Typography>}
                          </TableCell>,
                          <TableCell key={ind+'-p'} sx={{ ...TD }}>
                            {pts != null
                              ? <Typography sx={{ fontSize:11, fontWeight:600, color: col }}>{pts.toFixed(1)}</Typography>
                              : <Typography sx={{ color:'text.disabled', fontSize:12 }}>—</Typography>}
                          </TableCell>,
                        ];
                      })}
                      {/* TOTAL ciclo */}
                      <TableCell sx={{ ...TD, bgcolor: '#EFEBE6' }}>
                        {row.total != null
                          ? <Typography sx={{ fontSize:12, fontWeight:800, color:'#686158' }}>{Number(row.total).toFixed(1)}</Typography>
                          : <Typography sx={{ color:'text.disabled', fontSize:12 }}>—</Typography>}
                      </TableCell>
                      {/* TOTAL ACUM — suma de todos los ciclos */}
                      <TableCell sx={{ ...TD, bgcolor: '#E9E4DD' }}>
                        {accumByRm[row.rm_id] != null && accumByRm[row.rm_id] > 0
                          ? <Typography sx={{ fontSize:12, fontWeight:800, color:'#4a148c' }}>{Number(accumByRm[row.rm_id]).toFixed(1)}</Typography>
                          : <Typography sx={{ color:'text.disabled', fontSize:12 }}>—</Typography>}
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          </TableContainer>
        </Paper>
      )}
    </Box>
  );
}
