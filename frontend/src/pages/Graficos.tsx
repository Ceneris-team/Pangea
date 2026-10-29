import KpisAmpliados from "../components/KpisAmpliados";
import { acotarZoom, crearActualizadorSerial, type CambioRangoGrafico } from "./actualizacionGraficos";
import { NOMBRES_VISTA, VISTAS_SERIE, type VistaSerie } from "../components/configuracionSerieUtils";
import ComparacionDataloggers from "../components/ComparacionDataloggers";
import { agruparSeriesComparables, nombreFuente, colorDatalogger, type FuenteSerie, type SerieTelemetria, type DatosSerie } from "./seriesTelemetria";
import { useCallback, useEffect, useId, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import { useTheme } from "../hooks/useTheme";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import SelectorRangoFechasTimeline, { type ControlTimeline } from "../components/SelectorRangoFechasTimeline";
import {
  construirQuery,
  etiquetaDeIntervalo,
  formatearFechaCorta,
  pathDeEscalon,
  pathDeLinea,
  type DispositivoItem,
  type HoverInfo,
  type ListadoMediciones,
  type MedicionNumerica,
  type ParametroItem,
  type UbicacionItem,
  type Vista,
} from "./graficosUtils";
import type { RangoFechas } from "../utils/fechas";

/** Telemetría por proyecto, datalogger y formato. La clasificación del
 * mapeo define la vista inicial; cada serie conserva su propio selector.
 * Los KPI y las barras usan los registros completos y una referencia
 * anterior al rango. La reducción de puntos solo afecta al dibujo. */

export default function Graficos() {
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();

  // HU17 CA4: ubicación preseleccionada por query param. Se lee con
  // useSearchParams (y no de window.location) para que quede sincronizada
  // con la navegación de React Router: volver atrás desde el mapa
  // restaura el filtro anterior sin recargar.
  //
  // Ahora la ubicación es un selector SIEMPRE visible (no solo cuando
  // llega por query param): elegir una es el primer paso para poder
  // elegir DESPUÉS sus dataloggers, si tiene más de uno. El query param
  // sigue siendo la fuente de verdad -así el link del mapa sigue
  // funcionando igual- pero ahora también se escribe desde el <select>.
  const [searchParams, setSearchParams] = useSearchParams();
  const ubicacionIdParam = searchParams.get("ubicacion_id");
  const ubicacionId = ubicacionIdParam !== null ? Number(ubicacionIdParam) : null;
  const ubicacionIdValida = ubicacionId !== null && Number.isFinite(ubicacionId);

  const [catalogoSeries, setCatalogoSeries] = useState<{ ubicacion: number; items: SerieTelemetria[] } | null>(null);
  const proyectoDeParametros = useRef<number | null>(null);
  const [errorCatalogo, setErrorSeries] = useState<{ ubicacion: number; mensaje: string } | null>(null);
  const errorSeries = errorCatalogo?.ubicacion === ubicacionId ? errorCatalogo.mensaje : null;
  const [parametros, setParametros] = useState<ParametroItem[]>([]);
  const [ubicaciones, setUbicaciones] = useState<UbicacionItem[]>([]);

  // Catálogo de dispositivos (dataloggers) DE LA UBICACIÓN elegida. Sin
  // ubicación elegida no se listan -elegir la ubicación es el primer
  // paso-. Sin selección de dispositivos = "todos los de esa ubicación".
  const [dispositivos, setDispositivos] = useState<DispositivoItem[]>([]);
  const [dispositivosSeleccionados, setDispositivosSeleccionados] = useState<number[]>([]);
  // Panel lateral con los checkboxes de dataloggers: colapsado por
  // defecto para que la pantalla no se sienta lineal/apilada -se abre
  // como un drawer sobre el contenido, no como una sección fija más-.
  const [panelDataloggersAbierto, setPanelDataloggersAbierto] = useState(false);

  // CA: la selección de parámetros aplica al instante (sin botón "APLICAR");
  // es el único filtro además del rango de fechas.
  const [parametrosSeleccionados, setParametrosSeleccionados] = useState<number[]>([]);

  // La controla por completo SelectorRangoFechasTimeline (rango rápido,
  // arrastre de manijas, auto-actualización cada 60s siguiendo "ahora").
  const controlTimeline = useRef<ControlTimeline>(null);
  const actualizarDatos = useCallback(() => controlTimeline.current?.actualizar(), []);
  const [consultaRango, setConsultaRango] = useState<{ rango: RangoFechas; ambito: number; revision: number } | null>(null);
  const rangoFechas = consultaRango?.rango ?? null;
  const cambiarRango = useCallback((rango: RangoFechas, cambio: CambioRangoGrafico) => {
    setConsultaRango(actual => ({ rango, ambito: (actual?.ambito ?? 0) + (cambio.motivo === "seleccion" ? 1 : 0), revision: (actual?.revision ?? 0) + 1 }));
  }, []);

  const [vista, setVista] = useState<Vista>("grafico");

  const ambitoTabla = JSON.stringify([ubicacionId, parametrosSeleccionados, dispositivosSeleccionados, consultaRango?.ambito]);
  const [respuestaTabla, setRespuestaTabla] = useState<{ ambito: string; datos: ListadoMediciones } | null>(null);
  const mediciones = respuestaTabla?.ambito === ambitoTabla ? respuestaTabla.datos : null;
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);


  // Solo tiene sentido graficar parámetros numéricos (línea/área).
  const parametrosGraficables = useMemo(
    () => parametros.filter((p) => p.tipo_dato === "numerico" && catalogoSeries?.ubicacion === ubicacionId && catalogoSeries.items.some(s => s.id_prmtr === p.id_prmtr)),
    [parametros, catalogoSeries, ubicacionId],
  );

  useEffect(() => {
    apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros")
      .then((res) => {
        setParametros(res.items);
      })
      .catch(() => setParametros([]));
  }, []);

  // Catálogo de ubicaciones para el selector, siempre cargado -ya no
  // depende de que llegue un ubicacion_id por query param, porque ahora
  // el selector se ofrece siempre, no solo cuando se llega desde el mapa
  // (HU17)-.
  useEffect(() => {
    apiFetch<{ items: UbicacionItem[] }>("/ubicaciones", { params: { por_pagina: 100 } })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]));
  }, []);

  // Catálogo de dispositivos de la ubicación elegida. Elegir la
  // ubicación es el primer paso para poder elegir DESPUÉS sus
  // dataloggers -sin ubicación elegida no se listan ninguno-, y la
  // selección de dataloggers de la ubicación anterior se descarta al
  // cambiar: los ids ya no aplican a la ubicación nueva.
  useEffect(() => {
    const controlador = new AbortController();
    queueMicrotask(() => {
      if (controlador.signal.aborted) return;
      setDispositivosSeleccionados([]);
      setPanelDataloggersAbierto(false);
      setDispositivos([]);
    });
    if (!ubicacionIdValida) return () => controlador.abort();
    apiFetch<{ items: DispositivoItem[] }>("/dispositivos", {
      params: { por_pagina: 100, id_ubccn: ubicacionId as number }, signal: controlador.signal,
    })
      .then(res => { if (!controlador.signal.aborted) setDispositivos(res.items); })
      .catch(() => { if (!controlador.signal.aborted) setDispositivos([]); });
    return () => controlador.abort();
  }, [ubicacionIdValida, ubicacionId]);

  useEffect(() => {
    let cancelado = false;
    if (vista !== "tabla") {
      queueMicrotask(() => { if (!cancelado) setLoading(false); });
      return () => { cancelado = true; };
    }
    // La ubicación ahora es obligatoria (es el primer paso del flujo:
    // elegir ubicación antes de poder elegir sus dataloggers), así que
    // sin una elegida todavía no hay nada que pedir -antes se pedían
    // "todas las ubicaciones permitidas" a la vez, lo que mezclaba
    // estaciones distintas en la misma serie por color-.
    //
    // Sin este `setMediciones(null)`, quitar la ubicación dejaba
    // `mediciones` con la última respuesta válida -el efecto solo
    // hacía `return`- y el gráfico de la ubicación anterior seguía
    // dibujado en pantalla aunque el selector ya mostrara "Selecciona
    // una ubicación...", sin pertenecer a ningún filtro activo.
    if (parametrosSeleccionados.length === 0 || rangoFechas === null || !ubicacionIdValida) {
      queueMicrotask(() => {
        if (cancelado) return;
        setRespuestaTabla(null);
        setLoading(false);
        setError(null);
      });
      return () => { cancelado = true; };
    }
    queueMicrotask(() => {
      if (cancelado) return;
      setLoading(true);
      setError(null);
    });

    apiFetch<ListadoMediciones>(
      construirQuery(
        parametrosSeleccionados,
        [ubicacionId as number],
        dispositivosSeleccionados,
        rangoFechas,
      ),
    )
      .then((res) => {
        if (!cancelado) setRespuestaTabla({ ambito: ambitoTabla, datos: res });
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
  }, [parametrosSeleccionados, rangoFechas, ubicacionId, ubicacionIdValida, dispositivosSeleccionados, vista, ambitoTabla]);

  useEffect(() => {
    if (!ubicacionIdValida) return;
    let cancelado = false;
    apiFetch<{ items: SerieTelemetria[] }>(`/mediciones/series?ubicacion_id=${ubicacionId}`)
      .then(res => {
        if (cancelado) return;
        setCatalogoSeries({ ubicacion: ubicacionId!, items: res.items });
        setErrorSeries(null);
        if (proyectoDeParametros.current !== ubicacionId) {
          proyectoDeParametros.current = ubicacionId;
          setParametrosSeleccionados(prev => {
            const validos = prev.filter(id => res.items.some(s => s.id_prmtr === id));
            return validos.length ? validos : res.items.length ? [res.items[0].id_prmtr] : [];
          });
        }
      })
      .catch(err => { if (!cancelado) setErrorSeries({ ubicacion: ubicacionId!, mensaje: err instanceof ApiError ? err.message : "No se pudieron cargar las series" }); });
    return () => { cancelado = true; };
  }, [ubicacionId, ubicacionIdValida, rangoFechas]);
  const seriesVisibles = catalogoSeries?.ubicacion === ubicacionId ? catalogoSeries.items.filter(s =>
    parametrosSeleccionados.includes(s.id_prmtr) && (!dispositivosSeleccionados.length || dispositivosSeleccionados.includes(s.id_dspstv))) : [];

  const gruposComparables = agruparSeriesComparables(seriesVisibles);

  const toggleParametro = (id: number) => {
    setParametrosSeleccionados((actual) => (actual.includes(id) ? actual.filter((v) => v !== id) : [...actual, id]));
  };

  const toggleDispositivo = (id: number) => {
    setDispositivosSeleccionados((actual) => (actual.includes(id) ? actual.filter((v) => v !== id) : [...actual, id]));
  };

  function elegirUbicacion(id: string) {
    const siguiente = new URLSearchParams(searchParams);
    if (id) siguiente.set("ubicacion_id", id);
    else siguiente.delete("ubicacion_id");
    setSearchParams(siguiente, { replace: true });
  }

  // GET /mediciones pagina sobre la unión de todas las series, así que
  // `total` mayor que los items recibidos significa que lo que se dibuja
  // es un recorte, no la serie entera.
  const respuestaTruncada = mediciones !== null && mediciones.total > mediciones.items.length;

  // El auto-refresco de SelectorRangoFechasTimeline (cada 60s, mientras el
  // rango siga "hasta ahora") pone `loading` en true en cada tick. Antes
  // eso ocultaba TODA la grilla de gráficos -"!loading && ..."- y la
  // reemplazaba por un spinner de unos pocos px de alto: el documento se
  // encogía de golpe cada 60s y el navegador perdía la posición de
  // scroll, saltando arriba en medio de la lectura. Distinguiendo la
  // carga inicial (sin datos previos) de un refresco silencioso (ya hay
  // datos, solo se están actualizando), los refrescos dejan la grilla
  // anterior en pantalla -sin desmontarla- hasta que llegan los datos
  // nuevos.
  const cargandoPrimeraVez = vista === "tabla" && loading && mediciones === null;

  // El backend devuelve más reciente primero; para la línea de tiempo se
  // necesita orden cronológico ascendente. Solo valores numéricos son
  // graficables (los parámetros de texto no aplican a línea/área).
  const itemsOrdenados = useMemo(() => {
    return [...(mediciones?.items ?? [])]
      .filter((item): item is MedicionNumerica => typeof item.vlr === "number")
      .sort((a, b) => new Date(a.fch_hr).getTime() - new Date(b.fch_hr).getTime());
  }, [mediciones]);


  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="graficos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-5 mb-6">
              {/* Elegir la ubicación es el primer paso: define qué
                  dataloggers hay disponibles para el paso siguiente
                  (botón "Dataloggers", que abre el panel lateral solo
                  si esa ubicación tiene más de uno). */}
              <div>
                <label htmlFor="ubicacion-graficos" className="block text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">
                  Proyecto
                </label>
                <div className="flex items-center gap-3 flex-wrap">
                  <select
                    id="ubicacion-graficos"
                    value={ubicacionId ?? ""}
                    onChange={(e) => elegirUbicacion(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full max-w-xs p-2.5 outline-none cursor-pointer"
                  >
                    {/* El <select> cerrado sí hereda el tema (clases
                        dark: arriba), pero su lista desplegada la pinta
                        el navegador con SUS colores por defecto -blanco/
                        negro-, salvo que cada <option> tenga su propio
                        color explícito: por eso van con bg-white/
                        dark:bg-[#2d3748] acá mismo y no solo en el
                        contenedor. */}
                    <option value="" className="bg-white dark:bg-[#2d3748] text-gray-900 dark:text-white">
                      Selecciona un proyecto…
                    </option>
                    {ubicaciones.map((u) => (
                      <option
                        key={u.id_ubccn}
                        value={u.id_ubccn}
                        className="bg-white dark:bg-[#2d3748] text-gray-900 dark:text-white"
                      >
                        {u.nmbr}
                      </option>
                    ))}
                  </select>

                  {/* Solo se ofrece el panel si la ubicación elegida
                      tiene más de un datalogger -con uno solo, filtrar
                      no cambiaría nada y sería un botón sin efecto-. */}
                  {dispositivos.length > 1 && (
                    <button
                      type="button"
                      onClick={() => setPanelDataloggersAbierto(true)}
                      className="inline-flex items-center gap-2 px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#8fb300]/40 dark:border-[#ccff00]/30 rounded-xl transition-colors"
                    >
                      <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M9 3v2m6-2v2M5 8h14M5 8a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2v-9a2 2 0 00-2-2M5 8V6a2 2 0 012-2h10a2 2 0 012 2v2" />
                      </svg>
                      Dataloggers
                      {dispositivosSeleccionados.length > 0 && (
                        <span className="inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-[#ccff00] text-gray-900">
                          {dispositivosSeleccionados.length}
                        </span>
                      )}
                    </button>
                  )}
                </div>
              </div>

              {ubicacionIdValida && (
                <fieldset className="mt-6 pt-6 border-t border-black/10 dark:border-white/10">
                  <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-3">Parámetros</legend>
                  <div className="flex flex-wrap gap-2">
                    {parametrosGraficables.length === 0 && (
                      <span className="text-sm text-gray-500 dark:text-gray-400">No hay parámetros disponibles.</span>
                    )}
                    {/* Chips tipo toggle en vez de checkboxes nativos: el
                        checkbox de navegador es minúsculo y sin relación
                        visual con el resto de la UI -pills, badges- que
                        ya usa la app para selección de estado. Sigue
                        siendo un <input type="checkbox"> real (accesible,
                        con checked/onChange), solo que oculto y con su
                        estado dibujado por el propio <label>. */}
                    {parametrosGraficables.map((p) => {
                      const activo = parametrosSeleccionados.includes(p.id_prmtr);
                      return (
                        <label
                          key={p.id_prmtr}
                          className={`inline-flex items-center gap-1.5 pl-3 pr-3.5 py-1.5 rounded-full text-sm font-medium cursor-pointer border transition-colors ${
                            activo
                              ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#8fb300]/40 dark:border-[#ccff00]/30"
                              : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 border-transparent hover:bg-black/10 dark:hover:bg-white/10"
                          }`}
                        >
                          <input
                            type="checkbox"
                            checked={activo}
                            onChange={() => toggleParametro(p.id_prmtr)}
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
              )}

              {ubicacionIdValida && (
                <div className="mt-6 pt-6 border-t border-black/10 dark:border-white/10">
                  <SelectorRangoFechasTimeline controlRef={controlTimeline} zonaHoraria={zonaHoraria} onCambiarRango={cambiarRango} />
                </div>
              )}
            </div>

            {!ubicacionIdValida && (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
                Selecciona un proyecto para ver sus gráficos.
              </div>
            )}

            {ubicacionIdValida && (
              <div className="flex items-center justify-end mb-4 flex-wrap gap-3">
                  {/* Refresco en segundo plano (auto-actualización cada
                      60s de SelectorRangoFechasTimeline, mientras siga
                      "hasta ahora"): antes esto ocultaba toda la grilla
                      de gráficos y la reemplazaba por un spinner grande,
                      lo que hacía que el documento se encogiera de golpe
                      y el navegador perdiera la posición de scroll -acá
                      solo se avisa sin tapar nada de lo que ya está
                      dibujado-. */}
                  {vista === "tabla" && loading && !cargandoPrimeraVez && (
                    <span className="flex items-center gap-1.5 pl-3 text-xs text-gray-500 dark:text-gray-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#ccff00] animate-pulse" />
                      Actualizando…
                    </span>
                  )}

                <button
                  type="button"
                  onClick={() => setVista((v) => (v === "grafico" ? "tabla" : "grafico"))}
                  className="px-4 py-2 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/10 dark:hover:bg-white/10 transition-all"
                >
                  {vista === "grafico" ? "VER TABLA" : "VER GRÁFICOS"}
                </button>
              </div>
            )}

            {/* La respuesta viene paginada: si hay más puntos de los que
                llegaron, las series se están dibujando INCOMPLETAS. Sin
                este aviso una serie recortada es indistinguible de una con
                pocos datos reales -que es justo lo que confunde al ver
                "MEDICIONES 5" al abrir varios gráficos a la vez-. */}
            {vista === "tabla" && !cargandoPrimeraVez && respuestaTruncada && (
              <div className="mb-6 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-300/50 dark:border-amber-800/40 text-amber-800 dark:text-amber-300 text-sm">
                Mostrando {mediciones?.items.length ?? 0} de {mediciones?.total ?? 0} mediciones del
                rango en esta tabla. Consulta todos los registros desde Consulta de datos.
              </div>
            )}

            {vista === "tabla" && error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800/30">
                {error}
              </div>
            )}

            {cargandoPrimeraVez && (
              <div className="flex justify-center items-center gap-2 py-24 text-gray-600 dark:text-gray-300">
                <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce" />
                <span>Cargando telemetría...</span>
              </div>
            )}

            {!cargandoPrimeraVez && parametrosSeleccionados.length === 0 && (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
                Selecciona al menos un parámetro para ver sus gráficos.
              </div>
            )}

            {!cargandoPrimeraVez && vista === "tabla" && itemsOrdenados.length > 0 && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Fecha</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Hora</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
                      {/* Dispositivo: sin esto, dos lecturas del mismo
                          parámetro en el mismo instante -de dos
                          dataloggers distintos de la misma ubicación-
                          eran indistinguibles en la tabla. No hace falta
                          repetir la ubicación: la vista ya está acotada
                          a una sola (selector obligatorio). */}
                      <th className="px-6 py-4 font-bold tracking-wider">Dispositivo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Valor</th>
                    </tr>
                  </thead>
                  <tbody>
                    {[...itemsOrdenados].reverse().map((item) => {
                      const fecha = new Date(item.fch_hr);
                      return (
                        <tr
                          key={`${item.id_prmtr}-${item.id_registro}`}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4">{fecha.toLocaleDateString("es", { timeZone: zonaHoraria })}</td>
                          <td className="px-6 py-4">{fecha.toLocaleTimeString("es", { timeZone: zonaHoraria })}</td>
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{item.parametro_nombre}</td>
                          <td className="px-6 py-4">{item.dispositivo_nombre}</td>
                          <td className="px-6 py-4">
                            {item.vlr} {item.undd}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}

            {vista === "grafico" && errorSeries && <p role="alert" className="text-red-500">{errorSeries}</p>}
            {vista === "grafico" && rangoFechas && (
              <div className="grid grid-cols-1 gap-6">
                {gruposComparables.map(grupo => <VisualizacionComparada
                  key={grupo.clave} grupo={grupo.series} rangoFechas={rangoFechas} zonaHoraria={zonaHoraria}
                  ambitoRango={consultaRango?.ambito ?? 0} revisionRefresco={consultaRango?.revision ?? 0} onActualizar={actualizarDatos} />)}
              </div>
            )}
            {vista === "grafico" && catalogoSeries?.ubicacion === ubicacionId && !seriesVisibles.length && (
              <p className="py-8 text-sm text-gray-500">No hay series numéricas mapeadas para esta selección.</p>
            )}
          </main>
        </div>
      </div>

      {/* Panel lateral de dataloggers: se pidió explícitamente que no
          fuera "todo lineal" -una sección más apilada en la pantalla-,
          así que es un drawer que se desliza desde la derecha por
          encima del contenido, en vez de ocupar espacio fijo. */}
      <DrawerPanel
        abierto={panelDataloggersAbierto}
        onCerrar={() => setPanelDataloggersAbierto(false)}
        titulo="Dataloggers"
        pie={
          dispositivosSeleccionados.length > 0 ? (
            <button
              type="button"
              onClick={() => setDispositivosSeleccionados([])}
              className="w-full px-4 py-2.5 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/5 dark:hover:bg-white/10 transition-all"
            >
              Quitar selección ({dispositivosSeleccionados.length})
            </button>
          ) : undefined
        }
      >
        <p className="text-xs text-gray-500 dark:text-gray-400 mb-4">
          {ubicaciones.find((u) => u.id_ubccn === ubicacionId)?.nmbr ?? ""} tiene {dispositivos.length}{" "}
          dataloggers. Sin ninguno marcado se muestran todos, con indicadores separados.
        </p>
        <div className="flex flex-col gap-1">
          {dispositivos.map((d) => (
            <label
              key={d.id_dspstv}
              className="flex items-center gap-2.5 text-sm text-gray-700 dark:text-gray-200 cursor-pointer rounded-lg px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            >
              <input
                type="checkbox"
                checked={dispositivosSeleccionados.includes(d.id_dspstv)}
                onChange={() => toggleDispositivo(d.id_dspstv)}
                className="accent-[#ccff00]"
              />
              {d.nmbr}
            </label>
          ))}
        </div>
      </DrawerPanel>
    </div>
  );
}

interface SolicitudGrupo {
  rango: RangoFechas;
}
interface RespuestaGrupo {
  fuentes: FuenteSerie[];
  errores: string[];
}
interface EstadoGrupo {
  ambito: string;
  consulta: { rango: RangoFechas; fuentes: FuenteSerie[]; revision: number } | null;
  errores: string[];
  cargando: boolean;
  desactualizado: boolean;
}

function VisualizacionComparada({ grupo, rangoFechas, zonaHoraria, ambitoRango, revisionRefresco, onActualizar }: {
  onActualizar: () => void;
  grupo: SerieTelemetria[]; rangoFechas: RangoFechas; zonaHoraria: string; ambitoRango: number; revisionRefresco: number;
}) {
  const [estado, setEstado] = useState<EstadoGrupo | null>(null);
  const [intento, setIntento] = useState(0);
  const [presentacion, setPresentacion] = useState<VistaSerie>(grupo.every(s => s.configuracion.vista === grupo[0].configuracion.vista)
    ? grupo[0].configuracion.vista : VISTAS_SERIE[grupo[0].configuracion.significado][0]);
  const [ocultas, setOcultas] = useState<number[]>([]);
  const [resumenAbierto, setResumenAbierto] = useState(false);
  const actualizador = useRef<ReturnType<typeof crearActualizadorSerial<SolicitudGrupo, RespuestaGrupo>> | null>(null);
  const revisionDatos = useRef(0);
  const ambito = JSON.stringify([grupo, zonaHoraria, ambitoRango]);
  const solicitud = JSON.stringify(rangoFechas);

  useEffect(() => {
    let montado = true;
    const [fuentes, zona] = JSON.parse(ambito) as [SerieTelemetria[], string, number];
    const controlador = crearActualizadorSerial<SolicitudGrupo, RespuestaGrupo>({
      ejecutar: async ({ rango }, signal) => {
        const params = new URLSearchParams({ fecha_inicio: rango.inicio, fecha_fin: rango.fin, zona_horaria: zona });
        const respuestas = await Promise.allSettled(fuentes.map(async serie => {
          const peticion = new AbortController();
          const cancelar = () => peticion.abort();
          signal.addEventListener("abort", cancelar, { once: true });
          if (signal.aborted) cancelar();
          let agotado = false;
          const limite = setTimeout(() => { agotado = true; peticion.abort(); }, 90_000);
          try {
            return { serie, datos: await apiFetch<DatosSerie>(`/mediciones/series/${serie.id_serie}?${params}`, { signal: peticion.signal }) };
          } catch (error) {
            if (agotado) throw new ApiError("La consulta tardó demasiado. Vuelve a intentarlo.", 408);
            throw error;
          } finally {
            clearTimeout(limite);
            signal.removeEventListener("abort", cancelar);
          }
        }));
        const resultado: RespuestaGrupo = { fuentes: [], errores: [] };
        respuestas.forEach((respuesta, i) => {
          if (respuesta.status === "fulfilled") resultado.fuentes.push(respuesta.value);
          else resultado.errores.push(`${nombreFuente(fuentes[i])}: ${respuesta.reason instanceof ApiError ? respuesta.reason.message : "No se pudieron cargar sus datos"}`);
        });
        return resultado;
      },
      alIniciar: () => queueMicrotask(() => {
        if (montado) setEstado(prev => prev?.ambito === ambito ? { ...prev, cargando: true }
          : { ambito, consulta: null, errores: [], cargando: true, desactualizado: false });
      }),
      alCompletar: (resultado, { rango }) => {
        const revision = ++revisionDatos.current;
        setEstado(prev => {
          const anterior = prev?.ambito === ambito ? prev.consulta : null;
          // Un fallo no reemplaza una consulta válida por datos incompletos
          // ni mezcla estadísticas de períodos distintos entre equipos.
          const conservar = resultado.errores.length > 0 && !!anterior?.fuentes.length;
          return { ambito, cargando: true, errores: resultado.errores, desactualizado: conservar,
            consulta: conservar ? anterior : { rango, fuentes: resultado.fuentes, revision } };
        });
      },
      alFallar: () => setEstado(prev => ({ ambito, consulta: prev?.ambito === ambito ? prev.consulta : null,
        errores: ["No se pudo actualizar esta consulta."], cargando: false, desactualizado: true })),
      alTerminar: () => setEstado(prev => prev?.ambito === ambito ? { ...prev, cargando: false } : prev),
    });
    actualizador.current = controlador;
    return () => { montado = false; controlador.cancelar(); actualizador.current = null; };
  }, [ambito]);

  useEffect(() => {
    actualizador.current?.pedir({ rango: JSON.parse(solicitud) as RangoFechas });
  }, [solicitud, ambito, revisionRefresco, intento]);

  const actual = estado?.ambito === ambito ? estado : null;
  const consulta = actual?.consulta;
  return <section className="min-w-0" aria-label={`Comparación de ${grupo[0].parametro_nombre}`}>
    <div className="min-h-5 text-xs text-gray-500 mb-2" role="status">
      {actual?.cargando ? consulta?.fuentes.length ? "Actualizando comparación…" : `Cargando ${grupo[0].parametro_nombre}…`
        : actual?.desactualizado ? "Se conserva la última consulta disponible; hay datos pendientes de actualizar."
        : consulta ? `Consulta hasta ${new Date(consulta.rango.fin).toLocaleString("es", { timeZone: zonaHoraria, dateStyle: "short", timeStyle: "medium" })}` : "Cargando comparación…"}
    </div>
    {!!actual?.errores.length && <div className="mb-3 text-sm text-red-600 dark:text-red-400" role="alert">
      {actual.errores.map(error => <p key={error}>{error}</p>)}
      <button type="button" className="mt-2 underline" onClick={() => setIntento(n => n + 1)}>Reintentar actualización</button>
    </div>}
    {!!consulta?.fuentes.length && <GraficoDeParametro
      serie={grupo[0]} datos={consulta.fuentes[0].datos} fuentes={consulta.fuentes} comparacion={grupo.length > 1}
      presentacion={presentacion} setPresentacion={setPresentacion} ocultas={ocultas} setOcultas={setOcultas}
      resumenAbierto={resumenAbierto} setResumenAbierto={setResumenAbierto} revisionDatos={consulta.revision}
      onActualizar={onActualizar} actualizando={actual?.cargando ?? false} desactualizado={actual?.desactualizado ?? false}
      zonaHoraria={zonaHoraria} rangoFechas={consulta.rango} />}
  </section>;
}

function GraficoDeParametro({ serie, datos, zonaHoraria, rangoFechas, presentacion, setPresentacion, fuentes, comparacion = false, ocultas = [], setOcultas, resumenAbierto, setResumenAbierto, revisionDatos, onActualizar, actualizando, desactualizado }: {
  onActualizar: () => void; actualizando: boolean; desactualizado: boolean;
  resumenAbierto: boolean; setResumenAbierto: (abierto: boolean) => void; revisionDatos: number;
  fuentes?: FuenteSerie[]; comparacion?: boolean; ocultas?: number[]; setOcultas?: (ids: number[]) => void;
  presentacion: VistaSerie; setPresentacion: (vista: VistaSerie) => void;
  serie: SerieTelemetria; datos: DatosSerie; zonaHoraria: string; rangoFechas: RangoFechas;
}) {
  const { esOscuro } = useTheme();
  const [hoverGuardado, setHoverGuardado] = useState<{ revision: number; valor: HoverInfo | null } | null>(null);
  const hover = hoverGuardado?.revision === revisionDatos ? hoverGuardado.valor : null;
  const onHover = (valor: HoverInfo | null) => setHoverGuardado({ revision: revisionDatos, valor });
  const idPanel = useId();
  const mostrarResumen = comparacion && resumenAbierto;
  const vistaKpi = presentacion === "kpi";
  function cambiarPanel(resumen: boolean) {
    setResumenAbierto(resumen);
    onHover(null);
  }
  function aislarFuente(id: number) {
    setOcultas?.((fuentes ?? [{ serie, datos }]).filter(f => f.serie.id_serie !== id).map(f => f.serie.id_serie));
    cambiarPanel(false);
    if (vistaKpi) setPresentacion(VISTAS_SERIE[serie.configuracion.significado].find(v => v !== "kpi") ?? "linea");
  }
  const tipoGrafico = presentacion === "area" ? "area" : "linea";
  const fuentesCompletas = fuentes ?? [{ serie, datos }];
  const fuentesVisibles = fuentesCompletas.filter(f => !ocultas.includes(f.serie.id_serie));
  const items = fuentesVisibles.flatMap(f => f.datos.items);
  const parametro = { id_prmtr: serie.id_prmtr, nmbr: serie.parametro_nombre, undd: serie.undd };
  const series = fuentesVisibles.map(f => ({ id: f.serie.id_serie, nombre: nombreFuente(f.serie),
    color: colorDatalogger(f.serie.id_dspstv), items: f.datos.items, barras: f.datos.resumen.barras }));

  const unidad = items[0]?.undd ?? parametro.undd;
  const significado = serie.configuracion.significado;
  const tipoVisualizacion = significado === "estado" ? "estado" : significado === "contador" || significado === "secuencia" ? "contador" : "continuo";
  const resumen = datos.resumen;
  const formatoNumero = new Intl.NumberFormat("es", { maximumFractionDigits: 6 });
  const etiquetaKpi = { continuo: "Última lectura", contador: "Eventos en el período", secuencia: "Tramas recibidas", estado: "Activaciones en el período", desconocido: "Última lectura" }[significado];

  const numero = (v: number | null) => v === null ? "—" : formatoNumero.format(v);
  const tiles = tipoVisualizacion === "continuo" ? [
    { etiqueta: "Lecturas únicas", valor: String(resumen.lecturas) },
    { etiqueta: "Mínimo", valor: numero(resumen.minimo) },
    { etiqueta: "Promedio", valor: numero(resumen.promedio) },
    { etiqueta: "Máximo", valor: numero(resumen.maximo) },
  ] : [
    { etiqueta: "Lecturas únicas", valor: String(resumen.lecturas) },
    { etiqueta: significado === "secuencia" ? "Último consecutivo" : "Último valor", valor: numero(resumen.ultimo) },
    { etiqueta: etiquetaKpi, valor: numero(resumen.valor) },
    { etiqueta: "Calidad del conteo", valor: resumen.parcial ? "Parcial" : "Disponible" },
  ];

  // Geometría del SVG: simple, sin librerías, siguiendo specs de marca fina
  // (línea 2px, extremos redondeados, grilla recesiva).
  const [pantallaCompleta, setPantallaCompleta] = useState(false);
  const [altoMarcador, setAltoMarcador] = useState(0);
  const [anchoGrafico, setAnchoGrafico] = useState(900);
  const [altoGrafico, setAltoGrafico] = useState(320);
  const ANCHO = anchoGrafico;
  const ALTO = altoGrafico;
  const PAD = { top: 16, right: 16, bottom: 32, left: 48 };

  // Zoom sobre el eje X (tiempo): un rango activo restringe minT/maxT sin
  // tocar la escala del eje Y. null = rango completo original. El zoom es
  // independiente de la pantalla completa y se conserva al salir de ella.
  const [zoomGuardado, setZoomT] = useState<{ min: number; max: number } | null>(null);
  const zoomT = acotarZoom(zoomGuardado, rangoFechas);
  const [seleccion, setSeleccion] = useState<{ x1: number; x2: number } | null>(null);
  const [arrastrando, setArrastrando] = useState(false);

  const contenedorRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);
  const areaGraficoRef = useRef<HTMLDivElement>(null);
  const botonAmpliarRef = useRef<HTMLButtonElement>(null);
  const scrollAnterior = useRef<{ elemento: HTMLElement; posicion: number } | null>(null);
  const hayDatos = items.length > 0;

  useEffect(() => {
    const contenedor = contenedorRef.current;
    if (!contenedor) return;
    const area = areaGraficoRef.current;
    const observador = new ResizeObserver(() => {
      if (!contenedor.isConnected) return;
      const estilo = getComputedStyle(contenedor);
      const ancho = Math.max(280, Math.round((area?.clientWidth ?? contenedor.clientWidth - parseFloat(estilo.paddingLeft) - parseFloat(estilo.paddingRight))));
      setAnchoGrafico(ancho);
      setAltoGrafico(pantallaCompleta && area ? Math.max(240, area.clientHeight) : ancho < 500 ? 260 : 320);
    });
    observador.observe(contenedor);
    if (area) observador.observe(area);
    return () => observador.disconnect();
  }, [pantallaCompleta, mostrarResumen, vistaKpi, hayDatos]);


  // Posición en pantalla (no en el viewBox del SVG) del tooltip de hover,
  // recalculada vía efecto -no durante el render, que es donde React ya
  // no permite leer refs- cada vez que cambia el punto resaltado o la
  // página se desplaza/redimensiona mientras el tooltip sigue abierto.
  const [posicionTooltip, setPosicionTooltip] = useState<{ left: number; top: number } | null>(null);
  useEffect(() => {
    let cancelado = false;
    if (!hover) {
      queueMicrotask(() => { if (!cancelado) setPosicionTooltip(null); });
      return () => { cancelado = true; };
    }
    const puntoActivo = hover;
    function recalcular() {
      const rect = svgRef.current?.getBoundingClientRect();
      if (!rect) return;
      setPosicionTooltip({
        left: rect.left + (puntoActivo.x / ANCHO) * rect.width,
        top: rect.top + (puntoActivo.y / ALTO) * rect.height,
      });
    }
    recalcular();
    window.addEventListener("scroll", recalcular, true);
    window.addEventListener("resize", recalcular);
    return () => {
      cancelado = true;
      window.removeEventListener("scroll", recalcular, true);
      window.removeEventListener("resize", recalcular);
    };
  }, [hover, ANCHO, ALTO]);

  useEffect(() => {
    if (!pantallaCompleta) return;
    const contenedor = contenedorRef.current;
    if (!contenedor) return;
    const overflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const fondo = [...document.body.children].filter((el): el is HTMLElement => el instanceof HTMLElement && el !== contenedor);
    const estados = fondo.map(el => ({ el, inert: el.inert }));
    fondo.forEach(el => { el.inert = true; });
    botonAmpliarRef.current?.focus({ preventScroll: true });
    const teclado = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        e.preventDefault(); e.stopPropagation();
        setPantallaCompleta(false);
      } else if (e.key === "Tab") {
        const controles = [...contenedor.querySelectorAll<HTMLElement>('button:not(:disabled), select:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]')]
          .filter(el => el.getClientRects().length > 0);
        const primero = controles[0], ultimo = controles.at(-1);
        if (e.shiftKey && (document.activeElement === primero || !contenedor.contains(document.activeElement))) {
          e.preventDefault(); ultimo?.focus();
        } else if (!e.shiftKey && (document.activeElement === ultimo || !contenedor.contains(document.activeElement))) {
          e.preventDefault(); primero?.focus();
        }
      }
    };
    document.addEventListener("keydown", teclado, true);
    return () => {
      document.removeEventListener("keydown", teclado, true);
      document.body.style.overflow = overflow;
      estados.forEach(({ el, inert }) => { el.inert = inert; });
      if (scrollAnterior.current?.elemento.isConnected) scrollAnterior.current.elemento.scrollTop = scrollAnterior.current.posicion;
      document.getElementById(`${idPanel}-ampliar`)?.focus({ preventScroll: true });
    };
  }, [pantallaCompleta, idPanel]);

  function alternarPantallaCompleta() {
    onHover(null);
    if (!pantallaCompleta) {
      setAltoMarcador(contenedorRef.current?.getBoundingClientRect().height ?? 0);
      const main = contenedorRef.current?.closest("main");
      scrollAnterior.current = main ? { elemento: main, posicion: main.scrollTop } : null;
    }
    setPantallaCompleta(!pantallaCompleta);
  }

  const todosLosValores = items.map((i) => i.vlr);
  // El eje Y siempre refleja el rango completo de valores: el zoom es
  // exclusivo del eje X (tiempo), sin alterar esta escala.
  const minVlr = todosLosValores.length ? Math.min(...todosLosValores) : 0;
  const maxVlrDatos = todosLosValores.length ? Math.max(...todosLosValores) : 1;
  const maxVlr = maxVlrDatos === minVlr ? minVlr + Math.max(Math.abs(minVlr) * 0.01, 1) : maxVlrDatos;
  const minTOriginal = new Date(rangoFechas.inicio).getTime();
  const maxTOriginal = new Date(rangoFechas.fin).getTime();
  const rangoVlr = maxVlr - minVlr || 1;

  // Decimales para las etiquetas del eje Y: los suficientes para que las
  // líneas de grilla se lean distintas entre sí. Con .toFixed(1) fijo, un
  // rango angosto (p. ej. 11.66-11.77) redondeaba varias líneas distintas
  // al mismo texto ("11.7", "11.7", "11.8"), y aunque el PUNTO se ubicaba
  // en su posición real, dos etiquetas iguales seguidas hacían parecer
  // que esa posición no correspondía a la mitad entre ambas -el problema
  // era de redondeo de la etiqueta, no de dónde se dibuja el punto-.
  const decimalesEje = rangoVlr < 1 ? 3 : rangoVlr < 10 ? 2 : rangoVlr < 100 ? 1 : 0;

  const minT = zoomT ? zoomT.min : minTOriginal;
  const maxT = zoomT ? zoomT.max : maxTOriginal;
  const rangoT = maxT - minT || 1;

  function xDe(item: MedicionNumerica) {
    const t = new Date(item.fch_hr).getTime();
    return PAD.left + ((t - minT) / rangoT) * (ANCHO - PAD.left - PAD.right);
  }
  function yDe(item: MedicionNumerica) {
    return PAD.top + (1 - (item.vlr - minVlr) / rangoVlr) * (ALTO - PAD.top - PAD.bottom);
  }

  // Solo se dibujan los puntos dentro del rango de zoom actual.
  function enRangoZoom(item: MedicionNumerica) {
    const t = new Date(item.fch_hr).getTime();
    return t >= minT && t <= maxT;
  }

  // Un contador acumulativo se muestra por defecto como eventos ocurridos
  // por intervalo ("cuántas veces se abrió la puerta el martes"), que es
  // la pregunta que se le hace, y no como el número corrido del equipo.
  // El toggle Área deja ver el acumulado en escalón cuando hace falta.
  const modoDelta = presentacion === "barras";
  const intervaloDelta = resumen.intervalo;
  const seriesDeBarras = modoDelta ? series : [];

  // Escala propia: los deltas son de otra magnitud que el acumulado (12
  // eventos vs. un contador en 30.071), así que reusar la escala del
  // acumulado dejaría todas las barras pegadas al piso del gráfico.
  const maxDelta = Math.max(
    1,
    ...seriesDeBarras.flatMap((s) => s.barras.map((b) => b.delta)),
  );
  function yDeDelta(delta: number) {
    return PAD.top + (1 - delta / maxDelta) * (ALTO - PAD.top - PAD.bottom);
  }
  function xDeTiempo(t: number) {
    return PAD.left + ((t - minT) / rangoT) * (ANCHO - PAD.left - PAD.right);
  }

  function modificarZoom(factor: number) {
    const total = maxTOriginal - minTOriginal;
    const ancho = Math.min(total, Math.max(1000, (maxT - minT) * factor));
    if (ancho >= total) { setZoomT(null); return; }
    const inicio = Math.max(minTOriginal, Math.min((minT + maxT - ancho) / 2, maxTOriginal - ancho));
    setZoomT({ min: inicio, max: inicio + ancho });
    onHover(null);
  }

  function coordenadaSvgX(clientX: number): number {
    const rect = svgRef.current?.getBoundingClientRect();
    if (!rect || rect.width === 0) return 0;
    return ((clientX - rect.left) / rect.width) * ANCHO;
  }


  function xATiempo(x: number): number {
    return minT + ((x - PAD.left) / (ANCHO - PAD.left - PAD.right)) * rangoT;
  }

  function iniciarSeleccion(e: React.MouseEvent<SVGSVGElement>) {
    const x = coordenadaSvgX(e.clientX);
    setArrastrando(true);
    setSeleccion({ x1: x, x2: x });
  }

  function actualizarSeleccion(e: React.MouseEvent<SVGSVGElement>) {
    if (!arrastrando) return;
    const x = coordenadaSvgX(e.clientX);
    setSeleccion((s) => (s ? { ...s, x2: x } : null));
  }

  function finalizarSeleccion() {
    if (!arrastrando) return;
    setArrastrando(false);
    setSeleccion((s) => {
      if (s) {
        const xMin = Math.min(s.x1, s.x2);
        const xMax = Math.max(s.x1, s.x2);
        // Ignorar arrastres insignificantes (clic simple sin selección real).
        if (xMax - xMin >= 8) {
          setZoomT({ min: xATiempo(xMin), max: xATiempo(xMax) });
        }
      }
      return null;
    });
  }

  const yBase = ALTO - PAD.bottom;
  const lineasGrilla = 4;

  // El SVG se dibuja con currentColor no aplica a stroke/fill fijos, así que
  // la grilla, el texto de los ejes y el borde del punto en hover eligen su
  // color según el tema activo en vez de asumir siempre fondo oscuro.
  const colorGrilla = esOscuro ? "rgba(255,255,255,0.08)" : "rgba(0,0,0,0.08)";
  const colorTextoEje = esOscuro ? "rgba(255,255,255,0.4)" : "rgba(0,0,0,0.45)";
  const colorFondoContraste = esOscuro ? "#0b1220" : "#ffffff";

  const contenido = (
    <div
      ref={contenedorRef}
      role={pantallaCompleta ? "dialog" : undefined} aria-modal={pantallaCompleta ? true : undefined}
      aria-labelledby={pantallaCompleta ? `${idPanel}-titulo` : undefined} tabIndex={pantallaCompleta ? -1 : undefined}
      onKeyDown={e => {
        if (!pantallaCompleta || mostrarResumen || vistaKpi || (e.target instanceof HTMLElement && e.target.matches("input, select, textarea"))) return;
        if (["+", "=", "-"].includes(e.key)) { e.preventDefault(); modificarZoom(e.key === "-" ? 2 : 0.5); }
      }}
      className={
        pantallaCompleta
          ? "fixed inset-0 z-[100] bg-white dark:bg-[#0b1220] h-[100dvh] w-full flex flex-col overflow-hidden"
          : "bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl border border-black/10 dark:border-white/10 p-5"
      }
    >
      <div className={`flex items-center justify-between flex-wrap gap-3 shrink-0 ${pantallaCompleta ? "p-4 md:px-8 md:py-5 border-b border-black/10 dark:border-white/10" : "mb-4"}`}>
        <h2 id={`${idPanel}-titulo`} className={`${pantallaCompleta ? "text-lg md:text-xl" : "text-sm"} font-bold text-gray-900 dark:text-white`}>
          <span className="block text-xs font-normal text-gray-500 dark:text-gray-400 mb-1">{serie.ubicacion_nombre} · {comparacion ? `${fuentesCompletas.length} fuentes comparadas` : `${serie.dispositivo_nombre} · Trama ${serie.tp_trm}`}</span>
          {parametro.nmbr}{unidad && !["-", "N/A"].includes(unidad) ? ` (${unidad})` : ""}{modoDelta ? ` · ${etiquetaDeIntervalo(intervaloDelta)}` : ""}
        </h2>

        <div className="flex items-center gap-4 flex-wrap">
          {!mostrarResumen && <label className="text-xs text-gray-500 dark:text-gray-400 flex items-center gap-2">Mostrar
            <select aria-label={comparacion ? `Vista comparada de ${parametro.nmbr}` : `Vista de ${parametro.nmbr} en ${serie.dispositivo_nombre}`} value={presentacion}
              onChange={e => { setPresentacion(e.target.value as VistaSerie); onHover(null); }}
              className="rounded-lg border border-black/15 dark:border-white/20 bg-white dark:bg-[#1a202c] px-3 py-2 text-sm text-gray-900 dark:text-white">
              {VISTAS_SERIE[significado].map(v => <option key={v} value={v}>{NOMBRES_VISTA[v]}</option>)}
            </select>
          </label>}
          <div className="flex items-center gap-2">
            {pantallaCompleta && <button type="button" onClick={onActualizar} disabled={actualizando}
              className="px-3 py-2 text-sm font-medium rounded-lg hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-50 text-gray-700 dark:text-gray-200">
              {actualizando ? "Actualizando…" : "Actualizar"}
            </button>}
            {pantallaCompleta && !mostrarResumen && !vistaKpi && <div className="flex rounded-lg border border-black/15 dark:border-white/15">
              <button type="button" aria-label="Alejar gráfico" onClick={() => modificarZoom(2)} disabled={!zoomT} className="px-3 py-1.5 text-lg disabled:opacity-40 dark:text-white">−</button>
              <button type="button" aria-label="Acercar gráfico" onClick={() => modificarZoom(0.5)} className="px-3 py-1.5 text-lg dark:text-white">+</button>
            </div>}
            {!mostrarResumen && !vistaKpi && zoomT && (
              <button
                type="button"
                onClick={() => setZoomT(null)}
                className="text-xs font-semibold px-3 py-1.5 rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:border-[#ccff00] hover:text-[#ccff00] transition-colors"
              >
                Restablecer zoom
              </button>
            )}

            <button
              type="button"
              ref={botonAmpliarRef}
              id={`${idPanel}-ampliar`}
              onClick={alternarPantallaCompleta}
              title={pantallaCompleta ? "Cerrar vista ampliada (Esc)" : "Ampliar visualización"}
              aria-label={pantallaCompleta ? "Cerrar vista ampliada" : "Ampliar visualización"}
              className="flex items-center gap-2 p-1.5 rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:border-[#ccff00] hover:text-[#ccff00] transition-colors"
            >
              {pantallaCompleta ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M6 6l12 12M18 6L6 18" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" />
                </svg>
              )}
              {pantallaCompleta && <span className="pr-1 text-sm">Cerrar</span>}
            </button>
          </div>
        </div>
      </div>
      {pantallaCompleta && <div className="px-4 md:px-8 py-3 shrink-0 flex flex-wrap gap-x-5 gap-y-1 text-xs text-gray-500 dark:text-gray-400 border-b border-black/5 dark:border-white/5">
        <span>{new Date(rangoFechas.inicio).toLocaleString("es", { timeZone: zonaHoraria, dateStyle: "medium", timeStyle: "short" })} — {new Date(rangoFechas.fin).toLocaleString("es", { timeZone: zonaHoraria, dateStyle: "medium", timeStyle: "short" })}</span>
        <span>{zonaHoraria}</span>
        <span role="status" className={desactualizado ? "text-amber-700 dark:text-amber-300" : ""}>{actualizando ? "Actualizando datos…" : desactualizado ? "No se pudo actualizar. Se conserva la última consulta." : "Consulta actualizada"}</span>
      </div>}

      {comparacion && <div role="tablist" aria-label={`Contenido de ${parametro.nmbr}`} className={`flex gap-6 border-b border-black/10 dark:border-white/10 shrink-0 ${pantallaCompleta ? "px-4 md:px-8 pt-4" : "mb-5"}`}>
        {[{ resumen: false, nombre: vistaKpi ? "KPI" : "Gráfico" }, { resumen: true, nombre: "Resumen por equipo" }].map((tab, indice) => <button
          key={String(tab.resumen)} type="button" role="tab" id={`${idPanel}-${tab.resumen ? "resumen" : "grafico"}`}
          aria-controls={`${idPanel}-contenido`} aria-selected={mostrarResumen === tab.resumen} tabIndex={mostrarResumen === tab.resumen ? 0 : -1}
          onClick={() => cambiarPanel(tab.resumen)}
          onKeyDown={e => {
            if (!["ArrowRight", "ArrowLeft", "Home", "End"].includes(e.key)) return;
            e.preventDefault();
            const siguiente = e.key === "Home" ? 0 : e.key === "End" ? 1 : 1 - indice;
            cambiarPanel(siguiente === 1);
            (e.currentTarget.parentElement?.querySelectorAll<HTMLButtonElement>('[role="tab"]')[siguiente])?.focus();
          }}
          className={`pb-3 text-sm font-medium border-b-2 -mb-px transition-colors ${mostrarResumen === tab.resumen ? "border-[#809f00] dark:border-[#ccff00] text-gray-900 dark:text-white" : "border-transparent text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white"}`}>
          {tab.nombre}
        </button>)}
      </div>}
      <div role={comparacion ? "tabpanel" : undefined} id={`${idPanel}-contenido`}
        className={pantallaCompleta ? "flex-1 min-h-0 flex flex-col overflow-y-auto overscroll-contain p-4 md:p-8" : undefined}
        aria-labelledby={comparacion ? `${idPanel}-${mostrarResumen ? "resumen" : "grafico"}` : undefined}>
      {comparacion && !mostrarResumen && !vistaKpi && <div className="flex flex-wrap items-center gap-x-4 gap-y-2 mb-4" aria-label="Series visibles">
        {fuentesCompletas.map(f => <button type="button" key={f.serie.id_serie} aria-pressed={!ocultas.includes(f.serie.id_serie)}
          onClick={() => { onHover(null); setOcultas?.(ocultas.includes(f.serie.id_serie) ? ocultas.filter(id => id !== f.serie.id_serie) : [...ocultas, f.serie.id_serie]); }}
          className={`flex items-center gap-2 text-xs py-1 ${ocultas.includes(f.serie.id_serie) ? "opacity-40 line-through" : "text-gray-700 dark:text-gray-200"}`}>
          <span className="w-5 h-0.5" style={{ backgroundColor: colorDatalogger(f.serie.id_dspstv) }} />{nombreFuente(f.serie)}
        </button>)}
        {!!ocultas.length && <button type="button" onClick={() => { setOcultas?.([]); onHover(null); }} className="text-xs font-semibold underline">Mostrar todos</button>}
      </div>}
      {!comparacion && !serie.configuracion.confirmada && <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">{significado === "desconocido" ? "Significado pendiente: se muestra el valor recibido sin interpretarlo como eventos." : "Clasificación sugerida por el encabezado. Pendiente de confirmar en los datos del datalogger."}</p>}
      {!comparacion && resumen.parcial && <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">Conteo parcial: falta la lectura anterior al rango o hubo una disminución sin regla de reinicio confirmada.</p>}
      {!comparacion && resumen.sin_origen && <p className="mb-4 text-xs text-amber-700 dark:text-amber-300">Hay lecturas manuales sin formato identificado. Se excluyeron para no mezclar tramas.</p>}
      {fuentesCompletas.some(f => f.datos.muestreado) && !mostrarResumen && !vistaKpi && !modoDelta && <p className="mb-3 text-xs text-gray-500">Se reducen los puntos del gráfico para facilitar la lectura. Los resúmenes y las barras usan todas las mediciones.</p>}
      {mostrarResumen ? <ComparacionDataloggers fuentes={fuentesCompletas} zonaHoraria={zonaHoraria} etiquetaKpi={etiquetaKpi}
        kpi={false} ampliado={pantallaCompleta} ocultas={ocultas} onSolo={aislarFuente} /> : vistaKpi ? (pantallaCompleta ? <KpisAmpliados fuentes={fuentesCompletas} etiqueta={etiquetaKpi} zonaHoraria={zonaHoraria} onEvolucion={aislarFuente} /> : comparacion ? <ComparacionDataloggers fuentes={fuentesCompletas} zonaHoraria={zonaHoraria} etiquetaKpi={etiquetaKpi}
        kpi ocultas={ocultas} onSolo={aislarFuente} /> :
        <div className="py-4 sm:py-6" aria-live="polite">
          <p className="text-xs font-bold uppercase tracking-widest text-gray-500 dark:text-gray-400">{etiquetaKpi}</p>
          <p className="mt-2 text-5xl sm:text-6xl font-semibold tabular-nums tracking-tight text-gray-900 dark:text-white">
            {resumen.valor === null ? "—" : formatoNumero.format(resumen.valor)}
            {significado === "continuo" && unidad && !["-", "N/A"].includes(unidad) && <span className="text-lg ml-2">{unidad}</span>}
          </p>
          <p className="mt-3 text-sm text-gray-500 dark:text-gray-400">
            {significado === "secuencia" ? "Tramas únicas por fecha y consecutivo; los saltos no cuentan como acciones." : significado === "contador" ? "Incrementos del contador dentro del rango seleccionado." : significado === "estado" ? "Cambios observados de 0 a 1 dentro del rango." : "Valor más reciente dentro del rango seleccionado."}
          </p>
          {(significado === "contador" || significado === "secuencia") && <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">
            {significado === "secuencia" ? "Último consecutivo" : "Acumulado actual"}: {resumen.ultimo === null ? "—" : formatoNumero.format(resumen.ultimo)}
          </p>}
          <div className="mt-5 flex flex-wrap gap-x-5 gap-y-2 border-t border-black/10 dark:border-white/10 pt-4 text-xs text-gray-500 dark:text-gray-400">
            <span>{resumen.lecturas.toLocaleString("es")} lecturas únicas</span>
            {resumen.duplicados > 0 && <span>{resumen.duplicados} duplicados excluidos</span>}
            {resumen.reinicios > 0 && <span>{resumen.reinicios} disminuciones del contador</span>}
            {significado === "secuencia" && <span>{resumen.saltos_secuencia} posiciones saltadas</span>}
            {resumen.ultima_lectura && <span>Última lectura: {formatearFechaCorta(resumen.ultima_lectura, zonaHoraria)}</span>}
          </div>
        </div>
      ) : (
      <>
      {!comparacion && <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {tiles.map((tile) => (
          <div key={tile.etiqueta} className="bg-black/5 dark:bg-white/5 rounded-xl p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{tile.etiqueta}</div>
            <div className="text-lg font-bold text-gray-900 dark:text-white mt-0.5">{tile.valor}</div>
          </div>
        ))}
      </div>}

      {items.length === 0 ? (
        <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
          {fuentesVisibles.length === 0 ? "Activa un datalogger en la leyenda para ver su serie." : "No hay mediciones registradas para este parámetro en el período seleccionado."}
        </div>
      ) : (
        <div ref={areaGraficoRef} className={`relative w-full ${pantallaCompleta ? "flex-1 min-h-[240px]" : "overflow-x-auto"}`}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${ANCHO} ${ALTO}`}
            // select-none: el arrastre para hacer zoom (iniciarSeleccion/
            // actualizarSeleccion) es un mousedown+drag sobre el SVG, y
            // sin esto el navegador lo interpreta como una selección de
            // texto normal -resalta en azul las etiquetas del eje Y y
            // muestra su menú contextual de "copiar/buscar" al soltar-.
            className={`${pantallaCompleta ? "absolute inset-0 w-full h-full" : "w-full h-auto"} cursor-crosshair select-none`}
            onDoubleClick={() => { setZoomT(null); onHover(null); }}
            role="img" aria-label={`Gráfico de ${parametro.nmbr}`}
            onMouseDown={iniciarSeleccion}
            onMouseMove={actualizarSeleccion}
            onMouseUp={finalizarSeleccion}
            onMouseLeave={finalizarSeleccion}
          >
            <defs>
              {/* Resplandor del punto en hover: mismo color de la serie, sin
                  agregar un color nuevo a la paleta. */}
              <filter id="glowPuntoHover" x="-200%" y="-200%" width="500%" height="500%">
                <feGaussianBlur stdDeviation="3" result="blur" />
                <feMerge>
                  <feMergeNode in="blur" />
                  <feMergeNode in="SourceGraphic" />
                </feMerge>
              </filter>
            </defs>

            {/* Grilla recesiva. En modo delta el eje Y cuenta eventos por
                intervalo, no el valor acumulado, así que la escala y las
                etiquetas son las de las barras. */}
            {Array.from({ length: lineasGrilla + 1 }).map((_, i) => {
              const y = PAD.top + (i / lineasGrilla) * (ALTO - PAD.top - PAD.bottom);
              const valor = modoDelta
                ? maxDelta - (i / lineasGrilla) * maxDelta
                : maxVlr - (i / lineasGrilla) * rangoVlr;
              return (
                <g key={i}>
                  <line x1={PAD.left} x2={ANCHO - PAD.right} y1={y} y2={y} stroke={colorGrilla} strokeWidth={1} />
                  <text x={PAD.left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={colorTextoEje}>
                    {modoDelta ? Math.round(valor).toLocaleString("es") : valor.toFixed(decimalesEje)}
                  </text>
                </g>
              );
            })}

            {/* Eje de tiempo: primero y último timestamp */}
            <text x={PAD.left} y={ALTO - 10} fontSize={10} fill={colorTextoEje}>
              {formatearFechaCorta(new Date(minT).toISOString(), zonaHoraria)}
            </text>
            <text x={ANCHO - PAD.right} y={ALTO - 10} textAnchor="end" fontSize={10} fill={colorTextoEje}>
              {formatearFechaCorta(new Date(maxT).toISOString(), zonaHoraria)}
            </text>

            {/* Barras de delta: eventos por intervalo. Las series se
                dibujan lado a lado dentro de cada bucket para que dos
                dataloggers no se tapen entre sí. */}
            {modoDelta &&
              seriesDeBarras.map((s, indiceSerie) => {
                const color = s.color;

                return (
                  <g key={`barras-${s.id}`} data-serie-id={s.id}>
                    {s.barras.map((b) => {
                      if (b.t_fin <= minT || b.t > maxT) return null;
                      const izquierda = xDeTiempo(Math.max(b.t, minT));
                      const derecha = xDeTiempo(Math.min(b.t_fin, maxT));
                      const anchoGrupo = Math.min(80, derecha - izquierda) * 0.8;
                      const anchoBarra = Math.max(0.5, anchoGrupo / seriesDeBarras.length);
                      const x = izquierda + (derecha - izquierda - anchoGrupo) / 2 + indiceSerie * anchoBarra;
                      const y = yDeDelta(b.delta);
                      const alto = Math.max(1, ALTO - PAD.bottom - y);
                      if (x + anchoBarra < PAD.left || x > ANCHO - PAD.right) return null;
                      return (
                        <rect
                          key={b.t}
                          x={x}
                          y={y}
                          width={anchoBarra}
                          height={alto}
                          fill={color}
                          fillOpacity={0.85}
                        ><title>{formatearFechaCorta(new Date(b.t).toISOString(), zonaHoraria)}: {formatoNumero.format(b.delta)} · {s.nombre}</title></rect>
                      );
                    })}
                  </g>
                );
              })}

            {!modoDelta && series.map((s) => {
              const color = s.color;

              const itemsVisibles = s.items.filter(enRangoZoom);
              const coords = itemsVisibles.map((item) => ({ x: xDe(item), y: yDe(item) }));
              // Un contador y un estado se mantienen planos entre lecturas
              // y saltan de golpe: la spline los dibujaría subiendo de a
              // poco, inventando valores intermedios que nunca se midieron.
              const trazo =
                presentacion === "linea" || presentacion === "area" ? pathDeLinea(coords) : pathDeEscalon(coords);
              // Radio del punto visible, adaptado a cuánto espacio real
              // hay entre una medición y la siguiente. Con un radio fijo
              // (antes 3px siempre), una serie de varios cientos de
              // puntos en los ~836px útiles del gráfico terminaba con
              // menos de 2px entre centros -bastante menos que su propio
              // diámetro-, así que los puntos se solapaban entre sí y
              // tapaban la línea en vez de solo marcar cada dato. Achicar
              // el punto (o quitarlo del todo a partir de cierta
              // densidad, dejando solo la línea) no pierde ningún dato:
              // el círculo invisible de abajo -que sostiene el hover-
              // sigue del mismo tamaño siempre.
              const anchoUtil = ANCHO - PAD.left - PAD.right;
              const espacioPorPunto = itemsVisibles.length > 1 ? anchoUtil / (itemsVisibles.length - 1) : anchoUtil;
              const radioPunto = espacioPorPunto > 12 ? 3 : espacioPorPunto > 6 ? 2 : 0;
              // El punto resaltado solo se dibuja en la serie a la que
              // pertenece, para que su color coincida con el de su línea.
              const indiceHover = hover && hover.serieId === s.id
                ? itemsVisibles.findIndex((item) => item.id_registro === hover.item.id_registro)
                : -1;
              const puntoEnHover = indiceHover >= 0 ? coords[indiceHover] : null;
              // El área reutiliza el mismo trazo de la línea (reemplazando
              // su "M" inicial por un "L") y lo cierra contra la base: así
              // el borde superior del relleno calca exactamente la línea.
              const areaPath =
                coords.length > 0
                  ? `M ${coords[0].x},${yBase} L` +
                    trazo.slice(1) +
                    ` L ${coords[coords.length - 1].x},${yBase} Z`
                  : "";
              return (
                <g key={s.id} data-serie-id={s.id}>
                  {tipoGrafico === "area" && areaPath && <path d={areaPath} fill={color} fillOpacity={0.18} stroke="none" />}
                  <path d={trazo} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  {/* Cada medición lleva un punto chico -guía visual de que
                      ahí hay un dato para pasar el mouse, sin saturar el
                      trazo- en el color de la serie, más un círculo invisible
                      más grande encima que amplía el área de captura del
                      hover sin agrandar lo que se ve. El punto en hover se
                      resalta aparte, más abajo (línea guía + glow). */}
                  {itemsVisibles.map((item, indice) => {
                    const puntoActivo = hover?.serieId === s.id && hover.item.id_registro === item.id_registro;
                    return (
                    <g key={item.id_registro}>
                      {!puntoActivo && radioPunto > 0 && (
                        <circle cx={coords[indice].x} cy={coords[indice].y} r={radioPunto} fill={color} pointerEvents="none" />
                      )}
                      <circle
                        cx={coords[indice].x}
                        cy={coords[indice].y}
                        r={6}
                        fill="transparent"
                        className="cursor-pointer"
                        onMouseEnter={() => onHover({ serieId: s.id, parametroId: parametro.id_prmtr, x: coords[indice].x, y: coords[indice].y, item })}
                        onMouseLeave={() =>
                          onHover(hover?.serieId === s.id && hover.item.id_registro === item.id_registro ? null : hover)
                        }
                      />
                    </g>
                    );
                  })}
                  {puntoEnHover && (
                    <g pointerEvents="none">
                      {/* Cruce de líneas guía (vertical al eje de tiempo,
                          horizontal al eje de valor) + glow chico en el
                          punto: mismo color de la serie, sin sumar un color
                          nuevo, para reconocer dónde se está tocando. */}
                      <line
                        x1={puntoEnHover.x}
                        x2={puntoEnHover.x}
                        y1={puntoEnHover.y}
                        y2={yBase}
                        stroke={color}
                        strokeWidth={1}
                        strokeDasharray="3 3"
                        strokeOpacity={0.6}
                      />
                      <line
                        x1={PAD.left}
                        x2={puntoEnHover.x}
                        y1={puntoEnHover.y}
                        y2={puntoEnHover.y}
                        stroke={color}
                        strokeWidth={1}
                        strokeDasharray="3 3"
                        strokeOpacity={0.6}
                      />
                      <circle cx={puntoEnHover.x} cy={puntoEnHover.y} r={9} fill={color} fillOpacity={0.25} filter="url(#glowPuntoHover)" />
                      <circle
                        cx={puntoEnHover.x}
                        cy={puntoEnHover.y}
                        r={4}
                        fill={color}
                        stroke={colorFondoContraste}
                        strokeWidth={1.5}
                      />
                    </g>
                  )}
                </g>
              );
            })}

            {/* Rectángulo de selección mientras se arrastra para hacer zoom */}
            {seleccion && Math.abs(seleccion.x2 - seleccion.x1) >= 2 && (
              <rect
                x={Math.min(seleccion.x1, seleccion.x2)}
                y={PAD.top}
                width={Math.abs(seleccion.x2 - seleccion.x1)}
                height={ALTO - PAD.top - PAD.bottom}
                fill="rgba(204,255,0,0.15)"
                stroke="#ccff00"
                strokeWidth={1}
              />
            )}
          </svg>

          {hover &&
            posicionTooltip &&
            createPortal(
              // Portal a document.body con `position: fixed`: el tooltip
              // vivía dentro de un contenedor con overflow-x-auto (y sin
              // overflow visible hacia arriba tampoco), así que cerca de
              // cualquier borde -no solo el horizontal, también pegado al
              // techo del gráfico- quedaba recortado a la mitad en vez de
              // mostrarse completo por encima de todo lo demás.
              <div
                role="tooltip" className="fixed pointer-events-none bg-white dark:bg-[#0b1220] border border-black/20 dark:border-white/20 rounded-lg px-3 py-2 text-xs text-gray-900 dark:text-white shadow-xl z-[150]"
                style={{
                  left: posicionTooltip.left,
                  top: posicionTooltip.top,
                  transform: `translate(${
                    hover.x > ANCHO * 0.85 ? "-100%" : hover.x < ANCHO * 0.15 ? "0%" : "-50%"
                  }, ${
                    // Si no hay suficiente espacio arriba del punto en la
                    // pantalla real (no en el SVG), el tooltip se muestra
                    // debajo en vez de arriba -mismo problema que el
                    // horizontal, pero en el eje vertical-.
                    posicionTooltip.top < 90 ? "20%" : "-120%"
                  })`,
                }}
              >
                <div className="font-semibold">
                  {hover.item.vlr} {hover.item.undd}
                </div>
                {/* Solo el dispositivo: la ubicación ya está fija por
                    el selector obligatorio, repetirla sería ruido. */}
                <div className="text-gray-500 dark:text-gray-400">{series.find(s => s.id === hover.serieId)?.nombre ?? hover.item.dispositivo_nombre}</div>
                <div className="text-gray-500 dark:text-gray-400">
                  {new Date(hover.item.fch_hr).toLocaleString("es", { timeZone: zonaHoraria, dateStyle: "medium", timeStyle: "medium" })}
                </div>
              </div>,
              document.body,
            )}
        </div>
      )}
      </>
      )}
      </div>
      {pantallaCompleta && !mostrarResumen && !vistaKpi && <div className="shrink-0 border-t border-black/10 dark:border-white/10 px-4 md:px-8 py-3 flex flex-wrap justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
        <span>Arrastra para acercar · Doble clic para restablecer · Teclas + y −</span>
        <span>{fuentesVisibles.length} de {fuentesCompletas.length} series visibles</span>
      </div>}
    </div>
  );
  return pantallaCompleta ? <><div style={{ height: altoMarcador }} aria-hidden="true" />{createPortal(contenido, document.body)}</> : contenido;
}
