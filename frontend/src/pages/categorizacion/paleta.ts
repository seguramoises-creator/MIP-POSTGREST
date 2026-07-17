/**
 * Paleta A/B/C/D compartida por las vistas de categorización.
 * A = Teal esmeralda · B = Azul zafiro · C = Ámbar dorado · D = Gris acero
 */
export const CAT_PAL: Record<string, { dark: string; mid: string; light: string; text: string }> = {
  A: { dark: '#00695c', mid: '#00897b', light: '#e0f2f1', text: '#fff' },
  B: { dark: '#1a237e', mid: '#283593', light: '#e8eaf6', text: '#fff' },
  C: { dark: '#e65100', mid: '#ef6c00', light: '#fff3e0', text: '#fff' },
  D: { dark: '#37474f', mid: '#455a64', light: '#eceff1', text: '#fff' },
};

export const CATS = ['A', 'B', 'C', 'D'] as const;
