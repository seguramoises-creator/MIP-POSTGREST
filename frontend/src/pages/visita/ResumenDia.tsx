/**
 * Monitor del día — «Así va el día».
 *
 * Pantalla de seguimiento, no de análisis: se mira MIENTRAS la jornada corre,
 * para saber quién ha registrado actividad y cómo va contra su agenda. De ahí
 * tres decisiones:
 *
 * 1. El AVANCE SE MIDE CONTRA LA SEMANA. La planeación guarda semana (1-4) y un
 *    día opcional; repartir la semana entre sus días hábiles inventaría un
 *    objetivo que nadie fijó. Cuando la planeación sí trae día, se muestra
 *    además el objetivo del día.
 * 2. SIN AGENDA NO SE PINTA UN CERO. `avance_pct` llega en `null` y se muestra
 *    «—», nunca 0% en rojo: acusar de incumplimiento a quien no tenía nada
 *    planeado es peor que no informar.
 * 3. «SIN REGISTROS» NO ES «NO TRABAJÓ». Un representante sin filas puede no
 *    haber sincronizado; la pantalla lo dice con esas palabras y el panel de
 *    seguimiento invita a revisar la sincronización antes de sacar conclusiones.
 * 4. DIEZ FILAS POR PÁGINA, con paginador. Con cuarenta y tantos representantes la
 *    tabla ocupaba tres pantallas y el resto de la página quedaba fuera de vista;
 *    desplegarla con un botón resolvía lo mismo creciendo, que es justo lo que no
 *    se quiere. Paginada, la tarjeta mide SIEMPRE lo mismo. El orden es por MENOR
 *    avance, así que la primera página ya trae a quien hay que mirar, y el
 *    paginador deja llegar a todos: recortar sin salida sería esconder gente, el
 *    mismo error que pintar un cero donde no hay dato.
 */
import { useEffect, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, Stack, Table, TableHead, TableRow,
  TableCell, TableBody, Chip, Alert, CircularProgress, TextField, LinearProgress, MenuItem,
  Pagination,
} from '@mui/material';
import { AVISO, AVISO_TENUE, BORDE_SUAVE, EXITO, SUPERFICIE_3 } from '../../theme/marca';
import { marcaViva } from '../../theme/marcaViva';
import { resumenDia, type FilaRepresentante } from '../../services/visitaDia.service';
import { listarGerentesVisita, type Catalogo } from '../../services/visita.service';
import { TEXTO_TENUE } from '../../components/layout/navTokens';

const hoy = () => new Date().toISOString().slice(0, 10);

/** Una cifra grande con su explicación debajo. */
function Tarjeta({ titulo, valor, detalle }: { titulo: string; valor: string; detalle: string }) {
  return (
    <Card variant="outlined" sx={{ flex: 1, minWidth: 168, borderRadius: 2 }}>
      {/* Densidad: la cifra manda, el resto acompaña. Antes cada tarjeta gastaba el
          alto de tres filas de la tabla para decir un número de un dígito. */}
      <CardContent sx={{ py: 1, px: 1.5, '&:last-child': { pb: 1 } }}>
        <Typography variant="caption" sx={{ color: TEXTO_TENUE, display: 'block', lineHeight: 1.2 }}>
          {titulo}
        </Typography>
        <Typography sx={{ fontSize: 24, fontWeight: 800, lineHeight: 1.1 }}>{valor}</Typography>
        <Typography variant="caption" sx={{ color: TEXTO_TENUE, fontSize: '0.68rem' }}>
          {detalle}
        </Typography>
      </CardContent>
    </Card>
  );
}

/** Porcentaje de avance, o «—» cuando no hay agenda contra la que medir. */
function Avance({ pct, hechas, planeadas }: { pct: number | null; hechas: number; planeadas: number }) {
  if (pct === null) {
    return <Typography variant="body2" sx={{ color: TEXTO_TENUE }} title="Sin visitas planeadas para esta semana">—</Typography>;
  }
  const color = pct >= 90 ? EXITO : pct >= 60 ? AVISO : undefined;
  return (
    <Box sx={{ minWidth: 108 }}>
      <Typography variant="body2" sx={{ fontWeight: 700, color }}>
        {pct}% <Typography component="span" variant="caption" sx={{ color: TEXTO_TENUE }}>
          {hechas}/{planeadas}
        </Typography>
      </Typography>
      <LinearProgress variant="determinate" value={Math.min(pct, 100)}
                      sx={{ height: 5, borderRadius: 3, mt: 0.4 }} />
    </Box>
  );
}

/** Filas por página. Fija la altura de la tarjeta: no crece con el equipo. */
const POR_PAGINA = 14;

/**
 * Orden de la tabla: primero quien tiene agenda, y dentro de ellos el más
 * atrasado. Es el orden de la ATENCIÓN, no el alfabético — quien va al 20 % de su
 * semana necesita una llamada hoy, y en una lista por código quedaba en el puesto
 * treinta. Los que no tienen planeación van al final: no se les puede medir, así
 * que no compiten por las primeras filas.
 */
