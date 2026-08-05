/**
 * formacion.service.ts — Plan de Cierre de Brechas (§12).
 * Rutas exactas del router backend `/formacion/brechas`
 * (ver backend/app/api/v1/routers/formacion_brechas.py).
 *
 * El motor NO genera nada por IA: cruza los 4 desgloses del KPI de Refuerzo y
 * devuelve alertas priorizadas (alta/media/informativa). La clave interna
 * `_capsula_id` no viaja por la API — el frontend solo ve el contrato público.
 */
import { api } from './api';

export type PrioridadBrecha = 'alta' | 'media' | 'informativa';

// Las 5 reglas del §12.2 (regla_aplicada).
export type ReglaBrecha =
  | 'contenido_generalizado'
  | 'concentrada_equipo_pais'
  | 'material_no_personas'
  | 'escalamiento_individual'
  | 'operativa_gestion';

/** Alerta tal como sale de POST /generar (aún sin persistir id). */
export interface AlertaBrecha {
  regla_aplicada: ReglaBrecha;
  prioridad: PrioridadBrecha;
  alcance: string;
  descripcion: string;
  accion_sugerida: string;
  link_accion: string | null;
}

/** Alerta persistida (GET / PATCH): agrega id, ciclo, atendida y timestamp. */
export interface AlertaBrechaPersistida extends AlertaBrecha {
  id: number;
  pais_codigo: string;
  ciclo_id: number | null;
  atendida: boolean;
  generado_en: string;
}

export interface GenerarResultado {
  total: number;
  alertas: AlertaBrecha[];
}

export const generarPlanBrechas = (params: {
  pais_codigo: string; campana_id?: number | null; ciclo_id?: number | null;
  persistir?: boolean;
}) =>
  api.post<GenerarResultado>('/formacion/brechas/generar', {
    persistir: true, ...params,
  }).then((r) => r.data);

export const listarBrechas = (params: {
  pais_codigo: string; ciclo_id?: number | null; incluir_atendidas?: boolean;
}) =>
  api.get<AlertaBrechaPersistida[]>('/formacion/brechas', {
    params: {
      pais_codigo: params.pais_codigo,
      ...(params.ciclo_id != null ? { ciclo_id: params.ciclo_id } : {}),
      ...(params.incluir_atendidas ? { incluir_atendidas: true } : {}),
    },
  }).then((r) => r.data);

export const atenderBrecha = (alertaId: number) =>
  api.patch<AlertaBrechaPersistida>(`/formacion/brechas/${alertaId}/atender`)
    .then((r) => r.data);

// ── Umbrales configurables (§12.3 — punto abierto 6) ──────────────────────
export interface UmbralesBrechas {
  pais_codigo: string;
  valores: Record<string, number>;
  claves_validas: string[];
}

export const obtenerUmbralesBrechas = (paisCodigo: string) =>
  api.get<UmbralesBrechas>('/formacion/brechas/umbrales', {
    params: { pais_codigo: paisCodigo },
  }).then((r) => r.data);

export const fijarUmbralBrecha = (params: {
  pais_codigo: string; clave: string; valor: number; descripcion?: string | null;
}) =>
  api.put('/formacion/brechas/umbrales', params).then((r) => r.data);

// ── Calendario de Coaching (§7) ───────────────────────────────────────────
export interface CeldaCalendario {
  id: number; gd_id: number; ciclo_id: number; rm_id: number;
  semana: number; dia_semana: string; cuadrante: string | null;
  editado_manualmente: boolean; publicado: boolean;
}
export interface SinEvaluar { rm_id: number; rm_nombre: string; }
export interface GenerarCalendarioResp {
  semanas: number;
  celdas: { rm_id: number; rm_nombre: string; semana: number; dia_semana: string; cuadrante: string }[];
  sin_evaluar: SinEvaluar[];
}
export interface FrecuenciasLSII {
  pais_codigo: string; valores: Record<string, number>; cuadrantes: string[];
}

export const generarCalendario = (p: { ciclo_id: number; gd_id?: number | null; persistir?: boolean }) =>
  api.post<GenerarCalendarioResp>('/formacion/calendario-coaching/generar', { persistir: true, ...p })
    .then((r) => r.data);

export const listarCalendario = (params: { ciclo_id: number; gd_id?: number | null }) =>
  api.get<CeldaCalendario[]>('/formacion/calendario-coaching', {
    params: { ciclo_id: params.ciclo_id, ...(params.gd_id != null ? { gd_id: params.gd_id } : {}) },
  }).then((r) => r.data);

export const moverCelda = (celdaId: number, semana: number, dia_semana: string) =>
  api.put<CeldaCalendario>(`/formacion/calendario-coaching/celda/${celdaId}`, { semana, dia_semana })
    .then((r) => r.data);

export const publicarCalendario = (p: { ciclo_id: number; gd_id?: number | null }) =>
  api.post<{ publicadas: number }>('/formacion/calendario-coaching/publicar', p).then((r) => r.data);

export const obtenerFrecuenciasLSII = (paisCodigo: string) =>
  api.get<FrecuenciasLSII>('/formacion/calendario-coaching/frecuencias', {
    params: { pais_codigo: paisCodigo },
  }).then((r) => r.data);

export const fijarFrecuenciaLSII = (p: {
  pais_codigo: string; cuadrante: string; visitas_por_ciclo: number; descripcion?: string | null;
}) => api.put('/formacion/calendario-coaching/frecuencias', p).then((r) => r.data);
