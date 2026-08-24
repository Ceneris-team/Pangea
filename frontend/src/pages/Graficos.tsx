import { useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * Vista rápida de telemetría en gráficos. Reutiliza los mismos endpoints
 * que Consulta de Datos (HU13: /mediciones y /mediciones/parametros), pero
 * en vez de una tabla muestra una serie de tiempo simple por ubicación
 * para el parámetro elegido, más un resumen (mín/prom/máx).
 */

interface ParametroItem {
  id_prmtr: number;
  nmbr: string;
  undd: string;
}

interface MedicionItem {
  id_lctr: number;
  fch_hr: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  parametro_nombre: string;
  undd: string;
  vlr: number;
}

interface ListadoMediciones {
  total: number;
  items: MedicionItem[];
}

// Paleta categórica validada para fondo oscuro (dataviz skill): azul,
// naranja, aqua, amarillo — en ese orden fijo, nunca por índice aleatorio.
const COLORES_SERIE = ["#3987e5", "#d95926", "#199e70", "#c98500"];

function formatearFechaCorta(iso: string): string {
  return new Date(iso).toLocaleString("es", { day: "2-digit", month: "short", hour: "2-digit", minute: "2-digit" });
}

export default function Graficos() {
  const { nombreCompleto, rol, logout } = useAuth();

  const [parametros, setParametros] = useState<ParametroItem[]>([]);
  const [parametroId, setParametroId] = useState<number | null>(null);

  const [mediciones, setMediciones] = useState<ListadoMediciones | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [hover, setHover] = useState<{ x: number; y: number; item: MedicionItem } | null>(null);

  useEffect(() => {
    apiFetch<{ items: ParametroItem[] }>("/mediciones/parametros")
      .then((res) => {
        setParametros(res.items);
        if (res.items.length > 0) setParametroId(res.items[0].id_prmtr);
      })
      .catch(() => setParametros([]));
  }, []);

  useEffect(() => {
    if (parametroId === null) return;
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<ListadoMediciones>(`/mediciones?parametro_ids=${parametroId}&por_pagina=200`)
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
  }, [parametroId]);

  // El backend devuelve más reciente primero; para la línea de tiempo se
  // necesita orden cronológico ascendente.
  const itemsOrdenados = useMemo(() => {
    return [...(mediciones?.items ?? [])].sort(
      (a, b) => new Date(a.fch_hr).getTime() - new Date(b.fch_hr).getTime()
    );
  }, [mediciones]);

  // Serie por ubicación, hasta 4 (paleta categórica validada). El resto se
  // agrupa como "Otras" en vez de generar un color nuevo por índice.
  const { series, otrasUbicaciones } = useMemo(() => {
    const porUbicacion = new Map<number, { nombre: string; items: MedicionItem[] }>();
    for (const item of itemsOrdenados) {
      const entry = porUbicacion.get(item.id_ubccn);
      if (entry) entry.items.push(item);
      else porUbicacion.set(item.id_ubccn, { nombre: item.ubicacion_nombre, items: [item] });
    }
    const todas = [...porUbicacion.values()];
    return { series: todas.slice(0, 4), otrasUbicaciones: todas.slice(4).map((s) => s.nombre) };
  }, [itemsOrdenados]);

  const resumen = useMemo(() => {
    const valores = itemsOrdenados.map((i) => i.vlr);
    if (valores.length === 0) return null;
    const suma = valores.reduce((acc, v) => acc + v, 0);
    return {
      min: Math.min(...valores),
      max: Math.max(...valores),
      promedio: suma / valores.length,
      cantidad: valores.length,
    };
  }, [itemsOrdenados]);

  const unidad = itemsOrdenados[0]?.undd ?? "";
  const parametroActual = parametros.find((p) => p.id_prmtr === parametroId);

  // Geometría del SVG: simple, sin librerías, siguiendo specs de marca fina
  // (línea 2px, extremos redondeados, grilla recesiva).
  const ANCHO = 900;
  const ALTO = 320;
  const PAD = { top: 16, right: 16, bottom: 32, left: 48 };

  const todosLosValores = itemsOrdenados.map((i) => i.vlr);
  const todosLosTiempos = itemsOrdenados.map((i) => new Date(i.fch_hr).getTime());
  const minVlr = todosLosValores.length ? Math.min(...todosLosValores) : 0;
  const maxVlr = todosLosValores.length ? Math.max(...todosLosValores) : 1;
  const minT = todosLosTiempos.length ? Math.min(...todosLosTiempos) : 0;
  const maxT = todosLosTiempos.length ? Math.max(...todosLosTiempos) : 1;
  const rangoVlr = maxVlr - minVlr || 1;
  const rangoT = maxT - minT || 1;

  function xDe(item: MedicionItem) {
    const t = new Date(item.fch_hr).getTime();
    return PAD.left + ((t - minT) / rangoT) * (ANCHO - PAD.left - PAD.right);
  }
  function yDe(item: MedicionItem) {
    return PAD.top + (1 - (item.vlr - minVlr) / rangoVlr) * (ALTO - PAD.top - PAD.bottom);
  }

  const lineasGrilla = 4;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="graficos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Gráficos</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Vista rápida de telemetría por parámetro, agrupada por ubicación.
                </p>
              </div>

              <select
                value={parametroId ?? ""}
                onChange={(e) => setParametroId(e.target.value ? Number(e.target.value) : null)}
                className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md border border-black/20 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] p-2.5 outline-none min-w-[220px]"
              >
                {parametros.length === 0 && <option value="">Sin parámetros disponibles</option>}
                {parametros.map((p) => (
                  <option key={p.id_prmtr} value={p.id_prmtr} className="bg-[#0b1220]">
                    {p.nmbr} ({p.undd})
                  </option>
                ))}
              </select>
            </header>

            {error && (
              <div className="mb-6 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border border-red-200 dark:border-red-800/30">
                {error}
              </div>
            )}

            {/* Tarjetas resumen: la lectura más rápida antes de mirar la línea */}
            <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-6">
              {[
                { etiqueta: "Mediciones", valor: resumen ? resumen.cantidad.toLocaleString("es") : "—" },
                { etiqueta: "Mínimo", valor: resumen ? `${resumen.min.toFixed(2)} ${unidad}` : "—" },
                { etiqueta: "Promedio", valor: resumen ? `${resumen.promedio.toFixed(2)} ${unidad}` : "—" },
                { etiqueta: "Máximo", valor: resumen ? `${resumen.max.toFixed(2)} ${unidad}` : "—" },
              ].map((tile) => (
                <div
                  key={tile.etiqueta}
                  className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl border border-black/10 dark:border-white/10 p-4"
                >
                  <div className="text-xs font-bold uppercase tracking-wider text-gray-500 dark:text-gray-400">{tile.etiqueta}</div>
                  <div className="text-2xl font-bold text-gray-900 dark:text-white mt-1">{tile.valor}</div>
                </div>
              ))}
            </div>

            <div className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl border border-black/10 dark:border-white/10 p-5">
              <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
                <h2 className="text-sm font-bold text-gray-900 dark:text-white">
                  {parametroActual ? `${parametroActual.nmbr} en el tiempo` : "Selecciona un parámetro"}
                </h2>

                {series.length > 0 && (
                  <div className="flex items-center gap-4 flex-wrap">
                    {series.map((s, i) => (
                      <div key={s.nombre} className="flex items-center gap-1.5 text-xs text-gray-600 dark:text-gray-300">
                        <span
                          className="w-2.5 h-2.5 rounded-full"
                          style={{ backgroundColor: COLORES_SERIE[i] }}
                        />
                        {s.nombre}
                      </div>
                    ))}
                    {otrasUbicaciones.length > 0 && (
                      <span className="text-xs text-gray-500">+{otrasUbicaciones.length} más sin graficar</span>
                    )}
                  </div>
                )}
              </div>

              {loading && (
                <div className="flex justify-center items-center gap-2 py-24 text-gray-600 dark:text-gray-300">
                  <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce" />
                  <span>Cargando telemetría...</span>
                </div>
              )}

              {!loading && itemsOrdenados.length === 0 && (
                <div className="py-24 text-center text-gray-500 dark:text-gray-400 text-sm">
                  No hay mediciones registradas para este parámetro todavía.
                </div>
              )}

              {!loading && itemsOrdenados.length > 0 && (
                <div className="relative w-full overflow-x-auto">
                  <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} className="w-full h-auto min-w-[600px]">
                    {/* Grilla recesiva */}
                    {Array.from({ length: lineasGrilla + 1 }).map((_, i) => {
                      const y = PAD.top + (i / lineasGrilla) * (ALTO - PAD.top - PAD.bottom);
                      const valor = maxVlr - (i / lineasGrilla) * rangoVlr;
                      return (
                        <g key={i}>
                          <line
                            x1={PAD.left}
                            x2={ANCHO - PAD.right}
                            y1={y}
                            y2={y}
                            stroke="rgba(255,255,255,0.08)"
                            strokeWidth={1}
                          />
                          <text x={PAD.left - 8} y={y} textAnchor="end" dominantBaseline="middle" fontSize={10} fill="rgba(255,255,255,0.4)">
                            {valor.toFixed(1)}
                          </text>
                        </g>
                      );
                    })}

                    {/* Eje de tiempo: primero y último timestamp */}
                    <text x={PAD.left} y={ALTO - 10} fontSize={10} fill="rgba(255,255,255,0.4)">
                      {formatearFechaCorta(new Date(minT).toISOString())}
                    </text>
                    <text x={ANCHO - PAD.right} y={ALTO - 10} textAnchor="end" fontSize={10} fill="rgba(255,255,255,0.4)">
                      {formatearFechaCorta(new Date(maxT).toISOString())}
                    </text>

                    {series.map((s, i) => {
                      const color = COLORES_SERIE[i];
                      const puntos = s.items.map((item) => `${xDe(item)},${yDe(item)}`).join(" ");
                      return (
                        <g key={s.nombre}>
                          <polyline
                            points={puntos}
                            fill="none"
                            stroke={color}
                            strokeWidth={2}
                            strokeLinecap="round"
                            strokeLinejoin="round"
                          />
                          {s.items.map((item) => (
                            <circle
                              key={item.id_lctr}
                              cx={xDe(item)}
                              cy={yDe(item)}
                              r={hover?.item.id_lctr === item.id_lctr ? 5 : 3}
                              fill={color}
                              stroke="#0b1220"
                              strokeWidth={1.5}
                              className="cursor-pointer"
                              onMouseEnter={() => setHover({ x: xDe(item), y: yDe(item), item })}
                              onMouseLeave={() => setHover((h) => (h?.item.id_lctr === item.id_lctr ? null : h))}
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
                        {hover.item.vlr.toFixed(2)} {hover.item.undd}
                      </div>
                      <div className="text-gray-500 dark:text-gray-400">{hover.item.ubicacion_nombre}</div>
                      <div className="text-gray-500 dark:text-gray-400">{formatearFechaCorta(hover.item.fch_hr)}</div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
