import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU28 - Crear alarma.
 *
 *   CA1  formulario con Nombre de la alarma, Parámetro a monitorear y
 *        Ubicación asociada
 *   CA2  "SIGUIENTE" (con los obligatorios completos) lleva al paso de
 *        configuración de condiciones definido en HU29
 *   CA3  "GUARDAR" crea la alarma en estado Activa, la agrega al listado
 *        y muestra "Alarma creada correctamente"
 *   CA4  "CANCELAR" descarta el formulario y vuelve al listado sin crear
 *        ningún registro
 *
 * El alta es un asistente de DOS pasos en UNA sola pantalla, no dos rutas:
 * el estado del paso 1 tiene que seguir vivo cuando el usuario está en el
 * paso 2 -si no, volver atrás perdería lo tecleado- y nada se persiste
 * hasta el GUARDAR final, que es lo que hace cierto el CA4.
 *
 * El paso 2 que se implementa acá es el mínimo que HU28 necesita para
 * poder llegar a su CA3 (una condición operador + umbral, que es lo que
 * admite cndcn_alrm). Las reglas de negocio de las condiciones -cuántas,
 * con qué combinaciones, histéresis- son de HU29.
 */

interface UbicacionOpcion {
  id_ubccn: number;
  nmbr: string;
}

interface ParametroOpcion {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  dscrpcn: string | null;
  tipo_dato: string;
}

/** Mismos operadores que admite el CHECK de cndcn_alrm. */
const OPERADORES = [">", ">=", "<", "<=", "="] as const;

const MAX_NOMBRE = 100;

