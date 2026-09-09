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
/*
 * VISTA TIENE DOS ARCHIVOS, y cada uno sirve para un fondo — igual que Mallén.
 *
 * El `.svg` nunca fue un vectorial: lleva un JPEG incrustado, o sea un RECTÁNGULO
 * con su propio fondo azul y una moldura dibujada. Ese fondo no es plano (medido:
 * de `#001834` en las esquinas a `#042A64` en el centro), así que sobre las barras
 * y sobre la tarjeta de entrada el logotipo se veía montado en su propia placa, con
 * relieve, y ningún color de superficie lo tapaba.
 *
 * El PNG sale de ese mismo JPEG sin el fondo: el dibujo es claro sobre oscuro, así
 * que se estima el fondo con un desenfoque fuerte, se resta, y lo que sobresale del
 * ruido es el dibujo; la opacidad viene de esa diferencia con una rampa suave para
 * no dentar los bordes, y se recortan la moldura y el aire sobrante.
 *
 * Pero el dibujo es CLARO: sobre una superficie blanca desaparecería. Por eso el
 * PNG es el de fondo oscuro y el `.svg` original —que trae su propia placa— sigue
 * siendo el de fondo claro, donde esa placa es justo lo que lo hace legible. Con un
 * vectorial de verdad, uno solo bastaría para los dos.
 */
import vistaBlanco from '../assets/vista-logo.png';
import vistaColor from '../assets/vista-logo.svg';

export interface Identidad {
  nombre: string;
  /** Sobre fondo OSCURO (barras superior e inferior, tarjeta de entrada). */
  logoBlanco: string;
  /** Sobre fondo CLARO (activación de cuenta, pantalla de Identidad visual). */
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
    // Ver la nota de los imports: el PNG sin fondo va sobre lo oscuro; el archivo
    // original, que trae su propia placa azul, va sobre lo claro.
    logoBlanco: vistaBlanco,
    logoColor: vistaColor,
    // El azul marino original de VISTA, recuperado de `navTokens.ts` anterior al
    // rebrand (`#1a237e` y el degradado que arrancaba en `#0d1b4c`).
    // Azul de acción MEDIDO sobre el propio logotipo (#0050B4 es uno de sus tonos
    // luminosos). El turquesa anterior venía del degradado viejo y no era un color
    // de VISTA: se veía prestado junto al azul de la marca.
    rojo: '#0050B4',
    taupe: '#1A237E',  // azul marino: barras, superficies y texto fuerte
    /**
     * Tonos exactos, y aquí hay un motivo concreto además del habitual.
     *
     * `taupeProfundo` —el 0% del degradado, justo debajo del logotipo— es el azul
     * que traía el fondo del archivo original (`#011D42`). Nació para que el
     * extremo izquierdo de la barra valiera lo mismo que ese fondo y no se viera
     * el corte del recuadro; ahora el logotipo tiene transparencia y ya no hace
     * falta igualar nada, pero el tono se queda: es el arranque afinado del
     * degradado, y recalcularlo daba `#0F1447`, que ensucia el azul.
     */
    exactos: {
      rojoOscuro: '#003C87',    // azul oscurecido: enlaces y texto sobre blanco
      /**
       * Aquí `rojoTenue` NO es un fondo pálido como en Mallén: es el azul de
       * acción ACLARADO, para el botón que se apoya sobre el degradado oscuro
       * de la pantalla de entrada.
       *
       * Medido: el azul de marca (#0050B4) sobre esa tarjeta da 2.24:1 — por
       * debajo del 3:1 que WCAG 1.4.11 exige a un elemento gráfico, así que el
       * botón se difuminaría en el fondo. Este tono da 3.42:1 contra la tarjeta
       * y 4.88:1 con su texto blanco encima.
       */
      rojoTenue: '#2E6FD0',
      taupeProfundo: '#011D42', // 0% del degradado — el fondo del propio logotipo
      taupeMedio: '#0D1F60',    // 55% — tránsito hacia el azul de marca
      taupeNegro: '#00122C',    // arranque del degradado de la pantalla de entrada
      taupeClaro: '#2E3894',    // bordes y acentos sobre fondo oscuro
    },
  },
};

/** La identidad por defecto cuando la instalación no ha elegido ninguna. */
export const IDENTIDAD_FABRICA = 'mallen';

export function identidad(nombre?: string | null): Identidad {
  return IDENTIDADES[(nombre || '').toLowerCase()] || IDENTIDADES[IDENTIDAD_FABRICA];
}
