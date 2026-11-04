/** La versión pertenece a la cuenta verificada, nunca al rol almacenado en la UI. */
export function leerVersionAcceso(storage: Pick<Storage, "getItem" | "removeItem">, usuario: string): string | null {
  try {
    const acceso: unknown = JSON.parse(storage.getItem("pangea_acceso") ?? "null");
    if (acceso && typeof acceso === "object" && "usuario" in acceso && "version" in acceso
      && acceso.usuario === usuario && typeof acceso.version === "string") {
      return acceso.version;
    }
    if (acceso && typeof acceso === "object" && "usuario" in acceso && acceso.usuario !== usuario) {
      storage.removeItem("pangea_aviso_acceso");
    }
  } catch { /* Un valor antiguo o corrupto requiere una nueva validación. */ }
  storage.removeItem("pangea_acceso");
  return null;
}

export function guardarVersionAcceso(storage: Pick<Storage, "setItem">, usuario: string, version: string): void {
  storage.setItem("pangea_acceso", JSON.stringify({ usuario, version }));
}
