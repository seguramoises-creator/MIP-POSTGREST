import { create } from 'zustand';
import { api } from '../services/api';

export type Ciclo = {
  id: number; nombre: string; nombre_canonico?: string;
  pais_codigo: string; anio: number; numero: number; cerrado: boolean;
  fecha_inicio?: string; fecha_fin?: string; dias_laborables?: number;
  estado?: 'PLANIFICADO' | 'VIGENTE' | 'POR_CERRAR' | 'CERRADO';
  vencido?: boolean;   // abierto pero con fecha fin ya pasada
};

const ROLES_MULTIPAIS = ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD'];

interface CicloState {
  paisCodigo: string | null;
  cicloId: number | null;          // ciclo EN CONSULTA (default = abierto)
  ciclo: Ciclo | null;
  cicloAbiertoId: number | null;   // ciclo ABIERTO (de trabajo) — único editable
  cicloAbierto: Ciclo | null;
  paisesDisponibles: string[];
  ciclosDisponibles: Ciclo[];
  puedeCambiarPais: boolean;
  esSoloLectura: boolean;          // cicloId !== cicloAbiertoId (o sin abierto)
  init: () => Promise<void>;
  setPais: (codigo: string) => Promise<void>;
  setCicloVer: (id: number) => void;
}

export const useCicloStore = create<CicloState>((set, get) => ({
  paisCodigo: null, cicloId: null, ciclo: null,
  cicloAbiertoId: null, cicloAbierto: null,
  paisesDisponibles: [], ciclosDisponibles: [], puedeCambiarPais: false,
  esSoloLectura: true,

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
    // País inicial: el propio del usuario; si no tiene (ADMIN), el país con operación/datos
    // (el de más RMs) para no arrancar en un país vacío; fallback: el primero de la lista.
    let inicial = me.pais_codigo || null;
    if (!inicial && multipais) {
      try { inicial = (await api.get('/admin/pais-defecto')).data as string | null; } catch { /* noop */ }
    }
    inicial = inicial || paises[0] || null;
    if (inicial) await get().setPais(inicial);
  },

  setPais: async (codigo) => {
    const ciclos = (await api.get(`/admin/ciclos?pais_codigo=${codigo}`)).data as Ciclo[];
    const actual = (await api.get(`/admin/ciclos/actual?pais_codigo=${codigo}`)).data as Ciclo | null;
    const abierto = actual || null;
    // El ciclo EN CONSULTA arranca en el abierto; si no hay abierto, en el último de la lista.
    const verInicial = abierto || ciclos[ciclos.length - 1] || null;
    set({
      paisCodigo: codigo,
      ciclosDisponibles: ciclos,
      cicloAbierto: abierto,
      cicloAbiertoId: abierto ? abierto.id : null,
      ciclo: verInicial,
      cicloId: verInicial ? verInicial.id : null,
      esSoloLectura: !abierto || !verInicial || verInicial.id !== abierto.id,
    });
  },

  setCicloVer: (id) => {
    const c = get().ciclosDisponibles.find((x) => x.id === id) || null;
    const abiertoId = get().cicloAbiertoId;
    set({ cicloId: id, ciclo: c, esSoloLectura: abiertoId == null || id !== abiertoId });
  },
}));
