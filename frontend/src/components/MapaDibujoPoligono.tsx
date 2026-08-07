import { useRef, useState, type MouseEvent } from "react";

/**
 * Herramienta de dibujo de polígono sobre mapa (HU08 CA1).
 *
 * Una UBICACIÓN (zona/sede) se delimita con un polígono GeoJSON de varios
 * vértices, para representar el contorno real e irregular del terreno -no
 * un círculo ni un "punto + radio"-. Un DISPOSITIVO, en cambio, se ubica
 * con un punto GPS simple; por eso el punto de referencia (lat/lng) se
 * captura aparte, en el formulario, y acá solo se dibuja el contorno.
 *
 * Por qué es SVG y no Leaflet/Mapbox: el proyecto no tiene ninguna
 * librería de mapas instalada y el CA1 pide "una herramienta de dibujo de
 * polígono sobre un mapa". Este componente resuelve el dibujo -que es lo
 * que la HU necesita- sin agregar una dependencia ni exigir tiles de un
 * servicio externo. La proyección es equirectangular (lng->x, lat->y
 * lineal), suficiente para dibujar el contorno de un terreno, que abarca
 * unos pocos cientos de metros. El fondo cartográfico real entra con
 * HU22 (Ver ubicaciones en mapa), que es la historia que sí trata sobre
 * el mapa; cuando llegue, se cambia el <svg> por la capa de tiles y este
 * mismo contrato de props (valor/onChange en GeoJSON) se conserva.
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

const ANCHO = 640;
const ALTO = 360;

/** Grados que abarca el lienzo. ~0.01° de latitud son ~1.1 km: la escala
 *  de un terreno, que es lo que una ubicación delimita. */
const SPAN_LAT = 0.01;
const SPAN_LNG = 0.02;

// Centro por defecto cuando el formulario todavía no tiene lat/lng:
// Lima, Perú. Solo fija el encuadre inicial del lienzo.
const CENTRO_POR_DEFECTO = { lat: -12.0464, lng: -77.0428 };

