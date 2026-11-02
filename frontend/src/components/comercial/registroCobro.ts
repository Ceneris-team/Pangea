/**
 * PP-67 - Registrar cobro: validación del formulario antes de llamar a
 * POST /comercial/clientes/{id}/cobros. Repite las reglas de
 * backend/app/services/cobros.py con los mismos mensajes; el backend sigue
 * siendo quien decide. Sin imports a propósito: node --test no resuelve
 * rutas sin extensión.
 */

export const METODOS_PAGO = ["Transferencia bancaria", "Efectivo", "Cheque"] as const;

export type DatosCobro = { monto: string; fecha_cobro: string; metodo_pago: string };
export type ErroresCobro = Partial<Record<keyof DatosCobro, string>>;

export const MSG_MONTO = "El monto cobrado debe ser un número mayor que 0 con hasta 2 decimales";
export const MSG_MONTO_MAXIMO = "El monto cobrado no puede superar 9 999 999 999.99";
export const MSG_FECHA = "Indica la fecha de cobro en formato AAAA-MM-DD";
export const MSG_FECHA_FUTURA = "La fecha de cobro no puede ser futura";
export const MSG_METODO = "Elige un método de pago: Transferencia bancaria, Efectivo o Cheque";

const MONTO = /^\d+(\.\d{1,2})?$/;
const FECHA = /^\d{4}-\d{2}-\d{2}$/;

/** Acepta coma o punto decimal ("350,50" o "350.50"), como se escribe en Perú. */
export function normalizarMonto(monto: string): string {
  return monto.trim().replace(",", ".");
}

export function validarCobro(datos: DatosCobro, hoy: string): ErroresCobro {
  const errores: ErroresCobro = {};
  const monto = normalizarMonto(datos.monto);
  if (!MONTO.test(monto) || Number(monto) <= 0) errores.monto = MSG_MONTO;
  else if (Number(monto) > 9999999999.99) errores.monto = MSG_MONTO_MAXIMO;
  if (!FECHA.test(datos.fecha_cobro)) errores.fecha_cobro = MSG_FECHA;
  else if (datos.fecha_cobro > hoy) errores.fecha_cobro = MSG_FECHA_FUTURA;
  if (!(METODOS_PAGO as readonly string[]).includes(datos.metodo_pago)) errores.metodo_pago = MSG_METODO;
  return errores;
}

export function cuerpoCobro(datos: DatosCobro) {
  return { monto: normalizarMonto(datos.monto), fecha_cobro: datos.fecha_cobro, metodo_pago: datos.metodo_pago };
}

/** Monto con separador de miles y 2 decimales, como lo muestra es-PE ("1250.5" → "1,250.50"). */
export function montoVisible(monto: string): string {
  const numero = Number(monto);
  return Number.isFinite(numero) ? numero.toLocaleString("es-PE", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) : monto;
}
