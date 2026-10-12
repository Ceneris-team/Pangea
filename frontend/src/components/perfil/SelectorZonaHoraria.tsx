import { useEffect, useId, useMemo, useRef, useState, type KeyboardEvent } from "react";

const MAX_OPCIONES_VISIBLES = 80;

interface Props {
  id: string;
  zonas: string[];
  valor: string;
  onCambiar: (zona: string) => void;
  cargando: boolean;
  errorCarga: boolean;
}

/** Lista propia para evitar el desplegable nativo y permitir buscar zonas IANA. */
export default function SelectorZonaHoraria({ id, zonas, valor, onCambiar, cargando, errorCarga }: Props) {
  const [abierto, setAbierto] = useState(false);
  const [busqueda, setBusqueda] = useState("");
  const [indiceActivo, setIndiceActivo] = useState(0);
  const contenedorRef = useRef<HTMLDivElement>(null);
  const entradaRef = useRef<HTMLInputElement>(null);
  const listaRef = useRef<HTMLDivElement>(null);
  const listaId = useId();

  const opciones = useMemo(() => {
    const disponibles = valor && !zonas.includes(valor) ? [valor, ...zonas] : zonas;
    const termino = busqueda.trim().toLocaleLowerCase();
    if (termino) return disponibles.filter((zona) => zona.toLocaleLowerCase().includes(termino));
    return valor ? [valor, ...disponibles.filter((zona) => zona !== valor)] : disponibles;
  }, [busqueda, valor, zonas]);
  const visibles = opciones.slice(0, MAX_OPCIONES_VISIBLES);

  useEffect(() => {
    if (!abierto) return;
    function cerrarFuera(e: PointerEvent) {
      if (!contenedorRef.current?.contains(e.target as Node)) setAbierto(false);
    }
    document.addEventListener("pointerdown", cerrarFuera);
    return () => document.removeEventListener("pointerdown", cerrarFuera);
  }, [abierto]);

  useEffect(() => {
    if (!abierto) return;
    listaRef.current?.querySelector<HTMLElement>(`[data-indice="${indiceActivo}"]`)?.scrollIntoView({ block: "nearest" });
  }, [abierto, indiceActivo]);

  function abrir() {
    setBusqueda("");
    setIndiceActivo(0);
    setAbierto(true);
  }

  function seleccionar(zona: string) {
    onCambiar(zona);
    setBusqueda("");
    setAbierto(false);
  }

  function manejarTecla(e: KeyboardEvent<HTMLInputElement>) {
    if (e.key === "Escape") {
      if (abierto) {
        e.preventDefault();
        e.stopPropagation();
        setAbierto(false);
      }
      return;
    }
    if (e.key === "Tab") {
      setAbierto(false);
      return;
    }
    if (e.key === "ArrowDown" || e.key === "ArrowUp") {
      e.preventDefault();
      if (!abierto) {
        abrir();
      } else if (visibles.length > 0) {
        setIndiceActivo((actual) =>
          e.key === "ArrowDown"
            ? Math.min(actual + 1, visibles.length - 1)
            : Math.max(actual - 1, 0),
        );
      }
      return;
    }
    if (e.key === "Enter" && abierto) {
      e.preventDefault();
      const opcion = visibles[indiceActivo];
      if (opcion) seleccionar(opcion);
    }
  }

  return (
    <div ref={contenedorRef} className="relative">
      <div className="relative">
        <input
          ref={entradaRef}
          id={id}
          type="text"
          role="combobox"
          aria-autocomplete="list"
          aria-expanded={abierto}
          aria-controls={listaId}
          aria-activedescendant={abierto && visibles[indiceActivo] ? `${listaId}-opcion-${indiceActivo}` : undefined}
          autoComplete="off"
          placeholder={cargando ? "Cargando zonas horarias..." : "Buscar zona horaria..."}
          value={abierto ? busqueda : valor}
          onFocus={() => { if (!abierto) abrir(); }}
          onClick={() => { if (!abierto) abrir(); }}
          onChange={(e) => {
            setBusqueda(e.target.value);
            setIndiceActivo(0);
            setAbierto(true);
          }}
          onKeyDown={manejarTecla}
          className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white placeholder:text-gray-500 dark:placeholder:text-gray-400 text-sm rounded-xl block w-full p-2.5 pr-10 outline-none focus:ring-1 focus:ring-[#ccff00] focus:border-[#ccff00]"
        />
        <button
          type="button"
          aria-label={abierto ? "Cerrar zonas horarias" : "Mostrar zonas horarias"}
          onMouseDown={(e) => e.preventDefault()}
          onClick={() => {
            if (abierto) setAbierto(false);
            else entradaRef.current?.focus();
          }}
          className="absolute inset-y-0 right-0 px-3 text-gray-600 dark:text-gray-300"
        >
          <svg className="h-4 w-4" viewBox="0 0 20 20" fill="none" aria-hidden="true">
            <path d="m5 7 5 5 5-5" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
        </button>
      </div>

      {abierto && (
        <div
          ref={listaRef}
          id={listaId}
          role="listbox"
          aria-label="Zonas horarias"
          className="mt-1 max-h-60 w-full overflow-y-auto rounded-xl border border-black/15 dark:border-white/20 bg-white dark:bg-[#1a202c] py-1 text-sm shadow-xl"
        >
          {visibles.map((zona, indice) => (
            <div
              key={zona}
              id={`${listaId}-opcion-${indice}`}
              role="option"
              aria-selected={zona === valor}
              data-indice={indice}
              onMouseDown={(e) => e.preventDefault()}
              onMouseEnter={() => setIndiceActivo(indice)}
              onClick={() => seleccionar(zona)}
              className={`flex cursor-pointer items-center justify-between gap-2 px-3 py-2 ${
                indice === indiceActivo
                  ? "bg-[#ccff00]/25 text-gray-900 dark:text-white"
                  : "text-gray-800 dark:text-gray-100 hover:bg-black/5 dark:hover:bg-white/10"
              }`}
            >
              <span>{zona}</span>
              {zona === valor && <span aria-hidden="true">✓</span>}
            </div>
          ))}
          {visibles.length === 0 && (
            <p className="px-3 py-2 text-gray-600 dark:text-gray-300">
              {cargando ? "Cargando zonas horarias..." : errorCarga ? "No se pudieron cargar las zonas horarias." : "No se encontraron zonas horarias."}
            </p>
          )}
          {opciones.length > MAX_OPCIONES_VISIBLES && (
            <p className="border-t border-black/10 dark:border-white/10 px-3 py-2 text-xs text-gray-600 dark:text-gray-300">
              Mostrando {MAX_OPCIONES_VISIBLES} de {opciones.length}. Escribe para filtrar.
            </p>
          )}
        </div>
      )}
      {errorCarga && (
        <p className="mt-1 text-xs text-red-600 dark:text-red-400">
          No se pudo cargar la lista de zonas horarias. Recarga la página para intentarlo de nuevo.
        </p>
      )}
    </div>
  );
}
