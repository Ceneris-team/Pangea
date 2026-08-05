import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import ProtectedRoute from "../components/ProtectedRoute";
import Login from "../pages/Login";
import OlvideContrasena from "../pages/OlvideContrasena";
import RestablecerContrasena from "../pages/RestablecerContrasena";
import MiPerfil from "../pages/MiPerfil";
import PanelAdmin from "../pages/PanelAdmin";
import Usuarios from "../pages/Usuarios";
import { ROLES } from "../config/roles";

export default function AppRouter() {
  return (
    <BrowserRouter>
      <AuthProvider>
        <Routes>
          <Route path="/login" element={<Login />} />
          {/* HU02: flujo de recuperación de contraseña, accesible sin sesión */}
          <Route path="/olvide-contrasena" element={<OlvideContrasena />} />
          <Route path="/restablecer-contrasena" element={<RestablecerContrasena />} />

          {/* HU02: cambiar contraseña con sesión activa desde "Mi perfil" */}
          <Route
            path="/mi-perfil"
            element={
              <ProtectedRoute>
                <MiPerfil />
              </ProtectedRoute>
            }
          />

          <Route
            path="/panel-admin"
            element={
              <ProtectedRoute rolRequerido={ROLES.ADMINISTRADOR}>
                <PanelAdmin />
              </ProtectedRoute>
            }
          />

          {/* HU03: "Solo el rol Administrador puede acceder a este módulo." */}
          <Route
            path="/usuarios"
            element={
              <ProtectedRoute rolRequerido={ROLES.ADMINISTRADOR}>
                <Usuarios />
              </ProtectedRoute>
            }
          />

          {/* TODO (equipo): agregar /panel-tecnico, /panel-cliente, /panel-comercial
              cuando se implementen esas historias. Por ahora, si un rol distinto
              a Administrador inicia sesión, no tiene panel propio todavía. */}

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}
