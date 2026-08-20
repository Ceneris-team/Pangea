import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU09 - Monitorear cola de procesamiento
 *
 * CA1: listado paginado (10 por página por defecto).
 * CA2: filtro por estado, en el lenguaje de negocio de la HU (el backend
 * traduce contra Pendiente/Procesando/Exitoso/Fallido de archv_ingst).
 * CA3: detalle en un modal al hacer click en la fila.
 * Refresco automático cada 30 segundos.
 */

interface ArchivoIngestaListItem {
  id_archv: number;
  nmbr_archv: string;
  datalogger_nombre: string;
  fch_dtccn: string;
  estado: string;
}

interface ArchivoIngestaDetalle extends ArchivoIngestaListItem {
  fch_prcsd: string | null;
  rgstrs_prcsds: number | null;
  mnsj_errr: string | null;
}

interface ListadoColaIngesta {
  total: number;
  pagina: number;
  por_pagina: number;
  items: ArchivoIngestaListItem[];
}

const POR_PAGINA = 10;
const REFRESCO_MS = 30_000;

const ESTADOS_FILTRO = ["En espera", "Procesando", "Procesado", "Fallido"] as const;

const ESTILO_ESTADO: Record<string, string> = {
  "En espera": "bg-white/10 text-gray-300 border-white/20",
  Procesando: "bg-blue-900/20 text-blue-400 border-blue-800/30",
  Procesado: "bg-[#ccff00]/20 text-[#ccff00] border-[#ccff00]/30",
  Fallido: "bg-red-900/20 text-red-400 border-red-800/30",
};

function formatearFecha(iso: string | null): string {
  if (!iso) return "-";
  return new Date(iso).toLocaleString("es", { dateStyle: "medium", timeStyle: "short" });
}

