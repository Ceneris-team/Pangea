import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface DispositivoListItem {
  id_dspstv: number;
  nmbr: string;
  mrc: string;
  ubicacion_nombre: string;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: DispositivoListItem[];
}

interface UbicacionListItem {
  id_ubccn: number;
  nmbr: string;
}

const POR_PAGINA = 10;

// HU11: "Solo los roles Administrador y Técnico CENERIS pueden añadir
// dispositivos". El backend lo exige igual vía require_permiso
// ('Dispositivos', EDICION); esto solo evita mostrar un botón que
// terminaría en 403. Mismo criterio que ROLES_PUEDEN_AGREGAR en
// Ubicaciones.tsx (HU08).
const ROLES_PUEDEN_AGREGAR: readonly string[] = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);
  return debounced;
}

export default function Dispositivos() {
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // HU11 CA3: al volver del formulario, el listado muestra el mensaje de
  // éxito junto con el dispositivo recién registrado. Mismo patrón que
  // Ubicaciones.tsx usa tras HU08.
  const [mensajeExito, setMensajeExito] = useState<string | null>(
    (location.state as { mensaje?: string } | null)?.mensaje ?? null
  );

  // Se limpia el state de navegación para que el mensaje no reaparezca si
  // el usuario recarga o vuelve atrás.
  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  // Estado para el Modo Oscuro (mismo patrón que Ubicaciones.tsx)
  const [isDarkMode, setIsDarkMode] = useState(false);

  // CA HU10: búsqueda por nombre o marca, insensible a mayúsculas/minúsculas
  const [busquedaInput, setBusquedaInput] = useState("");
  const busqueda = useDebouncedValue(busquedaInput, 400);

  // CA HU10: filtro por ubicación y por estado
  const [idUbccn, setIdUbccn] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // El selector de "Ubicación" se puebla con GET /ubicaciones (HU07 ya
  // existente): no hace falta otro endpoint para esto.
  const [ubicaciones, setUbicaciones] = useState<UbicacionListItem[]>([]);

  useEffect(() => {
    apiFetch<{ items: UbicacionListItem[] }>("/ubicaciones", {
      params: { por_pagina: 100 },
    })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]));
  }, []);

  useEffect(() => {
    setPagina(1);
  }, [busqueda, idUbccn, estado]);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/dispositivos", {
      params: {
        busqueda: busqueda || undefined,
        id_ubccn: idUbccn || undefined,
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
  }, [busqueda, idUbccn, estado, pagina]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;
  const inicioRango = data ? (data.pagina - 1) * data.por_pagina + 1 : 0;
  const finRango = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  const hayFiltrosActivos = busquedaInput !== "" || idUbccn !== "" || estado !== "";

  function limpiarFiltros() {
    setBusquedaInput("");
    setIdUbccn("");
    setEstado("");
  }

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden">

        {/* SIDEBAR */}
        <Sidebar onLogout={logout} activo="dispositivos" rol={rol} />

        {/* ÁREA PRINCIPAL */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* TOP NAVBAR */}
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
            />

          {/* CONTENIDO DE LA PÁGINA (Dispositivos) */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Gestión de Dispositivos</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Listado centralizado de dispositivos de monitoreo registrados.
                </p>
              </div>

              {/* HU11 CA1: punto de entrada al formulario de registro. */}
              {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && (
                <button
                  onClick={() => navigate("/dispositivos/nueva")}
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
                  Añadir dispositivo
                </button>
              )}
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

            <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700">
              {/* Barra de filtros */}
              <div className="p-5 flex flex-col lg:flex-row gap-3 items-center justify-between border-b border-gray-100 dark:border-gray-700">
                <div className="relative w-full lg:w-80">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 20 20" xmlns="http://www.w3.org/2000/svg">
                      <path stroke="currentColor" strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z" />
                    </svg>
                  </div>
                  <input
                    type="text"
                    value={busquedaInput}
                    onChange={(e) => setBusquedaInput(e.target.value)}
                    placeholder="Buscar por nombre o marca..."
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400 dark:placeholder-gray-500"
                  />
                </div>

                <div className="flex w-full lg:w-auto gap-3">
                  <select
                    value={idUbccn}
                    onChange={(e) => setIdUbccn(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todas las ubicaciones</option>
                    {ubicaciones.map((u) => (
                      <option key={u.id_ubccn} value={u.id_ubccn}>
                        {u.nmbr}
                      </option>
                    ))}
                  </select>

                  <select
                    value={estado}
                    onChange={(e) => setEstado(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los estados</option>
                    <option value="Activo">Activo</option>
                    <option value="Inactivo">Inactivo</option>
                  </select>

                  {hayFiltrosActivos && (
                    <button
                      onClick={limpiarFiltros}
                      className="px-3 py-2.5 text-sm font-medium rounded-xl border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors whitespace-nowrap"
                    >
                      Limpiar filtros
                    </button>
                  )}
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {/* Tabla */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                  <thead className="text-xs text-gray-500 dark:text-gray-400 uppercase bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Marca</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Ubicación</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          No se encontraron dispositivos con ese criterio.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((d) => (
                        <tr
                          key={d.id_dspstv}
                          className="bg-white dark:bg-[#2d3748] border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors group"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{d.nmbr}</td>
                          <td className="px-6 py-4">{d.mrc}</td>
                          <td className="px-6 py-4">{d.ubicacion_nombre}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                d.estd === "Activo"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600"
                              }`}
                            >
                              {d.estd === "Activo" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#8fb300] dark:bg-[#ccff00]"></span>
                              )}
                              {d.estd}
                            </span>
                          </td>
                          {/* Acciones: placeholder, se implementa en HU18/HU19 (Sprint 3) */}
                          <td className="px-6 py-4 text-right">
                            <button
                              disabled
                              title="Próximamente"
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-gray-200 dark:focus:ring-gray-800 disabled:opacity-50 disabled:hover:bg-white dark:disabled:hover:bg-transparent transition-all"
                            >
                              <svg className="w-4 h-4 mr-2 text-gray-500 dark:text-gray-400" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                              Editar
                            </button>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {data && (
                <div className="p-5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between">
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    Mostrando <span className="font-semibold text-gray-900 dark:text-white">{inicioRango}</span> a{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{finRango}</span> de{" "}
                    <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span> registros
                  </span>
                  <div className="flex gap-2">
                    <button
                      onClick={() => setPagina((p) => Math.max(1, p - 1))}
                      disabled={pagina <= 1}
                      className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                    >
                      Anterior
                    </button>
                    <button
                      onClick={() => setPagina((p) => Math.min(totalPaginas, p + 1))}
                      disabled={pagina >= totalPaginas}
                      className="px-3 py-1.5 text-sm rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
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
