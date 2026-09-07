import { createContext, useContext, useEffect, useState, type ReactNode } from "react";
import { ApiError, apiFetch, limpiarDatosDeSesion } from "../services/api";

interface LoginResponse {
  access_token: string;
  token_type: string;
  rol: string;
  nombre_completo: string;
  debe_cambiar_contrasena: boolean;
  zona_horaria: string;
}

/** Forma de GET /auth/perfil (routers/auth.py). Distinta de LoginResponse
 *  -"rol" es el único campo que comparten con el mismo nombre-, así que
 *  no se puede reutilizar esa interfaz para la verificación de sesión. */
interface PerfilResponse {
  nombre_completo: string;
  correo: string;
  rol: string;
  scope: string;
  estado: string;
  debe_cambiar_contrasena: boolean;
  zona_horaria: string;
}

interface AuthState {
  /** Ya NO es el JWT: el navegador ni lo ve, vive en una cookie httpOnly
   *  que el backend setea en el login (ver Set-Cookie en
   *  routers/auth.py). Este flag solo refleja "hay una sesión iniciada
   *  según el último login/lectura de storage", para que isAuthenticated
   *  y el guard de rutas protegidas sigan funcionando igual que antes. */
  sesionIniciada: boolean;
  rol: string | null;
  nombreCompleto: string | null;
  /** HU01/HU04: la contraseña temporal generada al crear el usuario debe
   *  cambiarse en el primer inicio de sesión. Se persiste junto al resto
   *  de datos de UI para que el guard siga aplicando si el usuario
   *  recarga la página. */
  debeCambiarContrasena: boolean;
  /** HU14: zona horaria de visualización elegida por el usuario. Se usa
   *  para convertir las marcas de tiempo de telemetría (almacenadas en UTC). */
  zonaHoraria: string;
}

interface AuthContextValue extends AuthState {
  isAuthenticated: boolean;
  /** true SOLO durante la comprobación inicial de sesión (GET
   *  /auth/perfil al montar la app). Mientras esté en true, ProtectedRoute
   *  debe mostrar un loading en vez de decidir login-vs-dashboard: es lo
   *  que evita el bug de "pestaña nueva pide login aunque la cookie
   *  httpOnly siga viva" -sin esto, ProtectedRoute mira sesionIniciada en
   *  memoria (vacía en una pestaña nueva) antes de que la cookie tenga
   *  chance de demostrar que la sesión sigue activa-. */
  verificandoSesion: boolean;
  login: (correo: string, contrasena: string, recordar: boolean) => Promise<LoginResponse>;
  logout: () => void;
  /** Se llama tras cambiar la contraseña para levantar el bloqueo. */
  marcarContrasenaCambiada: () => void;
  /** HU14 CA2: se llama tras guardar la nueva zona horaria en "Mi perfil". */
  actualizarZonaHoraria: (zona: string) => void;
}

