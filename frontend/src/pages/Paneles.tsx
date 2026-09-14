import { useEffect, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import ConfirmarEliminacionModal from "../components/ConfirmarEliminacionModal";

interface PanelListItem {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

interface ListadoPaneles {
  items: PanelListItem[];
}

interface PanelCreado {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

const NOMBRE_MAX_LARGO = 100;

const INPUT_CLASE =
  "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
const LABEL_CLASE = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";

// HU24/HU25: "YO COMO Cliente Final..." -crear, editar y eliminar paneles
// es exclusivo de ese rol. El backend ya lo exige (require_permiso EDICION
// + chequeo de rol en routers/panel.py, 403 para cualquier otro); esto
// solo evita mostrar acciones que terminarían en 403, mismo patrón que
// ROLES_PUEDEN_AGREGAR en Ubicaciones.tsx.
const ROLES_PUEDEN_GESTIONAR: readonly string[] = [ROLES.CLIENTE_FINAL];

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

  // Extraída como función nombrada (no solo dentro del useEffect) para
  // poder recargar el listado después de eliminar un panel, mismo patrón
  // que cargarDispositivos en Dispositivos.tsx.
  function cargarPaneles() {
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaneles>("/paneles", {
      params: { busqueda: busqueda || undefined },
    })
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado");
      })
      .finally(() => setLoading(false));
  }

  useEffect(cargarPaneles, [busqueda]);

  // CA1: "si el usuario no tiene paneles creados" se refiere a que no
  // existe NINGUNO, no a que la búsqueda no encontró nada -por eso el
  // mensaje con el botón "Crear panel" solo aplica sin filtro activo.
  const sinPanelesCreados = !loading && !busqueda && data?.items.length === 0;

  // HU25 CA3/CA4: mismo patrón que Dispositivos.tsx (desactivar/reactivar)
  // -el item pendiente de confirmar en un state, el id en progreso en
  // otro, un handler async que llama al backend y recarga el listado-.
  const [panelAEliminar, setPanelAEliminar] = useState<PanelListItem | null>(null);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);
  const [errorEliminar, setErrorEliminar] = useState<string | null>(null);

  /** HU25 CA4: elimina PERMANENTEMENTE el panel (no hay soft-delete, a
   *  diferencia de Dispositivos.tsx) y refresca el listado. */
  async function confirmarEliminarPanel() {
    if (!panelAEliminar) return;
    setEliminandoId(panelAEliminar.id_pnl);
    setErrorEliminar(null);
    try {
      await apiFetch<{ mensaje: string }>(`/paneles/${panelAEliminar.id_pnl}`, {
        method: "DELETE",
      });
      setPanelAEliminar(null);
      setMensajeExito("Panel eliminado correctamente");
      cargarPaneles();
    } catch (err) {
      setErrorEliminar(err instanceof ApiError ? err.message : "No se pudo eliminar el panel");
    } finally {
      setEliminandoId(null);
    }
  }

  // HU24/HU25: crear y editar panel viven como drawer lateral, en vez de
  // rutas propias (/paneles/nuevo, /paneles/:id/editar) -mismo patrón que
  // el resto del sistema para crear/editar-. `panelEnEdicion` es null al
  // crear y el panel a editar cuando corresponde: un solo formulario para
  // ambos casos, igual que ya lo eran CrearPanel.tsx/EditarPanel.tsx entre
  // sí (comparten el mismo único campo).
  const [panelEnEdicion, setPanelEnEdicion] = useState<PanelListItem | null>(null);
  const [panelDrawerAbierto, setPanelDrawerAbierto] = useState(false);
  const [nombrePanel, setNombrePanel] = useState("");
  const [guardandoPanel, setGuardandoPanel] = useState(false);
  const [errorPanel, setErrorPanel] = useState("");

  function abrirCrearPanel() {
    setPanelEnEdicion(null);
    setNombrePanel("");
    setErrorPanel("");
    setPanelDrawerAbierto(true);
  }

  function abrirEditarPanel(panel: PanelListItem) {
    setPanelEnEdicion(panel);
    setNombrePanel(panel.nmbr);
    setErrorPanel("");
    setPanelDrawerAbierto(true);
  }

  /** CA2 (HU24) / CA2 (HU25). */
  async function handleSubmitPanel(e: FormEvent) {
    e.preventDefault();

    if (!nombrePanel.trim()) {
      setErrorPanel("El nombre del panel es obligatorio");
      return;
    }

    setGuardandoPanel(true);
    setErrorPanel("");
    try {
      if (panelEnEdicion) {
        const respuesta = await apiFetch<{ mensaje: string }>(`/paneles/${panelEnEdicion.id_pnl}`, {
          method: "PUT",
          body: { nmbr: nombrePanel.trim() },
        });
        setPanelDrawerAbierto(false);
        setMensajeExito(respuesta.mensaje);
        cargarPaneles();
      } else {
        // HU24 CA3: "tras guardar, redirige al panel recién creado (vacío,
        // con 'Añadir ubicaciones' visible)" -a diferencia de editar, que
        // se queda en el listado-.
        const respuesta = await apiFetch<{ mensaje: string; panel: PanelCreado }>("/paneles", {
          method: "POST",
          body: { nmbr: nombrePanel.trim() },
        });
        setPanelDrawerAbierto(false);
        navigate(`/paneles/${respuesta.panel.id_pnl}`, {
          state: { mensaje: respuesta.mensaje },
        });
      }
    } catch (err) {
      setErrorPanel(
        err instanceof ApiError
          ? err.message
          : `No se pudo ${panelEnEdicion ? "actualizar" : "crear"} el panel`,
      );
    } finally {
      setGuardandoPanel(false);
    }
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="paneles" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="franja-superior flex justify-end p-4 md:p-6 pb-0">
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

              {ROLES_PUEDEN_GESTIONAR.includes(rol ?? "") && (
                <div className="flex gap-3">
                  <button
                    onClick={abrirCrearPanel}
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

              {errorEliminar && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {errorEliminar}
                </div>
              )}

              {sinPanelesCreados ? (
                <div className="flex flex-col items-center justify-center gap-4 py-16 px-6 text-center">
                  <p className="text-gray-600 dark:text-gray-300">Aún no tienes paneles creados</p>
                  {ROLES_PUEDEN_GESTIONAR.includes(rol ?? "") && (
                    <button
                      onClick={abrirCrearPanel}
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
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-xs sm:text-sm font-medium whitespace-nowrap text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                                >
                                  Abrir
                                </Link>
                                {ROLES_PUEDEN_GESTIONAR.includes(rol ?? "") && (
                                  <>
                                    {/* HU25 CA1: abre el drawer de edición con el nombre precargado. */}
                                    <button
                                      type="button"
                                      onClick={() => abrirEditarPanel(p)}
                                      className="inline-flex items-center justify-center px-3 py-1.5 text-xs sm:text-sm font-medium whitespace-nowrap text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                                    >
                                      Editar
                                    </button>
                                    {/* HU25 CA3: abre el diálogo de confirmación, no elimina directo. */}
                                    <button
                                      onClick={() => setPanelAEliminar(p)}
                                      className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 bg-transparent border border-red-200 dark:border-red-800/40 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-all"
                                    >
                                      Eliminar
                                    </button>
                                  </>
                                )}
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

      {/* HU25 CA3/CA4: "muestra un mensaje de confirmación preguntando si
          desea eliminar el panel y todo su contenido" -la eliminación es
          permanente e irreversible (DETALLES DE LA CONVERSACIÓN), así que
          variante="peligro" (default) es la correcta acá. */}
      {panelAEliminar && (
        <ConfirmarEliminacionModal
          titulo={`Eliminar panel '${panelAEliminar.nmbr}'`}
          mensaje="Esta acción eliminará el panel junto con todas sus ubicaciones y widgets asociados. Los datos de telemetría no se ven afectados. Esta acción no se puede deshacer."
          confirmando={eliminandoId === panelAEliminar.id_pnl}
          onConfirmar={confirmarEliminarPanel}
          onCancelar={() => setPanelAEliminar(null)}
        />
      )}

      {/* HU24/HU25: drawer de crear/editar panel, un solo formulario de
          un campo (Nombre) para ambos casos. */}
      <DrawerPanel
        abierto={panelDrawerAbierto}
        onCerrar={() => setPanelDrawerAbierto(false)}
        titulo={panelEnEdicion ? "Editar panel" : "Crear panel"}
      >
        <form onSubmit={handleSubmitPanel} className="flex flex-col h-full">
          <p className="text-sm text-gray-600 dark:text-gray-300 mb-5">
            {panelEnEdicion
              ? "Modifica el nombre de tu tablero personalizado."
              : "Dale un nombre a tu nuevo tablero personalizado."}
          </p>

          {errorPanel && (
            <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
              {errorPanel}
            </div>
          )}

          <div>
            <label className={LABEL_CLASE} htmlFor="nmbr-panel">
              Nombre del panel <span className="text-red-500">*</span>
            </label>
            <input
              id="nmbr-panel"
              type="text"
              maxLength={NOMBRE_MAX_LARGO}
              value={nombrePanel}
              onChange={(e) => setNombrePanel(e.target.value)}
              placeholder="Resumen de estaciones"
              autoFocus
              className={INPUT_CLASE}
            />
            <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
              {nombrePanel.length}/{NOMBRE_MAX_LARGO}
            </p>
          </div>

          <div className="mt-auto pt-6 flex gap-3">
            <button
              type="button"
              onClick={() => setPanelDrawerAbierto(false)}
              className="flex-1 px-4 py-2.5 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
            >
              Cancelar
            </button>
            <button
              type="submit"
              disabled={guardandoPanel}
              className="flex-1 px-4 py-2.5 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
            >
              {guardandoPanel ? "Guardando..." : "Guardar"}
            </button>
          </div>
        </form>
      </DrawerPanel>
    </div>
  );
}
