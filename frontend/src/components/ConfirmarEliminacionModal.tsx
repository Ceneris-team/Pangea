import { useEffect, useState } from "react";

/**
 * Modal de confirmación para acciones destructivas (eliminar/desactivar).
 *
 * Reemplaza a window.confirm(): el diálogo nativo del navegador se
 * confirma con Enter/click reflejo sin leer el texto, que es justo el
 * riesgo en una acción como desactivar un mapeo (los archivos nuevos con
 * ese prefijo dejan de poder interpretarse). El botón de confirmar arranca
 * deshabilitado con una cuenta regresiva y solo se habilita al llegar a
 * cero, forzando una pausa mínima antes de poder confirmar.
 */

interface ConfirmarEliminacionModalProps {
  titulo: string;
  mensaje: string;
  segundosEspera?: number;
  confirmando?: boolean;
  onConfirmar: () => void;
  onCancelar: () => void;
}

export default function ConfirmarEliminacionModal({
  titulo,
  mensaje,
  segundosEspera = 3,
  confirmando = false,
  onConfirmar,
  onCancelar,
}: ConfirmarEliminacionModalProps) {
  const [segundosRestantes, setSegundosRestantes] = useState(segundosEspera);

  useEffect(() => {
    if (segundosRestantes <= 0) return;
    const temporizador = setTimeout(() => setSegundosRestantes((s) => s - 1), 1000);
    return () => clearTimeout(temporizador);
  }, [segundosRestantes]);

  const puedeConfirmar = segundosRestantes <= 0 && !confirmando;

  return (
    <div
      className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4"
      onClick={onCancelar}
    >
      <div
        className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 max-w-md w-full p-6"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-start gap-3 mb-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full bg-red-50 dark:bg-red-900/20 flex items-center justify-center">
            <svg
              className="w-5 h-5 text-red-600 dark:text-red-400"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="2"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v3.75m9-.75a9 9 0 11-18 0 9 9 0 0118 0zm-9 3.75h.008v.008H12v-.008z"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-bold text-gray-900 dark:text-white">{titulo}</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">{mensaje}</p>
          </div>
        </div>

        <div className="flex justify-end gap-3 mt-5">
          <button
            type="button"
            onClick={onCancelar}
            className="px-4 py-2.5 text-sm font-medium text-gray-600 dark:text-gray-300 hover:text-gray-900 dark:hover:text-white transition-all"
          >
            Cancelar
          </button>
          <button
            type="button"
            onClick={onConfirmar}
            disabled={!puedeConfirmar}
            className="px-4 py-2.5 text-sm font-semibold text-white bg-red-600 rounded-xl hover:bg-red-700 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
          >
            {confirmando
              ? "Eliminando..."
              : segundosRestantes > 0
                ? `Eliminar (${segundosRestantes})`
                : "Eliminar"}
          </button>
        </div>
      </div>
    </div>
  );
}
