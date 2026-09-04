import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { AuthProvider } from "../context/AuthContext";
import { ThemeProvider } from "../context/ThemeContext";
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
import Dispositivos from "../pages/Dispositivos";
import AgregarUbicacion from "../pages/AgregarUbicacion";
import DetalleUbicacion from "../pages/DetalleUbicacion";
import MapaUbicacionesPage from "../pages/MapaUbicacionesPage";
import MapaEstacionesPage from "../pages/MapaEstacionesPage";
import EditarUbicacion from "../pages/EditarUbicacion";
import { ROLES } from "../config/roles";
import ConexionesFTP from "../pages/ConexionesFTP";
import ConsultaDatos from "../pages/ConsultaDatos";
import Graficos from "../pages/Graficos";
import DispositivoDetalle from "../pages/DispositivoDetalle";
import Parametros from "../pages/Parametros";
import ColaIngesta from "../pages/ColaIngesta";
import Alarmas from "../pages/Alarmas";
import CrearAlarma from "../pages/CrearAlarma";

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
      <ThemeProvider>
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
          {/* HU22: mapa de ubicaciones, solo lectura. Se declara ANTES de
              /ubicaciones/:id para que ese parámetro no la capture (mismo
              patrón que /dispositivos/nueva vs /dispositivos/:id). */}
          <Route
            path="/ubicaciones/mapa"
            element={
              <ProtectedRoute>
                <MapaUbicacionesPage />
              </ProtectedRoute>
            }
          />
          {/* HU08 (ampliación): editar una ubicación existente. Mismos
              roles que el alta -el backend exige Edición sobre
              "Ubicaciones"-. Va antes de /ubicaciones/:id por el mismo
              motivo que /ubicaciones/mapa: el segmento literal tiene que
              ganarle al parámetro. */}
          <Route
            path="/ubicaciones/:id/editar"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_AGREGAR_UBICACION}>
                <EditarUbicacion />
              </ProtectedRoute>
            }
          />
          {/* Ficha de ubicación: datos + parámetros en uso (derivado de
              los mapeos de sus dispositivos). Sin restricción de rol
              adicional: el backend ya filtra qué ubicación puede ver
              cada uno (Cliente Final incluido, vía PermisoUbicacion). */}
          <Route
            path="/ubicaciones/:id"
            element={
              <ProtectedRoute>
                <DetalleUbicacion />
              </ProtectedRoute>
            }
          />
          {/* HU10: listar dispositivos. Sin restricción de rol adicional:
              el backend ya filtra qué ve cada uno (Cliente Final incluido,
              tiene Lectura sembrada en el módulo 'Dispositivos'). */}
          <Route
            path="/dispositivos"
            element={
              <ProtectedRoute>
                <Dispositivos />
              </ProtectedRoute>
            }
          />
          {/* DEC-09: ficha del dispositivo. Reemplaza al módulo "Mapeos de
              Formato": acá viven las pestañas Formato y Datos (el mapeo de
              ESTE datalogger), además de Carga de datos, Carga manual y
              Logs (IMP-06). Se declara DESPUÉS de /dispositivos/nueva para
              que esa ruta literal no la capture el parámetro :id. */}
          <Route
            path="/dispositivos/:id"
            element={
              <ProtectedRoute>
                <DispositivoDetalle />
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

          {/* HU17: mapa de estaciones del Cliente Final, con telemetría en
              vivo. Es una pantalla DISTINTA de /ubicaciones/mapa (HU22,
              vista de Administrador): esta muestra solo las ubicaciones
              asignadas al usuario y su último dato. Sin restricción de rol
              adicional -el backend ya filtra por prms_ubccn (HU21) y exige
              Lectura sobre "Tableros"-, así que un Administrador también
              puede entrar y ve todas, igual que en el resto de la app. */}
          <Route
            path="/mapa-estaciones"
            element={
              <ProtectedRoute>
                <MapaEstacionesPage />
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

          {/* Vista rápida de telemetría en gráficos, misma fuente que HU13 */}
          <Route
            path="/graficos"
            element={
              <ProtectedRoute>
                <Graficos />
              </ProtectedRoute>
            }
          />

          {/* DEC-09: las rutas /mapeos, /mapeos/nuevo y /mapeos/:id/editar
              se retiraron. El mapeo de formato dejó de ser un módulo
              propio y vive en la ficha del dispositivo
              (/dispositivos/:id, pestañas Formato y Datos).
              Mapeos.tsx y ConfigurarMapeo.tsx siguen en el repo sin ruta
              que los monte, a propósito, por si hay que revertir. */}

          {/* Catálogo de parámetros estándar que consume HU06 */}
          <Route
            path="/parametros"
            element={
              <ProtectedRoute rolesPermitidos={ROLES_MAPEOS}>
                <Parametros />
              </ProtectedRoute>
            }
          />

          {/* HU27/HU28: gestión de alarmas y notificaciones. Sin
              restricción de rol adicional: el backend ya exige Lectura
              sobre "Alarmas" para el listado y Edición para crear, y
              filtra por ubicación asignada (HU21). */}
          <Route
            path="/alarmas"
            element={
              <ProtectedRoute>
                <Alarmas />
              </ProtectedRoute>
            }
          />
          {/* HU28: alta en dos pasos (datos generales + condiciones de
              HU29). Va antes de cualquier /alarmas/:id futuro, mismo
              criterio que /ubicaciones/nueva. */}
          <Route
            path="/alarmas/nueva"
            element={
              <ProtectedRoute>
                <CrearAlarma />
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
      </ThemeProvider>
    </BrowserRouter>
  );
}