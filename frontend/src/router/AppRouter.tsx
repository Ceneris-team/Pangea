import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import ProtectedRoute from "../components/ProtectedRoute";
import Login from "../pages/Login";
import OlvideContrasena from "../pages/OlvideContrasena";
import RestablecerContrasena from "../pages/RestablecerContrasena";
import MiPerfil from "../pages/MiPerfil";
import PanelAdmin from "../pages/PanelAdmin";
import PanelTecnico from "../pages/PanelTecnico";
import Usuarios from "../pages/Usuarios";
import Ubicaciones from "../pages/Ubicaciones";
import { ROLES } from "../config/roles";
import ConexionesFTP from "../pages/ConexionesFTP";
import ConfigurarConexionFTP from "../pages/ConfigurarConexionFTP";
import Mapeos from "../pages/Mapeos";
import ConfigurarMapeo from "../pages/ConfigurarMapeo";

// HU06: "Solo los roles Técnico CENERIS y Administrador tienen acceso a
// este módulo." El backend lo exige igual vía require_permiso('Ingesta').
const ROLES_MAPEOS = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS] as const;

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

          {/* Nueva: resuelve el problema de que el Técnico no aterrizaba
              en ningún lado tras el login (rutaPorRol() apuntaba aquí y
              la ruta no existía). */}
          <Route
            path="/panel-tecnico"
            element={
              <ProtectedRoute rolRequerido={ROLES.TECNICO_CENERIS}>
                <PanelTecnico />
              </ProtectedRoute>
            }
          />

          <Route
            path="/usuarios"
            element={
              <ProtectedRoute rolRequerido={ROLES.ADMINISTRADOR}>
                <Usuarios />
              </ProtectedRoute>
            }
          />

          <Route
            path="/ubicaciones"
            element={
              <ProtectedRoute>
                <Ubicaciones />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp"
            element={
              <ProtectedRoute>
                <ConexionesFTP />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp/nueva"
            element={
              <ProtectedRoute>
                <ConfigurarConexionFTP />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp/:id/editar"
            element={
              <ProtectedRoute>
                <ConfigurarConexionFTP />
              </ProtectedRoute>
            }
          />

          {/* HU06: mapeo de formato por marca de sensor */}
          <Route
            path="/mapeos"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_MAPEOS}>
                <Mapeos />
              </ProtectedRoute>
            }
          />
          <Route
            path="/mapeos/nuevo"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_MAPEOS}>
                <ConfigurarMapeo />
              </ProtectedRoute>
            }
          />
          <Route
            path="/mapeos/:id/editar"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_MAPEOS}>
                <ConfigurarMapeo />
              </ProtectedRoute>
            }
          />

          {/* TODO (equipo): agregar /panel-cliente y /panel-comercial
              cuando se implementen esas historias. */}

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}