/**
 * PP-68 - Consultar vencimientos: textos y reglas de la tabla, sin
 * interfaz, para probarlos con node --test. El filtro lo aplica el backend
 * (GET /comercial/vencimientos?rango=...); esto solo define las opciones y
 * cómo se muestra cada fila. Sin imports a propósito: node --test no
 * resuelve rutas sin extensión.
 */

/** "Los rangos de días disponibles son: vencidos, vencen hoy, próximos 7 días, próximos 30 días y todos." */
export const RANGOS_VENCIMIENTO = [
  { valor: "todos", texto: "Todos" },
  { valor: "vencidos", texto: "Vencidos" },
  { valor: "hoy", texto: "Vencen hoy" },
  { valor: "7", texto: "Próximos 7 días" },
  { valor: "30", texto: "Próximos 30 días" },
] as const;

export type RangoVencimiento = (typeof RANGOS_VENCIMIENTO)[number]["valor"];

export function esRango(valor: string | null): valor is RangoVencimiento {
  return RANGOS_VENCIMIENTO.some((rango) => rango.valor === valor);
}

export function diasRestantesTexto(dias: number): string {
  if (dias === 0) return "Vence hoy";
  if (dias === 1) return "1 día";
  if (dias > 1) return `${dias} días`;
  return dias === -1 ? "Venció hace 1 día" : `Venció hace ${-dias} días`;
}

function sumarDias(fecha: string, dias: number): string {
  const d = new Date(fecha + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + dias);
  return d.toISOString().slice(0, 10);
}

/**
 * "Renovar" abre Asignar plan (HU45). Si todavía no vence, la renovación
 * empieza el día siguiente al vencimiento (queda Programada y no se pierden
 * los días pagados); si ya venció, empieza hoy.
 */
export function inicioRenovacion(fechaVencimiento: string, hoy: string): string {
  const siguiente = sumarDias(fechaVencimiento, 1);
  return siguiente > hoy ? siguiente : hoy;
}
