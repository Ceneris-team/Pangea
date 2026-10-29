import { useContext } from "react";
import { AuthContext } from "../context/authContextValue";
import type { AuthContextValue } from "../context/AuthContext";

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth debe usarse dentro de <AuthProvider>");
  return ctx;
}
