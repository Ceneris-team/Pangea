import { colorDatalogger, nombreFuente, type FuenteSerie } from "../pages/seriesTelemetria";
import { formatearFechaCorta } from "../pages/graficosUtils";

/** Resúmenes por equipo, calculados por el servidor con todas las lecturas. */
export default function ComparacionDataloggers({ fuentes, zonaHoraria, etiquetaKpi, kpi, ocultas, onSolo, ampliado = false }: {
  fuentes: FuenteSerie[]; zonaHoraria: string; etiquetaKpi: string; kpi: boolean;
  ampliado?: boolean;
  ocultas: number[]; onSolo: (id: number) => void;
}) {
  const formato = new Intl.NumberFormat("es", { maximumFractionDigits: 6 });
  const numero = (n: number | null) => n === null ? "—" : formato.format(n);
  const continuo = ["continuo", "desconocido"].includes(fuentes[0].serie.configuracion.significado);
  return <div className={`mt-5 overflow-x-auto ${ampliado ? "w-full max-w-screen-2xl mx-auto" : ""}`}>
    <table className={`w-full ${ampliado ? "text-sm md:text-base" : "text-xs"} text-left text-gray-600 dark:text-gray-300`}>
      <caption className="text-left text-xs text-gray-500 dark:text-gray-400 pb-3">
        Comparación por datalogger · mismo período{fuentes[0].serie.undd && !["-", "N/A"].includes(fuentes[0].serie.undd) ? ` · ${fuentes[0].serie.undd}` : ""}
      </caption>
      <thead className="border-b border-black/10 dark:border-white/10 text-gray-500 dark:text-gray-400">
        <tr>
          <th scope="col" className="py-2 pr-4 font-medium">Datalogger</th>
          <th scope="col" className="py-2 px-3 font-medium text-right">{kpi ? etiquetaKpi : "Último valor"}</th>
          {continuo ? <>
            <th scope="col" className="py-2 px-3 font-medium text-right">Mínimo</th>
            <th scope="col" className="py-2 px-3 font-medium text-right">Promedio</th>
            <th scope="col" className="py-2 px-3 font-medium text-right">Máximo</th>
          </> : <th scope="col" className="py-2 px-3 font-medium text-right">{kpi ? "Último valor" : etiquetaKpi}</th>}
          <th scope="col" className="py-2 px-3 font-medium text-right">Lecturas</th>
          <th scope="col" className="py-2 px-3 font-medium">Última lectura</th>
          <th scope="col" className="py-2 pl-3 font-medium"><span className="sr-only">Acciones</span></th>
        </tr>
      </thead>
      <tbody>
        {fuentes.map(({ serie, datos }) => {
          const r = datos.resumen;
          return <tr key={serie.id_serie} className={`border-b border-black/5 dark:border-white/5 ${ocultas.includes(serie.id_serie) ? "opacity-50" : ""}`}>
            <th scope="row" className="py-3 pr-4 font-medium text-gray-800 dark:text-gray-100">
              <span className="inline-block w-2 h-2 rounded-full mr-2" style={{ backgroundColor: colorDatalogger(serie.id_dspstv) }} />
              {nombreFuente(serie)}
              {r.lecturas === 0 && <span className="block mt-1 text-gray-500 font-normal">Sin datos en este período</span>}
              {r.parcial && <span className="block mt-1 text-amber-700 dark:text-amber-300 font-normal">Conteo parcial</span>}
              {!serie.configuracion.confirmada && <span className="block mt-1 text-amber-700 dark:text-amber-300 font-normal">Clasificación pendiente de confirmar</span>}
              {r.sin_origen && <span className="block mt-1 font-normal">Lecturas sin formato excluidas</span>}
            </th>
            <td className={`py-3 px-3 text-right tabular-nums ${kpi ? "text-xl font-semibold text-gray-900 dark:text-white" : ""}`}>{numero(kpi ? r.valor : r.ultimo)}</td>
            {continuo ? <>
              <td className="py-3 px-3 text-right tabular-nums">{numero(r.minimo)}</td>
              <td className="py-3 px-3 text-right tabular-nums">{numero(r.promedio)}</td>
              <td className="py-3 px-3 text-right tabular-nums">{numero(r.maximo)}</td>
            </> : <td className="py-3 px-3 text-right tabular-nums">{numero(kpi ? r.ultimo : r.valor)}</td>}
            <td className="py-3 px-3 text-right tabular-nums">{r.lecturas.toLocaleString("es")}</td>
            <td className="py-3 px-3 whitespace-nowrap">{r.ultima_lectura ? formatearFechaCorta(r.ultima_lectura, zonaHoraria) : "—"}</td>
            <td className="py-3 pl-3 text-right"><button type="button" onClick={() => onSolo(serie.id_serie)} aria-label={`Ver solo ${nombreFuente(serie)}`} className="font-semibold underline underline-offset-4 whitespace-nowrap">Solo este</button></td>
          </tr>;
        })}
      </tbody>
    </table>
  </div>;
}
