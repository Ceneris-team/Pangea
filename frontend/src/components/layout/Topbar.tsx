import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { useTheme } from "../../context/ThemeContext";
import { apiFetch } from "../../services/api";
import { ROLES } from "../../config/roles";

interface TopbarProps {
  nombreCompleto: string | null;
  rol: string | null;
}

/** HU50 CA4: dispositivo/trama/columna de una asignación pendiente,
 *  mismo shape que ColumnaPendienteItem del backend (routers/mapeos.py). */
interface ColumnaPendiente {
  id_mp_cl_pnd: number;
  id_dspstv: number;
  dispositivo_nombre: string;
  tp_trm: string;
  nmbr_clmn_orgn: string;
}

// HU50 CA4: la notificación es para quien puede resolverla (Técnico
// CENERIS/Administrador, mismos roles que ya editan Ingesta en el resto
// de la app) - un Cliente Final o Administrador Comercial no tiene
// permiso sobre GET /mapeos/columnas-pendientes, así que ni se intenta
// el fetch para esos roles.
const ROLES_VEN_NOTIFICACION: readonly string[] = [ROLES.ADMINISTRADOR, ROLES.TECNICO_CENERIS];

const MAXIMO_EN_POPOVER = 15;

export default function Topbar({ nombreCompleto, rol }: TopbarProps) {
  const { esOscuro, toggleTema } = useTheme();
  const [conteoPendientes, setConteoPendientes] = useState(0);
  const [popoverAbierto, setPopoverAbierto] = useState(false);
  const [pendientes, setPendientes] = useState<ColumnaPendiente[] | null>(null);

  const puedeVerNotificacion = ROLES_VEN_NOTIFICACION.includes(rol ?? "");

  useEffect(() => {
    if (!puedeVerNotificacion) return;
    let cancelado = false;

    function cargarConteo() {
      apiFetch<{ total: number }>("/mapeos/columnas-pendientes/conteo")
        .then((res) => {
          if (!cancelado) setConteoPendientes(res.total);
        })
        .catch(() => {
          // Silencioso a propósito: un badge de notificación que falla
          // por una red inestable no debe interrumpir al usuario con un
          // error -simplemente no muestra nada hasta el próximo refresco.
        });
    }

    cargarConteo();
    // Refresco periódico: el Topbar vive montado durante toda la sesión
    // (layout compartido), así que sin esto el conteo quedaría
    // desactualizado en sesiones largas -p. ej. si otra pestaña resuelve
    // una pendiente, o si llega un archivo nuevo con columnas sin match-.
    const intervalo = window.setInterval(cargarConteo, 60_000);
    return () => {
      cancelado = true;
      window.clearInterval(intervalo);
    };
  }, [puedeVerNotificacion]);

  function abrirPopover() {
    setPopoverAbierto((prev) => !prev);
    if (!pendientes) {
      apiFetch<ColumnaPendiente[]>("/mapeos/columnas-pendientes")
        .then((res) => setPendientes(res))
        .catch(() => setPendientes([]));
    }
  }

  return (
    <div className="inline-flex items-center gap-4 bg-white/60 dark:bg-white/10 backdrop-blur-md border border-black/10 dark:border-white/10 rounded-2xl pl-3 pr-4 py-2 shadow-lg transition-colors duration-300">
      <button
        onClick={toggleTema}
        className="text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/10 p-2 rounded-full transition-colors"
        aria-label="Alternar modo oscuro"
      >
        {esOscuro ? (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M12 3v1m0 16v1m9-9h-1M4 12H3m15.364 6.364l-.707-.707M6.343 6.343l-.707-.707m12.728 0l-.707.707M6.343 17.657l-.707.707M16 12a4 4 0 11-8 0 4 4 0 018 0z" />
          </svg>
        ) : (
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth="2" d="M20.354 15.354A9 9 0 018.646 3.646 9.003 9.003 0 0012 21a9.003 9.003 0 008.354-5.646z" />
          </svg>
        )}
      </button>

      {puedeVerNotificacion && (
        <div className="relative">
          <button
            onClick={abrirPopover}
            className="relative text-gray-600 dark:text-gray-300 hover:bg-black/5 dark:hover:bg-white/10 p-2 rounded-full transition-colors"
            aria-label="Columnas pendientes de asignar"
          >
            <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                strokeWidth="2"
                d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
              />
            </svg>
            {conteoPendientes > 0 && (
              <span className="absolute -top-0.5 -right-0.5 inline-flex items-center justify-center min-w-[18px] h-[18px] px-1 rounded-full text-[10px] font-bold bg-red-500 text-white border border-white dark:border-[#1a202c]">
                {conteoPendientes > 99 ? "99+" : conteoPendientes}
              </span>
            )}
          </button>

          {popoverAbierto && (
            <div className="absolute right-0 mt-2 w-80 max-h-96 overflow-y-auto bg-white dark:bg-[#2d3748] border border-black/10 dark:border-white/10 rounded-xl shadow-xl z-50">
              <div className="px-4 py-3 border-b border-black/10 dark:border-white/10">
                <h3 className="text-sm font-bold text-gray-900 dark:text-white">
                  Columnas pendientes de asignar
                </h3>
              </div>
              {pendientes === null ? (
                <p className="px-4 py-6 text-sm text-center text-gray-500 dark:text-gray-400">
                  Cargando...
                </p>
              ) : pendientes.length === 0 ? (
                <p className="px-4 py-6 text-sm text-center text-gray-500 dark:text-gray-400">
                  No hay columnas pendientes.
                </p>
              ) : (
                <ul>
                  {pendientes.slice(0, MAXIMO_EN_POPOVER).map((p) => (
                    <li
                      key={p.id_mp_cl_pnd}
                      className="border-b border-black/5 dark:border-white/5 last:border-0"
                    >
                      <Link
                        to={`/dispositivos/${p.id_dspstv}`}
                        onClick={() => setPopoverAbierto(false)}
                        className="block px-4 py-3 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                      >
                        <div className="text-sm font-medium text-gray-900 dark:text-white">
                          {p.dispositivo_nombre}
                        </div>
                        <div className="text-xs text-gray-500 dark:text-gray-400">
                          Trama '{p.tp_trm}' · columna "{p.nmbr_clmn_orgn}"
                        </div>
                      </Link>
                    </li>
                  ))}
                  {pendientes.length > MAXIMO_EN_POPOVER && (
                    <li className="px-4 py-2 text-xs text-center text-gray-500 dark:text-gray-400">
                      Y {pendientes.length - MAXIMO_EN_POPOVER} más...
                    </li>
                  )}
                </ul>
              )}
            </div>
          )}
        </div>
      )}

      <div className="flex items-center gap-3 pl-4 border-l border-black/10 dark:border-white/10">
        <div className="text-right hidden sm:block">
          <div className="text-sm font-semibold text-gray-900 dark:text-white">{nombreCompleto ?? "Usuario"}</div>
          <div className="text-xs text-gray-500 dark:text-gray-300">{rol ?? ""}</div>
        </div>
        <img
          className="w-10 h-10 rounded-full border-2 border-[#ccff00] object-cover"
          src={`https://ui-avatars.com/api/?name=${encodeURIComponent(nombreCompleto ?? "Usuario")}&background=2d3748&color=ccff00`}
          alt="Avatar del usuario"
        />
      </div>
    </div>
  );
}
