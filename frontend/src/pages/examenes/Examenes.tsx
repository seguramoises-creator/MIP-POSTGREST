import { useEffect, useState, useCallback, type MouseEvent } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Divider,
  Table, TableHead, TableRow, TableCell, TableBody, Tabs, Tab, Alert, Checkbox,
  FormControlLabel, CircularProgress, Divider as MuiDivider, IconButton, Autocomplete,
  MenuItem, RadioGroup, Radio, InputAdornment,
} from '@mui/material';
import { Add, AutoAwesome, UploadFile, CheckCircle, DeleteOutline, FileDownload } from '@mui/icons-material';
import {
  listarExamenes, crearExamen, agregarPregunta, publicarExamen, asignarExamen,
  resultadosExamen, analisisPreguntas, listarPreguntasExamen, eliminarPregunta,
  generarExamenIA, jobEstadoIA, exportarResultadosExcel, eliminarExamen, listarEvaluados,
  type Examen, type OpcionCrear, type EvaluadoRef, type ResultadosExamen,
  type AnalisisPregunta, type PreguntaConOpciones,
} from '../../services/examenes.service';

type EvalOpt = { tipo: 'RM' | 'GERENTE'; id: number; nombre: string; grupo: string };

// Color del score según la escala del indicador EVAL_CONOCIMIENTOS (nota /10):
//  nota < 8  → factor 0      → rojo  (no aporta al indicador)
//  nota 8–8.9 → factor 0.8–0.89 → ámbar (aprobado, bajo)
//  nota 9–10 → factor 0.9–1.0  → verde (excelente)
function colorPorNota(score: number): string {
  if (score >= 90) return '#1b5e20'; // verde
  if (score >= 80) return '#e65100'; // ámbar/naranja
  return '#b71c1c';                  // rojo
}

// Opción múltiple: 5 opciones (a–e) según el estándar VISTA.
const opcionesVacias = (): OpcionCrear[] =>
  [0, 1, 2, 3, 4].map(() => ({ texto_opcion: '', es_correcta: false }));
const LETRAS = ['a', 'b', 'c', 'd', 'e'];

// Detección para advertencias de redacción (sección 5.3 del spec).
const RE_NEGACION = /\b(no|nunca|jam[aá]s|tampoco|excepto|incorrecto|falso|falsa)\b/i;
const RE_TODAS_NINGUNA = /\b(todas|ninguna)\b.*\banteriores\b/i;

