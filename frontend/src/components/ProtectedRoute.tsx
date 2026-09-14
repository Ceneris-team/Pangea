import type { ReactNode } from "react";
import { Navigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import CambiarContrasenaModal from "./CambiarContrasenaModal";

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
  const { isAuthenticated, rol, debeCambiarContrasena, verificandoSesion } = useAuth();

  // Pestaña nueva, F5, o la primera carga de la app montan AuthProvider
  // desde cero, y con él arranca la verificación de sesión contra
  // GET /auth/perfil (ver el useEffect en AuthContext.tsx). Decidir acá
  // ANTES de que esa respuesta llegue significaría mirar isAuthenticated
  // en su valor inicial -vacío en una pestaña nueva, aunque la cookie
  // httpOnly siga viva- y mandar a login a alguien con sesión activa.
  // Un loading breve es preferible al parpadeo de "login -> dashboard"
  // que se vería si se dejara pasar y luego se redirigiera.
  if (verificandoSesion) {
    return (
      <div
        className="flex min-h-screen items-center justify-center bg-white dark:bg-neutral-900"
        aria-busy="true"
        aria-live="polite"
      />
    );
  }

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

  return (
    <>
      {children}
      {/* HU04: "la contraseña temporal deberá cambiarla en su primer inicio
          de sesión". Hasta que lo haga, se le bloquea con esta ventana
          emergente sobre cualquier ruta protegida en la que esté. */}
      {debeCambiarContrasena && <CambiarContrasenaModal />}
    </>
  );
}
