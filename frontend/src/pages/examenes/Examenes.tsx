import { useEffect, useState, useCallback, type MouseEvent } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Divider,
  Table, TableHead, TableRow, TableCell, TableBody, Tabs, Tab, Alert, Checkbox,
  FormControlLabel, CircularProgress, Divider as MuiDivider, IconButton, Autocomplete,
  MenuItem, RadioGroup, Radio, InputAdornment, Switch, Tooltip,
} from '@mui/material';
import { Add, AutoAwesome, UploadFile, CheckCircle, DeleteOutline, FileDownload } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { useCicloStore } from '../../store/ciclo.store';
import ConsolidacionPanel from './ConsolidacionPanel';
import {
  listarExamenes, crearExamen, agregarPregunta, publicarExamen, asignarExamen,
  resultadosExamen, analisisPreguntas, listarPreguntasExamen, eliminarPregunta,
  generarExamenIA, jobEstadoIA, exportarResultadosExcel, eliminarExamen, listarEvaluados,
  respuestasAbiertas, calificarRespuesta, getIaDemo, setIaDemo, enviarCorrecciones,
  type Examen, type OpcionCrear, type EvaluadoRef, type ResultadosExamen,
  type AnalisisPregunta, type PreguntaConOpciones, type RespuestaAbierta,
} from '../../services/examenes.service';
import { AVISO } from '../../theme/marca';
import { detalleError } from '../../utils/errores';

type EvalOpt = { tipo: 'RM' | 'GERENTE'; id: number; nombre: string; grupo: string };

// Color del score según la escala del indicador EVAL_CONOCIMIENTOS (nota /10):
//  nota < 8  → factor 0      → rojo  (no aporta al indicador)
//  nota 8–8.9 → factor 0.8–0.89 → ámbar (aprobado, bajo)
//  nota 9–10 → factor 0.9–1.0  → verde (excelente)
function colorPorNota(score: number): string {
  if (score >= 90) return '#1b5e20'; // verde
  if (score >= 80) return AVISO; // ámbar/naranja
  return '#b71c1c';                  // rojo
}

// Opción múltiple: 5 opciones (a–e) según el estándar VISTA.
const opcionesVacias = (): OpcionCrear[] =>
  [0, 1, 2, 3, 4].map(() => ({ texto_opcion: '', es_correcta: false }));
const LETRAS = ['a', 'b', 'c', 'd', 'e'];

/* ── ETIQUETA Y COLOR DEL TIPO DE PREGUNTA ────────────────────────────────
 * Un MAPA, no una cadena de ternarios, y la diferencia importa.
 *
 * Antes esto era `p.tipo === 'vf' ? … : p.tipo === 'abierta' ? … : 'Opción
 * múltiple'`, o sea que CUALQUIER tipo no contemplado se anunciaba como opción
 * múltiple. Con `objecion` pasó exactamente eso (informe de QA, 21-ago-2026):
 * el servidor guardaba bien `tipo: "objecion"` y el escenario completo, y la
 * pantalla decía otra cosa. Un `?? p.tipo` no miente: un tipo desconocido se ve
 * como desconocido, que es un fallo visible en vez de uno plausible.
 *
 * Los tipos que el backend guarda son cinco (`exam.DimPregunta.tipo`, String(10)):
 * multi, vf, abierta, caso y objecion. `caso_abierto` es solo del formulario —
 * se traduce a `caso` antes de enviarse, y aquí se distingue por no traer
 * opciones.
 */
