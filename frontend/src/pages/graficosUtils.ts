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

/** Cómo se dibuja la serie, independiente de dónde se persiste (eso lo
 *  decide tipo_dato). Ver prmtr.tipo_visualizacion en el backend. */
export type TipoVisualizacion = "continuo" | "contador" | "estado";

export interface ParametroItem {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  tipo_dato: string;
  /** Opcional: un backend sin la migración aplicada no lo manda, y ahí
   *  todo se comporta como antes ('continuo'). */
  tipo_visualizacion?: TipoVisualizacion;
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
  next_cursor?: string | null;
  items: MedicionItem[];
}

// Solo los registros con valor numérico son graficables (línea/área); los
// de tipo texto (evnt_txt) se filtran antes de agrupar por parámetro.
export type MedicionNumerica = MedicionItem & { vlr: number };

export type TipoGrafico = "linea" | "area";
export type Vista = "grafico" | "tabla";

export interface HoverInfo {
  serieId?: number;
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

/**
 * Trazo en escalón: mantiene el valor constante hasta la medición
 * siguiente y solo ahí sube. Es la forma correcta para un contador
 * acumulativo -entre dos lecturas el contador NO creció de a poco, se
 * quedó quieto y saltó cuando ocurrió el evento-, mientras que la
 * spline de pathDeLinea inventa una rampa suave que sugiere un flujo
 * continuo que nunca existió.
 */
export function pathDeEscalon(puntos: { x: number; y: number }[]): string {
  if (puntos.length === 0) return "";
  let d = `M ${puntos[0].x},${puntos[0].y}`;
  for (let i = 1; i < puntos.length; i++) {
    d += ` L ${puntos[i].x},${puntos[i - 1].y} L ${puntos[i].x},${puntos[i].y}`;
  }
  return d;
}

export interface TileResumen {
  etiqueta: string;
  valor: string;
}

/**
 * Los cuatro tiles de arriba del gráfico, según qué representa la serie.
 * Un contador acumulativo y un estado binario comparten el tipo de dato
 * numérico con una medición ambiental, pero min/promedio/máximo solo
 * significa algo para la última: el promedio de una cuenta corrida es el
 * promedio de un número que solo sube, y el de un 0/1 es un porcentaje
 * disfrazado de magnitud.
 */
export function tilesDeResumen(
  seriesDeValores: number[][],
  unidad: string,
  tipo: TipoVisualizacion,
): TileResumen[] {
  // Los contadores y los estados se leen POR dispositivo: dos dataloggers
  // llevan cada uno su propia cuenta, y concatenarlas hace que el salto
  // entre una y otra se lea como un incremento gigante que nunca ocurrió.
  // Para 'continuo' da igual -min/promedio/máximo de la unión es lo que
  // se venía mostrando-, pero se arma igual desde las series para tener
  // una sola forma de entrada.
  const valores = seriesDeValores.flat();

  if (valores.length === 0) {
    return [
      { etiqueta: "Mediciones", valor: "—" },
      { etiqueta: "Mínimo", valor: "—" },
      { etiqueta: "Promedio", valor: "—" },
      { etiqueta: "Máximo", valor: "—" },
    ];
  }

  const cantidad = valores.length;
  const cantidadTxt = cantidad.toLocaleString("es");
  // La unidad real de un contador son "eventos" y la de un estado no
  // existe; el catálogo las tiene como 'N/A' (ver seed_dispositivos_demo)
  // y arrastrar ese literal a un tile solo mete ruido.
  const sufijo = unidad && unidad !== "N/A" ? ` ${unidad}` : "";

  // Series con al menos un dato, cada una ya ordenada cronológicamente
  // por quien llama.
  const seriesConDatos = seriesDeValores.filter((s) => s.length > 0);

  if (tipo === "contador") {
    // Un contador puede reiniciarse (reemplazo del equipo, corte de
    // energía). Sumar solo los incrementos positivos evita que un reset
    // reporte un delta negativo sin sentido.
    let acumulado = 0;
    for (const serie of seriesConDatos) {
      for (let i = 1; i < serie.length; i++) {
        const delta = serie[i] - serie[i - 1];
        if (delta > 0) acumulado += delta;
      }
    }
    // Con varios dispositivos no existe UN valor inicial ni UNO actual:
    // cada uno lleva su cuenta. Se suman, que es la lectura útil ("cuánto
    // marcan entre todos"), y el detalle por dispositivo ya está en el
    // gráfico, con una línea por serie.
    const inicial = seriesConDatos.reduce((acc, s) => acc + s[0], 0);
    const actual = seriesConDatos.reduce((acc, s) => acc + s[s.length - 1], 0);
    return [
      { etiqueta: "Lecturas", valor: cantidadTxt },
      { etiqueta: "Inicial", valor: inicial.toLocaleString("es") },
      { etiqueta: "Actual", valor: actual.toLocaleString("es") },
      { etiqueta: "Incremento", valor: `+${acumulado.toLocaleString("es")}` },
    ];
  }

  if (tipo === "estado") {
    // "Activo" = cualquier valor distinto de 0, sin asumir que el estado
    // se codifica exactamente como 1: basta con que 0 sea el reposo.
    const activas = valores.filter((v) => v !== 0).length;
    let transiciones = 0;
    for (const serie of seriesConDatos) {
      for (let i = 1; i < serie.length; i++) {
        if ((serie[i] !== 0) !== (serie[i - 1] !== 0)) transiciones++;
      }
    }
    const porcentaje = (activas / cantidad) * 100;
    const ultimoActivo = seriesConDatos.some((s) => s[s.length - 1] !== 0);
    return [
      { etiqueta: "Lecturas", valor: cantidadTxt },
      { etiqueta: "Activo", valor: `${porcentaje.toFixed(1)} %` },
      { etiqueta: "Transiciones", valor: transiciones.toLocaleString("es") },
      { etiqueta: "Estado actual", valor: ultimoActivo ? "Activo" : "Inactivo" },
    ];
  }

  const suma = valores.reduce((acc, v) => acc + v, 0);
  return [
    { etiqueta: "Mediciones", valor: cantidadTxt },
    { etiqueta: "Mínimo", valor: `${Math.min(...valores).toFixed(2)}${sufijo}` },
    { etiqueta: "Promedio", valor: `${(suma / cantidad).toFixed(2)}${sufijo}` },
    { etiqueta: "Máximo", valor: `${Math.max(...valores).toFixed(2)}${sufijo}` },
  ];
}

/** Ancho del bucket de las barras de delta, elegido según el rango visible. */
export type IntervaloDelta = "hora" | "dia" | "semana" | "mes";

const MS_HORA = 3_600_000;
const MS_DIA = 24 * MS_HORA;

/**
 * Bucket que deja una cantidad de barras legible (~15-45) para el rango
 * que se está mirando. Sin esto, un rango de un año agrupado por hora
 * daría ~8760 barras de menos de un píxel, y un rango de un día agrupado
 * por mes daría una sola.
 */
export function intervaloParaRango(rangoMs: number): IntervaloDelta {
  if (rangoMs <= 2 * MS_DIA) return "hora";
  if (rangoMs <= 45 * MS_DIA) return "dia";
  if (rangoMs <= 300 * MS_DIA) return "semana";
  return "mes";
}

/**
 * Inicio del bucket al que cae `t`, en la zona horaria de visualización.
 * Importa que sea esa y no UTC: si un día empieza a las 00:00 UTC, en
 * America/Lima las barras quedarían cortadas a las 19:00 del día anterior
 * y "los eventos del martes" incluirían parte del lunes.
 */
export function inicioDeBucket(t: number, intervalo: IntervaloDelta, zonaHoraria: string): number {
  // Partes del instante YA en la zona del usuario, para truncar sobre
  // ellas en vez de sobre UTC.
  const fmt = new Intl.DateTimeFormat("en-CA", {
    timeZone: zonaHoraria,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false,
  });
  const p: Record<string, string> = {};
  for (const parte of fmt.formatToParts(new Date(t))) {
    if (parte.type !== "literal") p[parte.type] = parte.value;
  }
  // El offset real de ESE instante (no el de hoy): así el truncado sigue
  // siendo correcto si la zona tuvo un cambio de horario en el rango.
  const comoUtc = Date.UTC(
    Number(p.year),
    Number(p.month) - 1,
    Number(p.day),
    Number(p.hour === "24" ? "0" : p.hour),
    Number(p.minute),
    Number(p.second),
  );
  const offset = comoUtc - Math.floor(t / 1000) * 1000;

  const anio = Number(p.year);
  const mes = Number(p.month) - 1;
  const dia = Number(p.day);
  const hora = Number(p.hour === "24" ? "0" : p.hour);

  if (intervalo === "hora") return Date.UTC(anio, mes, dia, hora) - offset;
  if (intervalo === "dia") return Date.UTC(anio, mes, dia) - offset;
  if (intervalo === "mes") return Date.UTC(anio, mes, 1) - offset;
  // Semana: se ancla al lunes, que es el inicio de semana de la configuración
  // regional del proyecto (es-PE).
  const diaSemana = new Date(Date.UTC(anio, mes, dia)).getUTCDay();
  const diasDesdeLunes = (diaSemana + 6) % 7;
  return Date.UTC(anio, mes, dia - diasDesdeLunes) - offset;
}

export interface BarraDelta {
  /** Inicio del bucket, en ms epoch. */
  t: number;
  /** Eventos ocurridos dentro del bucket. */
  delta: number;
}

/**
 * Convierte una serie acumulativa en los eventos ocurridos por intervalo.
 *
 * Un contador acumulativo responde "en qué número va"; lo que casi
 * siempre se quiere saber de él es "cuántas veces pasó esto hoy", y eso
 * es la diferencia entre lecturas consecutivas agrupada por tiempo.
 *
 * Los deltas negativos se descartan en vez de restarse: un contador que
 * baja no registró eventos negativos, se reinició (reemplazo de equipo,
 * corte de energía), y contarlo como -22.000 eventos ensuciaría el
 * bucket entero.
 */
export function barrasDeDelta(
  items: { fch_hr: string; vlr: number }[],
  intervalo: IntervaloDelta,
  zonaHoraria: string,
): BarraDelta[] {
  if (items.length < 2) return [];
  const ordenados = [...items].sort(
    (a, b) => new Date(a.fch_hr).getTime() - new Date(b.fch_hr).getTime(),
  );

  const porBucket = new Map<number, number>();
  for (let i = 1; i < ordenados.length; i++) {
    const delta = ordenados[i].vlr - ordenados[i - 1].vlr;
    if (delta <= 0) continue;
    // El evento se atribuye al bucket de la lectura que lo reporta.
    const t = new Date(ordenados[i].fch_hr).getTime();
    const bucket = inicioDeBucket(t, intervalo, zonaHoraria);
    porBucket.set(bucket, (porBucket.get(bucket) ?? 0) + delta);
  }

  return [...porBucket.entries()]
    .map(([t, delta]) => ({ t, delta }))
    .sort((a, b) => a.t - b.t);
}

const ETIQUETA_INTERVALO: Record<IntervaloDelta, string> = {
  hora: "por hora",
  dia: "por día",
  semana: "por semana",
  mes: "por mes",
};

export function etiquetaDeIntervalo(intervalo: IntervaloDelta): string {
  return ETIQUETA_INTERVALO[intervalo];
}
