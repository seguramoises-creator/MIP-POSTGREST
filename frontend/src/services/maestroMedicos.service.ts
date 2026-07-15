import { api } from './api';

export interface MaestroMedico {
  id: number; pais_codigo: string; nombre: string; codigo: string | null;
  cedula: string | null; exequatur: string | null; especialidad_id: number | null;
  telefono: string | null; email: string | null; direccion: string | null;
  provincia_id: number | null; municipio_id: number | null; centro_medico_id: number | null;
  sector: string | null; observaciones: string | null; activo: boolean;
  estado_validacion: string; origen: string;
}
export interface MaestroMedicoKpis {
  total: number; activos: number; nuevos_mes: number;
  sin_asignacion: number; pendientes_validacion: number;
}
export interface DuplicadoDetalle { tipo: 'duro' | 'blando'; mensaje: string; coincidencias: any[]; }

export const mmListar = (params: Record<string, any> = {}) =>
  api.get<MaestroMedico[]>('/medicos/maestro', { params }).then(r => r.data);
export const mmKpis = () => api.get<MaestroMedicoKpis>('/medicos/maestro/kpis').then(r => r.data);
export const mmObtener = (id: number) => api.get<MaestroMedico>(`/medicos/maestro/${id}`).then(r => r.data);
export const mmCrear = (p: Partial<MaestroMedico> & { pais_codigo: string; confirmar_duplicado?: boolean }) =>
  api.post<MaestroMedico>('/medicos/maestro', p).then(r => r.data);
export const mmActualizar = (id: number, p: Partial<MaestroMedico>) =>
  api.put<MaestroMedico>(`/medicos/maestro/${id}`, p).then(r => r.data);
