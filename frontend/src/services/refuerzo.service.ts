/**
 * refuerzo.service.ts — Refuerzo de Memoria y su KPI (§10 y §11).
 * Rutas exactas del router backend `/formacion/refuerzo`
 * (ver backend/app/api/v1/routers/formacion_refuerzo.py).
 *
 * LO QUE NUNCA LLEGA ANTES DE TIEMPO: `opcion_correcta` no viaja con el
 * enunciado en `misCapsulas`; solo la devuelve `responderCapsula` (§10.7).
 */
import { api } from './api';

export type ModoEspaciado = 'creciente' | 'fijo_48h';
export type FormatoCapsula = 'microlectura' | 'reto' | 'caso_breve' | 'reflexion_abierta';

export const MODOS_ESPACIADO: ModoEspaciado[] = ['creciente', 'fijo_48h'];
export const FORMATOS: FormatoCapsula[] = ['microlectura', 'reto', 'caso_breve', 'reflexion_abierta'];
export const DURACIONES = [15, 30, 60, 90];

export interface Campana {
  id: number; nombre: string; duracion_dias: number;
  modo_espaciado: ModoEspaciado; estado: string; aprobado_por_gm: boolean;
}

export interface Ronda {
  id: number; numero_ronda: number;
  fecha_hora_sugerida: string | null;
  fecha_hora_programada: string | null;
  publicada: boolean;
}

export interface CapsulaPendiente {
  capsula_id: number; formato: FormatoCapsula; enunciado: string;
  opciones: Record<string, string> | null;
  orden: number; ronda: number; campana: string; recibida_en: string | null;
}

export interface ResultadoRespuesta {
  capsula_id: number; tiempo_respuesta_seg: number; pct_participacion: number;
  puntos_obtenidos: number; es_acierto: boolean | null;
  opcion_seleccionada: string | null;
  opcion_correcta: string | null; explicacion: string | null; repetida: boolean;
}

export interface PreguntaExtremo {
  capsula_id: number; enunciado: string; pct_aciertos: number; respuestas: number;
}

export interface Metricas {
  respuestas: number; tiempo_promedio_seg: number;
  pct_participacion: number; pct_aciertos: number | null;
  pregunta_mas_acertada: PreguntaExtremo | null;
  pregunta_menos_acertada: PreguntaExtremo | null;
}

export interface ReporteKpi {
  total_respuestas: number;
  general: Metricas;
  por_representante: (Metricas & { rm_id: number | null })[];
  por_producto: (Metricas & { producto_id: number | null })[];
  por_pais: (Metricas & { pais_codigo: string | null })[];
  por_gd?: (Metricas & { gerente_id: number | null })[];
}

export interface CampanaEntrada {
  pais_codigo: string; nombre: string; duracion_dias: number;
  modo_espaciado: ModoEspaciado;
  producto_id?: number | null; ciclo_id?: number | null; material_fuente_id?: number | null;
}

export interface CapsulaEntrada {
  formato: FormatoCapsula; enunciado: string; orden: number;
  opciones?: Record<string, string> | null;
  opcion_correcta?: string | null; explicacion?: string | null;
}

// ── Campañas (Capacitación) ───────────────────────────────────────────────
export const crearCampana = (body: CampanaEntrada) =>
  api.post<{ id: number; nombre: string; estado: string; modo_espaciado: ModoEspaciado }>(
    '/formacion/refuerzo/campanas', body).then((r) => r.data);

export const listarCampanas = (paisCodigo: string) =>
  api.get<Campana[]>('/formacion/refuerzo/campanas', { params: { pais_codigo: paisCodigo } })
    .then((r) => r.data);

export const generarCalendario = (campanaId: number, inicio?: string) =>
  api.post<Ronda[]>(`/formacion/refuerzo/campanas/${campanaId}/calendario`, null,
    { params: inicio ? { inicio } : {} }).then((r) => r.data);

export const programarRonda = (rondaId: number, fechaHora?: string) =>
  api.put<{ id: number; fecha_hora_programada: string | null }>(
    `/formacion/refuerzo/rondas/${rondaId}/programar`, null,
    { params: fechaHora ? { fecha_hora: fechaHora } : {} }).then((r) => r.data);

export const agregarCapsula = (rondaId: number, body: CapsulaEntrada) =>
  api.post<{ id: number; formato: FormatoCapsula }>(
    `/formacion/refuerzo/rondas/${rondaId}/capsulas`, body).then((r) => r.data);

export const publicarRonda = (rondaId: number) =>
  api.post<{ id: number; publicada: boolean; notificada_en: string | null }>(
    `/formacion/refuerzo/rondas/${rondaId}/publicar`).then((r) => r.data);

// ── El representante responde ─────────────────────────────────────────────
export const misCapsulas = () =>
  api.get<CapsulaPendiente[]>('/formacion/refuerzo/mis-capsulas').then((r) => r.data);

export const responderCapsula = (capsulaId: number, body: { opcion?: string; texto_libre?: string }) =>
  api.post<ResultadoRespuesta>(`/formacion/refuerzo/capsulas/${capsulaId}/responder`, body)
    .then((r) => r.data);

export const misPuntos = (campanaId?: number) =>
  api.get<{ puntos: number }>('/formacion/refuerzo/mis-puntos',
    { params: campanaId != null ? { campana_id: campanaId } : {} }).then((r) => r.data);

// ── KPI (§11) — el backend recorta el alcance por rol ─────────────────────
export const reporteKpi = (params: { campana_id?: number; pais_codigo?: string } = {}) =>
  api.get<ReporteKpi>('/formacion/refuerzo/kpi', { params }).then((r) => r.data);
