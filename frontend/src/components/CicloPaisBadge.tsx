import { useEffect } from 'react';
import { Box, Chip, Typography } from '@mui/material';
import { useCicloStore } from '../store/ciclo.store';

/** Barra superior: informativa. Muestra el país y el CICLO ABIERTO (de trabajo).
 *  No permite seleccionar — el cambio de ciclo/país vive en CicloPaisHeader. */
export default function CicloPaisBadge() {
  const { paisCodigo, cicloAbierto, init } = useCicloStore();
  useEffect(() => {
    if (!paisCodigo) init().catch((e) => console.error('CicloPaisBadge: init failed', e));
  }, [paisCodigo, init]);

  if (!paisCodigo) return null;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      <Typography variant="body2" fontWeight={700}>{paisCodigo}</Typography>
      <Typography variant="body2" color="text.secondary">
        {cicloAbierto ? (cicloAbierto.nombre_canonico || cicloAbierto.nombre) : 'Sin ciclo abierto'}
      </Typography>
      <Chip size="small" color={cicloAbierto ? 'success' : 'default'}
            label={cicloAbierto ? 'Abierto' : '—'} />
    </Box>
  );
}
