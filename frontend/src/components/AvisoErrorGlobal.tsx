/**
 * AvisoErrorGlobal — muestra un aviso amigable cuando ocurre un error de servidor (500+) o de red.
 * Escucha el evento `app:error-servidor` que dispara el interceptor de axios, busca el error en la
 * Matriz de Errores (Config.DIM_CatalogoError) por su código HTTP y muestra código + descripción +
 * solución. Los errores 4xx (400/403/409) ya traen su mensaje específico en cada pantalla.
 */
import { useEffect, useState } from 'react';
import { Snackbar, Alert, AlertTitle, Typography } from '@mui/material';
import { useQuery } from '@tanstack/react-query';
import { api } from '../services/api';

interface ErrorCat {
  codigo: string; titulo: string; descripcion?: string | null; solucion?: string | null;
  http_status?: number | null; activo: boolean;
}
type DetalleEvento = { status: number; detalle?: unknown };

export default function AvisoErrorGlobal() {
  const [aviso, setAviso] = useState<{ codigo?: string; titulo: string; texto: string } | null>(null);

  // La Matriz de Errores (se puede leer autenticado). Cache generoso: cambia poco.
  const { data: catalogo } = useQuery({
    queryKey: ['catalogo-errores'],
    queryFn: () => api.get<ErrorCat[]>('/admin/catalogo-errores').then((r) => r.data),
    staleTime: 5 * 60 * 1000, retry: 1,
    enabled: !!localStorage.getItem('access_token'),
  });

  useEffect(() => {
    const handler = (ev: Event) => {
      const { status, detalle } = (ev as CustomEvent<DetalleEvento>).detail || { status: 0 };
      const cat = (Array.isArray(catalogo) ? catalogo : [])
        .find((e) => e.http_status === status && e.activo)
        // sin http_status coincidente, cae al genérico de sistema
        || (Array.isArray(catalogo) ? catalogo : []).find((e) => e.codigo === 'SYS-500');
      const partes = [
        typeof detalle === 'string' && detalle ? detalle : null,
        cat?.descripcion || null,
        cat?.solucion ? `Qué hacer: ${cat.solucion}` : null,
      ].filter(Boolean);
      setAviso({
        codigo: cat?.codigo,
        titulo: cat?.titulo || 'Error del sistema',
        texto: partes.join(' — ') || 'Ocurrió un error inesperado. Reintenta; si persiste, reporta al equipo.',
      });
    };
    window.addEventListener('app:error-servidor', handler);
    return () => window.removeEventListener('app:error-servidor', handler);
  }, [catalogo]);

  return (
    <Snackbar open={!!aviso} autoHideDuration={8000} onClose={() => setAviso(null)}
      anchorOrigin={{ vertical: 'bottom', horizontal: 'center' }}>
      <Alert severity="error" variant="filled" onClose={() => setAviso(null)} sx={{ maxWidth: 520 }}>
        <AlertTitle sx={{ mb: 0.3 }}>
          {aviso?.titulo}{aviso?.codigo ? <Typography component="span" variant="caption" sx={{ ml: 1, opacity: 0.85 }}>[{aviso.codigo}]</Typography> : null}
        </AlertTitle>
        {aviso?.texto}
      </Alert>
    </Snackbar>
  );
}
