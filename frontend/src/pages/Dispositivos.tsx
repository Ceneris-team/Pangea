import { useEffect, useState, type FormEvent } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import ConfirmarEliminacionModal from "../components/ConfirmarEliminacionModal";
import SelectorRangoFechas from "../components/SelectorRangoFechas";
import {
  formatearFechaHoraEnZona,
  rangoUltimos7Dias,
  type RangoFechas,
} from "../utils/fechas";

interface DispositivoListItem {
  id_dspstv: number;
  nmbr: string;
  mrc: string;
  ubicacion_nombre: string;
  estd: string;
}

/** HU19: respuesta de GET /dispositivos/{id}/estadisticas. */
interface EstadisticasDispositivo {
  total_recibidos: number;
  total_procesados: number;
  total_fallidos: number;
  ultima_fecha_recepcion: string | null;
  fecha_inicio: string;
  fecha_fin: string;
  id_cnxn: number;
  id_ubccn: number;
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

interface ConexionFTPOption {
  id_cnxn: number;
  nmbr: string;
}

interface DispositivoForm {
  nmbr: string;
  mrc: string;
  mdl: string;
  id_ubccn: string;
  id_cnxn: string;
}

const FORM_VACIO: DispositivoForm = {
  nmbr: "",
  mrc: "",
  mdl: "",
  id_ubccn: "",
  id_cnxn: "",
};

const POR_PAGINA = 10;

// HU11: "Solo los roles Administrador y Técnico CENERIS pueden añadir
// dispositivos". El backend lo exige igual vía require_permiso
// ('Dispositivos', EDICION); esto solo evita mostrar un botón que
// terminaría en 403. Mismo criterio que ROLES_PUEDEN_AGREGAR en
// Ubicaciones.tsx (HU08).
//
// HU19 usa el mismo conjunto de roles para "Ver estadísticas" ('Solo los
// roles Técnico CENERIS y Administrador tienen acceso a esta vista'), así
// que se reusa esta constante en vez de duplicarla.
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
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();
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

  function cargarDispositivos() {
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
  }

  useEffect(cargarDispositivos, [busqueda, idUbccn, estado, pagina]);

  // HU11: formulario de "Añadir dispositivo" como ventana emergente sobre
  // el listado (mismo patrón que Conexiones FTP y Parámetros).
  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [form, setForm] = useState<DispositivoForm>(FORM_VACIO);
  const [ubicacionesActivas, setUbicacionesActivas] = useState<UbicacionListItem[]>([]);
  const [conexiones, setConexiones] = useState<ConexionFTPOption[]>([]);
  const [guardandoDispositivo, setGuardandoDispositivo] = useState(false);
  const [errorFormulario, setErrorFormulario] = useState("");

  // HU18: desactivar/reactivar dispositivo, mismo patrón que Parámetros.tsx,
  // con el modal de confirmación con cuenta regresiva.
  const [dispositivoADesactivar, setDispositivoADesactivar] = useState<DispositivoListItem | null>(null);
  const [desactivandoId, setDesactivandoId] = useState<number | null>(null);
  const [errorDesactivar, setErrorDesactivar] = useState<string | null>(null);

  const [dispositivoAReactivar, setDispositivoAReactivar] = useState<DispositivoListItem | null>(null);
  const [reactivandoId, setReactivandoId] = useState<number | null>(null);
  const [errorReactivar, setErrorReactivar] = useState<string | null>(null);

  // HU19: panel de estadísticas de un dispositivo. dispositivoEstadisticas
  // no nulo controla si el modal está abierto (mismo patrón que los otros
  // modales de esta página).
  const [dispositivoEstadisticas, setDispositivoEstadisticas] = useState<DispositivoListItem | null>(
    null,
  );
  const [estadisticas, setEstadisticas] = useState<EstadisticasDispositivo | null>(null);
  const [cargandoEstadisticas, setCargandoEstadisticas] = useState(false);
  const [errorEstadisticas, setErrorEstadisticas] = useState<string | null>(null);

  // CA2: rango de fechas del panel, con su propia selección/filtro aplicado
  // (mismo patrón que HU12 en ConsultaDatos.tsx). Detalle de la HU: el
  // rango por defecto son los últimos 7 días.
  const [seleccionFechasEstadisticas, setSeleccionFechasEstadisticas] =
    useState<RangoFechas>(rangoUltimos7Dias);
  const [filtroFechasEstadisticas, setFiltroFechasEstadisticas] =
    useState<RangoFechas>(rangoUltimos7Dias);

