import { useEffect, useState, type FormEvent } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import ConfirmarEliminacionModal from "../components/ConfirmarEliminacionModal";

/**
 * Catálogo de parámetros estándar (prmtr).
 *
 * No es parte de los CA de HU06 -que solo consume este catálogo para
 * poblar el selector de la tabla de asignación columna -> parámetro- sino
 * el complemento que faltaba: antes de esto, un parámetro nuevo (ej. una
 * marca de sensor que mide algo que todavía no existe en `prmtr`) solo se
 * podía dar de alta con un INSERT manual en la base de datos.
 *
 * Paginado server-side (25 por página) con búsqueda por nombre también
 * en el servidor: el catálogo crece con cada sensor nuevo, y GET
 * /parametros sin pagina/por_pagina sigue devolviendo la lista completa
 * (lo usan los selectores de ConfigurarMapeo/DispositivoDetalle), así que
 * esta pantalla es la única que pasa esos parámetros.
 */

interface Parametro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
  tipo_dato: "numerico" | "texto";
}

interface ListadoParametros {
  total: number;
  pagina: number;
  por_pagina: number;
  items: Parametro[];
}

const POR_PAGINA = 25;

export default function Parametros() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [isDarkMode, setIsDarkMode] = useState(false);

  const [data, setData] = useState<ListadoParametros | null>(null);
  const [pagina, setPagina] = useState(1);
  const [busqueda, setBusqueda] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const [mostrarFormulario, setMostrarFormulario] = useState(false);
  const [editandoId, setEditandoId] = useState<number | null>(null);
  const [nmbr, setNmbr] = useState("");
  const [undd, setUndd] = useState("");
  const [dscrpcn, setDscrpcn] = useState("");
  // Solo se define al crear: cambiarlo después de que el parámetro ya
  // tenga lecturas mezclaría datos entre tlmtr (numérico) y evnt_txt
  // (texto) bajo el mismo id_prmtr, así que PUT no lo acepta.
  const [tipoDato, setTipoDato] = useState<"numerico" | "texto">("numerico");
  const [guardando, setGuardando] = useState(false);
  const [errorFormulario, setErrorFormulario] = useState<string | null>(null);

  const [parametroAEliminar, setParametroAEliminar] = useState<Parametro | null>(null);
  const [eliminandoId, setEliminandoId] = useState<number | null>(null);
  const [errorEliminar, setErrorEliminar] = useState<string | null>(null);

  function cargarParametros() {
    setLoading(true);
    setError(null);
    apiFetch<ListadoParametros>("/parametros", {
      params: { pagina, por_pagina: POR_PAGINA, q: busqueda.trim() || undefined },
    })
      .then(setData)
      .catch((err) => {
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el catálogo de parámetros");
      })
      .finally(() => setLoading(false));
  }

  useEffect(() => {
    cargarParametros();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [pagina, busqueda]);

  // Cambiar el término de búsqueda vuelve a la primera página: quedarse
  // en la página 3 de un resultado que ahora tiene 1 sola dejaría la
  // tabla vacía sin que quede claro por qué.
  function actualizarBusqueda(valor: string) {
    setBusqueda(valor);
    setPagina(1);
  }

  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;

  function abrirFormularioCrear() {
    setEditandoId(null);
    setNmbr("");
    setUndd("");
    setDscrpcn("");
    setTipoDato("numerico");
    setErrorFormulario(null);
    setMostrarFormulario(true);
  }

  function abrirFormularioEditar(p: Parametro) {
    setEditandoId(p.id_prmtr);
    setNmbr(p.nmbr);
    setUndd(p.undd);
    setDscrpcn(p.dscrpcn ?? "");
    setTipoDato(p.tipo_dato);
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
      // tipo_dato solo se manda al crear: el PUT no lo acepta (ver
      // backend ParametroActualizar), así que incluirlo en la edición
      // no tendría efecto -se omite para que quede claro en el payload.
      const body =
        editandoId !== null
          ? { nmbr: nmbr.trim(), undd: undd.trim(), dscrpcn: dscrpcn.trim() || null }
          : {
              nmbr: nmbr.trim(),
              undd: undd.trim(),
              dscrpcn: dscrpcn.trim() || null,
              tipo_dato: tipoDato,
            };
      if (editandoId !== null) {
        await apiFetch<Parametro>(`/parametros/${editandoId}`, { method: "PUT", body });
      } else {
        await apiFetch<Parametro>("/parametros", { method: "POST", body });
      }
      setMostrarFormulario(false);
      cargarParametros();
    } catch (err) {
      setErrorFormulario(
        err instanceof ApiError
          ? err.message
          : `No se pudo ${editandoId !== null ? "actualizar" : "crear"} el parámetro`
      );
    } finally {
      setGuardando(false);
    }
  }

  async function confirmarEliminarParametro() {
    if (!parametroAEliminar) return;
    setEliminandoId(parametroAEliminar.id_prmtr);
    setErrorEliminar(null);
    try {
      await apiFetch<{ mensaje: string }>(`/parametros/${parametroAEliminar.id_prmtr}`, {
        method: "DELETE",
      });
      setParametroAEliminar(null);
      cargarParametros();
    } catch (err) {
      setErrorEliminar(err instanceof ApiError ? err.message : "No se pudo eliminar el parámetro");
    } finally {
      setEliminandoId(null);
    }
  }

  return (
    <div className={`${isDarkMode ? "dark" : ""} font-sans`}>
      <div className="flex h-screen bg-gray-50 dark:bg-gray-900 transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="parametros" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <Topbar
            isDarkMode={isDarkMode}
            onToggleDarkMode={() => setIsDarkMode(!isDarkMode)}
            nombreCompleto={nombreCompleto}
            rol={rol}
          />

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-extrabold text-gray-900 dark:text-white">Parámetros</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400 mt-1 font-light">
                  Catálogo estándar de parámetros usado por los mapeos de formato (HU06).
                </p>
              </div>
              <button
                onClick={abrirFormularioCrear}
                className="px-4 py-2.5 text-sm font-semibold text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 rounded-xl transition-colors"
              >
                + Nuevo parámetro
              </button>
            </header>

            <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-200 dark:border-gray-700 overflow-hidden transition-colors duration-300">
              <div className="p-5 border-b border-gray-100 dark:border-gray-700">
                <div className="relative w-full lg:max-w-md">
                  <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                    <svg className="w-5 h-5 text-gray-400 dark:text-gray-500" fill="none" viewBox="0 0 20 20">
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
                    onChange={(e) => actualizarBusqueda(e.target.value)}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 transition-all outline-none placeholder-gray-400 dark:placeholder-gray-500"
                  />
                </div>
              </div>

              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30">
                  {error}
                </div>
              )}

              {errorEliminar && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30">
                  {errorEliminar}
                </div>
              )}

              <div className="overflow-x-auto">
                <table className="w-full text-sm text-left text-gray-500 dark:text-gray-400">
                  <thead className="text-xs text-gray-500 dark:text-gray-400 uppercase bg-gray-50 dark:bg-gray-800/50 border-b border-gray-200 dark:border-gray-700">
                    <tr>
                      <th className="px-6 py-4 font-bold tracking-wider">Nombre</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Tipo</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Unidad</th>
                      <th className="px-6 py-4 font-bold tracking-wider">Descripción</th>
                      <th className="px-6 py-4 font-bold tracking-wider text-right">Acciones</th>
                    </tr>
                  </thead>
                  <tbody>
                    {loading && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          <div className="flex justify-center items-center gap-2">
                            <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                            <span>Cargando parámetros...</span>
                          </div>
                        </td>
                      </tr>
                    )}

                    {!loading && data?.items.length === 0 && (
                      <tr>
                        <td colSpan={5} className="px-6 py-8 text-center text-gray-500 dark:text-gray-400">
                          {busqueda
                            ? "Ningún parámetro coincide con la búsqueda."
                            : 'Todavía no hay parámetros registrados. Crea el primero con "Nuevo parámetro".'}
                        </td>
                      </tr>
                    )}

                    {!loading &&
                      data?.items.map((p) => (
                        <tr
                          key={p.id_prmtr}
                          className="bg-white dark:bg-[#2d3748] border-b border-gray-100 dark:border-gray-700 hover:bg-gray-50 dark:hover:bg-gray-800/50 transition-colors"
                        >
                          <td className="px-6 py-4 font-medium text-gray-900 dark:text-white">{p.nmbr}</td>
                          <td className="px-6 py-4">
                            <span
                              className={`inline-flex items-center px-2.5 py-1 rounded-full text-xs font-bold border ${
                                p.tipo_dato === "texto"
                                  ? "bg-blue-50 dark:bg-blue-900/20 text-blue-600 dark:text-blue-400 border-blue-200 dark:border-blue-800/30"
                                  : "bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border-[#ccff00]/30"
                              }`}
                            >
                              {p.tipo_dato === "texto" ? "Texto" : "Numérico"}
                            </span>
                          </td>
                          <td className="px-6 py-4">{p.undd}</td>
                          <td className="px-6 py-4">{p.dscrpcn ?? "—"}</td>
                          <td className="px-6 py-4 text-right">
                            <div className="inline-flex gap-2">
                              <button
                                onClick={() => abrirFormularioEditar(p)}
                                className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-lg hover:bg-gray-100 dark:hover:bg-gray-700 hover:text-gray-900 dark:hover:text-white transition-all"
                              >
                                Editar
                              </button>
                              <button
                                onClick={() => setParametroAEliminar(p)}
                                disabled={eliminandoId === p.id_prmtr}
                                className="inline-flex items-center justify-center px-3 py-1.5 text-sm font-medium text-red-600 dark:text-red-400 bg-white dark:bg-transparent border border-red-200 dark:border-red-800/40 rounded-lg hover:bg-red-50 dark:hover:bg-red-900/20 transition-all disabled:opacity-50"
                              >
                                {eliminandoId === p.id_prmtr ? "Eliminando..." : "Eliminar"}
                              </button>
                            </div>
                          </td>
                        </tr>
                      ))}
                  </tbody>
                </table>
              </div>

              {data && (
                <div className="p-5 border-t border-gray-100 dark:border-gray-700 flex items-center justify-between flex-wrap gap-3">
                  <span className="text-sm text-gray-500 dark:text-gray-400">
                    <span className="font-semibold text-gray-900 dark:text-white">{data.total}</span>{" "}
                    parámetro(s) registrado(s)
                  </span>
                  {totalPaginas > 1 && (
                    <div className="flex items-center gap-3">
                      <span className="text-sm text-gray-500 dark:text-gray-400">
                        Página {data.pagina} de {totalPaginas}
                      </span>
                      <div className="flex gap-2">
                        <button
                          disabled={pagina <= 1}
                          onClick={() => setPagina((p) => p - 1)}
                          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50"
                        >
                          Anterior
                        </button>
                        <button
                          disabled={pagina >= totalPaginas}
                          onClick={() => setPagina((p) => p + 1)}
                          className="px-3 py-1.5 text-sm border border-gray-300 dark:border-gray-600 rounded-lg disabled:opacity-50"
                        >
                          Siguiente
                        </button>
                      </div>
                    </div>
                  )}
                </div>
              )}
            </div>
          </main>
        </div>
      </div>

      {mostrarFormulario && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4">
          <div className="w-full max-w-md bg-white dark:bg-[#2d3748] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700">
            <form onSubmit={guardarParametro}>
              <div className="p-6 border-b border-gray-100 dark:border-gray-700">
                <h2 className="text-lg font-bold text-gray-900 dark:text-white">
                  {editandoId !== null ? "Editar parámetro" : "Nuevo parámetro"}
                </h2>
              </div>

              <div className="p-6 space-y-4">
                {errorFormulario && (
                  <div className="p-3 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-lg">
                    {errorFormulario}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Nombre *
                  </label>
                  <input
                    type="text"
                    value={nmbr}
                    onChange={(e) => setNmbr(e.target.value)}
                    placeholder="Ej. Caudal"
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Tipo de dato *
                  </label>
                  {editandoId !== null ? (
                    <p className="text-sm text-gray-500 dark:text-gray-400 py-2.5">
                      {tipoDato === "texto" ? "Texto" : "Numérico"} (no se puede cambiar después
                      de creado)
                    </p>
                  ) : (
                    <div className="inline-flex rounded-xl border border-gray-300 dark:border-gray-600 overflow-hidden">
                      <button
                        type="button"
                        onClick={() => setTipoDato("numerico")}
                        className={
                          "px-4 py-2 text-sm font-medium transition-colors " +
                          (tipoDato === "numerico"
                            ? "bg-[#ccff00] text-[#1a202c]"
                            : "bg-white dark:bg-[#2d3748] text-gray-700 dark:text-gray-300")
                        }
                      >
                        Numérico
                      </button>
                      <button
                        type="button"
                        onClick={() => setTipoDato("texto")}
                        className={
                          "px-4 py-2 text-sm font-medium transition-colors " +
                          (tipoDato === "texto"
                            ? "bg-[#ccff00] text-[#1a202c]"
                            : "bg-white dark:bg-[#2d3748] text-gray-700 dark:text-gray-300")
                        }
                      >
                        Texto
                      </button>
                    </div>
                  )}
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {tipoDato === "texto"
                      ? 'Para eventos como mensajes de alarma (ej. "Puerta Abierta"). No admite unidad numérica.'
                      : "Para mediciones (temperatura, caudal, etc.)."}
                  </p>
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Unidad de medida *
                  </label>
                  <input
                    type="text"
                    value={undd}
                    onChange={(e) => setUndd(e.target.value)}
                    placeholder="Ej. m3/s"
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none"
                  />
                </div>

                <div>
                  <label className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1">
                    Descripción
                  </label>
                  <textarea
                    value={dscrpcn}
                    onChange={(e) => setDscrpcn(e.target.value)}
                    placeholder="Opcional: para qué se usa este parámetro"
                    rows={3}
                    className="bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none resize-none"
                  />
                </div>
              </div>

              <div className="p-6 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
                <button
                  type="button"
                  onClick={() => setMostrarFormulario(false)}
                  className="px-4 py-2.5 text-sm font-semibold text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition-colors"
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

      {parametroAEliminar && (
        <ConfirmarEliminacionModal
          titulo={`Eliminar parámetro '${parametroAEliminar.nmbr}'`}
          mensaje="Si algún mapeo ya usa este parámetro, no se va a poder eliminar hasta quitarlo de esa asignación de columnas."
          confirmando={eliminandoId === parametroAEliminar.id_prmtr}
          onConfirmar={confirmarEliminarParametro}
          onCancelar={() => setParametroAEliminar(null)}
        />
      )}
    </div>
  );
}
