import { useEffect, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * Catálogo de parámetros estándar (prmtr).
 *
 * No es parte de los CA de HU06 -que solo consume este catálogo para
 * poblar el selector de la tabla de asignación columna -> parámetro- sino
 * el complemento que faltaba: antes de esto, un parámetro nuevo (ej. una
 * marca de sensor que mide algo que todavía no existe en `prmtr`) solo se
 * podía dar de alta con un INSERT manual en la base de datos.
 */

interface Parametro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
}

export default function Parametros() {
  const { nombreCompleto, rol, logout } = useAuth();

  const [parametros, setParametros] = useState<Parametro[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [nmbr, setNmbr] = useState("");
  const [undd, setUndd] = useState("");
  const [dscrpcn, setDscrpcn] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);

  function cargarParametros() {
    setLoading(true);
    setError(null);
    apiFetch<Parametro[]>("/parametros")
      .then(setParametros)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el catálogo de parámetros");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    cargarParametros();
  }, []);

  const parametrosFiltrados = parametros.filter((p) =>
    p.nmbr.toLowerCase().includes(busqueda.toLowerCase())
  );

  function abrirFormulario() {
    setNmbr("");
    setUndd("");
    setDscrpcn("");
    setErrorFormulario(null);
    setMostrarFormulario(true);
  }

  async function guardarParametro(e: FormEvent) {
    e.preventDefault();
    setErrorFormulario(null);

    if (!nmbr.trim() || !undd.trim()) {
      setErrorFormulario("Nombre y unidad de medida son obligatorios");
      return;
    }

    setGuardando(true);
    try {
      await apiFetch<Parametro>("/parametros", {
        method: "POST",
        body: { nmbr: nmbr.trim(), undd: undd.trim(), dscrpcn: dscrpcn.trim() || null },
      });
      setMostrarFormulario(false);
      cargarParametros();
    } catch (err) {
      setErrorFormulario(err instanceof ApiError ? err.message : "No se pudo crear el parámetro");
    } finally {
      setGuardando(false);
    }
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="parametros" rol={rol} />

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
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Parámetros</h1>
                <p className="text-sm text-gray-600 dark:text-gray-300 mt-1 font-light">
                  Catálogo estándar de parámetros usado por los mapeos de formato (HU06).
                </p>
              </div>
              <button
                onClick={abrirFormulario}
                className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
              >
                + Nuevo parámetro
              </button>
            </header>

            <div className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10 overflow-hidden transition-colors duration-300">
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
                    placeholder="Buscar por nombre..."
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
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Unidad</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Descripción</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={3} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando parámetros...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && parametrosFiltrados.length === 0 && (
                      <tr>
                        <td colSpan={3} className="px-6 py-8 text-center text-gray-600 dark:text-gray-300">
                          {parametros.length === 0
                            ? 'Todavía no hay parámetros registrados. Crea el primero con "Nuevo parámetro".'
                            : "Ningún parámetro coincide con la búsqueda."}
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      parametrosFiltrados.map((p) => (
                        <tr
                          key={p.id_prmtr}
                          className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md border-b border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{p.nmbr}</td>
                          <td className="px-6 py-4">{p.undd}</td>
                          <td className="px-6 py-4">{p.dscrpcn ?? "—"}</td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {!loading && (
                <div className="p-5 border-t border-black/10 dark:border-white/10">
                  <span className="text-sm text-gray-600 dark:text-gray-300">
                    <span className="font-semibold text-gray-900 dark:text-white">{parametrosFiltrados.length}</span>{" "}
                    parámetro(s) registrado(s)
                  </span>
                </div>
              )}
            </div>
          </main>
        </div>
      </div>

      {mostrarFormulario && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-xl border border-black/10 dark:border-white/10">
            <form onSubmit={guardarParametro}>
              <div className="p-6 border-b border-black/10 dark:border-white/10">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">Nuevo parámetro</h2>
              </div>

              <div className="p-6 space-y-4">
                {errorFormulario && (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                    {errorFormulario}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Nombre *
                  </label>
                  <input
                    type="text"
                    value={nmbr}
                    onChange={(e) => setNmbr(e.target.value)}
                    placeholder="Ej. Caudal"
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Unidad de medida *
                  </label>
                  <input
                    type="text"
                    value={undd}
                    onChange={(e) => setUndd(e.target.value)}
                    placeholder="Ej. m3/s"
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1">
                    Descripción
                  </label>
                  <textarea
                    value={dscrpcn}
                    onChange={(e) => setDscrpcn(e.target.value)}
                    placeholder="Opcional: para qué se usa este parámetro"
                    rows={3}
                    className="bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none resize-none"
                  />
                </div>
              </div>

              <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setMostrarFormulario(false)}
                  className="px-4 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-200 bg-transparent border border-black/20 dark:border-white/20 rounded-xl hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors disabled:opacity-50"
                >
                  {guardando ? "Guardando..." : "Guardar"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}