const ETIQUETA_TIPO: Record<string, string> = {
  multi: 'Opción múltiple',
  vf: 'Verdadero/Falso',
  abierta: 'Abierta',
  objecion: 'Objeción de Producto',
};
const COLOR_TIPO: Record<string, 'primary' | 'secondary' | 'info' | 'warning'> = {
  multi: 'primary',
  vf: 'secondary',
  abierta: 'info',
  caso: 'warning',
  // Naranja igual que el banner que ve el representante al presentar el examen
  // (`MisExamenes.tsx`): la misma pregunta se reconoce por el mismo color en las
  // dos pantallas.
  objecion: 'warning',
};
function etiquetaTipo(p: { tipo: string; opciones: unknown[] }): string {
  if (p.tipo === 'caso') return p.opciones.length === 0 ? 'Caso abierto' : 'Caso';
  return ETIQUETA_TIPO[p.tipo] ?? p.tipo;
}

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

  // Ciclo/país activos del control global — todo examen nuevo se crea contra el ciclo operativo actual.
  const { cicloId, esSoloLectura, paisCodigo } = useCicloStore();

  // Crear examen
  const [nuevo, setNuevo] = useState({ nombre: '', producto: '', nota_minima: 70, tiempo_limite_min: '' as string });
  async function handleCrear() {
    try {
      const ex = await crearExamen({
        nombre: nuevo.nombre, producto: nuevo.producto || null,
        nota_minima: Number(nuevo.nota_minima),
        tiempo_limite_min: nuevo.tiempo_limite_min ? Number(nuevo.tiempo_limite_min) : null,
        ciclo_id: cicloId,
      });
      setNuevo({ nombre: '', producto: '', nota_minima: 70, tiempo_limite_min: '' });
      setMsg({ tipo: 'success', texto: `Examen "${ex.nombre}" creado en borrador.` });
      cargar(); setSel(ex);
    } catch { setMsg({ tipo: 'error', texto: 'No se pudo crear el examen.' }); }
  }

  // Modo de generación con IA (DEMO vs real) — solo lo alterna el ADMIN
  const rol = useAuthStore((s) => s.rol);
  const esAdmin = rol === 'ADMIN';
  const [iaDemo, setIaDemoState] = useState<boolean | null>(null);
  useEffect(() => { if (esAdmin) getIaDemo().then(setIaDemoState).catch(() => {}); }, [esAdmin]);
  async function toggleIaDemo() {
    if (iaDemo === null) return;
    try {
      const nuevo = await setIaDemo(!iaDemo);
      setIaDemoState(nuevo);
      setMsg({ tipo: 'success', texto: `Generación con IA: ${nuevo ? 'modo DEMO (sin gastar API)' : 'Claude real'}.` });
    } catch { setMsg({ tipo: 'error', texto: 'No se pudo cambiar el modo de IA.' }); }
  }

  // Crear con IA
  const [ia, setIa] = useState({ nombre: '', producto: '', n_multi: 5, n_casos: 0, n_vf: 0, n_objeciones: 0, texto_pegado: '' });
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
        n_objeciones: Number(ia.n_objeciones),
        texto_pegado: ia.texto_pegado || undefined, archivo: iaArchivo,
      });
      setIaJob({ estado: 'procesando' });
      setMsg({ tipo: 'success', texto: 'Documento recibido. La IA está generando las preguntas…' });
      pollIA(resp.job_id, resp.examen_id);
      setIa({ nombre: '', producto: '', n_multi: 5, n_casos: 0, n_vf: 0, n_objeciones: 0, texto_pegado: '' });
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
  type TipoPreg = 'multi' | 'vf' | 'abierta' | 'caso' | 'caso_abierto' | 'objecion';
  const [preg, setPreg] = useState({
    tipo: 'multi' as TipoPreg, texto: '', escenario: '', explicacion: '', peso: '',
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
    if ((preg.tipo === 'multi' || preg.tipo === 'caso') && preg.opciones.some((o) => RE_TODAS_NINGUNA.test(o.texto_opcion))) {
      if (!window.confirm('Una opción usa "todas/ninguna de las anteriores". Se recomienda evitarlas. ¿Continuar de todas formas?')) return;
    }
    const esCaso = preg.tipo === 'caso' || preg.tipo === 'caso_abierto';
    const esAbierta = preg.tipo === 'abierta' || preg.tipo === 'caso_abierto';
    const esObjecion = preg.tipo === 'objecion';
    const tipoBackend = esCaso ? 'caso' : preg.tipo;  // 'multi' | 'vf' | 'abierta' | 'caso' | 'objecion'
    const opciones = preg.tipo === 'vf'
      ? [
          { texto_opcion: 'Verdadero', es_correcta: preg.vfCorrecta === 'V' },
          { texto_opcion: 'Falso', es_correcta: preg.vfCorrecta === 'F' },
        ]
      : esAbierta ? [] : preg.opciones;
    try {
      await agregarPregunta(sel.id, {
        tipo: tipoBackend, texto: preg.texto,
        escenario: (esCaso || esObjecion) ? (preg.escenario || null) : null,
        explicacion: preg.explicacion || null,
        peso: preg.peso ? Number(preg.peso) : null, opciones,
      });
      setPreg({ tipo: preg.tipo, texto: '', escenario: '', explicacion: '', peso: '', opciones: opcionesVacias(), vfCorrecta: 'V' });
      setMsg({ tipo: 'success', texto: 'Pregunta agregada.' });
      cargarPreguntas(sel.id);
    } catch (e) {
      // Mostrar el motivo REAL del backend (p. ej. falta el texto de la objeción, el examen ya
      // no está en borrador, o no hay exactamente 1 correcta). Antes se tragaba y el usuario
      // creía que la pregunta se había agregado.
      setMsg({ tipo: 'error', texto: detalleError(e, 'Revisa que haya exactamente 1 opción correcta y el examen esté en borrador.') });
    }
  }
  async function handlePublicar() {
    if (!sel) return;
    try { const ex = await publicarExamen(sel.id); setSel(ex); setMsg({ tipo: 'success', texto: 'Examen publicado. Ya puedes asignarlo.' }); cargar(); }
    catch (e) {
      // El motivo real suele ser la regla de pesos (o todas las preguntas con peso sumando 100,
      // o todas en automático) — antes quedaba oculto tras un mensaje genérico.
      setMsg({ tipo: 'error', texto: detalleError(e, 'No se pudo publicar (¿tiene al menos 1 pregunta?).') });
    }
  }

  // Asignar
  const [asig, setAsig] = useState({ fecha_limite: '', intentos_max: '1' });
  const [evalOpts, setEvalOpts] = useState<EvalOpt[]>([]);
  const [evalSel, setEvalSel] = useState<EvalOpt[]>([]);
  useEffect(() => {
    listarEvaluados(paisCodigo).then((cat) => {
      setEvalOpts([
        ...cat.rms.map((r) => ({ tipo: 'RM' as const, id: r.id, nombre: r.nombre, grupo: 'Representantes Médicos' })),
        ...cat.gerentes.map((g) => ({ tipo: 'GERENTE' as const, id: g.id, nombre: g.nombre, grupo: 'Gerentes de Distrito' })),
      ]);
    }).catch(() => {});
  }, [paisCodigo]);
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

  // Calificar (preguntas abiertas)
  const [abiertas, setAbiertas] = useState<RespuestaAbierta[]>([]);
  const [puntosInput, setPuntosInput] = useState<Record<number, string>>({});
  const cargarAbiertas = useCallback((id: number) => {
    respuestasAbiertas(id).then(setAbiertas).catch(() => setAbiertas([]));
  }, []);
  useEffect(() => { if (sel && tab === 3) cargarAbiertas(sel.id); }, [sel, tab, cargarAbiertas]);
  async function handleCalificar(r: RespuestaAbierta) {
    if (!sel) return;
    const v = Number(puntosInput[r.respuesta_id] ?? r.puntos ?? 0);
    try {
      await calificarRespuesta(r.intento_id, r.respuesta_id, v);
      setMsg({ tipo: 'success', texto: `Calificada: ${v} pts.` });
      cargarAbiertas(sel.id);
    } catch { setMsg({ tipo: 'error', texto: 'No se pudo calificar.' }); }
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

      <ConsolidacionPanel />

      <Box sx={{ display: 'flex', gap: 2, flexWrap: 'wrap', alignItems: 'flex-start' }}>
        <Box sx={{ flex: '1 1 340px', minWidth: 300 }}>
          <Card variant="outlined" sx={{ mb: 2 }}>
            <CardContent>
              <Typography fontWeight={600} gutterBottom>Nuevo examen</Typography>
              {esSoloLectura && (
                <Alert severity="info" sx={{ mb: 1.5 }}>
                  Estás viendo un ciclo distinto al abierto. Solo se pueden crear exámenes en el ciclo abierto.
                </Alert>
              )}
              <Stack spacing={1.5}>
                <TextField label="Nombre" size="small" value={nuevo.nombre} onChange={(e) => setNuevo({ ...nuevo, nombre: e.target.value })} />
                <TextField label="Producto" size="small" value={nuevo.producto} onChange={(e) => setNuevo({ ...nuevo, producto: e.target.value })} />
                <Stack direction="row" spacing={1.5}>
                  <TextField label="Nota mínima %" type="number" size="small" value={nuevo.nota_minima} onChange={(e) => setNuevo({ ...nuevo, nota_minima: Number(e.target.value) })} />
                  <TextField label="Tiempo (min)" type="number" size="small" value={nuevo.tiempo_limite_min} onChange={(e) => setNuevo({ ...nuevo, tiempo_limite_min: e.target.value })} />
                </Stack>
                <Button variant="contained" startIcon={<Add />} onClick={handleCrear} disabled={!nuevo.nombre || esSoloLectura}>Crear borrador</Button>
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
              {esSoloLectura && (
                <Alert severity="info" sx={{ mb: 1.5 }}>
                  Estás viendo un ciclo distinto al abierto. Solo se pueden crear exámenes en el ciclo abierto.
                </Alert>
              )}
              {esAdmin && (
                <Box sx={{ mb: 1.5, p: 1, borderRadius: 1, bgcolor: iaDemo ? 'rgba(255,152,0,0.08)' : 'rgba(27,94,32,0.08)',
                           display: 'flex', alignItems: 'center', justifyContent: 'space-between', flexWrap: 'wrap', gap: 1 }}>
                  <Box>
                    <Typography variant="caption" fontWeight={700} display="block">
                      Modo de generación (solo admin)
                    </Typography>
                    <Typography variant="caption" color="text.secondary">
                      {iaDemo === null ? 'cargando…'
                        : iaDemo ? 'DEMO — preguntas locales [DEMO], sin gastar API'
                        : 'IA real — usa Claude (consume créditos de la API)'}
                    </Typography>
                  </Box>
                  <FormControlLabel
                    control={<Switch color="success" checked={iaDemo === false} disabled={iaDemo === null} onChange={toggleIaDemo} />}
                    label={<Chip size="small" color={iaDemo === false ? 'success' : 'warning'}
                                 label={iaDemo === false ? 'IA REAL' : 'DEMO'} />}
                    labelPlacement="start"
                  />
                </Box>
              )}
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
                  <TextField label="Objeción de Producto" type="number" size="small" inputProps={{ min: 0 }}
                             InputProps={{ endAdornment: <InputAdornment position="end">preg.</InputAdornment> }}
                             value={ia.n_objeciones} onChange={(e) => setIa({ ...ia, n_objeciones: Number(e.target.value) })} />
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
                        disabled={!ia.nombre || iaJob?.estado === 'procesando' || iaJob?.estado === 'enviando' || esSoloLectura}>
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
                  <Tab label="Preguntas" /><Tab label="Asignar" /><Tab label="Resultados" /><Tab label="Calificar" />
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
                    <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                      <TextField select size="small" label="Tipo de pregunta" value={preg.tipo}
                                 onChange={(e) => setPreg({ ...preg, tipo: e.target.value as TipoPreg })}
                                 sx={{ minWidth: 320 }}>
                        <MenuItem value="multi">Opción múltiple (5 opciones)</MenuItem>
                        <MenuItem value="vf">Verdadero / Falso</MenuItem>
                        <MenuItem value="abierta">Abierta (respuesta libre)</MenuItem>
                        <MenuItem value="caso">Caso — consigna de opción múltiple</MenuItem>
                        <MenuItem value="caso_abierto">Caso — consigna abierta</MenuItem>
                        <MenuItem value="objecion">Objeción de Producto</MenuItem>
                      </TextField>
                      <Tooltip title="Evalúa cómo el visitador responde cuando el médico objeta una característica, efecto adverso o limitación del producto. Se muestra en un banner naranja destacado antes de las opciones.">
                        <Button variant="outlined" color="warning" size="small"
                                onClick={() => setPreg({ ...preg, tipo: 'objecion' })}>
                          + Objeción de Producto
                        </Button>
                      </Tooltip>
                    </Stack>
                    {(preg.tipo === 'caso' || preg.tipo === 'caso_abierto') && (
                      <TextField label="Escenario (contexto de la visita médica)" multiline minRows={2}
                                 value={preg.escenario} onChange={(e) => setPreg({ ...preg, escenario: e.target.value })} />
                    )}
                    {preg.tipo === 'objecion' && (
                      <TextField label="Objeción del médico" multiline minRows={2}
                                 value={preg.escenario} onChange={(e) => setPreg({ ...preg, escenario: e.target.value })}
                                 placeholder="Ej: El Dr. García dice: No receto [Producto X] porque escuché que causa [efecto adverso]. El competidor no tiene ese problema." />
                    )}
                    <TextField label={preg.tipo === 'vf' ? 'Afirmación'
                                       : (preg.tipo === 'caso' || preg.tipo === 'caso_abierto') ? 'Consigna'
                                       : preg.tipo === 'objecion' ? 'Pregunta (¿cuál es la mejor respuesta técnica?)'
                                       : 'Enunciado'} multiline minRows={2}
                               value={preg.texto} onChange={(e) => setPreg({ ...preg, texto: e.target.value })} />
                    {(preg.tipo === 'multi' || preg.tipo === 'caso' || preg.tipo === 'objecion') ? (
                      preg.opciones.map((op, i) => (
                        <Stack key={i} direction="row" spacing={1} alignItems="center">
                          <TextField fullWidth size="small" label={`Opción ${LETRAS[i] ?? i + 1}`} value={op.texto_opcion} onChange={(e) => setOpcion(i, 'texto_opcion', e.target.value)} />
                          <FormControlLabel control={<Checkbox checked={op.es_correcta} onChange={(e) => setOpcion(i, 'es_correcta', e.target.checked)} />} label="Correcta" />
                        </Stack>
                      ))
                    ) : (preg.tipo === 'abierta' || preg.tipo === 'caso_abierto') ? (
                      <Alert severity="info" variant="outlined">
                        El evaluado responderá en <b>texto libre</b>. Tú la calificarás manualmente
                        (pestaña <b>Calificar</b>) hasta el peso de la pregunta.
                      </Alert>
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
                            {/* `component="div"`: por defecto Typography pinta un <p>, y los
                                Chip de abajo son <div> — HTML inválido, y React lo avisaba en
                                consola en cada render de esta lista. */}
                            <Typography component="div" variant="body2" fontWeight={600} sx={{ flex: 1 }}>
                              {i + 1}. {p.texto}
                              <Chip size="small" variant="outlined" sx={{ ml: 1 }}
                                    color={COLOR_TIPO[p.tipo] ?? 'default'}
                                    label={etiquetaTipo(p)} />
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
                    <Table size="small" sx={{ '& thead th': { fontWeight: 700, color: 'primary.main', bgcolor: 'rgba(104,97,88,0.04)' } }}>
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
                      <Chip size="small" sx={{ bgcolor: AVISO, color: '#fff', height: 18 }} label="80–89% aprobado" />
                      <Chip size="small" sx={{ bgcolor: '#b71c1c', color: '#fff', height: 18 }} label="< 80% no aporta" />
                    </Stack>
                    <Divider sx={{ my: 2 }} />
                    <Stack direction="row" justifyContent="space-between" alignItems="center" flexWrap="wrap" gap={1}>
                      <Typography fontWeight={600}>Análisis por pregunta (pasa el cursor sobre las barras para ver los nombres)</Typography>
                      <Button size="small" variant="outlined" startIcon={<span>📧</span>}
                              onClick={async () => {
                                try { const r = await enviarCorrecciones(sel.id);
                                  setMsg({ tipo: 'success', texto: `Correcciones enviadas/simuladas a ${r.enviados} participante(s).` });
                                } catch { setMsg({ tipo: 'error', texto: 'No se pudieron enviar las correcciones.' }); }
                              }}>
                        Enviar / Simular correcciones
                      </Button>
                    </Stack>
                    {analisis.length > 0 && (() => {
                      const mejor = [...analisis].sort((a, b) => b.acierto_pct - a.acierto_pct)[0];
                      const peor = [...analisis].sort((a, b) => b.error_pct - a.error_pct)[0];
                      return (
                        <Stack direction="row" spacing={1.5} sx={{ my: 1.5, flexWrap: 'wrap' }}>
                          <Card variant="outlined" sx={{ flex: 1, minWidth: 220, borderColor: 'success.light' }}>
                            <CardContent sx={{ py: 1.25 }}>
                              <Typography variant="caption" color="success.main" fontWeight={700}>MEJOR COMPRENDIDA</Typography>
                              <Typography variant="body2" fontWeight={600}>{mejor.texto}</Typography>
                              <Typography variant="caption">{mejor.acierto_pct}% acierto</Typography>
                            </CardContent>
                          </Card>
                          <Card variant="outlined" sx={{ flex: 1, minWidth: 220, borderColor: 'error.light' }}>
                            <CardContent sx={{ py: 1.25 }}>
                              <Typography variant="caption" color="error.main" fontWeight={700}>MÁS FALLADA</Typography>
                              <Typography variant="body2" fontWeight={600}>{peor.texto}</Typography>
                              <Typography variant="caption">{peor.error_pct}% desacierto</Typography>
                            </CardContent>
                          </Card>
                        </Stack>
                      );
                    })()}
                    <Table size="small" sx={{ '& thead th': { fontWeight: 700, color: 'primary.main', bgcolor: 'rgba(104,97,88,0.04)' } }}>
                      <TableHead><TableRow>
                        <TableCell>#</TableCell><TableCell>Pregunta</TableCell>
                        <TableCell align="center" sx={{ width: 90 }}>% Acierto</TableCell>
                        <TableCell align="center" sx={{ width: 90 }}>% Desacierto</TableCell>
                        <TableCell>Etiqueta</TableCell>
                      </TableRow></TableHead>
                      <TableBody>
                        {analisis.map((a, i) => (
                          <TableRow key={a.pregunta_id} hover>
                            <TableCell>{i + 1}</TableCell>
                            <TableCell>{a.texto}</TableCell>
                            <TableCell align="center">
                              <Tooltip arrow title={a.aciertan.length ? a.aciertan.join(', ') : 'Nadie acertó'}>
                                <Box sx={{ bgcolor: 'success.light', color: '#000', borderRadius: 1, px: 0.5, cursor: 'help', fontWeight: 600 }}>{a.acierto_pct}%</Box>
                              </Tooltip>
                            </TableCell>
                            <TableCell align="center">
                              <Tooltip arrow title={a.fallan.length ? a.fallan.join(', ') : 'Nadie falló'}>
                                <Box sx={{ bgcolor: a.error_pct > 0 ? 'error.light' : 'grey.200', color: '#000', borderRadius: 1, px: 0.5, cursor: 'help', fontWeight: 600 }}>{a.error_pct}%</Box>
                              </Tooltip>
                            </TableCell>
                            <TableCell>{a.etiqueta}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    {(() => {
                      const recs = analisis.filter((a) => a.error_pct >= 40);
                      return recs.length > 0 && (
                        <Alert severity="warning" sx={{ mt: 1.5 }}>
                          <Typography fontWeight={700}>Recomendaciones de refuerzo (desacierto ≥ 40%)</Typography>
                          {recs.map((a) => (
                            <Typography key={a.pregunta_id} variant="body2">
                              • <b>{a.texto}</b> — {a.error_pct}% · fallaron: {a.fallan.join(', ') || '—'}
                            </Typography>
                          ))}
                        </Alert>
                      );
                    })()}
                  </Box>
                )}

                {tab === 3 && (
                  <Stack spacing={1.5}>
                    <Typography variant="caption" color="text.secondary">
                      Califica las respuestas de preguntas abiertas / caso-abierto (hasta el peso de cada pregunta).
                    </Typography>
                    {abiertas.length === 0 && (
                      <Alert severity="info">No hay respuestas abiertas para calificar en este examen.</Alert>
                    )}
                    {abiertas.map((r) => (
                      <Card key={r.respuesta_id} variant="outlined">
                        <CardContent sx={{ py: 1.25 }}>
                          <Box sx={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                            <Typography fontWeight={600}>{r.evaluado_nombre}</Typography>
                            <Chip size="small" color={r.calificada ? 'success' : 'warning'}
                                  label={r.calificada ? `${r.puntos} pts` : 'pendiente'} />
                          </Box>
                          {r.escenario && (
                            <Typography variant="caption" color="text.secondary" display="block">{r.escenario}</Typography>
                          )}
                          <Typography variant="body2" fontWeight={600} sx={{ mt: 0.5 }}>{r.pregunta_texto}</Typography>
                          <Alert severity="info" variant="outlined" sx={{ my: 1 }}>{r.respuesta_texto}</Alert>
                          <Stack direction="row" spacing={1} alignItems="center">
                            <TextField size="small" type="number" label={`Puntos (máx ${r.peso ?? '—'})`} sx={{ maxWidth: 170 }}
                                       inputProps={{ min: 0, max: r.peso ?? undefined }}
                                       value={puntosInput[r.respuesta_id] ?? (r.puntos ?? '')}
                                       onChange={(e) => setPuntosInput({ ...puntosInput, [r.respuesta_id]: e.target.value })} />
                            <Button variant="contained" size="small" onClick={() => handleCalificar(r)}>Guardar</Button>
                          </Stack>
                        </CardContent>
                      </Card>
                    ))}
                  </Stack>
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
