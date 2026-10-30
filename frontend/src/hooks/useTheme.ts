import { useContext } from "react";
import { ThemeContext } from "../context/themeContextValue";
import type { ThemeContextValue } from "../context/ThemeContext";

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>");
  return ctx;
}
