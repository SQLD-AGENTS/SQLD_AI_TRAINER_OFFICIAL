import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '../../contexts/AuthContext';

export default function AuthGuard({ children }: { children: ReactNode }) {
  const { token, isGuest } = useAuth();
  const location = useLocation();

  if (!token || isGuest) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  return <>{children}</>;
}
