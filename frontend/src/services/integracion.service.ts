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

// ── Visitas (sub-proyecto 3) ─────────────────────────────────────────────
export interface ConteoHecho {
  hecho: string; en_ext: number; integrados: number;
  actualizados: number; omitidos: number;
}

export interface HallazgoVisita {
  hecho: string; origen_id: string | null; problema: string;
  severidad: SeveridadHallazgo;
}

export interface RecalculoIntegracion {
  abortado: boolean;
  motivo?: string;
  filas_kpi_actualizadas?: number;
  rankings_generados?: number;
}

export interface ResultadoIntegracionVisitas {
  pais_codigo: string; ciclo_codigo: string;
  hechos: ConteoHecho[];
  // `omitido_ciclo_cerrado` viene siempre de `calcular_indicadores` (True/False,
  // nunca ausente) — ver `integracion_indicadores_service.calcular_indicadores`.
  indicadores: { rms: number; filas: number; omitido_ciclo_cerrado: boolean };
  recalculo: RecalculoIntegracion;
  lotes_cerrados: number[];
  hallazgos: HallazgoVisita[];
}

export interface FilaResumenVisita {
  hecho: string; en_ext: number; integradas: number;
}

export const integrarVisitas = (paisCodigo: string, cicloCodigo: string) =>
  api.post<ResultadoIntegracionVisitas>('/integracion/visitas/integrar', null,
    { params: { pais_codigo: paisCodigo, ciclo_codigo: cicloCodigo } })
    .then((r) => r.data);

export const resumenVisitas = (paisCodigo: string, cicloCodigo: string) =>
  api.get<FilaResumenVisita[]>('/integracion/visitas/resumen',
    { params: { pais_codigo: paisCodigo, ciclo_codigo: cicloCodigo } })
    .then((r) => r.data);

// ── Prescripción IR (sub-proyecto 6) ─────────────────────────────────────
export interface ConteoIR {
  entidad: string; en_ext: number; enlazados: number; ya_enlazados: number;
  no_enlazados: number; casi_enlazados: number; omitidos: number;
}

export interface ResultadoSincronizacionIR {
  pais_codigo: string;
  entidades: ConteoIR[];
  hallazgos: HallazgoDimension[];
}

export interface EjemploPrescriptor {
  codigo: string; exequatur: string; nombre: string;
}

export interface EjemploRmNoEnlazado {
  origen_id: string | null; rm_codigo: string;
}

// Refleja el dict REAL de `integracion_ir_service.diagnosticar_ir` (Tareas 1-2),
// no el borrador original del brief: `recetas` trae dos sub-conteos que se
// añadieron en la ronda de revisión de la Tarea 2 (`sin_ciclo`,
// `rm_no_enlazado` + sus ejemplos). Son causas de `huerfanas`, no un balde
// nuevo — los cuatro baldes (`directas+por_cadena+ambiguas+huerfanas`) siguen
// sumando `total` por sí solos.
export interface DiagnosticoIR {
  pais_codigo: string;
  prescriptores: {
    en_ext: number; enlazados: number; con_panel: number;
    casi_enlazados: number; huerfanos: number;
    ejemplos_casi_enlazados: EjemploPrescriptor[];
    ejemplos_huerfanos: EjemploPrescriptor[];
  };
  productos: {
    en_ext: number; propios: number; enlazados: number;
    propios_sin_equivalencia: number;
    ejemplos_propios_sin_equivalencia: { codigo: string; nombre: string }[];
  };
  periodos: { en_ext: number; con_ciclo: number; sin_ciclo: number };
  recetas: {
    total: number; directas: number; por_cadena: number;
    ambiguas: number; huerfanas: number;
    // Sub-causas de `huerfanas` — no participan de la suma de los 4 baldes.
    sin_ciclo: number;
    rm_no_enlazado: number;
    ejemplos_rm_no_enlazado: EjemploRmNoEnlazado[];
  };
}

export const sincronizarIR = (paisCodigo: string) =>
  api.post<ResultadoSincronizacionIR>('/integracion/ir/sincronizar', null,
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const diagnosticoIR = (paisCodigo: string) =>
  api.get<DiagnosticoIR>('/integracion/ir/diagnostico',
    { params: { pais_codigo: paisCodigo } }).then((r) => r.data);
