import type { RangoFechas } from "../utils/fechas";

/**
 * Tipos, constantes y funciones puras de la vista de Gráficos (HU15),
 * separados de Graficos.tsx a propósito: ese archivo mezclaba estas
 * funciones sueltas con los componentes React (Graficos,
 * GraficoDeParametro), y un módulo que mezcla componentes con
 * no-componentes rompe el "Fast Refresh boundary" de React/Vite -en dev,
 * el HMR puede terminar aplicando una edición a medias y dejar el
 * navegador ejecutando una mezcla de código viejo y nuevo hasta el
 * próximo refresh completo (visto en vivo: un TypeError en una firma de
 * función que en el archivo real ya no existía, seguido de un
 * "An error occurred in the <Graficos> component" que tumbaba toda la
 * pantalla). Nada de esto afecta producción -ahí no hay HMR-, pero
 * conviene evitarlo mientras el archivo sigue en cambio.
 */

export interface ParametroItem {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  tipo_dato: string;
}

export interface UbicacionItem {
  id_ubccn: number;
  nmbr: string;
}

// Una Ubicación puede tener más de un Dispositivo (dos dataloggers
// midiendo el mismo parámetro en la misma estación, caso real). El
// filtro de dataloggers deja aislar la serie de uno solo cuando eso pasa.
export interface DispositivoItem {
  id_dspstv: number;
  nmbr: string;
  ubicacion_nombre: string;
}

export interface MedicionItem {
  id_registro: number;
  fch_hr: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  // Una Ubicación puede tener más de un Dispositivo (dos dataloggers
  // midiendo el mismo parámetro en la misma estación, caso real y no
  // hipotético). Sin distinguir por dispositivo, agrupar solo por
  // ubicación mezclaba sus lecturas en una sola línea.
  id_dspstv: number;
  dispositivo_nombre: string;
  id_prmtr: number;
  parametro_nombre: string;
  undd: string;
  vlr: number | string;
}

export interface ListadoMediciones {
  /** Puntos que existen para la consulta, no los que vinieron en `items`:
   *  la respuesta está paginada, así que `total > items.length` significa
   *  que las series se están dibujando incompletas. */
  total: number;
  /** HT-10 CA3: true si el backend muestreó la serie por rango amplio. */
  downsampling?: boolean;
  total_sin_muestrear?: number;
  items: MedicionItem[];
}

// Solo los registros con valor numérico son graficables (línea/área); los
// de tipo texto (evnt_txt) se filtran antes de agrupar por parámetro.
export type MedicionNumerica = MedicionItem & { vlr: number };

export type TipoGrafico = "linea" | "area";
export type Vista = "grafico" | "tabla";

export interface HoverInfo {
  parametroId: number;
  x: number;
  y: number;
  item: MedicionNumerica;
}

// Paleta categórica validada para fondo oscuro (dataviz skill): azul,
// naranja, aqua, amarillo — en ese orden fijo, nunca por índice aleatorio.
export const COLORES_SERIE = ["#3987e5", "#d95926", "#199e70", "#c98500"];

// HU15/HU14: los datos se almacenan en UTC y se muestran en la zona
// horaria configurada por el usuario.
export function formatearFechaCorta(iso: string, zonaHoraria: string): string {
  return new Date(iso).toLocaleString("es", {
    timeZone: zonaHoraria,
    day: "2-digit",
    month: "short",
    hour: "2-digit",
    minute: "2-digit",
  });
}

// Puntos que se piden POR PARÁMETRO seleccionado. GET /mediciones pagina
// sobre la UNIÓN de todas las series, no por parámetro: sin pedir un
// por_pagina acorde, el default del backend (50 filas) se reparte entre
// todos los gráficos y cada serie queda con una fracción -con 5
// parámetros, ~8 puntos cada uno, que es el bug de "el gráfico muestra 5
// mediciones cuando agrego más gráficos"-. Se escala con la cantidad de
// parámetros para que cada serie conserve su resolución.
export const PUNTOS_POR_PARAMETRO = 500;

// Topes duros del endpoint (mediciones.py): por_pagina <= 5000 y
// max_puntos <= 50000. Pedir por encima devuelve 422, así que se acotan
// acá en vez de dejar que la petición falle.
export const TOPE_POR_PAGINA = 5000;
export const TOPE_MAX_PUNTOS = 50000;

