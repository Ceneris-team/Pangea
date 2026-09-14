import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface AlarmaListItem {
  id_alrm: number;
  nmbr: string;
  parametro_nombre: string;
  condicion: string | null;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: AlarmaListItem[];
}

// HU30: panel de configuración de notificaciones de una alarma.
interface DestinatarioNotificacion {
  crr: string;
}

interface NotificacionesAlarma {
  id_alrm: number;
  nmbr: string;
  canales_disponibles: string[];
  canal_email_activo: boolean;
  destinatarios: DestinatarioNotificacion[];
}

// HU29 CA5: edición de la condición de disparo de una alarma existente.
interface CondicionAlarmaDetalle {
  id_alrm: number;
  nmbr: string;
  unidad: string;
  oprdr: string | null;
  vlr_umbrl: number | null;
}

const OPERADORES_CONDICION = [">", ">=", "<", "<=", "="] as const;

const POR_PAGINA = 10;

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);
  return debounced;
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

  // CA3: búsqueda por nombre, insensible a mayúsculas/minúsculas.
  const [busquedaInput, setBusquedaInput] = useState("");
  const busqueda = useDebouncedValue(busquedaInput, 400);

  // CA2: filtro por estado.
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // HU30: panel de configuración de notificaciones, abierto sobre una
  // alarma del listado.
  const [alarmaEnPanel, setAlarmaEnPanel] = useState<{ id_alrm: number; nmbr: string } | null>(
    null
  );
  const [notificaciones, setNotificaciones] = useState<NotificacionesAlarma | null>(null);
  const [cargandoPanel, setCargandoPanel] = useState(false);
  const [guardandoPanel, setGuardandoPanel] = useState(false);
  const [errorPanel, setErrorPanel] = useState("");
  const [mensajePanel, setMensajePanel] = useState("");

  function abrirPanelNotificaciones(alarma: { id_alrm: number; nmbr: string }) {
    setAlarmaEnPanel(alarma);
    setNotificaciones(null);
    setErrorPanel("");
    setMensajePanel("");
    setCargandoPanel(true);

    apiFetch<NotificacionesAlarma>(`/alarmas/${alarma.id_alrm}/notificaciones`)
      .then(setNotificaciones)
      .catch((err) =>
        setErrorPanel(
          err instanceof ApiError ? err.message : "No se pudo cargar la configuración"
        )
      )
      .finally(() => setCargandoPanel(false));
  }

  function cerrarPanelNotificaciones() {
    setAlarmaEnPanel(null);
    setNotificaciones(null);
  }

  // CA2/CA4: activar o desactivar el canal de correo y GUARDAR.
  async function guardarNotificaciones(canalEmailActivo: boolean) {
    if (!alarmaEnPanel) return;

    setGuardandoPanel(true);
    setErrorPanel("");
    setMensajePanel("");
    try {
      const resp = await apiFetch<{ mensaje: string; notificaciones: NotificacionesAlarma }>(
        `/alarmas/${alarmaEnPanel.id_alrm}/notificaciones`,
        { method: "PUT", body: { canal_email_activo: canalEmailActivo } }
      );
      setNotificaciones(resp.notificaciones);
      setMensajePanel(resp.mensaje);
    } catch (err) {
      setErrorPanel(
        err instanceof ApiError ? err.message : "No se pudo guardar la configuración"
      );
    } finally {
      setGuardandoPanel(false);
    }
  }

  // HU29 CA5: editar la condición de disparo de una alarma existente.
  const [alarmaEnEdicion, setAlarmaEnEdicion] = useState<{ id_alrm: number; nmbr: string } | null>(
    null
  );
  const [operadorEdicion, setOperadorEdicion] = useState<string>(">");
  const [umbralEdicion, setUmbralEdicion] = useState("");
  const [unidadEdicion, setUnidadEdicion] = useState("");
  const [cargandoEdicion, setCargandoEdicion] = useState(false);
  const [guardandoEdicion, setGuardandoEdicion] = useState(false);
  const [errorEdicion, setErrorEdicion] = useState("");

  function abrirEdicionCondicion(alarma: { id_alrm: number; nmbr: string }) {
    setAlarmaEnEdicion(alarma);
    setErrorEdicion("");
    setCargandoEdicion(true);

    apiFetch<CondicionAlarmaDetalle>(`/alarmas/${alarma.id_alrm}/condicion`)
      .then((res) => {
        setOperadorEdicion(res.oprdr ?? ">");
        setUmbralEdicion(res.vlr_umbrl !== null ? String(res.vlr_umbrl) : "");
        setUnidadEdicion(res.unidad);
      })
      .catch((err) =>
        setErrorEdicion(err instanceof ApiError ? err.message : "No se pudo cargar la condición")
      )
      .finally(() => setCargandoEdicion(false));
  }

  function cerrarEdicionCondicion() {
    setAlarmaEnEdicion(null);
  }

  // CA5: "ACTUALIZAR" guarda los nuevos valores.
  async function actualizarCondicion() {
    if (!alarmaEnEdicion) return;
    if (umbralEdicion.trim() === "" || Number.isNaN(Number(umbralEdicion))) {
      setErrorEdicion("Indica el valor umbral de la condición");
      return;
    }

    setGuardandoEdicion(true);
    setErrorEdicion("");
    try {
      const resp = await apiFetch<{ mensaje: string }>(
        `/alarmas/${alarmaEnEdicion.id_alrm}/condicion`,
        { method: "PUT", body: { oprdr: operadorEdicion, vlr_umbrl: Number(umbralEdicion) } }
      );
      setAlarmaEnEdicion(null);
      setMensajeExito(resp.mensaje);
      cargarAlarmas();
    } catch (err) {
      setErrorEdicion(
        err instanceof ApiError ? err.message : "No se pudo actualizar la condición"
      );
    } finally {
      setGuardandoEdicion(false);
    }
  }

  useEffect(() => {
    setPagina(1);
  }, [busqueda, estado]);

  function cargarAlarmas() {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/alarmas", {
      params: {
        busqueda: busqueda || undefined,
        estado: estado || undefined,
        pagina,
        por_pagina: POR_PAGINA,
      },
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
  }

  useEffect(cargarAlarmas, [busqueda, estado, pagina]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;
  const inicioRango = data ? (data.pagina - 1) * data.por_pagina + 1 : 0;
  const finRango = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  const hayFiltrosActivos = busquedaInput !== "" || estado !== "";

  function limpiarFiltros() {
    setBusquedaInput("");
    setEstado("");
  }

  // Detalle de la HU: el mensaje "Aún no tienes alarmas configuradas" solo
  // aplica cuando el usuario no tiene NINGUNA alarma -no cuando un filtro
  // simplemente no encontró resultados-, así que se distingue por si hay
  // filtros activos.
  const sinAlarmasConfiguradas = !loading && data?.total === 0 && !hayFiltrosActivos;
  const sinResultadosPorFiltro = !loading && data?.total === 0 && hayFiltrosActivos;

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
                  Alarmas configuradas sobre tus parámetros de monitoreo.
                </p>
              </div>

              <button
                onClick={() => navigate("/alarmas/nueva")}
                className="inline-flex items-center px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
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
                <button
                  onClick={() => setMensajeExito(null)}
                  className="text-xs font-medium underline"
                >
                  Cerrar
                </button>
              </div>
            )}

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10">
              {/* Barra de filtros */}
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
                    placeholder="Buscar por nombre..."
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400"
                  />
                </div>

                <div className="flex w-full lg:w-auto gap-3">
                  <select
                    value={estado}
                    onChange={(e) => setEstado(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los estados</option>
                    <option value="Activa">Activa</option>
                    <option value="Disparada">Disparada</option>
                    <option value="Inactiva">Inactiva</option>
                  </select>

                  {hayFiltrosActivos && (
                    <button
                      onClick={limpiarFiltros}
                      className="px-3 py-2.5 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors whitespace-nowrap"
                    >
                      Limpiar filtros
                    </button>
                  )}
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {/* Tabla */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Condición</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {sinAlarmasConfiguradas && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Aún no tienes alarmas configuradas.
                        </td>
                      </tr>
                    )}

                    {sinResultadosPorFiltro && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No se encontraron alarmas con ese criterio.
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
                          <td className="px-6 py-4">{a.parametro_nombre}</td>
                          <td className="px-6 py-4">{a.condicion ?? "Sin condición configurada"}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                a.estd === "Disparada"
                                  ? "bg-red-500/15 text-red-600 dark:text-red-400 border-red-500/30"
                                  : a.estd === "Activa"
                                    ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                    : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {a.estd === "Activa" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {a.estd === "Disparada" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-red-500"></span>
                              )}
                              {a.estd}
                            </span>
                          </td>
                          {/* Eliminar/activar-desactivar son HUs aparte;
                              "Editar condición" es HU29 CA5 y
                              "Configurar notificaciones" es HU30. */}
                          <td className="px-6 py-4 text-right whitespace-nowrap space-x-2">
                            <button
                              onClick={() => abrirEdicionCondicion(a)}
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-black/5 dark:bg-white/5 hover:bg-black/10 dark:hover:bg-white/10 border border-black/10 dark:border-white/20 rounded-lg transition-colors"
                            >
                              Editar condición
                            </button>
                            <button
                              onClick={() => abrirPanelNotificaciones(a)}
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-lg transition-colors"
                            >
                              Configurar notificaciones
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {data && data.total > 0 && (
                <div className="p-5 border-t border-black/10 dark:border-white/10 flex items-center justify-between">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    Mostrando <span className="font-semibold text-gray-900 dark:text-white">{inicioRango}</span> a{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{finRango}</span> de{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span> registros
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

      {/* HU30 CA1: panel de configuración de notificaciones de una alarma. */}
      {alarmaEnPanel && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <div className="p-6 border-b border-gray-100 dark:border-gray-700">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                Configurar notificaciones
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-300">{alarmaEnPanel.nmbr}</p>
            </div>

            <div className="p-6 space-y-4">
              {cargandoPanel && (
                <div className="flex justify-center items-center gap-2 text-sm text-gray-600 dark:text-gray-300 py-4">
                  <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                  <span>Cargando configuración...</span>
                </div>
              )}

              {errorPanel && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                  {errorPanel}
                </div>
              )}

              {mensajePanel && (
                <div className="p-3 bg-[#ccff00]/20 border border-[#ccff00]/40 text-[#5a7000] dark:text-[#ccff00] text-sm rounded-lg">
                  {mensajePanel}
                </div>
              )}

              {notificaciones && (
                <div className="rounded-xl border border-black/10 dark:border-white/10 p-4 flex items-start justify-between gap-4">
                  <div>
                    <p className="text-sm font-semibold text-gray-900 dark:text-white">
                      Correo electrónico
                    </p>
                    <p className="text-xs text-gray-500 dark:text-gray-400">
                      {notificaciones.canal_email_activo && notificaciones.destinatarios.length > 0
                        ? `Se notifica a ${notificaciones.destinatarios.map((d) => d.crr).join(", ")}`
                        : "No se enviarán notificaciones por este canal."}
                    </p>
                  </div>

                  {/* CA2/CA4: activar o desactivar el canal de correo. */}
                  <button
                    type="button"
                    role="switch"
                    aria-checked={notificaciones.canal_email_activo}
                    disabled={guardandoPanel}
                    onClick={() => guardarNotificaciones(!notificaciones.canal_email_activo)}
                    className={`relative inline-flex h-6 w-11 shrink-0 items-center rounded-full transition-colors disabled:opacity-50 ${
                      notificaciones.canal_email_activo
                        ? "bg-[#ccff00]"
                        : "bg-black/20 dark:bg-white/20"
                    }`}
                  >
                    <span
                      className={`inline-block h-4 w-4 transform rounded-full bg-white transition-transform ${
                        notificaciones.canal_email_activo ? "translate-x-6" : "translate-x-1"
                      }`}
                    />
                  </button>
                </div>
              )}
            </div>

            <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end">
              <button
                type="button"
                onClick={cerrarPanelNotificaciones}
                className="px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
              >
                Cerrar
              </button>
            </div>
          </div>
        </div>
      )}

      {/* HU29 CA5: editar la condición de disparo de una alarma. */}
      {alarmaEnEdicion && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <div className="p-6 border-b border-gray-100 dark:border-gray-700">
              <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                Editar condición
              </h2>
              <p className="text-sm text-gray-600 dark:text-gray-300">{alarmaEnEdicion.nmbr}</p>
            </div>

            <div className="p-6 space-y-4">
              {cargandoEdicion && (
                <div className="flex justify-center items-center gap-2 text-sm text-gray-600 dark:text-gray-300 py-4">
                  <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                  <span>Cargando condición...</span>
                </div>
              )}

              {errorEdicion && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                  {errorEdicion}
                </div>
              )}

              {!cargandoEdicion && (
                <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                      Condición
                    </label>
                    <select
                      value={operadorEdicion}
                      onChange={(e) => setOperadorEdicion(e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none cursor-pointer"
                    >
                      {OPERADORES_CONDICION.map((op) => (
                        <option key={op} value={op}>
                          {op}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                      Valor umbral{unidadEdicion ? ` (${unidadEdicion})` : ""}
                    </label>
                    <input
                      type="number"
                      step="any"
                      value={umbralEdicion}
                      onChange={(e) => setUmbralEdicion(e.target.value)}
                      className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                    />
                  </div>
                </div>
              )}
            </div>

            <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-between gap-3">
              <button
                type="button"
                onClick={cerrarEdicionCondicion}
                className="px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="button"
                onClick={actualizarCondicion}
                disabled={cargandoEdicion || guardandoEdicion}
                className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
              >
                {guardandoEdicion ? "Actualizando..." : "Actualizar"}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