function porUrgencia(a: FilaRepresentante, b: FilaRepresentante): number {
  const pa = a.semana.avance_pct, pb = b.semana.avance_pct;
  if (pa === null && pb === null) return a.codigo.localeCompare(b.codigo);
  if (pa === null) return 1;
  if (pb === null) return -1;
  return pa - pb || a.codigo.localeCompare(b.codigo);
}

export default function ResumenDia() {
  const [fecha, setFecha] = useState(hoy());
  const [gerenteId, setGerenteId] = useState<number | ''>('');
  const [pagina, setPagina] = useState(1);
  const [gerentes, setGerentes] = useState<Catalogo[]>([]);

  // El catálogo se pide una vez: no cambia entre días ni entre filtros.
  useEffect(() => { listarGerentesVisita().then(setGerentes).catch(() => setGerentes([])); }, []);

  // Cambiar de día es empezar de cero: quedarse en la página 4 de un día que solo
  // tiene dos dejaría la tabla vacía sin explicar por qué.
  useEffect(() => { setPagina(1); }, [fecha, gerenteId]);
  const { data, isLoading, error } = useQuery({
    // El filtro va al SERVIDOR y no se aplica sobre lo ya traído: las tarjetas de
    // arriba y el avance de la semana los calcula él. Filtrar solo la tabla dejaría
    // «2 visitas registradas» encima de un equipo de un gerente que no hizo ninguna.
    queryKey: ['resumen-dia', fecha, gerenteId],
    queryFn: () => resumenDia({ fecha, ...(gerenteId ? { gerente_id: gerenteId } : {}) }),
    // Se mira durante la jornada: media hora de antigüedad ya engaña.
    refetchInterval: 120_000,
  });

  if (isLoading) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error" sx={{ m: 3 }}>No se pudo cargar la actividad del día.</Alert>;
  if (!data) return null;

  const { totales, semana, ciclo, representantes } = data;
  const sinRegistros = representantes.filter((r) => r.v + r.r + r.farmacias === 0).length;
  const ordenados = [...representantes].sort(porUrgencia);
  const paginas = Math.max(1, Math.ceil(ordenados.length / POR_PAGINA));
  // Se acota al rango REAL en vez de confiar en el estado: si el equipo encoge —otro
  // día, otro filtro— la página guardada puede quedar fuera y la tabla saldría vacía
  // sin decir nada. Acotar aquí es un renglón; diagnosticar «no hay datos» es una tarde.
  const actual = Math.min(pagina, paginas);
  const visibles = ordenados.slice((actual - 1) * POR_PAGINA, actual * POR_PAGINA);
  const conAgenda = representantes.filter((r) => r.semana.avance_pct !== null).length;

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="overline" sx={{ color: TEXTO_TENUE, letterSpacing: 1 }}>
        Fuerza de ventas · {fecha === hoy() ? 'hoy' : 'día consultado'}
      </Typography>
      <Typography variant="h5" fontWeight={800}>Así va el día</Typography>
      <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 1.5 }}>
        Actividad registrada, por equipo y representante.
      </Typography>

      <Stack direction="row" spacing={1.5} sx={{ mb: 1.5, flexWrap: 'wrap' }} useFlexGap>
        <TextField type="date" size="small" label="Día" value={fecha}
                   onChange={(e) => setFecha(e.target.value)}
                   InputLabelProps={{ shrink: true }} sx={{ width: 180 }} />
        <TextField select size="small" label="Gerente de Distrito" value={gerenteId}
                   onChange={(e) => setGerenteId(e.target.value === '' ? '' : Number(e.target.value))}
                   sx={{ minWidth: 240 }}>
          <MenuItem value="">Todos los distritos</MenuItem>
          {gerentes.map((g) => <MenuItem key={g.id} value={g.id}>{g.nombre}</MenuItem>)}
        </TextField>
      </Stack>

      <Stack direction="row" spacing={1.5} sx={{ mb: 1.5, flexWrap: 'wrap' }} useFlexGap>
        <Tarjeta titulo="Visitas registradas" valor={String(totales.visitas)}
                 detalle={`${totales.medicas} médicas · ${totales.farmacias} farmacias`} />
        <Tarjeta titulo="Representantes con actividad"
                 valor={`${totales.rms_con_actividad} / ${totales.rms_total}`}
                 detalle="Al menos un registro recibido" />
        <Tarjeta titulo="Acompañadas por el gerente" valor={String(totales.acompanadas_gd)}
                 detalle="Incluidas en las visitas médicas" />
        <Tarjeta titulo="Hojas MORE del día" valor={String(totales.hojas_more)}
                 detalle="Acompañamientos documentados" />
      </Stack>

      {/* El avance del equipo, o el motivo por el que no se puede calcular. */}
      <Card variant="outlined" sx={{ mb: 1.5, borderRadius: 2,
                                     bgcolor: semana.calculable ? SUPERFICIE_3 : AVISO_TENUE }}>
        <CardContent sx={{ py: 1, '&:last-child': { pb: 1 } }}>
          {semana.calculable ? (
            <>
              <Typography variant="body2" sx={{ fontWeight: 700 }}>
                Avance de la semana {semana.numero} · {ciclo?.nombre}
              </Typography>
              <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 1 }}>
                {semana.ejecutadas} visitas registradas de {semana.planeadas} planeadas para esta
                semana, contadas hasta el día consultado.
              </Typography>
              <Stack direction="row" spacing={2} alignItems="center">
                <Typography sx={{ fontSize: 26, fontWeight: 800, color: marcaViva.taupeMedio }}>
                  {semana.avance_pct}%
                </Typography>
                <LinearProgress variant="determinate" value={Math.min(semana.avance_pct ?? 0, 100)}
                                sx={{ flex: 1, height: 8, borderRadius: 4 }} />
              </Stack>
            </>
          ) : (
            <>
              <Typography variant="body2" sx={{ fontWeight: 700, color: AVISO }}>
                Avance contra agenda: no calculable
              </Typography>
              <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>
                No hay visitas planeadas para esta semana del ciclo, así que no existe una
                referencia contra la que medir. La actividad registrada sí se muestra abajo.
              </Typography>
            </>
          )}
        </CardContent>
      </Card>

      <Card variant="outlined" sx={{ borderRadius: 2 }}>
        <CardContent sx={{ pb: 1 }}>
          <Typography fontWeight={700}>La jornada de cada representante</Typography>
          <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>
            V: visitas médicas · R: revisitas · Con GD: acompañadas · MORE: hojas completadas.
          </Typography>
          {/* Qué se está viendo, dicho antes de la tabla: una lista recortada sin
              avisar se lee como la lista completa. */}
          <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
            {`${ordenados.length} representantes, del menor avance al mayor · `}
            {`${conAgenda} con agenda esta semana`}
          </Typography>
        </CardContent>
        <Box sx={{ overflowX: 'auto' }}>
          <Table size="small">
            <TableHead>
              <TableRow sx={{ '& th': { borderBottom: `2px solid ${BORDE_SUAVE}` } }}>
                <TableCell>Representante / línea</TableCell>
                <TableCell align="right">V</TableCell>
                <TableCell align="right">R</TableCell>
                <TableCell align="right">Farm.</TableCell>
                <TableCell align="right">Con GD</TableCell>
                <TableCell align="right">MORE</TableCell>
                <TableCell>Última actividad</TableCell>
                <TableCell>Avance de la semana</TableCell>
              </TableRow>
            </TableHead>
            <TableBody>
              {visibles.map((r: FilaRepresentante) => {
                const sin = r.v + r.r + r.farmacias === 0;
                return (
                  <TableRow key={r.rm_id} hover>
                    <TableCell>
                      <Typography variant="body2" sx={{ fontWeight: 700 }}>
                        {r.codigo} · {r.nombre}
                      </Typography>
                      <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
                        {[r.linea, r.gerente].filter(Boolean).join(' · ') || '—'}
                      </Typography>
                    </TableCell>
                    <TableCell align="right">{r.v}</TableCell>
                    <TableCell align="right">{r.r}</TableCell>
                    <TableCell align="right">{r.farmacias}</TableCell>
                    <TableCell align="right">{r.con_gd}</TableCell>
                    <TableCell align="right">{r.more}</TableCell>
                    <TableCell>
                      {/* «Sin registros» y no «0 visitas»: puede no haber sincronizado. */}
                      {sin ? <Chip size="small" label="Sin registros" variant="outlined" />
                           : r.ultima_actividad}
                    </TableCell>
                    <TableCell>
                      <Avance pct={r.semana.avance_pct} hechas={r.semana.ejecutadas}
                              planeadas={r.semana.planeadas} />
                    </TableCell>
                  </TableRow>
                );
              })}
            </TableBody>
          </Table>
        </Box>
        {paginas > 1 && (
          <Box sx={{ px: 2, py: 1.5, borderTop: `1px solid ${BORDE_SUAVE}`,
                     display: 'flex', alignItems: 'center', justifyContent: 'space-between',
                     flexWrap: 'wrap', gap: 1 }}>
            <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>
              {(actual - 1) * POR_PAGINA + 1}–{(actual - 1) * POR_PAGINA + visibles.length}
              {' '}de {ordenados.length}
            </Typography>
            {/* Primera y última página además de las flechas: con cinco páginas, volver
                al principio a base de clics es lo que hace que nadie vuelva. */}
            <Pagination count={paginas} page={actual} onChange={(_, p) => setPagina(p)}
                        size="small" shape="rounded" color="primary"
                        showFirstButton showLastButton siblingCount={1} />
          </Box>
        )}
      </Card>

      {sinRegistros > 0 && (
        <Alert severity="info" sx={{ mt: 2 }}>
          <b>{sinRegistros}</b> representante{sinRegistros === 1 ? '' : 's'} sin registros recibidos.
          Conviene revisar la sincronización antes de evaluar su actividad — la ausencia de datos
          no es lo mismo que la ausencia de trabajo.
        </Alert>
      )}
    </Box>
  );
}
