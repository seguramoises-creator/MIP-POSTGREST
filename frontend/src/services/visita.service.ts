import { api } from './api';

export interface MedicoVisita {
  id: number;
  vm_id: number;
  nombre_completo: string;
  especialidad_id: number | null;
  especialidad_nombre: string | null;
  categoria: string;
  tipo_consultorio: string | null;
  direccion: string | null;
  telefono: string | null;
  ciclos_sin_visita: number;
  activo: boolean;
}

export interface MedicoCrear {
  vm_id: number;
  nombre_completo: string;
  especialidad_id?: number | null;
  categoria: string;
  tipo_consultorio?: string | null;
  direccion?: string | null;
  telefono?: string | null;
  confirmar_duplicado?: boolean;
}

export interface PosibleDuplicado {
  id: number; nombre_completo: string; direccion: string | null; palabras_coinciden: number;
}

export interface Catalogo { id: number; nombre: string; }

export const listarMedicos = (vmId?: number) =>
  api.get<MedicoVisita[]>('/visita/medicos', { params: vmId ? { vm_id: vmId } : {} }).then(r => r.data);

export const listarEspecialidades = () =>
  api.get<Catalogo[]>('/visita/especialidades').then(r => r.data);

export const listarVMs = () =>
  api.get<Catalogo[]>('/visita/vms').then(r => r.data);

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
