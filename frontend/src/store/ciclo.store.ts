import { create } from 'zustand';
import { api } from '../services/api';

export type Ciclo = {
  id: number; nombre: string; nombre_canonico?: string;
  pais_codigo: string; anio: number; numero: number; cerrado: boolean;
  fecha_inicio?: string; fecha_fin?: string; dias_laborables?: number;
  estado?: 'PLANIFICADO' | 'VIGENTE' | 'POR_CERRAR' | 'CERRADO';
  vencido?: boolean;   // abierto pero con fecha fin ya pasada
};

// Roles con visión de todos los países (incluye los de LECTURA TOTAL, que si no tienen país
// propio se quedaban en blanco). Arrancan en el país con operación (pais-defecto).
const ROLES_MULTIPAIS = ['ADMIN', 'PRESIDENCIA', 'DIR_COMERCIAL', 'GERENTE_PRODUCTIVIDAD',
  'ANALISTA_DATOS', 'CONSULTA'];
// Roles de solo lectura/observación: arrancan en el ÚLTIMO ciclo CON DATOS (no en el abierto,
// que puede estar vacío) para no mostrar páginas en blanco.
const ROLES_VER_ULTIMO_DATO = ['CONSULTA', 'ANALISTA_DATOS', 'DIR_COMERCIAL', 'PRESIDENCIA',
  'GERENTE_MARKETING', 'GERENTE_MEDICO'];

interface CicloState {
  rol: string | null;
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
  rol: null,
  paisCodigo: null, cicloId: null, ciclo: null,
  cicloAbiertoId: null, cicloAbierto: null,
  paisesDisponibles: [], ciclosDisponibles: [], puedeCambiarPais: false,
  esSoloLectura: true,

  init: async () => {
    const me = (await api.get('/auth/me')).data as { pais_codigo?: string; rol: string };
    set({ rol: me.rol });
    const multipais = ROLES_MULTIPAIS.includes(me.rol);
    let paises: string[];
    if (multipais) {
      // Defensa: si por RBAC no pudiera listar países, no abortar el init — el fallback de
      // país-defecto de más abajo igual resuelve un país para no dejar todo en blanco.
      try {
        const rows = (await api.get('/admin/paises')).data as { codigo: string }[];
        paises = rows.map((p) => p.codigo);
      } catch { paises = []; }
    } else {
      paises = me.pais_codigo ? [me.pais_codigo] : [];
    }
    // País inicial: el propio del usuario; si no tiene, el país con operación/datos (el de más
    // RMs) para no arrancar en un país vacío; fallback: el primero de la lista. Esto aplica
    // TAMBIÉN a roles de solo lectura sin país propio y fuera de ROLES_MULTIPAIS — antes se
    // quedaban en `paises=[]` y nunca se fijaba país, dejando TODAS las pantallas en blanco.
    let inicial = me.pais_codigo || null;
    if (!inicial) {
      try { inicial = (await api.get('/admin/pais-defecto')).data as string | null; } catch { /* noop */ }
    }
    inicial = inicial || paises[0] || null;
    // Si el rol no expone lista de países pero resolvimos uno, publícalo para que los
    // selectores/KPIs tengan contexto (aunque no pueda cambiarlo).
    if (inicial && paises.length === 0) paises = [inicial];
    set({ puedeCambiarPais: multipais, paisesDisponibles: paises });
    if (inicial) await get().setPais(inicial);
  },

  setPais: async (codigo) => {
    const ciclos = (await api.get(`/admin/ciclos?pais_codigo=${codigo}`)).data as Ciclo[];
    const actual = (await api.get(`/admin/ciclos/actual?pais_codigo=${codigo}`)).data as Ciclo | null;
    const abierto = actual || null;
    // El ciclo EN CONSULTA arranca en el abierto; si no hay abierto, en el último de la lista.
    let verInicial = abierto || ciclos[ciclos.length - 1] || null;
    // Roles de solo lectura: arrancan en el ÚLTIMO ciclo CON DATOS (aunque esté cerrado), para no
    // caer en un ciclo abierto todavía vacío. Si el abierto ya tiene datos, ese es el más reciente.
    if (ROLES_VER_ULTIMO_DATO.includes(get().rol || '')) {
      try {
        const ult = (await api.get(`/admin/ciclos/ultimo-con-datos?pais_codigo=${codigo}`)).data as Ciclo | null;
        if (ult) verInicial = ciclos.find((c) => c.id === ult.id) || ult;
      } catch { /* sin dato → queda el default */ }
    }
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