export default function CrearAlarma() {
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const [paso, setPaso] = useState<1 | 2>(1);

  // Paso 1 (HU28 CA1): los tres campos obligatorios.
  const [nombre, setNombre] = useState("");
  const [ubicacionId, setUbicacionId] = useState("");
  const [parametroId, setParametroId] = useState("");

  // Paso 2 (HU29).
  const [operador, setOperador] = useState<string>(">");
  const [umbral, setUmbral] = useState("");

  const [ubicaciones, setUbicaciones] = useState<UbicacionOpcion[]>([]);
  const [parametros, setParametros] = useState<ParametroOpcion[]>([]);
  const [cargandoParametros, setCargandoParametros] = useState(false);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // CA1: el selector de ubicaciones se puebla con las asignadas al
  // usuario (HU21); el backend aplica el mismo filtro al guardar.
  useEffect(() => {
    apiFetch<{ items: UbicacionOpcion[] }>("/alarmas/ubicaciones")
      .then((res) => setUbicaciones(res.items))
      .catch((err) =>
        setError(
          err instanceof ApiError ? err.message : "No se pudieron cargar tus ubicaciones asignadas"
        )
      );
  }, []);

  /** Los dos selectores van encadenados: al cambiar de ubicación se
   *  descarta el parámetro elegido, que podría no existir en la nueva. El
   *  reset vive en el handler y no en el efecto de carga a propósito -un
   *  setState síncrono dentro de un efecto encadena renders de más-. */
  function cambiarUbicacion(valor: string) {
    setUbicacionId(valor);
    setParametroId("");
    setParametros([]);
  }

  // "El selector de parámetros muestra únicamente los parámetros
  // disponibles en las ubicaciones asignadas al usuario según HU 21": la
  // lista se recarga cada vez que cambia la ubicación elegida.
  useEffect(() => {
    if (!ubicacionId) return;

    let cancelado = false;
    setCargandoParametros(true);

    apiFetch<{ items: ParametroOpcion[] }>("/alarmas/parametros", {
      params: { ubicacion_id: ubicacionId },
    })
      .then((res) => {
        if (!cancelado) setParametros(res.items);
      })
      .catch((err) => {
        if (cancelado) return;
        setParametros([]);
        setError(
          err instanceof ApiError ? err.message : "No se pudieron cargar los parámetros disponibles"
        );
      })
      .finally(() => {
        if (!cancelado) setCargandoParametros(false);
      });

    return () => {
      cancelado = true;
    };
  }, [ubicacionId]);

  /** CA4: descarta el formulario y vuelve al listado. No llama al backend
   *  -no hay nada creado que deshacer: la única escritura es el GUARDAR-. */
  function handleCancelar() {
    navigate("/alarmas");
  }

  /** CA2: los obligatorios completos habilitan el paso a las condiciones.
   *  Se valida acá para no gastar un viaje al backend, pero el schema
   *  Pydantic repite las mismas reglas: esto es comodidad de UI, no la
   *  garantía. */
  function handleSiguiente() {
    if (!nombre.trim()) {
      setError("El nombre de la alarma es obligatorio");
      return;
    }
    if (!ubicacionId) {
      setError("Selecciona la ubicación asociada");
      return;
    }
    if (!parametroId) {
      setError("Selecciona el parámetro a monitorear");
      return;
    }
    setError("");
    setPaso(2);
  }

  /** CA3. */
  async function handleGuardar(e: FormEvent) {
    e.preventDefault();

    if (umbral.trim() === "" || Number.isNaN(Number(umbral))) {
      setError("Indica el valor umbral de la condición");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      await apiFetch<{ mensaje: string }>("/alarmas", {
        method: "POST",
        body: {
          nmbr: nombre.trim(),
          id_ubccn: Number(ubicacionId),
          id_prmtr: Number(parametroId),
          condiciones: [{ oprdr: operador, vlr_umbrl: Number(umbral) }],
        },
      });

      // CA3: volver al listado, que recarga y ya muestra la alarma nueva.
      // El mensaje viaja en el state de navegación, mismo mecanismo que
      // usa HU08 al registrar una ubicación.
      navigate("/alarmas", { state: { mensaje: "Alarma creada correctamente" } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear la alarma");
      // Si el backend rechaza algo del paso 1 (nombre inválido, ubicación
      // sin acceso), el usuario tiene que poder corregirlo: el error se
      // muestra en el paso 2 pero "Atrás" sigue disponible.
    } finally {
      setGuardando(false);
    }
  }

  const parametroElegido = parametros.find((p) => String(p.id_prmtr) === parametroId);
  const ubicacionElegida = ubicaciones.find((u) => String(u.id_ubccn) === ubicacionId);

  const inputClase =
    "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";
  const botonSecundario =
    "px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors";
  const botonPrimario =
    "px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors";

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="alarmas" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Crear alarma</h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Recibe una notificación automática cuando un parámetro supere o caiga por debajo del
                umbral que definas.
              </p>
            </header>

            {/* Indicador de los dos pasos del alta. */}
            <ol className="mb-6 flex items-center gap-4 text-sm">
              {[
                { numero: 1 as const, titulo: "Datos generales" },
                { numero: 2 as const, titulo: "Condiciones" },
              ].map((etapa) => (
                <li key={etapa.numero} className="flex items-center gap-2">
                  <span
                    className={`w-7 h-7 flex items-center justify-center rounded-full text-xs font-bold border ${
                      paso === etapa.numero
                        ? "bg-[#ccff00] text-[#1a202c] border-[#ccff00]"
                        : "border-black/20 dark:border-white/20 text-gray-500 dark:text-gray-400"
                    }`}
                  >
                    {etapa.numero}
                  </span>
                  <span
                    className={
                      paso === etapa.numero
                        ? "font-semibold text-gray-900 dark:text-white"
                        : "text-gray-500 dark:text-gray-400"
                    }
                  >
                    {etapa.titulo}
                  </span>
                </li>
              ))}
            </ol>

            <form
              onSubmit={handleGuardar}
              className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10"
            >
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30 rounded-t-2xl">
                  {error}
                </div>
              )}

              {/* ---------------- Paso 1: datos generales (CA1) ---------------- */}
              {paso === 1 && (
                <div className="p-6 space-y-5">
                  <div>
                    <label className={labelClase} htmlFor="nmbr">
                      Nombre de la alarma <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="nmbr"
                      type="text"
                      maxLength={MAX_NOMBRE}
                      value={nombre}
                      onChange={(e) => setNombre(e.target.value)}
                      placeholder="Crecida del río Rímac"
                      className={inputClase}
                    />
                    <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                      {nombre.length}/{MAX_NOMBRE} caracteres
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div>
                      <label className={labelClase} htmlFor="id_ubccn">
                        Ubicación asociada <span className="text-red-500">*</span>
                      </label>
                      <select
                        id="id_ubccn"
                        value={ubicacionId}
                        onChange={(e) => cambiarUbicacion(e.target.value)}
                        className={inputClase + " cursor-pointer"}
                      >
                        <option value="">Selecciona una ubicación</option>
                        {ubicaciones.map((u) => (
                          <option key={u.id_ubccn} value={u.id_ubccn}>
                            {u.nmbr}
                          </option>
                        ))}
                      </select>
                      {ubicaciones.length === 0 && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          No tienes ubicaciones asignadas.
                        </p>
                      )}
                    </div>

                    <div>
                      <label className={labelClase} htmlFor="id_prmtr">
                        Parámetro a monitorear <span className="text-red-500">*</span>
                      </label>
                      <select
                        id="id_prmtr"
                        value={parametroId}
                        onChange={(e) => setParametroId(e.target.value)}
                        disabled={!ubicacionId || cargandoParametros}
                        className={inputClase + " cursor-pointer disabled:opacity-60"}
                      >
                        <option value="">
                          {!ubicacionId
                            ? "Elige primero la ubicación"
                            : cargandoParametros
                              ? "Cargando parámetros..."
                              : "Selecciona un parámetro"}
                        </option>
                        {parametros.map((p) => (
                          <option key={p.id_prmtr} value={p.id_prmtr}>
                            {p.nmbr} ({p.undd})
                          </option>
                        ))}
                      </select>
                      {ubicacionId && !cargandoParametros && parametros.length === 0 && (
                        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                          Esa ubicación todavía no mide ningún parámetro numérico.
                        </p>
                      )}
                    </div>
                  </div>
                </div>
              )}

              {/* ---------------- Paso 2: condiciones (HU29) ---------------- */}
              {paso === 2 && (
                <div className="p-6 space-y-5">
                  <div className="rounded-xl border border-black/10 dark:border-white/10 p-4 text-sm text-gray-600 dark:text-gray-300">
                    <p className="font-semibold text-gray-900 dark:text-white">{nombre.trim()}</p>
                    <p>
                      {parametroElegido?.nmbr}
                      {parametroElegido ? ` (${parametroElegido.undd})` : ""} en{" "}
                      {ubicacionElegida?.nmbr}
                    </p>
                  </div>

                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div>
                      <label className={labelClase} htmlFor="oprdr">
                        Condición <span className="text-red-500">*</span>
                      </label>
                      <select
                        id="oprdr"
                        value={operador}
                        onChange={(e) => setOperador(e.target.value)}
                        className={inputClase + " cursor-pointer"}
                      >
                        {OPERADORES.map((op) => (
                          <option key={op} value={op}>
                            {op}
                          </option>
                        ))}
                      </select>
                    </div>

                    <div>
                      <label className={labelClase} htmlFor="vlr_umbrl">
                        Valor umbral <span className="text-red-500">*</span>
                        {parametroElegido && (
                          <span className="text-gray-500 dark:text-gray-400 font-normal">
                            {" "}
                            ({parametroElegido.undd})
                          </span>
                        )}
                      </label>
                      <input
                        id="vlr_umbrl"
                        type="number"
                        step="any"
                        value={umbral}
                        onChange={(e) => setUmbral(e.target.value)}
                        placeholder="3.5"
                        className={inputClase}
                      />
                    </div>
                  </div>

                  <p className="text-xs text-gray-500 dark:text-gray-400">
                    La alarma se creará en estado <span className="font-semibold">Activa</span>.
                  </p>
                </div>
              )}

              <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-between gap-3">
                {/* CA4: no toca el backend, solo descarta y vuelve. */}
                <button type="button" onClick={handleCancelar} className={botonSecundario}>
                  Cancelar
                </button>

                <div className="flex gap-3">
                  {paso === 2 && (
                    <button
                      type="button"
                      onClick={() => {
                        setError("");
                        setPaso(1);
                      }}
                      className={botonSecundario}
                    >
                      Atrás
                    </button>
                  )}

                  {paso === 1 ? (
                    // CA2. type="button": el paso 1 no envía el formulario,
                    // solo avanza; el submit real es el GUARDAR del paso 2.
                    <button type="button" onClick={handleSiguiente} className={botonPrimario}>
                      Siguiente
                    </button>
                  ) : (
                    <button type="submit" disabled={guardando} className={botonPrimario}>
                      {guardando ? "Guardando..." : "Guardar"}
                    </button>
                  )}
                </div>
              </div>
            </form>
          </main>
        </div>
      </div>
    </div>
  );
}
