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
import { esIntegrada } from '../../config/instalacion';

export function usePuedeVerItem() {
  const { rol } = useAuthStore();
  const puedePerm = usePuede();

  // Si el ítem está en la matriz RBAC, la decide la matriz. Mientras los permisos
  // no han cargado (`puedePerm` devuelve null) o si el módulo no está en la matriz,
  // se cae al gate por rol — mismo criterio que tenía el menú lateral.
  return useCallback((item: NavItem) => {
    // Antes que el permiso: si la instalación está integrada, la pantalla de
    // carga por Excel no existe para nadie, ni siquiera para el ADMIN. No es una
    // restricción de acceso — es que ahí los datos entran por otra puerta.
    if (item.soloSinIntegracion && esIntegrada()) return false;
    if (item.recurso) {
      const p = puedePerm(item.recurso, item.accion ?? 'read');
      if (p !== null) return p;
    }
    return !!rol && item.roles.includes(rol);
  }, [rol, puedePerm]);
}
