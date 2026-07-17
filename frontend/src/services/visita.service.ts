import { api } from './api';

export interface MedicoVisita {
  id: number;
  vm_id: number;
  codigo: string | null;
  nombre_completo: string;
  nombre: string | null;
  apellidos: string | null;
  especialidad_id: number | null;
  especialidad_nombre: string | null;
  subespecialidad: string | null;
  linea_id?: number | null;
  linea_nombre?: string | null;
  categoria: string;
  centro_trabajo: string | null;
  institucion_tipo: string | null;
  tipo_consultorio: string | null;
  provincia: string | null;
  municipio: string | null;
  sector: string | null;
  direccion: string | null;
  latitud: number | null;
  longitud: number | null;
  telefono: string | null;
  email: string | null;
  exequatur: string | null;
  dias_consulta: string | null;
  horario_consulta: string | null;
  frecuencia_visita: string | null;
  acepta_visita: boolean | null;
  potencial_prescripcion: string | null;
  kol: boolean | null;
  segmento: string | null;
  observaciones: string | null;
  fecha_alta: string | null;
  fecha_ultima_visita: string | null;
  ciclos_sin_visita: number;
  activo: boolean;
  estado_visita?: 'vr' | 'v' | 'sin';   // Vista+Revisita / una visita / sin visitar
  estado_aprobacion?: 'APROBADO' | 'PENDIENTE_ALTA' | 'PENDIENTE_BAJA' | 'RECHAZADO';
  ciclo_baja_id?: number | null;
}

export interface AprobacionPendiente {
  id: number; nombre_completo: string; categoria: string; especialidad_nombre: string | null;
  vm_id: number; vm_nombre: string; linea_nombre: string | null;
  tipo_solicitud: 'ALTA' | 'BAJA'; fecha_solicitud: string | null;
}

export interface MedicoCrear {
  vm_id: number;
  codigo?: string | null;
  nombre_completo: string;
  nombre?: string | null;
  apellidos?: string | null;
  especialidad_id?: number | null;
  subespecialidad?: string | null;
  categoria: string;
  centro_trabajo?: string | null;
  institucion_tipo?: string | null;
  tipo_consultorio?: string | null;
  provincia?: string | null;
  municipio?: string | null;
  sector?: string | null;
  direccion?: string | null;
  latitud?: number | null;
  longitud?: number | null;
  telefono?: string | null;
  email?: string | null;
  exequatur?: string | null;
  dias_consulta?: string | null;
  horario_consulta?: string | null;
  frecuencia_visita?: string | null;
  acepta_visita?: boolean;
  potencial_prescripcion?: string | null;
  kol?: boolean;
  segmento?: string | null;
  observaciones?: string | null;
  fecha_alta?: string | null;
  confirmar_duplicado?: boolean;
}

export interface PosibleDuplicado {
  id: number; nombre_completo: string; direccion: string | null; palabras_coinciden: number;
}

export interface Catalogo { id: number; nombre: string; }

// `lite=true` trae solo campos de lista (rendimiento). La ficha completa se pide con
// obtenerMedico(id) al editar.
export const listarMedicos = (vmId?: number, incluirInactivos = false, lite = false) =>
  api.get<MedicoVisita[]>('/visita/medicos', {
    params: {
      ...(vmId ? { vm_id: vmId } : {}), ...(incluirInactivos ? { incluir_inactivos: true } : {}),
      ...(lite ? { lite: true } : {}),
    },
  }).then(r => r.data);

// Ficha COMPLETA de un médico (para editar en el Panel).
export const obtenerMedico = (id: number) =>
  api.get<MedicoVisita>(`/visita/medicos/${id}`).then(r => r.data);

// Médico existente (ya registrado por otro VM del país) que se puede COPIAR al panel.
export type MedicoExistente = MedicoVisita & { vm_nombre?: string | null };

