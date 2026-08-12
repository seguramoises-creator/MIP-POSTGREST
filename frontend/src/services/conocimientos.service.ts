/**
 * conocimientos.service.ts — Fuente de EVAL_CONOCIMIENTOS y captura de notas.
 * Rutas exactas del router `/conocimientos` (ADMIN, GERENTE_PRODUCTIVIDAD, CAPACITACION).
 */
import { api } from './api';

export type FuenteConocimientos = 'EXAMEN_VISTA' | 'NOTA_EXTERNA' | 'CAPTURA_MANUAL';

export interface FuenteActual {
  pais_codigo: string;
  fuente: FuenteConocimientos;
  fuentes: FuenteConocimientos[];
}

export interface NotaCapturada {
  id: number; nota: string; tema: string | null;
  fecha_evaluacion: string; capturado_en: string;
}

export interface FilaNotas {
  rm_id: number; rm_codigo: string; rm_nombre: string;
  notas: NotaCapturada[]; promedio: string | null;
}

export interface ResultadoIntegracion {
  abortado: boolean; motivo?: string; rms_integrados: number;
}

export const verFuente = (paisCodigo: string) =>
  api.get<FuenteActual>('/conocimientos/fuente',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const cambiarFuente = (paisCodigo: string, fuente: FuenteConocimientos) =>
  api.put<{ pais_codigo: string; fuente: FuenteConocimientos }>(
    '/conocimientos/fuente', { pais_codigo: paisCodigo, fuente }).then((r) => r.data);

export const listarNotas = (paisCodigo: string, cicloId: number) =>
  api.get<FilaNotas[]>('/conocimientos/notas',
    { params: { pais_codigo: paisCodigo, ciclo_id: cicloId } }).then((r) => r.data);

export const capturarNota = (datos: {
  pais_codigo: string; ciclo_id: number; rm_id: number;
  nota: number; fecha_evaluacion: string; tema?: string | null;
}) => api.post<{ id: number }>('/conocimientos/notas', datos).then((r) => r.data);

export const corregirNota = (notaId: number, nota: number, tema: string | null) =>
  api.put<{ ok: boolean }>(`/conocimientos/notas/${notaId}`, { nota, tema })
    .then((r) => r.data);

export const integrarCaptura = (paisCodigo: string, cicloId: number) =>
  api.post<ResultadoIntegracion>('/conocimientos/integrar', null,
    { params: { pais_codigo: paisCodigo, ciclo_id: cicloId } }).then((r) => r.data);
