/**
 * rankingFormacion.service.ts — Ranking de Formación (§8).
 * Rutas exactas del router backend `/formacion/ranking`.
 *
 * Es un ranking PROPIO del módulo: no alimenta el Score Integral ni los premios.
 */
import { api } from './api';

export interface FilaRankingFormacion {
  posicion: number; rm_id: number; rm_nombre: string;
  puntos_certificacion: number; puntos_examenes: number;
  puntos_refuerzo: number; puntos_onboarding: number;
  puntos_total: number; racha_ciclos: number;
}

export interface PesosRanking {
  ranking_puntos_certificacion: number;
  ranking_puntos_examen: number;
  ranking_puntos_paso_onboarding: number;
  ranking_bono_ruta_completa: number;
}

export const listarRankingFormacion = (cicloId: number) =>
  api.get<FilaRankingFormacion[]>('/formacion/ranking', { params: { ciclo_id: cicloId } })
    .then((r) => r.data);

export const misPuntosFormacion = (cicloId: number) =>
  api.get<FilaRankingFormacion | null>('/formacion/ranking/mis-puntos',
    { params: { ciclo_id: cicloId } }).then((r) => r.data);

export const recalcularRankingFormacion = (cicloId: number, paisCodigo: string) =>
  api.post<{ ciclo_id: number; rms_procesados: number; puntos_totales: number }>(
    '/formacion/ranking/recalcular', null,
    { params: { ciclo_id: cicloId, pais_codigo: paisCodigo } }).then((r) => r.data);

export const pesosRankingFormacion = (paisCodigo: string) =>
  api.get<PesosRanking>('/formacion/ranking/pesos', { params: { pais_codigo: paisCodigo } })
    .then((r) => r.data);

export const fijarPesoRankingFormacion = (body: {
  pais_codigo: string; clave: string; valor: number; descripcion?: string | null;
}) => api.put<{ clave: string; valor: number }>('/formacion/ranking/pesos', body)
  .then((r) => r.data);
