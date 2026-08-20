import { Link } from "react-router-dom";
import pangeaLogo from "../../assets/pangea-logo.png";
import { ROLES, rutaPorRol } from "../../config/roles";

export type SeccionActiva = "panel" | "usuarios" | "ubicaciones" | "dispositivos" | "conexiones-ftp" | "dashboard" | "configuracion" | "consulta-datos"| "mapeos" | "parametros" | "cola-ingesta" | "graficos";

interface SidebarProps {
  onLogout: () => void;
  activo: SeccionActiva;
  rol: string | null;
}

const linkBase = "flex items-center gap-3 px-3 py-2 rounded-lg transition-colors";
const linkInactivo = "text-gray-300 hover:bg-white/5";
const linkActivo = "bg-[#ccff00]/10 text-[#ccff00] font-medium";
const linkDeshabilitado = linkInactivo + " opacity-60 cursor-not-allowed";

export default function Sidebar({ onLogout, activo, rol }: SidebarProps) {
  return (
    <aside className="w-64 bg-white/[0.04] backdrop-blur-md border-r border-white/10 hidden md:flex flex-col transition-colors duration-300">
      <div className="h-16 flex items-center px-6 border-b border-white/10">
        <img src={pangeaLogo} alt="Pangea" className="h-8 w-auto rounded-md bg-white px-2 py-1" />
      </div>

      <nav className="flex-1 p-4 space-y-1 overflow-y-auto">
        {/* Panel: lleva al panel real del rol logueado (panel-admin / panel-tecnico) */}
        <Link
          to={rutaPorRol(rol ?? "")}
          className={linkBase + " " + (activo === "panel" ? linkActivo : linkInactivo)}
        >
          <svg
            className={"w-5 h-5 " + (activo === "panel" ? "text-[#ccff00]" : "")}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M4 6h16M4 12h16M4 18h7"
            />
          </svg>
          Panel
        </Link>

        {/* Dashboard: placeholder, aun no implementado */}
        <a
          href="#"
          title="Proximamente"
          onClick={(e) => e.preventDefault()}
          className={linkBase + " " + linkDeshabilitado}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M3 12l2-2m0 0l7-7 7 7M5 10v10a1 1 0 001 1h3m10-11l2 2m-2-2v10a1 1 0 01-1 1h-3m-6 0a1 1 0 001-1v-4a1 1 0 011-1h2a1 1 0 011 1v4a1 1 0 001 1m-6 0h6"
            />
          </svg>
          Dashboard
        </a>

        {/* HU03: Solo el rol Administrador puede acceder a este modulo */}
        {rol === ROLES.ADMINISTRADOR && (
          <Link
            to="/usuarios"
            className={linkBase + " " + (activo === "usuarios" ? linkActivo : linkInactivo)}
          >
            <svg
              className={"w-5 h-5 " + (activo === "usuarios" ? "text-[#ccff00]" : "")}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z"
              />
            </svg>
            Gestion de Usuarios
          </Link>
        )}

        {/* HU05: Solo Administrador y Tecnico CENERIS acceden a este modulo */}
        {(rol === ROLES.ADMINISTRADOR || rol === ROLES.TECNICO_CENERIS) && (
          <Link
            to="/conexiones-ftp"
            className={linkBase + " " + (activo === "conexiones-ftp" ? linkActivo : linkInactivo)}
          >
            <svg
              className={"w-5 h-5 " + (activo === "conexiones-ftp" ? "text-[#ccff00]" : "")}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M5 12h14M5 12a2 2 0 01-2-2V7a2 2 0 012-2h14a2 2 0 012 2v3a2 2 0 01-2 2M5 12a2 2 0 00-2 2v3a2 2 0 002 2h14a2 2 0 002-2v-3a2 2 0 00-2-2M6 8h.01M6 16h.01"
              />
            </svg>
            Conexiones FTP
          </Link>
        )}

        {/* DEC-09: el link "Mapeos de Formato" se retiró. El formato ya no
            es un módulo propio navegable por sede+marca: se configura
            dentro de la ficha de cada Dispositivo (Gestión de Dispositivos
            -> click en el dispositivo -> pestañas Formato y Datos), porque
            el mapeo depende de qué sensores tiene cableados ese datalogger
            concreto. */}

        {/* Catálogo de parámetros estándar que consume HU06. Mismo
            criterio de acceso: solo Administrador y Técnico CENERIS. */}
        {(rol === ROLES.ADMINISTRADOR || rol === ROLES.TECNICO_CENERIS) && (
          <Link
            to="/parametros"
            className={linkBase + " " + (activo === "parametros" ? linkActivo : linkInactivo)}
          >
            <svg
              className={"w-5 h-5 " + (activo === "parametros" ? "text-[#ccff00]" : "")}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M9 17V7m3 10V11m3 6V9M5 21h14a2 2 0 002-2V5a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2z"
              />
            </svg>
            Parámetros
          </Link>
        )}

        {/* HU09: monitoreo de la cola de procesamiento. Mismo criterio de
            acceso que HU05/HU06: solo Administrador y Tecnico CENERIS. */}
        {(rol === ROLES.ADMINISTRADOR || rol === ROLES.TECNICO_CENERIS) && (
          <Link
            to="/cola-ingesta"
            className={linkBase + " " + (activo === "cola-ingesta" ? linkActivo : linkInactivo)}
          >
            <svg
              className={"w-5 h-5 " + (activo === "cola-ingesta" ? "text-[#ccff00]" : "")}
              fill="none"
              stroke="currentColor"
              viewBox="0 0 24 24"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M4 7h16M4 12h16M4 17h16"
              />
            </svg>
            Cola de Ingesta
          </Link>
        )}

        <Link
          to="/ubicaciones"
          className={linkBase + " " + (activo === "ubicaciones" ? linkActivo : linkInactivo)}
        >
          <svg
            className={"w-5 h-5 " + (activo === "ubicaciones" ? "text-[#ccff00]" : "")}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M17.657 16.657L13.414 20.9a2 2 0 01-2.828 0l-4.243-4.243a8 8 0 1111.314 0z"
            />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 11a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Gestion de Ubicaciones
        </Link>

        {/* HU10: listar dispositivos. Visible para todos los roles, igual
            que Ubicaciones: el backend ya filtra qué ve cada uno. */}
        <Link
          to="/dispositivos"
          className={linkBase + " " + (activo === "dispositivos" ? linkActivo : linkInactivo)}
        >
          <svg
            className={"w-5 h-5 " + (activo === "dispositivos" ? "text-[#ccff00]" : "")}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M9 3v2m6-2v2M9 19v2m6-2v2M5 9H3m2 6H3m18-6h-2m2 6h-2M7 19h10a2 2 0 002-2V7a2 2 0 00-2-2H7a2 2 0 00-2 2v10a2 2 0 002 2zM9 9h6v6H9V9z"
            />
          </svg>
          Gestion de Dispositivos
        </Link>

        {/* HU13: consulta de datos de telemetria filtrada por parametros/ubicaciones */}
        <Link
          to="/consulta-datos"
          className={linkBase + " " + (activo === "consulta-datos" ? linkActivo : linkInactivo)}
        >
          <svg
            className={"w-5 h-5 " + (activo === "consulta-datos" ? "text-[#ccff00]" : "")}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M9 17V7m6 10V11m-9 6h12a2 2 0 002-2V5a2 2 0 00-2-2H6a2 2 0 00-2 2v10a2 2 0 002 2z"
            />
          </svg>
          Consulta de Datos
        </Link>

        {/* Graficos: vista rapida de telemetria en charts (misma fuente que Consulta de Datos) */}
        <Link
          to="/graficos"
          className={linkBase + " " + (activo === "graficos" ? linkActivo : linkInactivo)}
        >
          <svg
            className={"w-5 h-5 " + (activo === "graficos" ? "text-[#ccff00]" : "")}
            fill="none"
            stroke="currentColor"
            viewBox="0 0 24 24"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M3 3v18h18M7 15l4-5 3 3 5-7"
            />
          </svg>
          Gráficos
        </Link>

        {/* Configuracion: placeholder, aun no implementado */}
        <a
          href="#"
          title="Proximamente"
          onClick={(e) => e.preventDefault()}
          className={linkBase + " " + linkDeshabilitado}
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M10.325 4.317c.426-1.756 2.924-1.756 3.35 0a1.724 1.724 0 002.573 1.066c1.543-.94 3.31.826 2.37 2.37a1.724 1.724 0 001.065 2.572c1.756.426 1.756 2.924 0 3.35a1.724 1.724 0 00-1.066 2.573c.94 1.543-.826 3.31-2.37 2.37a1.724 1.724 0 00-2.572 1.065c-.426 1.756-2.924 1.756-3.35 0a1.724 1.724 0 00-2.573-1.066c-1.543.94-3.31-.826-2.37-2.37a1.724 1.724 0 00-1.065-2.572c-1.756-.426-1.756-2.924 0-3.35a1.724 1.724 0 001.066-2.573c-.94-1.543.826-3.31 2.37-2.37.996.608 2.296.07 2.572-1.065z"
            />
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M15 12a3 3 0 11-6 0 3 3 0 016 0z" />
          </svg>
          Configuracion
        </a>
      </nav>

      <div className="p-4 border-t border-white/10">
        <button
          onClick={onLogout}
          className="flex items-center gap-3 px-3 py-2 w-full text-left text-gray-300 hover:bg-red-500/10 hover:text-red-400 rounded-lg transition-colors"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth="2"
              d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1"
            />
          </svg>
          Cerrar Sesion
        </button>
      </div>
    </aside>
  );
}
