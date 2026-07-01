import { api } from './api';

export interface MedicoVisita {
  id: number;
  vm_id: number;
  nombre_completo: string;
  especialidad_id: number | null;
  especialidad_nombre: string | null;
  categoria: string;
  tipo_consultorio: string | null;
  direccion: string | null;
  telefono: string | null;
  ciclos_sin_visita: number;
  activo: boolean;
}

export interface MedicoCrear {
  vm_id: number;
  nombre_completo: string;
  especialidad_id?: number | null;
  categoria: string;
  tipo_consultorio?: string | null;
  direccion?: string | null;
  telefono?: string | null;
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
export const misVisitasHoy = () => api.get<VisitaHoy[]>('/visita/mis-visitas-hoy').then(r => r.data);
export const registrarVisita = (medico_id: number, tipo_visita: string, comentario: string, hace_minutos = 0) =>
  api.post('/visita/registrar', { medico_id, tipo_visita, comentario, hace_minutos }).then(r => r.data);
export const registrarNoVisita = (medico_id: number, causa: string, comentario?: string) =>
  api.post('/visita/no-visita', { medico_id, causa, comentario }).then(r => r.data);

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
