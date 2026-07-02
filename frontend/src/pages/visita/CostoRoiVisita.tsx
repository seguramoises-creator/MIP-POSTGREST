import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, MenuItem,
  CircularProgress, Grid, Divider, Table, TableHead, TableRow, TableCell, TableBody, Slider,
} from '@mui/material';
import { Paid, Save, UploadFile, Calculate, Inventory2, MonetizationOn, CalendarMonth, Assessment, WarningAmber } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import {
  costoEstructura, guardarCostoEstructura, importarCostoExcel, listarLineasVisita,
  type CostoFull, type CostoEstructuraInput, type CostoProdInput, type Catalogo,
} from '../../services/visita.service';

function errMsg(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detalle?: { msg?: string }[]; detail?: string } } })?.response?.data;
  if (Array.isArray(d?.detalle) && d.detalle[0]?.msg) return d.detalle[0].msg.replace('Value error, ', '');
  if (typeof d?.detail === 'string') return d.detail;
  return fallback;
}

// Reconstruye la lista editable de productos a partir de los bloques calculados.
function productosDe(full: CostoFull): CostoProdInput[] {
  const map: Record<string, CostoProdInput> = {};
  full.muestras.productos.forEach((m) => { map[m.producto] = { producto: m.producto, costo_unitario_muestra: m.costo_unitario, cantidad_muestras: m.cantidad, pool_ventas: 0, visitas_detalladas: 0, presupuesto_anual: 0, precio_prom: 0 }; });
  full.pool.productos.forEach((p) => { map[p.producto] = { ...(map[p.producto] || { producto: p.producto, costo_unitario_muestra: 0, cantidad_muestras: 0, presupuesto_anual: 0, precio_prom: 0 }), pool_ventas: p.pool_ventas, visitas_detalladas: p.visitas_detalladas }; });
  full.plan_anual.productos.forEach((p) => { map[p.producto] = { ...(map[p.producto] || { producto: p.producto, costo_unitario_muestra: 0, cantidad_muestras: 0, pool_ventas: 0, visitas_detalladas: 0 }), presupuesto_anual: p.presupuesto_anual, precio_prom: p.precio_prom }; });
  return Object.values(map);
}

