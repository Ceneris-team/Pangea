/**
 * Envoltorio único sobre fetch para toda la app.
 *
 * Por qué existe: sin esto, cada página tendría que repetir la URL base.
 * Centralizarlo aquí evita que alguien olvide `credentials: "include"` en
 * un endpoint nuevo (HT-04/HT-09 exigen sesión en cada endpoint
 * protegido).
 *
 * SESIÓN POR COOKIE HTTPONLY (no localStorage/JS): el backend setea la
 * sesión como cookie httpOnly en el login (ver Set-Cookie en
 * routers/auth.py). El navegador la adjunta solo en cada request; acá no
 * hay ningún token que leer ni mandar a mano. `credentials: "include"` es
 * el único requisito, y es obligatorio porque pangea-api vive en un
 * dominio DISTINTO al del frontend (Container Service o CloudFront):
 * sin esto, el navegador no manda cookies en requests cross-origin aunque
 * la cookie exista.
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

/** Claves de UI que AuthContext guarda junto a la sesión (rol, nombre,
 *  etc. - nunca el JWT, que vive solo en la cookie httpOnly). Un solo
 *  lugar para la lista: AuthContext.logout() y el interceptor de 401 de
 *  acá abajo tienen que borrar exactamente las mismas. */
export const CLAVES_SESION_UI = [
  "pangea_rol",
  "pangea_nombre",
  "pangea_debe_cambiar",
  "pangea_zona_horaria",
] as const;

export function limpiarDatosDeSesion(): void {
  CLAVES_SESION_UI.forEach((key) => {
    localStorage.removeItem(key);
    sessionStorage.removeItem(key);
  });
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

interface ApiOptions {
  method?: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  body?: unknown;
  params?: Record<string, string | number | undefined>;
  /** true para saltear el interceptor de 401 (limpiar storage + redirect
   *  a /login) y dejar que el 401 llegue como ApiError normal al
   *  llamador. Existe por la verificación de sesión al montar la app
   *  (AuthContext): ahí un 401 de /auth/perfil es el resultado ESPERADO
   *  de "todavía no hay sesión" -pestaña nueva, primera visita-, no una
   *  sesión que se cae en medio del uso. Tratarlo como el segundo caso
   *  dispararía una recarga dura de toda la SPA (window.location.href)
   *  en el arranque normal de cualquiera que no esté logueado. */
  sinInterceptor401?: boolean;
}

export async function apiFetch<T>(path: string, options: ApiOptions = {}): Promise<T> {
  const url = new URL(path, API_BASE_URL);

  if (options.params) {
    Object.entries(options.params).forEach(([key, value]) => {
      if (value !== undefined && value !== "") {
        url.searchParams.set(key, String(value));
      }
    });
  }

  const res = await fetch(url.toString(), {
    method: options.method ?? "GET",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  return manejarRespuesta<T>(res, path, options.sinInterceptor401);
}

/**
 * HU06 CA2: la vista previa manda un archivo .dat de muestra, así que va
 * como multipart/form-data y no como JSON. Deliberadamente NO se fija el
 * header Content-Type: el navegador tiene que ponerlo él para incluir el
 * `boundary` que separa las partes; fijarlo a mano rompe el parseo en el
 * backend. Por lo demás comparte la cookie de sesión y el manejo de 401
 * con apiFetch.
 */
export async function apiUpload<T>(path: string, formData: FormData): Promise<T> {
  const url = new URL(path, API_BASE_URL);

  const res = await fetch(url.toString(), {
    method: "POST",
    credentials: "include",
    body: formData,
  });

  return manejarRespuesta<T>(res);
}

async function manejarRespuesta<T>(
  res: Response,
  path?: string,
  sinInterceptor401?: boolean
): Promise<T> {
  // /auth/login nunca lleva token: su propio 401 significa "correo o
  // contraseña incorrectos" (ver MSG_CREDENCIALES_INVALIDAS en el backend),
  // no una sesión expirada. Sin esta excepción, cada intento fallido de
  // login disparaba el mismo interceptor que un token vencido: borraba el
  // storage y forzaba window.location.href, una recarga dura de la SPA que
  // se llevaba por delante el mensaje de error que el propio catch de
  // Login.tsx acababa de mostrar.
  if (res.status === 401 && path !== "/auth/login" && !sinInterceptor401) {
    // HU 01 CA: cookie de sesión ausente/inválida/expirada -> cerrar
    // sesión y volver a login. Ya no hay token que borrar del lado del
    // cliente (vive en una cookie httpOnly que el propio backend
    // gestiona), pero sí quedan los datos de UI que AuthContext guardó
    // junto a él (rol, nombre, etc.) y que hay que limpiar igual.
    limpiarDatosDeSesion();
    window.location.href = "/login";
    throw new ApiError("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", 401);
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(data?.detail ?? "Ocurrió un error inesperado", res.status);
  }

  return res.json() as Promise<T>;
}