export const listarMedicosExistentes = (vmId?: number) =>
  api.get<MedicoExistente[]>('/visita/medicos/existentes', {
    params: vmId ? { vm_id: vmId } : {},
  }).then(r => r.data);

export type MedicoActualizar = Partial<Omit<MedicoCrear, 'vm_id' | 'confirmar_duplicado'>>;
export const actualizarMedico = (id: number, datos: MedicoActualizar) =>
  api.put<MedicoVisita>(`/visita/medicos/${id}`, datos).then(r => r.data);

// Flujo de aprobación de alta/baja (Gerente de Distrito)
export const solicitarBajaMedico = (id: number) =>
  api.post(`/visita/medicos/${id}/baja`).then(r => r.data);
export const reactivarMedico = (id: number) =>
  api.post(`/visita/medicos/${id}/reactivar`).then(r => r.data);
export const listarAprobaciones = () =>
  api.get<AprobacionPendiente[]>('/visita/aprobaciones').then(r => r.data);
export const aprobarMedico = (id: number) =>
  api.post(`/visita/medicos/${id}/aprobar`).then(r => r.data);
export const rechazarMedico = (id: number, motivo?: string) =>
  api.post(`/visita/medicos/${id}/rechazar`, null, { params: motivo ? { motivo } : {} }).then(r => r.data);

export const listarEspecialidades = () =>
  api.get<Catalogo[]>('/visita/especialidades').then(r => r.data);

// Carga masiva del Panel Médico desde los datos ya cargados en Categorización.
export const importarMedicosCategorizacion = () =>
  api.post<{ creados: number; omitidos: number; invalidos: number; total_origen: number }>(
    '/visita/medicos/importar-categorizacion').then(r => r.data);

