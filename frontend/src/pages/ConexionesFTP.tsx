import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface ConexionFTPListItem {
  id_cnxn: number;
  nmbr: string;
  hst: string;
  prt: number;
  usr_ftp: string | null;
  rt_rmt: string | null;
  frcnc_mnts: number;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: ConexionFTPListItem[];
}

const POR_PAGINA = 10;

function textoFrecuencia(frcnc_mnts: number): string {
  return frcnc_mnts === 1 ? "Cada minuto" : "Cada hora";
}

export default function ConexionesFTP() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/conexiones-ftp", {
      params: { pagina, por_pagina: POR_PAGINA },
    })
      .then((res) => {
        if (!cancelado) setData(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [pagina]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="conexiones-ftp" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
          />

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-white">Conexiones FTP</h1>
                <p className="text-sm text-gray-300 mt-1 font-light">
                  Dataloggers configurados para la ingesta automática de telemetría.
                </p>
              </div>
              <Link
                to="/conexiones-ftp/nueva"
                className="px-4 py-2.5 text-sm font-semibold text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
              >
                + Nueva conexión FTP
              </Link>
            </header>

            <div className="bg-white/5 backdrop-blur-xl rounded-2xl shadow-sm border border-white/10 overflow-hidden transition-colors duration-300">
              {error && (
                <div className="p-4 bg-red-900/20 text-red-400 text-sm border-b border-red-800/30">
                  {error}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-300">
                  <thead className="text-xs text-gray-300 uppercase bg-white/5 border-b border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Datalogger</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Host/IP</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Directorio remoto</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Frecuencia</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando conexiones...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-300">
                          Todavía no hay conexiones FTP registradas.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((c) => (
                        <tr
                          key={c.id_cnxn}
                          className="bg-white/5 backdrop-blur-xl border-b border-white/10 hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-white">{c.nmbr}</td>
                          <td className="px-6 py-4">
                            {c.hst}:{c.prt}
                          </td>
                          <td className="px-6 py-4">{c.rt_rmt}</td>
                          <td className="px-6 py-4">{textoFrecuencia(c.frcnc_mnts)}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                c.estd === "Activa"
                                  ? "bg-[#ccff00]/20 text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-white/10 text-gray-300 border-white/20"
                              }`}
                            >
                              {c.estd === "Activa" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {c.estd}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <Link
                              to={`/conexiones-ftp/${c.id_cnxn}/editar`}
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-200 bg-transparent border border-white/20 rounded-lg hover:bg-white/10 hover:text-white transition-all"
                            >
                              <svg
                                className="w-4 h-4 mr-2 text-gray-300"
                                fill="none"
                                viewBox="0 0 24 24"
                                strokeWidth="2"
                                stroke="currentColor"
                              >
                                <path
                                  strokeLinecap="round"
                                  strokeLinejoin="round"
                                  d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                                />
                              </svg>
                              Editar
                            </Link>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {data && (
                <div className="p-5 border-t border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-300">
                    Página {data.pagina} de {totalPaginas}
                  </span>
                  <div className="flex gap-2">
                    <button
                      disabled={pagina <= 1}
                      onClick={() => setPagina((p) => p - 1)}
                      className="px-3 py-1.5 text-sm font-medium text-gray-200 bg-transparent border border-white/20 rounded-lg hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Anterior
                    </button>
                    <button
                      disabled={pagina >= totalPaginas}
                      onClick={() => setPagina((p) => p + 1)}
                      className="px-3 py-1.5 text-sm font-medium text-gray-200 bg-transparent border border-white/20 rounded-lg hover:bg-white/10 transition-all disabled:opacity-50 disabled:cursor-not-allowed"
                    >
                      Siguiente
                    </button>
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