export function construirQuery(
  parametroIds: number[],
  ubicacionIds: number[],
  dispositivoIds: number[],
  rangoFechas: RangoFechas | null,
): string {
  const params = new URLSearchParams();
  parametroIds.forEach((id) => params.append("parametro_ids", String(id)));
  ubicacionIds.forEach((id) => params.append("ubicacion_ids", String(id)));
  dispositivoIds.forEach((id) => params.append("dispositivo_ids", String(id)));
  if (rangoFechas) {
    params.append("fecha_inicio", new Date(rangoFechas.inicio).toISOString());
    params.append("fecha_fin", new Date(rangoFechas.fin).toISOString());
  }

  const seriesPedidas = Math.max(parametroIds.length, 1);
  const puntosDeseados = seriesPedidas * PUNTOS_POR_PARAMETRO;
  params.append("por_pagina", String(Math.min(puntosDeseados, TOPE_POR_PAGINA)));
  // El downsampling del backend (rangos >30 días) recorta al mismo tope,
  // así que se pide explícito: su default (2000) es para la tabla de
  // HU12, y acá el reparto entre series necesita más margen.
  params.append("max_puntos", String(Math.min(puntosDeseados, TOPE_MAX_PUNTOS)));

  return `/mediciones?${params.toString()}`;
}

// CA: 1-3 parámetros seleccionados -> una columna; 4-6 -> dos columnas;
// 7 o más -> tres columnas en pantallas grandes. El CA original solo
// contemplaba hasta 8 parámetros, pero el selector no limita cuántos se
// pueden marcar, así que el último tramo cubre cualquier cantidad.
export function claseColumnasGrilla(cantidad: number): string {
  if (cantidad <= 3) return "grid-cols-1";
  if (cantidad <= 6) return "grid-cols-1 md:grid-cols-2";
  return "grid-cols-1 md:grid-cols-2 lg:grid-cols-3";
}

/**
 * Convierte una lista de puntos en un path SVG suavizado con interpolación
 * cúbica monótona (Fritsch-Carlson, la misma familia que D3 curveMonotoneX
 * o Chart.js con tensión monótona): a diferencia de un spline Catmull-Rom
 * -que se probó antes y se descartó-, esta variante limita la tangente en
 * cada punto para que la curva nunca "overshoot" ni ondule entre dos
 * mediciones consecutivas. Es decir, entre dos puntos la curva siempre se
 * mantiene dentro del rango de valores que ellos definen, así que no
 * dibuja una subida o bajada que el usuario pueda leer como una medición
 * intermedia inexistente -eso sí pasaba con Catmull-Rom, y también con un
 * primer intento de redondear solo las esquinas: la asimetría entre
 * segmentos de pendiente muy distinta metía un quiebre visible junto al
 * punto en vez de una curva limpia-.
 */
export function pathDeLinea(puntos: { x: number; y: number }[]): string {
  const n = puntos.length;
  if (n === 0) return "";
  if (n <= 2) {
    return puntos.map((p, i) => `${i === 0 ? "M" : "L"} ${p.x},${p.y}`).join(" ");
  }

  // Pendiente de cada segmento consecutivo.
  const pendientes: number[] = [];
  for (let i = 0; i < n - 1; i++) {
    const dx = puntos[i + 1].x - puntos[i].x;
    pendientes.push(dx === 0 ? 0 : (puntos[i + 1].y - puntos[i].y) / dx);
  }

  // Tangente en cada punto: promedio de las pendientes vecinas, pero
  // puesta a cero en cualquier punto donde la serie cambia de dirección
  // (mínimo o máximo local) -ahí es exactamente donde Catmull-Rom se
  // pasaba de largo- y limitada (paso de Fritsch-Carlson) para que ningún
  // segmento se curve más allá del rango [min, max] de sus dos extremos.
  const tangentes: number[] = new Array(n).fill(0);
  for (let i = 1; i < n - 1; i++) {
    const m0 = pendientes[i - 1];
    const m1 = pendientes[i];
    tangentes[i] = m0 * m1 <= 0 ? 0 : (m0 + m1) / 2;
  }
  tangentes[0] = pendientes[0];
  tangentes[n - 1] = pendientes[n - 2];

  for (let i = 0; i < n - 1; i++) {
    const m = pendientes[i];
    if (m === 0) {
      tangentes[i] = 0;
      tangentes[i + 1] = 0;
      continue;
    }
    const a = tangentes[i] / m;
    const b = tangentes[i + 1] / m;
    const s = Math.hypot(a, b);
    if (s > 3) {
      const factor = 3 / s;
      tangentes[i] = a * factor * m;
      tangentes[i + 1] = b * factor * m;
    }
  }

  let d = `M ${puntos[0].x},${puntos[0].y}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = puntos[i];
    const p1 = puntos[i + 1];
    const dx = (p1.x - p0.x) / 3;
    const c1x = p0.x + dx;
    const c1y = p0.y + tangentes[i] * dx;
    const c2x = p1.x - dx;
    const c2y = p1.y - tangentes[i + 1] * dx;
    d += ` C ${c1x},${c1y} ${c2x},${c2y} ${p1.x},${p1.y}`;
  }
  return d;
}
