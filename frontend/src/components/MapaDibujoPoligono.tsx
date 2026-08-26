import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { GoogleMap, Marker, Polygon, Polyline, useJsApiLoader } from "@react-google-maps/api";
import {
  GOOGLE_MAPS_API_KEY,
  GOOGLE_MAPS_LIBRARIES,
  GOOGLE_MAPS_LOADER_ID,
} from "../config/googleMaps";

/**
 * Herramienta de dibujo de polígono sobre mapa (HU08 CA1).
 *
 * Una UBICACIÓN (zona/sede) se delimita con un polígono GeoJSON de varios
 * vértices, para representar el contorno real e irregular del terreno -no
 * un círculo ni un "punto + radio"-. Un DISPOSITIVO, en cambio, se ubica
 * con un punto GPS simple; por eso el punto de referencia (lat/lng) se
 * captura aparte, en el formulario, y acá solo se dibuja el contorno.
 *
 * El fondo cartográfico es Google Maps (DEC-20). Antes este componente
 * dibujaba sobre un <svg> propio con proyección equirectangular, como
 * placeholder deliberado mientras el proyecto no tenía librería de mapas
 * ni proveedor decidido; ese SVG ya no existe.
 *
 * Por qué el dibujo es a mano y no con la Drawing library de Google: el
 * DrawingManager fue deprecado en agosto 2025 y ELIMINADO de la Maps
 * JavaScript API en la v3.65 (junio 2026) -usarlo hoy lanza una excepción
 * que tumba la página entera-. Google recomienda migrar a Terra Draw, pero
 * para "clic por vértice" no hace falta una dependencia nueva: se escucha
 * el onClick del mapa y se cierra el anillo al hacer clic sobre el primer
 * vértice. Lo que sí sigue plenamente soportado es google.maps.Polygon con
 * editable:true, que es lo que da los vértices arrastrables una vez que el
 * contorno está cerrado.
 *
 * El contrato de props (valor/onChange en GeoJSON, centroLat/centroLng) se
 * conservó intacto en la migración desde el SVG, así que
 * AgregarUbicacion.tsx no necesitó cambios.
 *
 * Arriba del mapa hay un buscador de lugares (Places Autocomplete) que
 * solo reencuadra la vista, para no tener que arrastrar desde el centro
 * por defecto hasta la zona a dibujar. Si "Places API" no está habilitada
 * en el proyecto de Google Cloud, el input queda inerte y el dibujo sigue
 * funcionando igual.
 *
 * Nota sobre centroLat/centroLng: los formularios ya no piden lat/lng
 * tecleados, los DERIVAN del contorno (ver components/poligono.ts). Estas
 * props siguen recibiendo ese punto para dibujarlo como referencia, así
 * que el contrato no cambió.
 *
 * La API key va por VITE_GOOGLE_MAPS_API_KEY (nunca hardcodeada).
 */

export interface PoligonoGeoJSON {
  type: "Polygon";
  /** GeoJSON usa [longitud, latitud], en ese orden. El anillo exterior
   *  va cerrado: el último vértice repite el primero. */
  coordinates: number[][][];
}

interface Props {
  /** Polígono actual, o null si todavía no se dibujó ninguno. */
  valor: PoligonoGeoJSON | null;
  onChange: (poligono: PoligonoGeoJSON | null) => void;
  /** Punto de referencia del formulario (lat/lng). Se dibuja como marca
   *  para que el usuario vea si el contorno rodea al punto que declaró. */
  centroLat: number | null;
  centroLng: number | null;
}

// Centro por defecto cuando el formulario todavía no tiene lat/lng:
// Lima, Perú. Solo fija el encuadre inicial del mapa.
const CENTRO_POR_DEFECTO = { lat: -12.0464, lng: -77.0428 };

const CONTENEDOR_ESTILO = { width: "100%", height: "360px" };

const ESTILO_POLIGONO = {
  fillColor: "#ccff00",
  fillOpacity: 0.25,
  strokeColor: "#8fb300",
  strokeWeight: 2,
};

/** Mínimo para que el anillo delimite un área. Es el mismo que valida
 *  UbicacionCrear (Pydantic) en el backend; se repite acá para no depender
 *  solo de esa validación tardía. */
const VERTICES_MINIMOS = 3;

/** 6 decimales: la misma precisión que Numeric(9,6) de ubccn.lttd/lngtd. */
function redondear(valor: number): number {
  return Number(valor.toFixed(6));
}

