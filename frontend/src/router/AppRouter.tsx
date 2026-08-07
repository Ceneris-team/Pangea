import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import ProtectedRoute from "../components/ProtectedRoute";
import Login from "../pages/login";
import OlvideContrasena from "../pages/OlvideContrasena";
import RestablecerContrasena from "../pages/RestablecerContrasena";
import MiPerfil from "../pages/MiPerfil";
import PanelAdmin from "../pages/PanelAdmin";
import PanelTecnico from "../pages/PanelTecnico";
import PanelUsuario from "../pages/PanelUsuario";
import PanelComercial from "../pages/PanelComercial";
import Usuarios from "../pages/Usuarios";
import Ubicaciones from "../pages/Ubicaciones";
import { ROLES } from "../config/roles";
import ConexionesFTP from "../pages/ConexionesFTP";
import ConfigurarConexionFTP from "../pages/ConfigurarConexionFTP";
import ConsultaDatos from "../pages/ConsultaDatos";

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
            path="/panel-cliente"
            element={
              <ProtectedRoute rolRequerido={ROLES.CLIENTE_FINAL}>
                <PanelUsuario />
              </ProtectedRoute>
            }
          />

          <Route
            path="/panel-comercial"
            element={
              <ProtectedRoute rolRequerido={ROLES.ADMINISTRADOR_COMERCIAL}>
                <PanelComercial />
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

          {/* HU13: consulta de datos de telemetría filtrada por parámetros/ubicaciones */}
          <Route
            path="/consulta-datos"
            element={
              <ProtectedRoute>
                <ConsultaDatos />
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