/**
 * Regla ÚNICA de visibilidad de un ítem de navegación.
 *
 * Vive aparte porque ahora la consumen dos superficies —la barra inferior y las
 * pestañas superiores—, y una regla de permisos duplicada es una regla que
 * termina divergiendo: bastaría con tocar una copia para que un módulo quedara
 * visible en un lado y oculto en el otro.
 */
import { useCallback } from 'react';

import { useAuthStore } from '../../store/auth.store';
import { usePuede } from '../../store/permisos.store';
import type { NavItem } from './Sidebar';

export function usePuedeVerItem() {
  const { rol } = useAuthStore();
  const puedePerm = usePuede();

  // Si el ítem está en la matriz RBAC, la decide la matriz. Mientras los permisos
  // no han cargado (`puedePerm` devuelve null) o si el módulo no está en la matriz,
  // se cae al gate por rol — mismo criterio que tenía el menú lateral.
  return useCallback((item: NavItem) => {
    if (item.recurso) {
      const p = puedePerm(item.recurso, item.accion ?? 'read');
      if (p !== null) return p;
    }
    return !!rol && item.roles.includes(rol);
  }, [rol, puedePerm]);
}
