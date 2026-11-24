import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import NotificacionesAlarma from "../components/NotificacionesAlarma";
import EditarAlarma from "../components/EditarAlarma";
import EstadoLecturasAlarma, { type EstadoDispositivoAlarma } from "../components/EstadoLecturasAlarma";

interface AlarmaListItem {
  id_alrm: number;
  nmbr: string;
  parametro_nombre: string;
  condicion: string | null;
  estd: string;
  correos_habilitados?: boolean;
  dispositivos?: EstadoDispositivoAlarma[];
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: AlarmaListItem[];
}

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
  const { nombreCompleto, rol, logout, puedeEditarAlarmas } = useAuth();
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

  const consulta = JSON.stringify([busqueda, estado, pagina]);
  const [resultado, setResultado] = useState<{ consulta: string; datos: ListadoPaginado } | null>(null);
  const data = resultado?.consulta === consulta ? resultado.datos : null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [alarmaSeleccionada, setAlarmaSeleccionada] = useState<AlarmaListItem | null>(null);
  const [version, setVersion] = useState(0);
  const [editando, setEditando] = useState<number | null>(null);

  useEffect(() => {
    const intervalo = window.setInterval(() => setVersion(v => v + 1), 30_000);
    return () => window.clearInterval(intervalo);
  }, []);

  // Los setState van en microtarea y no síncronos dentro del efecto (regla
  // react-hooks/set-state-in-effect de dev), igual que en ColaIngesta.tsx.
  useEffect(() => {
    queueMicrotask(() => setPagina(1));
  }, [busqueda, estado]);

  function cargarAlarmas() {
    let cancelado = false;
    queueMicrotask(() => {
      if (cancelado) return;
      setLoading(true);
      setError(null);
    });

    apiFetch<ListadoPaginado>("/alarmas", {
      params: {
        busqueda: busqueda || undefined,
        estado: estado || undefined,
        pagina,
        por_pagina: POR_PAGINA,
      },
    })
      .then((res) => {
        if (!cancelado) setResultado({ consulta, datos: res });
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

  useEffect(cargarAlarmas, [busqueda, estado, pagina, version, consulta]);

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
                  Alarmas compartidas de los proyectos a los que tienes acceso. Los permisos del proyecto determinan quién puede modificarlas.
                </p>
              </div>

              <div className="flex flex-wrap gap-2">
              <button type="button" onClick={() => setVersion(v => v + 1)} disabled={loading} className="rounded-xl border border-black/20 px-4 py-2 text-sm text-gray-700 dark:border-white/20 dark:text-gray-200 disabled:opacity-50">Actualizar</button>
              {puedeEditarAlarmas && <button
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
              </button>}
              </div>
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
              {loading && data && <p role="status" className="px-5 py-2 text-xs text-gray-600 dark:text-gray-300">Actualizando alarmas…</p>}
              <div className="overflow-x-auto">
                <table className="tabla-alarmas w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Condición</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Regla</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado de lecturas</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && !data && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {sinAlarmasConfiguradas && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Aún no tienes alarmas configuradas.
                        </td>
                      </tr>
                    )}

                    {sinResultadosPorFiltro && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No se encontraron alarmas con ese criterio.
                        </td>
                      </tr>
                    )}

                    {data?.items.map((a) => (
                        <tr
                          key={a.id_alrm}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td data-label="Nombre" className="px-6 py-4 font-medium text-gray-900 dark:text-white">{a.nmbr}</td>
                          <td data-label="Parámetro" className="px-6 py-4">{a.parametro_nombre}</td>
                          <td data-label="Condición" className="px-6 py-4">{a.condicion ?? "Sin condición configurada"}</td>
                          <td data-label="Regla" className="px-6 py-4">
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
                              {a.estd === "Activa" ? "Habilitada" : "Pausada"}
                            </span>
                          </td>
                          <td data-label="Estado de lecturas" className="px-6 py-4"><EstadoLecturasAlarma regla={a.estd} dispositivos={a.dispositivos} /></td>
                          {/* HT-14: destinatarios e historial de esta alarma. */}
                          <td data-label="Acciones" className="px-6 py-4 text-right whitespace-nowrap">
                            {puedeEditarAlarmas && <button type="button" onClick={() => setEditando(a.id_alrm)} className="mr-2 rounded-lg border border-black/20 px-3 py-1.5 text-sm dark:border-white/20">Editar condiciones</button>}
                            <button
                              onClick={() => setAlarmaSeleccionada(a)}
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/5 dark:hover:bg-white/5"
                            >
                              Notificaciones
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {data && data.total > 0 && (
                <div className="p-5 border-t border-black/10 dark:border-white/10 flex flex-wrap gap-3 items-center justify-between">
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
            <p className="mt-3 text-xs text-gray-600 dark:text-gray-400">El estado corresponde a la última lectura evaluada. Consulta su fecha para comprobar la antigüedad. Se actualiza cada 30 segundos.</p>
            {editando !== null && <EditarAlarma id={editando} onCerrar={() => setEditando(null)} onGuardar={() => { setEditando(null); setVersion(v => v + 1); setMensajeExito("Condiciones guardadas. Se evaluarán con la siguiente lectura nueva."); }} />}
            {alarmaSeleccionada && <NotificacionesAlarma key={alarmaSeleccionada.id_alrm}
              alarma={alarmaSeleccionada} puedeEditar={puedeEditarAlarmas} onClose={() => setAlarmaSeleccionada(null)}
              onUpdate={() => {
                setAlarmaSeleccionada(a => a ? { ...a, estd: a.estd === "Activa" ? "Inactiva" : "Activa" } : null);
                setVersion(v => v + 1);
              }} />}
          </main>
        </div>
      </div>
    </div>
  );
}
