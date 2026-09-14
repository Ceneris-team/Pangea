import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { useTheme } from "../context/ThemeContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import SelectorRangoFechasTimeline from "../components/SelectorRangoFechasTimeline";
import {
  claseColumnasGrilla,
  construirQuery,
  COLORES_SERIE,
  formatearFechaCorta,
  pathDeLinea,
  type DispositivoItem,
  type HoverInfo,
  type ListadoMediciones,
  type MedicionNumerica,
  type ParametroItem,
  type TipoGrafico,
  type UbicacionItem,
  type Vista,
} from "./graficosUtils";
import type { RangoFechas } from "../utils/fechas";

/**
 * HU15: visualización de telemetría en gráficos interactivos. El usuario
 * selecciona parámetros (aplican al instante, sin botón "APLICAR") y un
 * rango de fechas con el selector tipo línea de tiempo; por cada parámetro
 * elegido se dibuja un gráfico independiente (una línea por ubicación, con
 * leyenda), y puede alternar entre tipo línea/área o ver los mismos datos
 * en tabla ("VER TABLA"). La grilla de gráficos usa 1 columna con 1-3
 * parámetros, 2 columnas con 4-6, y 3 columnas (en pantallas grandes) con
 * 7-8.
 *
 * Los tipos, constantes y funciones puras (construirQuery, pathDeLinea,
 * etc.) viven en graficosUtils.ts y no acá: un módulo que mezcla
 * componentes React con funciones sueltas rompe el "Fast Refresh
 * boundary" de Vite/React, y en dev eso puede dejar el navegador
 * ejecutando una mezcla de código viejo y nuevo entre ediciones en
 * caliente -se vio en vivo un TypeError en una firma de función que en
 * el archivo real ya no existía-.
 */

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
  const [rangoFechas, setRangoFechas] = useState<RangoFechas | null>(null);

  const [tipoGrafico, setTipoGrafico] = useState<TipoGrafico>("linea");
  const [vista, setVista] = useState<Vista>("grafico");

  const [mediciones, setMediciones] = useState<ListadoMediciones | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [hover, setHover] = useState<HoverInfo | null>(null);

  // Solo tiene sentido graficar parámetros numéricos (línea/área).
  const parametrosGraficables = useMemo(
    () => parametros.filter((p) => p.tipo_dato === "numerico"),
    [parametros],
  );

  useEffect(() => {
    apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros")
      .then((res) => {
        setParametros(res.items);
        const primerNumerico = res.items.find((p) => p.tipo_dato === "numerico");
        if (primerNumerico) setParametrosSeleccionados([primerNumerico.id_prmtr]);
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
    setDispositivosSeleccionados([]);
    setPanelDataloggersAbierto(false);
    if (!ubicacionIdValida) {
      setDispositivos([]);
      return;
    }
    apiFetch<{ items: DispositivoItem[] }>("/dispositivos", {
      params: { por_pagina: 100, id_ubccn: ubicacionId as number },
    })
      .then((res) => setDispositivos(res.items))
      .catch(() => setDispositivos([]));
  }, [ubicacionIdValida, ubicacionId]);

  useEffect(() => {
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
      setMediciones(null);
      return;
    }
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoMediciones>(
      construirQuery(
        parametrosSeleccionados,
        [ubicacionId as number],
        dispositivosSeleccionados,
        rangoFechas,
      ),
    )
      .then((res) => {
        if (!cancelado) setMediciones(res);
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
  }, [parametrosSeleccionados, rangoFechas, ubicacionId, ubicacionIdValida, dispositivosSeleccionados]);

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
  const cargandoPrimeraVez = loading && mediciones === null;

  // El backend devuelve más reciente primero; para la línea de tiempo se
  // necesita orden cronológico ascendente. Solo valores numéricos son
  // graficables (los parámetros de texto no aplican a línea/área).
  const itemsOrdenados = useMemo(() => {
    return [...(mediciones?.items ?? [])]
      .filter((item): item is MedicionNumerica => typeof item.vlr === "number")
      .sort((a, b) => new Date(a.fch_hr).getTime() - new Date(b.fch_hr).getTime());
  }, [mediciones]);

  // Un gráfico por cada parámetro seleccionado (aunque todavía no tenga
  // datos), en el orden del catálogo para que no salte con la selección:
  // así N parámetros elegidos siempre producen N gráficos.
  const parametrosARenderizar = useMemo(() => {
    const porParametro = new Map<number, MedicionNumerica[]>();
    for (const item of itemsOrdenados) {
      const lista = porParametro.get(item.id_prmtr);
      if (lista) lista.push(item);
      else porParametro.set(item.id_prmtr, [item]);
    }
    return parametrosGraficables
      .filter((p) => parametrosSeleccionados.includes(p.id_prmtr))
      .map((p) => ({ parametro: p, items: porParametro.get(p.id_prmtr) ?? [] }));
  }, [itemsOrdenados, parametrosGraficables, parametrosSeleccionados]);

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
                  Ubicación
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
                      Selecciona una ubicación…
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
                  <SelectorRangoFechasTimeline zonaHoraria={zonaHoraria} onCambiarRango={setRangoFechas} />
                </div>
              )}
            </div>

            {!ubicacionIdValida && (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
                Selecciona una ubicación para ver sus gráficos.
              </div>
            )}

            {ubicacionIdValida && (
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <div className="flex items-center gap-1 bg-black/5 dark:bg-white/5 rounded-xl p-1">
                  <button
                    type="button"
                    onClick={() => setTipoGrafico("linea")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      tipoGrafico === "linea" ? "bg-[#ccff00] text-gray-900" : "text-gray-600 dark:text-gray-300"
                    }`}
                  >
                    Línea
                  </button>
                  <button
                    type="button"
                    onClick={() => setTipoGrafico("area")}
                    className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                      tipoGrafico === "area" ? "bg-[#ccff00] text-gray-900" : "text-gray-600 dark:text-gray-300"
                    }`}
                  >
                    Área
                  </button>

                  {/* Refresco en segundo plano (auto-actualización cada
                      60s de SelectorRangoFechasTimeline, mientras siga
                      "hasta ahora"): antes esto ocultaba toda la grilla
                      de gráficos y la reemplazaba por un spinner grande,
                      lo que hacía que el documento se encogiera de golpe
                      y el navegador perdiera la posición de scroll -acá
                      solo se avisa sin tapar nada de lo que ya está
                      dibujado-. */}
                  {loading && !cargandoPrimeraVez && (
                    <span className="flex items-center gap-1.5 pl-3 text-xs text-gray-500 dark:text-gray-400">
                      <span className="w-1.5 h-1.5 rounded-full bg-[#ccff00] animate-pulse" />
                      Actualizando…
                    </span>
                  )}
                </div>

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
            {!cargandoPrimeraVez && respuestaTruncada && (
              <div className="mb-6 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-300/50 dark:border-amber-800/40 text-amber-800 dark:text-amber-300 text-sm">
                Mostrando {mediciones?.items.length ?? 0} de {mediciones?.total ?? 0} mediciones del
                rango. Los gráficos dibujan solo esa parte: reduce el rango de fechas o la cantidad
                de parámetros seleccionados para verlas completas.
              </div>
            )}

            {error && (
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

            {!cargandoPrimeraVez && vista === "grafico" && parametrosARenderizar.length > 0 && (
              <div className={`grid ${claseColumnasGrilla(parametrosARenderizar.length)} gap-6`}>
                {parametrosARenderizar.map(({ parametro, items }) => (
                  <GraficoDeParametro
                    key={parametro.id_prmtr}
                    parametro={parametro}
                    items={items}
                    tipoGrafico={tipoGrafico}
                    zonaHoraria={zonaHoraria}
                    hover={hover?.parametroId === parametro.id_prmtr ? hover : null}
                    onHover={setHover}
                  />
                ))}
              </div>
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
          dataloggers. Sin ninguno marcado se muestran todos juntos.
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

interface GraficoDeParametroProps {
  parametro: ParametroItem;
  items: MedicionNumerica[];
  tipoGrafico: TipoGrafico;
  zonaHoraria: string;
  hover: HoverInfo | null;
  onHover: (hover: HoverInfo | null) => void;
}

function GraficoDeParametro({ parametro, items, tipoGrafico, zonaHoraria, hover, onHover }: GraficoDeParametroProps) {
  const { esOscuro } = useTheme();

  // Serie por DISPOSITIVO (no por ubicación), hasta 4 (paleta categórica
  // validada). El resto se agrupa como "Otras" en vez de generar un color
  // nuevo por índice.
  //
  // Antes se agrupaba por id_ubccn, pero una Ubicación puede tener más de
  // un Dispositivo -dos dataloggers midiendo el mismo parámetro en la
  // misma estación es un caso real ("Estacion Prueba" tiene dos-, no
  // hipotético-: agrupar por ubicación mezclaba sus lecturas en una sola
  // línea, así que un sensor con fallas (ceros intercalados) contaminaba
  // visualmente al otro que medía bien.
  const { series, otrosDispositivos } = useMemo(() => {
    const porDispositivo = new Map<number, { nombre: string; items: MedicionNumerica[] }>();
    // Cuántas ubicaciones distintas hay entre los puntos: si es una sola,
    // el nombre de la ubicación ya lo dice el título de la tarjeta del
    // gráfico (fuera de este componente) y repetirlo en cada serie sería
    // ruido; con más de una, hace falta para no perder de qué estación es
    // cada dispositivo.
    const ubicacionesDistintas = new Set(items.map((i) => i.id_ubccn)).size;
    for (const item of items) {
      const entry = porDispositivo.get(item.id_dspstv);
      if (entry) {
        entry.items.push(item);
      } else {
        const nombre =
          ubicacionesDistintas > 1
            ? `${item.ubicacion_nombre} · ${item.dispositivo_nombre}`
            : item.dispositivo_nombre;
        porDispositivo.set(item.id_dspstv, { nombre, items: [item] });
      }
    }
    const todas = [...porDispositivo.values()];
    return { series: todas.slice(0, 4), otrosDispositivos: todas.slice(4).map((s) => s.nombre) };
  }, [items]);

  const resumen = useMemo(() => {
    const valores = items.map((i) => i.vlr);
    if (valores.length === 0) return null;
    const suma = valores.reduce((acc, v) => acc + v, 0);
    return {
      min: Math.min(...valores),
      max: Math.max(...valores),
      promedio: suma / valores.length,
      cantidad: valores.length,
    };
  }, [items]);

  const unidad = items[0]?.undd ?? parametro.undd;

  // Geometría del SVG: simple, sin librerías, siguiendo specs de marca fina
  // (línea 2px, extremos redondeados, grilla recesiva).
  const ANCHO = 900;
  const ALTO = 320;
  const PAD = { top: 16, right: 16, bottom: 32, left: 48 };

  // Zoom sobre el eje X (tiempo): un rango activo restringe minT/maxT sin
  // tocar la escala del eje Y. null = rango completo original. El zoom es
  // independiente de la pantalla completa y se conserva al salir de ella.
  const [zoomT, setZoomT] = useState<{ min: number; max: number } | null>(null);
  const [seleccion, setSeleccion] = useState<{ x1: number; x2: number } | null>(null);
  const [arrastrando, setArrastrando] = useState(false);

  const [pantallaCompleta, setPantallaCompleta] = useState(false);
  const contenedorRef = useRef<HTMLDivElement>(null);
  const svgRef = useRef<SVGSVGElement>(null);

  // Posición en pantalla (no en el viewBox del SVG) del tooltip de hover,
  // recalculada vía efecto -no durante el render, que es donde React ya
  // no permite leer refs- cada vez que cambia el punto resaltado o la
  // página se desplaza/redimensiona mientras el tooltip sigue abierto.
  const [posicionTooltip, setPosicionTooltip] = useState<{ left: number; top: number } | null>(null);
  useEffect(() => {
    if (!hover) {
      setPosicionTooltip(null);
      return;
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
      window.removeEventListener("scroll", recalcular, true);
      window.removeEventListener("resize", recalcular);
    };
  }, [hover]);

  useEffect(() => {
    function onFullscreenChange() {
      setPantallaCompleta(document.fullscreenElement === contenedorRef.current);
    }
    document.addEventListener("fullscreenchange", onFullscreenChange);
    return () => document.removeEventListener("fullscreenchange", onFullscreenChange);
  }, []);

  async function alternarPantallaCompleta() {
    try {
      if (document.fullscreenElement) {
        await document.exitFullscreen();
      } else {
        await contenedorRef.current?.requestFullscreen();
      }
    } catch {
      // El navegador puede rechazar la solicitud (falta de gesto del
      // usuario, política de permisos); no hay nada más que hacer aquí.
    }
  }

  const todosLosValores = items.map((i) => i.vlr);
  const todosLosTiempos = items.map((i) => new Date(i.fch_hr).getTime());
  // El eje Y siempre refleja el rango completo de valores: el zoom es
  // exclusivo del eje X (tiempo), sin alterar esta escala.
  const minVlr = todosLosValores.length ? Math.min(...todosLosValores) : 0;
  const maxVlr = todosLosValores.length ? Math.max(...todosLosValores) : 1;
  const minTOriginal = todosLosTiempos.length ? Math.min(...todosLosTiempos) : 0;
  const maxTOriginal = todosLosTiempos.length ? Math.max(...todosLosTiempos) : 1;
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

  return (
    <div
      ref={contenedorRef}
      className={
        pantallaCompleta
          ? "bg-white dark:bg-[#0b1220] p-6 h-screen w-screen flex flex-col"
          : "bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl border border-black/10 dark:border-white/10 p-5"
      }
    >
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h2 className="text-sm font-bold text-gray-900 dark:text-white">
          {parametro.nmbr} en el tiempo
        </h2>

        <div className="flex items-center gap-4 flex-wrap">
          {series.length > 0 && (
            <div className="flex items-center gap-4 flex-wrap">
              {series.map((s, i) => (
                <div
                  key={s.nombre}
                  className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300"
                >
                  <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORES_SERIE[i] }} />
                  {s.nombre}
                </div>
              ))}
              {otrosDispositivos.length > 0 && (
                <span className="text-xs text-gray-500">+{otrosDispositivos.length} más sin graficar</span>
              )}
            </div>
          )}

          <div className="flex items-center gap-2">
            {zoomT && (
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
              onClick={alternarPantallaCompleta}
              title={pantallaCompleta ? "Salir de pantalla completa" : "Pantalla completa"}
              aria-label={pantallaCompleta ? "Salir de pantalla completa" : "Pantalla completa"}
              className="p-1.5 rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:border-[#ccff00] hover:text-[#ccff00] transition-colors"
            >
              {pantallaCompleta ? (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3v3a2 2 0 0 1-2 2H3M21 8h-3a2 2 0 0 1-2-2V3M3 16h3a2 2 0 0 1 2 2v3M16 21v-3a2 2 0 0 1 2-2h3" />
                </svg>
              ) : (
                <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <path d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M21 16v3a2 2 0 0 1-2 2h-3M8 21H5a2 2 0 0 1-2-2v-3" />
                </svg>
              )}
            </button>
          </div>
        </div>
      </div>

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-4">
        {[
          { etiqueta: "Mediciones", valor: resumen ? resumen.cantidad.toLocaleString("es") : "—" },
          { etiqueta: "Mínimo", valor: resumen ? `${resumen.min.toFixed(2)} ${unidad}` : "—" },
          { etiqueta: "Promedio", valor: resumen ? `${resumen.promedio.toFixed(2)} ${unidad}` : "—" },
          { etiqueta: "Máximo", valor: resumen ? `${resumen.max.toFixed(2)} ${unidad}` : "—" },
        ].map((tile) => (
          <div key={tile.etiqueta} className="bg-black/5 dark:bg-white/5 rounded-xl p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{tile.etiqueta}</div>
            <div className="text-lg font-bold text-gray-900 dark:text-white mt-0.5">{tile.valor}</div>
          </div>
        ))}
      </div>

      {items.length === 0 ? (
        <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
          No hay mediciones registradas para este parámetro todavía.
        </div>
      ) : (
        <div className={`relative w-full overflow-x-auto ${pantallaCompleta ? "flex-1 flex items-center" : ""}`}>
          <svg
            ref={svgRef}
            viewBox={`0 0 ${ANCHO} ${ALTO}`}
            // select-none: el arrastre para hacer zoom (iniciarSeleccion/
            // actualizarSeleccion) es un mousedown+drag sobre el SVG, y
            // sin esto el navegador lo interpreta como una selección de
            // texto normal -resalta en azul las etiquetas del eje Y y
            // muestra su menú contextual de "copiar/buscar" al soltar-.
            className="w-full h-auto min-w-[600px] cursor-crosshair select-none"
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

            {/* Grilla recesiva */}
            {Array.from({ length: lineasGrilla + 1 }).map((_, i) => {
              const y = PAD.top + (i / lineasGrilla) * (ALTO - PAD.top - PAD.bottom);
              const valor = maxVlr - (i / lineasGrilla) * rangoVlr;
              return (
                <g key={i}>
                  <line x1={PAD.left} x2={ANCHO - PAD.right} y1={y} y2={y} stroke={colorGrilla} strokeWidth={1} />
                  <text x={PAD.left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill={colorTextoEje}>
                    {valor.toFixed(decimalesEje)}
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

            {series.map((s, i) => {
              const color = COLORES_SERIE[i];
              const itemsVisibles = s.items.filter(enRangoZoom);
              const coords = itemsVisibles.map((item) => ({ x: xDe(item), y: yDe(item) }));
              const trazo = pathDeLinea(coords);
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
              const indiceHover = hover
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
                <g key={s.nombre}>
                  {tipoGrafico === "area" && areaPath && <path d={areaPath} fill={color} fillOpacity={0.18} stroke="none" />}
                  <path d={trazo} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  {/* Cada medición lleva un punto chico -guía visual de que
                      ahí hay un dato para pasar el mouse, sin saturar el
                      trazo- en el color de la serie, más un círculo invisible
                      más grande encima que amplía el área de captura del
                      hover sin agrandar lo que se ve. El punto en hover se
                      resalta aparte, más abajo (línea guía + glow). */}
                  {itemsVisibles.map((item, indice) => {
                    const puntoActivo = hover?.item.id_registro === item.id_registro;
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
                        onMouseEnter={() => onHover({ parametroId: parametro.id_prmtr, x: coords[indice].x, y: coords[indice].y, item })}
                        onMouseLeave={() =>
                          onHover(hover?.item.id_registro === item.id_registro ? null : hover)
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
                className="fixed pointer-events-none bg-white dark:bg-[#0b1220] border border-black/20 dark:border-white/20 rounded-lg px-3 py-2 text-xs text-gray-900 dark:text-white shadow-xl z-50"
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
                <div className="text-gray-500 dark:text-gray-400">{hover.item.dispositivo_nombre}</div>
                <div className="text-gray-500 dark:text-gray-400">
                  {formatearFechaCorta(hover.item.fch_hr, zonaHoraria)}
                </div>
              </div>,
              document.body,
            )}
        </div>
      )}
    </div>
  );
}
