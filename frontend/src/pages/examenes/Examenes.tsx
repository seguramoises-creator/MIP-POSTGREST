import { useEffect, useState, useCallback } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Divider,
  Table, TableHead, TableRow, TableCell, TableBody, Tabs, Tab, Alert, Checkbox,
  FormControlLabel,
} from '@mui/material';
import { Add } from '@mui/icons-material';
import {
  listarExamenes, crearExamen, agregarPregunta, publicarExamen, asignarExamen,
  resultadosExamen, analisisPreguntas,
  type Examen, type OpcionCrear, type EvaluadoRef, type ResultadosExamen,
  type AnalisisPregunta,
} from '../../services/examenes.service';

const opcionesVacias = (): OpcionCrear[] =>
  [0, 1, 2, 3].map(() => ({ texto_opcion: '', es_correcta: false }));

export default function Examenes() {
  const [examenes, setExamenes] = useState<Examen[]>([]);
  const [sel, setSel] = useState<Examen | null>(null);
  const [tab, setTab] = useState(0);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const cargar = useCallback(() => { listarExamenes().then(setExamenes).catch(() => {}); }, []);
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

  // Pregunta
  const [preg, setPreg] = useState({ texto: '', explicacion: '', opciones: opcionesVacias() });
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
    try {
      await agregarPregunta(sel.id, { tipo: 'multi', texto: preg.texto, explicacion: preg.explicacion || null, opciones: preg.opciones });
      setPreg({ texto: '', explicacion: '', opciones: opcionesVacias() });
      setMsg({ tipo: 'success', texto: 'Pregunta agregada.' });
    } catch { setMsg({ tipo: 'error', texto: 'Revisa que haya exactamente 1 opción correcta y el examen esté en borrador.' }); }
  }
  async function handlePublicar() {
    if (!sel) return;
    try { await publicarExamen(sel.id); setMsg({ tipo: 'success', texto: 'Examen publicado.' }); cargar(); }
    catch { setMsg({ tipo: 'error', texto: 'No se pudo publicar (¿tiene al menos 1 pregunta?).' }); }
  }

  // Asignar
  const [asig, setAsig] = useState({ evaluados: '', fecha_limite: '', intentos_max: '' });
  async function handleAsignar() {
    if (!sel) return;
    const evaluados: EvaluadoRef[] = asig.evaluados.split(',').map((s) => s.trim()).filter(Boolean).map((tok) => {
      const [tipo, id] = tok.split(':');
      return { tipo: (tipo.toUpperCase() as 'RM' | 'GERENTE'), id: Number(id) };
    });
    try {
      await asignarExamen(sel.id, {
        examen_id: sel.id, evaluados,
        fecha_limite: asig.fecha_limite || null,
        intentos_max: asig.intentos_max ? Number(asig.intentos_max) : null,
      });
      setMsg({ tipo: 'success', texto: `Asignado a ${evaluados.length} evaluado(s).` });
      setAsig({ evaluados: '', fecha_limite: '', intentos_max: '' });
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

          <Card variant="outlined">
            <CardContent>
              <Typography fontWeight={600} gutterBottom>Exámenes</Typography>
              <Table size="small">
                <TableHead><TableRow><TableCell>Nombre</TableCell><TableCell>Estado</TableCell></TableRow></TableHead>
                <TableBody>
                  {examenes.map((ex) => (
                    <TableRow key={ex.id} hover selected={sel?.id === ex.id} sx={{ cursor: 'pointer' }} onClick={() => { setSel(ex); setTab(0); }}>
                      <TableCell>{ex.nombre}</TableCell>
                      <TableCell><Chip size="small" label={ex.estado} color={ex.estado === 'activo' ? 'success' : 'default'} /></TableCell>
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
                    <TextField label="Enunciado" multiline minRows={2} value={preg.texto} onChange={(e) => setPreg({ ...preg, texto: e.target.value })} />
                    {preg.opciones.map((op, i) => (
                      <Stack key={i} direction="row" spacing={1} alignItems="center">
                        <TextField fullWidth size="small" label={`Opción ${i + 1}`} value={op.texto_opcion} onChange={(e) => setOpcion(i, 'texto_opcion', e.target.value)} />
                        <FormControlLabel control={<Checkbox checked={op.es_correcta} onChange={(e) => setOpcion(i, 'es_correcta', e.target.checked)} />} label="Correcta" />
                      </Stack>
                    ))}
                    <TextField label="Explicación (retroalimentación)" value={preg.explicacion} onChange={(e) => setPreg({ ...preg, explicacion: e.target.value })} />
                    <Stack direction="row" spacing={1.5}>
                      <Button variant="outlined" startIcon={<Add />} onClick={handleAgregarPregunta} disabled={sel.estado !== 'borrador'}>Agregar pregunta</Button>
                      <Button variant="contained" color="success" onClick={handlePublicar} disabled={sel.estado !== 'borrador'}>Publicar</Button>
                    </Stack>
                    {sel.estado !== 'borrador' && <Alert severity="info">El examen ya no está en borrador; no se pueden editar preguntas.</Alert>}
                  </Stack>
                )}

                {tab === 1 && (
                  <Stack spacing={1.5}>
                    <TextField label="Evaluados (ej: RM:5, GERENTE:9)" value={asig.evaluados} onChange={(e) => setAsig({ ...asig, evaluados: e.target.value })} helperText="Formato tipo:id separados por coma" />
                    <Stack direction="row" spacing={1.5}>
                      <TextField label="Fecha límite" type="date" InputLabelProps={{ shrink: true }} value={asig.fecha_limite} onChange={(e) => setAsig({ ...asig, fecha_limite: e.target.value })} />
                      <TextField label="Intentos máx" type="number" value={asig.intentos_max} onChange={(e) => setAsig({ ...asig, intentos_max: e.target.value })} />
                    </Stack>
                    <Button variant="contained" onClick={handleAsignar} disabled={sel.estado !== 'activo' || !asig.evaluados}>Asignar</Button>
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
                    <Typography fontWeight={600} gutterBottom>Ranking (último intento)</Typography>
                    <Table size="small">
                      <TableHead><TableRow><TableCell>Evaluado</TableCell><TableCell>Score</TableCell><TableCell>Estado</TableCell></TableRow></TableHead>
                      <TableBody>
                        {resultados?.ranking.map((r, i) => (
                          <TableRow key={i}>
                            <TableCell>{r.evaluado_tipo} #{r.evaluado_rm_id ?? r.evaluado_gerente_id}</TableCell>
                            <TableCell>{r.ultimo_score ?? '—'}{r.aprobado ? ' ✓' : ''}</TableCell>
                            <TableCell>{r.estado}</TableCell>
                          </TableRow>
                        ))}
                      </TableBody>
                    </Table>
                    <Divider sx={{ my: 2 }} />
                    <Typography fontWeight={600} gutterBottom>% Error por pregunta</Typography>
                    <Table size="small">
                      <TableHead><TableRow><TableCell>Pregunta</TableCell><TableCell>Respuestas</TableCell><TableCell>% Error</TableCell></TableRow></TableHead>
                      <TableBody>
                        {analisis.map((a) => (
                          <TableRow key={a.pregunta_id}>
                            <TableCell>{a.texto}</TableCell>
                            <TableCell>{a.total_respuestas}</TableCell>
                            <TableCell>{a.error_pct}%</TableCell>
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
