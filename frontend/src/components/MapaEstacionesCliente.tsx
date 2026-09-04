import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GoogleMap, Marker, InfoWindow, useJsApiLoader } from "@react-google-maps/api";
import {
  GOOGLE_MAPS_API_KEY,
  GOOGLE_MAPS_LIBRARIES,
  GOOGLE_MAPS_LOADER_ID,
} from "../config/googleMaps";

/**
 * HU17 - Ver datos en mapa (rol Cliente Final).
 *
 *   CA1  marcadores en las coordenadas de las ubicaciones ASIGNADAS al
 *        usuario, coloreados por semáforo (verde/amarillo/rojo)
 *   CA2  clic en un marcador -> panel con el nombre de la estación, el
 *        último valor de cada parámetro y la fecha/hora de la última
 *        lectura
 *   CA3  el marcador se actualiza en vivo (lo resuelve la pantalla, que
 *        es quien sostiene el WebSocket; acá solo se re-renderiza)
 *   CA4  "Ver gráfico" -> /graficos con esta ubicación preseleccionada
 *
 * Es una pantalla DISTINTA del mapa de HU22 (MapaUbicaciones.tsx), no una
 * variante suya: aquella es la vista de gestión del Administrador -con
 * polígonos, conteo de dispositivos y acceso a edición-, esta es la del
 * Cliente Final, centrada en el ESTADO ACTUAL de sus estaciones. Por eso
 * son dos componentes y no uno con props condicionales: casi todo lo que
 * dibujan es diferente, y el de HU22 no se toca.
 *
 * Sin polígonos a propósito: HU17 pide marcadores en las coordenadas, y
 * el contorno de la zona no aporta nada a "ver el dato de un vistazo".
 *
 * DEUDA CONOCIDA: usa google.maps.Marker, deprecado en favor de
 * AdvancedMarkerElement. Se mantiene por consistencia con MapaUbicaciones
 * (HU22), que usa la misma API; migrar los dos a la vez es una tarea
 * aparte y fuera del alcance de HU17.
 */

export interface ParametroDeEstacion {
  parametro: string;
  unidad: string;
  valor: number | string | null;
  fch_hr: string | null;
}

export interface EstacionParaMapa {
  id_ubccn: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  semaforo: string;
  ultima_lectura: string | null;
  parametros: ParametroDeEstacion[];
}

interface Props {
  estaciones: EstacionParaMapa[];
  /** id_ubccn que acaba de recibir un dato nuevo por WebSocket. Sirve
   *  para resaltar el marcador un instante: sin señal visual, una
   *  actualización en vivo es indistinguible de que no pase nada (CA3). */
  destelloEn?: number | null;
  destelloSecuencia?: number;
}

const CONTENEDOR_ESTILO = { width: "100%", height: "100%" };

// Mismo centro por defecto que el resto de los mapas de la app (Lima,
// Perú), para cuando el usuario todavía no tiene estaciones asignadas.
const CENTRO_POR_DEFECTO = { lat: -12.0464, lng: -77.0428 };

/** Colores del semáforo. Elegidos para que se distingan también en
 *  daltonismo rojo-verde: el amarillo es claramente más luminoso que los
 *  otros dos, y el panel de CA2 dice el estado en palabras además del
 *  color, así que el color nunca es el único portador de la información. */
const COLOR_SEMAFORO: Record<string, string> = {
  verde: "#16a34a",
  amarillo: "#eab308",
  rojo: "#dc2626",
};

const ETIQUETA_SEMAFORO: Record<string, string> = {
  verde: "Normal",
  amarillo: "Atención",
  rojo: "Crítico",
};

function colorDe(semaforo: string): string {
  return COLOR_SEMAFORO[semaforo] ?? COLOR_SEMAFORO.verde;
}

/** Marcador como SVG embebido en un data URI: igual que en HU22, así el
 *  ícono no depende de ningún asset externo (la CSP tampoco lo permitiría).
 *
 *  `destacado` engorda el anillo exterior. Es el efecto que marca "este
 *  marcador acaba de recibir un dato" (CA3). */
function iconoEstacion(color: string, destacado: boolean): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="34" height="34">
    ${destacado ? `<circle cx="17" cy="17" r="16" fill="${color}" opacity="0.35"/>` : ""}
    <circle cx="17" cy="17" r="10" fill="${color}" stroke="#ffffff" stroke-width="3"/>
  </svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

