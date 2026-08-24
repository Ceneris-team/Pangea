import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import ConfirmarEliminacionModal from "../components/ConfirmarEliminacionModal";

/**
 * HU06 CA5 - "VER MAPEOS": listado donde el mapeo recién creado aparece
 * asociado a su dispositivo.
 *
 * DEC-09: el mapeo se identifica por dispositivo + tipo de trama, no por
 * sede + marca. Marca y sede ahora vienen derivadas del JOIN del backend
 * (mp_frmt -> dspstv -> ubccn), no de columnas propias de mp_frmt.
 */

interface MapeoListItem {
  id_mp: number;
  id_dspstv: number;
  dispositivo_nombre: string;
  id_sd: number;
  mrc: string;
  tp_trm: string;
  dscrpcn: string | null;
  dlmtdr: string;
  fl_inc_dts: number;
  frmt_fch: string;
  estd: string;
  total_columnas: number;
}

interface ListadoMapeos {
  total: number;
  items: MapeoListItem[];
}

// Etiquetas legibles: en BD se guarda el token que entiende el parser.
const ETIQUETA_DELIMITADOR: Record<string, string> = {
  ",": "Coma (,)",
  ";": "Punto y coma (;)",
  tab: "Tabulador",
  espacio: "Espacio",
};

const ETIQUETA_TRAMA: Record<string, string> = {
  H: "H · Datos periódicos",
  E: "E · Estados y eventos",
  P: "P · Eventos de puerta",
};

