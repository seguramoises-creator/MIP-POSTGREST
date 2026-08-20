import { BORDE_SUAVE, NEUTRO_600 } from '../../theme/marca';
// Requerimiento Mallén (Item 6): esquema de color por categoría médica, único para toda la
// suite de Visita. A=Verde · B=Azul · C=Amarillo · D=Rojo.
export const CAT_AV: Record<string, { bg: string; fg: string }> = {
  A: { bg: '#DCF3E3', fg: '#1B7A3E' }, // Verde
  B: { bg: '#D6E4FF', fg: '#1E52C7' }, // Azul
  C: { bg: '#FFF1C2', fg: '#8A6D0B' }, // Amarillo
  D: { bg: '#F8D5D5', fg: '#B23B3B' }, // Rojo
};

// `sx` listo para un <Chip>/<Avatar> con la categoría (fallback gris si viene vacía/desconocida).
export const catChipSx = (categoria?: string | null) => {
  const c = CAT_AV[(categoria || '').toUpperCase()] ?? { bg: BORDE_SUAVE, fg: NEUTRO_600 };
  return { bgcolor: c.bg, color: c.fg, fontWeight: 700 };
};
