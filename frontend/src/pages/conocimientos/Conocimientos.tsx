/**
 * Conocimientos — quién alimenta EVAL_CONOCIMIENTOS y captura manual de notas.
 *
 * Sustituye al Excel para este indicador. Los controles de captura se apagan
 * por dos motivos independientes:
 *   - Fuente ajena: el backend SÍ guarda una puerta (`/conocimientos/integrar`
 *     responde 409 si el país no es CAPTURA_MANUAL) — apagar el botón aquí
 *     solo evita que el usuario descubra el 409 después de teclear notas.
 *   - Ciclo en consulta (`esSoloLectura`): NO hay guard en el backend para
 *     `POST /notas` ni `PUT /notas/{id}` — nada impide, hoy, capturar sobre un
 *     ciclo que no es el de trabajo salvo este `disabled` de la pantalla. Que
 *     quede claro para no repetir aquí la afirmación errónea de que "la
 *     puerta que manda es la del backend" para AMBOS motivos.
 */
import { useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Alert, Box, Button, Chip, MenuItem, Paper, Select, Table, TableBody,
  TableCell, TableHead, TableRow, TextField, Typography,
} from '@mui/material';
import { Edit, PlaylistAddCheck, Save } from '@mui/icons-material';
import { useCicloStore } from '../../store/ciclo.store';
import {
  cambiarFuente, capturarNota, corregirNota, integrarCaptura, listarNotas,
  verFuente, type FuenteConocimientos,
} from '../../services/conocimientos.service';

const EXPLICACION: Record<FuenteConocimientos, string> = {
  EXAMEN_VISTA: 'Las notas salen de los exámenes de VISTA; Capacitación las consolida por ciclo. Esta pantalla queda de solo lectura.',
  NOTA_EXTERNA: 'Las notas las envía Laboratorio Mallén y entran por la integración. Esta pantalla queda de solo lectura.',
  CAPTURA_MANUAL: 'Las notas se capturan aquí y entran al ciclo con el botón "Integrar al ciclo".',
};

// El `motivo` que devuelve `POST /conocimientos/integrar` es un código interno
// (igual que en ETL/recálculo: "ciclo_cerrado"). Traducirlo aquí evita pintarle
// al operador el literal crudo.
const MOTIVO_ABORTO: Record<string, string> = {
  ciclo_cerrado: 'el ciclo está cerrado (snapshot histórico inmutable).',
};

function mensajeError(e: unknown, respaldo: string): string {
  const det = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
  return typeof det === 'string' && det ? det : respaldo;
}

