import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * Gestión de Alarmas y Notificaciones - listado.
 *
 * Es el punto de entrada de HU28: "DADO QUE me encuentro en el módulo
 * 'Gestión de Alarmas y Notificaciones', CUANDO selecciono 'Crear
 * alarma'..." (CA1), y el destino al que vuelve el alta tanto al GUARDAR
 * (CA3) como al CANCELAR (CA4).
 *
 * El listado en sí es HU27 y está acá en su versión mínima -las columnas
 * de la ficha, los filtros y las acciones por fila son de esa historia-.
 * Se implementa solo lo que HU28 necesita para poder cerrar sus CA: que
 * la alarma recién creada se vea, con su estado Activa, junto al mensaje
 * de éxito.
 */

interface CondicionAlarma {
  id_cndcn: number;
  oprdr: string;
  vlr_umbrl: number;
}

interface AlarmaListItem {
  id_alrm: number;
  nmbr: string;
  id_prmtr: number;
  parametro_nombre: string;
  undd: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  estd: string;
  fch_crcn: string;
  condiciones: CondicionAlarma[];
}

interface ListadoAlarmas {
  total: number;
  pagina: number;
  por_pagina: number;
  items: AlarmaListItem[];
}

const POR_PAGINA = 10;

/** "> 3.5 m" / "sin condiciones configuradas". Las condiciones son de
 *  HU29; acá solo se muestran para que la alarma recién creada se vea
 *  completa al volver del alta. */
function resumenCondiciones(alarma: AlarmaListItem): string {
  if (alarma.condiciones.length === 0) return "Sin condiciones configuradas";
  return alarma.condiciones
    .map((c) => `${c.oprdr} ${c.vlr_umbrl} ${alarma.undd}`.trim())
    .join(" · ");
}

export default function Alarmas() {
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // HU28 CA3: al volver del alta, el listado muestra "Alarma creada
  // correctamente" junto a la alarma recién registrada. Mismo mecanismo
  // (state de navegación) que usa HU08 en Ubicaciones.tsx.
  const [mensajeExito, setMensajeExito] = useState<string | null>(
    (location.state as { mensaje?: string } | null)?.mensaje ?? null
  );

  // Se limpia el state para que el mensaje no reaparezca al recargar o
  // volver atrás.
  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  const [pagina, setPagina] = useState(1);
  const [data, setData] = useState<ListadoAlarmas | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const cargar = useCallback(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoAlarmas>("/alarmas", {
      params: { pagina, por_pagina: POR_PAGINA },
    })
      .then((res) => {
        if (!cancelado) setData(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado de alarmas");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [pagina]);

  useEffect(cargar, [cargar]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="alarmas" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Gestión de Alarmas y Notificaciones
                </h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Alarmas configuradas sobre los parámetros de tus ubicaciones asignadas.
                </p>
              </div>

              {/* HU28 CA1: punto de entrada al formulario de creación. */}
              <button
                onClick={() => navigate("/alarmas/nueva")}
                className="inline-flex items-center px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] transition-colors"
              >
                <svg
                  className="w-4 h-4 mr-2"
                  aria-hidden="true"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                  strokeWidth="2"
                  stroke="currentColor"
                >
                  <path strokeLinecap="round" strokeLinejoin="round" d="M12 4.5v15m7.5-7.5h-15" />
                </svg>
                Crear alarma
              </button>
            </header>

            {mensajeExito && (
              <div className="mb-4 p-4 rounded-xl bg-[#ccff00]/20 border border-[#ccff00]/40 text-[#5a7000] dark:text-[#ccff00] text-sm flex items-center justify-between">
                <span>{mensajeExito}</span>
                <button onClick={() => setMensajeExito(null)} className="text-xs font-medium underline">
                  Cerrar
                </button>
              </div>
            )}

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10">
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30 rounded-t-2xl">
                  {error}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Ubicación</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Condiciones</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando alarmas...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Todavía no has creado ninguna alarma.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((a) => (
                        <tr
                          key={a.id_alrm}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{a.nmbr}</td>
                          <td className="px-6 py-4">
                            {a.parametro_nombre}
                            <span className="text-gray-500 dark:text-gray-400"> ({a.undd})</span>
                          </td>
                          <td className="px-6 py-4">{a.ubicacion_nombre}</td>
                          <td className="px-6 py-4 font-mono text-xs">{resumenCondiciones(a)}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                a.estd === "Activa"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {a.estd === "Activa" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {a.estd}
                            </span>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {data && data.total > data.por_pagina && (
                <div className="p-5 border-t border-black/10 dark:border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    Página <span className="font-semibold text-gray-900 dark:text-white">{data.pagina}</span> de{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{totalPaginas}</span>
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPagina((p) => Math.max(1, p - 1))}
                      disabled={pagina <= 1}
                      className="px-3 py-1.5 text-sm rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                    >
                      Anterior
                    </button>
                    <button
                      onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
                      disabled={pagina >= totalPaginas}
                      className="px-3 py-1.5 text-sm rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
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