export default function Mapeos() {
  const { nombreCompleto, rol, logout } = useAuth();
  const navigate = useNavigate();

  const [busqueda, setBusqueda] = useState("");
  const [data, setData] = useState<ListadoMapeos | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);
  const [mapeoAEliminar, setMapeoAEliminar] = useState<MapeoListItem | null>(null);

  function cargar() {
    setLoading(true);
    setError(null);
    apiFetch<ListadoMapeos>("/mapeos")
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado de mapeos");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    cargar();
  }, []);

  async function confirmarEliminarMapeo() {
    if (!mapeoAEliminar) return;
    setEliminandoId(mapeoAEliminar.id_mp);
    try {
      await apiFetch<{ mensaje: string }>(`/mapeos/${mapeoAEliminar.id_mp}`, { method: "DELETE" });
      setMapeoAEliminar(null);
      cargar();
    } catch (err) {
      setMapeoAEliminar(null);
      setError(err instanceof ApiError ? err.message : "No se pudo eliminar el mapeo");
    } finally {
      setEliminandoId(null);
    }
  }

  // Filtro local por nombre o marca del dispositivo: el listado ya no es
  // tan grande como para justificar un filtro server-side por marca.
  const itemsFiltrados = (data?.items ?? []).filter((m) => {
    const patron = busqueda.trim().toLowerCase();
    if (!patron) return true;
    return (
      m.dispositivo_nombre.toLowerCase().includes(patron) ||
      m.mrc.toLowerCase().includes(patron)
    );
  });

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mapeos" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Mapeos de Formato</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Define cómo se interpretan los archivos .dat de cada dispositivo.
                </p>
              </div>
              <button
                onClick={() => navigate("/mapeos/nuevo")}
                className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
              >
                + Nuevo mapeo
              </button>
            </header>

            <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-hidden transition-colors duration-300">
              <div className="p-5 border-b border-black/10 dark:border-white/10">
                <div className="relative w-full lg:max-w-md">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-5 h-5 text-gray-500 dark:text-gray-400" fill="none" viewBox="0 0 20 20">
                      <path
                        stroke="currentColor"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                        strokeWidth="2"
                        d="m19 19-4-4m0-7A7 7 0 1 1 1 8a7 7 0 0 1 14 0Z"
                      />
                    </svg>
                  </div>
                  <input
                    type="search"
                    placeholder="Filtrar por dispositivo o marca..."
                    value={busqueda}
                    onChange={(e) => setBusqueda(e.target.value)}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400"
                  />
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30">
                  {error}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-600 dark:text-gray-300">
                  <thead className="text-xs text-gray-600 dark:text-gray-300 uppercase bg-black/5 dark:bg-white/5 border-b border-black/10 dark:border-white/10">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Dispositivo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Marca</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Tipo de trama</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Delimitador</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Formato de fecha</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Columnas</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Estado</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={8} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando mapeos...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && itemsFiltrados.length === 0 && (
                      <tr>
                        <td colSpan={8} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          Todavía no hay mapeos registrados. Crea el primero con "Nuevo mapeo".
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      itemsFiltrados.map((m) => (
                        <tr
                          key={m.id_mp}
                          className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{m.dispositivo_nombre}</td>
                          <td className="px-6 py-4">{m.mrc}</td>
                          <td className="px-6 py-4">
                            <div>{ETIQUETA_TRAMA[m.tp_trm] ?? m.tp_trm}</div>
                            {m.dscrpcn && (
                              <div className="text-xs text-gray-400 dark:text-gray-500 font-light">
                                {m.dscrpcn}
                              </div>
                            )}
                          </td>
                          <td className="px-6 py-4">{ETIQUETA_DELIMITADOR[m.dlmtdr] ?? m.dlmtdr}</td>
                          <td className="px-6 py-4 font-mono text-xs">{m.frmt_fch}</td>
                          <td className="px-6 py-4">{m.total_columnas}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                m.estd === "Activo"
                                  ? "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                                  : "bg-black/5 dark:bg-white/10 text-gray-600 dark:text-gray-300 border-black/20 dark:border-white/20"
                              }`}
                            >
                              {m.estd === "Activo" && (
                                <span className="w-1.5 h-1.5 mr-1.5 rounded-full bg-[#ccff00]"></span>
                              )}
                              {m.estd}
                            </span>
                          </td>
                          <td className="px-6 py-4 text-right">
                            <div className="inline-flex gap-2">
                              <Link
                                to={`/mapeos/${m.id_mp}/editar`}
                                className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white transition-all"
                              >
                                <svg
                                  className="w-4 h-4 mr-2 text-gray-500 dark:text-gray-400"
                                  fill="none"
                                  viewBox="0 0 24 24"
                                  strokeWidth="2"
                                  stroke="currentColor"
                                >
                                  <path
                                    strokeLinecap="round"
                                    strokeLinejoin="round"
                                    d="M15.232 5.232l3.536 3.536m-2.036-5.036a2.5 2.5 0 113.536 3.536L6.5 21.036H3v-3.572L16.732 3.732z"
                                  />
                                </svg>
                                Editar
                              </Link>
                              {m.estd === "Activo" && (
                                <button
                                  onClick={() => setMapeoAEliminar(m)}
                                  disabled={eliminandoId === m.id_mp}
                                  className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 bg-white dark:bg-transparent border border-red-200 dark:border-red-800/40 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-all disabled:opacity-50"
                                >
                                  {eliminandoId === m.id_mp ? "Eliminando..." : "Eliminar"}
                                </button>
                              )}
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {data && (
                <div className="p-5 border-t border-black/10 dark:border-white/10">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    <span className="font-semibold text-gray-900 dark:text-white">
                      {itemsFiltrados.length}
                    </span>{" "}
                    de <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span>{" "}
                    mapeo(s)
                  </span>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>

      {mapeoAEliminar && (
        <ConfirmarEliminacionModal
          titulo={`Eliminar mapeo de la trama '${mapeoAEliminar.tp_trm}'`}
          mensaje={`De "${mapeoAEliminar.dispositivo_nombre}". Los archivos ya procesados no se ven afectados, pero los archivos nuevos con el prefijo "${mapeoAEliminar.tp_trm}_" dejarán de poder interpretarse hasta que se cree un mapeo nuevo para esa trama.`}
          confirmando={eliminandoId === mapeoAEliminar.id_mp}
          onConfirmar={confirmarEliminarMapeo}
          onCancelar={() => setMapeoAEliminar(null)}
        />
      )}
    </div>
  );
}