export default function Conocimientos() {
  const qc = useQueryClient();
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const cicloId = useCicloStore((s) => s.cicloId);
  const esSoloLectura = useCicloStore((s) => s.esSoloLectura);
  const [error, setError] = useState<string | null>(null);
  const [aviso, setAviso] = useState<string | null>(null);
  const [nuevo, setNuevo] = useState<{ rm_id: number; nota: string; fecha: string; tema: string } | null>(null);
  const [editando, setEditando] = useState<{ id: number; nota: string; tema: string } | null>(null);

  const fuente = useQuery({
    queryKey: ['conocimientos-fuente', paisCodigo],
    queryFn: () => verFuente(paisCodigo as string),
    enabled: !!paisCodigo,
  });

  const notas = useQuery({
    queryKey: ['conocimientos-notas', paisCodigo, cicloId],
    queryFn: () => listarNotas(paisCodigo as string, cicloId as number),
    enabled: !!paisCodigo && !!cicloId,
  });

  const refrescar = () => qc.invalidateQueries({ queryKey: ['conocimientos-notas'] });

  const mutFuente = useMutation({
    mutationFn: (f: FuenteConocimientos) => cambiarFuente(paisCodigo as string, f),
    onSuccess: () => { setError(null); qc.invalidateQueries({ queryKey: ['conocimientos-fuente'] }); },
    onError: (e) => setError(mensajeError(e, 'No se pudo cambiar la fuente.')),
  });

  const mutCapturar = useMutation({
    mutationFn: () => capturarNota({
      pais_codigo: paisCodigo as string, ciclo_id: cicloId as number,
      rm_id: nuevo!.rm_id, nota: Number(nuevo!.nota),
      fecha_evaluacion: nuevo!.fecha, tema: nuevo!.tema || null,
    }),
    onSuccess: () => { setNuevo(null); setError(null); refrescar(); },
    onError: (e) => setError(mensajeError(e, 'No se pudo capturar la nota.')),
  });

  const mutCorregir = useMutation({
    mutationFn: () => corregirNota(editando!.id, Number(editando!.nota), editando!.tema || null),
    onSuccess: () => { setEditando(null); setError(null); refrescar(); },
    onError: (e) => setError(mensajeError(e, 'No se pudo corregir la nota.')),
  });

  const mutIntegrar = useMutation({
    mutationFn: () => integrarCaptura(paisCodigo as string, cicloId as number),
    onSuccess: (r) => {
      setError(null);
      setAviso(r.abortado
        ? `No se integró: ${(r.motivo && MOTIVO_ABORTO[r.motivo]) || r.motivo || 'motivo desconocido'}`
        : `${r.rms_integrados} representante(s) integrados al ciclo.`);
      refrescar();
    },
    onError: (e) => setError(mensajeError(e, 'No se pudo integrar.')),
  });

  if (!paisCodigo || !cicloId) {
    return <Alert severity="info" sx={{ m: 3 }}>
      Selecciona país y ciclo en el encabezado.
    </Alert>;
  }

  const esCaptura = fuente.data?.fuente === 'CAPTURA_MANUAL';
  const puedeCapturar = esCaptura && !esSoloLectura;

  return (
    <Box sx={{ p: 3 }}>
      <Typography variant="h5" fontWeight={700} sx={{ mb: 2 }}>Conocimientos</Typography>

      {/* Sin esto, un 403/500 en cualquiera de las dos queries deja la tabla
          vacía y los botones apagados sin ningún mensaje — indistinguible de
          "no hay datos" en una pantalla cuyo propósito es saber a quién le
          falta nota. */}
      {fuente.isLoading && <Alert severity="info" sx={{ mb: 2 }}>Cargando la fuente configurada…</Alert>}
      {fuente.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeError(fuente.error, 'No se pudo cargar la fuente configurada.')}
        </Alert>
      )}
      {notas.isLoading && <Alert severity="info" sx={{ mb: 2 }}>Cargando las notas del ciclo…</Alert>}
      {notas.isError && (
        <Alert severity="error" sx={{ mb: 2 }}>
          {mensajeError(notas.error, 'No se pudieron cargar las notas del ciclo.')}
        </Alert>
      )}

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2, p: 2, mb: 3 }}>
        <Box sx={{ display: 'flex', alignItems: 'center', gap: 2 }}>
          <Typography variant="subtitle2" fontWeight={700}>
            Quién alimenta EVAL_CONOCIMIENTOS en {paisCodigo}
          </Typography>
          <Select size="small" sx={{ minWidth: 220 }}
            value={fuente.data?.fuente ?? ''}
            onChange={(e) => mutFuente.mutate(e.target.value as FuenteConocimientos)}>
            {(fuente.data?.fuentes ?? []).map((f) => (
              <MenuItem key={f} value={f}>{f}</MenuItem>
            ))}
          </Select>
        </Box>
        {fuente.data && (
          <Typography variant="body2" color="text.secondary" sx={{ mt: 1 }}>
            {EXPLICACION[fuente.data.fuente]}
          </Typography>
        )}
      </Paper>

      {fuente.data && !esCaptura && (
        <Alert severity="warning" sx={{ mb: 2 }}>
          En {paisCodigo} el indicador lo alimenta «{fuente.data.fuente}»: aquí no
          se puede capturar ni integrar. Cambia la fuente arriba si esa es la decisión.
        </Alert>
      )}
      {esCaptura && esSoloLectura && (
        <Alert severity="info" sx={{ mb: 2 }}>
          Estás viendo un ciclo que no es el de trabajo: la captura queda en
          solo lectura. Cambia al ciclo abierto en el encabezado para capturar o corregir notas.
        </Alert>
      )}
      {error && <Alert severity="error" sx={{ mb: 2 }}>{error}</Alert>}
      {aviso && <Alert severity="success" sx={{ mb: 2 }} onClose={() => setAviso(null)}>{aviso}</Alert>}

      <Box sx={{ display: 'flex', justifyContent: 'flex-end', mb: 2 }}>
        <Button variant="contained" startIcon={<PlaylistAddCheck />}
          disabled={!puedeCapturar || mutIntegrar.isPending}
          onClick={() => mutIntegrar.mutate()}>
          {mutIntegrar.isPending ? 'Integrando…' : 'Integrar al ciclo'}
        </Button>
      </Box>

      <Paper elevation={0} sx={{ border: '1px solid #e0e7ef', borderRadius: 2 }}>
        <Table size="small">
          <TableHead>
            <TableRow>
              <TableCell>Representante</TableCell>
              <TableCell>Notas del ciclo</TableCell>
              <TableCell align="right">Promedio</TableCell>
              <TableCell align="right">Capturar</TableCell>
            </TableRow>
          </TableHead>
          <TableBody>
            {(notas.data ?? []).map((f) => (
              <TableRow key={f.rm_id} sx={{ opacity: f.notas.length ? 1 : 0.55 }}>
                <TableCell>
                  {f.rm_codigo} — {f.rm_nombre}
                  {!f.notas.length && <Chip size="small" label="falta" color="warning" sx={{ ml: 1 }} />}
                </TableCell>
                <TableCell>
                  {f.notas.map((n) => (
                    <Box key={n.id} sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                      {editando?.id === n.id ? (
                        <>
                          <TextField size="small" type="number" sx={{ width: 90 }}
                            value={editando.nota}
                            onChange={(e) => setEditando({ ...editando, nota: e.target.value })} />
                          <TextField size="small" sx={{ width: 140 }} placeholder="Tema"
                            value={editando.tema}
                            onChange={(e) => setEditando({ ...editando, tema: e.target.value })} />
                          <Button size="small" startIcon={<Save />}
                            disabled={mutCorregir.isPending}
                            onClick={() => mutCorregir.mutate()}>Guardar</Button>
                          <Button size="small" onClick={() => setEditando(null)}>Cancelar</Button>
                        </>
                      ) : (
                        <>
                          <Typography variant="body2">
                            {n.nota}{n.tema ? ` · ${n.tema}` : ''} · {n.fecha_evaluacion}
                          </Typography>
                          <Button size="small" startIcon={<Edit />} disabled={!puedeCapturar}
                            onClick={() => setEditando({ id: n.id, nota: String(n.nota), tema: n.tema ?? '' })}>
                            Corregir
                          </Button>
                        </>
                      )}
                    </Box>
                  ))}
                  {nuevo?.rm_id === f.rm_id && (
                    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1, mt: 1 }}>
                      <TextField size="small" type="number" sx={{ width: 90 }} label="Nota"
                        value={nuevo.nota} onChange={(e) => setNuevo({ ...nuevo, nota: e.target.value })} />
                      <TextField size="small" type="date" sx={{ width: 160 }}
                        value={nuevo.fecha} onChange={(e) => setNuevo({ ...nuevo, fecha: e.target.value })} />
                      <TextField size="small" sx={{ width: 140 }} label="Tema"
                        value={nuevo.tema} onChange={(e) => setNuevo({ ...nuevo, tema: e.target.value })} />
                      <Button size="small" variant="contained"
                        disabled={!nuevo.nota || mutCapturar.isPending}
                        onClick={() => mutCapturar.mutate()}>Añadir</Button>
                      <Button size="small" onClick={() => setNuevo(null)}>Cancelar</Button>
                    </Box>
                  )}
                </TableCell>
                {/* El promedio que integra al ciclo (`integrar_captura`) usa el valor
                    EXACTO — este `.toFixed(2)` es solo de presentación: `promedio` sale
                    de `sum/len` con `Decimal` de 28 dígitos y, sin redondear, tres notas
                    80/85/83 pintarían "82.66666666666667". */}
                <TableCell align="right">{f.promedio !== null ? f.promedio.toFixed(2) : '—'}</TableCell>
                <TableCell align="right">
                  <Button size="small" disabled={!puedeCapturar}
                    onClick={() => setNuevo({
                      rm_id: f.rm_id, nota: '', tema: '',
                      fecha: new Date().toISOString().slice(0, 10),
                    })}>
                    Añadir nota
                  </Button>
                </TableCell>
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </Paper>
    </Box>
  );
}
