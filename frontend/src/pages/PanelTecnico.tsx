import { useState } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

export default function PanelTecnico() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="dashboard" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              isDarkMode={isDarkMode}
              onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          {/* CONTENIDO */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-white">
                Hola, {nombreCompleto ?? "Técnico"}
              </h1>
              <p className="text-sm text-gray-300">
                Panel de Técnico CENERIS — Pangea 4.0.
              </p>
            </header>

            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4">
              <Link
                to="/ubicaciones"
                className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 p-6 hover:border-[#ccff00] transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z" />
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
                  </svg>
                </div>
                <h2 className="font-semibold text-white">Gestión de Ubicaciones</h2>
                <p className="text-sm text-gray-300">Estaciones de monitoreo registradas.</p>
              </Link>

              {/* Placeholder: HU10 (Listar dispositivos) y HU05 (Conexión FTP) aún no implementadas para este rol */}
              <div className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 p-6 opacity-60">
                <div className="w-10 h-10 rounded-lg bg-white/10 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-gray-400" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M5 8h14M5 8a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2v-9a2 2 0 00-2-2M5 8V6a2 2 0 012-2h10a2 2 0 012 2v2" />
                  </svg>
                </div>
                <h2 className="font-semibold text-white">Dispositivos</h2>
                <p className="text-sm text-gray-300">Próximamente (HU10 / HU11).</p>
              </div>

              <Link
                to="/conexiones-ftp"
                className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 p-6 hover:border-[#ccff00] transition-colors"
              >
                <div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
                  <svg className="w-5 h-5 text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" />
                  </svg>
                </div>
                <h2 className="font-semibold text-white">Conexión FTP</h2>
                <p className="text-sm text-gray-300">Gestionar y crear conexiones FTP.</p>
              </Link>
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}