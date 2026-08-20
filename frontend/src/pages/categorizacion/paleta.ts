import { AVISO, AVISO_OSCURO, AVISO_TENUE, BORDE_SUAVE, EXITO_MEDIO, EXITO_OSCURO, EXITO_TENUE, NEUTRO_700, NEUTRO_900, SUPERFICIE_4, TAUPE, TAUPE_PROFUNDO } from '../../theme/marca';
/**
 * Paleta A/B/C/D compartida por las vistas de categorización.
 * A = Teal esmeralda · B = Azul zafiro · C = Ámbar dorado · D = Gris acero
 */
export const CAT_PAL: Record<string, { dark: string; mid: string; light: string; text: string }> = {
  A: { dark: EXITO_OSCURO, mid: EXITO_MEDIO, light: EXITO_TENUE, text: '#fff' },
  B: { dark: TAUPE, mid: TAUPE_PROFUNDO, light: SUPERFICIE_4, text: '#fff' },
  C: { dark: AVISO, mid: AVISO_OSCURO, light: AVISO_TENUE, text: '#fff' },
  D: { dark: NEUTRO_900, mid: NEUTRO_700, light: BORDE_SUAVE, text: '#fff' },
};

export const CATS = ['A', 'B', 'C', 'D'] as const;
