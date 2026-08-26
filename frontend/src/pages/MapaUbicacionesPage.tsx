import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import MapaUbicaciones, {
  type DispositivoParaMapa,
  type UbicacionParaMapa,
} from "../components/MapaUbicaciones";

/**
 * HU22: ver las Ubicaciones en un mapa. Solo lectura -el editor de
 * dibujo de polígono (HU08) es aparte, en AgregarUbicacion.tsx-.
 *
 *   CA1  marcadores verdes (Activa) / grises (Inactiva) sobre el contorno
 *   CA2  clic en un marcador -> panel con nombre, descripción, estado y
 *        cantidad de dispositivos (ambos CA los resuelve MapaUbicaciones)
 *   CA3  "Editar ubicación", dentro de ese panel
 *   CA4  "Ver listado", el botón del encabezado de esta pantalla
 *
 * Se consume GET /ubicaciones/mapa, que trae todo lo anterior en UNA
 * llamada. Antes esta pantalla usaba el listado paginado de HU07 y, como
 * ese endpoint no incluye plgn_gjsn, pedía además el detalle de cada
 * ubicación por separado (N+1).
 *
 * I-17: en paralelo se pide GET /dispositivos/mapa, para pintar el punto
 * propio de cada Dispositivo (DEC-28) dentro de su zona. Son dos
 * llamadas y no un solo endpoint anidado porque "Ubicaciones" y
 * "Dispositivos" son módulos de permiso distintos (HT-03).
 *
 * Sin filtro de estado a propósito: CA1 pide "todas las ubicaciones
 * registradas", y las Inactivas son justamente las que se pintan en gris.
 */

