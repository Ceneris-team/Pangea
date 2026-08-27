import { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import SelectorRangoFechasTimeline from "../components/SelectorRangoFechasTimeline";
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
 */

interface ParametroItem {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  tipo_dato: string;
}

interface MedicionItem {
  id_registro: number;
  fch_hr: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  id_prmtr: number;
  parametro_nombre: string;
  undd: string;
  vlr: number | string;
}

interface ListadoMediciones {
  total: number;
  items: MedicionItem[];
}

// Solo los registros con valor numérico son graficables (línea/área); los
// de tipo texto (evnt_txt) se filtran antes de agrupar por parámetro.
type MedicionNumerica = MedicionItem & { vlr: number };

type TipoGrafico = "linea" | "area";
type Vista = "grafico" | "tabla";

interface HoverInfo {
  parametroId: number;
  x: number;
  y: number;
  item: MedicionNumerica;
}

// Paleta categórica validada para fondo oscuro (dataviz skill): azul,
// naranja, aqua, amarillo — en ese orden fijo, nunca por índice aleatorio.
const COLORES_SERIE = ["#3987e5", "#d95926", "#199e70", "#c98500"];

// HU15/HU14: los datos se almacenan en UTC y se muestran en la zona
// horaria configurada por el usuario.
function formatearFechaCorta(iso: string, zonaHoraria: string): string {
  return new Date(iso).toLocaleString("es", {
    timeZone: zonaHoraria,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function construirQuery(parametroIds: number[], rangoFechas: RangoFechas | null): string {
  const params = new URLSearchParams();
  parametroIds.forEach((id) => params.append("parametro_ids", String(id)));
  if (rangoFechas) {
    params.append("fecha_inicio", new Date(rangoFechas.inicio).toISOString());
    params.append("fecha_fin", new Date(rangoFechas.fin).toISOString());
  }
  const query = params.toString();
  return query ? `/mediciones?${query}` : "/mediciones";
}

// CA: 1-3 parámetros seleccionados -> una columna; 4-6 -> dos columnas;
// 7-8 -> tres columnas en pantallas grandes.
function claseColumnasGrilla(cantidad: number): string {
  if (cantidad <= 3) return "grid-cols-1";
  if (cantidad <= 6) return "grid-cols-1 md:grid-cols-2";
  return "grid-cols-1 md:grid-cols-2 lg:grid-cols-3";
}

export default function Graficos() {
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();

  // HU17 CA4: ubicación preseleccionada por query param. Se lee con
  // useSearchParams (y no de window.location) para que quede sincronizada
  // con la navegación de React Router: volver atrás desde el mapa
  // restaura el filtro anterior sin recargar.
  const [searchParams, setSearchParams] = useSearchParams();
  const ubicacionIdParam = searchParams.get("ubicacion_id");
  const ubicacionId = ubicacionIdParam !== null ? Number(ubicacionIdParam) : null;
  const ubicacionIdValida = ubicacionId !== null && Number.isFinite(ubicacionId);

  const [parametros, setParametros] = useState<ParametroItem[]>([]);

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

  // HU17 CA4: nombre de la ubicación preseleccionada, para el aviso de
  // "filtrando por...". Se pide solo cuando hay filtro activo.
  useEffect(() => {
    if (!ubicacionIdValida) return;
    apiFetch<{ items: UbicacionItem[] }>("/ubicaciones", { params: { por_pagina: 100 } })
      .then((res) => setUbicaciones(res.items))
      .catch(() => setUbicaciones([]));
  }, [ubicacionIdValida]);

  useEffect(() => {
    if (parametrosSeleccionados.length === 0 || rangoFechas === null) {
      return;
    }
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoMediciones>(construirQuery(parametrosSeleccionados, rangoFechas))
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
  }, [parametrosSeleccionados, rangoFechas]);

  const toggleParametro = (id: number) => {
    setParametrosSeleccionados((actual) => (actual.includes(id) ? actual.filter((v) => v !== id) : [...actual, id]));
  };

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
              <fieldset>
                <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">Parámetros</legend>
                <div className="flex flex-wrap gap-3">
                  {parametrosGraficables.length === 0 && (
                    <span className="text-sm text-gray-500 dark:text-gray-400">No hay parámetros disponibles.</span>
                  )}
                  {parametrosGraficables.map((p) => (
                    <label key={p.id_prmtr} className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 cursor-pointer">
                      <input
                        type="checkbox"
                        checked={parametrosSeleccionados.includes(p.id_prmtr)}
                        onChange={() => toggleParametro(p.id_prmtr)}
                        className="accent-[#ccff00]"
                      />
                      {p.nmbr} ({p.undd})
                    </label>
                  ))}
                </div>
              </fieldset>

              <div className="mt-6 pt-6 border-t border-black/10 dark:border-white/10">
                <SelectorRangoFechasTimeline zonaHoraria={zonaHoraria} onCambiarRango={setRangoFechas} />
              </div>
            </div>

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
              </div>

              <button
                type="button"
                onClick={() => setVista((v) => (v === "grafico" ? "tabla" : "grafico"))}
                className="px-4 py-2 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/10 dark:hover:bg-white/10 transition-all"
              >
                {vista === "grafico" ? "VER TABLA" : "VER GRÁFICOS"}
              </button>
            </div>

            {/* HU17 CA4: aviso de que se está viendo UNA sola ubicación,
                con salida a la vista completa. Sin esto, alguien que
                llega desde el mapa podría creer que su cuenta solo tiene
                datos de esa estación. */}
            {ubicacionIdValida && (
              <div className="mb-6 p-4 rounded-xl bg-[#ccff00]/10 border border-[#ccff00]/30 text-sm flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                <span className="text-gray-700 dark:text-gray-200">
                  Mostrando solo la ubicación{" "}
                  <strong className="font-semibold">
                    {ubicaciones.find((u) => u.id_ubccn === ubicacionId)?.nmbr ??
                      `#${ubicacionId}`}
                  </strong>
                  , preseleccionada desde el mapa de estaciones.
                </span>
                <button
                  type="button"
                  onClick={() => {
                    // Se quita solo este parámetro y se conservan los
                    // demás: hoy es el único, pero borrar toda la query
                    // string sería un bug latente en cuanto se agregue otro.
                    const siguiente = new URLSearchParams(searchParams);
                    siguiente.delete("ubicacion_id");
                    setSearchParams(siguiente, { replace: true });
                  }}
                  className="shrink-0 self-start sm:self-auto inline-flex items-center px-3 py-1.5 text-xs font-medium rounded-lg border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                >
                  Ver todas las ubicaciones
                </button>
              </div>
            )}

            {error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800/30">
                {error}
              </div>
            )}

            {loading && (
              <div className="flex justify-center items-center gap-2 py-24 text-gray-600 dark:text-gray-300">
                <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce" />
                <span>Cargando telemetría...</span>
              </div>
            )}

            {!loading && parametrosSeleccionados.length === 0 && (
              <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
                Selecciona al menos un parámetro para ver sus gráficos.
              </div>
            )}

            {!loading && vista === "tabla" && itemsOrdenados.length > 0 && (
              <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Fecha</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Hora</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Parámetro</th>
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

            {!loading && vista === "grafico" && parametrosARenderizar.length > 0 && (
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
  // Serie por ubicación, hasta 4 (paleta categórica validada). El resto se
  // agrupa como "Otras" en vez de generar un color nuevo por índice.
  const { series, otrasUbicaciones } = useMemo(() => {
    const porUbicacion = new Map<number, { nombre: string; items: MedicionNumerica[] }>();
    for (const item of items) {
      const entry = porUbicacion.get(item.id_ubccn);
      if (entry) entry.items.push(item);
      else porUbicacion.set(item.id_ubccn, { nombre: item.ubicacion_nombre, items: [item] });
    }
    const todas = [...porUbicacion.values()];
    return { series: todas.slice(0, 4), otrasUbicaciones: todas.slice(4).map((s) => s.nombre) };
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

  const todosLosValores = items.map((i) => i.vlr);
  const todosLosTiempos = items.map((i) => new Date(i.fch_hr).getTime());
  const minVlr = todosLosValores.length ? Math.min(...todosLosValores) : 0;
  const maxVlr = todosLosValores.length ? Math.max(...todosLosValores) : 1;
  const minT = todosLosTiempos.length ? Math.min(...todosLosTiempos) : 0;
  const maxT = todosLosTiempos.length ? Math.max(...todosLosTiempos) : 1;
  const rangoVlr = maxVlr - minVlr || 1;
  const rangoT = maxT - minT || 1;

  function xDe(item: MedicionNumerica) {
    const t = new Date(item.fch_hr).getTime();
    return PAD.left + ((t - minT) / rangoT) * (ANCHO - PAD.left - PAD.right);
  }
  function yDe(item: MedicionNumerica) {
    return PAD.top + (1 - (item.vlr - minVlr) / rangoVlr) * (ALTO - PAD.top - PAD.bottom);
  }

  const yBase = ALTO - PAD.bottom;
  const lineasGrilla = 4;

  return (
    <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl border border-black/10 dark:border-white/10 p-5">
      <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
        <h2 className="text-sm font-bold text-gray-900 dark:text-white">
          {parametro.nmbr} en el tiempo
        </h2>

        {series.length > 0 && (
          <div className="flex items-center gap-4 flex-wrap">
            {series.map((s, i) => (
              <div key={s.nombre} className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: COLORES_SERIE[i] }} />
                {s.nombre}
              </div>
            ))}
            {otrasUbicaciones.length > 0 && (
              <span className="text-xs text-gray-500">+{otrasUbicaciones.length} más sin graficar</span>
            )}
          </div>
        )}
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
        <div className="relative w-full overflow-x-auto">
          <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="w-full h-auto min-w-[600px]">
            {/* Grilla recesiva */}
            {Array.from({ length: lineasGrilla + 1 }).map((_, i) => {
              const y = PAD.top + (i / lineasGrilla) * (ALTO - PAD.top - PAD.bottom);
              const valor = maxVlr - (i / lineasGrilla) * rangoVlr;
              return (
                <g key={i}>
                  <line x1={PAD.left} x2={ANCHO - PAD.right} y1={y} y2={y} stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
                  <text x={PAD.left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="rgba(255,255,255,0.4)">
                    {valor.toFixed(1)}
                  </text>
                </g>
              );
            })}

            {/* Eje de tiempo: primero y último timestamp */}
            <text x={PAD.left} y={ALTO - 10} fontSize={10} fill="rgba(255,255,255,0.4)">
              {formatearFechaCorta(new Date(minT).toISOString(), zonaHoraria)}
            </text>
            <text x={ANCHO - PAD.right} y={ALTO - 10} textAnchor="end" fontSize={10} fill="rgba(255,255,255,0.4)">
              {formatearFechaCorta(new Date(maxT).toISOString(), zonaHoraria)}
            </text>

            {series.map((s, i) => {
              const color = COLORES_SERIE[i];
              const puntos = s.items.map((item) => `${xDe(item)},${yDe(item)}`).join(" ");
              const areaPath =
                s.items.length > 0
                  ? `M ${xDe(s.items[0])},${yBase} ` +
                    s.items.map((item) => `L ${xDe(item)},${yDe(item)}`).join(" ") +
                    ` L ${xDe(s.items[s.items.length - 1])},${yBase} Z`
                  : "";
              return (
                <g key={s.nombre}>
                  {tipoGrafico === "area" && areaPath && <path d={areaPath} fill={color} fillOpacity={0.18} stroke="none" />}
                  <polyline points={puntos} fill="none" stroke={color} strokeWidth={2} strokeLinecap="round" strokeLinejoin="round" />
                  {s.items.map((item) => (
                    <circle
                      key={item.id_registro}
                      cx={xDe(item)}
                      cy={yDe(item)}
                      r={hover?.item.id_registro === item.id_registro ? 5 : 3}
                      fill={color}
                      stroke="#0b1220"
                      strokeWidth={1.5}
                      className="cursor-pointer"
                      onMouseEnter={() => onHover({ parametroId: parametro.id_prmtr, x: xDe(item), y: yDe(item), item })}
                      onMouseLeave={() =>
                        onHover(hover?.item.id_registro === item.id_registro ? null : hover)
                      }
                    />
                  ))}
                </g>
              );
            })}
          </svg>

          {hover && (
            <div
              className="absolute pointer-events-none bg-[#0b1220] border border-black/20 dark:border-white/20 rounded-lg px-3 py-2 text-xs text-gray-900 dark:text-white shadow-xl"
              style={{
                left: `${(hover.x / ANCHO) * 100}%`,
                top: `${(hover.y / ALTO) * 100}%`,
                transform: "translate(-50%, -120%)",
              }}
            >
              <div className="font-semibold">
                {hover.item.vlr} {hover.item.undd}
              </div>
              <div className="text-gray-500 dark:text-gray-400">{hover.item.ubicacion_nombre}</div>
              <div className="text-gray-500 dark:text-gray-400">{formatearFechaCorta(hover.item.fch_hr, zonaHoraria)}</div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
