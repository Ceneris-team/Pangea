import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

export default function PanelAdmin() {
  const { nombreCompleto, rol, logout } = useAuth();

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">

        {/* SIDEBAR */}
        <Sidebar onLogout={logout} activo="panel" rol={rol} />

        {/* ÁREA PRINCIPAL */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          {/* CONTENIDO */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                Hola, {nombreCompleto ?? "Administrador"}
              </h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Bienvenido al panel de Pangea 4.0.
              </p>
            </header>

            {/* Accesos rápidos (placeholder básico) */}
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <Link
                to="/usuarios"
                className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 hover:border-[#ccff00] transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-[#5a7000] dark:text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"></path></svg>
                </div>
                <h2 className="font-semibold text-gray-900 dark:text-white">Gestión de Usuarios</h2>
                <p className="text-sm text-gray-600 dark:text-gray-300">Ver, buscar y filtrar usuarios registrados.</p>
              </Link>

              <Link
                to="/ubicaciones"
                className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 hover:border-[#ccff00] transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-[#5a7000] dark:text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z"></path><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z"></path></svg>
                </div>
                <h2 className="font-semibold text-gray-900 dark:text-white">Gestión de Ubicaciones</h2>
                <p className="text-sm text-gray-600 dark:text-gray-300">Estaciones de monitoreo registradas.</p>
              </Link>

              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 opacity-60">
                <div className="w-10 h-10 rounded-lg bg-black/5 dark:bg-white/10 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-gray-500 dark:text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M5 8h14M5 8a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2v-9a2 2 0 00-2-2M5 8V6a2 2 0 012-2h10a2 2 0 012 2v2" /></svg>
                </div>
                <h2 className="font-semibold text-gray-900 dark:text-white">Dispositivos</h2>
                <p className="text-sm text-gray-600 dark:text-gray-300">Próximamente (HU10 / HU11).</p>
              </div>
            </div>
          </main>
        </div>
      </div>
      <nav style={{ marginTop: 24, display: "flex", gap: 16 }}>
        <Link to="/usuarios">Gestión de Usuarios</Link>
        <Link to="/mi-perfil">Mi perfil</Link>
        {/* TODO (equipo): agregar aquí los links a Ubicaciones (HU07/HU08),
            Dispositivos (HU10/HU11), etc. a medida que se implementen. */}
      </nav>
    </div>
  );
}