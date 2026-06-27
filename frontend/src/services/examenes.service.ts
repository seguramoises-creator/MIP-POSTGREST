import { api } from './api';

// ── Tipos ─────────────────────────────────────────────────────────────
export interface Examen {
  id: number;
  nombre: string;
  producto: string | null;
  nota_minima: number;
  tiempo_limite_min: number | null;
  estado: string;
  fuente: string;
  rand_preguntas: boolean;
  rand_opciones: boolean;
  indicador_codigo: string | null;
  ciclo_id: number | null;
  fecha_creacion: string;
  fecha_publicacion: string | null;
}

export interface OpcionCrear { texto_opcion: string; es_correcta: boolean; }
export interface PreguntaCrear {
  tipo: string; escenario?: string | null; texto: string;
  explicacion?: string | null; opciones: OpcionCrear[];
}
export interface ExamenCrear {
  nombre: string; producto?: string | null; nota_minima?: number;
  tiempo_limite_min?: number | null; rand_preguntas?: boolean; rand_opciones?: boolean;
  indicador_codigo?: string | null; ciclo_id?: number | null;
}

export interface EvaluadoRef { tipo: 'RM' | 'GERENTE'; id: number; }
export interface AsignacionCrear {
  examen_id: number; evaluados: EvaluadoRef[];
  fecha_limite?: string | null; intentos_max?: number | null; notif_activa?: boolean;
}
export interface Asignacion {
  id: number; examen_id: number; evaluado_tipo: string;
  evaluado_rm_id: number | null; evaluado_gerente_id: number | null;
  fecha_limite: string | null; intentos_max: number | null;
  intentos_usados: number; estado: string;
}

export interface OpcionPresentada { indice_presentado: number; texto_opcion: string; }
export interface PreguntaPresentada {
  pregunta_id: number; tipo: string; escenario: string | null;
  texto: string; opciones: OpcionPresentada[];
}
export interface IntentoIniciado {
  intento_id: number; examen_nombre: string;
  tiempo_limite_min: number | null; preguntas: PreguntaPresentada[];
}
export interface ReporteRespuesta {
  pregunta_texto: string; explicacion: string | null;
  indice_elegido_presentado: number | null; texto_elegido: string | null;
  texto_correcto: string; es_correcta: boolean;
}
export interface ReporteIntento {
  intento_id: number; examen_nombre: string; producto: string | null;
  score: number; aprobado: boolean; nota_minima: number;
  correctas: number; total: number; fecha_fin: string | null;
  respuestas: ReporteRespuesta[];
}

export interface RankingFila {
  evaluado_tipo: string; evaluado_rm_id: number | null; evaluado_gerente_id: number | null;
  ultimo_score: number | null; aprobado: boolean; intentos_usados: number; estado: string;
}
export interface ResultadosExamen {
  examen_id: number; nombre: string; producto: string | null; estado: string;
  nota_minima: number; asignados: number; completados: number;
  completitud_pct: number; promedio_score: number; aprobacion_pct: number;
  ranking: RankingFila[];
}
export interface AnalisisPregunta {
  pregunta_id: number; texto: string; orden: number;
  total_respuestas: number; incorrectas: number; error_pct: number;
}

// ── Capacitación ──────────────────────────────────────────────────────
export const listarExamenes = () => api.get<Examen[]>('/examenes').then(r => r.data);
export const crearExamen = (d: ExamenCrear) => api.post<Examen>('/examenes', d).then(r => r.data);
export const agregarPregunta = (examenId: number, d: PreguntaCrear) =>
  api.post(`/examenes/${examenId}/preguntas`, d).then(r => r.data);
export const publicarExamen = (examenId: number) =>
  api.post<Examen>(`/examenes/${examenId}/publicar`).then(r => r.data);
export const asignarExamen = (examenId: number, d: AsignacionCrear) =>
  api.post<Asignacion[]>(`/examenes/${examenId}/asignar`, d).then(r => r.data);
export const resumenCapacitacion = () =>
  api.get<any[]>('/examenes/resumen').then(r => r.data);
export const resultadosExamen = (examenId: number) =>
  api.get<ResultadosExamen>(`/examenes/${examenId}/resultados`).then(r => r.data);
export const analisisPreguntas = (examenId: number) =>
  api.get<AnalisisPregunta[]>(`/examenes/${examenId}/analisis-preguntas`).then(r => r.data);

// ── Evaluado (visitador / gerente) ────────────────────────────────────
export const misPendientes = () => api.get<Asignacion[]>('/examenes/mis-pendientes').then(r => r.data);
export const miHistorial = () => api.get<any[]>('/examenes/mi-historial').then(r => r.data);
export const iniciarExamen = (examenId: number) =>
  api.post<IntentoIniciado>(`/examenes/${examenId}/iniciar`).then(r => r.data);
export const responder = (intentoId: number, pregunta_id: number, indice_presentado: number) =>
  api.post(`/intentos/${intentoId}/responder`, { pregunta_id, indice_presentado });
export const entregar = (intentoId: number) =>
  api.post<ReporteIntento>(`/intentos/${intentoId}/entregar`).then(r => r.data);
export const reporteIntento = (intentoId: number) =>
  api.get<ReporteIntento>(`/intentos/${intentoId}/reporte`).then(r => r.data);
