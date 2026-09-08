import { AVISO, AVISO_OSCURO, AVISO_TENUE, BORDE_SUAVE, EXITO_MEDIO, EXITO_OSCURO, EXITO_TENUE, NEUTRO_700, NEUTRO_900, SUPERFICIE_4 } from '../../theme/marca';
import { marcaViva } from '../../theme/marcaViva';
/**
 * Paleta A/B/C/D compartida por las vistas de categorización.
 * A = Teal esmeralda · B = Azul zafiro · C = Ámbar dorado · D = Gris acero
 */
// Función y no constante: en ámbito de módulo el color se copiaría antes de que
// `cargarMarca()` traiga la identidad, y quedaría congelado en el de fábrica.
export const catPal = (): Record<string, { dark: string; mid: string; light: string; text: string }> => ({
  A: { dark: EXITO_OSCURO, mid: EXITO_MEDIO, light: EXITO_TENUE, text: '#fff' },
  B: { dark: marcaViva.taupe, mid: marcaViva.taupeProfundo, light: SUPERFICIE_4, text: '#fff' },
  C: { dark: AVISO, mid: AVISO_OSCURO, light: AVISO_TENUE, text: '#fff' },
  D: { dark: NEUTRO_900, mid: NEUTRO_700, light: BORDE_SUAVE, text: '#fff' },
});

export const CATS = ['A', 'B', 'C', 'D'] as const;