/** Vértices en curso -> GeoJSON, con el anillo cerrado. Devuelve null si
 *  todavía no hay área: el formulario tiene que seguir viéndolo vacío. */
function aGeoJSON(vertices: google.maps.LatLngLiteral[]): PoligonoGeoJSON | null {
  if (vertices.length < VERTICES_MINIMOS) return null;
  const anillo = vertices.map((v) => [redondear(v.lng), redondear(v.lat)]);
  return { type: "Polygon", coordinates: [[...anillo, anillo[0]]] };
}

/** Quita el vértice de cierre para volver a la lista editable: Google Maps
 *  cierra el anillo solo, repetirlo duplicaría un vértice sobre el primero. */
function aVerticesAbiertos(poligono: PoligonoGeoJSON | null): google.maps.LatLngLiteral[] {
  const anillo = poligono?.coordinates?.[0];
  if (!anillo || anillo.length < VERTICES_MINIMOS + 1) return [];
  return anillo.slice(0, -1).map(([lng, lat]) => ({ lat, lng }));
}

export default function MapaDibujoPoligono({ valor, onChange, centroLat, centroLng }: Props) {
  const { isLoaded, loadError } = useJsApiLoader({
    id: GOOGLE_MAPS_LOADER_ID,
    googleMapsApiKey: GOOGLE_MAPS_API_KEY,
    libraries: GOOGLE_MAPS_LIBRARIES,
  });

  // Vértices en curso mientras se dibuja (anillo abierto). Una vez cerrado
  // el contorno, la fuente de verdad pasa a ser `valor` y este arreglo se
  // vacía: si no, habría dos copias del mismo dato desincronizándose.
  const [enCurso, setEnCurso] = useState<google.maps.LatLngLiteral[]>([]);

  // El <Polygon> editable, para leer sus vértices cuando el usuario los
  // arrastra. Vive fuera de React porque lo instancia Google Maps.
  const poligonoRef = useRef<google.maps.Polygon | null>(null);
  const listenersRef = useRef<google.maps.MapsEventListener[]>([]);

  const centro = useMemo(
    () => ({
      lat: centroLat ?? CENTRO_POR_DEFECTO.lat,
      lng: centroLng ?? CENTRO_POR_DEFECTO.lng,
    }),
    [centroLat, centroLng]
  );

  // El encuadre se congela en cuanto hay algo dibujado: si el mapa se
  // recentrara con cada tecleo en Latitud, el contorno ya marcado se
  // movería debajo del cursor mientras el usuario escribe.
  const [encuadreFijado, setEncuadreFijado] = useState<google.maps.LatLngLiteral | null>(null);
  const encuadre = encuadreFijado ?? centro;

  const contenedorBusquedaRef = useRef<HTMLDivElement | null>(null);
  const [busquedaDisponible, setBusquedaDisponible] = useState(true);

  const cerrado = valor !== null;
  const verticesCerrados = useMemo(() => aVerticesAbiertos(valor), [valor]);

  function quitarListeners() {
    listenersRef.current.forEach((l) => l.remove());
    listenersRef.current = [];
  }

  /** Lee los vértices del <Polygon> editable y los emite. Se llama cuando
   *  el usuario arrastra un vértice (set_at), agrega uno tirando del punto
   *  intermedio (insert_at) o quita uno (remove_at). */
  const emitirDesdePoligono = useCallback(
    (poligono: google.maps.Polygon) => {
      const vertices = poligono
        .getPath()
        .getArray()
        .map((p) => ({ lat: p.lat(), lng: p.lng() }));
      onChange(aGeoJSON(vertices));
    },
    [onChange]
  );

  const onPoligonoCargado = useCallback(
    (poligono: google.maps.Polygon) => {
      poligonoRef.current = poligono;
      quitarListeners();
      const ruta = poligono.getPath();
      listenersRef.current = [
        ruta.addListener("set_at", () => emitirDesdePoligono(poligono)),
        ruta.addListener("insert_at", () => emitirDesdePoligono(poligono)),
        ruta.addListener("remove_at", () => emitirDesdePoligono(poligono)),
      ];
    },
    [emitirDesdePoligono]
  );

  const onPoligonoDesmontado = useCallback(() => {
    quitarListeners();
    poligonoRef.current = null;
  }, []);

  /** Cada clic sobre el mapa agrega un vértice. No emite todavía: el
   *  polígono solo cuenta como válido cuando el usuario lo cierra, así el
   *  formulario no recibe contornos a medio dibujar. */
  const onMapaClick = useCallback(
    (e: google.maps.MapMouseEvent) => {
      if (cerrado || !e.latLng) return;
      const punto = { lat: e.latLng.lat(), lng: e.latLng.lng() };
      setEnCurso((previos) => {
        if (previos.length === 0) setEncuadreFijado(encuadre);
        return [...previos, punto];
      });
    },
    [cerrado, encuadre]
  );

  /** Clic sobre el primer vértice: cierra el anillo y recién ahí emite. */
  const cerrarPoligono = useCallback(() => {
    if (enCurso.length < VERTICES_MINIMOS) return;
    onChange(aGeoJSON(enCurso));
    setEnCurso([]);
  }, [enCurso, onChange]);

  function deshacer() {
    if (cerrado) return;
    setEnCurso((previos) => {
      const restantes = previos.slice(0, -1);
      if (restantes.length === 0) setEncuadreFijado(null);
      return restantes;
    });
  }

  function limpiar() {
    quitarListeners();
    poligonoRef.current = null;
    setEnCurso([]);
    setEncuadreFijado(null);
    onChange(null);
  }

  useEffect(() => {
    // Los listeners viven en objetos de Google Maps, fuera de React: sin
    // esto quedarían colgados al desmontar el formulario.
    return () => quitarListeners();
  }, []);

  /** Monta el buscador de lugares. Solo reencuadra el mapa: no toca el
   *  contorno ni emite onChange.
   *
   *  Usa PlaceAutocompleteElement y NO el clásico
   *  google.maps.places.Autocomplete: ese último dejó de estar disponible
   *  para proyectos de Google Cloud creados después de marzo de 2025 -el
   *  de Pangea lo es-, así que ahí no devuelve sugerencias nunca.
   *  PlaceAutocompleteElement es un custom element: se inyecta en un
   *  contenedor en vez de decorar un <input> propio.
   *
   *  Degradación: si "Places API (New)" no está habilitada en el proyecto,
   *  el elemento no se monta y en su lugar queda el aviso estático; el
   *  dibujo del contorno sigue funcionando igual. */
  useEffect(() => {
    const contenedor = contenedorBusquedaRef.current;
    if (!isLoaded || !contenedor) return;

    const Elemento = (
      google.maps.places as unknown as {
        PlaceAutocompleteElement?: new (opciones?: object) => HTMLElement;
      }
    )?.PlaceAutocompleteElement;
    if (!Elemento) {
      setBusquedaDisponible(false);
      return;
    }

    const elemento = new Elemento();
    elemento.style.width = "100%";
    contenedor.replaceChildren(elemento);

    // El evento entrega una referencia al lugar; hay que pedirle la
    // ubicación explícitamente (la API nueva no la trae de entrada).
    const onSelect = async (evento: Event) => {
      const prediccion = (evento as unknown as { placePrediction?: unknown }).placePrediction as
        | { toPlace: () => { fetchFields: (o: object) => Promise<void>; location?: google.maps.LatLng } }
        | undefined;
      if (!prediccion) return;
      try {
        const lugar = prediccion.toPlace();
        await lugar.fetchFields({ fields: ["location"] });
        if (!lugar.location) return;
        // Mueve el encuadre aunque ya haya vértices dibujados: es una
        // acción explícita del usuario, no el recentrado automático que
        // encuadreFijado existe para evitar.
        setEncuadreFijado({ lat: lugar.location.lat(), lng: lugar.location.lng() });
      } catch {
        // Places sin habilitar o cuota agotada: el mapa sigue usable.
        setBusquedaDisponible(false);
      }
    };

    elemento.addEventListener("gmp-select", onSelect as EventListener);
    return () => {
      elemento.removeEventListener("gmp-select", onSelect as EventListener);
      contenedor.replaceChildren();
    };
  }, [isLoaded]);

  if (!GOOGLE_MAPS_API_KEY) {
    return (
      <div className="rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-6 text-center text-sm text-red-600 dark:text-red-400">
        Falta configurar VITE_GOOGLE_MAPS_API_KEY en el .env del frontend.
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-6 text-center text-sm text-red-600 dark:text-red-400">
        No se pudo cargar Google Maps. Revisa la API key y sus restricciones.
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 p-6 text-center text-sm text-gray-500 dark:text-gray-400">
        Cargando mapa...
      </div>
    );
  }

  const puedeCerrar = !cerrado && enCurso.length >= VERTICES_MINIMOS;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {cerrado
            ? "Arrastra los vértices para ajustar el contorno."
            : "Haz clic sobre el mapa para marcar cada vértice. Se necesitan al menos 3; luego haz clic en el primer vértice (o en «Cerrar contorno») para cerrar la zona."}
        </p>
        <div className="flex gap-2">
          {!cerrado && (
            <>
              <button
                type="button"
                onClick={deshacer}
                disabled={enCurso.length === 0}
                className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
              >
                Deshacer punto
              </button>
              <button
                type="button"
                onClick={cerrarPoligono}
                disabled={!puedeCerrar}
                className="px-3 py-1.5 text-xs rounded-lg border border-[#8fb300] text-[#5a7000] dark:text-[#ccff00] disabled:opacity-40 hover:bg-[#ccff00]/10 transition-colors"
              >
                Cerrar contorno
              </button>
            </>
          )}
          <button
            type="button"
            onClick={limpiar}
            disabled={!cerrado && enCurso.length === 0}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            Limpiar
          </button>
        </div>
      </div>

      {/* Buscador de lugares: evita tener que arrastrar el mapa desde el
          centro por defecto (Lima) hasta la zona que se va a dibujar.
          Solo mueve el encuadre; no toca el contorno ni el formulario.
          El Enter se atrapa acá porque enviaría el formulario que envuelve
          a este componente. */}
      <div
        ref={contenedorBusquedaRef}
        onKeyDown={(e) => {
          if (e.key === "Enter") e.preventDefault();
        }}
        className="mb-2 [&_gmp-place-autocomplete]:w-full"
      />
      {!busquedaDisponible && (
        <p className="mb-2 text-xs text-gray-500 dark:text-gray-400">
          El buscador de lugares no está disponible (falta habilitar «Places API (New)» en
          Google Cloud). Puedes ubicar la zona arrastrando el mapa.
        </p>
      )}

      <div className="rounded-xl overflow-hidden border border-gray-300 dark:border-gray-600">
        <GoogleMap
          mapContainerStyle={CONTENEDOR_ESTILO}
          center={encuadre}
          zoom={15}
          onClick={onMapaClick}
          options={{ draggableCursor: cerrado ? undefined : "crosshair" }}
        >
          {/* Contorno ya cerrado: editable arrastrando vértices. */}
          {cerrado && verticesCerrados.length >= VERTICES_MINIMOS && (
            <Polygon
              paths={verticesCerrados}
              editable
              options={ESTILO_POLIGONO}
              onLoad={onPoligonoCargado}
              onUnmount={onPoligonoDesmontado}
            />
          )}

          {/* Mientras se dibuja: la línea que une lo marcado hasta ahora.
              Con 2 puntos todavía no hay área, pero conviene mostrar el
              segmento para que el trazo no parezca perdido. */}
          {!cerrado && enCurso.length >= 2 && (
            <Polyline
              path={enCurso}
              options={{ strokeColor: "#8fb300", strokeWeight: 2 }}
            />
          )}

          {/* Vértices marcados. El primero cierra el anillo al hacer clic,
              por eso va más grande y con su propio cursor. */}
          {!cerrado &&
            enCurso.map((punto, i) => (
              <Marker
                key={i}
                position={punto}
                onClick={i === 0 ? cerrarPoligono : undefined}
                title={i === 0 ? "Clic para cerrar el contorno" : `Vértice ${i + 1}`}
                icon={{
                  path: google.maps.SymbolPath.CIRCLE,
                  scale: i === 0 && puedeCerrar ? 8 : 5,
                  fillColor: "#8fb300",
                  fillOpacity: 1,
                  strokeColor: "#ffffff",
                  strokeWeight: 2,
                }}
              />
            ))}

          {/* Punto de referencia declarado en el formulario (lat/lng). */}
          {centroLat !== null && centroLng !== null && (
            <Marker position={{ lat: centroLat, lng: centroLng }} title="Punto de referencia" />
          )}
        </GoogleMap>
      </div>

      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {cerrado
          ? `Contorno cerrado con ${verticesCerrados.length} vértices.`
          : enCurso.length === 0
            ? "Sin contorno dibujado."
            : `${enCurso.length} vértice${enCurso.length === 1 ? "" : "s"} marcado${
                enCurso.length === 1 ? "" : "s"
              }${puedeCerrar ? " — ya puedes cerrar el contorno." : " — faltan puntos para cerrar la zona."}`}
      </p>
    </div>
  );
}
