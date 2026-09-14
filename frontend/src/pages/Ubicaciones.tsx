import { useEffect, useMemo, useState, type FormEvent } from "react";
import { Link, useLocation, useNavigate, useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import MapaDibujoPoligono, { type PoligonoGeoJSON } from "../components/MapaDibujoPoligono";
import { centroideDePoligono } from "../components/poligono";

interface UbicacionListItem {
  id_ubccn: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
}

interface ListadoPaginado {
  total: number;
  pagina: number;
  por_pagina: number;
  items: UbicacionListItem[];
}

interface Sede {
  id_sd: number;
  nmbr: string;
}

/** Shape de GET /ubicaciones/:id, usado para precargar el drawer de
 *  edición -el listado (UbicacionListItem) no trae el polígono, que solo
 *  hace falta cuando se va a editar el contorno-. */
interface UbicacionDetalle {
  id_ubccn: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  plgn_gjsn: PoligonoGeoJSON;
}

interface UbicacionForm {
  nmbr: string;
  dscrpcn: string;
  id_sd: string;
  estd: string;
}

const FORM_VACIO: UbicacionForm = { nmbr: "", dscrpcn: "", id_sd: "", estd: "Activa" };

const INPUT_CLASE =
  "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
const LABEL_CLASE = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";

const POR_PAGINA = 10;

// HU08: "Solo los roles Administrador y Técnico CENERIS pueden registrar
// ubicaciones". El backend lo exige igual vía
// require_permiso('Ubicaciones', EDICION); esto solo evita mostrar un
// botón que terminaría en 403.
const ROLES_PUEDEN_AGREGAR: readonly string[] = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS];

function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timeout = setTimeout(() => setDebounced(value), delayMs);
    return () => clearTimeout(timeout);
  }, [value, delayMs]);
  return debounced;
}

