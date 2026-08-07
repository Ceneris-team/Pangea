import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";

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
  const { logout, rol } = useAuth();

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
    <div className="flex h-screen bg-gray-50 dark:bg-gray-900 overflow-hidden">
      <Sidebar onLogout={logout} activo="conexiones-ftp" rol={rol} />

      <div className="flex-1 overflow-y-auto p-6 md:p-8">
        <div className="max-w-5xl mx-auto">
          <header className="flex flex-col lg:flex-row lg:items-center justify-between gap-4 mb-6">
            <div>
              <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Conexiones FTP</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">
                Dataloggers configurados para la ingesta automática de telemetría.
              </p>
            </div>
            <Link
              to="/conexiones-ftp/nueva"
              className="inline-flex items-center justify-center px-4 py-2.5 text-sm font-semibold text-gray-900 bg-[#ccff00] rounded-xl hover:bg-[#b8e600] transition-all"
            >
              Nueva conexión FTP
            </Link>
          </header>

          <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden">
            {error && (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30">
                {error}
              </div>
            )}

            <div className="overflow-x-auto">
              <table className="w-full text-sm text-left">
                <thead className="text-xs text-gray-500 dark:text-gray-400 uppercase bg-gray-50 dark:bg-gray-800/50">
                  <tr>
                    <th className="px-6 py-3">Datalogger</th>
                    <th className="px-6 py-3">Host/IP</th>
                    <th className="px-6 py-3">Directorio remoto</th>
                    <th className="px-6 py-3">Frecuencia</th>
                    <th className="px-6 py-3">Estado</th>
                    <th className="px-6 py-3 text-right">Acciones</th>
                  </tr>
                </thead>
                <tbody>
                  {loading && (
                    <tr>
                      <td colSpan={6} className="px-6 py-6 text-center text-gray-500 dark:text-gray-400">
                        Cargando...
                      </td>
                    </tr>
                  )}

                  {!loading && data?.items.length === 0 && (
                    <tr>
                      <td colSpan={6} className="px-6 py-6 text-center text-gray-500 dark:text-gray-400">
                        Todavía no hay conexiones FTP registradas.
                      </td>
                    </tr>
                  )}

                  {!loading &&
                    data?.items.map((c) => (
                      <tr key={c.id_cnxn} className="border-b border-gray-100 dark:border-gray-700">
                        <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{c.nmbr}</td>
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                          {c.hst}:{c.prt}
                        </td>
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">{c.rt_rmt}</td>
                        <td className="px-6 py-4 text-gray-600 dark:text-gray-300">
                          {textoFrecuencia(c.frcnc_mnts)}
                        </td>
                        <td className="px-6 py-4">
                          <span
                            className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-medium border ${
                              c.estd === "Activa"
                                ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600"
                            }`}
                          >
                            {c.estd}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <Link
                            to={`/conexiones-ftp/${c.id_cnxn}/editar`}
                            className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 transition-all"
                          >
                            Editar
                          </Link>
                        </td>
                      </tr>
                    ))}
                </tbody>
              </table>
            </div>

            {data && (
              <div className="p-5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                <span className="text-sm text-gray-500 dark:text-gray-400">
                  Página {data.pagina} de {totalPaginas}
                </span>
                <div className="flex gap-2">
                  <button
                    disabled={pagina <= 1}
                    onClick={() => setPagina((p) => p - 1)}
                    className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50"
                  >
                    Anterior
                  </button>
                  <button
                    disabled={pagina >= totalPaginas}
                    onClick={() => setPagina((p) => p + 1)}
                    className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50"
                  >
                    Siguiente
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}