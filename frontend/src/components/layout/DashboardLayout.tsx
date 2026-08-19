import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar, { type SeccionActiva } from "./Sidebar";
import Topbar from "./Topbar";
import { useAuth } from "../../context/AuthContext";

interface DashboardLayoutProps {
  children: ReactNode;
  /** Sección del sidebar que queda resaltada. Sin esto el layout no
   *  compila: Sidebar exige `activo` y `rol` (rompía `npm run build`). */
  activo?: SeccionActiva;
}

export default function DashboardLayout({ children, activo = "panel" }: DashboardLayoutProps) {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={isDarkMode ? "dark" : ""}>
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden font-sans">
        <Sidebar onLogout={handleLogout} activo={activo} rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode((v) => !v)}
            nombreCompleto={nombreCompleto}
            rol={rol}
          />

          <main className="flex-1 overflow-y-auto p-6 md:p-8">{children}</main>
        </div>
      </div>
    </div>
  );
}
