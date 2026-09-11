import { api } from './api';

/** Avance contra la agenda. `avance_pct` es null cuando no hay nada planeado. */
export interface Avance {
  planeadas: number;
  ejecutadas: number;
  avance_pct: number | null;
}

export interface FilaRepresentante {
  rm_id: number;
  codigo: string;
  nombre: string;
  linea: string | null;
  gerente: string | null;
  v: number;
  r: number;
  farmacias: number;
  con_gd: number;
  more: number;
  ultima_actividad: string | null;
  semana: Avance;
  dia: Avance;
  /** La farmacia se trabaja APARTE: sin planeación, su avance es la cobertura del ciclo. */
  farmacia?: FarmaciaRepresentante;
}

export interface FarmaciaRepresentante {
  hoy: number;
  semana: number;
  visitadas_ciclo: number;
  universo: number;
  /** null cuando el representante no tiene farmacias aprobadas en su panel. */
  cobertura_pct: number | null;
}

export interface ResumenDia {
  fecha: string;
  ciclo: { id: number; nombre: string; vencido: boolean; cerrado: boolean; semana: number | null } | null;
  totales: {
    medicas: number; farmacias: number; visitas: number;
    rms_con_actividad: number; rms_total: number;
    acompanadas_gd: number; hojas_more: number;
  };
  semana: { numero: number | null; planeadas: number; ejecutadas: number;
            avance_pct: number | null; calculable: boolean };
  /** Cobertura de farmacia del equipo en el ciclo — separada de la visita médica. */
  farmacia?: { semana: number; visitadas_ciclo: number; universo: number;
               cobertura_pct: number | null; calculable: boolean };
  representantes: FilaRepresentante[];
}

// ── Detalle del día de un representante (lo que hay detrás de su fila) ──────
export interface VisitaDetalle {
  id: number; medico_id: number; medico: string; tipo_visita: string; ejecutada: boolean;
  acompanado: boolean; causa_no_visita: string | null; comentario: string | null;
  productos: string[]; tiene_gps: boolean; tiene_foto: boolean; hora: string | null;
  especialidad: string | null; categoria: string | null;
  /** Planeado para ese día (semana del ciclo + día); si no, fue fuera de agenda. */
  programada_hoy: boolean;
}
export interface FarmaciaDetalle {
  id: number; farmacia: string; ejecutada: boolean; causa_no_visita: string | null;
  comentario: string | null; hora: string | null; tiene_gps: boolean; tiene_foto: boolean;
}
export interface MoreDetalle {
  id: number; gerente: string | null; medicos_vistos: number; evaluacion_promedio: number | null;
}
export interface DetalleDia {
  rm_id: number; codigo?: string; nombre?: string; fecha?: string;
  visitas: VisitaDetalle[]; farmacias: FarmaciaDetalle[]; more: MoreDetalle[];
}
export const detalleDia = (rmId: number, fecha?: string) =>
  api.get<DetalleDia>('/visita/dia/detalle', { params: { rm_id: rmId, ...(fecha ? { fecha } : {}) } })
    .then((r) => r.data);

export const resumenDia = (params: {
  fecha?: string; pais_codigo?: string; gerente_id?: number; linea_id?: number;
} = {}) => api.get<ResumenDia>('/visita/dia', { params }).then((r) => r.data);
