/**
 * MiRuta.tsx — La ruta de formación del representante (§4).
 * Descubre su asignación con `mis-asignaciones` (auto-scope por rm_id) y luego
 * consulta el estado detallado con sus bloqueos.
 */
import { useEffect, useState } from 'react';
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import {
  Box, Alert, CircularProgress, FormControl, InputLabel, Select, MenuItem, Snackbar,
} from '@mui/material';
import {
  misAsignaciones, estadoRuta, completarPaso,
} from '../../../services/onboarding.service';
import ListaPasos from './ListaPasos';

// Motivo real de un error de axios: 422 de FastAPI (detail = [{loc,msg}]) o string.
function detalleError(e: unknown, fallback: string): string {
  const d = (e as { response?: { data?: { detail?: unknown } } })?.response?.data?.detail;
  if (typeof d === 'string' && d.trim()) return d;
  if (Array.isArray(d) && d[0]) {
    const m = (d[0] as { msg?: string }).msg;
    if (m) return m.replace('Value error, ', '');
  }
  return fallback;
}

export default function MiRuta() {
  const qc = useQueryClient();
  const [sel, setSel] = useState<number | null>(null);
  const [aviso, setAviso] = useState<{ sev: 'success' | 'warning' | 'error'; msg: string } | null>(null);

  const asignaciones = useQuery({ queryKey: ['onb-mis-asignaciones'], queryFn: misAsignaciones });

  // Al llegar la lista, abre la más reciente (el backend las ordena desc).
  useEffect(() => {
    if (sel === null && asignaciones.data && asignaciones.data.length > 0) {
      setSel(asignaciones.data[0].id);
    }
  }, [asignaciones.data, sel]);

  const ruta = useQuery({
    queryKey: ['onb-estado-ruta', sel],
    queryFn: () => estadoRuta(sel as number),
    enabled: sel !== null,
  });

  const completar = useMutation({
    mutationFn: (pasoId: number) => completarPaso(sel as number, pasoId),
    onSuccess: () => {
      setAviso({ sev: 'success', msg: 'Paso completado.' });
      qc.invalidateQueries({ queryKey: ['onb-estado-ruta', sel] });
      qc.invalidateQueries({ queryKey: ['onb-mis-asignaciones'] });
    },
    // 403 = no te toca marcarlo (§4.6); 409 = todavía está bloqueado. En ambos
    // casos el backend manda el motivo exacto: se muestra tal cual.
    onError: (e) => setAviso({ sev: 'warning', msg: detalleError(e, 'No se pudo completar el paso.') }),
  });

  if (asignaciones.isLoading) return <CircularProgress />;
  if (asignaciones.isError) {
    return <Alert severity="warning">
      {detalleError(asignaciones.error,
        'No se pudo cargar tu ruta. Si tu usuario no está enlazado a un representante, pídele a un administrador que lo enlace.')}
    </Alert>;
  }

  const lista = asignaciones.data || [];
  if (lista.length === 0) {
    return <Alert severity="info">Aún no tienes una ruta de formación asignada.</Alert>;
  }

  return (
    <Box>
      {lista.length > 1 && (
        <FormControl sx={{ mb: 2, minWidth: 280 }} size="small">
          <InputLabel>Ruta</InputLabel>
          <Select label="Ruta" value={sel ?? ''} onChange={(e) => setSel(Number(e.target.value))}>
            {lista.map((a) => (
              <MenuItem key={a.id} value={a.id}>
                {a.nombre_plantilla} — desde {a.fecha_inicio}
              </MenuItem>
            ))}
          </Select>
        </FormControl>
      )}

      {ruta.isLoading && <CircularProgress />}
      {ruta.isError && <Alert severity="warning">No se pudo cargar el detalle de la ruta.</Alert>}
      {ruta.data && (
        <ListaPasos estado={ruta.data}
          onCompletar={(pasoId) => completar.mutate(pasoId)}
          completando={completar.isPending ? (completar.variables as number) : null} />
      )}

      <Snackbar open={!!aviso} autoHideDuration={8000} onClose={() => setAviso(null)}
        anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
        {aviso ? <Alert severity={aviso.sev} onClose={() => setAviso(null)}>{aviso.msg}</Alert> : undefined}
      </Snackbar>
    </Box>
  );
}
