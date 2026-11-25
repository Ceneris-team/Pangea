import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { listarTodasLasPaginas } from "../services/paginacion";
import { useAuth } from "../hooks/useAuth";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import SelectorRangoFechas from "../components/SelectorRangoFechas";
import ExportacionesPanel from "../components/ExportacionesPanel";
import ConsultaCalculo from "../components/ConsultaCalculo";
import FiltrosAvanzadosPanel from "../components/FiltrosAvanzadosPanel";
import { parametrosConRango, validarCondiciones, serializarCondiciones, describirCondicion, type CondicionBorrador, type ParametroFiltro } from "../services/filtrosAvanzados";
import { formatearFechaHoraEnZona, rangoUltimas24Horas, type RangoFechas } from "../utils/fechas";

type ParametroItem = ParametroFiltro;

interface UbicacionItem {
  id_ubccn: number;
  nmbr: string;
}

interface MedicionItem {
  id_calculado?: number | null;
  id_registro: number;
  fch_hr: string;
  ubicacion_nombre: string;
  parametro_nombre: string;
  undd: string;
  dispositivo_nombre: string;
  vlr: number | string;
}

interface ListadoMediciones {
  total: number;
  items: MedicionItem[];
  next_cursor: string | null;
}

interface ListadoUbicaciones {
  total: number;
  items: UbicacionItem[];
}

interface DispositivoItem { id_dspstv: number; nmbr: string; id_ubccn: number }

function construirQuery(
  parametroIds: number[],
  ubicacionIds: number[],
  rangoFechas: RangoFechas | null,
  filtrosAvanzados: CondicionBorrador[],
  dispositivoIds: number[],
): string {
  const params = new URLSearchParams();
  // La tabla recorre todas las páginas; el muestreo automático es para gráficas.
  params.append("sin_muestreo", "true");
  parametroIds.forEach((id) => params.append("parametro_ids", String(id)));
  ubicacionIds.forEach((id) => params.append("ubicacion_ids", String(id)));
  dispositivoIds.forEach((id) => params.append("dispositivo_ids", String(id)));
  if (rangoFechas) {
    params.append("fecha_inicio", new Date(rangoFechas.inicio).toISOString());
    params.append("fecha_fin", new Date(rangoFechas.fin).toISOString());
  }
  if (filtrosAvanzados.length) params.append("condiciones", JSON.stringify(serializarCondiciones(filtrosAvanzados)));
  const query = params.toString();
  return query ? `/mediciones?${query}` : "/mediciones";
}

