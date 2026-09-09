import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface PanelListItem {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

interface ListadoPaneles {
  items: PanelListItem[];
}

// HU24: "YO COMO Cliente Final..." -crear paneles es exclusivo de ese rol.
// El backend ya lo exige (require_permiso EDICION + chequeo de rol en
// routers/panel.py::crear_panel, 403 para cualquier otro); esto solo evita
// mostrar un botón que terminaría en 403, mismo patrón que
// ROLES_PUEDEN_AGREGAR en Ubicaciones.tsx.
const ROLES_PUEDEN_CREAR: readonly string[] = [ROLES.CLIENTE_FINAL];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);
  return debounced;
}

function formatearFecha(iso: string): string {
  return new Date(iso).toLocaleDateString("es-PE", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  });
}

export default function Paneles() {
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // HU24 CA2: al volver del formulario de creación, el listado muestra el
  // mensaje de éxito (mismo patrón que Ubicaciones.tsx).
  const [mensajeExito, setMensajeExito] = useState<string | null>(
    (location.state as { mensaje?: string } | null)?.mensaje ?? null
  );

  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  // CA3: búsqueda por nombre o fragmento, insensible a mayúsculas.
  const [busquedaInput, setBusquedaInput] = useState("");
  const busqueda = useDebouncedValue(busquedaInput, 400);

  const [data, setData] = useState<ListadoPaneles | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaneles>("/paneles", {
      params: { busqueda: busqueda || undefined },
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
  }, [busqueda]);

  // CA1: "si el usuario no tiene paneles creados" se refiere a que no
  // existe NINGUNO, no a que la búsqueda no encontró nada -por eso el
  // mensaje con el botón "Crear panel" solo aplica sin filtro activo.
  const sinPanelesCreados = !loading && !busqueda && data?.items.length === 0;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="paneles" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Tableros Personalizables</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Administra tu colección de paneles de visualización.
                </p>
              </div>

              {ROLES_PUEDEN_CREAR.includes(rol ?? "") && (
                <div className="flex gap-3">
                  <button
                    onClick={() => navigate("/paneles/nuevo")}
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
                    Crear panel
                  </button>
                </div>
              )}
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
              {/* Barra de búsqueda */}
              <div className="p-5 flex flex-col lg:flex-row gap-3 items-center justify-between border-b border-black/10 dark:border-white/10">
                <div className="relative w-full lg:w-80">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-4 h-4 text-gray-500 dark:text-gray-400" fill="none" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={busquedaInput}
                    onChange={(e) => setBusquedaInput(e.target.value)}
                    placeholder="Buscar por nombre de panel..."
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400"
                  />
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {sinPanelesCreados ? (
                <div className="flex flex-col items-center justify-center gap-4 py-16 px-6 text-center">
                  <p className="text-gray-600 dark:text-gray-300">Aún no tienes paneles creados</p>
                  {ROLES_PUEDEN_CREAR.includes(rol ?? "") && (
                    <button
                      onClick={() => navigate("/paneles/nuevo")}
                      className="inline-flex items-center px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] transition-colors"
                    >
                      Crear panel
                    </button>
                  )}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                    <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                      <tr>
                        <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                        <th className="px-6 py-4 font-bold tracking-wider">Fecha de creación</th>
                        <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                      </tr>
                    </thead>
                    <tbody>
                      {loading && (
                        <tr>
                          <td colSpan={3} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                            <div className="flex justify-center items-center gap-2">
                              <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                              <span>Cargando datos...</span>
                            </div>
                          </td>
                        </tr>
                      )}

                      {!loading && data?.items.length === 0 && (
                        <tr>
                          <td colSpan={3} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                            No se encontraron paneles con ese criterio.
                          </td>
                        </tr>
                      )}

                      {!loading &&
                        data?.items.map((p) => (
                          <tr
                            key={p.id_pnl}
                            className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors group"
                          >
                            <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">
                              {/* CA2: seleccionar el nombre abre el panel. */}
                              <Link
                                to={`/paneles/${p.id_pnl}`}
                                className="hover:text-[#5a7000] dark:hover:text-[#ccff00] hover:underline transition-colors"
                              >
                                {p.nmbr}
                              </Link>
                            </td>
                            <td className="px-6 py-4">{formatearFecha(p.fch_crcn)}</td>
                            <td className="px-6 py-4 text-right">
                              <div className="flex items-center justify-end gap-2">
                                <Link
                                  to={`/paneles/${p.id_pnl}`}
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                                >
                                  Abrir
                                </Link>
                              </div>
                            </td>
                          </tr>
                        ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