export default function MapaDibujoPoligono({ valor, onChange, centroLat, centroLng }: Props) {
  const svgRef = useRef<SVGSVGElement | null>(null);

  // Vértices en curso. Se mantienen abiertos (sin repetir el primero) y
  // solo se cierra el anillo al emitir el GeoJSON, que es donde el
  // formato lo exige.
  const [vertices, setVertices] = useState<number[][]>(() => aVerticesAbiertos(valor));

  const centro = {
    lat: centroLat ?? CENTRO_POR_DEFECTO.lat,
    lng: centroLng ?? CENTRO_POR_DEFECTO.lng,
  };

  // El encuadre se congela en cuanto hay vértices dibujados: si se
  // recalculara con cada tecleo en Latitud, los puntos ya marcados se
  // moverían debajo del cursor mientras el usuario escribe. Va en estado
  // (no en un ref leído durante el render) para que React lo trate como
  // lo que es: un valor que participa del render.
  const [encuadreFijado, setEncuadreFijado] = useState<{ lat: number; lng: number } | null>(null);
  const encuadre = encuadreFijado ?? centro;

  function aPixel([lng, lat]: number[]): { x: number; y: number } {
    return {
      x: ((lng - encuadre.lng) / SPAN_LNG + 0.5) * ANCHO,
      // El eje Y del SVG crece hacia abajo y la latitud hacia arriba.
      y: (0.5 - (lat - encuadre.lat) / SPAN_LAT) * ALTO,
    };
  }

  function aCoordenada(x: number, y: number): number[] {
    const lng = encuadre.lng + (x / ANCHO - 0.5) * SPAN_LNG;
    const lat = encuadre.lat + (0.5 - y / ALTO) * SPAN_LAT;
    return [redondear(lng), redondear(lat)];
  }

  function emitir(nuevos: number[][]) {
    setVertices(nuevos);
    // Menos de 3 vértices no delimitan un área: el polígono todavía no
    // es válido y el formulario tiene que seguir viéndolo como vacío.
    if (nuevos.length < 3) {
      onChange(null);
      return;
    }
    onChange({ type: "Polygon", coordinates: [[...nuevos, nuevos[0]]] });
  }

  function agregarVertice(e: MouseEvent<SVGSVGElement>) {
    const svg = svgRef.current;
    if (!svg) return;
    const caja = svg.getBoundingClientRect();
    // El SVG se escala con el ancho disponible, así que hay que pasar de
    // píxeles de pantalla a coordenadas del viewBox.
    const x = ((e.clientX - caja.left) / caja.width) * ANCHO;
    const y = ((e.clientY - caja.top) / caja.height) * ALTO;
    // Con el primer vértice se congela el encuadre (ver encuadreFijado).
    if (encuadreFijado === null) setEncuadreFijado(encuadre);
    emitir([...vertices, aCoordenada(x, y)]);
  }

  function deshacer() {
    const restantes = vertices.slice(0, -1);
    if (restantes.length === 0) setEncuadreFijado(null);
    emitir(restantes);
  }

  function limpiar() {
    // Sin vértices el encuadre vuelve a seguir al punto del formulario.
    setEncuadreFijado(null);
    setVertices([]);
    onChange(null);
  }

  const puntos = vertices.map(aPixel);
  const centroPx = aPixel([centro.lng, centro.lat]);
  const poligonoCompleto = vertices.length >= 3;

  return (
    <div>
      <div className="flex flex-wrap items-center justify-between gap-2 mb-2">
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Haz clic sobre el mapa para marcar cada vértice del contorno de la zona. Se
          necesitan al menos 3.
        </p>
        <div className="flex gap-2">
          <button
            type="button"
            onClick={deshacer}
            disabled={vertices.length === 0}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            Deshacer punto
          </button>
          <button
            type="button"
            onClick={limpiar}
            disabled={vertices.length === 0}
            className="px-3 py-1.5 text-xs rounded-lg border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 disabled:opacity-40 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
          >
            Limpiar
          </button>
        </div>
      </div>

      <svg
        ref={svgRef}
        viewBox={`0 0 ${ANCHO} ${ALTO}`}
        onClick={agregarVertice}
        role="application"
        aria-label="Mapa para dibujar el contorno de la ubicación"
        className="w-full h-auto rounded-xl border border-gray-300 dark:border-gray-600 bg-gray-50 dark:bg-gray-800 cursor-crosshair"
      >
        <defs>
          <pattern id="cuadricula-mapa" width="32" height="32" patternUnits="userSpaceOnUse">
            <path
              d="M 32 0 L 0 0 0 32"
              fill="none"
              stroke="currentColor"
              strokeWidth="1"
              className="text-gray-200 dark:text-gray-700"
            />
          </pattern>
        </defs>
        <rect width={ANCHO} height={ALTO} fill="url(#cuadricula-mapa)" />

        {poligonoCompleto && (
          <polygon
            points={puntos.map((p) => `${p.x},${p.y}`).join(" ")}
            fill="#ccff00"
            fillOpacity="0.25"
            stroke="#8fb300"
            strokeWidth="2"
          />
        )}

        {/* Con 2 vértices todavía no hay área, pero sí un segmento que
            conviene mostrar para que el trazo no parezca perdido. */}
        {!poligonoCompleto && puntos.length === 2 && (
          <line
            x1={puntos[0].x}
            y1={puntos[0].y}
            x2={puntos[1].x}
            y2={puntos[1].y}
            stroke="#8fb300"
            strokeWidth="2"
          />
        )}

        {puntos.map((p, i) => (
          <circle key={i} cx={p.x} cy={p.y} r="5" fill="#8fb300" stroke="#ffffff" strokeWidth="2" />
        ))}

        {/* Punto de referencia declarado en el formulario (lat/lng). */}
        {centroLat !== null && centroLng !== null && (
          <g>
            <circle cx={centroPx.x} cy={centroPx.y} r="6" fill="none" stroke="#ef4444" strokeWidth="2" />
            <line
              x1={centroPx.x - 10}
              y1={centroPx.y}
              x2={centroPx.x + 10}
              y2={centroPx.y}
              stroke="#ef4444"
              strokeWidth="2"
            />
            <line
              x1={centroPx.x}
              y1={centroPx.y - 10}
              x2={centroPx.x}
              y2={centroPx.y + 10}
              stroke="#ef4444"
              strokeWidth="2"
            />
          </g>
        )}
      </svg>

      <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
        {vertices.length === 0
          ? "Sin contorno dibujado."
          : `${vertices.length} vértice${vertices.length === 1 ? "" : "s"} marcado${
              vertices.length === 1 ? "" : "s"
            }${poligonoCompleto ? "." : " — faltan puntos para cerrar la zona."}`}
      </p>
    </div>
  );
}

/** Quita el vértice de cierre para volver a la lista editable. */
function aVerticesAbiertos(poligono: PoligonoGeoJSON | null): number[][] {
  const anillo = poligono?.coordinates?.[0];
  if (!anillo || anillo.length < 4) return [];
  return anillo.slice(0, -1);
}

function redondear(valor: number): number {
  // 6 decimales: la misma precisión que Numeric(9,6) de ubccn.lttd/lngtd.
  return Number(valor.toFixed(6));
}