export default function ConsultaDatos() {
  const [calculoAbierto, setCalculoAbierto] = useState<number | null>(null);
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();

  // Los enlaces desde una ficha conservan tanto el proyecto como el equipo.
  const [searchParams, setSearchParams] = useSearchParams();
  const idsEnlace = searchParams.getAll("dispositivo_ids").join(",");
  const filtroDispositivos = useMemo(() => [...new Set(idsEnlace.split(",").map(Number).filter(id => Number.isInteger(id) && id !== 0))], [idsEnlace]);
  const [seleccionDispositivos, setSeleccionDispositivos] = useState<number[]>(filtroDispositivos);
  const [dispositivos, setDispositivos] = useState<DispositivoItem[]>([]);
  const [errorCatalogos, setErrorCatalogos] = useState("");
  const [cargandoCatalogos, setCargandoCatalogos] = useState(true);
  const [revisionCatalogos, setRevisionCatalogos] = useState(0);
  const ubicacionIdParam = searchParams.get("ubicacion_id");
  const ubicacionIdInicial = ubicacionIdParam !== null ? Number(ubicacionIdParam) : null;
  const ubicacionesIniciales =
    ubicacionIdInicial !== null && Number.isFinite(ubicacionIdInicial) ? [ubicacionIdInicial] : [];

  const [parametros, setParametros] = useState<ParametroItem[]>([]);
  const [ubicaciones, setUbicaciones] = useState<UbicacionItem[]>([]);

  // CA: selección en curso vs. filtros aplicados (se aplican al pulsar "APLICAR")
  const [seleccionParametros, setSeleccionParametros] = useState<number[]>([]);
  const [seleccionUbicaciones, setSeleccionUbicaciones] = useState<number[]>(ubicacionesIniciales);
  const [filtroParametros, setFiltroParametros] = useState<number[]>([]);
  const [filtroUbicaciones, setFiltroUbicaciones] = useState<number[]>(ubicacionesIniciales);

  // Todos los campos se editan como borrador y se aplican juntos.
  // El rango inicial y el restablecimiento corresponden a las últimas 24 horas.
  const [seleccionFechas, setSeleccionFechas] = useState<RangoFechas>(rangoUltimas24Horas);
  const [filtroFechas, setFiltroFechas] = useState<RangoFechas>(rangoUltimas24Horas);

  // Los filtros avanzados siguen el mismo borrador que fechas, equipos y proyectos.
  const [seleccionAvanzados, setSeleccionAvanzados] = useState<CondicionBorrador[]>([]);
  const [filtroAvanzados, setFiltroAvanzados] = useState<CondicionBorrador[]>([]);
  const [revisionConsulta, setRevisionConsulta] = useState(0);
  const [errorAvanzados, setErrorAvanzados] = useState<string | null>(null);

  const [mediciones, setMediciones] = useState<ListadoMediciones | null>(null);
  const [loading, setLoading] = useState(false);
  const [cargandoMas, setCargandoMas] = useState(false);
  const [paginaCargada, setPaginaCargada] = useState(1);
  const [usaCursor, setUsaCursor] = useState(false);
  const peticionActual = useRef(0);
  const [error, setError] = useState<string | null>(null);

  // HU21: hasta que /ubicaciones responda no se sabe si el usuario tiene
  // ubicaciones asignadas; sin esto el mensaje parpadearía en cada carga.
  const [cargandoUbicaciones, setCargandoUbicaciones] = useState(true);
  const [errorUbicaciones, setErrorUbicaciones] = useState<string | null>(null);

  // Los filtros (parámetros, ubicaciones, rango de fechas) ya no viven
  // apilados en la pantalla principal -diecisiete parámetros más siete
  // ubicaciones más el selector de fechas, todo en un único bloque
  // horizontal, se sentía denso y "de formulario"-. Viven en un panel
  // lateral (mismo patrón que "Dataloggers" en Gráficos), colapsado por
  // defecto.
  const [panelFiltrosAbierto, setPanelFiltrosAbierto] = useState(false);

  // CA1: carga los parámetros y ubicaciones disponibles para el usuario (HU21/HU06)
  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => { if (!controller.signal.aborted) setCargandoCatalogos(true); });
    Promise.all([
      apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros", { signal: controller.signal }),
      listarTodasLasPaginas<DispositivoItem>("/dispositivos", {}, controller.signal),
    ]).then(([catalogo, equipos]) => {
      if (controller.signal.aborted) return;
      const puntosCalculados = [...new Set(catalogo.items.filter(p => p.id_prmtr < 0).flatMap(p => p.fuentes?.map(f => f.ubicacion_id) ?? []))];
      setParametros(catalogo.items); setDispositivos([...equipos, ...puntosCalculados.map(p => ({ id_dspstv: -p, id_ubccn: p, nmbr: "Cálculos del punto" }))]); setErrorCatalogos("");
    }).catch(() => { if (!controller.signal.aborted) setErrorCatalogos("No se pudieron cargar los parámetros o los equipos disponibles."); })
      .finally(() => { if (!controller.signal.aborted) setCargandoCatalogos(false); });

    let cancelado = false;
    async function cargarUbicaciones() {
      try {
        const todas: UbicacionItem[] = [];
        let pagina = 1;
        let total = 0;
        do {
          const res = await apiFetch<ListadoUbicaciones>("/ubicaciones", {
            params: { pagina, por_pagina: 100 },
          });
          todas.push(...res.items);
          total = res.total;
          if (res.items.length === 0 && todas.length < total) {
            throw new Error("El listado de proyectos no avanzó de página.");
          }
          pagina += 1;
        } while (todas.length < total);
        if (!cancelado) { setUbicaciones(todas); setErrorUbicaciones(null); }
      } catch {
        if (!cancelado) setErrorUbicaciones("No se pudieron cargar los proyectos disponibles.");
      } finally {
        if (!cancelado) setCargandoUbicaciones(false);
      }
    }
    void cargarUbicaciones();
    return () => { cancelado = true; controller.abort(); };
  }, [revisionCatalogos]);

  const queryMediciones = construirQuery(
    filtroParametros, filtroUbicaciones, filtroFechas, filtroAvanzados, filtroDispositivos,
  );

  useEffect(() => {
    let cancelado = false;
    peticionActual.current += 1;
    queueMicrotask(() => {
      if (cancelado) return;
      setLoading(true);
      setCargandoMas(false);
      setPaginaCargada(1);
      setUsaCursor(false);
      setMediciones(null);
      setError(null);
    });

    apiFetch<ListadoMediciones>(queryMediciones)
      .then((res) => {
        if (!cancelado) {
          setMediciones(res);
          setUsaCursor(Boolean(res.next_cursor));
        }
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar la telemetría");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [queryMediciones, revisionConsulta]);

  const hayMasMediciones = mediciones !== null && (
    usaCursor ? mediciones.next_cursor !== null : mediciones.items.length < mediciones.total
  );

  const cargarMasMediciones = async () => {
    if (!mediciones || !hayMasMediciones || loading || cargandoMas) return;
    const idPeticion = peticionActual.current;
    const siguientePagina = paginaCargada + 1;
    const separador = queryMediciones.includes("?") ? "&" : "?";
    const siguienteQuery = usaCursor
      ? `${queryMediciones}${separador}cursor=${encodeURIComponent(mediciones.next_cursor!)}`
      : `${queryMediciones}${separador}pagina=${siguientePagina}`;
    setCargandoMas(true);
    setError(null);
    try {
      const res = await apiFetch<ListadoMediciones>(siguienteQuery);
      if (idPeticion !== peticionActual.current) return;
      setMediciones((actual) => actual && ({
        ...res,
        items: [...actual.items, ...res.items],
      }));
      setPaginaCargada(siguientePagina);
    } catch (err) {
      if (idPeticion === peticionActual.current) {
        setError(err instanceof ApiError ? err.message : "No se pudieron cargar más registros.");
      }
    } finally {
      if (idPeticion === peticionActual.current) setCargandoMas(false);
    }
  };

  const toggleSeleccion = (lista: number[], setLista: (v: number[]) => void, id: number) => {
    setLista(lista.includes(id) ? lista.filter((v) => v !== id) : [...lista, id]);
  };

  /** HU21: "Un Cliente Final sin ninguna ubicación asignada ve el módulo de
   *  consulta vacío con el mensaje 'No tienes ubicaciones asignadas. Contacta
   *  al administrador.'"
   *
   *  Se deduce de que /ubicaciones -que ya filtra por prms_ubccn- no devuelva
   *  nada: los roles con acceso total siempre reciben todas las ubicaciones
   *  registradas, así que una lista vacía solo puede significar o que no hay
   *  ninguna ubicación en el sistema o que a este usuario no le asignaron
   *  ninguna. En ambos casos no hay nada que consultar. */
  const sinUbicacionesAsignadas = !cargandoUbicaciones && !errorUbicaciones && ubicaciones.length === 0;

  // Conteo de filtros YA APLICADOS (no la selección en curso dentro del
  // panel) para el badge del botón "Filtros": deja ver de un vistazo que
  // hay algo filtrado sin tener que abrir el panel a revisar.
  const cantidadFiltrosAvanzados = filtroAvanzados.length;
  const parametrosConCondicion = parametrosConRango(parametros, seleccionUbicaciones, seleccionDispositivos, seleccionParametros);
  const filtrosActivos =
    filtroParametros.length + filtroUbicaciones.length + filtroDispositivos.length + cantidadFiltrosAvanzados;

  // CA2/CA3: "APLICAR" traslada la selección en curso a los filtros activos
  const handleAplicar = () => {
    const inicio = Date.parse(seleccionFechas.inicio), fin = Date.parse(seleccionFechas.fin);
    if (!Number.isFinite(inicio) || !Number.isFinite(fin) || inicio >= fin) {
      setErrorAvanzados("La fecha final debe ser posterior a la fecha inicial."); return;
    }
    if (fin > Date.now()) { setErrorAvanzados("No se permiten fechas futuras."); return; }
    const errorCondiciones = validarCondiciones(seleccionAvanzados, parametrosConCondicion);
    if (errorCondiciones) { setErrorAvanzados(errorCondiciones); return; }
    if (seleccionDispositivos.some(id => !dispositivos.some(d => d.id_dspstv === id && (!seleccionUbicaciones.length || seleccionUbicaciones.includes(d.id_ubccn))))) {
      setErrorAvanzados("Selecciona equipos disponibles en los proyectos elegidos."); return;
    }
    setErrorAvanzados(null);
    setFiltroParametros(seleccionParametros);
    setFiltroUbicaciones(seleccionUbicaciones);
    setFiltroFechas(seleccionFechas);
    setFiltroAvanzados(serializarCondiciones(seleccionAvanzados).map(c => ({ ...c, minimo: c.minimo ?? "", maximo: c.maximo ?? "" })));
    const siguiente = new URLSearchParams(searchParams);
    siguiente.delete("dispositivo_ids");
    if (seleccionUbicaciones.length === 1) siguiente.set("ubicacion_id", String(seleccionUbicaciones[0]));
    else siguiente.delete("ubicacion_id");
    seleccionDispositivos.forEach(id => siguiente.append("dispositivo_ids", String(id)));
    setSearchParams(siguiente, { replace: true });
    setPanelFiltrosAbierto(false);
  };

  // Restablecer todo también quita los equipos del enlace y restaura las fechas.
  const handleLimpiar = () => {
    setSeleccionParametros([]);
    setSeleccionUbicaciones([]);
    setFiltroParametros([]);
    setFiltroUbicaciones([]);
    setSeleccionDispositivos([]);
    const siguiente = new URLSearchParams(searchParams);
    siguiente.delete("dispositivo_ids");
    siguiente.delete("ubicacion_id");
    setSearchParams(siguiente, { replace: true });
    handleLimpiarFechas();
    handleLimpiarAvanzados();
  };

  // HU12 CA2/CA3: aplica el rango de fechas en curso como filtro activo
  const handleAplicarFechas = (rango: RangoFechas) => {
    setFiltroFechas(rango);
  };

  // HU12 CA4: "LIMPIAR FILTRO" vuelve al rango por defecto (últimas 24 horas)
  const handleLimpiarFechas = () => {
    const rangoPorDefecto = rangoUltimas24Horas();
    setSeleccionFechas(rangoPorDefecto);
    setFiltroFechas(rangoPorDefecto);
  };

  // Parte del restablecimiento completo del formulario.
  const handleLimpiarAvanzados = () => {
    setErrorAvanzados(null);
    setSeleccionAvanzados([]);
    setFiltroAvanzados([]);
  };

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        {calculoAbierto !== null && <ConsultaCalculo key={calculoAbierto} id={calculoAbierto} onCerrar={() => setCalculoAbierto(null)} />}
        <Sidebar onLogout={logout} activo="consulta-datos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="franja-superior flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex items-start justify-between gap-4 flex-wrap">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Consulta de Datos</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  Selecciona los parámetros y proyectos que quieres consultar para personalizar la vista de telemetría.
                </p>
              </div>

              {/* Los filtros (17 parámetros + 7 ubicaciones + rango de
                  fechas, en la cuenta de prueba) se sacaron del flujo
                  principal de la pantalla -antes iban apilados en un
                  único bloque horizontal denso, tipo formulario- a un
                  panel lateral, mismo patrón que "Dataloggers" en
                  Gráficos. Este botón es el único punto de entrada;
                  muestra cuántos filtros hay aplicados sin necesidad de
                  abrir el panel. */}
              {!sinUbicacionesAsignadas && !errorUbicaciones && (
                <button
                  type="button"
                  onClick={() => { setSeleccionParametros(filtroParametros); setSeleccionUbicaciones(filtroUbicaciones); setSeleccionDispositivos(filtroDispositivos); setSeleccionFechas(filtroFechas); setSeleccionAvanzados(filtroAvanzados); setErrorAvanzados(null); setPanelFiltrosAbierto(true); }}
                  className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#8fb300]/40 dark:border-[#ccff00]/30 rounded-xl transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M3 4a1 1 0 011-1h16a1 1 0 011 1v2.586a1 1 0 01-.293.707l-6.414 6.414a1 1 0 00-.293.707V17l-4 4v-6.586a1 1 0 00-.293-.707L3.293 7.293A1 1 0 013 6.586V4z" />
                  </svg>
                  Filtros
                  {filtrosActivos > 0 && (
                    <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-[#ccff00] text-gray-900">
                      {filtrosActivos}
                    </span>
                  )}
                </button>
              )}
            </header>
            <p className="mb-4 text-sm text-gray-600 dark:text-gray-300">Período aplicado: {formatearFechaHoraEnZona(new Date(filtroFechas.inicio).toISOString(), zonaHoraria)} – {formatearFechaHoraEnZona(new Date(filtroFechas.fin).toISOString(), zonaHoraria)} ({zonaHoraria})</p>
            {filtroDispositivos.length > 0 && <p className="mb-4 text-sm text-gray-700 dark:text-gray-200">Equipos seleccionados: {filtroDispositivos.map(id => dispositivos.find(d => d.id_dspstv === id)?.nmbr ?? `Equipo ${id}`).join(", ")}</p>}
            {(errorCatalogos || errorUbicaciones) && <div role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">
              <p>{errorCatalogos || errorUbicaciones}</p><button type="button" onClick={() => setRevisionCatalogos(v => v + 1)} className="mt-2 underline">Reintentar catálogos</button>
            </div>}

            {filtroAvanzados.length > 0 && <section aria-label="Condiciones aplicadas" className="mb-4 rounded-xl border border-black/10 p-4 text-sm text-gray-700 dark:border-white/20 dark:text-gray-200"><p className="mb-2 font-semibold">Condiciones aplicadas por parámetro</p><ul className="list-disc space-y-1 pl-5">{filtroAvanzados.map(c => <li key={c.parametro_id}>{describirCondicion(c, parametros)}</li>)}</ul><p className="mt-2 text-xs">Cada condición se evalúa sobre su propia serie. Los parámetros sin condición conservan sus lecturas.</p><button type="button" onClick={handleLimpiarAvanzados} className="mt-3 underline">Limpiar filtros avanzados</button></section>}
            {!sinUbicacionesAsignadas && !errorUbicaciones && <ExportacionesPanel
              idInicial={Number(searchParams.get("exportacion")) || undefined}
              filtros={{
                fecha_inicio: new Date(filtroFechas.inicio).toISOString(),
                fecha_fin: new Date(filtroFechas.fin).toISOString(),
                ubicacion_ids: filtroUbicaciones,
                parametro_ids: filtroParametros,
                dispositivo_ids: filtroDispositivos,
                valor_min: null,
                valor_max: null,
                frecuencia_muestreo: null,
                condiciones: serializarCondiciones(filtroAvanzados),
              }}
            />}

            {/* HU21: un Cliente Final sin ninguna ubicación asignada ve el
                módulo vacío con este mensaje exacto, en lugar de unos filtros
                y una tabla que nunca podrían devolver nada. */}
            {sinUbicacionesAsignadas && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-8 text-center">
                <p className="text-sm text-gray-600 dark:text-gray-300">
                  No tienes proyectos asignados. Contacta al administrador.
                </p>
              </div>
            )}

            {!sinUbicacionesAsignadas && !errorUbicaciones && (
            <>
            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10">
              {error && (
                <div role="alert" className="p-4 bg-red-50 text-sm text-red-700 dark:bg-red-950 dark:text-red-300">{error}<button type="button" className="ml-3 underline" onClick={() => { if (mediciones && hayMasMediciones) void cargarMasMediciones(); else setRevisionConsulta(v => v + 1); }}>Reintentar consulta</button></div>
              )}
              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Proyecto</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Dispositivo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Valor</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Fecha</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Cargando datos...
                        </td>
                      </tr>
                    )}
                    {!loading && mediciones?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          No hay registros para los filtros seleccionados.
                        </td>
                      </tr>
                    )}
                    {!loading &&
                      mediciones?.items.map((m, indice) => (
                        <tr
                          key={`${m.id_registro}-${indice}`}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{m.parametro_nombre}{m.id_calculado && <button type="button" className="ml-2 text-xs underline" onClick={() => setCalculoAbierto(m.id_calculado!)}>Ver fórmula y fuentes</button>}</td>
                          <td className="px-6 py-4">{m.ubicacion_nombre}</td>
                          <td className="px-6 py-4">{m.dispositivo_nombre}</td>
                          <td className="px-6 py-4">
                            {m.vlr}
                            {typeof m.vlr === "number" && m.undd ? ` ${m.undd}` : ""}
                          </td>
                          <td className="px-6 py-4">{formatearFechaHoraEnZona(m.fch_hr, zonaHoraria)}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>
              {!loading && mediciones && mediciones.total > 0 && (
                <div className="flex flex-wrap items-center justify-between gap-3 px-6 py-4 border-t border-black/10 dark:border-white/10">
                  <p className="text-sm text-gray-600 dark:text-gray-300">
                    Mostrando {mediciones.items.length} de {mediciones.total} registros
                  </p>
                  {hayMasMediciones && (
                    <button
                      type="button"
                      onClick={() => void cargarMasMediciones()}
                      disabled={cargandoMas}
                      className="px-4 py-2 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:brightness-95 disabled:opacity-50"
                    >
                      {cargandoMas ? "Cargando..." : "Cargar más"}
                    </button>
                  )}
                </div>
              )}
            </div>
            </>
            )}
          </main>
        </div>
      </div>

      {/* Panel lateral de filtros: drawer que se desliza desde la
          derecha, en vez de un bloque de filtros apilado en el flujo
          principal de la pantalla. */}
      <DrawerPanel
        abierto={panelFiltrosAbierto}
        onCerrar={() => setPanelFiltrosAbierto(false)}
        titulo="Filtros"
        panelClassName="rounded-l-3xl overflow-hidden border-l border-black/10 dark:border-white/10"
        pie={<div className="space-y-3">
          {errorAvanzados && <p role="alert" className="text-sm text-red-700 dark:text-red-300">{errorAvanzados}</p>}
          <div className="flex flex-wrap gap-2"><button type="button" onClick={handleAplicar} disabled={cargandoCatalogos || cargandoUbicaciones || Boolean(errorCatalogos || errorUbicaciones)} className="rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 disabled:opacity-50">Aplicar filtros</button><button type="button" onClick={handleLimpiar} className="rounded-xl border border-gray-400 px-4 py-2 text-sm text-gray-700 dark:text-gray-200">Restablecer todo</button></div>
          <p className="text-xs text-gray-600 dark:text-gray-400">Restablecer quita todos los filtros y vuelve a las últimas 24 horas.</p>
        </div>}
      >
            <div className="min-w-0">
              {cargandoCatalogos && <p role="status" className="mb-4 text-sm text-gray-600 dark:text-gray-300">Cargando parámetros y equipos…</p>}
              <div className="min-w-0 pb-5 border-b border-black/10 dark:border-white/10">
              <fieldset className="min-w-0">
                <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-3">Parámetros</legend>
                <div className="flex flex-wrap gap-2">
                  {parametros.length === 0 && !errorCatalogos && !cargandoCatalogos && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">No hay parámetros disponibles.</span>
                  )}
                  {/* Chips tipo toggle en vez de checkboxes nativos, mismo
                      patrón que el filtro de Parámetros en Gráficos.tsx:
                      sigue siendo un <input type="checkbox"> real (oculto
                      con sr-only), solo que su estado lo dibuja el propio
                      <label>. */}
                  {parametros.map((p) => {
                    const activo = seleccionParametros.includes(p.id_prmtr);
                    return (
                      <label
                        key={p.id_prmtr}
                        className={`inline-flex items-center gap-1.5 pl-3 pr-3.5 py-1.5 rounded-xl text-sm font-medium cursor-pointer border transition-colors ${
                          activo
                            ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#8fb300]/40 dark:border-[#ccff00]/30"
                            : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 border-transparent hover:bg-black/10 dark:hover:bg-white/10"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={activo}
                          onChange={() => toggleSeleccion(seleccionParametros, setSeleccionParametros, p.id_prmtr)}
                          className="sr-only"
                        />
                        {activo && (
                          <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {p.nmbr}
                        <span className={activo ? "text-[#5a7000]/70 dark:text-[#ccff00]/70" : "text-gray-500 dark:text-gray-400"}>
                          {p.undd}
                        </span>
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <fieldset className="min-w-0 mt-5">
                <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-3">Proyectos</legend>
                <div className="flex flex-wrap gap-2">
                  {ubicaciones.length === 0 && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">No hay proyectos disponibles.</span>
                  )}
                  {ubicaciones.map((u) => {
                    const activo = seleccionUbicaciones.includes(u.id_ubccn);
                    return (
                      <label
                        key={u.id_ubccn}
                        className={`inline-flex items-center gap-1.5 pl-3 pr-3.5 py-1.5 rounded-xl text-sm font-medium cursor-pointer border transition-colors ${
                          activo
                            ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#8fb300]/40 dark:border-[#ccff00]/30"
                            : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 border-transparent hover:bg-black/10 dark:hover:bg-white/10"
                        }`}
                      >
                        <input
                          type="checkbox"
                          checked={activo}
                          onChange={() => toggleSeleccion(seleccionUbicaciones, setSeleccionUbicaciones, u.id_ubccn)}
                          className="sr-only"
                        />
                        {activo && (
                          <svg className="w-3.5 h-3.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="3" d="M5 13l4 4L19 7" />
                          </svg>
                        )}
                        {u.nmbr}
                      </label>
                    );
                  })}
                </div>
              </fieldset>

              <fieldset className="mt-5 space-y-2"><legend className="mb-2 text-sm font-bold text-gray-700 dark:text-gray-200">Dispositivos</legend>
                <p className="text-xs text-gray-600 dark:text-gray-400">Sin selección se consultan todos los equipos de los proyectos elegidos.</p>
                {dispositivos.filter(d => !seleccionUbicaciones.length || seleccionUbicaciones.includes(d.id_ubccn)).map(d => <label key={d.id_dspstv} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200"><input type="checkbox" checked={seleccionDispositivos.includes(d.id_dspstv)} onChange={() => toggleSeleccion(seleccionDispositivos, setSeleccionDispositivos, d.id_dspstv)} />{d.nmbr}</label>)}
              </fieldset>
              </div>

              {/* El pie del panel aplica también estas fechas. */}
              <div className="min-w-0 py-5 border-b border-black/10 dark:border-white/10">
                <SelectorRangoFechas
                  plano
                  sinAcciones
                  seleccion={seleccionFechas}
                  onCambiarSeleccion={setSeleccionFechas}
                  onAplicar={handleAplicarFechas}
                  onLimpiar={handleLimpiarFechas}
                />
              </div>

              <FiltrosAvanzadosPanel parametros={parametros} disponibles={parametrosConCondicion} condiciones={seleccionAvanzados} onCambiar={condiciones => { setSeleccionAvanzados(condiciones); setErrorAvanzados(null); }} onLimpiar={handleLimpiarAvanzados} hayAplicadas={filtroAvanzados.length > 0} />
            </div>
      </DrawerPanel>
    </div>
  );
}
