import { api } from './api';

export interface MedicoVisita {
  id: number;
  vm_id: number;
  codigo: string | null;
  nombre_completo: string;
  nombre: string | null;
  apellidos: string | null;
  especialidad_id: number | null;
  especialidad_nombre: string | null;
  subespecialidad: string | null;
  linea_id?: number | null;
  linea_nombre?: string | null;
  categoria: string;
  centro_trabajo: string | null;
  institucion_tipo: string | null;
  tipo_consultorio: string | null;
  provincia: string | null;
  municipio: string | null;
  sector: string | null;
  direccion: string | null;
  latitud: number | null;
  longitud: number | null;
  telefono: string | null;
  email: string | null;
  exequatur: string | null;
  dias_consulta: string | null;
  horario_consulta: string | null;
  frecuencia_visita: string | null;
  acepta_visita: boolean | null;
  potencial_prescripcion: string | null;
  kol: boolean | null;
  segmento: string | null;
  observaciones: string | null;
  fecha_alta: string | null;
  fecha_ultima_visita: string | null;
  ciclos_sin_visita: number;
  activo: boolean;
  estado_visita?: 'vr' | 'v' | 'sin';   // Vista+Revisita / una visita / sin visitar
}

export interface MedicoCrear {
  vm_id: number;
  codigo?: string | null;
  nombre_completo: string;
  nombre?: string | null;
  apellidos?: string | null;
  especialidad_id?: number | null;
  subespecialidad?: string | null;
  categoria: string;
  centro_trabajo?: string | null;
  institucion_tipo?: string | null;
  tipo_consultorio?: string | null;
  provincia?: string | null;
  municipio?: string | null;
  sector?: string | null;
  direccion?: string | null;
  latitud?: number | null;
  longitud?: number | null;
  telefono?: string | null;
  email?: string | null;
  exequatur?: string | null;
  dias_consulta?: string | null;
  horario_consulta?: string | null;
  frecuencia_visita?: string | null;
  acepta_visita?: boolean;
  potencial_prescripcion?: string | null;
  kol?: boolean;
  segmento?: string | null;
  observaciones?: string | null;
  fecha_alta?: string | null;
  confirmar_duplicado?: boolean;
}

export interface PosibleDuplicado {
  id: number; nombre_completo: string; direccion: string | null; palabras_coinciden: number;
}

export interface Catalogo { id: number; nombre: string; }

