/**
 * Opciones únicas del loader de Google Maps (DEC-20).
 *
 * @react-google-maps/api carga UN solo script por página: si dos
 * componentes llaman a useJsApiLoader con el mismo `id` pero distintas
 * `libraries`, el segundo revienta con "Loader must not be called again
 * with different options" y su mapa no carga nunca. Por eso las opciones
 * viven acá y no en cada componente: la lista de librerías es la UNIÓN de
 * lo que necesita cualquier mapa de la app. Al agregar un mapa nuevo que
 * precise otra librería, se agrega a esta lista, no a una constante local.
 *
 * Las constantes son de módulo a propósito: useJsApiLoader compara
 * `libraries` por identidad, así que un array nuevo en cada render
 * reiniciaría la carga del script.
 */
import type { Libraries } from "@react-google-maps/api";

export const GOOGLE_MAPS_LOADER_ID = "pangea-google-maps";

/**
 * 'places' la usa el buscador de lugares de MapaDibujoPoligono (HU08):
 * sin ella, google.maps.places llega undefined y la caja de búsqueda no
 * puede autocompletar. Requiere que "Places API" esté habilitada en el
 * proyecto de Google Cloud, aparte de Maps JavaScript API.
 *
 * En particular NO va 'drawing': el DrawingManager fue deprecado en agosto
 * 2025 y eliminado de la Maps JavaScript API en la v3.65 (junio 2026).
 * MapaDibujoPoligono resuelve el dibujo con los clics del mapa y un
 * google.maps.Polygon editable, que sí siguen soportados.
 */
export const GOOGLE_MAPS_LIBRARIES: Libraries = ["places"];

/** La key va por variable de entorno, nunca hardcodeada. */
export const GOOGLE_MAPS_API_KEY = import.meta.env.VITE_GOOGLE_MAPS_API_KEY ?? "";
