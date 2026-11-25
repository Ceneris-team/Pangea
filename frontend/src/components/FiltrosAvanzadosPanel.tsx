import type { CondicionBorrador, ParametroFiltro } from "../services/filtrosAvanzados";

interface Props {
  parametros: ParametroFiltro[];
  disponibles: ParametroFiltro[];
  condiciones: CondicionBorrador[];
  onCambiar: (condiciones: CondicionBorrador[]) => void;
  onLimpiar: () => void;
  hayAplicadas: boolean;
}

const campo = "w-full min-w-0 rounded-xl border border-black/20 dark:border-white/20 bg-white dark:bg-gray-900 px-3 py-2 text-sm text-gray-900 dark:text-white";

export default function FiltrosAvanzadosPanel({ parametros, disponibles, condiciones, onCambiar, onLimpiar, hayAplicadas }: Props) {
  const opciones = disponibles.filter(p => !condiciones.some(c => c.parametro_id === p.id_prmtr));
  function editar(id: number, cambios: Partial<CondicionBorrador>) {
    onCambiar(condiciones.map(c => c.parametro_id === id ? { ...c, ...cambios } : c));
  }
  return <fieldset className="min-w-0 mt-5 space-y-3">
    <legend className="text-sm font-bold text-gray-700 dark:text-gray-200">Filtros avanzados</legend>
    <p className="text-sm text-gray-600 dark:text-gray-300">Define límites por parámetro, en su propia unidad. Se conservan todas las lecturas que cumplan las condiciones.</p>
    <label className="block space-y-1 text-sm text-gray-700 dark:text-gray-200">
      <span>Añadir condición por parámetro</span>
      <select className={campo} value="" disabled={!opciones.length || condiciones.length >= 100} onChange={e => {
        if (e.target.value) onCambiar([...condiciones, { parametro_id: Number(e.target.value), minimo: "", maximo: "", modo: "dentro" }]);
      }}>
        <option value="">Selecciona un parámetro</option>
        {opciones.map(p => <option key={p.id_prmtr} value={p.id_prmtr}>{p.nmbr}{p.undd ? ` (${p.undd})` : ""}</option>)}
      </select>
    </label>
    {!disponibles.length && <p className="text-sm text-gray-600 dark:text-gray-300">No hay parámetros disponibles para filtrar por valor en esta selección. Los datos de texto y estados binarios se consultan sin límites numéricos.</p>}
    {condiciones.map(c => {
      const p = parametros.find(p => p.id_prmtr === c.parametro_id);
      const nombre = `${p?.nmbr ?? "Parámetro"}${p?.undd ? ` (${p.undd})` : ""}`;
      return <fieldset key={c.parametro_id} className="min-w-0 space-y-3 rounded-xl border border-black/15 p-3 dark:border-white/20" aria-label={`Condición de ${nombre}`}>
        <legend className="px-1 text-sm font-semibold text-gray-900 dark:text-white">{nombre}</legend>
        {!disponibles.some(p => p.id_prmtr === c.parametro_id) && <p className="text-sm text-amber-700 dark:text-amber-300">Esta condición no corresponde a la selección actual. Quítala o revisa los proyectos, equipos y parámetros.</p>}
        <label className="block text-sm text-gray-700 dark:text-gray-200">Mostrar lecturas
          <select className={`${campo} mt-1`} value={c.modo} onChange={e => editar(c.parametro_id, { modo: e.target.value as CondicionBorrador["modo"] })}>
            <option value="dentro">Dentro del rango</option><option value="fuera">Fuera del rango</option>
          </select>
        </label>
        <div className="grid min-w-0 grid-cols-1 gap-3 sm:grid-cols-2">
          <label className="block min-w-0 text-sm text-gray-700 dark:text-gray-200">Valor mínimo
            <input type="text" inputMode="decimal" maxLength={60} className={`${campo} mt-1`} value={c.minimo} onChange={e => editar(c.parametro_id, { minimo: e.target.value })} />
          </label>
          <label className="block min-w-0 text-sm text-gray-700 dark:text-gray-200">Valor máximo
            <input type="text" inputMode="decimal" maxLength={60} className={`${campo} mt-1`} value={c.maximo} onChange={e => editar(c.parametro_id, { maximo: e.target.value })} />
          </label>
        </div>
        <p className="text-xs text-gray-600 dark:text-gray-400">Puedes dejar un extremo vacío. Dentro del rango incluye los límites; fuera del rango los excluye.</p>
        <button type="button" className="text-sm text-red-700 underline dark:text-red-300" onClick={() => onCambiar(condiciones.filter(f => f.parametro_id !== c.parametro_id))}>Quitar condición de {p?.nmbr ?? "parámetro"}</button>
      </fieldset>;
    })}
    <button type="button" onClick={onLimpiar} disabled={!condiciones.length && !hayAplicadas} className="rounded-xl border border-gray-400 px-3 py-2 text-sm text-gray-700 disabled:opacity-40 dark:text-gray-200">Limpiar filtros avanzados</button>
    <p className="text-xs text-gray-600 dark:text-gray-400">Limpiar estas condiciones conserva las fechas y los proyectos, equipos y parámetros aplicados.</p>
  </fieldset>;
}
