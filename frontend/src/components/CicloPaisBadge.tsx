import { useEffect } from 'react';
import { Box, Typography } from '@mui/material';
import { useCicloStore } from '../store/ciclo.store';
import { SUPERFICIE_3, TAUPE_NEGRO } from '../theme/marca';

/** Barra superior: informativa (píldora compacta de una sola línea). Muestra el
 *  país y el CICLO ABIERTO. No permite seleccionar — el cambio vive en CicloPaisHeader.
 *  Responsive: en móvil se reduce a "DO ●" (país + punto de estado); en pantallas
 *  más anchas agrega el nombre del ciclo y la palabra "Abierto". Nunca se parte. */
export default function CicloPaisBadge() {
  const { paisCodigo, cicloAbierto, init } = useCicloStore();
  useEffect(() => {
    if (!paisCodigo) init().catch((e) => console.error('CicloPaisBadge: init failed', e));
  }, [paisCodigo, init]);

  if (!paisCodigo) return null;

  const abierto = !!cicloAbierto;
  const nombre = abierto ? (cicloAbierto!.nombre_canonico || cicloAbierto!.nombre) : 'Sin ciclo';

  return (
    <Box sx={{
      display: 'flex', alignItems: 'center', gap: 0.75, whiteSpace: 'nowrap',
      px: 1, py: 0.4, borderRadius: 5, bgcolor: SUPERFICIE_3, border: '1px solid #E0DAD3',
    }}>
      <Typography variant="caption" sx={{ fontWeight: 800, color: TAUPE_NEGRO, lineHeight: 1 }}>{paisCodigo}</Typography>

      {/* Nombre del ciclo — oculto en móvil para no saturar */}
      <Typography variant="caption" sx={{ color: 'text.secondary', lineHeight: 1, display: { xs: 'none', sm: 'inline' } }}>
        {nombre}
      </Typography>

      {/* Punto de estado (siempre visible) + palabra "Abierto" (solo pantallas anchas) */}
      <Box sx={{ width: 8, height: 8, borderRadius: '50%', bgcolor: abierto ? '#16a34a' : '#94a3b8', flexShrink: 0 }} />
      <Typography variant="caption" sx={{ fontWeight: 700, lineHeight: 1,
                                          color: abierto ? '#15803d' : '#64748b', display: { xs: 'none', md: 'inline' } }}>
        {abierto ? 'Abierto' : '—'}
      </Typography>
    </Box>
  );
}