function formatearFechaHora(iso: string | null): string {
  if (!iso) return "Sin lecturas";
  return new Date(iso).toLocaleString("es", {
    day: "2-digit",
    month: "short",
    year: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function formatearValor(valor: number | string | null): string {
  if (valor === null) return "—";
  // Un evento de texto (evnt_txt, ej. "Puerta Abierta") se muestra tal
  // cual; uno numérico se recorta a 2 decimales, que es lo que un panel
  // de un vistazo necesita -tlmtr guarda 4-.
  if (typeof valor === "string") return valor;
  return Number.isInteger(valor) ? String(valor) : valor.toFixed(2);
}

export default function MapaEstacionesCliente({
  estaciones,
  destelloEn,
  destelloSecuencia,
}: Props) {
  const navigate = useNavigate();
  const mapaRef = useRef<google.maps.Map | null>(null);
  const { isLoaded, loadError } = useJsApiLoader({
    id: GOOGLE_MAPS_LOADER_ID,
    googleMapsApiKey: GOOGLE_MAPS_API_KEY,
    libraries: GOOGLE_MAPS_LIBRARIES,
  });

  // Se guarda el id y no el objeto: así el panel siempre lee la versión
  // vigente de la lista. Es lo que hace que el panel abierto se actualice
  // solo cuando llega un dato nuevo por WebSocket (CA2 + CA3).
  const [seleccionada, setSeleccionada] = useState<number | null>(null);
  const estacionSeleccionada = useMemo(
    () => estaciones.find((e) => e.id_ubccn === seleccionada) ?? null,
    [estaciones, seleccionada]
  );

  // Marcador con destello activo. Se apaga solo tras un momento.
  const [destellando, setDestellando] = useState<number | null>(null);
  useEffect(() => {
    if (destelloEn == null) return;
    setDestellando(destelloEn);
    const timer = window.setTimeout(() => setDestellando(null), 2000);
    return () => window.clearTimeout(timer);
    // destelloSecuencia entra como dependencia a propósito: permite que
    // dos datos seguidos de la MISMA estación destellen las dos veces.
  }, [destelloEn, destelloSecuencia]);

  const centro = useMemo(() => {
    if (estaciones.length === 0) return CENTRO_POR_DEFECTO;
    const suma = estaciones.reduce(
      (acc, e) => ({ lat: acc.lat + e.lttd, lng: acc.lng + e.lngtd }),
      { lat: 0, lng: 0 }
    );
    return { lat: suma.lat / estaciones.length, lng: suma.lng / estaciones.length };
  }, [estaciones]);

  /** Encuadra todas las estaciones al cargar. fitBounds y no un zoom fijo:
   *  el usuario puede tener dos estaciones a 5 km o a 500 km y las dos
   *  tienen que entrar en pantalla sin adivinar el nivel de zoom.
   *
   *  Solo se ejecuta cuando cambia la CANTIDAD de estaciones, no en cada
   *  actualización de datos: si dependiera de `estaciones`, cada lectura
   *  que llega por WebSocket reencuadraría el mapa y le movería la vista
   *  al usuario mientras la está mirando (CA3 pide actualizar el
   *  marcador, no saltar la cámara). */
  const onLoad = useCallback(
    (mapa: google.maps.Map) => {
      mapaRef.current = mapa;
      if (estaciones.length === 0) return;
      if (estaciones.length === 1) {
        mapa.setCenter({ lat: estaciones[0].lttd, lng: estaciones[0].lngtd });
        mapa.setZoom(14);
        return;
      }
      const limites = new google.maps.LatLngBounds();
      estaciones.forEach((e) => limites.extend({ lat: e.lttd, lng: e.lngtd }));
      mapa.fitBounds(limites);
    },
    [estaciones]
  );

  if (!GOOGLE_MAPS_API_KEY) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-red-600 dark:text-red-400 p-6 text-center">
        Falta configurar VITE_GOOGLE_MAPS_API_KEY en el .env del frontend.
      </div>
    );
  }

  if (loadError) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-red-600 dark:text-red-400 p-6 text-center">
        No se pudo cargar Google Maps. Revisa la API key y que las APIs estén habilitadas.
      </div>
    );
  }

  if (!isLoaded) {
    return (
      <div className="flex items-center justify-center h-full text-sm text-gray-500 dark:text-gray-400">
        Cargando mapa...
      </div>
    );
  }

  return (
    <GoogleMap
      mapContainerStyle={CONTENEDOR_ESTILO}
      center={centro}
      zoom={6}
      onLoad={onLoad}
      options={{
        // CA de la conversación del .docx: "zoom y desplazamiento libre".
        gestureHandling: "greedy",
        streetViewControl: false,
        mapTypeControl: true,
        fullscreenControl: true,
      }}
    >
      {estaciones.map((estacion) => (
        <Marker
          key={estacion.id_ubccn}
          position={{ lat: estacion.lttd, lng: estacion.lngtd }}
          title={`${estacion.nmbr} — ${ETIQUETA_SEMAFORO[estacion.semaforo] ?? estacion.semaforo}`}
          icon={{
            url: iconoEstacion(
              colorDe(estacion.semaforo),
              destellando === estacion.id_ubccn
            ),
            scaledSize: new google.maps.Size(34, 34),
            anchor: new google.maps.Point(17, 17),
          }}
          onClick={() => setSeleccionada(estacion.id_ubccn)}
        />
      ))}

      {estacionSeleccionada && (
        <InfoWindow
          position={{ lat: estacionSeleccionada.lttd, lng: estacionSeleccionada.lngtd }}
          onCloseClick={() => setSeleccionada(null)}
        >
          {/* Google renderiza el InfoWindow fuera del árbol de Tailwind
              del resto de la app, así que los estilos van inline o con
              clases utilitarias simples, igual que en HU22. */}
          <div className="min-w-[260px] max-w-[320px] p-1">
            <div className="flex items-start justify-between gap-3 mb-2">
              <h3 className="text-base font-bold text-gray-900">{estacionSeleccionada.nmbr}</h3>
              <span
                className="shrink-0 inline-flex items-center gap-1.5 text-xs font-medium px-2 py-0.5 rounded-full"
                style={{
                  backgroundColor: `${colorDe(estacionSeleccionada.semaforo)}1a`,
                  color: colorDe(estacionSeleccionada.semaforo),
                }}
              >
                <span
                  className="w-2 h-2 rounded-full"
                  style={{ backgroundColor: colorDe(estacionSeleccionada.semaforo) }}
                />
                {ETIQUETA_SEMAFORO[estacionSeleccionada.semaforo] ?? estacionSeleccionada.semaforo}
              </span>
            </div>

            {estacionSeleccionada.dscrpcn && (
              <p className="text-xs text-gray-500 mb-2">{estacionSeleccionada.dscrpcn}</p>
            )}

            {/* CA2: último valor de CADA parámetro. */}
            {estacionSeleccionada.parametros.length === 0 ? (
              <p className="text-sm text-gray-500 py-2">
                Esta estación todavía no tiene lecturas registradas.
              </p>
            ) : (
              <table className="w-full text-sm mb-2">
                <tbody>
                  {estacionSeleccionada.parametros.map((p) => (
                    <tr key={p.parametro} className="border-b border-gray-100 last:border-0">
                      <td className="py-1 pr-3 text-gray-600">{p.parametro}</td>
                      <td className="py-1 text-right font-semibold text-gray-900 tabular-nums">
                        {formatearValor(p.valor)}
                        {p.unidad && p.unidad !== "-" && (
                          <span className="font-normal text-gray-500"> {p.unidad}</span>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}

            {/* CA2: fecha/hora de la última lectura. */}
            <p className="text-xs text-gray-500 mb-3">
              Última lectura: {formatearFechaHora(estacionSeleccionada.ultima_lectura)}
            </p>

            {/* CA4: ir a la vista de gráficos (HU15) con esta ubicación
                ya preseleccionada. */}
            <button
              type="button"
              onClick={() =>
                navigate(`/graficos?ubicacion_id=${estacionSeleccionada.id_ubccn}`)
              }
              className="w-full inline-flex items-center justify-center gap-2 px-3 py-2 text-sm font-medium rounded-lg bg-gray-900 text-white hover:bg-gray-700 transition-colors"
            >
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth="2"
                  d="M3 3v18h18M7 15l4-5 3 3 5-7"
                />
              </svg>
              Ver gráfico
            </button>
          </div>
        </InfoWindow>
      )}
    </GoogleMap>
  );
}
