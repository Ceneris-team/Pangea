/**
 * HU 65 - Registrar cliente: validación del formulario antes de llamar a
 * POST /comercial/clientes. Repite las reglas de backend/app/services/clientes.py
 * (con los mismos mensajes) para avisar junto a cada campo sin esperar al
 * servidor; el backend sigue siendo quien decide, incluido el RUC repetido.
 */

export type DatosCliente = {
  razon_social: string;
  ruc: string;
  correo_contacto: string;
  telefono_contacto: string;
};

export type ErroresCliente = Partial<Record<keyof DatosCliente, string>>;

export const CLIENTE_VACIO: DatosCliente = { razon_social: "", ruc: "", correo_contacto: "", telefono_contacto: "" };

export const MSG_RAZON_SOCIAL = "La razón social es obligatoria";
export const MSG_RUC = "El RUC debe tener exactamente 11 dígitos numéricos";
export const MSG_CORREO = "El correo de contacto debe tener el formato usuario@dominio.com";
export const MSG_TELEFONO = "El teléfono de contacto solo admite números, espacios, + y - (máximo 20 caracteres)";

const RUC = /^\d{11}$/;
const CORREO = /^[^@\s]+@[^@\s.]+(\.[^@\s.]+)+$/;
const TELEFONO = /^[0-9+\- ]{1,20}$/;

export function validarCliente(datos: DatosCliente): ErroresCliente {
  const errores: ErroresCliente = {};
  const razon = datos.razon_social.trim();
  if (!razon) errores.razon_social = MSG_RAZON_SOCIAL;
  if (!RUC.test(datos.ruc.trim())) errores.ruc = MSG_RUC;
  const correo = datos.correo_contacto.trim();
  if (correo.length > 150 || !CORREO.test(correo)) errores.correo_contacto = MSG_CORREO;
  const telefono = datos.telefono_contacto.trim();
  if (telefono && !(TELEFONO.test(telefono) && /\d/.test(telefono))) errores.telefono_contacto = MSG_TELEFONO;
  return errores;
}

/** Cuerpo para la API: sin espacios sobrantes y el teléfono vacío como null (es opcional). */
export function cuerpoCliente(datos: DatosCliente) {
  return {
    razon_social: datos.razon_social.trim(),
    ruc: datos.ruc.trim(),
    correo_contacto: datos.correo_contacto.trim(),
    telefono_contacto: datos.telefono_contacto.trim() || null,
  };
}
