import { useEffect, useMemo, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import MapaDibujoPoligono, { type PoligonoGeoJSON } from "../components/MapaDibujoPoligono";
import { centroideDePoligono } from "../components/poligono";

/**
 * HU08 (ampliación) - Editar ubicación.
 *
 * Mismo formulario que AgregarUbicacion.tsx (Nombre, Descripción, Latitud,
 * Longitud y el contorno dibujado sobre el mapa) más el Estado, que solo
 * tiene sentido sobre una ubicación que ya existe -al crearla siempre nace
 * "Activa" por el server_default-. Se llega desde el listado (HU07) y
 * desde el panel del mapa (HU22 CA3).
 *
 * La SEDE no se edita acá: mover una ubicación de sede arrastraría a sus
 * dispositivos y a los permisos ya concedidos sobre ella. El backend ni
 * siquiera acepta id_sd en el body (ver UbicacionActualizar).
 *
 * Es una pantalla separada de AgregarUbicacion.tsx a propósito, aunque
 * compartan estructura: el alta resuelve la sede y navega distinto, y
 * fusionarlas obligaría a un componente lleno de condicionales "si estoy
 * editando".
 */

interface UbicacionDetalle {
  id_ubccn: number;
  nmbr: string;
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  plgn_gjsn: PoligonoGeoJSON;
}

interface UbicacionForm {
  nmbr: string;
  dscrpcn: string;
  estd: string;
}

export default function EditarUbicacion() {
  const { id } = useParams();
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const [form, setForm] = useState<UbicacionForm | null>(null);
  const [poligono, setPoligono] = useState<PoligonoGeoJSON | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // Precarga: el formulario nace con los datos actuales de la ubicación.
  useEffect(() => {
    if (!id) return;
    let cancelado = false;
    setCargando(true);

    apiFetch<UbicacionDetalle>(`/ubicaciones/${id}`)
      .then((u) => {
        if (cancelado) return;
        setForm({
          nmbr: u.nmbr,
          dscrpcn: u.dscrpcn ?? "",
          estd: u.estd,
        });
        // MapaDibujoPoligono ya sabe renderizar un polígono existente como
        // editable (vértices arrastrables); solo hay que pasárselo.
        setPoligono(u.plgn_gjsn ?? null);
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

  function actualizarCampo<K extends keyof UbicacionForm>(campo: K, valor: UbicacionForm[K]) {
    setForm((prev) => (prev ? { ...prev, [campo]: valor } : prev));
  }

  // El punto de referencia se DERIVA del contorno, ya no se teclea: pedir
  // lat/lng a mano a quien ya dibujó la zona es redundante y permite que
  // el centro quede fuera de su propio polígono (pasa hoy en la BD).
  const centro = useMemo(() => centroideDePoligono(poligono), [poligono]);

  function handleCancelar() {
    navigate("/ubicaciones");
  }

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form || !id) return;

    // Mismas reglas que el alta; el backend las repite en
    // UbicacionActualizar, esto solo evita un viaje de ida y vuelta.
    if (!form.nmbr.trim()) {
      setError("El nombre de la ubicación es obligatorio");
      return;
    }
    // El contorno es lo único que se pide: el punto sale de él.
    if (!poligono || !centro) {
      setError("Dibuja sobre el mapa el contorno de la zona (mínimo 3 vértices)");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      await apiFetch<{ mensaje: string }>(`/ubicaciones/${id}`, {
        method: "PUT",
        body: {
          nmbr: form.nmbr.trim(),
          dscrpcn: form.dscrpcn.trim() || null,
          // Derivado del contorno, no tecleado (ver `centro`).
          lttd: centro.lat,
          lngtd: centro.lng,
          plgn_gjsn: poligono,
          estd: form.estd,
          // id_sd no viaja: la sede no es editable (ver cabecera).
        },
      });

      // Mismo patrón que el alta: el mensaje viaja en el state y lo
      // muestra el listado al aterrizar.
      navigate("/ubicaciones", {
        state: { mensaje: "Ubicación actualizada correctamente" },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar la ubicación");
    } finally {
      setGuardando(false);
    }
  }

  const inputClase =
    "bg-gray-50 dark:bg-gray-800 border border-gray-300 dark:border-gray-600 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1";

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

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Editar ubicación</h1>
              <p className="text-sm text-gray-500 dark:text-gray-400">
                Modifica los datos de la zona de monitoreo y ajusta su contorno sobre el mapa.
              </p>
            </header>

            {cargando ? (
              <div className="text-sm text-gray-500 dark:text-gray-400">Cargando…</div>
            ) : !form ? (
              <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm rounded-xl">
                {error || "No se pudo cargar la ubicación"}
              </div>
            ) : (
              <form
                onSubmit={handleSubmit}
                className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-sm border border-gray-100 dark:border-gray-700"
              >
                {error && (
                  <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-100 dark:border-red-800/30 rounded-t-2xl">
                    {error}
                  </div>
                )}

                <div className="p-6 space-y-5">
                  <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                    <div>
                      <label className={labelClase} htmlFor="nmbr">
                        Nombre <span className="text-red-500">*</span>
                      </label>
                      <input
                        id="nmbr"
                        type="text"
                        maxLength={150}
                        value={form.nmbr}
                        onChange={(e) => actualizarCampo("nmbr", e.target.value)}
                        className={inputClase}
                      />
                    </div>

                    {/* Solo tiene sentido al editar: al crear, la ubicación
                        siempre nace "Activa" (server_default del modelo). */}
                    <div>
                      <label className={labelClase} htmlFor="estd">
                        Estado <span className="text-red-500">*</span>
                      </label>
                      <select
                        id="estd"
                        value={form.estd}
                        onChange={(e) => actualizarCampo("estd", e.target.value)}
                        className={inputClase + " cursor-pointer"}
                      >
                        <option value="Activa">Activa</option>
                        <option value="Inactiva">Inactiva</option>
                      </select>
                    </div>
                  </div>

                  <div>
                    <label className={labelClase} htmlFor="dscrpcn">
                      Descripción <span className="text-gray-400 font-normal">(opcional)</span>
                    </label>
                    <textarea
                      id="dscrpcn"
                      rows={2}
                      maxLength={300}
                      value={form.dscrpcn}
                      onChange={(e) => actualizarCampo("dscrpcn", e.target.value)}
                      placeholder="Referencias del punto de monitoreo, accesos, observaciones..."
                      className={inputClase}
                    />
                  </div>

                  <div>
                    <span className={labelClase}>
                      Contorno de la zona <span className="text-red-500">*</span>
                    </span>
                    {/* El componente ya renderiza un polígono existente
                        como editable (vértices arrastrables): recibe el
                        actual en `valor` y no hay que redibujarlo.
                        El punto de referencia que dibuja es el centroide
                        calculado, no un valor tecleado. */}
                    <MapaDibujoPoligono
                      valor={poligono}
                      onChange={setPoligono}
                      centroLat={centro?.lat ?? null}
                      centroLng={centro?.lng ?? null}
                    />
                    <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">
                      El punto de referencia de la zona se calcula del contorno:{" "}
                      {centro ? (
                        <span className="font-mono">
                          {centro.lat.toFixed(6)}, {centro.lng.toFixed(6)}
                        </span>
                      ) : (
                        "se definirá al cerrar el contorno."
                      )}
                    </p>
                  </div>
                </div>

                <div className="p-6 border-t border-gray-100 dark:border-gray-700 flex justify-end gap-3">
                  <button
                    type="button"
                    onClick={handleCancelar}
                    className="px-4 py-2 text-sm font-medium rounded-xl border border-gray-300 dark:border-gray-600 text-gray-700 dark:text-gray-200 hover:bg-gray-100 dark:hover:bg-gray-800 transition-colors"
                  >
                    Cancelar
                  </button>
                  <button
                    type="submit"
                    disabled={guardando}
                    className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
                  >
                    {guardando ? "Guardando..." : "Guardar cambios"}
                  </button>
                </div>
              </form>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
