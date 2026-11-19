/**
 * HU29 (PP-74) - Condición de la alarma: operador + valor umbral.
 *
 * Mismas reglas que backend/app/schemas_alarmas.py (CondicionAlarmaCrear):
 * el operador es uno de los 5 del CHECK de cndcn_alrm y el umbral es un
 * número finito de hasta 4 decimales dentro de Numeric(14,4). Validar acá es
 * comodidad de la pantalla; la garantía es el backend.
 *
 * v1.0: una condición por alarma (Diccionario de Datos, CONDICION_ALARMA).
 * Sin imports a propósito: node --test no resuelve rutas sin extensión.
 */

export const OPERADORES_ALARMA = [
  { valor: ">", texto: "mayor que" },
  { valor: ">=", texto: "mayor o igual que" },
  { valor: "<", texto: "menor que" },
  { valor: "<=", texto: "menor o igual que" },
  { valor: "=", texto: "igual a" },
] as const;

export type OperadorAlarma = (typeof OPERADORES_ALARMA)[number]["valor"];

export const DECIMALES_UMBRAL = 4;
export const UMBRAL_MAXIMO = 9999999999.9999;

export const MSG_UMBRAL_OBLIGATORIO = "El valor umbral es obligatorio";
export const MSG_UMBRAL_NUMERO = "El valor umbral debe ser un número";
export const MSG_UMBRAL_RANGO =
  "El valor umbral debe estar entre -9999999999.9999 y 9999999999.9999";
export const MSG_UMBRAL_DECIMALES = `El valor umbral admite hasta ${DECIMALES_UMBRAL} decimales`;
export const MSG_OPERADOR = "Elige el operador de la condición";

/** Número escrito como lo acepta el backend: signo opcional, dígitos y un
 *  punto decimal opcional. Se admite la coma decimal y se convierte. */
const NUMERO = /^[+-]?(\d+(\.\d*)?|\.\d+)$/;

/** Normaliza lo tecleado ("  12,5 " → "12.5"). */
export function normalizarUmbral(texto: string): string {
  return texto.trim().replace(",", ".");
}

/** Mensaje de error del umbral, o null si es válido. */
export function errorUmbral(texto: string): string | null {
  const valor = normalizarUmbral(texto);
  if (!valor) return MSG_UMBRAL_OBLIGATORIO;
  if (!NUMERO.test(valor)) return MSG_UMBRAL_NUMERO;
  const decimales = valor.includes(".") ? valor.split(".")[1].length : 0;
  if (decimales > DECIMALES_UMBRAL) return MSG_UMBRAL_DECIMALES;
  if (Math.abs(Number(valor)) > UMBRAL_MAXIMO) return MSG_UMBRAL_RANGO;
  return null;
}

export function esOperadorValido(valor: string): valor is OperadorAlarma {
  return OPERADORES_ALARMA.some((o) => o.valor === valor);
}

export function textoOperador(valor: string): string {
  return OPERADORES_ALARMA.find((o) => o.valor === valor)?.texto ?? valor;
}

/** Umbral para mostrar: sin ceros de relleno (30.5000 → "30.5"). */
export function formatearUmbral(valor: number | string): string {
  const numero = typeof valor === "number" ? valor : Number(normalizarUmbral(valor));
  if (!Number.isFinite(numero)) return String(valor);
  return String(Number(numero.toFixed(DECIMALES_UMBRAL)));
}

/**
 * Frase de vista previa: "Se activará cuando Temperatura sea mayor que 30 °C".
 * Devuelve null mientras la condición no esté completa y válida.
 */
export function fraseCondicion(
  parametro: string,
  operador: string,
  umbral: string,
  unidad?: string | null,
): string | null {
  if (!parametro || !esOperadorValido(operador) || errorUmbral(umbral)) return null;
  const valor = formatearUmbral(umbral);
  const sufijo = unidad && unidad.trim() ? ` ${unidad.trim()}` : "";
  return `Se activará cuando ${parametro} sea ${textoOperador(operador)} ${valor}${sufijo}`;
}

/** Cuerpo para el backend ({oprdr, vlr_umbrl}); usar solo tras validar. */
export function condicionParaEnviar(operador: OperadorAlarma, umbral: string) {
  return { oprdr: operador, vlr_umbrl: Number(normalizarUmbral(umbral)) };
}
