/**
 * DEF-02 (PP-225): convierte el `detail` de una respuesta de error de la API
 * en un texto que se pueda mostrar.
 *
 * Los errores propios del backend (HTTPException) traen `detail` como texto,
 * pero un 422 de validación de FastAPI/Pydantic trae una LISTA de objetos
 * ({loc, msg, type, ...}). Pasar esa lista tal cual al mensaje de error
 * mostraba "[object Object]" en pantalla. Sin imports a propósito: node
 * --test no resuelve rutas sin extensión.
 */

export const MENSAJE_GENERICO = "Ocurrió un error inesperado";

type ErrorDeValidacion = { msg?: unknown };

function limpiar(msg: string): string {
  // Pydantic antepone "Value error, " a los ValueError de los validadores.
  return msg.replace(/^Value error,\s*/i, "").trim();
}

export function mensajeDeDetalle(detalle: unknown): string {
  if (typeof detalle === "string") return detalle.trim() || MENSAJE_GENERICO;
  if (Array.isArray(detalle)) {
    const mensajes = detalle
      .map((item) => (typeof item === "string" ? item : (item as ErrorDeValidacion)?.msg))
      .filter((msg): msg is string => typeof msg === "string" && msg.trim() !== "")
      .map(limpiar);
    const unicos = [...new Set(mensajes)];
    return unicos.length ? unicos.join(". ") : MENSAJE_GENERICO;
  }
  if (detalle && typeof detalle === "object" && typeof (detalle as ErrorDeValidacion).msg === "string") {
    return limpiar((detalle as { msg: string }).msg) || MENSAJE_GENERICO;
  }
  return MENSAJE_GENERICO;
}
