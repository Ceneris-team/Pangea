import type { ConfigSerie } from "../components/configuracionSerieUtils";
import type { MedicionNumerica } from "./graficosUtils";

export interface SerieTelemetria {
  id_serie: number;
  id_dspstv: number;
  dispositivo_nombre: string;
  id_prmtr: number;
  parametro_nombre: string;
  undd: string;
  id_ubccn: number;
  ubicacion_nombre: string;
  tp_trm: string;
  indc_clmn: number;
  configuracion: ConfigSerie;
}

export interface DatosSerie {
  items: MedicionNumerica[];
  muestreado: boolean;
  resumen: {
    minimo: number | null;
    maximo: number | null;
    promedio: number | null;
    valor: number | null;
    ultimo: number | null;
    lecturas: number;
    duplicados: number;
    parcial: boolean;
    reinicios: number;
    saltos_secuencia: number;
    ultima_lectura: string | null;
    sin_origen: boolean;
    intervalo: "hora" | "dia" | "mes";
    barras: { t: number; t_fin: number; delta: number }[];
  };
}

export function colorDatalogger(id: number): string {
  return `hsl(${(id * 137.508) % 360} 65% 52%)`;
}

export interface FuenteSerie {
  serie: SerieTelemetria;
  datos: DatosSerie;
}

/** Comparar únicamente la misma magnitud y significado. Los encabezados
 * ambiguos conservan su fuente hasta que se confirme su clasificación. */
export function agruparSeriesComparables(series: SerieTelemetria[]) {
  const grupos = new Map<string, SerieTelemetria[]>();
  for (const serie of series) {
    const significado = serie.configuracion.significado;
    const clave = JSON.stringify([serie.id_ubccn, serie.id_prmtr, serie.undd.trim(), significado,
      significado === "desconocido" ? serie.id_serie : null]);
    const grupo = grupos.get(clave) ?? [];
    grupo.push(serie);
    grupos.set(clave, grupo);
  }
  return [...grupos].map(([clave, series]) => ({ clave, series }));
}

export function nombreFuente(serie: SerieTelemetria): string {
  return `${serie.dispositivo_nombre} · ${serie.tp_trm}`;
}
