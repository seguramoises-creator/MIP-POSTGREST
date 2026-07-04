import { create } from 'zustand';
import { api } from '../services/api';

export type Ciclo = {
  id: number; nombre: string; nombre_canonico?: string;
  pais_codigo: string; anio: number; numero: number; cerrado: boolean;
};

const ROLES_MULTIPAIS = ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'];

interface CicloState {
  paisCodigo: string | null;
  cicloId: number | null;
  ciclo: Ciclo | null;
  paisesDisponibles: string[];
  ciclosDisponibles: Ciclo[];
  puedeCambiarPais: boolean;
  init: () => Promise<void>;
  setPais: (codigo: string) => Promise<void>;
  setCiclo: (id: number) => void;
}

export const useCicloStore = create<CicloState>((set, get) => ({
  paisCodigo: null, cicloId: null, ciclo: null,
  paisesDisponibles: [], ciclosDisponibles: [], puedeCambiarPais: false,

  init: async () => {
    const me = (await api.get('/auth/me')).data as { pais_codigo?: string; rol: string };
    const multipais = ROLES_MULTIPAIS.includes(me.rol);
    let paises: string[];
    if (multipais) {
      const rows = (await api.get('/admin/paises')).data as { codigo: string }[];
      paises = rows.map((p) => p.codigo);
    } else {
      paises = me.pais_codigo ? [me.pais_codigo] : [];
    }
    set({ puedeCambiarPais: multipais, paisesDisponibles: paises });
    const inicial = me.pais_codigo || paises[0] || null;
    if (inicial) await get().setPais(inicial);
  },

  setPais: async (codigo) => {
    const ciclos = (await api.get(`/admin/ciclos?pais_codigo=${codigo}`)).data as Ciclo[];
    const actual = (await api.get(`/admin/ciclos/actual?pais_codigo=${codigo}`)).data as Ciclo | null;
    const elegido = actual || ciclos[ciclos.length - 1] || null;
    set({ paisCodigo: codigo, ciclosDisponibles: ciclos, ciclo: elegido, cicloId: elegido ? elegido.id : null });
  },

  setCiclo: (id) => {
    const c = get().ciclosDisponibles.find((x) => x.id === id) || null;
    set({ cicloId: id, ciclo: c });
  },
}));