  // CA1: el selector de Ubicación solo ofrece ubicaciones Activas.
  useEffect(() => {
    apiFetch<{ items: UbicacionListItem[] }>("/ubicaciones", {
      params: { estado: "Activa", por_pagina: 100 },
    })
      .then((res) => setUbicacionesActivas(res.items))
      .catch(() => setUbicacionesActivas([]));
  }, []);

  // CA1: el selector de Conexión FTP reusa GET /conexiones-ftp (HU05).
  useEffect(() => {
    apiFetch<{ items: ConexionFTPOption[] }>("/conexiones-ftp", {
      params: { por_pagina: 100 },
    })
      .then((res) => setConexiones(res.items))
      .catch(() => setConexiones([]));
  }, []);

  function abrirFormulario() {
    setForm(FORM_VACIO);
    setErrorFormulario("");
    setMostrarFormulario(true);
  }

  /** CA4: descarta el formulario sin llamar al backend. */
  function cerrarFormulario() {
    setMostrarFormulario(false);
  }

  function actualizarCampoDispositivo<K extends keyof DispositivoForm>(campo: K, valor: DispositivoForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  /** CA2 + CA3. */
  async function handleSubmitDispositivo(e: FormEvent) {
    e.preventDefault();

    if (!form.nmbr.trim()) {
      setErrorFormulario("El nombre del dispositivo es obligatorio");
      return;
    }
    if (!form.mrc.trim()) {
      setErrorFormulario("La marca es obligatoria");
      return;
    }
    if (!form.id_ubccn) {
      setErrorFormulario("Selecciona la ubicación del dispositivo");
      return;
    }
    if (!form.id_cnxn) {
      setErrorFormulario("Selecciona la conexión FTP del dispositivo");
      return;
    }

    setGuardandoDispositivo(true);
    setErrorFormulario("");
    try {
      await apiFetch<{ mensaje: string }>("/dispositivos", {
        method: "POST",
        body: {
          nmbr: form.nmbr.trim(),
          mrc: form.mrc.trim(),
          mdl: form.mdl.trim() || null,
          id_ubccn: Number(form.id_ubccn),
          id_cnxn: Number(form.id_cnxn),
        },
      });

      setMostrarFormulario(false);
      setMensajeExito("Dispositivo añadido correctamente");
      cargarDispositivos();
    } catch (err) {
      setErrorFormulario(err instanceof ApiError ? err.message : "No se pudo registrar el dispositivo");
    } finally {
      setGuardandoDispositivo(false);
    }
  }

  /** HU18 CA1/CA2: desactiva el dispositivo (el backend hace borrado
   *  lógico, no físico: ver eliminar_dispositivo en routers/dispositivos.py). */
  async function confirmarDesactivarDispositivo() {
    if (!dispositivoADesactivar) return;
    setDesactivandoId(dispositivoADesactivar.id_dspstv);
    setErrorDesactivar(null);
    try {
      await apiFetch<{ mensaje: string }>(`/dispositivos/${dispositivoADesactivar.id_dspstv}`, {
        method: "DELETE",
      });
      setDispositivoADesactivar(null);
      setMensajeExito("Dispositivo desactivado correctamente");
      cargarDispositivos();
    } catch (err) {
      setErrorDesactivar(err instanceof ApiError ? err.message : "No se pudo desactivar el dispositivo");
    } finally {
      setDesactivandoId(null);
    }
  }

  /** HU18 CA3: reactiva un dispositivo Inactivo desde la misma columna de
   *  acciones (ver reactivar_dispositivo en routers/dispositivos.py). */
  async function confirmarReactivarDispositivo() {
    if (!dispositivoAReactivar) return;
    setReactivandoId(dispositivoAReactivar.id_dspstv);
    setErrorReactivar(null);
    try {
      await apiFetch<{ mensaje: string }>(`/dispositivos/${dispositivoAReactivar.id_dspstv}/reactivar`, {
        method: "POST",
      });
      setDispositivoAReactivar(null);
      setMensajeExito("Dispositivo reactivado correctamente");
      cargarDispositivos();
    } catch (err) {
      setErrorReactivar(err instanceof ApiError ? err.message : "No se pudo reactivar el dispositivo");
    } finally {
      setReactivandoId(null);
    }
  }

  /** HU19 CA1: abre el panel con el rango de fechas vuelto a los últimos 7
   *  días por defecto -si quedó otro rango aplicado de una apertura
   *  anterior del modal, no debe arrastrarse a un dispositivo distinto-. */
  function abrirEstadisticas(d: DispositivoListItem) {
    const rangoPorDefecto = rangoUltimos7Dias();
    setSeleccionFechasEstadisticas(rangoPorDefecto);
    setFiltroFechasEstadisticas(rangoPorDefecto);
    setEstadisticas(null);
    setErrorEstadisticas(null);
    setDispositivoEstadisticas(d);
  }

  function cerrarEstadisticas() {
    setDispositivoEstadisticas(null);
  }

  // CA2: recarga los 4 indicadores cada vez que se abre el panel o se
  // aplica un nuevo rango de fechas.
  useEffect(() => {
    if (!dispositivoEstadisticas) return;
    let cancelado = false;
    setCargandoEstadisticas(true);
    setErrorEstadisticas(null);

    apiFetch<EstadisticasDispositivo>(`/dispositivos/${dispositivoEstadisticas.id_dspstv}/estadisticas`, {
      params: {
        fecha_inicio: new Date(filtroFechasEstadisticas.inicio).toISOString(),
        fecha_fin: new Date(filtroFechasEstadisticas.fin).toISOString(),
      },
    })
      .then((res) => {
        if (!cancelado) setEstadisticas(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setErrorEstadisticas(err instanceof ApiError ? err.message : "No se pudieron cargar las estadísticas");
      })
      .finally(() => {
        if (!cancelado) setCargandoEstadisticas(false);
      });

    return () => {
      cancelado = true;
    };
  }, [dispositivoEstadisticas, filtroFechasEstadisticas]);

  /** HU19 CA2: "APLICAR" del selector de rango. */
  function handleAplicarFechasEstadisticas(rango: RangoFechas) {
    setFiltroFechasEstadisticas(rango);
  }

  /** HU19 CA2: "LIMPIAR FILTRO" vuelve al rango por defecto (últimos 7 días). */
  function handleLimpiarFechasEstadisticas() {
    const rangoPorDefecto = rangoUltimos7Dias();
    setSeleccionFechasEstadisticas(rangoPorDefecto);
    setFiltroFechasEstadisticas(rangoPorDefecto);
  }

  /** HU19 CA3: redirige a la cola de procesamiento con este dispositivo
   *  (su conexión FTP) preseleccionado. */
  function irAColaDeProcesamiento() {
    if (!estadisticas) return;
    navigate(`/cola-ingesta?id_cnxn=${estadisticas.id_cnxn}`);
  }

  /** HU19 CA4: redirige a Consulta de Datos con la ubicación de este
   *  dispositivo preseleccionada -el módulo no filtra por dispositivo,
   *  solo por ubicación (mismo criterio que HU17 CA4 en Gráficos)-. */
  function irAHistorialDeDatos() {
    if (!estadisticas) return;
    navigate(`/consulta-datos?ubicacion_id=${estadisticas.id_ubccn}`);
  }

  const inputClaseDispositivo =
    "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClaseDispositivo = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";

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
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">

        {/* SIDEBAR */}
        <Sidebar onLogout={logout} activo="dispositivos" rol={rol} />

        {/* ÁREA PRINCIPAL */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          {/* CONTENIDO DE LA PÁGINA (Dispositivos) */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Gestión de Dispositivos</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Listado centralizado de dispositivos de monitoreo registrados.
                </p>
              </div>

              {/* HU11 CA1: punto de entrada al formulario de registro. */}
              {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && (
                <button
                  onClick={abrirFormulario}
                  className="inline-flex items-center px-4 py-2.5 text-sm font-semibold text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
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
                    placeholder="Buscar por nombre o marca..."
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400"
                  />
                </div>

                <div className="flex w-full lg:w-auto gap-3">
                  <select
                    value={idUbccn}
                    onChange={(e) => setIdUbccn(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
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
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block p-2.5 outline-none cursor-pointer"
                  >
                    <option value="">Todos los estados</option>
                    <option value="Activo">Activo</option>
                    <option value="Inactivo">Inactivo</option>
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

              {errorDesactivar && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {errorDesactivar}
                </div>
              )}

              {errorReactivar && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {errorReactivar}
                </div>
              )}

              {/* Tabla */}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
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
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No se encontraron dispositivos con ese criterio.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((d) => (
                        <tr
                          key={d.id_dspstv}
                          onClick={() => navigate(`/dispositivos/${d.id_dspstv}`)}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors group cursor-pointer"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{d.nmbr}</td>
                          <td className="px-6 py-4">{d.mrc}</td>
                          <td className="px-6 py-4">{d.ubicacion_nombre}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                d.estd === "Activo"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {d.estd === "Activo" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {d.estd}
                            </span>
                          </td>
                          {/* DEC-09: abre la ficha del dispositivo, donde se
                              configura su formato y su mapeo de columnas. */}
                          <td className="px-6 py-4 text-right whitespace-nowrap">
                            <button
                              onClick={(e) => {
                                e.stopPropagation();
                                navigate(`/dispositivos/${d.id_dspstv}`);
                              }}
                              className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-black/10 dark:focus:ring-white/10 transition-all"
                            >
                              <svg className="w-4 h-4 mr-2 text-gray-600 dark:text-gray-300" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                              </svg>
                              Configurar
                            </button>

                            {/* HU19 CA1: solo Administrador/Técnico CENERIS
                                acceden al panel de estadísticas. */}
                            {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  abrirEstadisticas(d);
                                }}
                                className="inline-flex items-center justify-center px-3 py-1.5 ml-2 text-sm font-medium text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-black/10 dark:focus:ring-white/10 transition-all"
                              >
                                <svg className="w-4 h-4 mr-2 text-gray-600 dark:text-gray-300" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M3 13.125C3 12.504 3.504 12 4.125 12h2.25c.621 0 1.125.504 1.125 1.125v6.75C7.5 20.496 6.996 21 6.375 21h-2.25A1.125 1.125 0 013 19.875v-6.75zM9.75 8.625c0-.621.504-1.125 1.125-1.125h2.25c.621 0 1.125.504 1.125 1.125v11.25c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V8.625zM16.5 4.125c0-.621.504-1.125 1.125-1.125h2.25C20.496 3 21 3.504 21 4.125v15.75c0 .621-.504 1.125-1.125 1.125h-2.25a1.125 1.125 0 01-1.125-1.125V4.125z" />
                                </svg>
                                Ver estadísticas
                              </button>
                            )}

                            {/* HU18: solo Administrador/Técnico CENERIS (permiso
                                de EDICION sobre Dispositivos) pueden
                                desactivar/reactivar. Desactivar solo aplica a
                                un dispositivo Activo; Reactivar, a uno Inactivo. */}
                            {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && d.estd === "Activo" && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDispositivoADesactivar(d);
                                }}
                                className="inline-flex items-center justify-center px-3 py-1.5 ml-2 text-sm font-medium text-red-600 dark:text-red-400 bg-transparent border border-red-200 dark:border-red-800/40 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 focus:ring-4 focus:outline-none focus:ring-red-100 dark:focus:ring-red-900/30 transition-all"
                              >
                                <svg className="w-4 h-4 mr-2" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M18.364 18.364A9 9 0 005.636 5.636m12.728 12.728A9 9 0 015.636 5.636m12.728 12.728L5.636 5.636" />
                                </svg>
                                Desactivar
                              </button>
                            )}

                            {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && d.estd === "Inactivo" && (
                              <button
                                onClick={(e) => {
                                  e.stopPropagation();
                                  setDispositivoAReactivar(d);
                                }}
                                className="inline-flex items-center justify-center px-3 py-1.5 ml-2 text-sm font-medium text-[#5a7000] dark:text-[#ccff00] bg-transparent border border-[#ccff00]/40 rounded-lg hover:bg-[#ccff00]/10 focus:ring-4 focus:outline-none focus:ring-[#ccff00]/20 transition-all"
                              >
                                <svg className="w-4 h-4 mr-2" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                  <path strokeLinecap="round" strokeLinejoin="round" d="M16.023 9.348h4.992v-.001M2.985 19.644v-4.992m0 0h4.992m-4.993 0l3.181 3.183a8.25 8.25 0 0013.803-3.7M4.031 9.865a8.25 8.25 0 0113.803-3.7l3.181 3.182m0-4.991v4.99" />
                                </svg>
                                Reactivar
                              </button>
                            )}
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {/* Paginación */}
              {data && (
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

      {mostrarFormulario && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-lg max-h-[90vh] overflow-y-auto bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <form onSubmit={handleSubmitDispositivo}>
              <div className="p-6 border-b border-black/10 dark:border-white/10">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">Agregar dispositivo</h2>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Registra un nuevo dispositivo de monitoreo y asócialo a una ubicación y conexión FTP.
                </p>
              </div>

              <div className="p-6 space-y-5">
                {errorFormulario && (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                    {errorFormulario}
                  </div>
                )}

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClaseDispositivo} htmlFor="nmbr">
                      Nombre <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="nmbr"
                      type="text"
                      maxLength={150}
                      value={form.nmbr}
                      onChange={(e) => actualizarCampoDispositivo("nmbr", e.target.value)}
                      placeholder="CR1000-Norte"
                      className={inputClaseDispositivo}
                    />
                  </div>

                  <div>
                    <label className={labelClaseDispositivo} htmlFor="mrc">
                      Marca <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="mrc"
                      type="text"
                      maxLength={100}
                      value={form.mrc}
                      onChange={(e) => actualizarCampoDispositivo("mrc", e.target.value)}
                      placeholder="Campbell"
                      className={inputClaseDispositivo}
                    />
                  </div>
                </div>

                <div>
                  <label className={labelClaseDispositivo} htmlFor="mdl">
                    Modelo <span className="text-gray-500 dark:text-gray-400 font-normal">(opcional)</span>
                  </label>
                  <input
                    id="mdl"
                    type="text"
                    maxLength={100}
                    value={form.mdl}
                    onChange={(e) => actualizarCampoDispositivo("mdl", e.target.value)}
                    placeholder="CR1000X"
                    className={inputClaseDispositivo}
                  />
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClaseDispositivo} htmlFor="id_ubccn">
                      Ubicación <span className="text-red-500">*</span>
                    </label>
                    <select
                      id="id_ubccn"
                      value={form.id_ubccn}
                      onChange={(e) => actualizarCampoDispositivo("id_ubccn", e.target.value)}
                      className={inputClaseDispositivo + " cursor-pointer"}
                    >
                      <option value="">Selecciona una ubicación...</option>
                      {ubicacionesActivas.map((u) => (
                        <option key={u.id_ubccn} value={u.id_ubccn}>
                          {u.nmbr}
                        </option>
                      ))}
                    </select>
                  </div>

                  <div>
                    <label className={labelClaseDispositivo} htmlFor="id_cnxn">
                      Conexión FTP <span className="text-red-500">*</span>
                    </label>
                    <select
                      id="id_cnxn"
                      value={form.id_cnxn}
                      onChange={(e) => actualizarCampoDispositivo("id_cnxn", e.target.value)}
                      className={inputClaseDispositivo + " cursor-pointer"}
                    >
                      <option value="">Selecciona una conexión FTP...</option>
                      {conexiones.map((c) => (
                        <option key={c.id_cnxn} value={c.id_cnxn}>
                          {c.nmbr}
                        </option>
                      ))}
                    </select>
                  </div>
                </div>
              </div>

              <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
                {/* CA4: no toca el backend, solo descarta y cierra. */}
                <button
                  type="button"
                  onClick={cerrarFormulario}
                  className="px-4 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardandoDispositivo}
                  className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors disabled:opacity-50"
                >
                  {guardandoDispositivo ? "Guardando..." : "Guardar dispositivo"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {dispositivoADesactivar && (
        <ConfirmarEliminacionModal
          titulo={`Desactivar dispositivo '${dispositivoADesactivar.nmbr}'`}
          mensaje="El dispositivo pasará a estado Inactivo y se detendrá la ingesta de sus archivos. Su historial de telemetría no se pierde y puede reactivarse en cualquier momento."
          confirmando={desactivandoId === dispositivoADesactivar.id_dspstv}
          textoAccion="Desactivar"
          textoAccionEnProgreso="Desactivando..."
          onConfirmar={confirmarDesactivarDispositivo}
          onCancelar={() => setDispositivoADesactivar(null)}
        />
      )}

      {dispositivoAReactivar && (
        <ConfirmarEliminacionModal
          titulo={`Reactivar dispositivo '${dispositivoAReactivar.nmbr}'`}
          mensaje="El dispositivo pasará a estado Activo y volverá a recibir e ingestar datos de su conexión FTP."
          confirmando={reactivandoId === dispositivoAReactivar.id_dspstv}
          textoAccion="Reactivar"
          textoAccionEnProgreso="Reactivando..."
          variante="neutral"
          onConfirmar={confirmarReactivarDispositivo}
          onCancelar={() => setDispositivoAReactivar(null)}
        />
      )}

      {/* HU19: panel de estadísticas de operación del dispositivo. */}
      {dispositivoEstadisticas && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"
          onClick={cerrarEstadisticas}
        >
          <div
            className="w-full max-w-2xl max-h-[90vh] overflow-y-auto bg-white dark:bg-[#1f2733] rounded-2xl shadow-xl border border-black/10 dark:border-white/10"
            onClick={(e) => e.stopPropagation()}
          >
            <div className="p-6 border-b border-black/10 dark:border-white/10 flex items-start justify-between gap-4">
              <div>
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                  Estadísticas de '{dispositivoEstadisticas.nmbr}'
                </h2>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Indicadores de recepción y procesamiento de archivos, calculados sobre la cola de
                  procesamiento (HU09).
                </p>
              </div>
              <button
                type="button"
                onClick={cerrarEstadisticas}
                className="text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white text-xl leading-none"
                aria-label="Cerrar"
              >
                ×
              </button>
            </div>

            <div className="p-6 space-y-6">
              <SelectorRangoFechas
                seleccion={seleccionFechasEstadisticas}
                onCambiarSeleccion={setSeleccionFechasEstadisticas}
                onAplicar={handleAplicarFechasEstadisticas}
                onLimpiar={handleLimpiarFechasEstadisticas}
              />

              {errorEstadisticas && (
                <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                  {errorEstadisticas}
                </div>
              )}

              {cargandoEstadisticas && !estadisticas && (
                <div className="flex justify-center items-center gap-2 py-8 text-gray-600 dark:text-gray-300">
                  <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                  <span>Cargando estadísticas...</span>
                </div>
              )}

              {estadisticas && (
                <>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
                    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-4 text-center">
                      <p className="text-2xl font-bold text-gray-900 dark:text-white">
                        {estadisticas.total_recibidos}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">Recibidos</p>
                    </div>
                    <div className="rounded-xl border border-[#ccff00]/30 bg-[#ccff00]/10 p-4 text-center">
                      <p className="text-2xl font-bold text-[#5a7000] dark:text-[#ccff00]">
                        {estadisticas.total_procesados}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">Procesados</p>
                    </div>
                    <div className="rounded-xl border border-red-200 dark:border-red-800/40 bg-red-50 dark:bg-red-900/20 p-4 text-center">
                      <p className="text-2xl font-bold text-red-600 dark:text-red-400">
                        {estadisticas.total_fallidos}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">Fallidos</p>
                    </div>
                    <div className="rounded-xl border border-black/10 dark:border-white/10 bg-black/5 dark:bg-white/5 p-4 text-center">
                      <p className="text-sm font-bold text-gray-900 dark:text-white">
                        {estadisticas.ultima_fecha_recepcion
                          ? formatearFechaHoraEnZona(estadisticas.ultima_fecha_recepcion, zonaHoraria)
                          : "Sin datos"}
                      </p>
                      <p className="text-xs text-gray-600 dark:text-gray-300 mt-1">Última recepción</p>
                    </div>
                  </div>

                  <div className="flex flex-col sm:flex-row gap-3 pt-2 border-t border-black/10 dark:border-white/10">
                    <button
                      type="button"
                      onClick={irAColaDeProcesamiento}
                      className="flex-1 px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
                    >
                      VER COLA DE PROCESAMIENTO
                    </button>
                    <button
                      type="button"
                      onClick={irAHistorialDeDatos}
                      className="flex-1 px-4 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                    >
                      VER HISTORIAL DE DATOS
                    </button>
                  </div>
                </>
              )}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
