import { useEffect, useMemo, useState, useCallback, type ReactNode } from 'react';
import {
  Box, Typography, Card, CardContent, Button, TextField, Stack, Chip, Alert, Grid,
  Menu, MenuItem, Dialog, DialogTitle, DialogContent, DialogActions, CircularProgress,
  Avatar, InputAdornment, Divider, Switch, FormControlLabel, IconButton, Tooltip, Autocomplete, TablePagination,
} from '@mui/material';
import { Add, PersonAddAlt1, Warning, Search, FiberManualRecord, Edit, Block, Restore, HowToReg, ThumbUp, ThumbDown, Badge, SupervisorAccount, Layers } from '@mui/icons-material';
import { useAuthStore } from '../../store/auth.store';
import { CAT_AV } from './categoriaColores';
import {
  listarMedicos, obtenerMedico, listarMedicosExistentes, listarEspecialidades, listarVMs, crearMedico, actualizarMedico,
  solicitarBajaMedico, reactivarMedico, listarAprobaciones, aprobarMedico, rechazarMedico,
  listarProvincias, listarMunicipios, listarCentros, importarMedicosCategorizacion, miGerente,
  plantillaCategorizacion, obtenerClasificacion, actualizarClasificacion, resolverCambioMedico,
  type MedicoVisita, type MedicoExistente, type Catalogo, type PosibleDuplicado, type MedicoCrear, type AprobacionPendiente,
  type Provincia, type Municipio, type MiGerente, type CriterioPlantilla, type ClasificacionCrear,
} from '../../services/visita.service';
import { useCicloStore } from '../../store/ciclo.store';

// Tipos de consultorio válidos en RD (sin "Hospital privado", que no aplica).
const TIPOS = ['Clínica privada', 'Hospital público', 'Consultorio independiente'];
// Días hábiles para el selector múltiple de "Días de consulta".
const DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes'];
// Frecuencia de visita: F1 = una vez al mes, F2 = dos veces al mes (alinea con COB_MD_F1/F2).
const FRECUENCIAS = [
  { value: 'F1', label: 'F1 — una vez al mes' },
  { value: 'F2', label: 'F2 — dos veces al mes' },
];
/** Desglosa "ANA ALBERTA SOLANO MEDINA" → {nombre:"ANA ALBERTA", apellidos:"SOLANO MEDINA"}.
 *  Convención hispana: los DOS últimos términos son apellidos (paterno + materno) y el
 *  resto son nombres; con solo 2 palabras, uno de cada. Hace falta porque la carga masiva
 *  llenó únicamente `nombre_completo` (2704 de 2709 médicos no tienen el desglose). */
export function partirNombre(completo: string): { nombre: string; apellidos: string } {
  const p = (completo || '').trim().split(/\s+/).filter(Boolean);
  if (p.length < 2) return { nombre: p[0] ?? '', apellidos: '' };
  if (p.length === 2) return { nombre: p[0], apellidos: p[1] };
  return { nombre: p.slice(0, -2).join(' '), apellidos: p.slice(-2).join(' ') };
}

const parseDias = (s?: string | null): string[] =>
  (s ?? '').split(',').map((x) => x.trim()).filter(Boolean);
const POTENCIAL = ['Alto', 'Medio', 'Bajo'];
const INSTITUCION = ['Pública', 'Privada'];
// Plantilla de clasificación vacía: los 5 criterios son OBLIGATORIOS para dar de alta.
const clasificacionVacia = {
  pacientes_semana: '' as number | '', costo_consulta: '' as number | '',
  potencial_prescripcion: '', ubicacion_territorial: '', kol_nivel: '',
};
const vacio: MedicoCrear = {
  vm_id: 0, nombre_completo: '', especialidad_id: null,
  tipo_consultorio: '', direccion: '', telefono: '', acepta_visita: true, kol: false,
  clasificacion: { ...clasificacionVacia },
};

// Avatar de categoría (círculo) — A dorado, B azul, C gris (como el prototipo).
// Colores de categorización (A=Verde, B=Azul, C=Amarillo, D=Rojo): mapa compartido en ./categoriaColores.
// Paleta rotativa para las iniciales del médico.
const INICIAL_COLORS = ['#2E5BFF', '#7A5AF8', '#0F9B8E', '#E8833A', '#D6409F', '#2AA76A', '#C0392B', '#3B82C4'];

// Estado de aprobación → chip (solo si no está APROBADO).
const APROB: Record<string, { label: string; color: 'warning' | 'info' | 'default' }> = {
  PENDIENTE_ALTA: { label: 'Pendiente aprobación', color: 'warning' },
  PENDIENTE_BAJA: { label: 'Baja pendiente', color: 'warning' },
  RECHAZADO: { label: 'Rechazado', color: 'default' },
};

// Estado de visita del ciclo → etiqueta + color de punto.
const ESTADO: Record<string, { label: string; color: string }> = {
  vr:  { label: 'Vista + Revisita', color: '#2E7D32' },
  v:   { label: 'Vista realizada',  color: '#ED6C02' },
  sin: { label: 'Sin visitar',      color: '#D32F2F' },
};

function iniciales(nombre: string): string {
  const p = nombre.trim().split(/\s+/);
  return ((p[0]?.[0] ?? '') + (p[1]?.[0] ?? '')).toUpperCase();
}

// Extrae un mensaje legible del error del backend. El handler de validación de
// este app devuelve `detalle` (lista de errores Pydantic, texto limpio en
// `ctx.error`); otros endpoints devuelven `detail` (string). Cae a genérico.
function mensajeError(err: unknown): string {
  const data = (err as { response?: { data?: Record<string, unknown> } })?.response?.data ?? {};
  const detail = data.detail;
  if (typeof detail === 'string') return detail;
  const lista = (Array.isArray(data.detalle) ? data.detalle : Array.isArray(detail) ? detail : []) as Array<Record<string, any>>;
  if (lista.length) {
    const msgs = lista
      .map((d) => d?.ctx?.error ?? (d?.msg ?? '').replace(/^Value error,\s*/i, ''))
      .filter(Boolean);
    if (msgs.length) return msgs.join(' · ');
  }
  return 'No se pudo guardar (revisa nombre en MAYÚSCULAS, ≥2 palabras, categoría A/B/C/D).';
}

