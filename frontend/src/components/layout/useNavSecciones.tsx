/**
 * Convierte NAV_SECTIONS (el menú agrupado que ya existía) en los DESTINOS de la
 * barra inferior, filtrando por permisos.
 *
 * Por qué se derivan y no se escriben a mano: la barra inferior tiene 5 ranuras y
 * la app tiene ~30 rutas, así que la tentación es fijar 5 destinos "importantes".
 * Sería un segundo mapa que hay que mantener sincronizado con el de permisos, y
 * que para un representante —que ve 6 de esas 30 rutas— mostraría destinos vacíos.
 * Derivándolos, cada usuario ve exactamente las secciones donde tiene algo.
 */
import { useMemo } from 'react';

import {
  Home, Today, FolderShared, Leaderboard, School, Storage, Settings,
} from '@mui/icons-material';

import { NAV_SECTIONS, type NavItem } from './Sidebar';
import { usePuedeVerItem } from './navVisibilidad';

export interface Destino {
  /** Título de la sección en NAV_SECTIONS; null = el home (Dashboard). */
  titulo: string | null;
  /** Etiqueta corta para la barra: debe caber en una ranura de ~72 px. */
  etiqueta: string;
  icono: React.ReactNode;
  /** Ítems visibles de la sección — son las pestañas superiores. */
  items: NavItem[];
}

// Etiqueta corta + icono por sección. Las etiquetas del menú lateral ("Maestros y
// planeación", "Desempeño y análisis") no caben en una ranura, así que se acortan
// a una palabra, que es lo que hace la referencia.
const META: Record<string, { etiqueta: string; icono: React.ReactNode }> = {
  'Operación diaria':      { etiqueta: 'Operación',  icono: <Today /> },
  'Maestros y planeación': { etiqueta: 'Maestros',   icono: <FolderShared /> },
  'Desempeño y análisis':  { etiqueta: 'Desempeño',  icono: <Leaderboard /> },
  'Formación':             { etiqueta: 'Formación',  icono: <School /> },
  'Datos':                 { etiqueta: 'Datos',      icono: <Storage /> },
  'Sistema':               { etiqueta: 'Sistema',    icono: <Settings /> },
};

export function useNavSecciones(): Destino[] {
  const puedeVer = usePuedeVerItem();

  return useMemo(() => {
    const out: Destino[] = [];
    for (const s of NAV_SECTIONS) {
      const items = s.items.filter(puedeVer);
      if (items.length === 0) continue;          // sección sin nada visible: no es un destino
      if (s.title === null) {
        out.push({ titulo: null, etiqueta: 'Inicio', icono: <Home />, items });
      } else {
        const meta = META[s.title];
        if (!meta) continue;                     // sección nueva sin icono: mejor omitirla que romper
        out.push({ titulo: s.title, etiqueta: meta.etiqueta, icono: meta.icono, items });
      }
    }
    return out;
  }, [puedeVer]);
}
