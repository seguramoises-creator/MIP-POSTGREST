/**
 * farmacias.service.ts — Módulo de Farmacias (maestro único + panel VM + aprobación VM→GD).
 * Espejo de maestroMedicos.service.ts / visita.service.ts. Rutas exactas del router
 * backend `/farmacias` (ver backend/app/api/v1/routers/farmacias.py).
 */
import { api } from './api';

// ─────────────────────────────────────────────────────────────────────────
// Maestro (Config.DIM_Farmacia)
// ─────────────────────────────────────────────────────────────────────────

export interface FarmaciaMaestro {
  id: number;
  pais_codigo: string;
  es_cadena: boolean;
  cadena: string | null;
  sucursal: string | null;
  nombre: string | null;
  nombre_completo: string;
  direccion: string;
  provincia: string | null;
  municipio: string | null;
  sector: string | null;
  latitud: number | null;
  longitud: number | null;
  encargado: string;
  telefono: string | null;
  email: string | null;
  estado: string;   // ACTIVA | PENDIENTE_APROBACION | RECHAZADA
  origen: string;    // VM | CONFIG
  activo: boolean;
  created_at: string;
  updated_at: string;
}

/** Payload de las Acciones A/B del VM (Acción B) y del alta directa (ADMIN/GERPROD). */
export interface FarmaciaDatos {
  es_cadena: boolean;
  cadena?: string | null;
  sucursal?: string | null;
  nombre?: string | null;
  direccion: string;
  provincia?: string | null;
  municipio?: string | null;
  sector?: string | null;
  latitud?: number | null;
  longitud?: number | null;
  encargado: string;
  telefono?: string | null;
  email?: string | null;
}

export interface FarmaciaDuro {
  id: number;
  cadena: string | null;
  sucursal: string | null;
  nombre: string | null;
  nombre_completo: string;
  estado: string;
}

export interface FarmaciaBuscarResultado {
  duros: FarmaciaDuro[];
  existe: boolean;
}

/** Búsqueda anti-dup del maestro (F25/F09): si `existe` es false, habilita el
 *  formulario de creación (Acción B). */
export const buscarFarmaciaMaestro = (params: {
  cadena?: string; sucursal?: string; nombre?: string; pais_codigo?: string;
}) => api.get<FarmaciaBuscarResultado>('/farmacias/maestro/buscar', { params }).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────
// Panel del VM — Acciones A/B + lectura
// ─────────────────────────────────────────────────────────────────────────

export interface FarmaciaPanelResponse {
  id: number;
  maestro_farmacia_id: number;
  estado_aprobacion: string;   // PENDIENTE_ALTA | APROBADO | RECHAZADO
  vm_id: number;
  fecha_solicitud: string | null;
  fecha_aprobacion: string | null;
  motivo: string | null;
}

/** Acción A: agregar al panel una farmacia YA existente y ACTIVA del maestro. */
export const panelAgregarFarmacia = (maestroFarmaciaId: number, vmId?: number) =>
  api.post<FarmaciaPanelResponse>(
    '/farmacias/panel/agregar', { maestro_farmacia_id: maestroFarmaciaId },
    { params: vmId ? { vm_id: vmId } : {} },
  ).then((r) => r.data);

/** Acción B: dar de alta una farmacia nueva (bloqueantes F23/F24 + anti-dup F25/F09). */
export const panelCrearFarmacia = (datos: FarmaciaDatos, vmId?: number) =>
  api.post<FarmaciaPanelResponse>(
    '/farmacias/panel/crear', datos, { params: vmId ? { vm_id: vmId } : {} },
  ).then((r) => r.data);

export interface FarmaciaPanelItem {
  panel_id: number;
  maestro_farmacia_id: number;
  nombre_completo: string | null;
  direccion: string | null;
  encargado: string | null;
  estado_maestro: string | null;
  estado_aprobacion: string;   // PENDIENTE_ALTA | APROBADO | RECHAZADO
  ciclos_sin_visita: number;
  /** No siempre viene del backend (solo si se agrega en el futuro) — se muestra si está presente. */
  motivo?: string | null;
}

export const listarPanelFarmacias = (vmId?: number, incluirInactivos = false) =>
  api.get<FarmaciaPanelItem[]>('/farmacias/panel', {
    params: { ...(vmId ? { vm_id: vmId } : {}), incluir_inactivos: incluirInactivos },
  }).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────
