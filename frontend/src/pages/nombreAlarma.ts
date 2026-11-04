/**
 * HU28: "El nombre de la alarma acepta texto alfanumérico con un máximo de
 * 100 caracteres". Misma regla que backend/app/schemas_alarmas.py
 * (_RE_NOMBRE_ALARMA): empieza por letra o número y solo admite espacios y
 * la puntuación . , ; : _ ( ) - /. Se valida en el paso 1 para que un nombre
 * inválido no llegue hasta el GUARDAR del paso 2. Sin imports a propósito:
 * node --test no resuelve rutas sin extensión.
 */

export const MAX_NOMBRE_ALARMA = 100;
export const MSG_NOMBRE_OBLIGATORIO = "El nombre de la alarma es obligatorio";
export const MSG_NOMBRE_FORMATO =
  "El nombre de la alarma debe ser texto alfanumérico (se admiten espacios y los signos . , ; : _ ( ) - /)";
export const MSG_NOMBRE_LARGO = "El nombre de la alarma admite como máximo 100 caracteres";

const CARACTERES = "0-9A-Za-zÁÉÍÓÚÜÑáéíóúüñ";
const NOMBRE = new RegExp(`^[${CARACTERES}][${CARACTERES} .,;:_()\\-/]*$`);

/** Devuelve el mensaje de error, o null si el nombre es válido. */
export function errorNombreAlarma(nombre: string): string | null {
  const valor = nombre.trim();
  if (!valor) return MSG_NOMBRE_OBLIGATORIO;
  if (valor.length > MAX_NOMBRE_ALARMA) return MSG_NOMBRE_LARGO;
  if (!NOMBRE.test(valor)) return MSG_NOMBRE_FORMATO;
  return null;
}
