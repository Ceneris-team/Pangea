import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

interface ProtectedRouteProps {
  children: ReactNode;
  /** Si se indica, solo ese rol puede entrar (p. ej. HU03: "Solo Administrador"). */
  rolRequerido?: string;
  /** Varios roles admitidos, para módulos compartidos (p. ej. HU06: "Solo
   *  Técnico CENERIS y Administrador"). Se ignora si se pasa rolRequerido. */
  rolesPermitidos?: readonly string[];
}

export default function ProtectedRoute({
  children,
  rolRequerido,
  rolesPermitidos,
}: ProtectedRouteProps) {
  const { isAuthenticated, rol } = useAuth();

  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  // El backend igual devuelve 403 ante cualquier intento directo al endpoint;
  // esto solo evita mostrar la pantalla a quien no debería ni verla.
  if (rolRequerido && rol !== rolRequerido) {
    return <Navigate to="/login" replace />;
  }

  if (rolesPermitidos && !rolesPermitidos.includes(rol ?? "")) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
}
