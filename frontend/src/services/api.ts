/**
 * Envoltorio único sobre fetch para toda la app.
 *
 * Por qué existe: sin esto, cada página tendría que repetir la URL base y
 * agregar manualmente el header "Authorization: Bearer <token>". Centralizarlo
 * aquí evita que alguien olvide el token en un endpoint nuevo (HT-04/HT-09
 * exigen JWT en cada endpoint protegido).
 */
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "http://127.0.0.1:8000";

function getToken(): string | null {
  return localStorage.getItem("pangea_token") ?? sessionStorage.getItem("pangea_token");
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

  const token = getToken();

  const res = await fetch(url.toString(), {
    method: options.method ?? "GET",
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: options.body ? JSON.stringify(options.body) : undefined,
  });

  if (res.status === 401) {
    // HU 01 CA: token inválido/expirado -> cerrar sesión y volver a login.
    localStorage.removeItem("pangea_token");
    localStorage.removeItem("pangea_rol");
    sessionStorage.removeItem("pangea_token");
    sessionStorage.removeItem("pangea_rol");
    window.location.href = "/login";
    throw new ApiError("Tu sesión ha expirado. Por favor, vuelve a iniciar sesión.", 401);
  }

  if (!res.ok) {
    const data = await res.json().catch(() => null);
    throw new ApiError(data?.detail ?? "Ocurrió un error inesperado", res.status);
  }

  return res.json() as Promise<T>;
}