export default function ColaIngesta() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [pagina, setPagina] = useState(1);
  const [estadoFiltro, setEstadoFiltro] = useState("");
  const [data, setData] = useState<ListadoColaIngesta | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [idSeleccionado, setIdSeleccionado] = useState<number | null>(null);
  const [detalle, setDetalle] = useState<ArchivoIngestaDetalle | null>(null);
  const [detalleError, setDetalleError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;

    const cargar = () => {
      setLoading(true);
      apiFetch<ListadoColaIngesta>("/ingesta/cola", {
        params: { pagina, por_pagina: POR_PAGINA, estado: estadoFiltro || undefined },
      })
        .then((res) => {
          if (!cancelado) {
            setData(res);
            setError(null);
          }
        })
        .catch((err) => {
          if (!cancelado) setError(err instanceof ApiError ? err.message : "No se pudo cargar la cola de ingesta");
        })
        .finally(() => {
          if (!cancelado) setLoading(false);
        });
    };

    cargar();
    // Refresco automático de la cola (ver Conversación de la HU: cada 30s).
    const intervalo = setInterval(cargar, REFRESCO_MS);

    return () => {
      cancelado = true;
      clearInterval(intervalo);
    };
  }, [pagina, estadoFiltro]);

  useEffect(() => {
    if (idSeleccionado === null) {
      setDetalle(null);
      return;
    }
    let cancelado = false;
    setDetalleError(null);
    apiFetch<ArchivoIngestaDetalle>(`/ingesta/cola/${idSeleccionado}`)
      .then((res) => {
        if (!cancelado) setDetalle(res);
      })
      .catch((err) => {
        if (!cancelado) setDetalleError(err instanceof ApiError ? err.message : "No se pudo cargar el detalle");
      });
    return () => {
      cancelado = true;
    };
  }, [idSeleccionado]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="cola-ingesta" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-extrabold text-white">Cola de Procesamiento</h1>
              <p className="text-sm text-gray-300 mt-1 font-light">
                Archivos recibidos de los dataloggers y su estado de ingesta. Se actualiza automáticamente cada 30
                segundos.
              </p>
            </header>

            <div className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-white/10 overflow-hidden transition-colors duration-300">
              <div className="p-5 border-b border-white/10 flex flex-wrap items-center gap-3">
                <label className="text-sm font-medium text-gray-200" htmlFor="filtro-estado">
                  Estado:
                </label>
                <select
                  id="filtro-estado"
                  value={estadoFiltro}
                  onChange={(e) => {
                    setPagina(1);
                    setEstadoFiltro(e.target.value);
                  }}
                  className="bg-white/5 border border-white/20 text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] p-2.5 outline-none"
                >
                  <option value="">Todos</option>
                  {ESTADOS_FILTRO.map((estado) => (
                    <option key={estado} value={estado}>
                      {estado}
                    </option>
                  ))}
                </select>
              </div>

              {error && (
                <div className="p-4 bg-red-900/20 text-red-400 text-sm border-b border-red-800/30">
                  {error}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-300">
                  <thead className="text-xs text-gray-300 uppercase bg-white/5 border-b border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Archivo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Datalogger de origen</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Fecha de recepción</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && !data && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-300">
                          Cargando...
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-300">
                          No hay archivos en la cola{estadoFiltro ? ` con estado "${estadoFiltro}"` : ""}.
                        </td>
                      </tr>
                    )}

                    {data?.items.map((item) => (
                      <tr
                        key={item.id_archv}
                        onClick={() => setIdSeleccionado(item.id_archv)}
                        className="bg-white/[0.04] backdrop-blur-md border-b border-white/10 hover:bg-white/5 transition-colors cursor-pointer"
                      >
                        <td className="px-6 py-4 font-medium text-white">{item.nmbr_archv}</td>
                        <td className="px-6 py-4">{item.datalogger_nombre}</td>
                        <td className="px-6 py-4">{formatearFecha(item.fch_dtccn)}</td>
                        <td className="px-6 py-4">
                          <span
                            className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                              ESTILO_ESTADO[item.estado] ?? ESTILO_ESTADO["En espera"]
                            }`}
                          >
                            {item.estado}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-right">
                          <button
                            onClick={(e) => {
                              e.stopPropagation();
                              setIdSeleccionado(item.id_archv);
                            }}
                            className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-200 bg-transparent border border-white/20 rounded-lg hover:bg-white/10 hover:text-white transition-all"
                          >
                            Ver detalle
                          </button>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>

              {data && (
                <div className="p-5 border-t border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-300">
                    <span className="font-semibold text-white">{data.total}</span> archivo(s) en
                    la cola
                  </span>
                  <div className="flex items-center gap-3">
                    <span className="text-sm text-gray-300">
                      Página {data.pagina} de {totalPaginas}
                    </span>
                    <div className="flex gap-2">
                      <button
                        disabled={pagina <= 1}
                        onClick={() => setPagina((p) => p - 1)}
                        className="px-3 py-1.5 text-sm border border-white/20 rounded-lg disabled:opacity-50"
                      >
                        Anterior
                      </button>
                      <button
                        disabled={pagina >= totalPaginas}
                        onClick={() => setPagina((p) => p + 1)}
                        className="px-3 py-1.5 text-sm border border-white/20 rounded-lg disabled:opacity-50"
                      >
                        Siguiente
                      </button>
                    </div>
                  </div>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>

      {idSeleccionado !== null && (
        <div
          className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
          onClick={() => setIdSeleccionado(null)}
        >
          <div
            className="bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-xl border border-white/10 max-w-lg w-full p-6"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-center justify-between mb-4">
              <h2 className="text-lg font-bold text-white">Detalle del archivo</h2>
              <button
                onClick={() => setIdSeleccionado(null)}
                className="text-gray-400 hover:text-gray-200"
                aria-label="Cerrar"
              >
                <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
                </svg>
              </button>
            </div>

            {detalleError && (
              <div className="p-3 mb-4 bg-red-900/20 text-red-400 text-sm rounded-lg">
                {detalleError}
              </div>
            )}

            {!detalle && !detalleError && (
              <p className="text-sm text-gray-300">Cargando detalle...</p>
            )}

            {detalle && (
              <dl className="space-y-3 text-sm">
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Archivo</dt>
                  <dd className="font-medium text-white text-right">{detalle.nmbr_archv}</dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Datalogger de origen</dt>
                  <dd className="font-medium text-white text-right">
                    {detalle.datalogger_nombre}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Estado</dt>
                  <dd>
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                        ESTILO_ESTADO[detalle.estado] ?? ESTILO_ESTADO["En espera"]
                      }`}
                    >
                      {detalle.estado}
                    </span>
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Fecha de recepción</dt>
                  <dd className="font-medium text-white text-right">
                    {formatearFecha(detalle.fch_dtccn)}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Fecha de procesamiento</dt>
                  <dd className="font-medium text-white text-right">
                    {formatearFecha(detalle.fch_prcsd)}
                  </dd>
                </div>
                <div className="flex justify-between gap-4">
                  <dt className="text-gray-300">Registros procesados</dt>
                  <dd className="font-medium text-white text-right">
                    {detalle.rgstrs_prcsds ?? "-"}
                  </dd>
                </div>
                {detalle.estado === "Fallido" && detalle.mnsj_errr && (
                  <div>
                    <dt className="text-gray-300 mb-1">Mensaje de resultado</dt>
                    <dd className="text-red-400 bg-red-900/20 rounded-lg p-3">
                      {detalle.mnsj_errr}
                    </dd>
                  </div>
                )}

                {detalle.estado === "Procesado" && (
                  <div className="pt-3 border-t border-white/10">
                    <Link
                      to="/consulta-datos"
                      className="inline-flex items-center justify-center w-full px-4 py-2.5 text-sm font-semibold text-gray-900 bg-[#ccff00] rounded-xl hover:bg-[#b8e600] transition-all"
                    >
                      Ver datos
                    </Link>
                  </div>
                )}
              </dl>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
