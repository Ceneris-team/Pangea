import { useEffect, useRef } from "react";
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

// Solo el panel superior gestiona el teclado cuando se abren paneles anidados.
const panelesAbiertos: HTMLElement[] = [];
const SELECTOR_FOCO = 'a[href], button, input, select, textarea, [tabindex]';

interface DrawerPanelProps {
  abierto: boolean;
  onCerrar: () => void;
  titulo: string;
  children: React.ReactNode;
  ancho?: keyof typeof ANCHOS;
  panelClassName?: string;
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
  panelClassName = "",
  pie,
}: DrawerPanelProps) {
  const panelRef = useRef<HTMLDivElement>(null);
  const cerrarRef = useRef(onCerrar);

  useEffect(() => { cerrarRef.current = onCerrar; }, [onCerrar]);

  useEffect(() => {
    if (!abierto) return;
    if (!panelRef.current) return;
    const panel = panelRef.current;
    const focoAnterior = document.activeElement instanceof HTMLElement ? document.activeElement : null;
    panelesAbiertos.push(panel);
    const enfocable = () => [...panel.querySelectorAll<HTMLElement>(SELECTOR_FOCO)]
      .filter(el => el.tabIndex >= 0 && !el.matches(':disabled') && !el.closest('[inert]') && el.getClientRects().length > 0);
    const esSuperior = () => panelesAbiertos.at(-1) === panel;
    panel.focus({ preventScroll: true });

    function onKeyDown(e: KeyboardEvent) {
      if (!esSuperior()) return;
      if (e.key === "Escape") {
        e.preventDefault();
        e.stopPropagation();
        cerrarRef.current();
      }
      if (e.key !== "Tab") return;
      const elementos = enfocable();
      const primero = elementos[0];
      const ultimo = elementos.at(-1);
      if (!primero || !ultimo) { e.preventDefault(); panel.focus(); return; }
      if (e.shiftKey && (document.activeElement === primero || document.activeElement === panel)) {
        e.preventDefault(); ultimo.focus();
      } else if (!e.shiftKey && (document.activeElement === ultimo || document.activeElement === panel)) {
        e.preventDefault(); primero.focus();
      }
    }
    function mantenerFoco(e: FocusEvent) {
      if (esSuperior() && e.target instanceof Node && !panel.contains(e.target)) {
        (enfocable()[0] ?? panel).focus({ preventScroll: true });
      }
    }
    document.addEventListener("keydown", onKeyDown, true);
    document.addEventListener("focusin", mantenerFoco);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      document.removeEventListener("focusin", mantenerFoco);
      panelesAbiertos.splice(panelesAbiertos.indexOf(panel), 1);
      if (focoAnterior?.isConnected) focoAnterior.focus({ preventScroll: true });
    };
  }, [abierto]);

  return createPortal(
    <>
      <div
        className="ui-panel-fondo fixed inset-0 bg-black/30 z-40"
        data-abierto={abierto}
        onClick={onCerrar}
        aria-hidden="true"
      />
      <div
        ref={panelRef}
        role="dialog"
        aria-modal="true"
        aria-label={titulo}
        aria-hidden={!abierto}
        inert={!abierto}
        tabIndex={-1}
        data-abierto={abierto}
        className={`ui-panel-lateral fixed top-0 right-0 h-full w-full ${ANCHOS[ancho]} bg-white dark:bg-[#1a202c] shadow-2xl z-50 flex flex-col ${panelClassName}`}
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

        <div className="ui-panel-scroll flex-1 overflow-y-auto p-5">{children}</div>

        {pie && <div className="p-5 border-t border-black/10 dark:border-white/10 shrink-0">{pie}</div>}
      </div>
    </>,
    document.body,
  );
}
