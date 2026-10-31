import { useEffect, useMemo, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import { pathDeLinea } from "../pages/graficosUtils";
import { colorDatalogger, type DatosSerie, type FuenteSerie, type SerieTelemetria } from "../pages/seriesTelemetria";

export interface WidgetConfigurado {
  id_wdgt: number;
  tp: "linea" | "area" | "tarjeta" | "tabla";
  id_prmtr: number;
  id_ubccn: number;
  pscn: number;
  ancho: 1 | 2;
  parametro_nombre: string;
  undd: string;
}

interface Props {
  widget: WidgetConfigurado;
  ubicacionNombre: string;
  ultimoValor?: { valor: number | string; fch_hr: string | null; dispositivo_nombre: string };
  dias: number;
  fechaInicio?: string;
  fechaFin?: string;
  idDispositivo?: number | null;
  revision: number;
  zonaHoraria: string;
}

const ANCHO = 640;
const ALTO = 210;
const MARGEN = 20;

export default function WidgetTelemetria({ widget, ubicacionNombre, ultimoValor, dias, fechaInicio, fechaFin, idDispositivo, revision, zonaHoraria }: Props) {
  const [consulta, setConsulta] = useState<{ fuentes: FuenteSerie[]; error: string | null } | null>(null);

  useEffect(() => {
    if (widget.tp === "tarjeta") return;
    const controlador = new AbortController();
    const fin = fechaFin ? new Date(fechaFin) : new Date();
    const inicio = fechaInicio ? new Date(fechaInicio) : new Date(fin.getTime() - dias * 24 * 60 * 60 * 1000);

    async function cargar() {
      try {
        const catalogo = await apiFetch<{ items: SerieTelemetria[] }>(
          `/mediciones/series?ubicacion_id=${widget.id_ubccn}`,
          { signal: controlador.signal },
        );
        const series = catalogo.items.filter((serie) => serie.id_prmtr === widget.id_prmtr && (idDispositivo == null || serie.id_dspstv === idDispositivo));
        if (series.length === 0) {
          if (!controlador.signal.aborted) setConsulta({ fuentes: [], error: null });
          return;
        }
        const respuestas = await Promise.allSettled(series.map(async (serie) => {
          const params = new URLSearchParams({
            fecha_inicio: inicio.toISOString(),
            fecha_fin: fin.toISOString(),
            zona_horaria: zonaHoraria,
            max_puntos: "300",
          });
          const datos = await apiFetch<DatosSerie>(`/mediciones/series/${serie.id_serie}?${params}`, {
            signal: controlador.signal,
          });
          return { serie, datos };
        }));
        if (controlador.signal.aborted) return;
        const fuentes = respuestas
          .filter((respuesta): respuesta is PromiseFulfilledResult<FuenteSerie> => respuesta.status === "fulfilled")
          .map((respuesta) => respuesta.value);
        const fallo = respuestas.find((respuesta) => respuesta.status === "rejected");
        const error = fallo?.status === "rejected"
          ? fallo.reason instanceof ApiError ? fallo.reason.message : "No se pudieron cargar algunas series"
          : null;
        setConsulta({ fuentes, error });
      } catch (err) {
        if (!controlador.signal.aborted) {
          setConsulta({ fuentes: [], error: err instanceof ApiError ? err.message : "No se pudo cargar el widget" });
        }
      }
    }

    void cargar();
    return () => controlador.abort();
  }, [widget.id_prmtr, widget.id_ubccn, widget.tp, dias, fechaInicio, fechaFin, idDispositivo, revision, zonaHoraria]);

  const titulo = widget.parametro_nombre;
  const unidad = widget.undd;
  const puntos = useMemo(() => consulta?.fuentes.flatMap(({ datos }) => datos.items) ?? [], [consulta]);
  const tiempos = puntos.map((p) => Date.parse(p.fch_hr));
  const valores = puntos.map((p) => Number(p.vlr));
  const minTiempo = tiempos.length ? tiempos.reduce((a, b) => Math.min(a, b)) : 0;
  const maxTiempo = tiempos.length ? tiempos.reduce((a, b) => Math.max(a, b)) : 1;
  const minValor = valores.length ? valores.reduce((a, b) => Math.min(a, b)) : 0;
  const maxValor = valores.length ? valores.reduce((a, b) => Math.max(a, b)) : 1;
  const rangoTiempo = Math.max(maxTiempo - minTiempo, 1);
  const rangoValor = Math.max(maxValor - minValor, 1);
  const coord = (fecha: string, valor: number) => ({
    x: MARGEN + ((Date.parse(fecha) - minTiempo) / rangoTiempo) * (ANCHO - 2 * MARGEN),
    y: ALTO - MARGEN - ((valor - minValor) / rangoValor) * (ALTO - 2 * MARGEN),
  });

  return (
    <div>
      <p className="mb-1 text-sm font-semibold text-gray-900 dark:text-white">{titulo}</p>
      <p className="mb-4 text-xs text-gray-600 dark:text-gray-300">{ubicacionNombre}</p>
      {widget.tp !== "tarjeta" && !consulta && <p className="text-sm text-gray-500">Cargando telemetría...</p>}
      {widget.tp !== "tarjeta" && consulta?.error && <p role="alert" className="mb-3 text-sm text-red-600 dark:text-red-400">{consulta.error}</p>}
      {widget.tp !== "tarjeta" && consulta && !puntos.length && <p className="py-8 text-center text-sm text-gray-500">Sin datos para este parámetro en el período seleccionado.</p>}
      {widget.tp === "tarjeta" && !ultimoValor && <p className="py-8 text-center text-sm text-gray-500">Sin lecturas disponibles para este parámetro.</p>}
      {widget.tp === "tarjeta" && ultimoValor && (
        <div className="py-4">
          <p className="text-4xl font-bold text-gray-900 dark:text-white">
            {Number(ultimoValor.valor).toLocaleString("es-PE", { maximumFractionDigits: 3 })}
            <span className="ml-2 text-lg font-normal text-gray-600 dark:text-gray-300">{unidad}</span>
          </p>
          <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
            Última lectura: {ultimoValor.fch_hr ? new Date(ultimoValor.fch_hr).toLocaleString("es-PE", { timeZone: zonaHoraria }) : "Fecha desconocida"} · {ultimoValor.dispositivo_nombre}
          </p>
        </div>
      )}
      {consulta && puntos.length > 0 && widget.tp === "tabla" && <><p className="mb-2 text-xs text-gray-500 dark:text-gray-400">Muestra de hasta 20 lecturas del período seleccionado</p><div className="max-h-80 overflow-auto rounded-xl border border-black/10 dark:border-white/10">
        <table className="w-full text-left text-sm"><thead className="sticky top-0 bg-white text-xs text-gray-500 dark:bg-[#1e293b] dark:text-gray-300"><tr><th className="px-3 py-2">Fecha</th><th className="px-3 py-2">Dispositivo</th><th className="px-3 py-2 text-right">Valor</th></tr></thead><tbody>{[...puntos].sort((a, b) => Date.parse(b.fch_hr) - Date.parse(a.fch_hr)).slice(0, 20).map((p, indice) => <tr key={`${p.id_dspstv}-${p.fch_hr}-${indice}`} className="border-t border-black/5 dark:border-white/10"><td className="px-3 py-2 text-gray-600 dark:text-gray-300">{new Date(p.fch_hr).toLocaleString("es-PE", { timeZone: zonaHoraria })}</td><td className="px-3 py-2 text-gray-600 dark:text-gray-300">{p.dispositivo_nombre}</td><td className="px-3 py-2 text-right font-semibold text-gray-900 dark:text-white">{Number(p.vlr).toLocaleString("es-PE", { maximumFractionDigits: 3 })} {unidad}</td></tr>)}</tbody></table>
      </div></>}
      {consulta && puntos.length > 0 && (widget.tp === "linea" || widget.tp === "area") && (
        <>
          <svg viewBox={`0 0 ${ANCHO} ${ALTO}`} role="img" aria-label={`Gráfico de ${titulo} en ${ubicacionNombre}`} className="w-full rounded-lg bg-black/[0.03] dark:bg-white/[0.03]">
            <line x1={MARGEN} x2={ANCHO - MARGEN} y1={ALTO - MARGEN} y2={ALTO - MARGEN} stroke="currentColor" opacity="0.25" />
            {consulta.fuentes.map(({ serie, datos }) => {
              const coords = datos.items.map((item) => coord(item.fch_hr, Number(item.vlr)));
              const trazo = pathDeLinea(coords);
              const color = colorDatalogger(serie.id_dspstv);
              return (
                <g key={serie.id_serie}>
                  {widget.tp === "area" && coords.length > 1 && (
                    <path d={`${trazo} L ${coords[coords.length - 1].x} ${ALTO - MARGEN} L ${coords[0].x} ${ALTO - MARGEN} Z`} fill={color} opacity="0.16" />
                  )}
                  <path d={trazo} fill="none" stroke={color} strokeWidth="2.5" strokeLinejoin="round" />
                  {coords.length === 1 && <circle cx={coords[0].x} cy={coords[0].y} r="4" fill={color} />}
                </g>
              );
            })}
          </svg>
          <div className="mt-2 flex flex-wrap justify-between gap-2 text-xs text-gray-500 dark:text-gray-400">
            <span>{minValor.toLocaleString("es-PE")} – {maxValor.toLocaleString("es-PE")} {unidad}</span>
            <span>{new Date(minTiempo).toLocaleString("es-PE", { timeZone: zonaHoraria })} – {new Date(maxTiempo).toLocaleString("es-PE", { timeZone: zonaHoraria })}</span>
          </div>
          <div className="mt-2 flex flex-wrap gap-3 text-xs text-gray-600 dark:text-gray-300">
            {consulta.fuentes.map(({ serie }) => <span key={serie.id_serie} className="inline-flex items-center gap-1"><span className="inline-block h-0.5 w-4" style={{ backgroundColor: colorDatalogger(serie.id_dspstv) }} />{serie.dispositivo_nombre}</span>)}
          </div>
        </>
      )}
    </div>
  );
}
