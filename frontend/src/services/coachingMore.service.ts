import { api } from './api';

export interface CatalogoItem { id: number; seccion: string; orden_seccion: number; orden_item: number; texto: string; }
export interface VMItem { id: number; nombre: string; email: string | null; coaching_min_dia?: number; }
export interface AcompanadasHoy { rm_id: number; fecha: string; acompanadas: number; minimo: number; habilitado: boolean; }

export interface ItemCalif { item_catalogo_id: number | null; seccion: string; item_texto: string; calificacion: number; }
export interface HojaPayload {
  rm_id: number;
  medicos_vistos: number;
  items: ItemCalif[];
  fortalezas: string; areas_perfeccionar: string;
  plan_que_haras: string; plan_como_haras: string; plan_como_veras: string;
  plan_fecha_seguimiento: string;
  rm_acuerdo: 'de_acuerdo' | 'no_de_acuerdo' | '';
  rm_justificacion_desacuerdo?: string | null;
  rm_firma_imagen: string;
  motivo_correccion?: string | null;
}

export interface HojaResumen {
  id: number; fecha_coaching: string; rm_id: number; rm_nombre: string | null;
  gd_nombre: string | null; medicos_vistos: number; evaluacion_promedio: number;
  rm_acuerdo: string; ciclo_id: number | null; ciclo_nombre: string | null;
  corrige_a_id: number | null;
  es_correccion: boolean; tiene_correccion: boolean; created_at: string | null;
}
export interface SeccionDetalle { seccion: string; promedio: number | null; items: { texto: string; calificacion: number }[]; }
export interface HojaDetalle extends HojaResumen {
  fortalezas: string; areas_perfeccionar: string;
  plan_que_haras: string; plan_como_haras: string; plan_como_veras: string;
  plan_fecha_seguimiento: string; rm_justificacion_desacuerdo: string | null;
  rm_firma_imagen: string; motivo_correccion: string | null; secciones: SeccionDetalle[];
}
export interface CoachingKpi {
  ciclo_id: number | null; hojas_completadas: number; rms_con_coaching: number;
  total_rms: number; meta_hojas: number; pct_avance: number;
  por_gd: { gd_usuario_id: number; gd_nombre: string; hojas: number }[];
}

export const cmCatalogo = () => api.get<CatalogoItem[]>('/coaching-more/catalogo').then(r => r.data);
export const cmVms = (paisCodigo?: string) =>
  api.get<VMItem[]>('/coaching-more/vms', { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then(r => r.data);
export const cmAcompanadasHoy = (rmId: number) =>
  api.get<AcompanadasHoy>('/coaching-more/acompanadas-hoy', { params: { rm_id: rmId } }).then(r => r.data);
export const cmCrear = (p: HojaPayload) => api.post('/coaching-more', p).then(r => r.data);
// La corrección se retiró (jul-2026): una hoja guardada es inmutable. El endpoint responde 410.
export const cmListar = (params: { rm_id?: number; ciclo_id?: number } = {}) =>
  api.get<HojaResumen[]>('/coaching-more', { params }).then(r => r.data);
export const cmDetalle = (id: number) => api.get<HojaDetalle>(`/coaching-more/${id}`).then(r => r.data);
export const cmKpi = (cicloId?: number, paisCodigo?: string) =>
  api.get<CoachingKpi>('/coaching-more/kpi', { params: {
    ...(cicloId ? { ciclo_id: cicloId } : {}), ...(paisCodigo ? { pais_codigo: paisCodigo } : {}),
  } }).then(r => r.data);
export const cmConsolidar = (destino: 'coaching' | 'indicador', cicloId: number, paisCodigo: string) =>
  api.post('/coaching-more/consolidar', null, { params: { destino, ciclo_id: cicloId, pais_codigo: paisCodigo } }).then(r => r.data);
