import { Box, MenuItem, Select, Chip, Typography, Paper } from '@mui/material';
import { LockOutlined } from '@mui/icons-material';
import { useCicloStore } from '../store/ciclo.store';

/** Encabezado del cuerpo de cada módulo (montado 1 vez en MainLayout).
 *  País: Select solo si el rol puede cambiar país; si no, texto fijo.
 *  Ciclo: Select con el ABIERTO por defecto; elegir otro pone el módulo en solo lectura. */
export default function CicloPaisHeader() {
  const {
    paisCodigo, cicloId, ciclosDisponibles, cicloAbiertoId,
    paisesDisponibles, puedeCambiarPais, esSoloLectura, setPais, setCicloVer,
  } = useCicloStore();

  if (!paisCodigo) return null;

  return (
    <Paper variant="outlined"
           sx={{ display: 'flex', alignItems: 'center', gap: 1.5, px: 2, py: 1, mb: 2, flexWrap: 'wrap' }}>
      <Typography variant="caption"
                  sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5 }}>
        País
      </Typography>
      {puedeCambiarPais && paisesDisponibles.length > 1 ? (
        <Select size="small" value={paisCodigo} onChange={(e) => setPais(e.target.value)} sx={{ minWidth: 90 }}>
          {paisesDisponibles.map((p) => <MenuItem key={p} value={p}>{p}</MenuItem>)}
        </Select>
      ) : (
        <Typography variant="body2" fontWeight={700}>{paisCodigo}</Typography>
      )}

      <Typography variant="caption"
                  sx={{ fontWeight: 700, textTransform: 'uppercase', color: 'text.secondary', letterSpacing: 0.5, ml: 1 }}>
        Ciclo
      </Typography>
      <Select size="small" value={cicloId ?? ''} onChange={(e) => setCicloVer(Number(e.target.value))}
              sx={{ minWidth: 170 }} displayEmpty>
        {ciclosDisponibles.map((c) => (
          <MenuItem key={c.id} value={c.id}>
            {(c.nombre_canonico || c.nombre)}{c.id === cicloAbiertoId ? ' · Abierto' : ''}
          </MenuItem>
        ))}
      </Select>

      {esSoloLectura
        ? <Chip size="small" color="warning" icon={<LockOutlined />} label="Solo lectura" />
        : <Chip size="small" color="success" label="Abierto · editable" />}
    </Paper>
  );
}
