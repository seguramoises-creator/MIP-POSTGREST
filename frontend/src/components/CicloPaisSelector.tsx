import { useEffect } from 'react';
import { Box, MenuItem, Select, Chip, Typography } from '@mui/material';
import { useCicloStore } from '../store/ciclo.store';

export default function CicloPaisSelector() {
  const {
    paisCodigo, cicloId, ciclo, paisesDisponibles, ciclosDisponibles,
    puedeCambiarPais, init, setPais, setCiclo,
  } = useCicloStore();

  useEffect(() => { if (!paisCodigo) init().catch((e) => { console.error('CicloPaisSelector: init failed', e); }); }, [paisCodigo, init]);

  if (!paisCodigo) return null;

  return (
    <Box sx={{ display: 'flex', alignItems: 'center', gap: 1 }}>
      {puedeCambiarPais && paisesDisponibles.length > 1 && (
        <Select size="small" value={paisCodigo} onChange={(e) => setPais(e.target.value)}
                sx={{ minWidth: 90, bgcolor: 'background.paper' }}>
          {paisesDisponibles.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
        </Select>
      )}
      {!puedeCambiarPais && <Typography variant="body2" fontWeight={600}>{paisCodigo}</Typography>}
      <Select size="small" value={cicloId ?? ''} onChange={(e) => setCiclo(Number(e.target.value))}
              sx={{ minWidth: 150, bgcolor: 'background.paper' }} displayEmpty>
        {ciclosDisponibles.map((c) => (
          <MenuItem key={c.id} value={c.id}>{c.nombre_canonico || c.nombre}</MenuItem>
        ))}
      </Select>
      <Chip size="small" color={ciclo?.cerrado ? 'default' : 'success'}
            label={ciclo?.cerrado ? 'Cerrado' : 'Abierto'} />
    </Box>
  );
}
