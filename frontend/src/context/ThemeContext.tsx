import { createContext, useContext, useEffect, useState, type ReactNode } from "react";

type Tema = "light" | "dark";

interface ThemeContextValue {
  tema: Tema;
  esOscuro: boolean;
  toggleTema: () => void;
}

const ThemeContext = createContext<ThemeContextValue | undefined>(undefined);

const CLAVE_TEMA = "pangea_tema";

function leerTemaInicial(): Tema {
  const guardado = localStorage.getItem(CLAVE_TEMA);
  return guardado === "light" ? "light" : "dark";
}

export function ThemeProvider({ children }: { children: ReactNode }) {
  const [tema, setTema] = useState<Tema>(leerTemaInicial);

  // Tailwind (darkMode: 'class') busca un ancestro con clase "dark"; se
  // aplica en <html> para que todo el árbol (incluida cualquier página) la
  // herede sin que cada componente tenga que repetir la clase.
  useEffect(() => {
    document.documentElement.classList.toggle("dark", tema === "dark");
    localStorage.setItem(CLAVE_TEMA, tema);
  }, [tema]);

  function toggleTema() {
    setTema((t) => (t === "dark" ? "light" : "dark"));
  }

  return (
    <ThemeContext.Provider value={{ tema, esOscuro: tema === "dark", toggleTema }}>
      {children}
    </ThemeContext.Provider>
  );
}

export function useTheme(): ThemeContextValue {
  const ctx = useContext(ThemeContext);
  if (!ctx) throw new Error("useTheme debe usarse dentro de <ThemeProvider>");
  return ctx;
}
