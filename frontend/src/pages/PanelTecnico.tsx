import { useState, type ReactNode } from "react";
import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface TarjetaModulo {
  to: string;
  titulo: string;
  descripcion: string;
  icono: ReactNode;
}

// Módulos ya disponibles para Técnico CENERIS (mismo criterio de acceso
// que Sidebar.tsx: Conexiones FTP, Parámetros y Cola de Ingesta son
// exclusivos de Administrador/Técnico; Ubicaciones, Dispositivos, Consulta
// de Datos y Gráficos son comunes a todos los roles).
const MODULOS: TarjetaModulo[] = [
  {
    to: "/ubicaciones",
    titulo: "Gestión de Ubicaciones",
    descripcion: "Estaciones de monitoreo registradas.",
    icono: (
      <>
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z" />
        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
      </>
    ),
  },
  {
    to: "/dispositivos",
    titulo: "Gestión de Dispositivos",
    descripcion: "Dataloggers y sensores registrados por ubicación.",
    icono: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
      />
    ),
  },
  {
    to: "/conexiones-ftp",
    titulo: "Conexión FTP",
    descripcion: "Gestionar y crear conexiones FTP.",
    icono: (
      <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M8 7h12m0 0l-4-4m4 4l-4 4M16 17H4m0 0l4 4m-4-4l4-4" />
    ),
  },
  {
    to: "/parametros",
    titulo: "Parámetros",
    descripcion: "Catálogo de parámetros estándar para el mapeo de formato.",
    icono: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        d="M9 17V7m3 10V11m3 6V9M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z"
      />
    ),
  },
  {
    to: "/cola-ingesta",
    titulo: "Cola de Ingesta",
    descripcion: "Estado de los archivos recibidos de los dataloggers.",
    icono: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M4 7h16M4 12h16M4 17h16" />,
  },
  {
    to: "/consulta-datos",
    titulo: "Consulta de Datos",
    descripcion: "Telemetría filtrada por parámetros y ubicaciones.",
    icono: (
      <path
        strokeLinecap="round"
        strokeLinejoin="round"
        strokeWidth="2"
        d="M9 17V7m6 10V11m-9 6h12a2 2 0 002-2V5a2 2 0 00-2-2H6a2 2 0 00-2 2v10a2 2 0 002 2z"
      />
    ),
  },
  {
    to: "/graficos",
    titulo: "Gráficos",
    descripcion: "Vista rápida de telemetría en línea de tiempo.",
    icono: <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 3v18h18M7 15l4-5 3 3 5-7" />,
  },
];

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
              {MODULOS.map((m) => (
                <Link
                  key={m.to}
                  to={m.to}
                  className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 p-6 hover:border-[#ccff00] transition-colors"
                >
                  <div className="w-10 h-10 rounded-lg bg-[#ccff00]/20 flex items-center justify-center mb-3">
                    <svg className="w-5 h-5 text-[#ccff00]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                      {m.icono}
                    </svg>
                  </div>
                  <h2 className="font-semibold text-white">{m.titulo}</h2>
                  <p className="text-sm text-gray-300">{m.descripcion}</p>
                </Link>
              ))}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
