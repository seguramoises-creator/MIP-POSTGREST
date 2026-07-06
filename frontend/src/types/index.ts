// ── Roles ─────────────────────────────────────────────────────────────
export type Rol =
  | 'ADMIN'
  | 'PRESIDENCIA'
  | 'DIR_COMERCIAL'
  | 'GERENTE_PRODUCTIVIDAD'
  | 'GERENTE_DISTRITO'
  | 'GERENTE_MARCA'
  | 'REPRESENTANTE_MEDICO'
  | 'CAPACITACION'
  | 'CONSULTA';

// ── Auth ──────────────────────────────────────────────────────────────
export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  expires_in: number;
  debe_cambiar_password?: boolean;
  password_expira_en_dias?: number | null;
  password_motivo?: string;
}

export interface Usuario {
  id: number;
  username: string;
  email: string;
  nombre_completo: string;
  rol: Rol;
  pais_id: number | null;
  rm_id: number | null;
  activo: boolean;
}

// ── Catálogos ─────────────────────────────────────────────────────────
export interface Pais {
  id: number;
  codigo: string;
  nombre: string;
  moneda?: string;
  activo: boolean;
}

export interface Linea {
  id: number;
  pais_id: number;
  codigo: string;
  nombre: string;
  activo: boolean;
}

export interface Gerente {
  id: number;
  pais_id: number;
  linea_id: number | null;
  codigo: string;
  nombre: string;
  email?: string;
  tipo: string;
  activo: boolean;
}

export interface RM {
  id: number;
  pais_id: number;
  linea_id: number;
  gerente_id: number | null;
  codigo: string;
  nombre: string;
  cedula?: string;
  email?: string;
  zona?: string;
  activo: boolean;
}

export interface Indicador {
  id: number;
  pais_id: number;
  codigo: string;
  nombre: string;
  rol: string;
  modulo: string;          // GESTION | RESULTADOS
  tipo_periodo: string;    // CICLO | MES
  ponderacion_pct: number; // 0-100
  escala: number;          // 1 (%) ó 100 (puntos)
  valor_min: number | null;
  valor_max: number | null;
  peso_iup: number;
  activo: boolean;
}

export interface IndicadorTabla {
  id: number;
  indicador_id: number;
  pais_id: number;
  rango_desde: number;
  rango_hasta: number;
  puntos: number;
}

export interface Ciclo {
  id: number;
  pais_id: number;
  anio: number;
  numero: number;
  nombre: string;
  nombre_canonico: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  cerrado: boolean;
  activo: boolean;
}

// ── Productividad ─────────────────────────────────────────────────────
export interface ProductividadItem {
  rm_id: number;
  rm_codigo?: string;
  rm_nombre: string;
  pais_nombre?: string;
  linea_nombre?: string;
  indicador?: string;
  indicador_nombre?: string;
  indicador_codigo?: string;
  valor_meta?: number | null;
  valor_real: number | null;
  cumplimiento_pct?: number | null;
  porcentaje_cumplimiento?: number | null;
  puntaje: number | null;
}

// ── Dashboard ─────────────────────────────────────────────────────────
export interface KPIEjecutivo {
  total_rms: number;
  iup_promedio: number;
  iup_maximo: number;
  iup_minimo: number;
  total_elegibles: number;
  pct_elegibles: number;
}

// ── Ranking ───────────────────────────────────────────────────────────
// Fuente: FACT_RankingRM (rediseño jun-2026) — ver ranking.py / ranking_service.py
export interface RankingItem {
  posicion: number;
  posicion_linea?: number;
  posicion_anterior?: number | null;
  variacion?: number;
  rm_id: number;
  rm_codigo?: string;
  rm_nombre: string;
  pais_id?: number;
  pais_nombre?: string;
  linea_nombre?: string;
  score_total: number;
  categoria_id?: number | null;
  elegible: boolean;
  tipo_ranking?: string;
  fecha_generacion?: string;
}

// ── ETL ───────────────────────────────────────────────────────────────
export interface ETLJob {
  id: number;
  tipo_archivo: string;
  estado: string;
  total_filas: number;
  filas_exitosas: number;
  filas_error: number;
  fecha_inicio: string;
  fecha_fin?: string;
}

// ── Paginación ────────────────────────────────────────────────────────
export interface Paginated<T> {
  items: T[];
  total: number;
  page: number;
  size: number;
}

// ── LSII (Matriz de Desarrollo — Liderazgo Situacional II) ─────────────
// Importante: ReceptividadOpcion NUNCA trae score_oculto ni peso_dimension
// — esos campos son internos del backend (ver lsii_service.py) y jamás
// se exponen al GD evaluador. El frontend solo muestra texto_comportamiento.
export interface ReceptividadOpcion {
  id: number;
  orden_opcion: number;
  texto_comportamiento: string;
}

export interface ReceptividadDimension {
  dimension_codigo: string;
  dimension_nombre: string;
  dimension_descripcion?: string | null;
  orden_dimension: number;
  opciones: ReceptividadOpcion[];
}

export interface SeleccionReceptividad {
  dimension_codigo: string;
  opcion_id: number;
}

export type NivelLsii = 'D1' | 'D2' | 'D3' | 'D4';

export interface EvaluacionLsii {
  id: number;
  pais_id: number;
  rm_id: number;
  gerente_id: number | null;
  ciclo_id: number;
  score_receptividad: number;
  score_desempeno: number | null;
  nivel_lsii: NivelLsii;
  estilo_liderazgo: string;
  observaciones?: string | null;
  fecha_evaluacion: string;
}

export interface MatrizLsiiItem {
  rm_id: number;
  rm_codigo?: string;
  rm_nombre: string;
  pais_id: number;
  gerente_id: number | null;
  gerente_nombre?: string | null;
  ciclo_id: number;
  score_desempeno: number;     // eje Y
  score_receptividad: number;  // eje X
  nivel_lsii: NivelLsii;
  estilo_liderazgo: string;
  fecha_evaluacion: string;
}

// ── LSII — Administración (ADMIN / GERENTE_PRODUCTIVIDAD) ──────────────
// A diferencia de ReceptividadOpcion (vista del GD), estas variantes SÍ
// exponen score_oculto y peso_dimension — solo se usan en /lsii/admin/*.
export interface ReceptividadOpcionAdmin {
  id?: number;
  orden_opcion: number;
  texto_comportamiento: string;
  score_oculto: number;
  activo: boolean;
}

export interface ReceptividadDimensionAdmin {
  dimension_codigo: string;
  dimension_nombre: string;
  dimension_descripcion?: string | null;
  orden_dimension: number;
  peso_dimension: number;
  activo: boolean;
  opciones: ReceptividadOpcionAdmin[];
}

export interface ConfiguracionLsii {
  corte_desempeno: number;
  corte_receptividad: number;
  actualizado_en: string;
  actualizado_por?: string | null;
}