export const listarMedicos = (vmId?: number) =>
  api.get<MedicoVisita[]>('/visita/medicos', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

export const listarEspecialidades = () =>
  api.get<Catalogo[]>('/visita/especialidades').then(r => r.data);

export const listarVMs = () =>
  api.get<Catalogo[]>('/visita/vms').then(r => r.data);

// ── Cobertura ─────────────────────────────────────────────────────────
export interface CatCobertura { total: number; visitados: number; completos: number; }
export interface CoberturaResumen {
  ciclo_id: number | null;
  panel: number; visitados: number; con_revisita: number; sin_visitar: number;
  pct_cobertura: number; pct_completa: number; pct_gap: number;
  objetivo_cobertura: number; objetivo_completa: number;
  categorias: Record<string, CatCobertura>;
  sin_visita: { id: number; nombre: string; categoria: string }[];
  falta_revisita: { id: number; nombre: string; categoria: string }[];
  ruptura: { id: number; nombre: string; categoria: string; ciclos_sin_visita: number }[];
}
export interface RankingVM {
  metrica: string; objetivo: number | null; no_cumplen: number; total: number;
  items: { vm_id: number; nombre: string; zona: string | null; valor: number; cumple: boolean }[];
}
export const coberturaResumen = (vmId?: number) =>
  api.get<CoberturaResumen>('/visita/cobertura/resumen', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const coberturaRanking = (metrica: string) =>
  api.get<RankingVM>('/visita/cobertura/ranking', { params: { metrica } }).then(r => r.data);

// ── Registro de visita ────────────────────────────────────────────────
export interface VisitaHoy {
  id: number; medico_id: number; medico: string; tipo_visita: string;
  ejecutada: boolean; causa_no_visita: string | null; comentario: string | null; hora: string | null;
}
export const listarCausas = () => api.get<string[]>('/visita/causas').then(r => r.data);
export const misVisitasHoy = (vmId?: number) =>
  api.get<VisitaHoy[]>('/visita/mis-visitas-hoy', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const registrarVisita = (medico_id: number, tipo_visita: string, comentario: string, hace_minutos = 0, vmId?: number) =>
  api.post('/visita/registrar', { medico_id, tipo_visita, comentario, hace_minutos }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const registrarNoVisita = (medico_id: number, causa: string, comentario?: string, vmId?: number) =>
  api.post('/visita/no-visita', { medico_id, causa, comentario }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Proyección ────────────────────────────────────────────────────────
export interface Proyeccion {
  ciclo_dias: number; dia_actual: number; dias_restantes: number;
  panel: number; visitados: number; objetivo_pct: number; obj_medicos: number;
  ritmo_actual: number; proyeccion_final: number; gap_al_objetivo: number;
  ritmo_requerido: number | null; cumple_proyeccion: boolean;
  categorias: Record<string, { panel: number; visitados: number; proyeccion: number }>;
}
export const proyeccionVisita = (diaActual?: number) =>
  api.get<Proyeccion>('/visita/proyeccion', { params: diaActual ? { dia_actual: diaActual } : {} }).then(r => r.data);
export const proyeccionRanking = (diaActual?: number) =>
  api.get<RankingVM>('/visita/proyeccion/ranking', { params: diaActual ? { dia_actual: diaActual } : {} }).then(r => r.data);

// ── Planeación del ciclo ──────────────────────────────────────────────
export interface PlaneacionItem {
  medico_id: number; tipo_visita: string; semana: number;
  dia_semana?: string | null; hora_estimada?: string | null;
}
export interface PlaneacionResumen {
  ciclo_id: number | null; panel: number; total_planeadas: number;
  medicos_planeados: number; cobertura_planeada_pct: number;
  cat_a_sin_revisita: number; carga_por_dia: number;
}
export const obtenerPlaneacion = (vmId?: number) =>
  api.get<PlaneacionItem[]>('/visita/planeacion', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const guardarPlaneacion = (items: PlaneacionItem[], vmId?: number) =>
  api.post<{ guardadas: number }>('/visita/planeacion', { items }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const planeacionResumen = (vmId?: number) =>
  api.get<PlaneacionResumen>('/visita/planeacion/resumen', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Ruptura de secuencia / Cierre de ciclo ────────────────────────────
export interface RupturaMedico {
  id: number; nombre: string; categoria: string;
  vm_id: number; vm_nombre: string; ciclos_sin_visita: number;
}
export interface RupturaEstado {
  total: number; alerta: number; grave: number; critica: number;
  medicos: { alerta: RupturaMedico[]; grave: RupturaMedico[]; critica: RupturaMedico[] };
}
export interface CierrePreview {
  ciclo_id: number; panel: number; visitados: number; sin_visitar: number;
  ruptura_nueva: number; ruptura_critica: number; ya_cerrado?: boolean; fecha_cierre?: string | null;
}
export interface CierreHist {
  id: number; ciclo_id: number; ciclo_nombre: string; fecha_cierre: string | null;
  panel: number; visitados: number; sin_visitar: number; ruptura_nueva: number; ruptura_critica: number;
}
export const estadoRuptura = (vmId?: number) =>
  api.get<RupturaEstado>('/visita/ruptura', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const previsualizarCierre = () =>
  api.get<CierrePreview>('/visita/cierre/previsualizar').then(r => r.data);
export const cerrarCiclo = () => api.post<CierrePreview>('/visita/cierre').then(r => r.data);
export const historialCierres = () => api.get<CierreHist[]>('/visita/cierre/historial').then(r => r.data);

// ── Parrilla promocional / Muestras ───────────────────────────────────
export interface ParrillaItem {
  id?: number; producto: string; mensaje_clave?: string | null;
  prioridad: number; meta_muestras: number;
}
export interface MuestraResumenProducto {
  producto: string; mensaje_clave: string | null; entregadas: number;
  medicos_alcanzados: number; meta: number; cobertura_meta_pct: number | null; en_parrilla: boolean;
}
export interface MuestrasResumen {
  ciclo_id: number; total_entregadas: number; productos_con_muestras: number;
  productos: MuestraResumenProducto[];
}
export const listarLineasVisita = () => api.get<Catalogo[]>('/visita/lineas').then(r => r.data);
export const obtenerParrilla = (lineaId?: number) =>
  api.get<ParrillaItem[]>('/visita/parrilla', { params: lineaId ? { linea_id: lineaId } : {} }).then(r => r.data);
export const guardarParrilla = (linea_id: number, items: ParrillaItem[]) =>
  api.post<{ guardados: number }>('/visita/parrilla', { linea_id, items }).then(r => r.data);
export const registrarMuestras = (medico_id: number, entregas: { producto: string; cantidad: number }[]) =>
  api.post<{ registradas: number }>('/visita/muestras', { medico_id, entregas }).then(r => r.data);
export const muestrasResumen = (vmId?: number) =>
  api.get<MuestrasResumen>('/visita/muestras/resumen', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Costo & ROI ───────────────────────────────────────────────────────
export interface ParametroCosto {
  ciclo_id: number; linea_id: number | null; costo_visita: number; costo_muestra: number;
  costo_fijo_ciclo: number; moneda: string; configurado: boolean;
}
export interface RoiResumen {
  ciclo_id: number; configurado: boolean; moneda: string;
  contactos: number; medicos_visitados: number; muestras: number;
  costo_visitas: number; costo_muestras: number; costo_fijo: number; costo_total: number;
  costo_por_contacto: number; costo_por_medico: number;
  ingresos: number; utilidad: number; roi_pct: number | null;
  ratio_ingreso_costo: number | null; rentable: boolean | null;
}
export interface RoiRankingItem {
  vm_id: number; nombre: string; zona: string | null;
  costo_total: number; ingresos: number; valor: number; cumple: boolean;
}
export interface RoiRanking { metrica: string; objetivo: number; no_cumplen: number; total: number; items: RoiRankingItem[]; }

export const obtenerParametrosCosto = (lineaId?: number) =>
  api.get<ParametroCosto>('/visita/costo/parametros', { params: lineaId ? { linea_id: lineaId } : {} }).then(r => r.data);
export const guardarParametrosCosto = (datos: {
  linea_id: number | null; costo_visita: number; costo_muestra: number; costo_fijo_ciclo: number; moneda: string;
}) => api.post<ParametroCosto>('/visita/costo/parametros', datos).then(r => r.data);
export const costoRoi = (vmId?: number) =>
  api.get<RoiResumen>('/visita/costo/roi', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const costoRanking = () => api.get<RoiRanking>('/visita/costo/ranking').then(r => r.data);

// Devuelve { medico } si se creó, o { duplicados } si el backend respondió 409.
export const crearMedico = async (
  datos: MedicoCrear,
): Promise<{ medico?: MedicoVisita; duplicados?: PosibleDuplicado[] }> => {
  try {
    const r = await api.post<MedicoVisita>('/visita/medicos', datos);
    return { medico: r.data };
  } catch (e: unknown) {
    const resp = (e as { response?: { status?: number; data?: { detail?: { duplicados?: PosibleDuplicado[] } } } })?.response;
    if (resp?.status === 409) return { duplicados: resp.data?.detail?.duplicados ?? [] };
    throw e;
  }
};