export default function PanelMedico() {
  const rol = useAuthStore((s) => s.rol);
  const esVM = rol === 'REPRESENTANTE_MEDICO';
  const esAprobador = rol === 'ADMIN' || rol === 'GERENTE_PRODUCTIVIDAD' || rol === 'GERENTE_DISTRITO';
  // Quién puede GESTIONAR el panel (agregar/editar/baja). Los roles de solo lectura (CONSULTA,
  // Analista, Dirección, etc.) ven el panel pero sin controles de escritura.
  const puedeGestionar = esVM || esAprobador;

  const [medicos, setMedicos] = useState<MedicoVisita[]>([]);
  const [especialidades, setEspecialidades] = useState<Catalogo[]>([]);
  const [vms, setVms] = useState<Catalogo[]>([]);
  // Catálogos geográficos (dropdowns del formulario de médico).
  const [provincias, setProvincias] = useState<Provincia[]>([]);
  const [municipios, setMunicipios] = useState<Municipio[]>([]);
  const [centros, setCentros] = useState<Catalogo[]>([]);
  const [vmFiltro, setVmFiltro] = useState<number | ''>('');
  const [busqueda, setBusqueda] = useState('');
  const [catFiltro, setCatFiltro] = useState('');
  const [espFiltro, setEspFiltro] = useState('');
  const [pagina, setPagina] = useState(0);          // paginación de la lista (rendimiento)
  const POR_PAGINA = 30;
  // Ficha del representante (Gerente de Distrito + Línea) — viene de la dim del RM.
  const [infoRep, setInfoRep] = useState<MiGerente | null>(null);
  const [estadoFiltro, setEstadoFiltro] = useState<'activos' | 'inactivos' | 'todos'>('activos');
  const [editId, setEditId] = useState<number | null>(null);
  const [pendientes, setPendientes] = useState<AprobacionPendiente[]>([]);
  const [cargando, setCargando] = useState(true);
  const [msg, setMsg] = useState<{ tipo: 'success' | 'error'; texto: string } | null>(null);

  const [form, setForm] = useState<MedicoCrear>(vacio);
  // Plantilla de clasificación: los vocabularios válidos los define el país (cada criterio
  // tiene opciones cerradas y NO intuitivas). Sin ella no se puede clasificar el médico.
  const paisCodigo = useCicloStore((s) => s.paisCodigo);
  const [plantilla, setPlantilla] = useState<CriterioPlantilla[]>([]);
  const [plantillaError, setPlantillaError] = useState('');
  useEffect(() => {
    if (!paisCodigo) return;
    plantillaCategorizacion(paisCodigo)
      .then((cs) => { setPlantilla(cs); setPlantillaError(''); })
      .catch((e) => {
        setPlantilla([]);
        setPlantillaError(e?.response?.data?.detail
          || 'No se pudieron cargar los criterios de clasificación de este país.');
      });
  }, [paisCodigo]);

  const setClas = (campo: string, valor: string | number) =>
    setForm((f) => ({ ...f, clasificacion: { ...f.clasificacion, [campo]: valor } }));
  // Acceso por nombre de campo: la plantilla es dinámica (la define el país), así que
  // los criterios se leen por clave en vez de por propiedad fija.
  const valClas = (campo: string): string | number =>
    (form.clasificacion as unknown as Record<string, string | number>)?.[campo] ?? '';
  // Los 5 criterios son obligatorios: sin ellos el backend rechaza el alta (422).
  const clasificacionCompleta = (['pacientes_semana', 'costo_consulta', 'potencial_prescripcion',
    'ubicacion_territorial', 'kol_nivel'] as const)
    .every((k) => form.clasificacion?.[k] !== '' && form.clasificacion?.[k] !== undefined
                  && form.clasificacion?.[k] !== null);
  // Se pide la clasificación al DAR DE ALTA (siempre) y también cuando el REPRESENTANTE
  // MODIFICA: ese cambio pasa por validación del GD y se recalcula la categoría. El
  // GD/ADMIN —que es quien valida— edita directo y no la necesita.
  const pideClasificacion = editId === null || esVM;

  // ── Cambios propuestos por el representante sobre médicos ya activos ──────────
  const [resolviendo, setResolviendo] = useState<number | null>(null);

  async function resolverCambio(p: AprobacionPendiente, aprobar: boolean) {
    if (!p.solicitud_id) return;
    setResolviendo(p.solicitud_id);
    try {
      const r = await resolverCambioMedico(p.solicitud_id, aprobar);
      setMsg({
        tipo: 'success',
        texto: aprobar
          ? `Cambio aprobado.${r.categoria ? ` Categoría recalculada: ${r.categoria}.` : ''}`
          : 'Cambio rechazado. El médico queda con la información anterior.',
      });
      cargar(); cargarPendientes();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err) });
    } finally { setResolviendo(null); }
  }

  // ── Revisión de la clasificación por el Gerente de Distrito (antes de aprobar) ──
  const [revisar, setRevisar] = useState<AprobacionPendiente | null>(null);
  const [revClas, setRevClas] = useState<ClasificacionCrear | null>(null);
  const [revCargando, setRevCargando] = useState(false);
  const [revError, setRevError] = useState('');

  async function abrirRevision(p: AprobacionPendiente) {
    setRevisar(p); setRevClas(null); setRevError(''); setRevCargando(true);
    try {
      setRevClas(await obtenerClasificacion(p.id));
    } catch (e: unknown) {
      // Altas anteriores al Bloque B no tienen plantilla: se puede aprobar igual.
      const st = (e as { response?: { status?: number } })?.response?.status;
      setRevError(st === 404
        ? 'Este médico se dio de alta antes de la plantilla de clasificación; puedes aprobarlo, pero quedará sin categoría.'
        : 'No se pudo cargar la clasificación.');
    } finally { setRevCargando(false); }
  }

  const setRev = (campo: string, valor: string | number) =>
    setRevClas((c) => (c ? { ...c, [campo]: valor } as ClasificacionCrear : c));
  const valRev = (campo: string): string | number =>
    (revClas as unknown as Record<string, string | number>)?.[campo] ?? '';
  const revCompleta = !!revClas && (['pacientes_semana', 'costo_consulta', 'potencial_prescripcion',
    'ubicacion_territorial', 'kol_nivel'] as const)
    .every((k) => revClas[k] !== '' && revClas[k] !== null && revClas[k] !== undefined);

  /** Guarda las correcciones del GD (si las hubo) y aprueba: ahí se revela la categoría. */
  async function aprobarDesdeRevision() {
    if (!revisar) return;
    setRevCargando(true);
    try {
      if (revClas && revCompleta) await actualizarClasificacion(revisar.id, revClas);
      await aprobarMedico(revisar.id);
      setMsg({ tipo: 'success', texto: 'Médico aprobado. El sistema calculó su categoría.' });
      setRevisar(null); cargar(); cargarPendientes();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err) });
    } finally { setRevCargando(false); }
  }
  const [errCampos, setErrCampos] = useState<Record<string, string>>({});  // validación por campo
  const [abierto, setAbierto] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [duplicados, setDuplicados] = useState<PosibleDuplicado[] | null>(null);
  // "Agregar médico existente": copiar la ficha de un médico ya registrado por otro VM.
  const [menuAnchor, setMenuAnchor] = useState<null | HTMLElement>(null);
  const [confirmImport, setConfirmImport] = useState(false);
  const [importando, setImportando] = useState(false);
  const [modoExistente, setModoExistente] = useState(false);
  const [existentes, setExistentes] = useState<MedicoExistente[]>([]);
  const [existenteSel, setExistenteSel] = useState<number | ''>('');

  const cargar = useCallback(() => {
    setCargando(true);
    listarMedicos(esVM ? undefined : (vmFiltro || undefined), estadoFiltro !== 'activos', true, paisCodigo)
      .then(setMedicos).catch(() => setMedicos([])).finally(() => setCargando(false));
  }, [esVM, vmFiltro, estadoFiltro, paisCodigo]);

  const cargarPendientes = useCallback(() => {
    if (esAprobador) listarAprobaciones().then(setPendientes).catch(() => setPendientes([]));
  }, [esAprobador]);

  useEffect(() => { cargar(); }, [cargar]);
  useEffect(() => {
    listarEspecialidades().then(setEspecialidades).catch(() => {});
    listarProvincias().then(setProvincias).catch(() => {});
    listarCentros().then(setCentros).catch(() => {});
    if (!esVM) listarVMs(paisCodigo).then(setVms).catch(() => {});
    cargarPendientes();
  }, [esVM, cargarPendientes, paisCodigo]);

  // Ficha del representante: el VM ve la suya; ADMIN/GERENTE la del VM seleccionado.
  useEffect(() => {
    if (esVM) miGerente().then(setInfoRep).catch(() => setInfoRep(null));
    else if (vmFiltro) miGerente(Number(vmFiltro)).then(setInfoRep).catch(() => setInfoRep(null));
    else setInfoRep(null);
  }, [esVM, vmFiltro]);

  // Municipios en cascada: al elegir provincia (o abrir en edición), cargar sus municipios.
  useEffect(() => {
    const p = provincias.find((x) => x.nombre === form.provincia);
    if (p) listarMunicipios(p.id).then(setMunicipios).catch(() => setMunicipios([]));
    else setMunicipios([]);
  }, [form.provincia, provincias]);

  // KPIs del panel (del ciclo actual) — solo sobre médicos activos.
  const kpis = useMemo(() => {
    const act = medicos.filter((m) => m.activo);
    const total = act.length;
    const visitados = act.filter((m) => m.estado_visita && m.estado_visita !== 'sin').length;
    const ruptura = act.filter((m) => m.ciclos_sin_visita >= 3).length;
    return { total, visitados, sin: total - visitados, ruptura };
  }, [medicos]);

  // Opciones de los selectores, derivadas de los médicos presentes.
  const opcEspecialidades = useMemo(
    () => Array.from(new Set(medicos.map((m) => m.especialidad_nombre).filter(Boolean) as string[])).sort(),
    [medicos]);

  const filtrados = useMemo(() => {
    const q = busqueda.trim().toUpperCase();
    return medicos.filter((m) =>
      (estadoFiltro === 'todos' || (estadoFiltro === 'activos' ? m.activo : !m.activo)) &&
      (!catFiltro || m.categoria === catFiltro) &&
      (!espFiltro || m.especialidad_nombre === espFiltro) &&
      (!q || m.nombre_completo.toUpperCase().includes(q)
          || (m.especialidad_nombre ?? '').toUpperCase().includes(q)
          || (m.linea_nombre ?? '').toUpperCase().includes(q)));
  }, [medicos, busqueda, catFiltro, espFiltro, estadoFiltro]);

  // Rendimiento: renderizar solo la página actual (2705 filas de golpe congela el navegador).
  useEffect(() => { setPagina(0); }, [busqueda, catFiltro, espFiltro, estadoFiltro, vmFiltro]);
  const filtradosPagina = useMemo(
    () => filtrados.slice(pagina * POR_PAGINA, (pagina + 1) * POR_PAGINA),
    [filtrados, pagina],
  );

  const abrirNuevo = () => {
    setMenuAnchor(null); setModoExistente(false); setExistenteSel('');
    setEditId(null); setForm({ ...vacio, vm_id: esVM ? 0 : (vmFiltro || 0) }); setDuplicados(null); setAbierto(true);
  };
  // "Médico existente": carga los médicos ya registrados por otros VM del país y abre el
  // formulario con un selector arriba para copiar la ficha del elegido.
  const abrirExistente = async () => {
    setMenuAnchor(null);
    const targetVm = esVM ? undefined : (vmFiltro || undefined);
    if (!esVM && !targetVm) {
      setMsg({ tipo: 'error', texto: 'Selecciona primero el visitador (VM) para copiar el médico a su panel.' });
      return;
    }
    try {
      const lista = await listarMedicosExistentes(targetVm);
      setExistentes(lista);
      setModoExistente(true); setExistenteSel(''); setEditId(null); setDuplicados(null);
      setForm({ ...vacio, vm_id: esVM ? 0 : (vmFiltro || 0) });
      setAbierto(true);
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudieron cargar los médicos existentes.' });
    }
  };
  // Precarga la ficha del médico existente elegido (editable antes de guardar la copia).
  const elegirExistente = (id: number) => {
    setExistenteSel(id);
    const m = existentes.find((x) => x.id === id);
    if (!m) return;
    setForm({
      // Copia TODA la ficha del médico (incluido el NOMBRE) EXCEPTO la ubicación específica:
      // centro de trabajo, dirección y GPS — que pueden ser distintos en el panel del nuevo VM y
      // los captura el representante. El resto queda precargado y editable.
      ...vacio,
      vm_id: esVM ? 0 : (vmFiltro || 0),
      nombre_completo: m.nombre_completo,
      // El origen casi nunca trae el desglose (la carga masiva solo llenó nombre_completo),
      // así que se deriva del nombre completo. Queda editable por si el corte no aplica.
      ...(m.nombre || m.apellidos
        ? { nombre: m.nombre, apellidos: m.apellidos }
        : partirNombre(m.nombre_completo)),
      especialidad_id: m.especialidad_id, subespecialidad: m.subespecialidad, categoria: m.categoria,
      institucion_tipo: m.institucion_tipo, tipo_consultorio: m.tipo_consultorio,
      provincia: m.provincia, municipio: m.municipio, sector: m.sector,
      telefono: m.telefono, email: m.email, exequatur: m.exequatur,
      dias_consulta: m.dias_consulta, horario_consulta: m.horario_consulta, frecuencia_visita: m.frecuencia_visita,
      acepta_visita: m.acepta_visita ?? true, potencial_prescripcion: m.potencial_prescripcion, kol: m.kol ?? false,
      segmento: m.segmento, observaciones: m.observaciones,
      // NO se copian: centro_trabajo, direccion, latitud, longitud (ubicación específica del médico).
    });
  };
  const abrirEditar = async (mLite: MedicoVisita) => {
    setModoExistente(false); setExistenteSel('');
    setEditId(mLite.id); setDuplicados(null); setErrCampos({});
    // La lista viene "lite" (sin la ficha pesada): traemos la ficha completa para editar.
    let m = mLite;
    try { m = await obtenerMedico(mLite.id); } catch { /* fallback: usa lo que trae la lista */ }
    // El REPRESENTANTE debe confirmar/ajustar la clasificación al modificar (el cambio se
    // revalida). Se precarga la vigente para que no la reescriba desde cero.
    let clasActual = { ...clasificacionVacia };
    if (esVM) {
      try {
        const c = await obtenerClasificacion(mLite.id);
        clasActual = {
          pacientes_semana: c.pacientes_semana ?? '', costo_consulta: c.costo_consulta ?? '',
          potencial_prescripcion: c.potencial_prescripcion ?? '',
          ubicacion_territorial: c.ubicacion_territorial ?? '', kol_nivel: c.kol_nivel ?? '',
        };
      } catch { /* médico anterior al Bloque B: se captura por primera vez */ }
    }
    setForm({
      clasificacion: clasActual,
      vm_id: m.vm_id, codigo: m.codigo, nombre_completo: m.nombre_completo, nombre: m.nombre,
      apellidos: m.apellidos, especialidad_id: m.especialidad_id, subespecialidad: m.subespecialidad,
      categoria: m.categoria, centro_trabajo: m.centro_trabajo, institucion_tipo: m.institucion_tipo,
      tipo_consultorio: m.tipo_consultorio, provincia: m.provincia, municipio: m.municipio, sector: m.sector,
      direccion: m.direccion, latitud: m.latitud, longitud: m.longitud, telefono: m.telefono, email: m.email,
      exequatur: m.exequatur, dias_consulta: m.dias_consulta, horario_consulta: m.horario_consulta,
      frecuencia_visita: m.frecuencia_visita, acepta_visita: m.acepta_visita ?? true,
      potencial_prescripcion: m.potencial_prescripcion, kol: m.kol ?? false, segmento: m.segmento,
      observaciones: m.observaciones, fecha_alta: m.fecha_alta,
    });
    setAbierto(true);
  };
  const toggleActivo = async (m: MedicoVisita) => {
    try {
      if (m.activo) {
        await solicitarBajaMedico(m.id);
        setMsg({ tipo: 'success', texto: 'Solicitud de baja enviada — requiere aprobación del Gerente de Distrito (efectiva el próximo ciclo).' });
      } else {
        await reactivarMedico(m.id);
        setMsg({ tipo: 'success', texto: 'Solicitud de alta enviada — requiere aprobación del Gerente de Distrito.' });
      }
      cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo procesar la solicitud.' });
    }
  };

  const resolver = async (id: number, accion: 'aprobar' | 'rechazar') => {
    try {
      if (accion === 'aprobar') { await aprobarMedico(id); setMsg({ tipo: 'success', texto: 'Solicitud aprobada.' }); }
      else { await rechazarMedico(id); setMsg({ tipo: 'success', texto: 'Solicitud rechazada.' }); }
      cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo procesar (¿es de tu distrito?).' });
    }
  };
  const set = (k: keyof MedicoCrear, v: unknown) => {
    setForm((f) => ({ ...f, [k]: v }));
    setErrCampos((e) => (e[k] ? { ...e, [k]: '' } : e));  // limpia el error del campo al editarlo
  };

  // Carga masiva: crea en el Panel los médicos ya cargados en Categorización.
  const importarCat = async () => {
    setConfirmImport(false); setImportando(true); setMsg(null);
    try {
      const r = await importarMedicosCategorizacion();
      setMsg({ tipo: 'success', texto: `Importados desde Categorización: ${r.creados} creados · ${r.omitidos} ya existían · ${r.invalidos} con nombre inválido (de ${r.total_origen}). Quedan pendientes de aprobación del Gerente de Distrito.` });
      cargar(); cargarPendientes();
    } catch {
      setMsg({ tipo: 'error', texto: 'No se pudo importar desde Categorización. Verifica que haya datos cargados en Categorización.' });
    } finally { setImportando(false); }
  };

  // Días de consulta (multi-selección): se guarda como CSV ordenado L→V.
  const toggleDia = (d: string) => {
    const cur = parseDias(form.dias_consulta);
    const next = cur.includes(d) ? cur.filter((x) => x !== d) : [...cur, d];
    set('dias_consulta', DIAS_SEMANA.filter((x) => next.includes(x)).join(', '));
  };
  // Horario: "Todo el día" o "HH:MM-HH:MM" (desde/hasta).
  const horarioRaw = form.horario_consulta ?? '';
  const todoDia = horarioRaw.trim().toLowerCase() === 'todo el día';
  const [hDesde, hHasta] = (!todoDia && horarioRaw.includes('-'))
    ? horarioRaw.split('-').map((s) => s.trim()) : ['', ''];
  const setHorario = (desde: string, hasta: string) =>
    set('horario_consulta', desde || hasta ? `${desde}-${hasta}` : '');

  // Requerimiento Mallén (Item 4b): validación por campo. Campo vacío → borde rojo;
  // formato inválido → borde rojo + mensaje. Devuelve el mapa de errores (vacío = OK).
  function validarForm(): Record<string, string> {
    const e: Record<string, string> = {};
    const nom = (form.nombre_completo || '').trim();
    if (!nom) e.nombre_completo = 'Campo obligatorio.';
    else if (nom !== nom.toUpperCase()) e.nombre_completo = 'Debe ir en MAYÚSCULAS.';
    else if (nom.split(/\s+/).length < 2) e.nombre_completo = 'Ingresa al menos nombre y apellido.';
    if (!esVM && !form.vm_id) e.vm_id = 'Selecciona el visitador (VM).';
    const email = (form.email || '').trim();
    if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) e.email = 'Correo con formato inválido.';
    const tel = (form.telefono || '').trim();
    if (tel && !/^[0-9()+\-\s]{7,}$/.test(tel)) e.telefono = 'Teléfono con formato inválido.';
    return e;
  }

  async function guardar(confirmar = false) {
    const errs = validarForm();
    setErrCampos(errs);
    if (Object.keys(errs).length) { setMsg({ tipo: 'error', texto: 'Revisa los campos marcados en rojo.' }); return; }
    setGuardando(true); setDuplicados(null);
    try {
      if (editId !== null) {
        const { confirmar_duplicado: _c, vm_id: _v, clasificacion, ...cambios } = form;
        // El REPRESENTANTE envía la clasificación: su cambio queda PENDIENTE de validación
        // y el médico sigue activo con los datos anteriores. El GD/ADMIN edita directo.
        await actualizarMedico(editId, esVM ? { ...cambios, clasificacion } : cambios);
        setMsg({
          tipo: 'success',
          texto: esVM
            ? 'Cambio enviado. Tu Gerente de Distrito debe validarlo; mientras tanto el '
              + 'médico sigue activo con la información anterior.'
            : 'Médico actualizado.',
        });
      } else {
        // Al copiar un médico existente, la duplicidad es intencional → se confirma directo.
        const res = await crearMedico({ ...form, confirmar_duplicado: confirmar || modoExistente });
        if (res.duplicados && res.duplicados.length) { setDuplicados(res.duplicados); return; }
        setMsg({ tipo: 'success', texto: 'Médico registrado — pendiente de aprobación del Gerente de Distrito (contará desde el próximo ciclo).' });
      }
      setAbierto(false); cargar(); cargarPendientes();
    } catch (err: unknown) {
      setMsg({ tipo: 'error', texto: mensajeError(err) });
    } finally { setGuardando(false); }
  }

  const cap = (s: string) => s.charAt(0).toUpperCase() + s.slice(1).toLowerCase();
  // Un dato de la ficha del representante: icono + etiqueta + valor.
  const infoDato = (icono: ReactNode, label: string, valor: string) => (
    <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
      <Avatar sx={{ bgcolor: 'primary.main', color: '#fff', width: 32, height: 32 }}>{icono}</Avatar>
      <Box sx={{ minWidth: 0 }}>
        <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.1, fontWeight: 600, letterSpacing: 0.3 }}>{label}</Typography>
        <Typography variant="body2" fontWeight={700} noWrap>{valor}</Typography>
      </Box>
    </Stack>
  );

  const kpiCard = (label: string, valor: number, sub: string, color: string, alerta = false) => (
    <Card variant="outlined" sx={{ borderColor: alerta ? 'error.main' : 'divider', borderWidth: alerta ? 1.5 : 1 }}>
      <CardContent sx={{ py: 1.75 }}>
        <Stack direction="row" alignItems="center" spacing={0.75}>
          {alerta && <FiberManualRecord sx={{ fontSize: 12, color: 'error.main' }} />}
          <Typography variant="caption" color="text.secondary" sx={{ letterSpacing: 0.4, fontWeight: 600 }}>
            {label}
          </Typography>
        </Stack>
        <Typography variant="h4" fontWeight={700} sx={{ color, lineHeight: 1.2 }}>{valor}</Typography>
        <Typography variant="caption" color="text.secondary">{sub}</Typography>
      </CardContent>
    </Card>
  );

  return (
    <Box sx={{ p: { xs: 1.5, sm: 3 } }}>
      {/* Cabecera: título + ficha del representante (selector VM + Gerente de Distrito + Línea) */}
      <Box sx={{ mb: 2 }}>
        <Box sx={{ mb: 1.5 }}>
          <Typography variant="h5" fontWeight={700}>Panel Médico</Typography>
          <Typography variant="body2" color="text.secondary">
            {filtrados.length === medicos.length
              ? `${medicos.length} médicos registrados · Ciclo actual`
              : `${filtrados.length} de ${medicos.length} médicos · filtro activo`}
          </Typography>
        </Box>

        {/* El representante (VM) se ELIGE aquí; su Gerente de Distrito y Línea se
            muestran automáticamente (de la dim del RM). Un VM ve su ficha fija. */}
        {(!esVM || (infoRep && (infoRep.vm || infoRep.gerente || infoRep.linea))) && (
          <Card variant="outlined" sx={{ borderColor: 'primary.light', bgcolor: 'rgba(46,91,255,0.05)' }}>
            <CardContent sx={{ py: 1.25, '&:last-child': { pb: 1.25 } }}>
              <Stack direction={{ xs: 'column', sm: 'row' }} spacing={{ xs: 1.25, sm: 4 }} alignItems={{ sm: 'center' }}
                     flexWrap="wrap"
                     divider={<Divider orientation="vertical" flexItem sx={{ display: { xs: 'none', sm: 'block' } }} />}>
                <Stack direction="row" spacing={1} alignItems="center" sx={{ minWidth: 0 }}>
                  <Avatar sx={{ bgcolor: 'primary.main', color: '#fff', width: 32, height: 32 }}><Badge fontSize="small" /></Avatar>
                  {esVM ? (
                    <Box sx={{ minWidth: 0 }}>
                      <Typography variant="caption" color="text.secondary" sx={{ display: 'block', lineHeight: 1.1, fontWeight: 600, letterSpacing: 0.3 }}>Representante médico</Typography>
                      <Typography variant="body2" fontWeight={700} noWrap>{infoRep?.vm ?? '—'}</Typography>
                    </Box>
                  ) : (
                    <TextField select variant="standard" label="Representante médico (VM)" value={vmFiltro} sx={{ minWidth: 240 }}
                               onChange={(e) => setVmFiltro(e.target.value === '' ? '' : Number(e.target.value))}>
                      <MenuItem value="">Todos los visitadores</MenuItem>
                      {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
                    </TextField>
                  )}
                </Stack>
                {infoRep?.gerente && infoDato(<SupervisorAccount fontSize="small" />,
                  infoRep.gerente_tipo ? `Gerente de ${cap(infoRep.gerente_tipo)}` : 'Gerente de Distrito', infoRep.gerente)}
                {infoRep?.linea && infoDato(<Layers fontSize="small" />, 'Línea', infoRep.linea)}
              </Stack>
            </CardContent>
          </Card>
        )}
      </Box>

      {/* Filtros sobre el panel */}
      <Stack direction="row" spacing={1.5} flexWrap="wrap" alignItems="center" sx={{ mb: 2 }}>
        <TextField size="small" placeholder="Buscar médico…" value={busqueda} sx={{ minWidth: 220 }}
                   onChange={(e) => setBusqueda(e.target.value)}
                   InputProps={{ startAdornment: <InputAdornment position="start"><Search fontSize="small" /></InputAdornment> }} />
        <TextField select size="small" label="Especialidad" value={espFiltro} sx={{ minWidth: 180 }}
                   onChange={(e) => setEspFiltro(e.target.value)}>
          <MenuItem value="">Todas las especialidades</MenuItem>
          {opcEspecialidades.map((e) => <MenuItem key={e} value={e}>{e}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Categoría" value={catFiltro} sx={{ minWidth: 140 }}
                   onChange={(e) => setCatFiltro(e.target.value)}>
          <MenuItem value="">Todas</MenuItem>
          {['A', 'B', 'C', 'D'].map((c) => <MenuItem key={c} value={c}>Categoría {c}</MenuItem>)}
        </TextField>
        <TextField select size="small" label="Estado" value={estadoFiltro} sx={{ minWidth: 130 }}
                   onChange={(e) => setEstadoFiltro(e.target.value as 'activos' | 'inactivos' | 'todos')}>
          <MenuItem value="activos">Activos</MenuItem>
          <MenuItem value="inactivos">Inactivos</MenuItem>
          <MenuItem value="todos">Todos</MenuItem>
        </TextField>
        <Box sx={{ flexGrow: 1 }} />
        {esAprobador && !esVM && (
          <Button variant="outlined" startIcon={<HowToReg />} disabled={importando}
                  onClick={() => setConfirmImport(true)}>
            {importando ? 'Importando…' : 'Importar desde Categorización'}
          </Button>
        )}
        {puedeGestionar && (
        <Button variant="contained" startIcon={<PersonAddAlt1 />}
                onClick={(e) => setMenuAnchor(e.currentTarget)}>Agregar Médico</Button>
        )}
        <Menu anchorEl={menuAnchor} open={Boolean(menuAnchor)} onClose={() => setMenuAnchor(null)}>
          <MenuItem onClick={abrirNuevo}>
            <PersonAddAlt1 fontSize="small" style={{ marginRight: 8 }} /> Médico nuevo
          </MenuItem>
          <MenuItem onClick={abrirExistente}>
            <HowToReg fontSize="small" style={{ marginRight: 8 }} /> Médico existente (copiar al panel)
          </MenuItem>
        </Menu>
      </Stack>

      {msg && <Alert severity={msg.tipo} sx={{ mb: 2 }} onClose={() => setMsg(null)}>{msg.texto}</Alert>}

      {/* KPIs */}
      <Grid container spacing={2} sx={{ mb: 2 }}>
        <Grid item xs={6} md={3}>{kpiCard('TOTAL PANEL', kpis.total, 'médicos registrados', 'text.primary')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('VISITADOS', kpis.visitados, 'en el ciclo actual', 'success.main')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('SIN VISITAR', kpis.sin, 'requieren atención', 'error.main')}</Grid>
        <Grid item xs={6} md={3}>{kpiCard('RUPTURA SECUENCIA', kpis.ruptura, '3+ ciclos sin visitar', 'error.main', true)}</Grid>
      </Grid>

      {/* Solicitudes pendientes de aprobación (Gerente de Distrito) */}
      {esAprobador && pendientes.length > 0 && (
        <Card variant="outlined" sx={{ mb: 2, borderColor: 'warning.main' }}>
          <CardContent sx={{ py: 1.5 }}>
            <Stack direction="row" alignItems="center" spacing={1} sx={{ mb: 1 }}>
              <HowToReg color="warning" />
              <Typography variant="subtitle1" fontWeight={700}>Solicitudes pendientes de aprobación</Typography>
              <Chip size="small" color="warning" label={pendientes.length} />
            </Stack>
            <Stack divider={<Divider />} spacing={0}>
              {pendientes.map((p) => (
                <Stack key={p.id} direction="row" alignItems="center" spacing={1.5} sx={{ py: 1 }}>
                  <Chip size="small" color={p.tipo_solicitud === 'ALTA' ? 'success' : 'error'} label={p.tipo_solicitud} />
                  <Box sx={{ flex: 1, minWidth: 0 }}>
                    <Typography variant="body2" fontWeight={700} noWrap>
                      {p.nombre_completo}{p.categoria ? ` · Cat. ${p.categoria}` : ' · sin clasificar'}
                    </Typography>
                    <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                      {[p.especialidad_nombre, p.linea_nombre, `VM: ${p.vm_nombre}`].filter(Boolean).join(' · ')}
                    </Typography>
                    {/* Diferencias propuestas: el GD valida de un vistazo qué se movió,
                        en vez de tener que comparar la ficha completa. */}
                    {p.tipo_solicitud === 'CAMBIO' && (
                      <Typography variant="caption" sx={{ display: 'block', color: 'warning.dark' }}>
                        {Object.keys(p.cambios ?? {}).length
                          ? Object.entries(p.cambios ?? {})
                              .map(([k, v]) => `${k}: ${v ?? '—'}`).join(' · ')
                          : 'Solo cambia la clasificación'}
                      </Typography>
                    )}
                  </Box>
                  {/* CAMBIO: el representante propuso modificar un médico ya activo. Se
                      muestran las DIFERENCIAS para poder validar de un vistazo. */}
                  {p.tipo_solicitud === 'CAMBIO' ? (
                    <>
                      <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />}
                              disabled={resolviendo === p.solicitud_id}
                              onClick={() => resolverCambio(p, true)}>Aprobar cambio</Button>
                      <Button size="small" variant="outlined" color="error" startIcon={<ThumbDown />}
                              disabled={resolviendo === p.solicitud_id}
                              onClick={() => resolverCambio(p, false)}>Rechazar</Button>
                    </>
                  ) : p.tipo_solicitud === 'ALTA' ? (
                    <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />}
                            onClick={() => abrirRevision(p)}>Revisar y aprobar</Button>
                  ) : (
                    <Button size="small" variant="contained" color="success" startIcon={<ThumbUp />}
                            onClick={() => resolver(p.id, 'aprobar')}>Aprobar</Button>
                  )}
                  {/* El CAMBIO ya trae su propio Rechazar (resuelve la solicitud, no el médico). */}
                  {p.tipo_solicitud !== 'CAMBIO' && (
                    <Button size="small" variant="outlined" color="error" startIcon={<ThumbDown />}
                            onClick={() => resolver(p.id, 'rechazar')}>Rechazar</Button>
                  )}
                </Stack>
              ))}
            </Stack>
          </CardContent>
        </Card>
      )}

      {/* Lista de médicos (tarjetas) */}
      <Card variant="outlined">
        {cargando ? (
          <Box sx={{ p: 4, textAlign: 'center' }}><CircularProgress /></Box>
        ) : filtrados.length === 0 ? (
          <Alert severity="info" sx={{ m: 2 }}>
            {medicos.length === 0 ? 'No hay médicos en el panel. Agrega el primero con "Agregar Médico".' : 'Sin médicos que coincidan con el filtro.'}
          </Alert>
        ) : (
          <Box>
            {filtradosPagina.map((m, i) => {
              const ruptura = m.ciclos_sin_visita >= 3;
              const est = ESTADO[m.estado_visita ?? 'sin'];
              const av = CAT_AV[m.categoria] ?? CAT_AV.C;
              const color = INICIAL_COLORS[m.id % INICIAL_COLORS.length];
              return (
                <Box key={m.id}>
                  {i > 0 && <Divider />}
                  <Stack direction="row" alignItems="center" spacing={1.5}
                         sx={{ px: 2, py: 1.5, bgcolor: ruptura ? 'rgba(211,47,47,0.06)' : 'transparent', opacity: m.activo ? 1 : 0.55 }}>
                    <Avatar sx={{ bgcolor: 'transparent', color, fontWeight: 700, fontSize: 14, width: 40, height: 40, border: `2px solid ${color}22` }}>
                      {iniciales(m.nombre_completo)}
                    </Avatar>
                    <Avatar sx={{ bgcolor: av.bg, color: av.fg, fontWeight: 700, fontSize: 13, width: 26, height: 26 }}>
                      {m.categoria}
                    </Avatar>
                    <Box sx={{ flex: 1, minWidth: 0 }}>
                      <Stack direction="row" spacing={1} alignItems="center" flexWrap="wrap">
                        <Typography variant="body2" fontWeight={700} noWrap>{m.nombre_completo}</Typography>
                        {ruptura && (
                          <Chip size="small" color="error" icon={<FiberManualRecord sx={{ fontSize: '10px !important' }} />}
                                label={`${m.ciclos_sin_visita} ciclos sin visitar — Ruptura de secuencia`}
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                        {!m.activo && <Chip size="small" variant="outlined" label="Inactivo" sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />}
                        {m.estado_aprobacion && m.estado_aprobacion !== 'APROBADO' && APROB[m.estado_aprobacion] && (
                          <Chip size="small" variant="outlined" color={APROB[m.estado_aprobacion].color}
                                label={APROB[m.estado_aprobacion].label}
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                        {m.estado_aprobacion === 'APROBADO' && m.ciclo_baja_id && (
                          <Chip size="small" variant="outlined" color="info" label="Baja próx. ciclo"
                                sx={{ height: 20, '& .MuiChip-label': { px: 0.75, fontSize: 11 } }} />
                        )}
                      </Stack>
                      <Typography variant="caption" color="text.secondary" noWrap sx={{ display: 'block' }}>
                        {[m.especialidad_nombre, m.provincia, m.municipio, m.tipo_consultorio].filter(Boolean).join(' · ') || 'Sin datos de contacto'}
                      </Typography>
                    </Box>
                    <Stack direction="row" alignItems="center" spacing={0.75} sx={{ flexShrink: 0 }}>
                      <FiberManualRecord sx={{ fontSize: 11, color: est.color }} />
                      <Typography variant="caption" sx={{ color: est.color, fontWeight: 600, whiteSpace: 'nowrap' }}>
                        {est.label}
                      </Typography>
                      <Typography variant="caption" color="text.disabled" sx={{ ml: 1 }}>#{m.id}</Typography>
                      {puedeGestionar && (
                        <>
                          <Tooltip title="Editar médico">
                            <IconButton size="small" color="primary" onClick={() => abrirEditar(m)}><Edit fontSize="small" /></IconButton>
                          </Tooltip>
                          <Tooltip title={m.activo ? 'Solicitar baja (requiere aprobación)' : 'Solicitar alta (requiere aprobación)'}>
                            <IconButton size="small" color={m.activo ? 'error' : 'success'} onClick={() => toggleActivo(m)}>
                              {m.activo ? <Block fontSize="small" /> : <Restore fontSize="small" />}
                            </IconButton>
                          </Tooltip>
                        </>
                      )}
                    </Stack>
                  </Stack>
                </Box>
              );
            })}
            {filtrados.length > POR_PAGINA && (
              <TablePagination
                component="div"
                count={filtrados.length}
                page={pagina}
                onPageChange={(_e, p) => setPagina(p)}
                rowsPerPage={POR_PAGINA}
                rowsPerPageOptions={[POR_PAGINA]}
                labelDisplayedRows={({ from, to, count }) => `${from}–${to} de ${count}`}
              />
            )}
          </Box>
        )}
      </Card>

      {/* Alta de médico */}
      <Dialog open={abierto} onClose={() => !guardando && setAbierto(false)} maxWidth="md" fullWidth>
        <DialogTitle>
          {editId !== null
            ? <><Edit sx={{ verticalAlign: 'middle', mr: 1 }} />Editar médico</>
            : modoExistente
              ? <><HowToReg sx={{ verticalAlign: 'middle', mr: 1 }} />Copiar médico existente al panel</>
              : <><Add sx={{ verticalAlign: 'middle', mr: 1 }} />Agregar médico</>}
        </DialogTitle>
        <DialogContent dividers>
          {modoExistente && (
            <Box sx={{ mb: 1.5 }}>
              {/* Requerimiento Mallén (Item 4c): búsqueda de médico como autocompletado (se escribe y filtra). */}
              <Autocomplete
                fullWidth size="small"
                options={existentes}
                value={existentes.find((x) => x.id === existenteSel) ?? null}
                onChange={(_e, m) => { if (m) elegirExistente(m.id); else setExistenteSel(''); }}
                getOptionLabel={(m) => `${m.nombre_completo} · Cat ${m.categoria}${m.especialidad_nombre ? ` · ${m.especialidad_nombre}` : ''}${m.vm_nombre ? ` — ${m.vm_nombre}` : ''}`}
                isOptionEqualToValue={(a, b) => a.id === b.id}
                noOptionsText="Sin coincidencias."
                renderInput={(params) => (
                  <TextField {...params} label="Copiar de médico existente (escribe para buscar)"
                             helperText={existentes.length
                               ? 'Escribe el nombre; se precargan sus datos (puedes ajustarlos antes de guardar).'
                               : 'No hay médicos de otros visitadores para copiar.'} />
                )}
              />
            </Box>
          )}
          {(() => {
            const seccion = (t: string) => (
              <Grid item xs={12}><Typography variant="overline" color="primary" fontWeight={700}>{t}</Typography></Grid>
            );
            return (
              <Grid container spacing={1.75} sx={{ mt: 0 }}>
                {seccion('Identificación')}
                {!esVM && (
                  <Grid item xs={12} sm={6}>
                    <TextField select fullWidth size="small" label="Visitador (VM) — Representante asignado" value={form.vm_id || ''} required
                               onChange={(e) => set('vm_id', Number(e.target.value))}>
                      {vms.map((v) => <MenuItem key={v.id} value={v.id}>{v.nombre}</MenuItem>)}
                    </TextField>
                  </Grid>
                )}
                <Grid item xs={12} sm={esVM ? 6 : 6}>
                  <TextField fullWidth size="small" label="Código del médico" value={form.codigo ?? ''}
                             onChange={(e) => set('codigo', e.target.value)} />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth size="small" label="Nombre completo (MAYÚSCULAS, ≥2 palabras)" value={form.nombre_completo} required
                             error={!!errCampos.nombre_completo}
                             onChange={(e) => {
                               // Desglosa Nombre/Apellidos sobre la marcha para no teclearlos
                               // dos veces. Ambos quedan editables si el corte no aplica.
                               const v = e.target.value.toUpperCase();
                               const { nombre, apellidos } = partirNombre(v);
                               setForm((f) => ({ ...f, nombre_completo: v, nombre, apellidos }));
                             }}
                             helperText={errCampos.nombre_completo || 'Ej: MANUEL ANTONIO PEREZ GARCIA — sin abreviaciones con punto'} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Nombre" value={form.nombre ?? ''} onChange={(e) => set('nombre', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={6}>
                  <TextField fullWidth size="small" label="Apellidos" value={form.apellidos ?? ''} onChange={(e) => set('apellidos', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Especialidad" value={form.especialidad_id ?? ''}
                             onChange={(e) => set('especialidad_id', e.target.value === '' ? null : Number(e.target.value))}
                             helperText={especialidades.length === 0 ? 'Catálogo vacío' : ' '}>
                    <MenuItem value="">—</MenuItem>
                    {especialidades.map((e) => <MenuItem key={e.id} value={e.id}>{e.nombre}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Subespecialidad" value={form.subespecialidad ?? ''} onChange={(e) => set('subespecialidad', e.target.value)} />
                </Grid>
                {/* Clasificación: el representante captura los 5 criterios; la categoría
                    A/B/C/D la calcula el sistema cuando el Gerente de Distrito aprueba.
                    Solo al DAR DE ALTA — al editar, la ajusta el GD en su pantalla. */}
                {pideClasificacion && seccion('Clasificación del médico (obligatoria)')}
                {pideClasificacion && (
                <Grid item xs={12}>
                  <Alert severity={plantillaError ? 'error' : 'info'} sx={{ mb: 1 }}>
                    {plantillaError || (editId !== null ? (
                      <>
                        <b>Confirma o ajusta estos 5 criterios.</b> Al guardar, el cambio queda
                        <b> pendiente de validación</b> de tu Gerente de Distrito; mientras tanto
                        el médico sigue activo con la información anterior.
                      </>
                    ) : (
                      <>
                        <b>Completa tú estos 5 criterios</b> para registrar el médico. Tu Gerente
                        de Distrito solo revisa el alta y puede ajustarlos al aprobarla.
                        La categoría (A/B/C/D) la calcula el sistema; nadie la elige.
                      </>
                    ))}
                  </Alert>
                </Grid>
                )}
                {pideClasificacion && plantilla.map((c) => (
                  <Grid item xs={12} sm={4} key={c.codigo}>
                    {c.tipo === 'TEXTO' ? (
                      <TextField select fullWidth size="small" required label={c.etiqueta}
                                 value={valClas(c.campo)}
                                 error={!valClas(c.campo)}
                                 onChange={(e) => setClas(c.campo, e.target.value)}>
                        {c.opciones.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
                      </TextField>
                    ) : (
                      <TextField fullWidth size="small" required type="number" label={c.etiqueta}
                                 value={valClas(c.campo)}
                                 error={valClas(c.campo) === ''}
                                 helperText={c.minimo != null ? `Entre ${c.minimo} y ${c.maximo}` : ' '}
                                 inputProps={{ min: c.minimo ?? 0, max: c.maximo ?? undefined }}
                                 onChange={(e) => setClas(c.campo, e.target.value === '' ? '' : Number(e.target.value))} />
                    )}
                  </Grid>
                ))}

                {seccion('Ubicación / Zonificación')}
                <Grid item xs={12} sm={6}>
                  <Autocomplete
                    freeSolo size="small" options={centros.map((c) => c.nombre)}
                    value={form.centro_trabajo ?? ''}
                    onChange={(_, val) => set('centro_trabajo', val ?? '')}
                    onInputChange={(_, val) => set('centro_trabajo', val)}
                    renderInput={(params) => <TextField {...params} label="Centro de trabajo principal" />}
                  />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField select fullWidth size="small" label="Institución" value={form.institucion_tipo ?? ''} onChange={(e) => set('institucion_tipo', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {INSTITUCION.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField select fullWidth size="small" label="Tipo de consultorio" value={form.tipo_consultorio ?? ''} onChange={(e) => set('tipo_consultorio', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {TIPOS.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Autocomplete
                    freeSolo size="small"
                    options={Array.from(new Set([...provincias.map((p) => p.nombre), form.provincia].filter(Boolean) as string[]))}
                    value={form.provincia ?? null}
                    onChange={(_, val) => setForm((f) => ({ ...f, provincia: val ?? '', municipio: '' }))}
                    onInputChange={(_, val, reason) => { if (reason === 'input') setForm((f) => ({ ...f, provincia: val })); }}
                    renderInput={(params) => <TextField {...params} label="Provincia" />}
                  />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <Autocomplete
                    freeSolo size="small"
                    options={Array.from(new Set([...municipios.map((m) => m.nombre), form.municipio].filter(Boolean) as string[]))}
                    value={form.municipio ?? null}
                    disabled={!form.provincia}
                    onChange={(_, val) => set('municipio', val ?? '')}
                    onInputChange={(_, val, reason) => { if (reason === 'input') set('municipio', val); }}
                    renderInput={(params) => <TextField {...params} label="Ciudad / Municipio"
                      helperText={!form.provincia ? 'Elige una provincia primero' : undefined} />}
                  />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Sector" value={form.sector ?? ''} onChange={(e) => set('sector', e.target.value)} />
                </Grid>
                <Grid item xs={12}>
                  <TextField fullWidth size="small" label="Dirección" value={form.direccion ?? ''} onChange={(e) => set('direccion', e.target.value)} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField fullWidth size="small" type="number" label="Latitud (GPS)" value={form.latitud ?? ''} onChange={(e) => set('latitud', e.target.value === '' ? null : Number(e.target.value))} />
                </Grid>
                <Grid item xs={6} sm={3}>
                  <TextField fullWidth size="small" type="number" label="Longitud (GPS)" value={form.longitud ?? ''} onChange={(e) => set('longitud', e.target.value === '' ? null : Number(e.target.value))} />
                </Grid>

                {seccion('Contacto')}
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Teléfono" value={form.telefono ?? ''}
                             error={!!errCampos.telefono} helperText={errCampos.telefono || ''}
                             onChange={(e) => set('telefono', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Correo electrónico" value={form.email ?? ''}
                             error={!!errCampos.email} helperText={errCampos.email || ''}
                             onChange={(e) => set('email', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Exequátur / colegiación" value={form.exequatur ?? ''} onChange={(e) => set('exequatur', e.target.value)} />
                </Grid>

                {seccion('Consulta y visita')}
                <Grid item xs={12} sm={6}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    Días de consulta
                  </Typography>
                  <Stack direction="row" flexWrap="wrap" gap={0.5}>
                    {DIAS_SEMANA.map((d) => {
                      const sel = parseDias(form.dias_consulta).includes(d);
                      return (
                        <Chip key={d} label={d.slice(0, 3)} size="small" clickable
                              color={sel ? 'primary' : 'default'} variant={sel ? 'filled' : 'outlined'}
                              onClick={() => toggleDia(d)} />
                      );
                    })}
                  </Stack>
                </Grid>
                <Grid item xs={12} sm={6}>
                  <Typography variant="caption" color="text.secondary" sx={{ display: 'block', mb: 0.5 }}>
                    Horario de consulta
                  </Typography>
                  <Stack direction="row" spacing={1} alignItems="center">
                    <TextField size="small" type="time" label="Desde" value={hDesde} disabled={todoDia}
                               InputLabelProps={{ shrink: true }}
                               onChange={(e) => setHorario(e.target.value, hHasta)} sx={{ width: 130 }} />
                    <TextField size="small" type="time" label="Hasta" value={hHasta} disabled={todoDia}
                               InputLabelProps={{ shrink: true }}
                               onChange={(e) => setHorario(hDesde, e.target.value)} sx={{ width: 130 }} />
                    <FormControlLabel
                      control={<Switch size="small" checked={todoDia}
                        onChange={(e) => set('horario_consulta', e.target.checked ? 'Todo el día' : '')} />}
                      label="Todo el día" />
                  </Stack>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Frecuencia de visita" value={form.frecuencia_visita ?? ''} onChange={(e) => set('frecuencia_visita', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {FRECUENCIAS.map((f) => <MenuItem key={f.value} value={f.value}>{f.label}</MenuItem>)}
                    {/* Preserva un valor heredado (ej. "Mensual") que ya no está en el catálogo. */}
                    {form.frecuencia_visita && !FRECUENCIAS.some((f) => f.value === form.frecuencia_visita) && (
                      <MenuItem value={form.frecuencia_visita}>{form.frecuencia_visita} (actual)</MenuItem>
                    )}
                  </TextField>
                </Grid>

                {seccion('Comercial')}
                <Grid item xs={12} sm={4}>
                  <TextField select fullWidth size="small" label="Potencial de prescripción" value={form.potencial_prescripcion ?? ''} onChange={(e) => set('potencial_prescripcion', e.target.value)}>
                    <MenuItem value="">—</MenuItem>
                    {POTENCIAL.map((t) => <MenuItem key={t} value={t}>{t}</MenuItem>)}
                  </TextField>
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" label="Segmento" value={form.segmento ?? ''} onChange={(e) => set('segmento', e.target.value)} />
                </Grid>
                <Grid item xs={12} sm={4}>
                  <TextField fullWidth size="small" type="date" label="Fecha de alta" InputLabelProps={{ shrink: true }}
                             value={form.fecha_alta ?? ''} onChange={(e) => set('fecha_alta', e.target.value || null)} />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <FormControlLabel control={<Switch checked={!!form.kol} onChange={(e) => set('kol', e.target.checked)} />} label="Influenciador (KOL)" />
                </Grid>
                <Grid item xs={6} sm={4}>
                  <FormControlLabel control={<Switch checked={form.acepta_visita !== false} onChange={(e) => set('acepta_visita', e.target.checked)} />} label="Acepta visita" />
                </Grid>

                {seccion('Estado y observaciones')}
                <Grid item xs={12}>
                  <TextField fullWidth size="small" multiline minRows={2} label="Observaciones" value={form.observaciones ?? ''} onChange={(e) => set('observaciones', e.target.value)} />
                </Grid>

                {duplicados && (
                  <Grid item xs={12}>
                    <Alert severity="warning" icon={<Warning />}>
                      <Typography variant="subtitle2" fontWeight={700}>Posible duplicidad — verificar</Typography>
                      <Typography variant="caption">Ya existe(n) médico(s) con nombre similar:</Typography>
                      {duplicados.map((d) => (
                        <Typography key={d.id} variant="body2">• {d.nombre_completo}{d.direccion ? ` — ${d.direccion}` : ''}</Typography>
                      ))}
                    </Alert>
                  </Grid>
                )}
              </Grid>
            );
          })()}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setAbierto(false)} disabled={guardando}>Cancelar</Button>
          {duplicados ? (
            <Button color="warning" variant="contained" disabled={guardando} onClick={() => guardar(true)}>
              Registrar de todos modos
            </Button>
          ) : (
            <>
              {/* Decir QUÉ falta: un botón gris sin explicación se lee como "no graba". */}
              {pideClasificacion && !clasificacionCompleta && (
                <Typography variant="caption" color="error" sx={{ mr: 1 }}>
                  Faltan criterios de clasificación
                </Typography>
              )}
              <Button variant="contained" onClick={() => guardar(false)}
                      disabled={guardando || !form.nombre_completo
                                || (pideClasificacion && !clasificacionCompleta)}>
                {guardando ? 'Guardando…' : 'Guardar'}
              </Button>
            </>
          )}
        </DialogActions>
      </Dialog>

      {/* Revisión de la clasificación por el Gerente de Distrito antes de aprobar.
          El GD puede corregir lo que capturó el representante; la categoría A/B/C/D se
          calcula al aprobar (nunca se muestra ni se elige aquí). */}
      <Dialog open={!!revisar} onClose={() => setRevisar(null)} maxWidth="sm" fullWidth>
        <DialogTitle>
          Revisar clasificación
          <Typography variant="body2" color="text.secondary">{revisar?.nombre_completo}</Typography>
        </DialogTitle>
        <DialogContent dividers>
          {revError && <Alert severity="warning" sx={{ mb: 2 }}>{revError}</Alert>}
          {revCargando && !revClas && <Box sx={{ textAlign: 'center', py: 3 }}><CircularProgress size={24} /></Box>}
          {revClas && (
            <>
              <Alert severity="info" sx={{ mb: 2 }}>
                Verifica los datos que capturó el representante. Puedes corregirlos antes de
                aprobar. <b>La categoría (A/B/C/D) la calcula el sistema al aprobar.</b>
              </Alert>
              <Grid container spacing={2}>
                {plantilla.map((c) => (
                  <Grid item xs={12} sm={6} key={c.codigo}>
                    {c.tipo === 'TEXTO' ? (
                      <TextField select fullWidth size="small" label={c.etiqueta}
                                 value={valRev(c.campo)} error={!valRev(c.campo)}
                                 onChange={(e) => setRev(c.campo, e.target.value)}>
                        {c.opciones.map((o) => <MenuItem key={o} value={o}>{o}</MenuItem>)}
                      </TextField>
                    ) : (
                      <TextField fullWidth size="small" type="number" label={c.etiqueta}
                                 value={valRev(c.campo)} error={valRev(c.campo) === ''}
                                 helperText={c.minimo != null ? `Entre ${c.minimo} y ${c.maximo}` : ' '}
                                 inputProps={{ min: c.minimo ?? 0, max: c.maximo ?? undefined }}
                                 onChange={(e) => setRev(c.campo, e.target.value === '' ? '' : Number(e.target.value))} />
                    )}
                  </Grid>
                ))}
              </Grid>
            </>
          )}
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setRevisar(null)} disabled={revCargando}>Cancelar</Button>
          <Button color="error" disabled={revCargando}
                  onClick={() => { const id = revisar!.id; setRevisar(null); resolver(id, 'rechazar'); }}>
            Rechazar
          </Button>
          <Button variant="contained" color="success" onClick={aprobarDesdeRevision}
                  disabled={revCargando || (!!revClas && !revCompleta)}>
            {revCargando ? 'Procesando…' : 'Aprobar'}
          </Button>
        </DialogActions>
      </Dialog>

      {/* Confirmación de importación masiva desde Categorización */}
      <Dialog open={confirmImport} onClose={() => setConfirmImport(false)} maxWidth="xs" fullWidth>
        <DialogTitle>Importar médicos desde Categorización</DialogTitle>
        <DialogContent>
          <Typography variant="body2" color="text.secondary">
            Se crearán en el Panel los médicos ya cargados en Categorización, cada uno asignado a su
            visitador y con su especialidad, provincia, municipio, centro y categoría. Los médicos
            que ya existan se omiten. Quedarán <b>pendientes de aprobación</b> del Gerente de Distrito.
          </Typography>
        </DialogContent>
        <DialogActions>
          <Button onClick={() => setConfirmImport(false)}>Cancelar</Button>
          <Button variant="contained" onClick={importarCat} disabled={importando}>
            {importando ? 'Importando…' : 'Importar'}
          </Button>
        </DialogActions>
      </Dialog>
    </Box>
  );
}
