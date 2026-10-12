import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import PerfilConfiguracion from "../components/perfil/PerfilConfiguracion";

/** La ruta sigue disponible para el primer ingreso con contraseña temporal. */
export default function MiPerfil() {
  const { nombreCompleto, rol, logout, debeCambiarContrasena } = useAuth();

  if (debeCambiarContrasena) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50 dark:bg-[#1a202c]">
        <PerfilConfiguracion />
      </div>
    );
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mi-perfil" rol={rol} />
        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <PerfilConfiguracion />
          </main>
        </div>
      </div>
    </div>
  );
}
