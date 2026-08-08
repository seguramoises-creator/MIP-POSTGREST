/**
 * integracion.service.ts — Integración con Laboratorio Mallén.
 * Rutas exactas del router backend `/integracion` (solo ADMIN y GERENTE_PRODUCTIVIDAD).
 *
 * Este sub-proyecto solo valida lo que Mallén dejó en el esquema `ext`; no
 * integra nada a los esquemas internos de VISTA.
 */
import { api } from './api';

export type EstadoLote = 'RECIBIDO' | 'VALIDADO' | 'INTEGRADO' | 'RECHAZADO';
export type SeveridadHallazgo = 'error' | 'aviso';

export interface LoteIntegracion {
  lote_id: number; sistema_origen: string; modulo: string;
  pais_codigo: string; ciclo_codigo: string | null; periodo: string | null;
  fecha_extraccion: string; fecha_recepcion: string;
  filas_enviadas: number; estado: EstadoLote; mensaje: string | null;
  hallazgos: number;
}

export interface HallazgoIntegracion {
  id: number; tabla: string; origen_id: string | null; campo: string | null;
  problema: string; severidad: SeveridadHallazgo; detectado_en: string;
}

export interface DetalleLote {
  lote: Omit<LoteIntegracion, 'hallazgos'>;
  hallazgos: HallazgoIntegracion[];
}

export interface ResultadoValidacion {
  lote_id: number; estado: EstadoLote;
  filas_declaradas: number; filas_reales: number;
  errores: number; avisos: number; mensaje: string;
}

export type ResumenLotes = Record<EstadoLote, number>;

export const listarLotes = (params: {
  pais_codigo?: string; estado?: EstadoLote; limite?: number;
} = {}) => api.get<LoteIntegracion[]>('/integracion/lotes', { params })
  .then((r) => r.data);

export const detalleLote = (loteId: number) =>
  api.get<DetalleLote>(`/integracion/lotes/${loteId}`).then((r) => r.data);

export const validarLote = (loteId: number) =>
  api.post<ResultadoValidacion>(`/integracion/lotes/${loteId}/validar`)
    .then((r) => r.data);

export const resumenLotes = (paisCodigo?: string) =>
  api.get<ResumenLotes>('/integracion/resumen',
    { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then((r) => r.data);

// ── Dimensiones (sub-proyecto 2) ─────────────────────────────────────────
export interface ConteoDimension {
  entidad: string; en_ext: number; creados: number;
  adoptados: number; actualizados: number; omitidos: number;
}

export interface HallazgoDimension {
  entidad: string; codigo_externo: string; problema: string;
  severidad: SeveridadHallazgo;
}

export interface ResultadoSincronizacion {
  pais_codigo: string;
  dimensiones: ConteoDimension[];
  hallazgos: HallazgoDimension[];
}

export interface FilaResumenDimension {
  entidad: string; en_ext: number; mapeadas: number;
}

export const sincronizarDimensiones = (paisCodigo: string) =>
  api.post<ResultadoSincronizacion>('/integracion/dimensiones/sincronizar', null,
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const resumenDimensiones = (paisCodigo: string) =>
  api.get<FilaResumenDimension[]>('/integracion/dimensiones/resumen',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);
