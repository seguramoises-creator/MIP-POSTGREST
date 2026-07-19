/**
 * Contrato de autorización del frontend (RBAC Fase 2).
 *
 * Carga UNA vez `/authz/me/permisos` (capacidades efectivas del usuario, derivadas de la matriz
 * del backend) y expone `puede(recurso, accion)`. La navegación, las rutas y los controles deben
 * derivar de aquí — no de listas de rol hardcodeadas.
 *
 * `puede` devuelve `null` mientras los permisos aún no se cargan, para que los consumidores puedan
 * hacer *fallback* por rol y no parpadear/romper durante el fetch inicial.
 */
import { create } from 'zustand';
import { api } from '../services/api';

type Permisos = Record<string, Record<string, string>>;  // recurso -> {accion: alcance}

interface PermisosState {
  permisos: Permisos | null;
  cargando: boolean;
  /** true una vez que se INTENTÓ cargar (con éxito o error). Distingue "aún no cargó" de
   *  "cargó y falló" — evita el falso /sin-acceso al refrescar y el spinner infinito si el backend cae. */
  intentado: boolean;
  cargar: () => Promise<void>;
  /** true/false si ya cargó; null si todavía no (para fallback por rol). */
  puede: (recurso: string, accion?: string) => boolean | null;
  /** alcance concedido ('own'|'team'|'all') o null. */
  alcance: (recurso: string, accion?: string) => string | null;
  reset: () => void;
}

/**
 * Hook para gatear en componentes. SUSCRIBE a `permisos`, así el componente se re-renderiza
 * cuando los permisos terminan de cargar (seleccionar `s.puede` directamente NO re-renderiza,
 * porque la función es estable). Devuelve null mientras no cargan → fallback por rol en el caller.
 */
export function usePuede() {
  const permisos = usePermisosStore((s) => s.permisos);
  return (recurso: string, accion: string = 'read'): boolean | null =>
    permisos === null ? null : Boolean(permisos[recurso] && permisos[recurso][accion]);
}

export const usePermisosStore = create<PermisosState>((set, get) => ({
  permisos: null,
  cargando: false,
  intentado: false,
  cargar: async () => {
    if (get().cargando) return;
    set({ cargando: true });
    try {
      const { data } = await api.get('/authz/me/permisos');
      set({ permisos: data.permisos ?? {}, cargando: false, intentado: true });
    } catch {
      // Ante fallo, dejamos permisos=null pero marcamos intentado → los consumidores caen a
      // fallback por rol (no quedan esperando para siempre).
      set({ cargando: false, intentado: true });
    }
  },
  puede: (recurso, accion = 'read') => {
    const p = get().permisos;
    if (p === null) return null;
    return Boolean(p[recurso] && p[recurso][accion]);
  },
  alcance: (recurso, accion = 'read') => {
    const p = get().permisos;
    if (p === null) return null;
    return (p[recurso] && p[recurso][accion]) || null;
  },
  reset: () => set({ permisos: null, cargando: false, intentado: false }),
}));
