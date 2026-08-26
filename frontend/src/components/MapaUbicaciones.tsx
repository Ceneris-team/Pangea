import { Fragment, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { GoogleMap, Marker, Polygon, InfoWindow, useJsApiLoader } from "@react-google-maps/api";
import {
  GOOGLE_MAPS_API_KEY,
  GOOGLE_MAPS_LIBRARIES,
  GOOGLE_MAPS_LOADER_ID,
} from "../config/googleMaps";

/**
 * HU22 - Ver ubicaciones en mapa.
 *
 *   CA1  un control "⋮" por Ubicación anclado en la esquina noreste de
 *        su contorno, verde si está Activa y gris si está Inactiva
 *   CA2  clic en un marcador -> panel con nombre, descripción, estado y
 *        cantidad de dispositivos asociados
 *   CA3  desde ese panel, "Editar ubicación" lleva al formulario de
 *        edición de esa Ubicación, con sus datos precargados
 *   CA4  "Ver listado" vive en la pantalla (MapaUbicacionesPage)
 *
 * El marcador y el polígono conviven: el polígono es el contorno real de
 * la zona (HU08) y el marcador es el punto de referencia lttd/lngtd, que
 * es donde el CA pide anclar el panel.
 *
 * I-17: además se pinta el punto propio de cada Dispositivo (DEC-28)
 * dentro del polígono de su zona. Todos visibles siempre, sin depender
 * del zoom ni de hacer clic. Para que no se confundan con los de
 * Ubicación se distinguen por FORMA y POSICIÓN, no solo por color: la
 * Ubicación es un disco "⋮" en el borde de la zona y el Dispositivo un
 * rombo pequeño dentro del área.
 * Ojo con el estado: Dispositivo usa "Activo"/"Inactivo" (masculino) y
 * Ubicación "Activa"/"Inactiva"; son cadenas distintas en la BD.
 *
 * plgn_gjsn es un GeoJSON Polygon simple (un solo anillo, sin features
 * anidadas -confirmado contra un registro real de la BD-), así que se
 * pinta con <Polygon> pasando sus coordenadas convertidas a {lat, lng};
 * usar google.maps.Data.addGeoJson aquí sería de más, esa API existe para
 * FeatureCollections.
 */

export interface UbicacionParaMapa {
  id_ubccn: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  plgn_gjsn: { type: string; coordinates: number[][][] } | null;
  dispositivos_count: number;
}

/** I-17: el punto propio de un Dispositivo (DEC-28). */
export interface DispositivoParaMapa {
  id_dspstv: number;
  id_ubccn: number;
  nmbr: string;
  mrc: string;
  estd: string;
  lttd: number;
  lngtd: number;
}

interface Props {
  ubicaciones: UbicacionParaMapa[];
  dispositivos: DispositivoParaMapa[];
  /** Ubicación a la que volar, elegida en el buscador de la pantalla. Se
   *  pasa el id y no el objeto para que un cambio de referencia de la
   *  lista no dispare el vuelo de nuevo. */
  volarA?: number | null;
  /** Cambia con cada elección del buscador. Sin esto, elegir DOS VECES la
   *  misma zona no volvería a volar: `volarA` conservaría el mismo id y
   *  el efecto no se re-ejecutaría. */
  volarASecuencia?: number;
}

const CONTENEDOR_ESTILO = { width: "100%", height: "100%" };

// Mismo centro por defecto que MapaDibujoPoligono.tsx (Lima, Perú) para
// cuando todavía no hay ninguna ubicación que centrar.
const CENTRO_POR_DEFECTO = { lat: -12.0464, lng: -77.0428 };

/** CA1: "verde para Activa y gris para Inactiva". El verde es el mismo
 *  #8fb300 de la marca que ya usan los polígonos y los badges de estado
 *  del listado (HU07), para que el mapa no invente una paleta propia. */
const VERDE_ACTIVA = "#8fb300";
const GRIS_INACTIVA = "#9ca3af";

/** I-17: los dispositivos usan un azul propio para separarse de un golpe
 *  de vista del verde de las zonas; el gris de "apagado" es el mismo, así
 *  el mapa mantiene una sola convención para "esto no está operativo". */
const AZUL_ACTIVO = "#2563eb";

function esActiva(ubicacion: UbicacionParaMapa): boolean {
  return ubicacion.estd === "Activa";
}

function colorDe(ubicacion: UbicacionParaMapa): string {
  return esActiva(ubicacion) ? VERDE_ACTIVA : GRIS_INACTIVA;
}

/** Dispositivo.estd es "Activo"/"Inactivo" (masculino), NO el
 *  "Activa"/"Inactiva" de Ubicacion: son columnas distintas de tablas
 *  distintas y comparar con la cadena equivocada pintaría todo en gris. */
function esActivo(dispositivo: DispositivoParaMapa): boolean {
  return dispositivo.estd === "Activo";
}

function colorDeDispositivo(dispositivo: DispositivoParaMapa): string {
  return esActivo(dispositivo) ? AZUL_ACTIVO : GRIS_INACTIVA;
}

function anilloALatLng(poligono: UbicacionParaMapa["plgn_gjsn"]): google.maps.LatLngLiteral[] {
  const anillo = poligono?.coordinates?.[0];
  if (!anillo) return [];
  // GeoJSON usa [lng, lat]; Google Maps espera {lat, lng}.
  return anillo.map(([lng, lat]) => ({ lat, lng }));
}

/**
 * Dónde se ancla el control "⋮" de una zona: su esquina NORESTE (la
 * latitud y longitud máximas de su contorno).
 *
 * Va en el borde y no en el centro (lttd/lngtd) para no tapar el interior
 * del polígono -ahí viven los puntos de los dispositivos- y para que el
 * usuario sepa siempre en qué rincón buscarlo. Si la zona no tiene un
 * contorno válido se cae al punto de referencia, que es lo único que hay.
 */
function esquinaControl(ubicacion: UbicacionParaMapa): google.maps.LatLngLiteral {
  const vertices = anilloALatLng(ubicacion.plgn_gjsn);
  if (vertices.length < 3) return { lat: ubicacion.lttd, lng: ubicacion.lngtd };
  return vertices.reduce(
    (esquina, v) => ({
      lat: Math.max(esquina.lat, v.lat),
      lng: Math.max(esquina.lng, v.lng),
    }),
    { lat: -Infinity, lng: -Infinity }
  );
}

/** El "⋮" del control, como SVG embebido: Google Maps acepta un data URI
 *  en icon.url y así el ícono no depende de ningún asset externo (la CSP
 *  del proyecto tampoco permitiría traerlo de otro host). */
function iconoControl(color: string): string {
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="26" height="26">
    <circle cx="13" cy="13" r="11" fill="${color}" stroke="#ffffff" stroke-width="2"/>
    <circle cx="13" cy="8" r="1.6" fill="#ffffff"/>
    <circle cx="13" cy="13" r="1.6" fill="#ffffff"/>
    <circle cx="13" cy="18" r="1.6" fill="#ffffff"/>
  </svg>`;
  return `data:image/svg+xml;charset=UTF-8,${encodeURIComponent(svg)}`;
}

/** Qué panel está abierto. Un solo estado para los dos tipos: abrir uno
 *  cierra el otro, que es lo que Google Maps hace igual con InfoWindow. */
type Seleccion =
  | { tipo: "ubicacion"; id: number }
  | { tipo: "dispositivo"; id: number }
  | null;

export default function MapaUbicaciones({
  ubicaciones,
  dispositivos,
  volarA,
  volarASecuencia,
}: Props) {
  const navigate = useNavigate();
  const mapaRef = useRef<google.maps.Map | null>(null);
  const { isLoaded, loadError } = useJsApiLoader({
    id: GOOGLE_MAPS_LOADER_ID,
    googleMapsApiKey: GOOGLE_MAPS_API_KEY,
    libraries: GOOGLE_MAPS_LIBRARIES,
  });

  // Se guarda el id y no el objeto: así el panel siempre lee la versión
  // vigente de la lista si esta se recarga, en vez de una copia congelada.
  const [seleccion, setSeleccion] = useState<Seleccion>(null);
  const seleccionada = useMemo(
    () =>
      seleccion?.tipo === "ubicacion"
        ? ubicaciones.find((u) => u.id_ubccn === seleccion.id) ?? null
        : null,
    [ubicaciones, seleccion]
  );
  const dispositivoSeleccionado = useMemo(
    () =>
      seleccion?.tipo === "dispositivo"
        ? dispositivos.find((d) => d.id_dspstv === seleccion.id) ?? null
        : null,
    [dispositivos, seleccion]
  );

  const centro = useMemo(() => {
    if (ubicaciones.length === 0) return CENTRO_POR_DEFECTO;
    const suma = ubicaciones.reduce(
      (acc, u) => ({ lat: acc.lat + u.lttd, lng: acc.lng + u.lngtd }),
      { lat: 0, lng: 0 }
    );
    return { lat: suma.lat / ubicaciones.length, lng: suma.lng / ubicaciones.length };
  }, [ubicaciones]);

  /** Vuela a la ubicación elegida en el buscador y abre su panel.
   *
   *  Encuadra el POLÍGONO completo (fitBounds) en vez de centrar en un
   *  punto: así la zona entra en pantalla sea cual sea su tamaño, sin
   *  tener que adivinar un nivel de zoom. */
  useEffect(() => {
    if (volarA == null) return;
    const mapa = mapaRef.current;
    const destino = ubicaciones.find((u) => u.id_ubccn === volarA);
    if (!mapa || !destino) return;

    const vertices = anilloALatLng(destino.plgn_gjsn);
    if (vertices.length >= 3) {
      const limites = new google.maps.LatLngBounds();
      vertices.forEach((v) => limites.extend(v));
      mapa.fitBounds(limites);
    } else {
      // Sin contorno válido solo queda su punto de referencia.
      mapa.panTo({ lat: destino.lttd, lng: destino.lngtd });
      mapa.setZoom(15);
    }

    setSeleccion({ tipo: "ubicacion", id: destino.id_ubccn });
    // volarASecuencia entra como dependencia a propósito: es lo que
    // permite repetir el vuelo hacia la misma zona.
  }, [volarA, volarASecuencia, ubicaciones]);

  const abrirPanel = useCallback((u: UbicacionParaMapa) => {
    setSeleccion({ tipo: "ubicacion", id: u.id_ubccn });
  }, []);

  const abrirPanelDispositivo = useCallback((d: DispositivoParaMapa) => {
    setSeleccion({ tipo: "dispositivo", id: d.id_dspstv });
  }, []);

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
        No se pudo cargar Google Maps. Revisa la API key y sus restricciones.
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
      zoom={ubicaciones.length === 1 ? 15 : 12}
      // La instancia hace falta para que el buscador de la pantalla pueda
      // reencuadrar el mapa (ver el efecto de `volarA`).
      onLoad={(mapa) => {
        mapaRef.current = mapa;
      }}
      onUnmount={() => {
        mapaRef.current = null;
      }}
    >
      {ubicaciones.map((u) => {
        const trazado = anilloALatLng(u.plgn_gjsn);
        const color = colorDe(u);
        return (
          // Fragment y no <div>: GoogleMap espera a sus hijos como
          // componentes del mapa, envolverlos en DOM real los rompe.
          <Fragment key={u.id_ubccn}>
            {/* El contorno de la zona. Una ubicación sin polígono válido
                igual aparece en el mapa: su marcador basta. */}
            {trazado.length >= 3 && (
              <Polygon
                paths={trazado}
                options={{
                  fillColor: color,
                  fillOpacity: esActiva(u) ? 0.3 : 0.15,
                  strokeColor: color,
                  strokeWeight: 2,
                  clickable: true,
                }}
                onClick={() => abrirPanel(u)}
              />
            )}

            {/* CA1: el marcador de la zona. Se ancla en la esquina NE del
                contorno, no en su centro: en el medio tapaba el interior
                del polígono, que es donde se ven los dispositivos. El "⋮"
                indica que abre un menú con su información. */}
            <Marker
              position={esquinaControl(u)}
              title={`${u.nmbr} — ver detalle`}
              onClick={() => abrirPanel(u)}
              icon={{
                url: iconoControl(color),
                scaledSize: new google.maps.Size(26, 26),
                anchor: new google.maps.Point(13, 13),
              }}
            />
          </Fragment>
        );
      })}

      {/* I-17: el punto propio de cada Dispositivo (DEC-28). Se dibuja
          DESPUÉS de las ubicaciones para que quede por encima del relleno
          del polígono y no se pierda debajo. Rombo pequeño frente al
          círculo grande de la zona: la forma los separa aunque el color
          coincida (los dos usan el mismo gris al estar apagados). */}
      {dispositivos.map((d) => (
        <Marker
          key={d.id_dspstv}
          position={{ lat: d.lttd, lng: d.lngtd }}
          title={`${d.nmbr} · ${d.mrc}`}
          onClick={() => abrirPanelDispositivo(d)}
          icon={{
            path: "M 0,-6 L 6,0 L 0,6 L -6,0 z",
            scale: 1,
            fillColor: colorDeDispositivo(d),
            fillOpacity: 1,
            strokeColor: "#ffffff",
            strokeWeight: 1.5,
          }}
        />
      ))}

      {/* CA2: panel emergente con los datos de la ubicación elegida. Se
          abre sobre el control "⋮" que lo disparó, no sobre el centro. */}
      {seleccionada && (
        <InfoWindow
          position={esquinaControl(seleccionada)}
          onCloseClick={() => setSeleccion(null)}
        >
          {/* El InfoWindow lo renderiza Google fuera del árbol de Tailwind
              del <body>, así que los colores van inline: las clases dark:
              no aplican dentro de este contenedor. */}
          <div style={{ minWidth: 200, maxWidth: 260, color: "#1a202c" }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>{seleccionada.nmbr}</h3>

            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#4b5563" }}>
              {seleccionada.dscrpcn ?? "Sin descripción."}
            </p>

            <div
              style={{
                display: "flex",
                alignItems: "center",
                gap: 8,
                margin: "10px 0",
                flexWrap: "wrap",
              }}
            >
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  padding: "3px 9px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 700,
                  color: esActiva(seleccionada) ? "#3f5400" : "#4b5563",
                  backgroundColor: esActiva(seleccionada) ? "#eaffa3" : "#f3f4f6",
                  border: `1px solid ${esActiva(seleccionada) ? "#c9e86a" : "#d1d5db"}`,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 999,
                    backgroundColor: colorDe(seleccionada),
                  }}
                />
                {seleccionada.estd}
              </span>

              <span style={{ fontSize: 12, color: "#4b5563" }}>
                {seleccionada.dispositivos_count}{" "}
                {seleccionada.dispositivos_count === 1 ? "dispositivo" : "dispositivos"}
              </span>
            </div>

            {/* CA3: al formulario de edición con los datos precargados. */}
            <button
              type="button"
              onClick={() => navigate(`/ubicaciones/${seleccionada.id_ubccn}/editar`)}
              style={{
                width: "100%",
                padding: "7px 12px",
                borderRadius: 10,
                border: "none",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 700,
                color: "#1a202c",
                backgroundColor: "#ccff00",
              }}
            >
              Editar ubicación
            </button>
          </div>
        </InfoWindow>
      )}

      {/* I-17: panel del Dispositivo. Mismos estilos inline que el de
          Ubicación, por el mismo motivo: Google renderiza el InfoWindow
          fuera del árbol de Tailwind y las clases dark: no llegan acá. */}
      {dispositivoSeleccionado && (
        <InfoWindow
          position={{
            lat: dispositivoSeleccionado.lttd,
            lng: dispositivoSeleccionado.lngtd,
          }}
          onCloseClick={() => setSeleccion(null)}
        >
          <div style={{ minWidth: 200, maxWidth: 260, color: "#1a202c" }}>
            <h3 style={{ margin: 0, fontSize: 15, fontWeight: 700 }}>
              {dispositivoSeleccionado.nmbr}
            </h3>

            <p style={{ margin: "6px 0 0", fontSize: 13, color: "#4b5563" }}>
              {dispositivoSeleccionado.mrc}
            </p>

            <div style={{ margin: "10px 0" }}>
              <span
                style={{
                  display: "inline-flex",
                  alignItems: "center",
                  gap: 5,
                  padding: "3px 9px",
                  borderRadius: 999,
                  fontSize: 12,
                  fontWeight: 700,
                  color: esActivo(dispositivoSeleccionado) ? "#1e3a8a" : "#4b5563",
                  backgroundColor: esActivo(dispositivoSeleccionado) ? "#dbeafe" : "#f3f4f6",
                  border: `1px solid ${
                    esActivo(dispositivoSeleccionado) ? "#bfdbfe" : "#d1d5db"
                  }`,
                }}
              >
                <span
                  style={{
                    width: 6,
                    height: 6,
                    borderRadius: 999,
                    backgroundColor: colorDeDispositivo(dispositivoSeleccionado),
                  }}
                />
                {dispositivoSeleccionado.estd}
              </span>
            </div>

            {/* Misma ruta que usa el listado de Gestión de Dispositivos
                (Dispositivos.tsx) para abrir la ficha. */}
            <button
              type="button"
              onClick={() =>
                navigate(`/dispositivos/${dispositivoSeleccionado.id_dspstv}`)
              }
              style={{
                width: "100%",
                padding: "7px 12px",
                borderRadius: 10,
                border: "none",
                cursor: "pointer",
                fontSize: 13,
                fontWeight: 700,
                color: "#ffffff",
                backgroundColor: AZUL_ACTIVO,
              }}
            >
              Ver dispositivo
            </button>
          </div>
        </InfoWindow>
      )}
    </GoogleMap>
  );
}
