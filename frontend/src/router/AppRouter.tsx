import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import ProtectedRoute from "../components/ProtectedRoute";
import Login from "../pages/Login";
import OlvideContrasena from "../pages/OlvideContrasena";
import RestablecerContrasena from "../pages/RestablecerContrasena";
import MiPerfil from "../pages/MiPerfil";
import PanelAdmin from "../pages/PanelAdmin";
import PanelTecnico from "../pages/PanelTecnico";
import PanelUsuario from "../pages/PanelUsuario";
import PanelComercial from "../pages/PanelComercial";
import Usuarios from "../pages/Usuarios";
import Ubicaciones from "../pages/Ubicaciones";
import AgregarUbicacion from "../pages/AgregarUbicacion";
import { ROLES } from "../config/roles";
import ConexionesFTP from "../pages/ConexionesFTP";
import ConfigurarConexionFTP from "../pages/ConfigurarConexionFTP";
import ConsultaDatos from "../pages/ConsultaDatos";
import Mapeos from "../pages/Mapeos";
import ConfigurarMapeo from "../pages/ConfigurarMapeo";
import ColaIngesta from "../pages/ColaIngesta";

// HU06: "Solo los roles Técnico CENERIS y Administrador tienen acceso a
// este módulo." El backend lo exige igual vía require_permiso('Ingesta').
const ROLES_MAPEOS = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS] as const;

// HU05: "Solo los roles Técnico CENERIS y Administrador tienen acceso a
// este módulo." El backend lo exige igual (_requerir_tecnico_o_admin).
const ROLES_CONEXIONES_FTP = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS] as const;

// HU09: mismo módulo de permisos ('Ingesta') y mismos roles que HU06.
const ROLES_COLA_INGESTA = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS] as const;

// HU08: "Solo los roles Administrador y Técnico CENERIS pueden registrar
// ubicaciones." El backend lo exige con require_permiso('Ubicaciones',
// EDICION); el listado (HU07) sigue siendo visible para todos los roles.
const ROLES_AGREGAR_UBICACION = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS] as const;

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
          {/* HU08: agregar ubicación */}
          <Route
            path="/ubicaciones/nueva"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_AGREGAR_UBICACION}>
                <AgregarUbicacion />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_CONEXIONES_FTP}>
                <ConexionesFTP />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp/nueva"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_CONEXIONES_FTP}>
                <ConfigurarConexionFTP />
              </ProtectedRoute>
            }
          />
          <Route
            path="/conexiones-ftp/:id/editar"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_CONEXIONES_FTP}>
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

          {/* HU09: monitorear cola de procesamiento */}
          <Route
            path="/cola-ingesta"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_COLA_INGESTA}>
                <ColaIngesta />
              </ProtectedRoute>
            }
          />

          <Route path="*" element={<Navigate to="/login" replace />} />
        </Routes>
      </AuthProvider>
    </BrowserRouter>
  );
}