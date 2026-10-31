import { colorDatalogger, nombreFuente, type FuenteSerie } from "../pages/seriesTelemetria";
import { formatearFechaCorta } from "../pages/graficosUtils";

export default function KpisAmpliados({ fuentes, etiqueta, zonaHoraria, onEvolucion }: {
  fuentes: FuenteSerie[]; etiqueta: string; zonaHoraria: string; onEvolucion: (id: number) => void;
}) {
  const numero = (valor: number | null) => valor === null ? "—" : new Intl.NumberFormat("es", { maximumFractionDigits: 6 }).format(valor);
  return <div className={`w-full max-w-7xl mx-auto my-auto grid grid-cols-1 ${fuentes.length > 1 ? "md:grid-cols-2" : ""} ${fuentes.length > 4 ? "xl:grid-cols-3" : ""} gap-x-12 gap-y-10 py-6 md:py-10`}>
    {fuentes.map(({ serie, datos }) => <article key={serie.id_serie} aria-label={`Indicador de ${nombreFuente(serie)}`}
      className="min-w-0 pl-6 border-l-2" style={{ borderColor: colorDatalogger(serie.id_dspstv) }}>
      <h3 className="text-base md:text-lg font-semibold text-gray-900 dark:text-white">{serie.dispositivo_nombre}</h3>
      <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Trama {serie.tp_trm} · {etiqueta}</p>
      <p className="my-5 text-5xl md:text-7xl font-semibold tracking-tight tabular-nums break-words text-gray-900 dark:text-white" aria-live="polite">
        {numero(datos.resumen.valor)}
        {serie.configuracion.significado === "continuo" && !["-", "N/A", ""].includes(serie.undd) && <span className="ml-2 text-xl tracking-normal">{serie.undd}</span>}
      </p>
      {datos.resumen.lecturas === 0 && <p className="text-sm text-gray-500">Sin datos en el período</p>}
      {datos.resumen.parcial && <p className="text-sm text-amber-700 dark:text-amber-300">Conteo parcial</p>}
      {!serie.configuracion.confirmada && <p className="text-sm text-amber-700 dark:text-amber-300">Clasificación pendiente de confirmar</p>}
      {datos.resumen.sin_origen && <p className="text-sm text-amber-700 dark:text-amber-300">Lecturas sin formato excluidas</p>}
      <dl className="space-y-2 text-sm text-gray-600 dark:text-gray-300">
        {["contador", "secuencia"].includes(serie.configuracion.significado) && <div className="flex flex-wrap gap-x-3">
          <dt>{serie.configuracion.significado === "secuencia" ? "Último consecutivo" : "Acumulado actual"}</dt><dd className="font-medium tabular-nums">{numero(datos.resumen.ultimo)}</dd>
        </div>}
        <div className="flex flex-wrap gap-x-3"><dt>Lecturas únicas</dt><dd className="tabular-nums">{numero(datos.resumen.lecturas)}</dd></div>
        <div className="flex flex-wrap gap-x-3"><dt>Última lectura</dt><dd>{datos.resumen.ultima_lectura ? formatearFechaCorta(datos.resumen.ultima_lectura, zonaHoraria) : "—"}</dd></div>
      </dl>
      <button type="button" onClick={() => onEvolucion(serie.id_serie)} aria-label={`Ver evolución de ${nombreFuente(serie)}`}
        className="mt-6 text-sm font-semibold text-gray-800 dark:text-gray-100 underline underline-offset-4">Ver evolución</button>
    </article>)}
  </div>;
}
