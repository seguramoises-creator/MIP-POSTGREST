/**
 * Los juegos de identidad disponibles: logotipo + colores de partida.
 *
 * POR QUÉ EXISTE. Los colores ya se guardaban por instalación, pero el logotipo
 * estaba escrito en el código (`import logoImg from '…/mallen-logo-blanco.svg'`)
 * en cuatro pantallas. El resultado: dos servidores con configuración de color
 * distinta seguían mostrando el mismo logotipo, porque comparten el paquete
 * compilado. Media centralización es peor que ninguna — parece que la identidad
 * se puede cambiar hasta que topas con la pieza que no.
 *
 * DOS ARCHIVOS POR IDENTIDAD, y no es duplicación: el logotipo va sobre las
 * barras oscuras (versión blanca) y sobre las pantallas claras de entrada
 * (versión a color). Un solo archivo obligaría a elegir cuál de los dos fondos
 * se ve mal.
 *
 * Los SVG viajan dentro del paquete en vez de servirse desde el servidor: pesan
 * poco, funcionan sin conexión —requisito de una PWA que se usa en la calle— y
 * evitan una petición más antes de poder pintar la pantalla de entrada.
 */
import * as fabrica from './marca';
import mallenBlanco from '../assets/mallen-logo-blanco.svg';
import mallenColor from '../assets/mallen-logo.svg';
import vistaLogo from '../assets/vista-logo.svg';

export interface Identidad {
  nombre: string;
  /** Sobre fondo OSCURO (barras superior e inferior). */
  logoBlanco: string;
  /** Sobre fondo CLARO (entrada, activación de cuenta). */
  logoColor: string;
  /** Color de acción de fábrica para esta identidad. */
  rojo: string;
  /** Color de estructura de fábrica para esta identidad. */
  taupe: string;
  /**
   * Tonos EXACTOS, cuando la identidad los tiene afinados a mano.
   *
   * `derivar()` calcula los tonos oscuros multiplicando el color de estructura
   * por factores fijos, y para un color arbitrario es lo correcto. Pero los de
   * Mallén salieron del vectorial del logotipo y se ajustaron uno a uno: el
   * cálculo los aproxima con 1-3 puntos de diferencia por canal. Imperceptible,
   * pero recalcular lo que alguien afinó a mano lo borra en silencio.
   *
   * Solo se usan mientras nadie haya cambiado los colores desde la pantalla de
   * Identidad visual; en cuanto hay colores propios, manda el cálculo.
   */
  exactos?: {
    rojoOscuro: string; rojoTenue: string; taupeMedio: string;
    taupeProfundo: string; taupeNegro: string; taupeClaro: string;
  };
}

export const IDENTIDADES: Record<string, Identidad> = {
  mallen: {
    nombre: 'Laboratorios Mallén',
    logoBlanco: mallenBlanco,
    logoColor: mallenColor,
    // Extraídos del vectorial del logotipo, no aproximados de la carta Pantone.
    rojo: '#F63440',   // Pantone Red 032 CP
    taupe: '#686158',  // Pantone 405 C
    // Los mismos valores que `marca.ts` define como fábrica: así la instalación
    // de Mallén se ve EXACTAMENTE igual que antes de que la identidad fuera
    // configurable, hasta el último punto de color.
    exactos: {
      rojoOscuro: fabrica.ROJO_OSCURO, rojoTenue: fabrica.ROJO_TENUE,
      taupeMedio: fabrica.TAUPE_MEDIO, taupeProfundo: fabrica.TAUPE_PROFUNDO,
      taupeNegro: fabrica.TAUPE_NEGRO, taupeClaro: fabrica.TAUPE_CLARO,
    },
  },
  vista: {
    nombre: 'VISTA',
    // El logotipo de VISTA es legible sobre ambos fondos, así que no necesita
    // dos versiones. Se repite la misma referencia en lugar de inventar un
    // archivo que no existe.
    logoBlanco: vistaLogo,
    logoColor: vistaLogo,
    // El azul marino original de VISTA, recuperado de `navTokens.ts` anterior al
    // rebrand (`#1a237e` y el degradado que arrancaba en `#0d1b4c`).
    rojo: '#1F6F8F',   // el acento turquesa del degradado original
    taupe: '#1A237E',  // azul marino: barras, superficies y texto fuerte
  },
};

/** La identidad por defecto cuando la instalación no ha elegido ninguna. */
export const IDENTIDAD_FABRICA = 'mallen';

export function identidad(nombre?: string | null): Identidad {
  return IDENTIDADES[(nombre || '').toLowerCase()] || IDENTIDADES[IDENTIDAD_FABRICA];
}