export default function Examenes() {
  const [examenes, setExamenes] = useState<Examen[]>([]);
  const [sel, setSel] = useState<Examen | null>(null);
  const [tab, setTab] = useState(0);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const cargar = useCallback(() => { listarExamenes().then(setExamenes).catch(() => {}); }, []);

  const handleEliminarExamen = async (ex: Examen, e: MouseEvent) => {
    e.stopPropagation();
    if (!window.confirm(`¿Eliminar el examen "${ex.nombre}"? Esta acción no se puede deshacer.`)) return;
    try {
      await eliminarExamen(ex.id);
      setMsg({ tipo: 'success', texto: 'Examen eliminado.' });
      if (sel?.id === ex.id) setSel(null);
      cargar();
    } catch (err: unknown) {
      const detalle = (err as { response?: { status?: number; data?: { detail?: string } } })?.response;
      const texto = detalle?.status === 409
        ? (detalle.data?.detail || 'El examen ya fue tomado; no se puede eliminar.')
        : 'No se pudo eliminar el examen.';
      setMsg({ tipo: 'error', texto });
    }
  };
  useEffect(() => { cargar(); }, [cargar]);

  // Crear examen
  const [nuevo, setNuevo] = useState({ nombre: '', producto: '', nota_minima: 70, tiempo_limite_min: '' as string });
  async function handleCrear() {
    try {
      const ex = await crearExamen({
        nombre: nuevo.nombre, producto: nuevo.producto || null,
        nota_minima: Number(nuevo.nota_minima),
        tiempo_limite_min: nuevo.tiempo_limite_min ? Number(nuevo.tiempo_limite_min) : null,
      });
      setNuevo({ nombre: '', producto: '', nota_minima: 70, tiempo_limite_min: '' });
      setMsg({ tipo: 'success', texto: `Examen "${ex.nombre}" creado en borrador.` });
      cargar(); setSel(ex);
    } catch { setMsg({ tipo: 'error', texto: 'No se pudo crear el examen.' }); }
  }

  // Crear con IA
  const [ia, setIa] = useState({ nombre: '', producto: '', n_multi: 5, n_casos: 0, n_vf: 0, texto_pegado: '' });
  const [iaArchivo, setIaArchivo] = useState<File | null>(null);
  const [iaJob, setIaJob] = useState<{ estado: string; mensaje?: string | null; total?: number } | null>(null);

  function pollIA(jobId: number, examenId: number, intentos = 0) {
    jobEstadoIA(jobId).then((j) => {
      setIaJob({ estado: j.estado, mensaje: j.mensaje_error, total: j.total_preguntas });
      if (j.estado === 'exitoso') {
        setMsg({ tipo: 'success', texto: `IA generó ${j.total_preguntas} pregunta(s). Revísalas en la pestaña Preguntas y publica.` });
        cargar();
        listarExamenes().then((exs) => { const ex = exs.find((e) => e.id === examenId); if (ex) { setSel(ex); setTab(0); } });
      } else if (j.estado === 'error') {
        setMsg({ tipo: 'error', texto: `La generación con IA falló: ${j.mensaje_error || 'error desconocido'}` });
      } else if (intentos < 40) {
        setTimeout(() => pollIA(jobId, examenId, intentos + 1), 2500);
      }
    }).catch(() => setMsg({ tipo: 'error', texto: 'No se pudo consultar el estado de la generación IA.' }));
  }

  async function handleGenerarIA() {
    if (!ia.nombre) return;
    if (!iaArchivo && !ia.texto_pegado.trim()) {
      setMsg({ tipo: 'error', texto: 'Sube un documento (PDF/Word/PPT) o pega texto fuente.' }); return;
    }
    setIaJob({ estado: 'enviando' });
    try {
      const resp = await generarExamenIA({
        nombre: ia.nombre, producto: ia.producto || undefined,
        n_multi: Number(ia.n_multi), n_casos: Number(ia.n_casos), n_vf: Number(ia.n_vf),
        texto_pegado: ia.texto_pegado || undefined, archivo: iaArchivo,
      });
      setIaJob({ estado: 'procesando' });
      setMsg({ tipo: 'success', texto: 'Documento recibido. La IA está generando las preguntas…' });
      pollIA(resp.job_id, resp.examen_id);
      setIa({ nombre: '', producto: '', n_multi: 5, n_casos: 0, n_vf: 0, texto_pegado: '' });
      setIaArchivo(null);
    } catch (e: unknown) {
      const detalle = (e as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setIaJob(null);
      setMsg({ tipo: 'error', texto: `No se pudo iniciar la generación con IA. ${detalle || ''}` });
    }
  }

  // Listado de preguntas del examen (revisión)
  const [preguntasEx, setPreguntasEx] = useState<PreguntaConOpciones[]>([]);
  const cargarPreguntas = useCallback((id: number) => {
    listarPreguntasExamen(id).then(setPreguntasEx).catch(() => setPreguntasEx([]));
  }, []);
  async function handleEliminarPregunta(preguntaId: number) {
    if (!sel) return;
    try { await eliminarPregunta(sel.id, preguntaId); cargarPreguntas(sel.id); }
    catch { setMsg({ tipo: 'error', texto: 'No se pudo eliminar la pregunta.' }); }
  }
  useEffect(() => { if (sel && tab === 0) cargarPreguntas(sel.id); }, [sel, tab, cargarPreguntas]);

  // Pregunta
  const [preg, setPreg] = useState({
    tipo: 'multi' as 'multi' | 'vf', texto: '', explicacion: '', peso: '',
    opciones: opcionesVacias(), vfCorrecta: 'V' as 'V' | 'F',
  });
  function setOpcion(i: number, campo: keyof OpcionCrear, valor: string | boolean) {
    setPreg((p) => {
      const ops = p.opciones.map((o, j) => {
        if (j !== i) return campo === 'es_correcta' ? { ...o, es_correcta: false } : o;
        return { ...o, [campo]: valor } as OpcionCrear;
      });
      return { ...p, opciones: ops };
    });
  }
  async function handleAgregarPregunta() {
    if (!sel) return;
    // Advertencias de redacción (sección 5.3): avisar y pedir confirmación.
    if (RE_NEGACION.test(preg.texto)) {
      if (!window.confirm('El enunciado contiene términos negativos (no, nunca, excepto, falso…). Se recomienda redactar en positivo. ¿Continuar de todas formas?')) return;
    }
    if (preg.tipo === 'multi' && preg.opciones.some((o) => RE_TODAS_NINGUNA.test(o.texto_opcion))) {
      if (!window.confirm('Una opción usa "todas/ninguna de las anteriores". Se recomienda evitarlas. ¿Continuar de todas formas?')) return;
    }
    const opciones = preg.tipo === 'vf'
      ? [
          { texto_opcion: 'Verdadero', es_correcta: preg.vfCorrecta === 'V' },
          { texto_opcion: 'Falso', es_correcta: preg.vfCorrecta === 'F' },
        ]
      : preg.opciones;
    try {
      await agregarPregunta(sel.id, { tipo: preg.tipo, texto: preg.texto, explicacion: preg.explicacion || null, peso: preg.peso ? Number(preg.peso) : null, opciones });
      setPreg({ tipo: preg.tipo, texto: '', explicacion: '', peso: '', opciones: opcionesVacias(), vfCorrecta: 'V' });
      setMsg({ tipo: 'success', texto: 'Pregunta agregada.' });
      cargarPreguntas(sel.id);
    } catch { setMsg({ tipo: 'error', texto: 'Revisa que haya exactamente 1 opción correcta y el examen esté en borrador.' }); }
  }
  async function handlePublicar() {
    if (!sel) return;
    try { const ex = await publicarExamen(sel.id); setSel(ex); setMsg({ tipo: 'success', texto: 'Examen publicado. Ya puedes asignarlo.' }); cargar(); }
    catch { setMsg({ tipo: 'error', texto: 'No se pudo publicar (¿tiene al menos 1 pregunta?).' }); }
  }

  // Asignar
  const [asig, setAsig] = useState({ fecha_limite: '', intentos_max: '1' });
  const [evalOpts, setEvalOpts] = useState<EvalOpt[]>([]);
  const [evalSel, setEvalSel] = useState<EvalOpt[]>([]);
  useEffect(() => {
    listarEvaluados().then((cat) => {
      setEvalOpts([
        ...cat.rms.map((r) => ({ tipo: 'RM' as const, id: r.id, nombre: r.nombre, grupo: 'Representantes Médicos' })),
        ...cat.gerentes.map((g) => ({ tipo: 'GERENTE' as const, id: g.id, nombre: g.nombre, grupo: 'Gerentes de Distrito' })),
      ]);
    }).catch(() => {});
  }, []);
  async function handleAsignar() {
    if (!sel || evalSel.length === 0) return;
    const evaluados: EvaluadoRef[] = evalSel.map((o) => ({ tipo: o.tipo, id: o.id }));
    try {
      await asignarExamen(sel.id, {
        examen_id: sel.id, evaluados,
        fecha_limite: asig.fecha_limite || null,
        intentos_max: asig.intentos_max ? Number(asig.intentos_max) : null,
      });
      setMsg({ tipo: 'success', texto: `Asignado a ${evaluados.length} evaluado(s).` });
      setEvalSel([]); setAsig({ fecha_limite: '', intentos_max: '1' });
    } catch { setMsg({ tipo: 'error', texto: 'No se pudo asignar (el examen debe estar publicado).' }); }
  }

  // Resultados
  const [resultados, setResultados] = useState<ResultadosExamen | null>(null);
  const [analisis, setAnalisis] = useState<AnalisisPregunta[]>([]);
  useEffect(() => {
    if (sel && tab === 2) {
      resultadosExamen(sel.id).then(setResultados).catch(() => setResultados(null));
      analisisPreguntas(sel.id).then(setAnalisis).catch(() => setAnalisis([]));
    }
  }, [sel, tab]);

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      <Typography variant="h5" fontWeight={700} gutterBottom>Exámenes — Capacitación</Typography>
      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <Box sx={{ flex: '1 1 340px', minWidth: 300 }}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography fontWeight={600} gutterBottom>Nuevo examen</Typography>
              <Stack spacing={1.5}>
                <TextField label="Nombre" size="small" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
                <TextField label="Producto" size="small" value={nuevo.producto} onChange={(e) => setNuevo({ ...nuevo, producto: e.target.value })} />
                <Stack direction="row" spacing={1.5}>
                  <TextField label="Nota mínima %" type="number" size="small" value={nuevo.nota_minima} onChange={(e) => setNuevo({ ...nuevo, nota_minima: Number(e.target.value) })} />
                  <TextField label="Tiempo (min)" type="number" size="small" value={nuevo.tiempo_limite_min} onChange={(e) => setNuevo({ ...nuevo, tiempo_limite_min: e.target.value })} />
                </Stack>
                <Button variant="contained" startIcon={<Add />} onClick={handleCrear} disabled={!nuevo.nombre}>Crear borrador</Button>
              </Stack>
            </CardContent>
          </Card>

          <Card variant="outlined" sx={{ mb: 2, borderColor: 'secondary.main' }}>
            <CardContent>
              <Typography fontWeight={600} gutterBottom sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
                <AutoAwesome color="secondary" fontSize="small" /> Crear examen con IA
              </Typography>
              <Typography variant="body2" color="text.secondary" sx={{ mb: 1.5 }}>
                Sube el manual/documento (PDF, Word o PPT) o pega el texto, y la IA elabora las preguntas (quedan en borrador para tu revisión).
              </Typography>
              <Stack spacing={1.5}>
                <TextField label="Nombre del examen" size="small" value={ia.nombre} onChange={(e) => setIa({ ...ia, nombre: e.target.value })} />
                <TextField label="Producto" size="small" value={ia.producto} onChange={(e) => setIa({ ...ia, producto: e.target.value })} />
                <Typography variant="body2" fontWeight={600} sx={{ mt: 0.5 }}>
                  Escribe CUÁNTAS preguntas de cada tipo debe crear la IA:
                </Typography>
                <Stack direction="row" spacing={1.5}>
                  <TextField label="Opción múltiple" type="number" size="small" inputProps={{ min: 0 }}
                             InputProps={{ endAdornment: <InputAdornment position="end">preg.</InputAdornment> }}
                             value={ia.n_multi} onChange={(e) => setIa({ ...ia, n_multi: Number(e.target.value) })} />
                  <TextField label="Verdadero / Falso" type="number" size="small" inputProps={{ min: 0 }}
                             InputProps={{ endAdornment: <InputAdornment position="end">preg.</InputAdornment> }}
                             value={ia.n_vf} onChange={(e) => setIa({ ...ia, n_vf: Number(e.target.value) })} />
                  <TextField label="Casos clínicos" type="number" size="small" inputProps={{ min: 0 }}
                             InputProps={{ endAdornment: <InputAdornment position="end">preg.</InputAdornment> }}
                             value={ia.n_casos} onChange={(e) => setIa({ ...ia, n_casos: Number(e.target.value) })} />
                </Stack>
                <Button component="label" variant="outlined" startIcon={<UploadFile />} size="small">
                  {iaArchivo ? iaArchivo.name : 'Subir documento (PDF/Word/PPT)'}
                  <input hidden type="file" accept=".pdf,.docx,.pptx,.txt"
                         onChange={(e) => setIaArchivo(e.target.files?.[0] ?? null)} />
                </Button>
                <TextField label="…o pega el texto fuente" size="small" multiline minRows={2}
                           value={ia.texto_pegado} onChange={(e) => setIa({ ...ia, texto_pegado: e.target.value })} />
                <Button variant="contained" color="secondary" startIcon={<AutoAwesome />}
                        onClick={handleGenerarIA}
                        disabled={!ia.nombre || iaJob?.estado === 'procesando' || iaJob?.estado === 'enviando'}>
                  Generar con IA
                </Button>
                {iaJob && (iaJob.estado === 'enviando' || iaJob.estado === 'procesando') && (
                  <Stack direction="row" spacing={1} alignItems="center">
                    <CircularProgress size={18} />
                    <Typography variant="body2">Generando preguntas… (esto puede tardar unos segundos)</Typography>
                  </Stack>
                )}
                {iaJob?.estado === 'exitoso' && (
                  <Alert severity="success">Generadas {iaJob.total} pregunta(s). Revísalas en la pestaña Preguntas.</Alert>
                )}
                {iaJob?.estado === 'error' && (
                  <Alert severity="error">Falló: {iaJob.mensaje || 'error desconocido'}</Alert>
                )}
              </Stack>
            </CardContent>
          </Card>

          <Card variant="outlined">
            <CardContent>
              <Typography fontWeight={600} gutterBottom>Exámenes</Typography>
              <Table size="small">
                <TableHead><TableRow><TableCell>Nombre</TableCell><TableCell>Estado</TableCell><TableCell align="right">Acciones</TableCell></TableRow></TableHead>
                <TableBody>
                  {examenes.map((ex) => (
                    <TableRow key={ex.id} hover selected={sel?.id === ex.id} sx={{ cursor: 'pointer' }} onClick={() => { setSel(ex); setTab(0); }}>
                      <TableCell>{ex.nombre}</TableCell>
                      <TableCell><Chip size="small" label={ex.estado} color={ex.estado === 'activo' ? 'success' : 'default'} /></TableCell>
                      <TableCell align="right">
                        <IconButton size="small" color="error" onClick={(e) => handleEliminarExamen(ex, e)} title="Eliminar examen">
                          <DeleteOutline fontSize="small" />
                        </IconButton>
                      </TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </CardContent>
          </Card>
        </Box>

        <Box sx={{ flex: '2 1 420px', minWidth: 300 }}>
          {!sel ? (
            <Alert severity="info">Selecciona o crea un examen para gestionarlo.</Alert>
          ) : (
            <Card variant="outlined">
              <CardContent>
                <Typography variant="h6">{sel.nombre} <Chip size="small" label={sel.estado} sx={{ ml: 1 }} /></Typography>
                <Tabs value={tab} onChange={(_, v) => setTab(v)} sx={{ mb: 2 }}>
                  <Tab label="Preguntas" /><Tab label="Asignar" /><Tab label="Resultados" />
                </Tabs>

                {tab === 0 && (
                  <Stack spacing={1.5}>
                    <Alert severity="info" icon={false} sx={{ '& .MuiAlert-message': { width: '100%' } }}>
                      <Typography variant="caption" fontWeight={700} display="block" gutterBottom>
                        Guía de redacción (estándar VISTA):
                      </Typography>
                      <Typography variant="caption" color="text.secondary" component="div">
                        • Clara y sin ambigüedad — una sola interpretación.<br />
                        • Redacta en <b>positivo</b> (evita "no", "nunca", "excepto").<br />
                        • Un solo concepto por pregunta.<br />
                        • Opción múltiple: <b>5 opciones (a–e)</b> homogéneas y plausibles; sin "todas/ninguna de las anteriores".
                      </Typography>
                    </Alert>
                    <TextField select size="small" label="Tipo de pregunta" value={preg.tipo}
                               onChange={(e) => setPreg({ ...preg, tipo: e.target.value as 'multi' | 'vf' })}
                               sx={{ maxWidth: 280 }}>
                      <MenuItem value="multi">Opción múltiple (elegir la correcta)</MenuItem>
                      <MenuItem value="vf">Verdadero / Falso</MenuItem>
                    </TextField>
                    <TextField label={preg.tipo === 'vf' ? 'Afirmación' : 'Enunciado'} multiline minRows={2}
                               value={preg.texto} onChange={(e) => setPreg({ ...preg, texto: e.target.value })} />
                    {preg.tipo === 'multi' ? (
                      preg.opciones.map((op, i) => (
                        <Stack key={i} direction="row" spacing={1} alignItems="center">
                          <TextField fullWidth size="small" label={`Opción ${LETRAS[i] ?? i + 1}`} value={op.texto_opcion} onChange={(e) => setOpcion(i, 'texto_opcion', e.target.value)} />
                          <FormControlLabel control={<Checkbox checked={op.es_correcta} onChange={(e) => setOpcion(i, 'es_correcta', e.target.checked)} />} label="Correcta" />
                        </Stack>
                      ))
                    ) : (
                      <Box>
                        <Typography variant="body2" color="text.secondary" sx={{ mb: 0.5 }}>
                          ¿La afirmación es verdadera o falsa? (marca la respuesta correcta)
                        </Typography>
                        <RadioGroup row value={preg.vfCorrecta}
                                    onChange={(e) => setPreg({ ...preg, vfCorrecta: e.target.value as 'V' | 'F' })}>
                          <FormControlLabel value="V" control={<Radio color="success" />} label="Verdadero" />
                          <FormControlLabel value="F" control={<Radio color="success" />} label="Falso" />
                        </RadioGroup>
                      </Box>
                    )}
                    <TextField label="Explicación (retroalimentación)" value={preg.explicacion} onChange={(e) => setPreg({ ...preg, explicacion: e.target.value })} />
                    <TextField label="Peso (base 100)" type="number" size="small" sx={{ maxWidth: 220 }}
                               inputProps={{ min: 0, max: 100 }}
                               value={preg.peso} onChange={(e) => setPreg({ ...preg, peso: e.target.value })}
                               helperText="Opcional. Vacío = reparto automático (100 ÷ N). Si pones pesos, deben sumar 100." />
                    <Stack direction="row" spacing={1.5}>
                      <Button variant="outlined" startIcon={<Add />} onClick={handleAgregarPregunta} disabled={sel.estado !== 'borrador'}>Agregar pregunta</Button>
                      <Button variant="contained" color="success" onClick={handlePublicar} disabled={sel.estado !== 'borrador'}>Publicar</Button>
                    </Stack>
                    {sel.estado !== 'borrador' && <Alert severity="info">El examen ya no está en borrador; no se pueden editar preguntas.</Alert>}

                    <MuiDivider sx={{ my: 1 }} />
                    <Typography fontWeight={600}>
                      Preguntas del examen ({preguntasEx.length})
                    </Typography>
                    {preguntasEx.length === 0 && (
                      <Alert severity="info">Aún no hay preguntas. Agrégalas manualmente o genéralas con IA.</Alert>
                    )}
                    {preguntasEx.map((p, i) => (
                      <Card key={p.id} variant="outlined">
                        <CardContent sx={{ py: 1.25 }}>
                          <Box sx={{ display: 'flex', alignItems: 'flex-start', gap: 1 }}>
                            <Typography variant="body2" fontWeight={600} sx={{ flex: 1 }}>
                              {i + 1}. {p.texto}
                              <Chip size="small" variant="outlined" sx={{ ml: 1 }}
                                    color={p.tipo === 'vf' ? 'secondary' : p.tipo === 'caso' ? 'warning' : 'primary'}
                                    label={p.tipo === 'vf' ? 'Verdadero/Falso' : p.tipo === 'caso' ? 'Caso clínico' : 'Opción múltiple'} />
                              <Chip size="small" variant="outlined" sx={{ ml: 0.5 }}
                                    label={p.peso != null ? `peso ${p.peso}` : 'peso auto'} />
                            </Typography>
                            {sel.estado === 'borrador' && (
                              <IconButton size="small" color="error" onClick={() => handleEliminarPregunta(p.id)} title="Eliminar pregunta">
                                <DeleteOutline fontSize="small" />
                              </IconButton>
                            )}
                          </Box>
                          {p.escenario && (
                            <Typography variant="caption" color="text.secondary" display="block">{p.escenario}</Typography>
                          )}
                          <Stack sx={{ mt: 0.5 }}>
                            {p.opciones.map((o) => (
                              <Typography key={o.id} variant="body2"
                                          sx={{ display: 'flex', alignItems: 'center', gap: 0.5,
                                                color: o.es_correcta ? 'success.main' : 'text.secondary' }}>
                                {o.es_correcta && <CheckCircle fontSize="inherit" />} {o.texto_opcion}
                              </Typography>
                            ))}
                          </Stack>
                          {p.explicacion && (
                            <Typography variant="caption" color="text.secondary" sx={{ mt: 0.5, fontStyle: 'italic' }}>
                              {p.explicacion}
                            </Typography>
                          )}
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
                )}

                {tab === 1 && (
                  <Stack spacing={1.5}>
                    {sel.estado !== 'activo' && (
                      <Alert severity="warning"
                             action={sel.estado === 'borrador'
                               ? <Button color="inherit" size="small" onClick={handlePublicar}>Publicar ahora</Button>
                               : undefined}>
                        Este examen está en <b>{sel.estado}</b>. Debes <b>publicarlo</b> (requiere al menos 1 pregunta) antes de poder asignarlo.
                      </Alert>
                    )}
                    <Autocomplete
                      multiple
                      options={evalOpts}
                      value={evalSel}
                      onChange={(_, v) => setEvalSel(v)}
                      groupBy={(o) => o.grupo}
                      getOptionLabel={(o) => o.nombre}
                      isOptionEqualToValue={(a, b) => a.tipo === b.tipo && a.id === b.id}
                      renderTags={(value, getTagProps) =>
                        value.map((o, index) => (
                          <Chip {...getTagProps({ index })} key={`${o.tipo}-${o.id}`} size="small"
                                color={o.tipo === 'RM' ? 'primary' : 'secondary'}
                                label={`${o.tipo === 'RM' ? 'Rep. Médico' : 'Gerente Distrito'} · ${o.nombre}`} />
                        ))
                      }
                      renderInput={(params) => (
                        <TextField {...params} label="Asignar a (Representantes Médicos / Gerentes de Distrito)"
                                   placeholder="Buscar por nombre…"
                                   helperText="Elige por nombre; el grupo indica si es Representante Médico o Gerente de Distrito." />
                      )}
                    />
                    <Stack direction="row" spacing={1.5}>
                      <TextField label="Fecha para tomar el examen" type="date" required
                                 InputLabelProps={{ shrink: true }} value={asig.fecha_limite}
                                 onChange={(e) => setAsig({ ...asig, fecha_limite: e.target.value })}
                                 error={!asig.fecha_limite}
                                 helperText={!asig.fecha_limite ? 'Obligatoria' : ' '} fullWidth />
                      <TextField label="Intentos" type="number" value={asig.intentos_max}
                                 inputProps={{ min: 1 }}
                                 onChange={(e) => setAsig({ ...asig, intentos_max: e.target.value })}
                                 helperText="Por defecto 1" />
                    </Stack>
                    <Button variant="contained" onClick={handleAsignar}
                            disabled={sel.estado !== 'activo' || evalSel.length === 0 || !asig.fecha_limite}>
                      Asignar {evalSel.length > 0 ? `(${evalSel.length})` : ''}
                    </Button>
                  </Stack>
                )}

                {tab === 2 && (
                  <Box>
                    {resultados && (
                      <Stack direction="row" spacing={2} sx={{ mb: 2, flexWrap: 'wrap' }}>
                        <Kpi label="Completitud" valor={`${resultados.completitud_pct}%`} />
                        <Kpi label="Promedio" valor={`${resultados.promedio_score}%`} />
                        <Kpi label="% Aprobación" valor={`${resultados.aprobacion_pct}%`} />
                        <Kpi label="Asignados" valor={`${resultados.asignados}`} />
                      </Stack>
                    )}
                    <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                      <Typography fontWeight={600}>Ranking (último intento)</Typography>
                      <Button size="small" startIcon={<FileDownload />} onClick={() => exportarResultadosExcel(sel.id)}>
                        Exportar a Excel
                      </Button>
                    </Box>
                    <Table size="small" sx={{ '& thead th': { fontWeight: 700, color: 'primary.main', bgcolor: 'rgba(26,35,126,0.04)' } }}>
                      <TableHead><TableRow>
                        <TableCell>Evaluado</TableCell><TableCell>Tipo</TableCell>
                        <TableCell>Fecha del examen</TableCell><TableCell align="center">Score</TableCell><TableCell>Estado</TableCell>
                      </TableRow></TableHead>
                      <TableBody>
                        {resultados?.ranking.map((r, i) => (
                          <TableRow key={i} hover>
                            <TableCell>{r.evaluado_nombre ?? `${r.evaluado_tipo} #${r.evaluado_rm_id ?? r.evaluado_gerente_id}`}</TableCell>
                            <TableCell>
                              <Chip size="small" variant="outlined"
                                    color={r.evaluado_tipo === 'RM' ? 'primary' : 'secondary'}
                                    label={r.evaluado_tipo === 'RM' ? 'Rep. Médico' : 'Gerente Distrito'} />
                            </TableCell>
                            <TableCell>{r.fecha_limite ? new Date(r.fecha_limite).toLocaleDateString() : '—'}</TableCell>
                            <TableCell align="center">
                              {r.ultimo_score == null
                                ? <Typography variant="body2" color="text.secondary">—</Typography>
                                : <Chip size="small" label={`${r.ultimo_score}%`}
                                        sx={{ fontWeight: 700, color: '#fff', minWidth: 64,
                                              bgcolor: colorPorNota(Number(r.ultimo_score)) }} />}
                            </TableCell>
                            <TableCell>
                              <Chip size="small" variant="outlined"
                                    color={r.estado === 'completado' ? 'success' : 'default'}
                                    label={r.estado} />
                            </TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Stack direction="row" spacing={1.5} sx={{ mt: 1, flexWrap: 'wrap', alignItems: 'center' }}>
                      <Typography variant="caption" color="text.secondary">Escala (EVAL_CONOCIMIENTOS):</Typography>
                      <Chip size="small" sx={{ bgcolor: '#1b5e20', color: '#fff', height: 18 }} label="≥ 90% excelente" />
                      <Chip size="small" sx={{ bgcolor: '#e65100', color: '#fff', height: 18 }} label="80–89% aprobado" />
                      <Chip size="small" sx={{ bgcolor: '#b71c1c', color: '#fff', height: 18 }} label="< 80% no aporta" />
                    </Stack>
                    <Divider sx={{ my: 2 }} />
                    <Typography fontWeight={600} gutterBottom>% Error por pregunta</Typography>
                    <Table size="small" sx={{ '& thead th': { fontWeight: 700, color: 'primary.main', bgcolor: 'rgba(26,35,126,0.04)' } }}>
                      <TableHead><TableRow>
                        <TableCell>Pregunta</TableCell><TableCell>Respuesta correcta</TableCell>
                        <TableCell align="center">Respuestas</TableCell><TableCell align="center">% Error</TableCell>
                      </TableRow></TableHead>
                      <TableBody>
                        {analisis.map((a) => (
                          <TableRow key={a.pregunta_id} hover>
                            <TableCell>{a.texto}</TableCell>
                            <TableCell sx={{ color: 'success.main', fontWeight: 600 }}>
                              <Box sx={{ display: 'flex', alignItems: 'center', gap: 0.5 }}>
                                <CheckCircle fontSize="small" /> {a.respuesta_correcta ?? '—'}
                              </Box>
                            </TableCell>
                            <TableCell align="center">{a.total_respuestas}</TableCell>
                            <TableCell align="center">{a.error_pct}%</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                  </Box>
                )}
              </CardContent>
            </Card>
          )}
        </Box>
      </Box>
    </Box>
  );
}

function Kpi({ label, valor }: { label: string; valor: string }) {
  return (
    <Card variant="outlined" sx={{ minWidth: 110 }}>
      <CardContent sx={{ py: 1.5 }}>
        <Typography variant="caption" color="text.secondary">{label}</Typography>
        <Typography variant="h6" fontWeight={700}>{valor}</Typography>
      </CardContent>
    </Card>
  );
}