export default function MapaUbicacionesPage() {
  const { nombreCompleto, rol, logout } = useAuth();

  const [ubicaciones, setUbicaciones] = useState<UbicacionParaMapa[] | null>(null);
  const [dispositivos, setDispositivos] = useState<DispositivoParaMapa[]>([]);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Buscador de zonas. `volarA` es lo único que baja al mapa: cambia de
  // valor al elegir un resultado y dispara el reencuadre.
  const [busqueda, setBusqueda] = useState("");
  const [volarA, setVolarA] = useState<number | null>(null);
  const [volarASecuencia, setVolarASecuencia] = useState(0);

  const coincidencias = useMemo(() => {
    const termino = busqueda.trim().toLowerCase();
    if (termino === "" || !ubicaciones) return [];
    return ubicaciones.filter((u) => u.nmbr.toLowerCase().includes(termino)).slice(0, 8);
  }, [busqueda, ubicaciones]);

  useEffect(() => {
    let cancelado = false;
    setCargando(true);
    setError(null);

    // Dos llamadas en paralelo, una por recurso -no N+1-. Van separadas
    // porque "Ubicaciones" y "Dispositivos" son módulos de permiso
    // distintos (HT-03) y cada endpoint exige el suyo.
    Promise.all([
      apiFetch<UbicacionParaMapa[]>("/ubicaciones/mapa"),
      // Un usuario sin Lectura sobre "Dispositivos" recibe 403 acá: el
      // mapa sigue siendo útil con sus zonas, así que se degrada a una
      // lista vacía en vez de tumbar toda la pantalla.
      apiFetch<DispositivoParaMapa[]>("/dispositivos/mapa").catch(() => []),
    ])
      .then(([zonas, puntos]) => {
        if (cancelado) return;
        setUbicaciones(zonas);
        setDispositivos(puntos);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el mapa de ubicaciones");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, []);

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="ubicaciones" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          {/* TOP NAVBAR */}
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
              nombreCompleto={nombreCompleto}
              rol={rol}
            />
          </div>

          <main className="flex-1 overflow-hidden p-6 md:p-8 flex flex-col">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Mapa de Ubicaciones</h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Distribución de las estaciones de monitoreo. Haz clic en un marcador para ver
                  su detalle.
                </p>
              </div>
              <div className="flex items-center gap-4">
                {/* Leyenda: una sola fila con los dos tipos de marcador,
                    agrupados bajo su etiqueta. La FORMA distingue el tipo
                    (disco "⋮" en el borde = zona, rombo = dispositivo) y
                    el color el estado, así no hacen falta dos leyendas
                    compitiendo por el espacio. */}
                <div className="hidden lg:flex items-center gap-4 text-xs text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-2">
                    <span className="font-semibold text-gray-600 dark:text-gray-300">Zonas</span>
                    <span className="inline-flex items-center gap-1">
                      <span className="w-3 h-3 rounded-full bg-[#8fb300] ring-1 ring-white dark:ring-gray-700 flex items-center justify-center text-[7px] leading-none text-white font-bold">
                        ⋮
                      </span>
                      Activa
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="w-3 h-3 rounded-full bg-[#9ca3af] ring-1 ring-white dark:ring-gray-700 flex items-center justify-center text-[7px] leading-none text-white font-bold">
                        ⋮
                      </span>
                      Inactiva
                    </span>
                  </span>

                  <span className="w-px h-4 bg-gray-200 dark:bg-gray-600" />

                  <span className="inline-flex items-center gap-2">
                    <span className="font-semibold text-gray-600 dark:text-gray-300">
                      Dispositivos
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="w-2 h-2 rotate-45 bg-[#2563eb] ring-1 ring-white dark:ring-gray-700" />
                      Activo
                    </span>
                    <span className="inline-flex items-center gap-1">
                      <span className="w-2 h-2 rotate-45 bg-[#9ca3af] ring-1 ring-white dark:ring-gray-700" />
                      Inactivo
                    </span>
                  </span>
                </div>

                {/* CA4: volver a la vista de tabla (HU07). */}
                <Link
                  to="/ubicaciones"
                  className="inline-flex items-center px-4 py-2 text-sm font-medium text-gray-700 dark:text-gray-300 bg-white dark:bg-transparent border border-gray-300 dark:border-gray-600 rounded-xl hover:bg-gray-100 dark:hover:bg-gray-700 transition-all"
                >
                  Ver listado
                </Link>
              </div>
            </header>

            {/* Buscador de zonas: filtra sobre lo que el usuario YA puede
                ver -el endpoint solo devuelve las ubicaciones de su sede y
                con permiso (HU21)-, así que no hace falta pedir nada más
                al backend ni filtrar por sede en el cliente. */}
            {ubicaciones && ubicaciones.length > 0 && (
              <div className="mb-4 relative max-w-md">
                <div className="absolute inset-y-0 left-0 flex items-center pl-3 pointer-events-none">
                  <svg className="w-4 h-4 text-gray-400" fill="none" viewBox="0 0 20 20">
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
                  type="text"
                  value={busqueda}
                  onChange={(e) => setBusqueda(e.target.value)}
                  placeholder="Buscar una zona por nombre..."
                  aria-label="Buscar una zona"
                  className="bg-white dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full pl-10 p-2.5 outline-none placeholder-gray-400 dark:placeholder-gray-500"
                />

                {/* Resultados: al elegir uno, el mapa vuela a esa zona y
                    abre su panel (ver la prop volarA). */}
                {coincidencias.length > 0 && (
                  <ul className="absolute z-10 mt-1 w-full bg-white dark:bg-[#2d3748] border border-gray-200 dark:border-gray-600 rounded-xl shadow-lg overflow-hidden max-h-64 overflow-y-auto">
                    {coincidencias.map((u) => (
                      <li key={u.id_ubccn}>
                        <button
                          type="button"
                          onClick={() => {
                            setVolarA(u.id_ubccn);
                            setVolarASecuencia((n) => n + 1);
                            setBusqueda("");
                          }}
                          className="w-full text-left px-4 py-2.5 text-sm hover:bg-gray-50 dark:hover:bg-gray-700 flex items-center justify-between gap-3"
                        >
                          <span className="text-gray-900 dark:text-white">{u.nmbr}</span>
                          <span
                            className={`shrink-0 inline-flex items-center gap-1.5 text-xs ${
                              u.estd === "Activa"
                                ? "text-[#5a7000] dark:text-[#ccff00]"
                                : "text-gray-500 dark:text-gray-400"
                            }`}
                          >
                            <span
                              className={`w-2 h-2 rounded-full ${
                                u.estd === "Activa" ? "bg-[#8fb300]" : "bg-[#9ca3af]"
                              }`}
                            />
                            {u.estd}
                          </span>
                        </button>
                      </li>
                    ))}
                  </ul>
                )}

                {busqueda.trim() !== "" && coincidencias.length === 0 && (
                  <div className="absolute z-10 mt-1 w-full bg-white dark:bg-[#2d3748] border border-gray-200 dark:border-gray-600 rounded-xl shadow-lg px-4 py-2.5 text-sm text-gray-500 dark:text-gray-400">
                    Ninguna zona coincide con «{busqueda.trim()}».
                  </div>
                )}
              </div>
            )}

            {error && (
              <div className="mb-4 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            <div className="flex-1 bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
              {cargando ? (
                <div className="flex items-center justify-center h-full text-sm text-gray-500 dark:text-gray-400">
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                    <span>Cargando ubicaciones...</span>
                  </div>
                </div>
              ) : ubicaciones && ubicaciones.length === 0 ? (
                <div className="flex items-center justify-center h-full text-sm text-gray-500 dark:text-gray-400">
                  No hay ubicaciones registradas para mostrar.
                </div>
              ) : (
                ubicaciones && (
                  <MapaUbicaciones
                    ubicaciones={ubicaciones}
                    dispositivos={dispositivos}
                    volarA={volarA}
                    volarASecuencia={volarASecuencia}
                  />
                )
              )}
            </div>
          </main>
        </div>
      </div>
    </div>
  );
}
