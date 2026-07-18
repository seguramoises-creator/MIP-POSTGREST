import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/auth.store';
import { usePuede } from '../../store/permisos.store';
import { Rol } from '../../types';

interface Props {
  children: React.ReactNode;
  allowedRoles?: Rol[];
  /** Recurso de la matriz RBAC. Si se define, el acceso lo decide /authz/me/permisos
   *  (con fallback a allowedRoles mientras los permisos aún no cargan). */
  recurso?: string;
  accion?: string;
}

export default function ProtectedRoute({ children, allowedRoles, recurso, accion = 'read' }: Props) {
  const { isAuthenticated, rol } = useAuthStore();
  const puede = usePuede();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  // Gate por matriz (si el recurso está mapeado y los permisos ya cargaron).
  if (recurso) {
    const p = puede(recurso, accion);
    if (p !== null) {
      return p ? <>{children}</> : <Navigate to="/sin-acceso" replace />;
    }
    // permisos aún no cargan → cae al fallback por rol de abajo
  }

  if (allowedRoles && rol && !allowedRoles.includes(rol)) {
    return <Navigate to="/sin-acceso" replace />;
  }

  return <>{children}</>;
}