// Registro de visita a Farmacia (AD-HOC, guard F22)
// ─────────────────────────────────────────────────────────────────────────

export interface VisitaFarmaciaRegistrar {
  comentario?: string | null;
  hace_minutos?: number;
  ejecutada?: boolean;
  causa_no_visita?: string | null;
  latitud?: number | null;
  longitud?: number | null;
}

export interface VisitaFarmaciaResultado {
  id: number;
  vm_id: number;
  ciclo_id: number;
  farmacia_id: number;
  ejecutada: boolean;
  hora: string | null;
}

export const registrarVisitaFarmacia = (panelId: number, body: VisitaFarmaciaRegistrar, vmId?: number) =>
  api.post<VisitaFarmaciaResultado>(
    `/farmacias/${panelId}/visita`, body, { params: vmId ? { vm_id: vmId } : {} },
  ).then((r) => r.data);

export const subirFotoVisitaFarmacia = (visitaId: number, file: File) => {
  const fd = new FormData();
  fd.append('archivo', file);
  return api.post(`/farmacias/${visitaId}/foto`, fd, {
    headers: { 'Content-Type': 'multipart/form-data' },
  }).then((r) => r.data);
};

// ─────────────────────────────────────────────────────────────────────────
// Bandeja de aprobación (GD/ADMIN)
// ─────────────────────────────────────────────────────────────────────────

export interface FarmaciaPendiente {
  id: number;                  // panel_id
  maestro_farmacia_id: number;
  nombre_completo: string | null;
  direccion: string | null;
  encargado: string | null;
  estado_maestro: string | null;
  tipo_solicitud: 'NUEVA' | 'AGREGAR';
  vm_id: number;
  vm_nombre: string;
  fecha_solicitud: string | null;
  /** No siempre viene del backend — se muestra si está presente. */
  posible_duplicado?: { nombre_completo: string; id: number }[] | null;
}

export const aprobacionPendientesFarmacias = (gerenteId?: number) =>
  api.get<FarmaciaPendiente[]>('/farmacias/aprobacion/pendientes', {
    params: gerenteId ? { gerente_id: gerenteId } : {},
  }).then((r) => r.data);

export const aprobarFarmacia = (panelId: number) =>
  api.post<FarmaciaPanelResponse>(`/farmacias/aprobacion/${panelId}/aprobar`).then((r) => r.data);

export const rechazarFarmacia = (panelId: number, motivo: string) =>
  api.post<FarmaciaPanelResponse>(`/farmacias/aprobacion/${panelId}/rechazar`, { motivo }).then((r) => r.data);

export interface FarmaciaEditarAprobar {
  direccion?: string;
  encargado?: string;
  telefono?: string | null;
  email?: string | null;
  provincia?: string | null;
  municipio?: string | null;
  sector?: string | null;
}
export const editarYAprobarFarmacia = (panelId: number, cambios: FarmaciaEditarAprobar) =>
  api.post<FarmaciaPanelResponse>(`/farmacias/aprobacion/${panelId}/editar-aprobar`, cambios).then((r) => r.data);

// ─────────────────────────────────────────────────────────────────────────
// Maestro — CRUD directo (ADMIN/GERENTE_PRODUCTIVIDAD, sin aprobación)
// ─────────────────────────────────────────────────────────────────────────

export const listarMaestroFarmacias = (params: { pais_codigo?: string; estado?: string; q?: string } = {}) =>
  api.get<FarmaciaMaestro[]>('/farmacias/maestro', { params }).then((r) => r.data);

export const obtenerMaestroFarmacia = (id: number) =>
  api.get<FarmaciaMaestro>(`/farmacias/maestro/${id}`).then((r) => r.data);

export const crearMaestroFarmacia = (paisCodigo: string, datos: FarmaciaDatos) =>
  api.post<FarmaciaMaestro>('/farmacias/maestro', datos, { params: { pais_codigo: paisCodigo } }).then((r) => r.data);

export const actualizarMaestroFarmacia = (id: number, datos: Partial<FarmaciaDatos> & { activo?: boolean; es_cadena?: boolean }) =>
  api.put<FarmaciaMaestro>(`/farmacias/maestro/${id}`, datos).then((r) => r.data);
