import { useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { Box, CircularProgress } from '@mui/material';
import { useAuthStore } from '../../store/auth.store';
import { usePermisosStore } from '../../store/permisos.store';
import { Rol } from '../../types';

interface Props {
  children: React.ReactNode;
  allowedRoles?: Rol[];
  /** Recurso de la matriz RBAC. Si se define, el acceso lo decide /authz/me/permisos.
   *  Mientras los permisos NO han cargado se ESPERA (spinner) — nunca se deniega — para evitar
   *  el falso "Acceso Denegado" al refrescar. Si la carga falla, cae al fallback por rol. */
  recurso?: string;
  accion?: string;
}

export default function ProtectedRoute({ children, allowedRoles, recurso, accion = 'read' }: Props) {
  const { isAuthenticated, rol } = useAuthStore();
  const permisos = usePermisosStore((s) => s.permisos);
  const intentado = usePermisosStore((s) => s.intentado);
  const cargando = usePermisosStore((s) => s.cargando);
  const cargar = usePermisosStore((s) => s.cargar);

  // Asegura la carga de permisos (p. ej. al refrescar directo sobre una ruta protegida,
  // antes de que MainLayout la dispare).
  useEffect(() => {
    if (isAuthenticated && recurso && permisos === null && !cargando && !intentado) cargar();
  }, [isAuthenticated, recurso, permisos, cargando, intentado, cargar]);

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  if (recurso) {
    if (permisos !== null) {
      // Los permisos ya cargaron: la matriz es la autoridad.
      const ok = Boolean(permisos[recurso] && permisos[recurso][accion]);
      return ok ? <>{children}</> : <Navigate to="/sin-acceso" replace />;
    }
    if (!intentado) {
      // Aún cargando: ESPERAR (no denegar) para no mandar a /sin-acceso por una carrera.
      return (
        <Box sx={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '60vh' }}>
          <CircularProgress />
        </Box>
      );
    }
    // Se intentó y falló (backend caído): degradar al fallback por rol de abajo.
  }

  if (allowedRoles && rol && !allowedRoles.includes(rol)) {
    return <Navigate to="/sin-acceso" replace />;
  }

  return <>{children}</>;
}
