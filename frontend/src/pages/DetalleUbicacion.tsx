import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * Ficha de una ubicación: sus datos y qué parámetros se están midiendo
 * ahí hoy.
 *
 * La lista de parámetros es DERIVADA, no editable a mano: sale de los
 * mapeos de formato (HU06) de los dispositivos de esta ubicación, mismo
 * criterio que usa el selector de HU13. Si un parámetro no aparece acá,
 * la causa es que ningún dispositivo tiene todavía una columna mapeada a
 * él -se corrige en Mapeos de Formato, no aquí.
 */

interface UbicacionDetalle {
  id_ubccn: number;
  id_sd: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  plgn_gjsn: { type: string; coordinates: number[][][] };
}

interface Parametro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
}

export default function DetalleUbicacion() {
  const { id } = useParams();
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [ubicacion, setUbicacion] = useState<UbicacionDetalle | null>(null);
  const [parametros, setParametros] = useState<Parametro[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!id) return;
    let cancelado = false;
    setCargando(true);
    setError(null);

    Promise.all([
      apiFetch<UbicacionDetalle>(`/ubicaciones/${id}`),
      apiFetch<{ items: Parametro[] }>(`/ubicaciones/${id}/parametros`),
    ])
      .then(([detalle, params]) => {
        if (cancelado) return;
        setUbicacion(detalle);
        setParametros(params.items);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar la ubicación");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, [id]);

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="ubicaciones" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
          />

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <div className="mb-6">
              <Link
                to="/ubicaciones"
                className="inline-flex items-center text-sm font-medium text-gray-500 dark:text-gray-400 hover:text-gray-900 dark:hover:text-white transition-colors"
              >
                ← Volver a Ubicaciones
              </Link>
            </div>

            {error && (
              <div className="p-4 mb-6 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-xl">
                {error}
              </div>
            )}

            {cargando ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">Cargando…</div>
            ) : (
              ubicacion && (
                <>
                  <header className="mb-6 flex items-center justify-between gap-4">
                    <div>
                      <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">
                        {ubicacion.nmbr}
                      </h1>
                      {ubicacion.dscrpcn && (
                        <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">
                          {ubicacion.dscrpcn}
                        </p>
                      )}
                    </div>
                    <span
                      className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                        ubicacion.estd === "Activa"
                          ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                          : "bg-gray-100 dark:bg-gray-800 text-gray-600 dark:text-gray-400 border-gray-200 dark:border-gray-600"
                      }`}
                    >
                      {ubicacion.estd}
                    </span>
                  </header>

                  <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
                    <section className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                      <h2 className="text-base font-bold text-gray-900 dark:text-white mb-4">Ubicación</h2>
                      <dl className="space-y-3 text-sm">
                        <div>
                          <dt className="text-gray-500 dark:text-gray-400">Latitud</dt>
                          <dd className="font-mono text-gray-900 dark:text-white">{ubicacion.lttd}</dd>
                        </div>
                        <div>
                          <dt className="text-gray-500 dark:text-gray-400">Longitud</dt>
                          <dd className="font-mono text-gray-900 dark:text-white">{ubicacion.lngtd}</dd>
                        </div>
                        <div>
                          <dt className="text-gray-500 dark:text-gray-400">Vértices del polígono</dt>
                          <dd className="font-mono text-gray-900 dark:text-white">
                            {Math.max(0, (ubicacion.plgn_gjsn.coordinates[0]?.length ?? 1) - 1)}
                          </dd>
                        </div>
                      </dl>
                    </section>

                    <section className="lg:col-span-2 bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 p-6">
                      <h2 className="text-base font-bold text-gray-900 dark:text-white mb-1">
                        Parámetros en uso
                      </h2>
                      <p className="text-sm text-gray-500 dark:text-gray-400 mb-4 font-light">
                        Lo que se está midiendo hoy en esta ubicación, según los mapeos de formato de sus
                        dispositivos.
                      </p>

                      {parametros && parametros.length === 0 && (
                        <p className="text-sm text-gray-500 dark:text-gray-400">
                          Todavía no hay parámetros mapeados para los dispositivos de esta ubicación.{" "}
                          <Link to="/dispositivos" className="text-[#5a7000] dark:text-[#ccff00] underline">
                            Configura sus mapeos de formato
                          </Link>
                          .
                        </p>
                      )}

                      {parametros && parametros.length > 0 && (
                        <ul className="flex flex-wrap gap-2">
                          {parametros.map((p) => (
                            <li
                              key={p.id_prmtr}
                              title={p.dscrpcn ?? undefined}
                              className="inline-flex items-center px-3 py-1.5 rounded-full text-sm font-medium bg-[#ccff00]/10 text-[#5a7000] dark:text-[#ccff00] border border-[#ccff00]/30"
                            >
                              {p.nmbr}
                              <span className="ml-1.5 text-xs opacity-70">({p.undd})</span>
                            </li>
                          ))}
                        </ul>
                      )}
                    </section>
                  </div>
                </>
              )
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
