import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU26 - Añadir ubicaciones al panel.
 *
 *   CA1  "Añadir ubicaciones" muestra el listado de ubicaciones
 *        disponibles asignadas a mi cuenta
 *   CA2  "AGREGAR AL PANEL" asocia las seleccionadas y muestra el MSG
 *        "Ubicaciones añadidas correctamente"
 *   CA3  cada ubicación añadida aparece con su nombre y los últimos
 *        valores de telemetría disponibles
 *   CA4  "Quitar" retira la ubicación del panel y muestra el MSG
 *        "Ubicación retirada del panel"
 */

interface ParametroUltimoValor {
  parametro: string;
  unidad: string;
  valor: number | string | null;
  fch_hr: string | null;
}

interface UbicacionEnPanel {
  id_ubccn: number;
  nmbr: string;
  parametros: ParametroUltimoValor[];
}

interface PanelDetalle {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
  ubicaciones: UbicacionEnPanel[];
}

interface UbicacionParaPanel {
  id_ubccn: number;
  nmbr: string;
}

export default function DetallePanel() {
  const { id } = useParams<{ id: string }>();
  const { nombreCompleto, rol, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // HU24 CA2: tras crear el panel, la redirección trae el mensaje de
  // éxito en el state (mismo patrón que Ubicaciones.tsx).
  const [mensajeExito, setMensajeExito] = useState<string | null>(
    (location.state as { mensaje?: string } | null)?.mensaje ?? null
  );

  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  const [panel, setPanel] = useState<PanelDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  function cargarPanel() {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<PanelDetalle>(`/paneles/${id}`)
      .then((res) => {
        if (!cancelado) setPanel(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el panel");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }

  useEffect(cargarPanel, [id]);

  // CA4: "Quitar" retira la ubicación del panel.
  const [quitandoId, setQuitandoId] = useState<number | null>(null);

  async function quitarUbicacion(id_ubccn: number) {
    setQuitandoId(id_ubccn);
    setError(null);
    try {
      const resp = await apiFetch<{ mensaje: string; panel: PanelDetalle }>(
        `/paneles/${id}/ubicaciones/${id_ubccn}`,
        { method: "DELETE" }
      );
      setPanel(resp.panel);
      setMensajeExito(resp.mensaje);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo quitar la ubicación");
    } finally {
      setQuitandoId(null);
    }
  }

  // CA1/CA2: panel "Añadir ubicaciones".
  const [mostrarAnadir, setMostrarAnadir] = useState(false);
  const [disponibles, setDisponibles] = useState<UbicacionParaPanel[]>([]);
  const [seleccionadas, setSeleccionadas] = useState<Set<number>>(new Set());
  const [cargandoDisponibles, setCargandoDisponibles] = useState(false);
  const [agregando, setAgregando] = useState(false);
  const [errorAnadir, setErrorAnadir] = useState("");

  function abrirAnadirUbicaciones() {
    setSeleccionadas(new Set());
    setErrorAnadir("");
    setMostrarAnadir(true);
    setCargandoDisponibles(true);

    apiFetch<{ items: UbicacionParaPanel[] }>(`/paneles/${id}/ubicaciones-disponibles`)
      .then((res) => setDisponibles(res.items))
      .catch((err) =>
        setErrorAnadir(err instanceof ApiError ? err.message : "No se pudieron cargar las ubicaciones")
      )
      .finally(() => setCargandoDisponibles(false));
  }

  function alternarSeleccion(id_ubccn: number) {
    setSeleccionadas((prev) => {
      const siguiente = new Set(prev);
      if (siguiente.has(id_ubccn)) siguiente.delete(id_ubccn);
      else siguiente.add(id_ubccn);
      return siguiente;
    });
  }

  async function agregarAlPanel() {
    if (seleccionadas.size === 0) {
      setErrorAnadir("Selecciona al menos una ubicación");
      return;
    }

    setAgregando(true);
    setErrorAnadir("");
    try {
      const resp = await apiFetch<{ mensaje: string; panel: PanelDetalle }>(
        `/paneles/${id}/ubicaciones`,
        { method: "POST", body: { ids_ubccn: Array.from(seleccionadas) } }
      );
      setPanel(resp.panel);
      setMensajeExito(resp.mensaje);
      setMostrarAnadir(false);
    } catch (err) {
      setErrorAnadir(err instanceof ApiError ? err.message : "No se pudieron añadir las ubicaciones");
    } finally {
      setAgregando(false);
    }
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="paneles" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <div className="mb-6">
              <Link
                to="/paneles"
                className="text-sm text-gray-600 dark:text-gray-300 hover:text-[#5a7000] dark:hover:text-[#ccff00] transition-colors"
              >
                ← Volver a Tableros Personalizables
              </Link>
            </div>

            {mensajeExito && (
              <div className="mb-4 p-4 rounded-xl bg-[#ccff00]/20 border border-[#ccff00]/40 text-[#5a7000] dark:text-[#ccff00] text-sm flex items-center justify-between">
                <span>{mensajeExito}</span>
                <button onClick={() => setMensajeExito(null)} className="text-xs font-medium underline">
                  Cerrar
                </button>
              </div>
            )}

            {error && (
              <div className="mb-4 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {loading && (
              <div className="flex justify-center items-center gap-2 py-16 text-gray-600 dark:text-gray-300">
                <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                <span>Cargando panel...</span>
              </div>
            )}

            {!loading && panel && (
              <>
                <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{panel.nmbr}</h1>

                  <button
                    onClick={abrirAnadirUbicaciones}
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
                    Añadir ubicaciones
                  </button>
                </header>

                {panel.ubicaciones.length === 0 ? (
                  <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 flex flex-col items-center justify-center gap-4 py-20 px-6 text-center">
                    <p className="text-gray-600 dark:text-gray-300">
                      Este panel todavía no tiene ubicaciones configuradas.
                    </p>
                    <button
                      onClick={abrirAnadirUbicaciones}
                      className="inline-flex items-center px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] transition-colors"
                    >
                      + Añadir ubicaciones
                    </button>
                  </div>
                ) : (
                  <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">
                    {panel.ubicaciones.map((u) => (
                      <div
                        key={u.id_ubccn}
                        className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-5"
                      >
                        <div className="flex items-start justify-between gap-2 mb-3">
                          <h3 className="font-bold text-gray-900 dark:text-white">{u.nmbr}</h3>
                          {/* CA4 */}
                          <button
                            onClick={() => quitarUbicacion(u.id_ubccn)}
                            disabled={quitandoId === u.id_ubccn}
                            className="text-xs font-medium text-red-600 dark:text-red-400 hover:underline disabled:opacity-50 whitespace-nowrap"
                          >
                            {quitandoId === u.id_ubccn ? "Quitando..." : "Quitar"}
                          </button>
                        </div>

                        {/* CA3: últimos valores de telemetría disponibles. */}
                        {u.parametros.length === 0 ? (
                          <p className="text-xs text-gray-500 dark:text-gray-400">
                            Sin datos de telemetría todavía.
                          </p>
                        ) : (
                          <ul className="space-y-1.5">
                            {u.parametros.map((p) => (
                              <li
                                key={p.parametro}
                                className="flex items-center justify-between text-sm text-gray-600 dark:text-gray-300"
                              >
                                <span className="capitalize">{p.parametro.replace(/_/g, " ")}</span>
                                <span className="font-semibold text-gray-900 dark:text-white">
                                  {p.valor ?? "—"} {p.unidad}
                                </span>
                              </li>
                            ))}
                          </ul>
                        )}
                      </div>
                    ))}
                  </div>
                )}
              </>
            )}
          </main>
        </div>
      </div>

      {/* CA1: listado de ubicaciones disponibles para añadir. */}
      {mostrarAnadir && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <div className="p-6 border-b border-gray-100 dark:border-gray-700">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">Añadir ubicaciones</h2>
            </div>

            <div className="p-6 space-y-3 max-h-96 overflow-y-auto">
              {cargandoDisponibles && (
                <div className="flex justify-center items-center gap-2 text-sm text-gray-600 dark:text-gray-300 py-4">
                  <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                  <span>Cargando ubicaciones...</span>
                </div>
              )}

              {errorAnadir && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                  {errorAnadir}
                </div>
              )}

              {!cargandoDisponibles && disponibles.length === 0 && !errorAnadir && (
                <p className="text-sm text-gray-500 dark:text-gray-400 text-center py-4">
                  No tienes más ubicaciones asignadas para añadir a este panel.
                </p>
              )}

              {!cargandoDisponibles &&
                disponibles.map((u) => (
                  <label
                    key={u.id_ubccn}
                    className="flex items-center gap-3 p-2.5 rounded-xl border border-black/10 dark:border-white/10 cursor-pointer hover:bg-black/5 dark:hover:bg-white/5"
                  >
                    <input
                      type="checkbox"
                      checked={seleccionadas.has(u.id_ubccn)}
                      onChange={() => alternarSeleccion(u.id_ubccn)}
                      className="w-4 h-4 accent-[#ccff00]"
                    />
                    <span className="text-sm text-gray-900 dark:text-white">{u.nmbr}</span>
                  </label>
                ))}
            </div>

            <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setMostrarAnadir(false)}
                className="px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
              >
                Cancelar
              </button>
              {/* CA2 */}
              <button
                type="button"
                onClick={agregarAlPanel}
                disabled={agregando || cargandoDisponibles}
                className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
              >
                {agregando ? "Agregando..." : "Agregar al panel"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
