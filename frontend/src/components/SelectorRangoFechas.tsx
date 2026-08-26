import { useState } from "react";
import { aValorDatetimeLocal, type RangoFechas } from "../utils/fechas";

/**
 * HU12: selector de rango de fechas (con hora HH:mm) para el módulo de
 * consulta de datos. Mantiene su propia selección en curso (seleccion vs.
 * filtro aplicado), igual que los selectores de parámetros/ubicaciones, y
 * se aplica/limpia con sus propios botones "APLICAR" y "LIMPIAR FILTRO":
 * es independiente de "LIMPIAR FILTROS" (HU13/DEC-11), que solo controla
 * parámetros y ubicaciones.
 */

interface SelectorRangoFechasProps {
  seleccion: RangoFechas;
  onCambiarSeleccion: (rango: RangoFechas) => void;
  onAplicar: (rango: RangoFechas) => void;
  onLimpiar: () => void;
}

export default function SelectorRangoFechas({
  seleccion,
  onCambiarSeleccion,
  onAplicar,
  onLimpiar,
}: SelectorRangoFechasProps) {
  const [error, setError] = useState<string | null>(null);

  // CA: no se permiten fechas futuras (límite del propio input, además de
  // la validación explícita al aplicar).
  const maxDatetime = aValorDatetimeLocal(new Date());

  const handleAplicar = () => {
    if (!seleccion.inicio || !seleccion.fin) {
      setError("Selecciona fecha de inicio y fecha de fin.");
      return;
    }
    const inicio = new Date(seleccion.inicio);
    const fin = new Date(seleccion.fin);
    const ahora = new Date();

    if (inicio > fin) {
      setError("La fecha de inicio no puede ser posterior a la fecha de fin.");
      return;
    }
    if (inicio > ahora || fin > ahora) {
      setError("No se permiten fechas futuras.");
      return;
    }

    setError(null);
    onAplicar(seleccion);
  };

  const handleLimpiar = () => {
    setError(null);
    onLimpiar();
  };

  return (
    <fieldset className="flex-1">
      <legend className="text-sm font-bold text-gray-700 dark:text-gray-200 mb-2">
        Rango de fechas
      </legend>
      <div className="flex flex-col sm:flex-row gap-3">
        <label className="flex flex-col gap-1 text-sm text-gray-700 dark:text-gray-200">
          Fecha inicio
          <input
            type="datetime-local"
            value={seleccion.inicio}
            max={maxDatetime}
            onChange={(e) => onCambiarSeleccion({ ...seleccion, inicio: e.target.value })}
            className="rounded-lg border border-black/20 dark:border-white/20 bg-transparent px-3 py-1.5 text-sm text-gray-900 dark:text-white [color-scheme:light] dark:[color-scheme:dark]"
          />
        </label>
        <label className="flex flex-col gap-1 text-sm text-gray-700 dark:text-gray-200">
          Fecha fin
          <input
            type="datetime-local"
            value={seleccion.fin}
            max={maxDatetime}
            onChange={(e) => onCambiarSeleccion({ ...seleccion, fin: e.target.value })}
            className="rounded-lg border border-black/20 dark:border-white/20 bg-transparent px-3 py-1.5 text-sm text-gray-900 dark:text-white [color-scheme:light] dark:[color-scheme:dark]"
          />
        </label>
      </div>

      {error && <p className="text-xs text-red-600 dark:text-red-400 mt-2">{error}</p>}

      <div className="flex gap-2 mt-3">
        <button
          type="button"
          onClick={handleAplicar}
          className="px-4 py-2 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:brightness-95 transition-all"
        >
          APLICAR
        </button>
        <button
          type="button"
          onClick={handleLimpiar}
          className="px-4 py-2 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/10 dark:hover:bg-white/10 transition-all"
        >
          LIMPIAR FILTRO
        </button>
      </div>
    </fieldset>
  );
}
