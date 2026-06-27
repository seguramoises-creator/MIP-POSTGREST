import { Navigate } from 'react-router-dom';
import { useAuthStore } from '../../store/auth.store';
import { Rol } from '../../types';

interface Props {
  children: React.ReactNode;
  allowedRoles?: Rol[];
}

export default function ProtectedRoute({ children, allowedRoles }: Props) {
  const { isAuthenticated, rol } = useAuthStore();

  if (!isAuthenticated) return <Navigate to="/login" replace />;

  if (allowedRoles && rol && !allowedRoles.includes(rol)) {
    return <Navigate to="/sin-acceso" replace />;
  }

  return <>{children}</>;
}
