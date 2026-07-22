/**
 * HU 01 - Iniciar sesión
 * CA: "cada uno [rol] es redirigido a su panel correspondiente al ingresar."
 *
 * Este mapeo centraliza a dónde va cada rol tras el login. Si mañana se
 * agrega un rol nuevo, solo se toca este archivo (y se crea la ruta).
 */
export const ROLES = {
  ADMINISTRADOR: "Administrador",
  TECNICO_CENERIS: "Técnico CENERIS",
  CLIENTE_FINAL: "Cliente Final",
  ADMINISTRADOR_COMERCIAL: "Administrador Comercial",
} as const;

export type RolNombre = (typeof ROLES)[keyof typeof ROLES];

export const RUTA_POR_ROL: Record<string, string> = {
  [ROLES.ADMINISTRADOR]: "/panel-admin",
  [ROLES.TECNICO_CENERIS]: "/panel-tecnico",
  [ROLES.CLIENTE_FINAL]: "/panel-cliente",
  [ROLES.ADMINISTRADOR_COMERCIAL]: "/panel-comercial",
};

export function rutaPorRol(rol: string): string {
  return RUTA_POR_ROL[rol] ?? "/login";
}
