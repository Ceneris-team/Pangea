import { ROLES } from "./roles";

export function esCeneris(rol: string | null): boolean {
  return rol === ROLES.ADMINISTRADOR || rol === ROLES.TECNICO_CENERIS;
}

export function esAdministracion(path: string): boolean {
  return ["/panel-admin", "/panel-tecnico", "/usuarios", "/empresas", "/planes-suscripciones", "/clientes"]
    .some((ruta) => path === ruta || path.startsWith(ruta + "/"));
}

export function esModuloOperativo(path: string): boolean {
  return ["/entorno", "/ubicaciones", "/dispositivos", "/consulta-datos", "/graficos", "/mapa-estaciones",
    "/conexiones-ftp", "/parametros", "/cola-ingesta", "/paneles"]
    .some((ruta) => path === ruta || path.startsWith(ruta + "/"));
}
