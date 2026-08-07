/**
 * onboarding.service.ts — Onboarding y Biblioteca (§4 y §5).
 * Rutas exactas del router backend `/formacion`
 * (ver backend/app/api/v1/routers/formacion.py).
 *
 * El representante solo recibe material APROBADO: lo filtra el backend según el
 * rol, no esta capa.
 */
import { api } from './api';

export type TipoMaterial = 'manual' | 'ayuda_visual' | 'estudio_clinico' | 'ficha_tecnica' | 'video';
export type RolEnRuta = 'principal' | 'relacionado';

export const TIPOS_MATERIAL: TipoMaterial[] =
  ['manual', 'ayuda_visual', 'estudio_clinico', 'ficha_tecnica', 'video'];

export interface Producto {
  id: number; nombre_producto: string; rol_en_ruta: RolEnRuta; activo: boolean;
}

export interface Material {
  id: number; titulo: string; tipo: TipoMaterial; archivo_url: string;
  obligatorio: boolean; producto_id: number | null; aprobado_por_gm: boolean;
}

export interface MaterialEntrada {
  pais_codigo: string; titulo: string; tipo: TipoMaterial; archivo_url: string;
  producto_id?: number | null; obligatorio?: boolean;
  usado_en_examen_id?: number | null; usado_en_coaching_av?: boolean;
}

export interface ProgresoLectura {
  total: number; confirmados: number; completo: boolean;
  pendientes: { id: number; titulo: string; tipo: TipoMaterial }[];
}

export interface Confirmacion { rm_id: number; confirmado_en: string; }

export interface Paso {
  id: number; orden: number; titulo: string; tipo: string;
  plazo_sugerido: string | null; bloqueante: boolean; quien_lo_marca: string;
}

export interface MiAsignacion {
  id: number; plantilla_id: number; nombre_plantilla: string;
  fecha_inicio: string; progreso_pct: number; completada_en: string | null;
}

export interface PasoEstado {
  paso_id: number; orden: number; titulo: string; tipo: string;
  quien_lo_marca: string;
  estado: 'completado' | 'disponible' | 'bloqueado';
  bloqueos: string[];
  material?: ProgresoLectura | null;
}

export interface EstadoRuta {
  asignacion_id: number; rm_id: number; plantilla_id: number;
  total_pasos: number; completados: number; progreso_pct: number;
  pasos: PasoEstado[];
}

// ── Productos de línea (§4.3) ─────────────────────────────────────────────
export const listarProductos = (paisCodigo: string, lineaId: number) =>
  api.get<Producto[]>('/formacion/productos',
    { params: { pais_codigo: paisCodigo, linea_id: lineaId } }).then((r) => r.data);

export const crearProducto = (body: {
  pais_codigo: string; linea_id: number; nombre_producto: string; rol_en_ruta: RolEnRuta;
}) => api.post<{ id: number; nombre_producto: string; rol_en_ruta: RolEnRuta }>(
  '/formacion/productos', body).then((r) => r.data);

// ── Biblioteca (§5) ───────────────────────────────────────────────────────
export const listarMateriales = (paisCodigo: string, productoId?: number) =>
  api.get<Material[]>('/formacion/biblioteca', {
    params: { pais_codigo: paisCodigo, ...(productoId != null ? { producto_id: productoId } : {}) },
  }).then((r) => r.data);

export const subirMaterial = (body: MaterialEntrada) =>
  api.post<{ id: number; titulo: string; aprobado_por_gm: boolean }>(
    '/formacion/biblioteca', body).then((r) => r.data);

export const aprobarMaterial = (materialId: number) =>
  api.post<{ id: number; aprobado_por_gm: boolean }>(
    `/formacion/biblioteca/${materialId}/aprobar`).then((r) => r.data);

export const confirmarLectura = (materialId: number) =>
  api.post<{ material_id: number; confirmado_en: string }>(
    `/formacion/biblioteca/${materialId}/confirmar`).then((r) => r.data);

export const confirmacionesDeMaterial = (materialId: number) =>
  api.get<Confirmacion[]>(`/formacion/biblioteca/${materialId}/confirmaciones`)
    .then((r) => r.data);

export const progresoLectura = (productoIds: number[]) =>
  api.get<ProgresoLectura>('/formacion/biblioteca/progreso',
    { params: { producto_ids: productoIds.join(',') } }).then((r) => r.data);

// ── Onboarding (§4) ───────────────────────────────────────────────────────
export const crearPlantilla = (body: {
  pais_codigo: string; linea_id: number; nombre_plantilla: string; duracion_dias: number;
}) => api.post<{ id: number; nombre_plantilla: string; pasos: Paso[] }>(
  '/formacion/onboarding/plantillas', body).then((r) => r.data);

export const pasosDePlantilla = (plantillaId: number) =>
  api.get<Paso[]>(`/formacion/onboarding/plantillas/${plantillaId}/pasos`).then((r) => r.data);

export const asignarRuta = (body: { plantilla_id: number; rm_id: number; fecha_inicio?: string | null }) =>
  api.post<{ id: number; rm_id: number; progreso_pct: number }>(
    '/formacion/onboarding/asignaciones', body).then((r) => r.data);

export const misAsignaciones = () =>
  api.get<MiAsignacion[]>('/formacion/onboarding/mis-asignaciones').then((r) => r.data);

export const estadoRuta = (asignacionId: number) =>
  api.get<EstadoRuta>(`/formacion/onboarding/asignaciones/${asignacionId}`).then((r) => r.data);

export const completarPaso = (asignacionId: number, pasoId: number, observaciones?: string) =>
  api.post<{ paso_id: number; completado_en: string }>(
    `/formacion/onboarding/asignaciones/${asignacionId}/pasos/${pasoId}/completar`,
    null, { params: observaciones ? { observaciones } : {} }).then((r) => r.data);
