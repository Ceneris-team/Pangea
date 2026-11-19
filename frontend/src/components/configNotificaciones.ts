/**
 * HU30 (PP-75 / PP-231): textos del panel "Configurar notificaciones".
 * Sin imports a propósito: node --test no resuelve rutas sin extensión.
 */

export const MENSAJE_GUARDADO = "Notificaciones configuradas correctamente";

export interface CanalNotificacion {
  canal: string;
  nombre: string;
  disponible: boolean;
  activo: boolean;
}

/** Qué va a pasar con el canal de correo según el estado elegido (aún sin
 *  guardar), para que GUARDAR no sorprenda a nadie. */
export function ayudaCanalCorreo(
  activo: boolean,
  cantidadDestinatarios: number,
  correoCuenta: string,
): string {
  if (!activo) {
    return cantidadDestinatarios > 0
      ? "Desactivado: los destinatarios se conservan, pero no recibirán avisos de esta alarma."
      : "Desactivado: esta alarma no enviará avisos por correo.";
  }
  if (cantidadDestinatarios === 0) {
    return `Activo: al guardar se agregará el correo de tu cuenta (${correoCuenta}) como destinatario.`;
  }
  const plural = cantidadDestinatarios === 1 ? "destinatario recibirá" : "destinatarios recibirán";
  return `Activo: ${cantidadDestinatarios} ${plural} un aviso cuando la condición se cumpla.`;
}

/** Texto del estado de un canal en la lista. */
export function estadoCanal(canal: CanalNotificacion): string {
  if (!canal.disponible) return "No disponible en esta versión";
  return canal.activo ? "Activo" : "Desactivado";
}