export default function Ubicaciones() {
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // HU08 CA3: al volver del formulario, el listado muestra el mensaje de
  // éxito junto con la ubicación recién registrada.
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

  // Estado para el Modo Oscuro (mismo patrón que Usuarios.tsx)

  // CA HU07: búsqueda por nombre, insensible a mayúsculas/minúsculas
  const [busquedaInput, setBusquedaInput] = useState("");
  const busqueda = useDebouncedValue(busquedaInput, 400);

  // CA HU07: filtro por estado (Activa / Inactiva)
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);

  const [data, setData] = useState<ListadoPaginado | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setPagina(1);
  }, [busqueda, estado]);

  // Nombrada (no solo dentro del useEffect) para poder recargar el
  // listado después de crear/editar una ubicación desde el drawer, sin
  // depender de que busqueda/estado/pagina cambien -mismo patrón que
  // cargarPaneles en Paneles.tsx-.
  function cargarUbicaciones() {
    setLoading(true);
    setError(null);

    apiFetch<ListadoPaginado>("/ubicaciones", {
      params: {
        busqueda: busqueda || undefined,
        estado: estado || undefined,
        pagina,
        por_pagina: POR_PAGINA,
      },
    })
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado");
      })
      .finally(() => setLoading(false));
  }

  useEffect(cargarUbicaciones, [busqueda, estado, pagina]);

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;
  const inicioRango = data ? (data.pagina - 1) * data.por_pagina + 1 : 0;
  const finRango = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  // HU08: crear y editar ubicación viven como drawer lateral ANCHO
  // ("xl" en vez de "md") -a diferencia del resto de formularios del
  // sistema-, porque el mapa de dibujo del contorno necesita bastante
  // espacio horizontal para ser usable. `idEnEdicion` es null al crear;
  // solo el id (no el objeto completo del listado) porque también se
  // abre por id desde fuera del listado -ver el efecto de ?editar= más
  // abajo, para el botón "Editar ubicación" del popup del mapa (HU22
  // CA3), que no tiene el UbicacionListItem a mano-.
  const [drawerAbierto, setDrawerAbierto] = useState(false);
  const [idEnEdicion, setIdEnEdicion] = useState<number | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [form, setForm] = useState<UbicacionForm>(FORM_VACIO);
  const [poligono, setPoligono] = useState<PoligonoGeoJSON | null>(null);
  const [sedes, setSedes] = useState<Sede[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [errorForm, setErrorForm] = useState("");

  // El selector de sede solo lo necesita un usuario con scope "global"
  // (ver _resolver_sede en routers/ubicaciones.py); se ofrece siempre
  // como opcional y el backend ignora id_sd para "por_sede".
  useEffect(() => {
    apiFetch<Sede[]>("/sedes")
      .then(setSedes)
      .catch(() => setSedes([]));
  }, []);

  function actualizarCampo<K extends keyof UbicacionForm>(campo: K, valor: UbicacionForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  // El punto de referencia se DERIVA del contorno, ya no se teclea: pedir
  // lat/lng a mano a quien ya dibujó la zona es redundante y permite que
  // el centro quede fuera de su propio polígono.
  const centro = useMemo(() => centroideDePoligono(poligono), [poligono]);

  function abrirCrear() {
    setIdEnEdicion(null);
    setForm(FORM_VACIO);
    setPoligono(null);
    setErrorForm("");
    setDrawerAbierto(true);
  }

  /** HU08 (ampliación) CA1: precarga nombre/descripción/estado/contorno
   *  desde GET /ubicaciones/:id -el listado no trae el polígono-. */
  function abrirEditar(id: number) {
    setIdEnEdicion(id);
    setForm(FORM_VACIO);
    setPoligono(null);
    setErrorForm("");
    setDrawerAbierto(true);
    setCargandoDetalle(true);

    apiFetch<UbicacionDetalle>(`/ubicaciones/${id}`)
      .then((u) => {
        setForm({ nmbr: u.nmbr, dscrpcn: u.dscrpcn ?? "", id_sd: "", estd: u.estd });
        setPoligono(u.plgn_gjsn ?? null);
      })
      .catch((err) => {
        setErrorForm(err instanceof ApiError ? err.message : "No se pudo cargar la ubicación");
      })
      .finally(() => setCargandoDetalle(false));
  }

  // HU22 CA3: "Editar ubicación" desde el popup del mapa llega acá con
  // ?editar=<id> (ver MapaUbicaciones.tsx) -abre este drawer apenas monta
  // la página, mismo patrón que ?ubicacion_id= en Graficos.tsx (HU17
  // CA4)-.
  const [searchParams, setSearchParams] = useSearchParams();
  useEffect(() => {
    const idParam = searchParams.get("editar");
    const id = idParam !== null ? Number(idParam) : null;
    if (id !== null && Number.isFinite(id)) {
      abrirEditar(id);
      const siguiente = new URLSearchParams(searchParams);
      siguiente.delete("editar");
      setSearchParams(siguiente, { replace: true });
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  async function handleSubmitUbicacion(e: FormEvent) {
    e.preventDefault();

    // Mismas reglas que el backend (UbicacionCrear/UbicacionActualizar);
    // esto solo evita un viaje de ida y vuelta con un campo vacío.
    if (!form.nmbr.trim()) {
      setErrorForm("El nombre de la ubicación es obligatorio");
      return;
    }
    if (!poligono || !centro) {
      setErrorForm("Dibuja sobre el mapa el contorno de la zona (mínimo 3 vértices)");
      return;
    }

    setGuardando(true);
    setErrorForm("");
    try {
      if (idEnEdicion) {
        // La SEDE no se edita: mover una ubicación de sede arrastraría a
        // sus dispositivos y a los permisos ya concedidos sobre ella. El
        // backend ni siquiera acepta id_sd en UbicacionActualizar.
        await apiFetch<{ mensaje: string }>(`/ubicaciones/${idEnEdicion}`, {
          method: "PUT",
          body: {
            nmbr: form.nmbr.trim(),
            dscrpcn: form.dscrpcn.trim() || null,
            lttd: centro.lat,
            lngtd: centro.lng,
            plgn_gjsn: poligono,
            estd: form.estd,
          },
        });
        setDrawerAbierto(false);
        setMensajeExito("Ubicación actualizada correctamente");
        cargarUbicaciones();
      } else {
        await apiFetch<{ mensaje: string }>("/ubicaciones", {
          method: "POST",
          body: {
            nmbr: form.nmbr.trim(),
            dscrpcn: form.dscrpcn.trim() || null,
            lttd: centro.lat,
            lngtd: centro.lng,
            plgn_gjsn: poligono,
            ...(form.id_sd ? { id_sd: Number(form.id_sd) } : {}),
          },
        });
        setDrawerAbierto(false);
        setMensajeExito("Ubicación registrada correctamente");
        cargarUbicaciones();
      }
    } catch (err) {
      setErrorForm(
        err instanceof ApiError
          ? err.message
          : `No se pudo ${idEnEdicion ? "actualizar" : "registrar"} la ubicación`,
      );
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">

        {/* SIDEBAR */}
        <Sidebar onLogout={logout} activo="ubicaciones" rol={rol} />

        {/* ÁREA PRINCIPAL */}
        <div className="flex-1 flex flex-col overflow-hidden">

          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          {/* CONTENIDO DE LA PÁGINA (Ubicaciones) */}
          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Gestión de Ubicaciones</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Listado centralizado de estaciones de monitoreo registradas.
                </p>
              </div>

              <div className="flex gap-3">
                {/* HU22: entrada a la vista de mapa, solo lectura. */}
                <button
                  onClick={() => navigate("/ubicaciones/mapa")}
                  className="inline-flex items-center px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#8fb300]/40 dark:border-[#ccff00]/30 rounded-xl transition-colors"
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
                    <path strokeLinecap="round" strokeLinejoin="round" d="M9 20l-5.447-2.724A1 1 0 013 16.382V5.618a1 1 0 011.447-.894L9 7m0 13l6-3m-6 3V7m6 10l4.553 2.276A1 1 0 0021 18.382V7.618a1 1 0 00-.553-.894L15 4m0 13V4m0 0L9 7" />
                  </svg>
                  Ver en mapa
                </button>

                {/* HU08 CA1: punto de entrada al drawer de registro. */}
                {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && (
                  <button
                    onClick={abrirCrear}
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
                    Agregar ubicación
                  </button>
                )}
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
                    placeholder="Buscar por nombre de ubicación..."
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
                      <th className="px-6 py-4 font-bold tracking-wider">Descripción</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Latitud</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Longitud</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando datos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={6} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No se encontraron ubicaciones con ese criterio.
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((u) => (
                        <tr
                          key={u.id_ubccn}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors group"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{u.nmbr}</td>
                          <td className="px-6 py-4">{u.dscrpcn ?? "—"}</td>
                          <td className="px-6 py-4">{u.lttd}</td>
                          <td className="px-6 py-4">{u.lngtd}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                u.estd === "Activa"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {u.estd === "Activa" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {u.estd}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="flex items-center justify-end gap-2">
                              <Link
                                to={`/ubicaciones/${u.id_ubccn}`}
                                className="inline-flex items-center justify-center px-3 py-1.5 text-xs sm:text-sm font-medium whitespace-nowrap text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                              >
                                Ver detalles
                              </Link>
                              {/* HU15/HU17: misma preselección por
                                  ?ubicacion_id= que usa el mapa de
                                  estaciones para abrir Gráficos. */}
                              <Link
                                to={`/graficos?ubicacion_id=${u.id_ubccn}`}
                                className="inline-flex items-center justify-center px-3 py-1.5 text-xs sm:text-sm font-medium whitespace-nowrap text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white transition-all"
                              >
                                Ver gráficos
                              </Link>
                              {/* HU08 (ampliación): abre el drawer de
                                  edición con nombre/descripción/estado/
                                  contorno precargados. Mismos roles que el
                                  alta, porque el backend exige Edición
                                  sobre "Ubicaciones". */}
                              {ROLES_PUEDEN_AGREGAR.includes(rol ?? "") && (
                                <button
                                  type="button"
                                  onClick={() => abrirEditar(u.id_ubccn)}
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-xs sm:text-sm font-medium whitespace-nowrap text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-lg hover:bg-black/10 dark:hover:bg-white/10 hover:text-gray-900 dark:hover:text-white focus:ring-4 focus:outline-none focus:ring-black/10 dark:focus:ring-white/10 transition-all"
                                >
                                  <svg className="w-4 h-4 mr-2 text-gray-600 dark:text-gray-300" aria-hidden="true" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24" strokeWidth="2" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z" />
                                  </svg>
                                  Editar
                                </button>
                              )}
                            </div>
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

      {/* HU08: drawer ANCHO ("xl") de crear/editar ubicación -a diferencia
          del resto de formularios del sistema, que usan el ancho normal
          ("md")-, porque el mapa de dibujo del contorno necesita bastante
          espacio horizontal para ser usable. */}
      <DrawerPanel
        abierto={drawerAbierto}
        onCerrar={() => setDrawerAbierto(false)}
        titulo={idEnEdicion ? "Editar ubicación" : "Agregar ubicación"}
        ancho="xl"
      >
        {cargandoDetalle ? (
          <div className="text-sm text-gray-500 dark:text-gray-400">Cargando…</div>
        ) : (
          <form onSubmit={handleSubmitUbicacion} className="flex flex-col h-full">
            <p className="text-sm text-gray-600 dark:text-gray-300 mb-5">
              {idEnEdicion
                ? "Modifica los datos de la zona de monitoreo y ajusta su contorno sobre el mapa."
                : "Registra una nueva zona de monitoreo y delimita su contorno sobre el mapa."}
            </p>

            {errorForm && (
              <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {errorForm}
              </div>
            )}

            <div className="space-y-5 flex-1">
              <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                <div>
                  <label className={LABEL_CLASE} htmlFor="nmbr">
                    Nombre <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="nmbr"
                    type="text"
                    maxLength={150}
                    value={form.nmbr}
                    onChange={(e) => actualizarCampo("nmbr", e.target.value)}
                    placeholder="Estación Río Rímac"
                    className={INPUT_CLASE}
                  />
                </div>

                {/* Al crear: Sede (opcional, solo relevante para scope
                    "global"). Al editar: Estado en su lugar -la sede no
                    se edita, ver comentario de handleSubmitUbicacion-. */}
                {idEnEdicion ? (
                  <div>
                    <label className={LABEL_CLASE} htmlFor="estd">
                      Estado <span className="text-red-500">*</span>
                    </label>
                    <select
                      id="estd"
                      value={form.estd}
                      onChange={(e) => actualizarCampo("estd", e.target.value)}
                      className={INPUT_CLASE + " cursor-pointer"}
                    >
                      <option value="Activa">Activa</option>
                      <option value="Inactiva">Inactiva</option>
                    </select>
                  </div>
                ) : (
                  sedes.length > 0 && (
                    <div>
                      <label className={LABEL_CLASE} htmlFor="id_sd">
                        Sede
                      </label>
                      <select
                        id="id_sd"
                        value={form.id_sd}
                        onChange={(e) => actualizarCampo("id_sd", e.target.value)}
                        className={INPUT_CLASE + " cursor-pointer"}
                      >
                        <option value="">Mi sede</option>
                        {sedes.map((s) => (
                          <option key={s.id_sd} value={s.id_sd}>
                            {s.nmbr}
                          </option>
                        ))}
                      </select>
                    </div>
                  )
                )}
              </div>

              <div>
                <label className={LABEL_CLASE} htmlFor="dscrpcn">
                  Descripción <span className="text-gray-500 dark:text-gray-400 font-normal">(opcional)</span>
                </label>
                <textarea
                  id="dscrpcn"
                  rows={2}
                  maxLength={300}
                  value={form.dscrpcn}
                  onChange={(e) => actualizarCampo("dscrpcn", e.target.value)}
                  placeholder="Referencias del punto de monitoreo, accesos, observaciones..."
                  className={INPUT_CLASE}
                />
              </div>

              <div>
                <span className={LABEL_CLASE}>
                  Contorno de la zona <span className="text-red-500">*</span>
                </span>
                <MapaDibujoPoligono
                  valor={poligono}
                  onChange={setPoligono}
                  centroLat={centro?.lat ?? null}
                  centroLng={centro?.lng ?? null}
                />
                <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                  El punto de referencia de la zona se calcula del contorno:{" "}
                  {centro ? (
                    <span className="font-mono">
                      {centro.lat.toFixed(6)}, {centro.lng.toFixed(6)}
                    </span>
                  ) : (
                    "se definirá al cerrar el contorno."
                  )}
                </p>
              </div>
            </div>

            <div className="mt-6 pt-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
              <button
                type="button"
                onClick={() => setDrawerAbierto(false)}
                className="px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
              >
                Cancelar
              </button>
              <button
                type="submit"
                disabled={guardando}
                className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
              >
                {guardando ? "Guardando..." : idEnEdicion ? "Guardar cambios" : "Guardar ubicación"}
              </button>
            </div>
          </form>
        )}
      </DrawerPanel>
    </div>
  );
}