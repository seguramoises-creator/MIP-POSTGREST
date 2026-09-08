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
 */
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Box, Card, CardContent, Typography, Stack, Table, TableHead, TableRow,
  TableCell, TableBody, Chip, Alert, CircularProgress, TextField, LinearProgress,
} from '@mui/material';
import { AVISO, AVISO_TENUE, BORDE_SUAVE, EXITO, SUPERFICIE_3, TAUPE_MEDIO } from '../../theme/marca';
import { resumenDia, type FilaRepresentante } from '../../services/visitaDia.service';
import { TEXTO_TENUE } from '../../components/layout/navTokens';

const hoy = () => new Date().toISOString().slice(0, 10);

/** Una cifra grande con su explicación debajo. */
function Tarjeta({ titulo, valor, detalle }: { titulo: string; valor: string; detalle: string }) {
  return (
    <Card variant="outlined" sx={{ flex: 1, minWidth: 210, borderRadius: 2 }}>
      <CardContent sx={{ py: 2 }}>
        <Typography variant="body2" sx={{ color: TEXTO_TENUE }}>{titulo}</Typography>
        <Typography sx={{ fontSize: 34, fontWeight: 800, lineHeight: 1.15 }}>{valor}</Typography>
        <Typography variant="caption" sx={{ color: TEXTO_TENUE }}>{detalle}</Typography>
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

export default function ResumenDia() {
  const [fecha, setFecha] = useState(hoy());
  const { data, isLoading, error } = useQuery({
    queryKey: ['resumen-dia', fecha],
    queryFn: () => resumenDia({ fecha }),
    // Se mira durante la jornada: media hora de antigüedad ya engaña.
    refetchInterval: 120_000,
  });

  if (isLoading) return <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>;
  if (error) return <Alert severity="error" sx={{ m: 3 }}>No se pudo cargar la actividad del día.</Alert>;
  if (!data) return null;

  const { totales, semana, ciclo, representantes } = data;
  const sinRegistros = representantes.filter((r) => r.v + r.r + r.farmacias === 0).length;

  return (
    <Box sx={{ p: { xs: 2, md: 3 } }}>
      <Typography variant="overline" sx={{ color: TEXTO_TENUE, letterSpacing: 1 }}>
        Fuerza de ventas · {fecha === hoy() ? 'hoy' : 'día consultado'}
      </Typography>
      <Typography variant="h5" fontWeight={800}>Así va el día</Typography>
      <Typography variant="body2" sx={{ color: TEXTO_TENUE, mb: 2.5 }}>
        Actividad registrada, por equipo y representante.
      </Typography>

      <TextField type="date" size="small" label="Día" value={fecha}
                 onChange={(e) => setFecha(e.target.value)}
                 InputLabelProps={{ shrink: true }} sx={{ mb: 2.5, width: 190 }} />

      <Stack direction="row" spacing={2} sx={{ mb: 2.5, flexWrap: 'wrap' }} useFlexGap>
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
      <Card variant="outlined" sx={{ mb: 2.5, borderRadius: 2,
                                     bgcolor: semana.calculable ? SUPERFICIE_3 : AVISO_TENUE }}>
        <CardContent sx={{ py: 1.75 }}>
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
                <Typography sx={{ fontSize: 26, fontWeight: 800, color: TAUPE_MEDIO }}>
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
              {representantes.map((r: FilaRepresentante) => {
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
