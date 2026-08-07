import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface ProtectedRouteProps {
  children: ReactNode;
  /** Si se indica, solo ese rol puede entrar (p. ej. HU03: "Solo Administrador"). */
  rolRequerido?: string;
}

export default function ProtectedRoute({ children, rolRequerido }: ProtectedRouteProps) {
  const { isAuthenticated, rol } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  if (rolRequerido && rol !== rolRequerido) {
    // El backend igual devuelve 403 ante cualquier intento directo al endpoint;
    // esto solo evita mostrar la pantalla a quien no debería ni verla.
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