export default function CostoRoiVisita() {
  const rol = useAuthStore((s) => s.rol);
  const esGestor = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD';

  const [lineas, setLineas] = useState<Catalogo[]>([]);
  const [lineaId, setLineaId] = useState<number | ''>('');
  const [full, setFull] = useState<CostoFull | null>(null);
  const [est, setEst] = useState<CostoEstructuraInput | null>(null);
  const [prods, setProds] = useState<CostoProdInput[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);
  const fileRef = useRef<HTMLInputElement>(null);

  const moneda = full?.moneda ?? 'RD$';
  const money = (v: number) => `${moneda} ${Math.round(v).toLocaleString()}`;
  const lineaParam = esGestor ? (lineaId || undefined) : undefined;

  const aplicar = (f: CostoFull) => { setFull(f); setEst({ ...f.estructura }); setProds(productosDe(f)); };
  const cargar = useCallback(() => {
    setCargando(true);
    costoEstructura(lineaParam).then(aplicar).catch(() => setFull(null)).finally(() => setCargando(false));
  }, [lineaParam]);

  useEffect(() => {
    if (esGestor) listarLineasVisita().then((ls) => { setLineas(ls); if (ls.length && !lineaId) setLineaId(ls[0].id); }).catch(() => {});
  }, [esGestor]);   // eslint-disable-line react-hooks/exhaustive-deps
  useEffect(() => { if (!esGestor || lineaId) cargar(); }, [esGestor, lineaId, cargar]);

  const setE = (k: keyof CostoEstructuraInput, v: number | string | null) => setEst((e) => e ? { ...e, [k]: v } : e);
  const setP = (i: number, k: keyof CostoProdInput, v: number) => setProds((ps) => ps.map((p, idx) => idx === i ? { ...p, [k]: v } : p));

  async function guardar() {
    if (!est) return;
    setGuardando(true); setMsg(null);
    try {
      const f = await guardarCostoEstructura({ ...est, linea_id: lineaParam ?? null, productos: prods });
      aplicar(f);
      setMsg({ tipo: 'success', texto: 'Estructura guardada y recalculada.' });
    } catch (e) {
      setMsg({ tipo: 'error', texto: errMsg(e, 'No se pudo guardar.') });
    } finally { setGuardando(false); }
  }

  async function importar(file: File) {
    setGuardando(true); setMsg(null);
    try {
      const f = await importarCostoExcel(file, lineaParam);
      aplicar(f);
      setMsg({ tipo: 'success', texto: `Importados ${(f as { importados?: number }).importados ?? ''} productos desde Excel.` });
    } catch (e) {
      setMsg({ tipo: 'error', texto: errMsg(e, 'No se pudo importar el Excel.') });
    } finally { setGuardando(false); if (fileRef.current) fileRef.current.value = ''; }
  }

  if (cargando || !est || !full) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;

  const num = (label: string, val: number, k: keyof CostoEstructuraInput, sub?: string, width = 150) => (
    <Stack direction="row" justifyContent="space-between" alignItems="center" sx={{ py: 0.75 }}>
      <Box><Typography variant="body2" fontWeight={600}>{label}</Typography>{sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}</Box>
      <TextField size="small" type="number" value={val} sx={{ width }} onChange={(e) => setE(k, Number(e.target.value))} />
    </Stack>
  );
  const kpi = (label: string, valor: string, color = 'text.primary', sub?: string) => (
    <Card variant="outlined"><CardContent sx={{ py: 1.5 }}>
      <Typography variant="caption" color="text.secondary" fontWeight={600}>{label}</Typography>
      <Typography variant="h5" fontWeight={800} sx={{ color }}>{valor}</Typography>
      {sub && <Typography variant="caption" color="text.secondary">{sub}</Typography>}
    </CardContent></Card>
  );

  const pa = full.plan_anual; const r = full.resumen; const im = full.impacto;

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1} sx={{ mb: 1 }}>
        <Box>
          <Stack direction="row" alignItems="center" spacing={1}><Paid color="primary" /><Typography variant="h5" fontWeight={700}>Costo por Visita & ROI</Typography></Stack>
          <Typography variant="body2" color="text.secondary">Configurado por Finanzas · Pool de ventas ingresado por Gerencia al cierre del ciclo</Typography>
        </Box>
        <Stack direction="row" spacing={1.5} alignItems="center" flexWrap="wrap">
          {esGestor && (
            <TextField select size="small" label="Línea" value={lineaId} sx={{ minWidth: 190 }} onChange={(e) => setLineaId(Number(e.target.value))}>
              {lineas.map((l) => <MenuItem key={l.id} value={l.id}>{l.nombre}</MenuItem>)}
            </TextField>
          )}
          {esGestor && <>
            <input ref={fileRef} type="file" accept=".xlsx,.xls" hidden onChange={(e) => e.target.files?.[0] && importar(e.target.files[0])} />
            <Button size="small" startIcon={<UploadFile />} onClick={() => fileRef.current?.click()} disabled={guardando}>Importar Excel</Button>
            <Button size="small" variant="contained" startIcon={<Calculate />} onClick={guardar} disabled={guardando}>{guardando ? 'Guardando…' : 'Guardar y recalcular'}</Button>
          </>}
        </Stack>
      </Stack>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}
      {esGestor && <Alert severity="info" sx={{ mb: 2 }}>Edita los campos y pulsa <b>Guardar y recalcular</b> para actualizar los resultados. También puedes <b>importar un Excel</b> con columnas: producto, costo_unitario_muestra, cantidad_muestras, pool_ventas, visitas_detalladas, presupuesto_anual, precio_prom.</Alert>}

      <Grid container spacing={2}>
        {/* Bloque 1 — Estructura de costo del representante */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}><MonetizationOn fontSize="small" color="action" /><Typography variant="subtitle1" fontWeight={700}>Estructura de costo del representante</Typography></Stack>
            {num('Salario mensual bruto', est.salario_mensual, 'salario_mensual', 'Incluye sueldo base')}
            {num('Cargas y beneficios (%)', est.cargas_pct, 'cargas_pct', 'TSS, AFP, ARS, regalía', 90)}
            {num('Viáticos por día de campo', est.viaticos_dia, 'viaticos_dia', 'Combustible + alimentación')}
            {num('Materiales promo por ciclo', est.materiales_ciclo, 'materiales_ciclo', 'Folletos, detailads, gimmicks')}
            {num('Días de campo en el ciclo', est.dias_campo, 'dias_campo', 'Días hábiles de visita', 90)}
            {num('Total visitas del ciclo', est.total_visitas, 'total_visitas', 'Visitas registradas', 90)}
            <Box sx={{ mt: 1.5, p: 1.5, bgcolor: 'rgba(46,91,255,0.06)', borderRadius: 1 }}>
              <Typography variant="overline" color="text.secondary" fontWeight={700}>Resultados calculados</Typography>
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Costo fijo total del ciclo</Typography><Typography variant="body2" fontWeight={700}>{money(full.fijo.costo_fijo_total)}</Typography></Stack>
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Costo fijo por día</Typography><Typography variant="body2" fontWeight={700}>{money(full.fijo.costo_fijo_dia)}</Typography></Stack>
              <Divider sx={{ my: 0.5 }} />
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2" fontWeight={700}>Costo fijo por visita</Typography><Typography variant="body1" fontWeight={800} color="primary.main">{money(full.fijo.costo_fijo_visita)}</Typography></Stack>
            </Box>
          </CardContent></Card>
        </Grid>

        {/* Bloque 2 — Costo de muestras por producto */}
        <Grid item xs={12} md={6}>
          <Card variant="outlined" sx={{ height: '100%' }}><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}><Inventory2 fontSize="small" color="action" /><Typography variant="subtitle1" fontWeight={700}>Costo de muestras por producto</Typography></Stack>
            <Table size="small"><TableHead><TableRow>
              <TableCell>#</TableCell><TableCell>Producto</TableCell><TableCell align="center">Costo unit.</TableCell><TableCell align="center">Cant.</TableCell><TableCell align="right">Total ciclo</TableCell>
            </TableRow></TableHead><TableBody>
              {prods.map((p, i) => (
                <TableRow key={p.producto}>
                  <TableCell>{i + 1}</TableCell>
                  <TableCell>{p.producto}</TableCell>
                  <TableCell align="center"><TextField size="small" type="number" value={p.costo_unitario_muestra} sx={{ width: 90 }} onChange={(e) => setP(i, 'costo_unitario_muestra', Number(e.target.value))} /></TableCell>
                  <TableCell align="center"><TextField size="small" type="number" value={p.cantidad_muestras} sx={{ width: 90 }} onChange={(e) => setP(i, 'cantidad_muestras', Number(e.target.value))} /></TableCell>
                  <TableCell align="right">{money(p.costo_unitario_muestra * p.cantidad_muestras)}</TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
            <Box sx={{ mt: 1, p: 1.5, bgcolor: 'rgba(46,91,255,0.06)', borderRadius: 1 }}>
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Total muestras del ciclo</Typography><Typography variant="body2" fontWeight={700}>{full.muestras.total_muestras.toLocaleString()}</Typography></Stack>
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2">Costo total muestras</Typography><Typography variant="body2" fontWeight={700}>{money(full.muestras.costo_total_muestras)}</Typography></Stack>
              <Divider sx={{ my: 0.5 }} />
              <Stack direction="row" justifyContent="space-between"><Typography variant="body2" fontWeight={700}>Costo variable por visita</Typography><Typography variant="body1" fontWeight={800} color="primary.main">{money(full.muestras.costo_variable_visita)}</Typography></Stack>
            </Box>
          </CardContent></Card>
        </Grid>

        {/* Bloque 3 — Pool de ventas por línea */}
        <Grid item xs={12}>
          <Card variant="outlined"><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }} justifyContent="space-between">
              <Stack direction="row" alignItems="center" spacing={1}><MonetizationOn fontSize="small" color="action" /><Typography variant="subtitle1" fontWeight={700}>Pool de Ventas por Línea</Typography></Stack>
              <Typography variant="caption" color="text.secondary">Ingresado por Gerencia al cierre del ciclo · Sin ponderación por VM</Typography>
            </Stack>
            <Table size="small"><TableHead><TableRow>
              <TableCell>#</TableCell><TableCell>Producto</TableCell><TableCell align="center">Pool Ventas</TableCell><TableCell align="center">Visitas detalladas</TableCell><TableCell align="right">Retorno x visita</TableCell>
            </TableRow></TableHead><TableBody>
              {prods.map((p, i) => (
                <TableRow key={p.producto}>
                  <TableCell>{i + 1}</TableCell><TableCell sx={{ fontWeight: 600 }}>{p.producto}</TableCell>
                  <TableCell align="center"><TextField size="small" type="number" value={p.pool_ventas} sx={{ width: 140 }} onChange={(e) => setP(i, 'pool_ventas', Number(e.target.value))} /></TableCell>
                  <TableCell align="center"><TextField size="small" type="number" value={p.visitas_detalladas} sx={{ width: 100 }} onChange={(e) => setP(i, 'visitas_detalladas', Number(e.target.value))} /></TableCell>
                  <TableCell align="right"><Typography variant="body2" fontWeight={700} color="success.main">{p.visitas_detalladas ? money(p.pool_ventas / p.visitas_detalladas) : '—'}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </CardContent></Card>
        </Grid>

        {/* Bloque 4 — Planificación anual */}
        <Grid item xs={12}>
          <Card variant="outlined"><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}><CalendarMonth fontSize="small" color="action" /><Typography variant="subtitle1" fontWeight={700}>Planificación Anual — Productividad Objetivo del Contacto</Typography></Stack>
            <Stack direction="row" spacing={2} alignItems="center" flexWrap="wrap" sx={{ mb: 2 }}>
              <TextField size="small" label="Visitadores" type="number" value={est.visitadores} sx={{ width: 110 }} onChange={(e) => setE('visitadores', Number(e.target.value))} />
              <Typography>×</Typography>
              <TextField size="small" label="Visitas/ciclo VM" type="number" value={est.visitas_ciclo_vm} sx={{ width: 130 }} onChange={(e) => setE('visitas_ciclo_vm', Number(e.target.value))} />
              <Typography>×</Typography>
              <TextField size="small" label="Ciclos/año" type="number" value={est.ciclos_anio} sx={{ width: 110 }} onChange={(e) => setE('ciclos_anio', Number(e.target.value))} />
              <Typography>=</Typography>
              <Box><Typography variant="caption" color="text.secondary">Contactos/año equipo</Typography><Typography variant="h6" fontWeight={800} color="primary.main">{pa.contactos_anio.toLocaleString()}</Typography></Box>
              <Box sx={{ ml: 'auto' }}><Typography variant="caption" color="text.secondary">Contactos/año por VM</Typography><Typography variant="h6" fontWeight={800} color="primary.main">{pa.contactos_anio_vm.toLocaleString()}</Typography></Box>
            </Stack>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}>{kpi('CONTACTOS EQUIPO / AÑO', pa.contactos_anio.toLocaleString(), 'primary.main', `${est.visitadores} VMs × ${est.visitas_ciclo_vm} × ${est.ciclos_anio} ciclos`)}</Grid>
              <Grid item xs={12} md={4}>{kpi('PRESUPUESTO TOTAL ANUAL', money(pa.presupuesto_total), 'success.main', `${money(pa.presupuesto_por_vm)} por VM`)}</Grid>
              <Grid item xs={12} md={4}>{kpi('PRODUCTIVIDAD OBJETIVO / CONTACTO', money(pa.productiv_obj_contacto), 'warning.main', 'Presupuesto ÷ contactos')}</Grid>
            </Grid>
            <Table size="small"><TableHead><TableRow>
              <TableCell>Producto</TableCell><TableCell align="center">Presupuesto anual</TableCell><TableCell align="center">Precio prom.</TableCell><TableCell align="right">Productiv. obj/contacto</TableCell><TableCell align="right">Unidades obj/contacto</TableCell><TableCell align="center">Cumplimiento</TableCell>
            </TableRow></TableHead><TableBody>
              {prods.map((p, i) => {
                const pr = pa.productos.find((x) => x.producto === p.producto);
                const cumpl = pr?.cumplimiento_pct ?? 0;
                return (
                  <TableRow key={p.producto}>
                    <TableCell>{p.producto}</TableCell>
                    <TableCell align="center"><TextField size="small" type="number" value={p.presupuesto_anual} sx={{ width: 130 }} onChange={(e) => setP(i, 'presupuesto_anual', Number(e.target.value))} /></TableCell>
                    <TableCell align="center"><TextField size="small" type="number" value={p.precio_prom} sx={{ width: 90 }} onChange={(e) => setP(i, 'precio_prom', Number(e.target.value))} /></TableCell>
                    <TableCell align="right">{money(pr?.productiv_obj_contacto ?? 0)}</TableCell>
                    <TableCell align="right">{(pr?.unidades_obj_contacto ?? 0).toFixed(1)} uds</TableCell>
                    <TableCell align="center"><Chip size="small" color={cumpl >= 100 ? 'success' : cumpl >= 80 ? 'warning' : 'error'} label={`${cumpl}%`} /></TableCell>
                  </TableRow>
                );
              })}
            </TableBody></Table>
          </CardContent></Card>
        </Grid>

        {/* Resumen — costo, retorno y ROI por visita */}
        <Grid item xs={12}>
          <Card variant="outlined"><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1.5 }}><Assessment fontSize="small" color="action" /><Typography variant="subtitle1" fontWeight={700}>Resumen — Costo, Retorno y ROI por Visita</Typography></Stack>
            <Grid container spacing={2} sx={{ mb: 2 }}>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(46,167,106,0.08)', border: '1px solid', borderColor: 'success.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h4" fontWeight={800}>{money(r.costo_total_visita)}</Typography><Typography variant="caption" color="text.secondary">COSTO TOTAL POR VISITA</Typography><Typography variant="caption" display="block" color="text.secondary">Fijo {money(full.fijo.costo_fijo_visita)} + Variable {money(full.muestras.costo_variable_visita)}</Typography></CardContent></Card></Grid>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(46,167,106,0.08)', border: '1px solid', borderColor: 'success.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h4" fontWeight={800}>{money(r.retorno_prom_visita)}</Typography><Typography variant="caption" color="text.secondary">RETORNO PROMEDIO POR VISITA</Typography><Typography variant="caption" display="block" color="text.secondary">Pool total {money(full.pool.pool_total)} ÷ {est.total_visitas} visitas</Typography></CardContent></Card></Grid>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(46,167,106,0.08)', border: '1px solid', borderColor: 'success.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h4" fontWeight={800}>{r.roi_promedio ?? '—'}x</Typography><Typography variant="caption" color="text.secondary">ROI PROMEDIO DE LA FUERZA DE VENTA</Typography><Typography variant="caption" display="block" color={(r.roi_promedio ?? 0) >= 2 ? 'success.main' : 'warning.main'}>{(r.roi_promedio ?? 0) >= 2 ? '✅ Excelente · Retorno superior a 2x' : 'Retorno moderado'}</Typography></CardContent></Card></Grid>
            </Grid>
            <Table size="small"><TableHead><TableRow>
              <TableCell>Producto</TableCell><TableCell align="right">Costo/visita</TableCell><TableCell align="right">Retorno/visita</TableCell><TableCell align="center">ROI</TableCell><TableCell align="center">Estado</TableCell>
            </TableRow></TableHead><TableBody>
              {r.productos.map((x) => (
                <TableRow key={x.producto}>
                  <TableCell>{x.producto}</TableCell>
                  <TableCell align="right">{money(x.costo_visita)}</TableCell>
                  <TableCell align="right"><Typography variant="body2" color="success.main" fontWeight={700}>{money(x.retorno_visita)}</Typography></TableCell>
                  <TableCell align="center"><Typography fontWeight={700}>{x.roi}x</Typography></TableCell>
                  <TableCell align="center"><Chip size="small" color={x.estado === 'Excelente' ? 'success' : x.estado === 'Aceptable' ? 'warning' : 'error'} label={x.estado} /></TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </CardContent></Card>
        </Grid>

        {/* Impacto financiero de la cobertura */}
        <Grid item xs={12}>
          <Card variant="outlined" sx={{ borderColor: 'secondary.light' }}><CardContent>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}><WarningAmber fontSize="small" color="secondary" /><Typography variant="subtitle1" fontWeight={700}>Impacto Financiero de la Cobertura — Venta en Riesgo & Headcount</Typography></Stack>
            <Typography variant="caption" color="text.secondary">Convierte la brecha de cobertura en impacto de venta usando la Productividad Esperada por Contacto (PSP) y un coeficiente de atribución (visita→venta).</Typography>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12} md={6}>
                <Table size="small"><TableHead><TableRow><TableCell>Cat.</TableCell><TableCell align="center">Médicos sin visitar</TableCell><TableCell align="center">PSP / contacto</TableCell></TableRow></TableHead><TableBody>
                  {(['a', 'b', 'c'] as const).map((c) => (
                    <TableRow key={c}>
                      <TableCell><Chip size="small" label={c.toUpperCase()} color={c === 'a' ? 'success' : c === 'b' ? 'primary' : 'default'} /></TableCell>
                      <TableCell align="center"><TextField size="small" type="number" value={est[`med_sin_visitar_${c}` as keyof CostoEstructuraInput] ?? 0} sx={{ width: 100 }} onChange={(e) => setE(`med_sin_visitar_${c}` as keyof CostoEstructuraInput, Number(e.target.value))} /></TableCell>
                      <TableCell align="center"><TextField size="small" type="number" value={est[`psp_${c}` as keyof CostoEstructuraInput] as number} sx={{ width: 120 }} onChange={(e) => setE(`psp_${c}` as keyof CostoEstructuraInput, Number(e.target.value))} /></TableCell>
                    </TableRow>
                  ))}
                </TableBody></Table>
              </Grid>
              <Grid item xs={12} md={6}>
                <Typography variant="body2" fontWeight={600}>Coeficiente de atribución (visita → venta)</Typography>
                <Box sx={{ px: 1 }}>
                  <Typography variant="caption">Conservador: {Math.round(est.coef_conservador * 100)}%</Typography>
                  <Slider size="small" value={Math.round(est.coef_conservador * 100)} onChange={(_, v) => setE('coef_conservador', (v as number) / 100)} />
                  <Typography variant="caption">Optimista: {Math.round(est.coef_optimista * 100)}%</Typography>
                  <Slider size="small" color="secondary" value={Math.round(est.coef_optimista * 100)} onChange={(_, v) => setE('coef_optimista', (v as number) / 100)} />
                </Box>
              </Grid>
            </Grid>
            <Grid container spacing={2} sx={{ mt: 0.5 }}>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(123,90,248,0.08)', border: '1px solid', borderColor: 'secondary.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h5" fontWeight={800} color="secondary.main">{money(im.venta_riesgo_bajo)} – {money(im.venta_riesgo_alto)}</Typography><Typography variant="caption" color="text.secondary">VENTA EN RIESGO POR CICLO (EQUIPO)</Typography></CardContent></Card></Grid>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(123,90,248,0.08)', border: '1px solid', borderColor: 'secondary.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h5" fontWeight={800} color="secondary.main">{im.headcount_equivalente}</Typography><Typography variant="caption" color="text.secondary">HEADCOUNT EQUIVALENTE</Typography></CardContent></Card></Grid>
              <Grid item xs={12} md={4}><Card sx={{ bgcolor: 'rgba(123,90,248,0.08)', border: '1px solid', borderColor: 'secondary.light' }}><CardContent sx={{ textAlign: 'center' }}><Typography variant="h5" fontWeight={800} color="secondary.main">{im.total_medicos_sin_visitar}</Typography><Typography variant="caption" color="text.secondary">MÉDICOS SIN VISITAR (EQUIPO)</Typography></CardContent></Card></Grid>
            </Grid>
            <Table size="small" sx={{ mt: 1 }}><TableHead><TableRow><TableCell>Cat.</TableCell><TableCell align="center">Médicos sin visitar</TableCell><TableCell align="center">PSP / contacto</TableCell><TableCell align="right">Venta en riesgo (bajo)</TableCell><TableCell align="right">Venta en riesgo (alto)</TableCell></TableRow></TableHead><TableBody>
              {im.categorias.map((c) => (
                <TableRow key={c.categoria}>
                  <TableCell><Chip size="small" label={c.categoria} color={c.categoria === 'A' ? 'success' : c.categoria === 'B' ? 'primary' : 'default'} /></TableCell>
                  <TableCell align="center">{c.medicos_sin_visitar}</TableCell>
                  <TableCell align="center">{money(c.psp)}</TableCell>
                  <TableCell align="right">{money(c.venta_riesgo_bajo)}</TableCell>
                  <TableCell align="right"><Typography color="secondary.main" fontWeight={700}>{money(c.venta_riesgo_alto)}</Typography></TableCell>
                </TableRow>
              ))}
            </TableBody></Table>
          </CardContent></Card>
        </Grid>
      </Grid>
    </Box>
  );
}
