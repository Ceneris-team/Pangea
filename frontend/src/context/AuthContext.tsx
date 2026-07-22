import { createContext, useContext, useState, type ReactNode } from "react";
import { apiFetch } from "../services/api";

interface LoginResponse {
  access_token: string;
  token_type: string;
  rol: string;
  nombre_completo: string;
}

interface AuthState {
  token: string | null;
  rol: string | null;
  nombreCompleto: string | null;
}

interface AuthContextValue extends AuthState {
  isAuthenticated: boolean;
  login: (correo: string, contrasena: string, recordar: boolean) => Promise<LoginResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

function readInitialState(): AuthState {
  const token = localStorage.getItem("pangea_token") ?? sessionStorage.getItem("pangea_token");
  const rol = localStorage.getItem("pangea_rol") ?? sessionStorage.getItem("pangea_rol");
  const nombreCompleto =
    localStorage.getItem("pangea_nombre") ?? sessionStorage.getItem("pangea_nombre");
  return { token, rol, nombreCompleto };
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

    setState({ token: data.access_token, rol: data.rol, nombreCompleto: data.nombre_completo });
    return data;
  }

  function logout() {
    ["pangea_token", "pangea_rol", "pangea_nombre"].forEach((key) => {
      localStorage.removeItem(key);
      sessionStorage.removeItem(key);
    });
    setState({ token: null, rol: null, nombreCompleto: null });
  }

  return (
    <AuthContext.Provider value={{ ...state, isAuthenticated: !!state.token, login, logout }}>
      {children}
    </AuthContext.Provider>
  );
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
