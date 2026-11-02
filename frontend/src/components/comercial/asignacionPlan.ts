/**
 * HU 45 - Asignar plan a cliente: reglas del formulario, sin interfaz, para
 * probarlas con node --test. El backend (POST /comercial/clientes/{id}/plan)
 * calcula el vencimiento y valida de nuevo; esto solo lo muestra antes de
 * confirmar. Sin imports a propósito: node --test no resuelve rutas sin extensión.
 */

export const DIAS_VIGENCIA_PLAN = 30;
export const MSG_ELEGIR_PLAN = "Selecciona un plan";
export const MSG_FECHA_INICIO = "Indica la fecha de inicio de la suscripción";
export const MSG_FECHA_PASADA = "La fecha de inicio no puede ser anterior a hoy";

type PlanAsignable = { id_pln: number; estado: string; limites: unknown | null };

/** "El selector de planes muestra únicamente los planes con estado Activo." */
export function planesActivos<T extends PlanAsignable>(planes: T[]): T[] {
  return planes.filter((plan) => plan.estado === "Activo");
}

/** Un plan activo sin límites existe, pero el contrato lo rechaza: se muestra deshabilitado. */
export function planSinLimites(plan: PlanAsignable): boolean {
  return plan.limites === null;
}

/** "La fecha de vencimiento se calcula sumando 30 días calendario a la fecha de inicio." */
export function vencimientoPlan(fechaInicio: string): string {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(fechaInicio)) return "";
  const fecha = new Date(fechaInicio + "T12:00:00Z");
  fecha.setUTCDate(fecha.getUTCDate() + DIAS_VIGENCIA_PLAN);
  return fecha.toISOString().slice(0, 10);
}

/** AAAA-MM-DD a DD/MM/AAAA, como se muestran las fechas en la pantalla. */
export function fechaVisible(fecha: string | null | undefined): string {
  if (!fecha || !/^\d{4}-\d{2}-\d{2}/.test(fecha)) return "—";
  const [anio, mes, dia] = fecha.slice(0, 10).split("-");
  return `${dia}/${mes}/${anio}`;
}

export function validarAsignacion(planId: string, fechaInicio: string, hoy: string): { plan?: string; fecha?: string } {
  const errores: { plan?: string; fecha?: string } = {};
  if (!planId) errores.plan = MSG_ELEGIR_PLAN;
  if (!fechaInicio) errores.fecha = MSG_FECHA_INICIO;
  else if (fechaInicio < hoy) errores.fecha = MSG_FECHA_PASADA;
  return errores;
}