// Catálogos geográficos (dropdowns del maestro de médicos).
export interface Provincia { id: number; nombre: string; pais_codigo?: string; }
export interface Municipio { id: number; nombre: string; provincia_id?: number; }
export const listarProvincias = (paisCodigo?: string) =>
  api.get<Provincia[]>('/visita/provincias', { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then(r => r.data);
export const listarMunicipios = (provinciaId: number) =>
  api.get<Municipio[]>('/visita/municipios', { params: { provincia_id: provinciaId } }).then(r => r.data);
export const listarCentros = (paisCodigo?: string) =>
  api.get<Catalogo[]>('/visita/centros', { params: paisCodigo ? { pais_codigo: paisCodigo } : {} }).then(r => r.data);

export const listarVMs = () =>
  api.get<Catalogo[]>('/visita/vms').then(r => r.data);

export interface MiGerente { gerente: string | null; gerente_tipo: string | null; linea: string | null; vm: string | null; }
export const miGerente = (vmId?: number) =>
  api.get<MiGerente>('/visita/mi-gerente', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Cobertura ─────────────────────────────────────────────────────────
export interface CatCobertura { total: number; visitados: number; completos: number; }
export interface CoberturaResumen {
  ciclo_id: number | null;
  panel: number; visitados: number; con_revisita: number; sin_visitar: number;
  pct_cobertura: number; pct_completa: number; pct_gap: number;
  acompanadas?: number; visitas_ejecutadas?: number; pct_acompanamiento?: number;
  objetivo_cobertura: number; objetivo_completa: number;
  categorias: Record<string, CatCobertura>;
  sin_visita: { id: number; nombre: string; categoria: string }[];
  falta_revisita: { id: number; nombre: string; categoria: string }[];
  ruptura: { id: number; nombre: string; categoria: string; ciclos_sin_visita: number }[];
}
export interface RankingVM {
  metrica: string; objetivo: number | null; no_cumplen: number; total: number;
  items: { vm_id: number; nombre: string; zona: string | null; valor: number; cumple: boolean }[];
}
export interface CoberturaFiltros { vmId?: number; gerenteId?: number; lineaId?: number; soloRuptura?: boolean; }
export const coberturaResumen = (f: CoberturaFiltros = {}) =>
  api.get<CoberturaResumen>('/visita/cobertura/resumen', { params: {
    ...(f.vmId && { vm_id: f.vmId }), ...(f.gerenteId && { gerente_id: f.gerenteId }),
    ...(f.lineaId && { linea_id: f.lineaId }), ...(f.soloRuptura && { solo_ruptura: true }),
  } }).then(r => r.data);
export const listarGerentesVisita = () => api.get<Catalogo[]>('/visita/gerentes').then(r => r.data);
export const coberturaRanking = (metrica: string) =>
  api.get<RankingVM>('/visita/cobertura/ranking', { params: { metrica } }).then(r => r.data);

// ── Registro de visita ────────────────────────────────────────────────
export interface VisitaHoy {
  id: number; medico_id: number; medico: string; tipo_visita: string;
  ejecutada: boolean; causa_no_visita: string | null; comentario: string | null;
  productos: string[]; hora: string | null;
  tiene_gps?: boolean; tiene_foto?: boolean; acompanado?: boolean;
}
export interface AgendaMedico {
  medico_id: number; nombre: string; especialidad: string | null; categoria: string;
  centro_trabajo: string | null; provincia: string | null; linea_id: number | null;
  tipo_visita: string; hora_estimada: string | null;
  dia_semana?: string | null; grupo?: 'dia' | 'ciclo';
  estado: 'pendiente' | 'registrada'; no_visita: boolean;
}
export interface ProductoDetalle { producto: string; mencion: number; }

export const listarCausas = () => api.get<string[]>('/visita/causas').then(r => r.data);
export const misVisitasHoy = (vmId?: number) =>
  api.get<VisitaHoy[]>('/visita/mis-visitas-hoy', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
// Historial SOLO LECTURA: el RM consulta sus visitas anteriores (y su comentario),
// nunca puede editarlas — no existen endpoints de edición de visitas.
export const historialVisitas = (vmId?: number, dias = 30) =>
  api.get<VisitaHoy[]>('/visita/historial', { params: { dias, ...(vmId ? { vm_id: vmId } : {}) } }).then(r => r.data);
export const agendaHoy = (vmId?: number) =>
  api.get<AgendaMedico[]>('/visita/agenda-hoy', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const registrarVisita = (
  medico_id: number, tipo_visita: string, comentario: string, hace_minutos = 0,
  productos: ProductoDetalle[] = [], vmId?: number,
  latitud?: number | null, longitud?: number | null, acompanado = false,
) => api.post<{ id: number; tipo: string; hora: string | null }>(
  '/visita/registrar',
  { medico_id, tipo_visita, comentario, hace_minutos, productos, acompanado,
    latitud: latitud ?? null, longitud: longitud ?? null },
  { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const subirFotoVisita = (visitaId: number, file: File) => {
  const fd = new FormData(); fd.append('archivo', file);
  return api.post(`/visita/${visitaId}/foto`, fd, { headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};
export const registrarNoVisita = (medico_id: number, causa: string, comentario?: string, vmId?: number) =>
  api.post('/visita/no-visita', { medico_id, causa, comentario }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Planeación del ciclo ──────────────────────────────────────────────
export interface PlaneacionItem {
  medico_id: number; tipo_visita: string; semana: number;
  dia_semana?: string | null; hora_estimada?: string | null;
}
export interface PlaneacionResumen {
  ciclo_id: number | null; panel: number; total_planeadas: number;
  medicos_planeados: number; cobertura_planeada_pct: number;
  cat_a_sin_revisita: number; carga_por_dia: number;
}
export const obtenerPlaneacion = (vmId?: number) =>
  api.get<PlaneacionItem[]>('/visita/planeacion', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const guardarPlaneacion = (items: PlaneacionItem[], vmId?: number) =>
  api.post<{ guardadas: number }>('/visita/planeacion', { items }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const planeacionResumen = (vmId?: number) =>
  api.get<PlaneacionResumen>('/visita/planeacion/resumen', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Publicación de la planeación (la CONGELA: es el denominador de la cobertura) ──
export interface PlaneacionEvento {
  evento: 'PUBLICADA' | 'DESBLOQUEADA'; fecha: string;
  usuario_id: number | null; motivo: string | null; items: number | null;
}
export interface PlaneacionEstado {
  ciclo_id: number | null; publicada: boolean; publicada_en: string | null;
  historial: PlaneacionEvento[];
}
export const planeacionEstado = (vmId?: number) =>
  api.get<PlaneacionEstado>('/visita/planeacion/estado', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const publicarPlaneacion = (vmId?: number) =>
  api.post<{ publicada: boolean; items: number }>('/visita/planeacion/publicar', null,
    { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
/** Solo ADMIN. `vmId` es obligatorio y el motivo queda registrado. */
export const desbloquearPlaneacion = (vmId: number, motivo: string) =>
  api.post<{ publicada: boolean }>('/visita/planeacion/desbloquear', { motivo },
    { params: { vm_id: vmId } }).then(r => r.data);

// ── Ruptura de secuencia / Cierre de ciclo ────────────────────────────
export interface RupturaMedico {
  id: number; nombre: string; categoria: string;
  vm_id: number; vm_nombre: string; ciclos_sin_visita: number;
}
export interface RupturaEstado {
  total: number; alerta: number; grave: number; critica: number;
  medicos: { alerta: RupturaMedico[]; grave: RupturaMedico[]; critica: RupturaMedico[] };
}
export interface CierrePreview {
  ciclo_id: number; panel: number; visitados: number; sin_visitar: number;
  ruptura_nueva: number; ruptura_critica: number; ya_cerrado?: boolean; fecha_cierre?: string | null;
}
export interface CierreHist {
  id: number; ciclo_id: number; ciclo_nombre: string; fecha_cierre: string | null;
  panel: number; visitados: number; sin_visitar: number; ruptura_nueva: number; ruptura_critica: number;
}
export const estadoRuptura = (f: { vmId?: number; gerenteId?: number; lineaId?: number } = {}) =>
  api.get<RupturaEstado>('/visita/ruptura', { params: {
    ...(f.vmId && { vm_id: f.vmId }), ...(f.gerenteId && { gerente_id: f.gerenteId }),
    ...(f.lineaId && { linea_id: f.lineaId }),
  } }).then(r => r.data);
export const previsualizarCierre = () =>
  api.get<CierrePreview>('/visita/cierre/previsualizar').then(r => r.data);
export const cerrarCiclo = () => api.post<CierrePreview>('/visita/cierre').then(r => r.data);
export const historialCierres = () => api.get<CierreHist[]>('/visita/cierre/historial').then(r => r.data);

// ── Parrilla promocional / Muestras ───────────────────────────────────
export interface ProductoDim {
  id: number; codigo: string; nombre: string; area_terapeutica: string | null;
  descripcion: string | null; segmento_target: string | null;
  meta_muestras_visita: number; gerente_producto: string | null; linea_id: number | null;
}
export interface ParrillaItem {
  id?: number; producto_id?: number | null; producto: string; nombre?: string;
  area_terapeutica?: string | null; descripcion?: string | null; gerente_producto?: string | null;
  mensaje_clave?: string | null; segmento_target?: string | null;
  prioridad: number; meta_muestras: number; publicada?: boolean; fecha_publicacion?: string | null;
}
export interface PenetracionProducto {
  producto: string; nombre: string | null; segmento_target: string | null;
  medicos: number; penetracion_pct: number; muestras_total: number; promedio_visita: number;
}
export interface PenetracionCiclo {
  ciclo_id: number; panel: number; visitas: number; productos: PenetracionProducto[];
}
export const listarProductosDim = (lineaId?: number) =>
  api.get<ProductoDim[]>('/visita/productos', { params: lineaId ? { linea_id: lineaId } : {} }).then(r => r.data);
export const publicarParrilla = (linea_id: number, cicloId?: number) =>
  api.post<{ publicados: number }>('/visita/parrilla/publicar', null, { params: { linea_id, ...(cicloId && { ciclo_id: cicloId }) } }).then(r => r.data);
export const parrillaPenetracion = (lineaId?: number, cicloId?: number) =>
  api.get<PenetracionCiclo>('/visita/parrilla/penetracion', { params: { ...(lineaId && { linea_id: lineaId }), ...(cicloId && { ciclo_id: cicloId }) } }).then(r => r.data);
export interface MuestraResumenProducto {
  producto: string; mensaje_clave: string | null; entregadas: number;
  medicos_alcanzados: number; meta: number; cobertura_meta_pct: number | null; en_parrilla: boolean;
}
export interface MuestrasResumen {
  ciclo_id: number; total_entregadas: number; productos_con_muestras: number;
  productos: MuestraResumenProducto[];
}
export const listarLineasVisita = () => api.get<Catalogo[]>('/visita/lineas').then(r => r.data);
export const obtenerParrilla = (lineaId?: number, cicloId?: number, vmId?: number) =>
  api.get<ParrillaItem[]>('/visita/parrilla', { params: { ...(lineaId && { linea_id: lineaId }), ...(cicloId && { ciclo_id: cicloId }), ...(vmId && { vm_id: vmId }) } }).then(r => r.data);
export const guardarParrilla = (linea_id: number, items: ParrillaItem[], cicloId?: number) =>
  api.post<{ guardados: number }>('/visita/parrilla', { linea_id, items, ciclo_id: cicloId ?? null }).then(r => r.data);
export const registrarMuestras = (medico_id: number, entregas: { producto: string; cantidad: number }[], vmId?: number) =>
  api.post<{ registradas: number }>('/visita/muestras', { medico_id, entregas }, { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const muestrasResumen = (vmId?: number) =>
  api.get<MuestrasResumen>('/visita/muestras/resumen', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

// ── Costo & ROI ───────────────────────────────────────────────────────
export interface ParametroCosto {
  ciclo_id: number; linea_id: number | null; costo_visita: number; costo_muestra: number;
  costo_fijo_ciclo: number; moneda: string; configurado: boolean;
}
export interface RoiResumen {
  ciclo_id: number; configurado: boolean; moneda: string;
  contactos: number; medicos_visitados: number; muestras: number;
  costo_visitas: number; costo_muestras: number; costo_fijo: number; costo_total: number;
  costo_por_contacto: number; costo_por_medico: number;
  ingresos: number; utilidad: number; roi_pct: number | null;
  ratio_ingreso_costo: number | null; rentable: boolean | null;
}
export interface RoiRankingItem {
  vm_id: number; nombre: string; zona: string | null;
  costo_total: number; ingresos: number; valor: number; cumple: boolean;
}
export interface RoiRanking { metrica: string; objetivo: number; no_cumplen: number; total: number; items: RoiRankingItem[]; }

export const obtenerParametrosCosto = (lineaId?: number) =>
  api.get<ParametroCosto>('/visita/costo/parametros', { params: lineaId ? { linea_id: lineaId } : {} }).then(r => r.data);
export const guardarParametrosCosto = (datos: {
  linea_id: number | null; costo_visita: number; costo_muestra: number; costo_fijo_ciclo: number; moneda: string;
}) => api.post<ParametroCosto>('/visita/costo/parametros', datos).then(r => r.data);
export const costoRoi = (vmId?: number) =>
  api.get<RoiResumen>('/visita/costo/roi', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);
export const costoRanking = () => api.get<RoiRanking>('/visita/costo/ranking').then(r => r.data);

// ── Costo & ROI — modelo financiero completo ──────────────────────────
export interface CostoEstructuraInput {
  ciclo_id?: number | null; linea_id?: number | null; moneda: string;
  salario_mensual: number; cargas_pct: number; viaticos_dia: number; materiales_ciclo: number;
  dias_campo: number; total_visitas: number; dias_mes: number;
  visitadores: number; visitas_ciclo_vm: number; ciclos_anio: number;
  coef_conservador: number; coef_optimista: number; psp_a: number; psp_b: number; psp_c: number;
  med_sin_visitar_a: number | null; med_sin_visitar_b: number | null; med_sin_visitar_c: number | null;
  configurado?: boolean;
}
export interface CostoProdInput {
  producto_id?: number | null; producto: string; orden?: number;
  costo_unitario_muestra: number; cantidad_muestras: number;
  pool_ventas: number; visitas_detalladas: number; presupuesto_anual: number; precio_prom: number;
}
// Respuesta completa (bloques calculados) — estructura flexible.
export interface CostoFull {
  ciclo_id: number; linea_id: number | null; moneda: string; configurado: boolean;
  estructura: CostoEstructuraInput;
  fijo: { costo_fijo_total: number; costo_fijo_dia: number; costo_fijo_visita: number; salario_ciclo: number; viaticos_total: number };
  muestras: { productos: { producto: string; costo_unitario: number; cantidad: number; total_ciclo: number }[]; total_muestras: number; costo_total_muestras: number; costo_variable_visita: number };
  pool: { productos: { producto: string; pool_ventas: number; visitas_detalladas: number; retorno_x_visita: number }[]; pool_total: number };
  plan_anual: { contactos_anio: number; contactos_anio_vm: number; presupuesto_total: number; presupuesto_por_vm: number; productiv_obj_contacto: number; productos: { producto: string; presupuesto_anual: number; precio_prom: number; productiv_obj_contacto: number; unidades_obj_contacto: number; cumplimiento_pct: number; retorno_real: number }[] };
  resumen: { costo_total_visita: number; retorno_prom_visita: number; roi_promedio: number | null; productos: { producto: string; costo_visita: number; retorno_visita: number; roi: number; estado: string }[] };
  impacto: { categorias: { categoria: string; medicos_sin_visitar: number; psp: number; venta_riesgo_bajo: number; venta_riesgo_alto: number }[]; venta_riesgo_bajo: number; venta_riesgo_alto: number; total_medicos_sin_visitar: number; headcount_equivalente: number };
}
export const costoEstructura = (cicloId?: number, lineaId?: number) =>
  api.get<CostoFull>('/visita/costo/estructura', { params: { ...(cicloId && { ciclo_id: cicloId }), ...(lineaId && { linea_id: lineaId }) } }).then(r => r.data);
export const guardarCostoEstructura = (datos: CostoEstructuraInput & { productos: CostoProdInput[] }) =>
  api.post<CostoFull>('/visita/costo/estructura', datos).then(r => r.data);
export const importarCostoExcel = (file: File, cicloId?: number, lineaId?: number) => {
  const fd = new FormData(); fd.append('archivo', file);
  return api.post<CostoFull & { importados: number }>('/visita/costo/importar', fd,
    { params: { ...(cicloId && { ciclo_id: cicloId }), ...(lineaId && { linea_id: lineaId }) }, headers: { 'Content-Type': 'multipart/form-data' } }).then(r => r.data);
};

// Devuelve { medico } si se creó, o { duplicados } si el backend respondió 409.
export const crearMedico = async (
  datos: MedicoCrear,
): Promise<{ medico?: MedicoVisita; duplicados?: PosibleDuplicado[] }> => {
  try {
    const r = await api.post<MedicoVisita>('/visita/medicos', datos);
    return { medico: r.data };
  } catch (e: unknown) {
    const resp = (e as { response?: { status?: number; data?: { detail?: { duplicados?: PosibleDuplicado[] } } } })?.response;
    if (resp?.status === 409) return { duplicados: resp.data?.detail?.duplicados ?? [] };
    throw e;
  }
};
