import { useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";
import Sidebar from "./Sidebar";
import Topbar from "./Topbar";
import { useAuth } from "../../context/AuthContext";

interface DashboardLayoutProps {
  children: ReactNode;
}

export default function DashboardLayout({ children }: DashboardLayoutProps) {
  const [isDarkMode, setIsDarkMode] = useState(false);
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();

  function handleLogout() {
    logout();
    navigate("/login", { replace: true });
  }

  return (
    <div className={isDarkMode ? "dark" : ""}>
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden font-sans">
        <Sidebar onLogout={handleLogout} />

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
