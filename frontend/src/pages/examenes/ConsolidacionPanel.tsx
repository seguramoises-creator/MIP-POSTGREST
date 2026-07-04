import { useEffect, useState } from 'react';
import {
  Card, CardContent, Box, Typography, Button, Chip, Stack,
  Alert, CircularProgress, Divider, Tooltip,
} from '@mui/material';
import { Lock, CheckCircle } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  consolidacionEstado, consolidarCiclo, type ConsolidacionEstado,
} from '../../services/examenes.service';

/**
 * Panel "Consolidación de Ciclo → KPI": el gate del módulo de Exámenes. Escribe la
 * nota EVAL_CONOCIMIENTOS de los RM del (ciclo, país) a la FACT del motor de KPI —
 * es la ÚNICA vía por la que la nota entra al sistema. Solo Capacitación.
 *
 * Opera siempre sobre el ciclo/país del control global (useCicloStore), no sobre
 * un desplegable local — evita listar los ~72 ciclos históricos de todos los países.
 */
export default function ConsolidacionPanel() {
  const { cicloId, paisCodigo, ciclo } = useCicloStore();
  const [estado, setEstado] = useState<ConsolidacionEstado | null>(null);
  const [cargando, setCargando] = useState(false);
  const [ejecutando, setEjecutando] = useState(false);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const label = ciclo ? `${ciclo.nombre_canonico || ciclo.nombre} — ${ciclo.pais_codigo}` : '—';

  const cargarEstado = (cid: number, pais: string) => {
    setCargando(true); setMsg(null);
    consolidacionEstado(cid, pais)
      .then(setEstado)
      .catch(() => setMsg({ tipo: 'error', texto: 'No se pudo consultar el estado de consolidación.' }))
      .finally(() => setCargando(false));
  };

  useEffect(() => {
    if (cicloId != null && paisCodigo) cargarEstado(cicloId, paisCodigo);
    else setEstado(null);
  }, [cicloId, paisCodigo]);

  const consolidar = async () => {
    if (cicloId == null || !paisCodigo) return;
    if (!window.confirm(
      `Se escribirá la nota EVAL_CONOCIMIENTOS de ${estado?.rms_con_nota ?? 0} RM al KPI del ciclo `
      + `${label} y se recalculará el ranking. ¿Continuar?`)) return;
    setEjecutando(true); setMsg(null);
    try {
      const r = await consolidarCiclo(cicloId, paisCodigo);
      if (r.abortado) {
        setMsg({ tipo: 'error', texto: 'Consolidación abortada: el ciclo está cerrado.' });
      } else {
        setMsg({ tipo: 'success', texto: `Consolidado: ${r.rms_consolidados} RM (promedio ${r.nota_promedio_equipo ?? '—'}). Ranking recalculado.` });
        cargarEstado(cicloId, paisCodigo);
      }
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo consolidar el ciclo.' });
    } finally { setEjecutando(false); }
  };

  return (
    <Card variant="outlined" sx={{ mb: 2, borderColor: 'primary.main' }}>
      <CardContent>
        <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 0.5 }}>
          <Lock color="primary" fontSize="small" />
          <Typography fontWeight={700}>Consolidación de Ciclo → KPI (EVAL_CONOCIMIENTOS)</Typography>
        </Stack>
        <Typography variant="caption" color="text.secondary">
          La nota de exámenes de los RM entra al KPI <b>solo</b> cuando consolidas el ciclo aquí.
          Reejecutable mientras el ciclo esté abierto.
        </Typography>

        <Box sx={{ display: 'flex', gap: 1.5, alignItems: 'center', flexWrap: 'wrap', mt: 1.5 }}>
          <Box>
            <Typography variant="caption" color="text.secondary" display="block">Ciclo</Typography>
            <Typography fontWeight={600}>{label}</Typography>
          </Box>
          {cargando && <CircularProgress size={22} />}
          {estado && (
            <Tooltip arrow title={estado.ciclo_abierto ? 'Ciclo abierto — se puede consolidar'
              : 'Ciclo cerrado — snapshot inmutable, no se consolida'}>
              <Chip size="small" color={estado.ciclo_abierto ? 'success' : 'default'}
                    label={estado.ciclo_abierto ? 'Ciclo abierto' : 'Ciclo cerrado'} />
            </Tooltip>
          )}
        </Box>

        {estado && (
          <>
            <Divider sx={{ my: 1.5 }} />
            <Stack direction="row" spacing={3} flexWrap="wrap" sx={{ mb: 1 }}>
              <Box>
                <Typography variant="caption" color="text.secondary">RM con nota</Typography>
                <Typography variant="h6" fontWeight={800} color="primary.main">{estado.rms_con_nota}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Promedio equipo</Typography>
                <Typography variant="h6" fontWeight={800}>{estado.nota_promedio_equipo ?? '—'}</Typography>
              </Box>
              <Box>
                <Typography variant="caption" color="text.secondary">Estado del gate</Typography>
                <Box><Chip size="small" icon={estado.estado === 'consolidado' ? <CheckCircle /> : undefined}
                     color={estado.estado === 'consolidado' ? 'success' : 'warning'}
                     label={estado.estado === 'consolidado' ? 'Consolidado' : 'Pendiente'} /></Box>
              </Box>
              {estado.ultima_consolidacion && (
                <Box>
                  <Typography variant="caption" color="text.secondary">Última consolidación</Typography>
                  <Typography variant="body2">{new Date(estado.ultima_consolidacion).toLocaleString()}</Typography>
                </Box>
              )}
            </Stack>
            {estado.rms_con_nota_nombres.length > 0 && (
              <Typography variant="caption" color="text.secondary">
                RM: {estado.rms_con_nota_nombres.join(', ')}
              </Typography>
            )}
            <Box sx={{ mt: 1.5 }}>
              <Button variant="contained" startIcon={<Lock />} disabled={!estado.ciclo_abierto || ejecutando || estado.rms_con_nota === 0}
                      onClick={consolidar}>
                {ejecutando ? 'Consolidando…' : 'Consolidar ciclo → KPI'}
              </Button>
              {estado.rms_con_nota === 0 && (
                <Typography variant="caption" color="text.secondary" sx={{ ml: 1.5 }}>
                  No hay RM con nota de exámenes en este ciclo todavía.
                </Typography>
              )}
            </Box>
          </>
        )}

        {msg && <Alert severity={msg.tipo} sx={{ mt: 1.5 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}
      </CardContent>
    </Card>
  );
}
