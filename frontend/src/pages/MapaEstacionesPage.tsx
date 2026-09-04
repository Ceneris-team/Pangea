import { useCallback, useEffect, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import MapaEstacionesCliente, {
  type EstacionParaMapa,
} from "../components/MapaEstacionesCliente";
import { useMapaEnVivo, type EventoLectura } from "../hooks/useMapaEnVivo";

/**
 * HU17 - Ver datos en mapa (rol Cliente Final).
 *
 *   CA1  marcadores en las ubicaciones ASIGNADAS al usuario (HU21)
 *   CA2  clic en un marcador -> panel con último valor por parámetro y
 *        fecha/hora de la última lectura
 *   CA3  telemetría nueva actualiza el marcador SIN recargar la página
 *   CA4  "Ver gráfico" desde el panel -> /graficos con la ubicación
 *        preseleccionada
 *
 * Dos fuentes de datos que se complementan:
 *   - GET /mapa-cliente (REST): la foto inicial. El mapa se pinta con
 *     esto, aunque el WebSocket nunca llegue a conectar.
 *   - /mapa-cliente/ws (WebSocket): las actualizaciones en vivo, que se
 *     aplican sobre esa foto. Ver hooks/useMapaEnVivo.ts.
 *
 * Distinta de MapaUbicacionesPage.tsx (HU22, vista de Administrador), que
 * no se toca: aquella gestiona zonas y dispositivos, esta muestra el
 * estado actual de las estaciones del Cliente Final.
 */

/** Estado de conexión, en palabras que le sirvan al usuario. Se muestra
 *  siempre -no solo cuando falla-: en una pantalla que promete datos "en
 *  vivo", saber si el canal está realmente abierto es parte del dato. */
const TEXTO_ESTADO: Record<string, { texto: string; color: string; punto: string }> = {
  conectando: {
    texto: "Conectando…",
    color: "text-gray-500 dark:text-gray-400",
    punto: "bg-gray-400",
  },
  conectado: {
    texto: "En vivo",
    color: "text-[#5a7000] dark:text-[#ccff00]",
    punto: "bg-[#8fb300]",
  },
  reconectando: {
    texto: "Reconectando…",
    color: "text-amber-600 dark:text-amber-400",
    punto: "bg-amber-500",
  },
  "sin-conexion": {
    texto: "Sin conexión en vivo",
    color: "text-red-600 dark:text-red-400",
    punto: "bg-red-500",
  },
};

export default function MapaEstacionesPage() {
  const { nombreCompleto, rol, logout } = useAuth();

  const [estaciones, setEstaciones] = useState<EstacionParaMapa[] | null>(null);
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Marcador que acaba de recibir un dato, para el destello de CA3.
  const [destelloEn, setDestelloEn] = useState<number | null>(null);
  const [destelloSecuencia, setDestelloSecuencia] = useState(0);

  useEffect(() => {
    let cancelado = false;
    setCargando(true);
    setError(null);

    apiFetch<{ items: EstacionParaMapa[] }>("/mapa-cliente")
      .then((res) => {
        if (cancelado) return;
        setEstaciones(res.items);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el mapa de estaciones");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, []);

  /**
   * CA3: aplica una lectura nueva sobre la estación que corresponda.
   *
   * Solo se toca la estación afectada y solo el parámetro que llegó: el
   * resto del estado se conserva por referencia, así React no re-renderiza
   * los demás marcadores.
   *
   * El SEMÁFORO no se recalcula acá a propósito. Los umbrales viven en el
   * backend (hoy hardcodeados, mañana en cndcn_alrm con HU28) y duplicar
   * esa lógica en el navegador significaría que al implementar HU28 habría
   * que cambiarla en dos lugares -y que mientras tanto el color pudiera
   * discrepar entre la carga inicial y una actualización en vivo-. El
   * marcador refleja el color del último cálculo del servidor hasta la
   * próxima carga; el VALOR y la FECHA sí se actualizan al instante, que
   * es lo que CA3 pide explícitamente.
   */
  const aplicarLectura = useCallback((evento: EventoLectura) => {
    setEstaciones((previas) => {
      if (!previas) return previas;

      let cambio = false;
      const siguientes = previas.map((estacion) => {
        if (estacion.id_ubccn !== evento.id_ubccn) return estacion;
        cambio = true;

        const parametros = [...estacion.parametros];
        const indice = parametros.findIndex((p) => p.parametro === evento.parametro);
        const nuevo = {
          parametro: evento.parametro,
          unidad: evento.unidad,
          valor: evento.valor,
          fch_hr: evento.fch_hr,
        };
        if (indice >= 0) parametros[indice] = nuevo;
        else {
          // Un parámetro que aparece por primera vez (la estación no tenía
          // lecturas de él todavía) se agrega manteniendo el orden
          // alfabético que usa el backend, para que el panel no reordene
          // sus filas de golpe delante del usuario.
          parametros.push(nuevo);
          parametros.sort((a, b) => a.parametro.localeCompare(b.parametro));
        }

        // "Última lectura" de la estación: la más reciente de todas.
        const ultima =
          estacion.ultima_lectura && evento.fch_hr
            ? evento.fch_hr > estacion.ultima_lectura
              ? evento.fch_hr
              : estacion.ultima_lectura
            : evento.fch_hr ?? estacion.ultima_lectura;

        return { ...estacion, parametros, ultima_lectura: ultima };
      });

      if (!cambio) return previas;
      return siguientes;
    });

    setDestelloEn(evento.id_ubccn);
    setDestelloSecuencia((n) => n + 1);
  }, []);

  const { estado } = useMapaEnVivo(aplicarLectura);
  const indicador = TEXTO_ESTADO[estado] ?? TEXTO_ESTADO.conectando;

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mapa-estaciones" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-hidden p-6 md:p-8 flex flex-col">
            <header className="mb-6 flex flex-col md:flex-row md:items-center justify-between gap-4">
              <div>
                <h1 className="text-2xl font-bold text-gray-900 dark:text-white">
                  Mapa de Estaciones
                </h1>
                <p className="text-sm text-gray-500 dark:text-gray-400">
                  Estado actual de tus estaciones. Haz clic en un marcador para ver sus últimos
                  valores.
                </p>
              </div>

              <div className="flex items-center gap-4">
                {/* Leyenda del semáforo. El color nunca va solo: cada
                    nivel lleva su etiqueta en palabras, para que la
                    pantalla siga siendo legible con daltonismo. */}
                <div className="hidden lg:flex items-center gap-3 text-xs text-gray-500 dark:text-gray-400">
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-[#16a34a] ring-1 ring-white dark:ring-gray-700" />
                    Normal
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-[#eab308] ring-1 ring-white dark:ring-gray-700" />
                    Atención
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span className="w-3 h-3 rounded-full bg-[#dc2626] ring-1 ring-white dark:ring-gray-700" />
                    Crítico
                  </span>
                </div>

                <span className="w-px h-4 bg-gray-200 dark:bg-gray-600 hidden lg:block" />

                {/* CA3: estado del canal en vivo. */}
                <span
                  className={`inline-flex items-center gap-2 text-xs font-medium ${indicador.color}`}
                  aria-live="polite"
                >
                  <span
                    className={`w-2 h-2 rounded-full ${indicador.punto} ${
                      estado === "conectado" ? "animate-pulse" : ""
                    }`}
                  />
                  {indicador.texto}
                </span>
              </div>
            </header>

            {error && (
              <div className="mb-4 p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {/* Aviso cuando el canal en vivo no está disponible: el mapa
                sigue siendo útil con los datos de la carga inicial, pero
                el usuario tiene que saber que ya no se está actualizando
                solo -si no, vería datos viejos creyéndolos actuales-. */}
            {estado === "sin-conexion" && !error && (
              <div className="mb-4 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 text-amber-700 dark:text-amber-400 text-sm">
                No se pudo establecer el canal de actualización en vivo. Los datos que ves son los
                de la última carga; recarga la página para actualizarlos.
              </div>
            )}

            <div className="flex-1 bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700 overflow-hidden">
              {cargando ? (
                <div className="flex items-center justify-center h-full text-sm text-gray-500 dark:text-gray-400">
                  <div className="flex items-center gap-2">
                    <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                    <span>Cargando estaciones...</span>
                  </div>
                </div>
              ) : estaciones && estaciones.length === 0 ? (
                <div className="flex items-center justify-center h-full text-sm text-gray-500 dark:text-gray-400 text-center px-6">
                  No tienes estaciones asignadas todavía. Contacta al administrador para que te
                  asigne acceso a una ubicación.
                </div>
              ) : (
                estaciones && (
                  <MapaEstacionesCliente
                    estaciones={estaciones}
                    destelloEn={destelloEn}
                    destelloSecuencia={destelloSecuencia}
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