const ZONA_HORARIA_DEFECTO = "America/Lima";

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readInitialState(): AuthState {
  // Ningún token que leer: solo los datos de UI que dejó el login
  // anterior. Si la cookie httpOnly ya expiró del lado del navegador, el
  // primer fetch protegido devuelve 401 y el interceptor de api.ts
  // redirige a /login igual -este estado inicial es "optimista", no la
  // fuente de verdad de si la sesión sigue viva-.
  const rol = localStorage.getItem("pangea_rol") ?? sessionStorage.getItem("pangea_rol");
  const nombreCompleto =
    localStorage.getItem("pangea_nombre") ?? sessionStorage.getItem("pangea_nombre");
  const debeCambiar =
    localStorage.getItem("pangea_debe_cambiar") ?? sessionStorage.getItem("pangea_debe_cambiar");
  const zonaHoraria =
    localStorage.getItem("pangea_zona_horaria") ?? sessionStorage.getItem("pangea_zona_horaria");
  return {
    sesionIniciada: rol !== null,
    rol,
    nombreCompleto,
    debeCambiarContrasena: debeCambiar === "true",
    zonaHoraria: zonaHoraria ?? ZONA_HORARIA_DEFECTO,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(readInitialState);
  const [verificandoSesion, setVerificandoSesion] = useState(true);

  // Se corre UNA vez al montar el Provider -pestaña nueva, F5, o la
  // primera carga de la app son exactamente los tres casos en los que
  // React vuelve a montar todo desde cero, así que este único efecto
  // cubre los tres sin distinguirlos-. Es la pregunta que faltaba: antes
  // de esto, ProtectedRoute decidía login-vs-dashboard mirando SOLO el
  // estado en memoria (vacío en una pestaña nueva) sin haberle dado a la
  // cookie httpOnly ninguna oportunidad de demostrar que la sesión sigue
  // viva. GET /auth/perfil es el mismo endpoint protegido que ya se
  // verificó por curl que responde 200 solo con la cookie -no hace falta
  // uno nuevo dedicado a esto-.
  useEffect(() => {
    let cancelado = false;

    async function verificar() {
      try {
        // sinInterceptor401: un 401 acá es "todavía no hay sesión", el
        // resultado normal de una pestaña nueva sin login -no debe
        // disparar la recarga dura a /login que sí corresponde cuando la
        // sesión se cae en medio del uso (ver manejarRespuesta en
        // services/api.ts)-.
        const perfil = await apiFetch<PerfilResponse>("/auth/perfil", {
          sinInterceptor401: true,
        });
        if (cancelado) return;

        // El storage puede estar vacío (primera visita en este
        // navegador) o desactualizado (otra pestaña cambió el rol/zona
        // horaria); en ambos casos la respuesta de /auth/perfil es la
        // fuente de verdad, así que reemplaza el estado leído de storage
        // en vez de completarlo.
        localStorage.setItem("pangea_rol", perfil.rol);
        localStorage.setItem("pangea_nombre", perfil.nombre_completo);
        localStorage.setItem("pangea_debe_cambiar", String(perfil.debe_cambiar_contrasena));
        localStorage.setItem("pangea_zona_horaria", perfil.zona_horaria);

        setState({
          sesionIniciada: true,
          rol: perfil.rol,
          nombreCompleto: perfil.nombre_completo,
          debeCambiarContrasena: perfil.debe_cambiar_contrasena,
          zonaHoraria: perfil.zona_horaria,
        });
      } catch (err) {
        if (cancelado) return;
        // 401 (cookie ausente/vencida) es el caso esperado de "no hay
        // sesión": no es un error a reportar, solo el resultado normal de
        // no estar logueado. Cualquier OTRO error (red caída, backend
        // caído) también debe caer a "mostrar login" -no hay forma de
        // confirmar una sesión que no se pudo consultar-, pero sin
        // pisar silenciosamente datos de sesión que sí pudieran ser
        // válidos: se limpian igual, porque una sesión que no se puede
        // verificar no puede tratarse como activa.
        if (!(err instanceof ApiError) || err.status !== 401) {
          console.warn("No se pudo verificar la sesión activa:", err);
        }
        limpiarDatosDeSesion();
        setState({
          sesionIniciada: false,
          rol: null,
          nombreCompleto: null,
          debeCambiarContrasena: false,
          zonaHoraria: ZONA_HORARIA_DEFECTO,
        });
      } finally {
        if (!cancelado) setVerificandoSesion(false);
      }
    }

    verificar();
    return () => {
      cancelado = true;
    };
  }, []);

  async function login(correo: string, contrasena: string, recordar: boolean) {
    // El propio fetch (credentials: "include" en apiFetch) es lo que le
    // hace guardar la cookie Set-Cookie de la respuesta al navegador; acá
    // no hay nada que hacer con data.access_token del lado del token en
    // sí, solo con los datos de UI que lo acompañan.
    const data = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: { correo, contrasena },
    });

    const storage = recordar ? localStorage : sessionStorage;
    storage.setItem("pangea_rol", data.rol);
    storage.setItem("pangea_nombre", data.nombre_completo);
    storage.setItem("pangea_debe_cambiar", String(data.debe_cambiar_contrasena));
    storage.setItem("pangea_zona_horaria", data.zona_horaria);

    setState({
      sesionIniciada: true,
      rol: data.rol,
      nombreCompleto: data.nombre_completo,
      debeCambiarContrasena: data.debe_cambiar_contrasena,
      zonaHoraria: data.zona_horaria,
    });
    return data;
  }

  function logout() {
    // Best-effort: si la red falla a mitad de logout, igual se limpia el
    // estado local y se saca al usuario de las rutas protegidas. La
    // cookie del navegador quedaría viva hasta su propio vencimiento (8h),
    // pero ProtectedRoute ya no deja pasar sin sesionIniciada en el estado.
    apiFetch("/auth/logout", { method: "POST" }).catch(() => {});
    limpiarDatosDeSesion();
    setState({
      sesionIniciada: false,
      rol: null,
      nombreCompleto: null,
      debeCambiarContrasena: false,
      zonaHoraria: ZONA_HORARIA_DEFECTO,
    });
  }

  /** HU14 CA2: refleja la zona horaria recién guardada sin forzar un
   *  nuevo login (a diferencia del cambio de contraseña, este ajuste no
   *  invalida la sesión). */
  function actualizarZonaHoraria(zona: string) {
    // pangea_rol es el proxy de "el login usó localStorage (recordar)":
    // login() siempre guarda todas las claves de UI juntas en el mismo
    // storage, así que cualquiera de ellas sirve para saber cuál fue.
    const storage = localStorage.getItem("pangea_rol") ? localStorage : sessionStorage;
    storage.setItem("pangea_zona_horaria", zona);
    setState((prev) => ({ ...prev, zonaHoraria: zona }));
  }

  /** El cambio de contraseña invalida el token actual (ver
   *  security/dependencies.py), así que tras cambiarla el flujo termina en
   *  logout. Esto solo levanta el bloqueo en memoria para que el redirect
   *  a "Mi perfil" no se repita en el intervalo previo al logout. */
  function marcarContrasenaCambiada() {
    localStorage.removeItem("pangea_debe_cambiar");
    sessionStorage.removeItem("pangea_debe_cambiar");
    setState((prev) => ({ ...prev, debeCambiarContrasena: false }));
  }

  return (
    <AuthContext.Provider
      value={{
        ...state,
        isAuthenticated: state.sesionIniciada,
        verificandoSesion,
        login,
        logout,
        marcarContrasenaCambiada,
        actualizarZonaHoraria,
      }}
    >
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
