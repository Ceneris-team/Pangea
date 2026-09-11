import { useEffect } from "react";
import { createPortal } from "react-dom";

/**
 * Panel lateral que se desliza desde la derecha, con overlay oscuro +
 * blur de fondo. Es el ÚNICO patrón que usa todo el sistema para crear o
 * editar algo -formularios que antes eran una mezcla de modal centrado
 * (fixed inset-0 + flex items-center justify-center), página completa
 * con su propia ruta (Sidebar/Topbar repetidos) o un bloque inline que
 * empujaba el resto de la pantalla hacia abajo.
 *
 * Vía portal a document.body para no quedar acotado por el overflow de
 * ningún contenedor padre ni por z-index de otros elementos.
 *
 * `ancho` cubre el caso normal (formularios de texto/selects) con
 * "md" (max-w-md, ~28rem) por defecto; el mapa de dibujo de polígono de
 * Agregar/Editar Ubicación necesita mucho más espacio para ser usable,
 * así que ahí se pasa "xl" (80% del viewport) en vez de forzar el mismo
 * ancho angosto a todos los casos.
 */

const ANCHOS = {
  md: "max-w-md",
  lg: "max-w-2xl",
  xl: "max-w-[80vw]",
} as const;

interface DrawerPanelProps {
  abierto: boolean;
  onCerrar: () => void;
  titulo: string;
  children: React.ReactNode;
  ancho?: keyof typeof ANCHOS;
  /** Contenido fijo al pie del panel (botones Guardar/Cancelar), fuera
   *  del área con scroll -para que siempre queden visibles sin tener que
   *  bajar hasta el final de un formulario largo-. */
  pie?: React.ReactNode;
}

export default function DrawerPanel({
  abierto,
  onCerrar,
  titulo,
  children,
  ancho = "md",
  pie,
}: DrawerPanelProps) {
  // Escape cierra el panel, igual que clickear el overlay -consistente
  // con cualquier otro diálogo del sistema operativo o del navegador-.
  useEffect(() => {
    if (!abierto) return;
    function onKeyDown(e: KeyboardEvent) {
      if (e.key === "Escape") onCerrar();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, [abierto, onCerrar]);

  return createPortal(
    <>
      <div
        className={`fixed inset-0 bg-black/30 backdrop-blur-sm z-40 transition-opacity ${
          abierto ? "opacity-100" : "opacity-0 pointer-events-none"
        }`}
        onClick={onCerrar}
        aria-hidden="true"
      />
      <div
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        className={`fixed top-0 right-0 h-full w-full ${ANCHOS[ancho]} bg-white dark:bg-[#1a202c] shadow-2xl z-50 transition-transform duration-300 flex flex-col ${
          abierto ? "translate-x-0" : "translate-x-full"
        }`}
      >
        <div className="flex items-center justify-between p-5 border-b border-black/10 dark:border-white/10 shrink-0">
          <h2 className="text-sm font-bold text-gray-900 dark:text-white">{titulo}</h2>
          <button
            type="button"
            onClick={onCerrar}
            aria-label="Cerrar panel"
            className="p-1.5 rounded-lg text-gray-500 dark:text-gray-400 hover:bg-black/5 dark:hover:bg-white/10 transition-colors"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M6 18L18 6M6 6l12 12" />
            </svg>
          </button>
        </div>

        <div className="flex-1 overflow-y-auto p-5">{children}</div>

        {pie && <div className="p-5 border-t border-black/10 dark:border-white/10 shrink-0">{pie}</div>}
      </div>
    </>,
    document.body,
  );
}
