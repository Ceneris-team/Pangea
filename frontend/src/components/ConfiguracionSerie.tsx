import { VISTAS_SERIE, NOMBRES_VISTA, type ConfigSerie, type Significado, type VistaSerie } from "./configuracionSerieUtils";

export default function ConfiguracionSerie({ valor, onChange, disabled, clase }: {
  valor: ConfigSerie; onChange: (valor: ConfigSerie) => void; disabled: boolean; clase: string;
}) {
  return <div className="min-w-0 space-y-2">
    <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <label className="text-xs">Significado
        <select aria-label="Significado del dato" disabled={disabled} className={clase} value={valor.significado}
          onChange={e => { const significado = e.target.value as Significado; onChange({ ...valor, significado, vista: VISTAS_SERIE[significado][0], reinicio: "desconocido", modulo: null, confirmada: significado !== "desconocido" }); }}>
          <option value="desconocido">Pendiente de identificar</option>
          <option value="continuo">Medición continua</option>
          <option value="contador">Contador de eventos</option>
          <option value="secuencia">Consecutivo de tramas</option>
          <option value="estado">Estado: 0 inactivo / 1 activo</option>
        </select>
      </label>
      <label className="text-xs">Vista inicial
        <select aria-label="Vista inicial" disabled={disabled} className={clase} value={valor.vista}
          onChange={e => onChange({ ...valor, vista: e.target.value as VistaSerie })}>
          {VISTAS_SERIE[valor.significado].map(v => <option key={v} value={v}>{NOMBRES_VISTA[v]}</option>)}
        </select>
      </label>
    </div>
    {(valor.significado === "contador" || valor.significado === "secuencia") && <div className="grid grid-cols-1 sm:grid-cols-2 gap-2">
      <label className="text-xs">Cuando disminuye
        <select aria-label="Regla de reinicio" disabled={disabled} className={clase} value={valor.reinicio}
          onChange={e => onChange({ ...valor, reinicio: e.target.value as ConfigSerie["reinicio"] })}>
          <option value="desconocido">Marcar conteo parcial</option>
          <option value="cero">Reinicio confirmado desde cero</option>
          <option value="modulo">Vuelta del contador (módulo)</option>
        </select>
      </label>
      {valor.reinicio === "modulo" && <label className="text-xs">Módulo
        <input aria-label="Módulo del contador" type="number" min={2} step={1} required disabled={disabled}
          className={clase} value={valor.modulo ?? ""} placeholder="65536"
          onChange={e => onChange({ ...valor, modulo: e.target.value ? Number(e.target.value) : null })} />
      </label>}
    </div>}
    {!valor.confirmada && <label className="flex gap-2 items-center text-xs text-amber-700 dark:text-amber-300">
      <input type="checkbox" disabled={disabled || valor.significado === "desconocido"} checked={false}
        onChange={() => onChange({ ...valor, confirmada: true })} />
      {valor.significado === "desconocido" ? "El encabezado no permite identificar el dato. Selecciona su significado." : "Sugerencia del encabezado. Confirmar significado."}
    </label>}
  </div>;
}
