import { Navigate, Outlet } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';

export default function ProtectedRoute() {
  const { autenticado, carregando } = useAuth();

  if (carregando) {
    return <p className="status-message">Verificando sua sessão...</p>;
  }

  return autenticado ? <Outlet /> : <Navigate to="/login" replace />;
}
