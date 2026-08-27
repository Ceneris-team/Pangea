/** HU12: helpers de rango de fechas compartidos por el selector y sus consumidores. */

export interface RangoFechas {
  inicio: string;
  fin: string;
}

/** Formatea un Date a "YYYY-MM-DDTHH:mm" (formato de <input type="datetime-local">, hora local). */
export function aValorDatetimeLocal(fecha: Date): string {
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${fecha.getFullYear()}-${pad(fecha.getMonth() + 1)}-${pad(fecha.getDate())}T${pad(fecha.getHours())}:${pad(fecha.getMinutes())}`;
}

/** CA: el rango por defecto al ingresar al módulo son las últimas 24 horas. */
export function rangoUltimas24Horas(): RangoFechas {
  const ahora = new Date();
  const hace24h = new Date(ahora.getTime() - 24 * 60 * 60 * 1000);
  return { inicio: aValorDatetimeLocal(hace24h), fin: aValorDatetimeLocal(ahora) };
}

/** HU14: los datos se almacenan en UTC; esto los convierte a la zona
 *  horaria configurada por el usuario (America/Lima por defecto) para
 *  mostrarlos en el módulo de consulta. */
export function formatearFechaHoraEnZona(iso: string, zonaHoraria: string): string {
  return new Date(iso).toLocaleString("es", { timeZone: zonaHoraria });
}
