import { createContext, useContext, useState, type ReactNode } from "react";
import { apiFetch } from "../services/api";

interface LoginResponse {
  access_token: string;
  token_type: string;
  rol: string;
  nombre_completo: string;
  debe_cambiar_contrasena: boolean;
  zona_horaria: string;
}

interface AuthState {
  token: string | null;
  rol: string | null;
  nombreCompleto: string | null;
  /** HU01/HU04: la contraseña temporal generada al crear el usuario debe
   *  cambiarse en el primer inicio de sesión. Se persiste junto al token
   *  para que el guard siga aplicando si el usuario recarga la página. */
  debeCambiarContrasena: boolean;
  /** HU14: zona horaria de visualización elegida por el usuario. Se usa
   *  para convertir las marcas de tiempo de telemetría (almacenadas en UTC). */
  zonaHoraria: string;
}

interface AuthContextValue extends AuthState {
  isAuthenticated: boolean;
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
  const token = localStorage.getItem("pangea_token") ?? sessionStorage.getItem("pangea_token");
  const rol = localStorage.getItem("pangea_rol") ?? sessionStorage.getItem("pangea_rol");
  const nombreCompleto =
    localStorage.getItem("pangea_nombre") ?? sessionStorage.getItem("pangea_nombre");
  const debeCambiar =
    localStorage.getItem("pangea_debe_cambiar") ?? sessionStorage.getItem("pangea_debe_cambiar");
  const zonaHoraria =
    localStorage.getItem("pangea_zona_horaria") ?? sessionStorage.getItem("pangea_zona_horaria");
  return {
    token,
    rol,
    nombreCompleto,
    debeCambiarContrasena: debeCambiar === "true",
    zonaHoraria: zonaHoraria ?? ZONA_HORARIA_DEFECTO,
  };
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<AuthState>(readInitialState);

  async function login(correo: string, contrasena: string, recordar: boolean) {
    const data = await apiFetch<LoginResponse>("/auth/login", {
      method: "POST",
      body: { correo, contrasena },
    });

    const storage = recordar ? localStorage : sessionStorage;
    storage.setItem("pangea_token", data.access_token);
    storage.setItem("pangea_rol", data.rol);
    storage.setItem("pangea_nombre", data.nombre_completo);
    storage.setItem("pangea_debe_cambiar", String(data.debe_cambiar_contrasena));
    storage.setItem("pangea_zona_horaria", data.zona_horaria);

    setState({
      token: data.access_token,
      rol: data.rol,
      nombreCompleto: data.nombre_completo,
      debeCambiarContrasena: data.debe_cambiar_contrasena,
      zonaHoraria: data.zona_horaria,
    });
    return data;
  }

  function logout() {
    [
      "pangea_token",
      "pangea_rol",
      "pangea_nombre",
      "pangea_debe_cambiar",
      "pangea_zona_horaria",
    ].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
    setState({
      token: null,
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
    const storage = localStorage.getItem("pangea_token") ? localStorage : sessionStorage;
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
        isAuthenticated: !!state.token,
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
