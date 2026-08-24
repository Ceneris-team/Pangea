import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import MapaDibujoPoligono, { type PoligonoGeoJSON } from "../components/MapaDibujoPoligono";

/**
 * HU08 - Agregar ubicación.
 *
 *   CA1  formulario con Nombre, Descripción (opcional), Latitud, Longitud
 *        y la herramienta de dibujo del contorno de la zona
 *   CA2  "Guardar" -> POST /ubicaciones -> "Ubicación registrada correctamente"
 *   CA3  tras guardar, vuelve al listado (HU07) con la nueva ubicación
 *   CA4  "Cancelar" descarta el formulario sin llamar al backend
 *
 * Geometría (decisión de diseño del equipo): un DISPOSITIVO se ubica con
 * un punto GPS simple; una UBICACIÓN se delimita además con un polígono
 * GeoJSON de varios vértices, que dibuja el contorno real e irregular del
 * terreno. Por eso lat/lng y el polígono son ambos obligatorios: el punto
 * es la referencia/centro y el polígono el límite de la zona.
 */

interface Sede {
  id_sd: number;
  nmbr: string;
}

interface UbicacionForm {
  nmbr: string;
  dscrpcn: string;
  lttd: string;
  lngtd: string;
  id_sd: string;
}

const FORM_VACIO: UbicacionForm = {
  nmbr: "",
  dscrpcn: "",
  lttd: "",
  lngtd: "",
  id_sd: "",
};

/** Devuelve el número solo si el texto es un número válido: "" y "-" dan
 *  NaN y no deben dibujarse como coordenada 0,0 en el mapa. */
function aNumero(texto: string): number | null {
  if (texto.trim() === "") return null;
  const valor = Number(texto);
  return Number.isFinite(valor) ? valor : null;
}

export default function AgregarUbicacion() {
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const [form, setForm] = useState<UbicacionForm>(FORM_VACIO);
  const [poligono, setPoligono] = useState<PoligonoGeoJSON | null>(null);
  const [sedes, setSedes] = useState<Sede[]>([]);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // El selector de sede solo lo necesita un usuario con scope "global"
  // (ver _resolver_sede en routers/ubicaciones.py). El JWT no expone el
  // scope al frontend, así que se ofrece siempre como opcional -igual que
  // en HU06- y el backend ignora id_sd para los usuarios "por_sede".
  useEffect(() => {
    apiFetch<Sede[]>("/sedes")
      .then(setSedes)
      // Si el usuario no puede listar sedes, el formulario sigue siendo
      // usable: es un campo opcional y el backend resuelve la sede.
      .catch(() => setSedes([]));
  }, []);

  function actualizarCampo<K extends keyof UbicacionForm>(campo: K, valor: UbicacionForm[K]) {
    setForm((prev) => ({ ...prev, [campo]: valor }));
  }

  const latitud = aNumero(form.lttd);
  const longitud = aNumero(form.lngtd);

  /** CA4: descarta el formulario y vuelve al listado. No llama al backend. */
  function handleCancelar() {
    setForm(FORM_VACIO);
    setPoligono(null);
    navigate("/ubicaciones");
  }

  /** CA2 + CA3. */
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // CA2: campos obligatorios. Se valida acá para no gastar un viaje al
    // backend, pero el schema Pydantic repite las mismas reglas: este
    // chequeo es comodidad de UI, no la garantía.
    if (!form.nmbr.trim()) {
      setError("El nombre de la ubicación es obligatorio");
      return;
    }
    if (latitud === null || longitud === null) {
      setError("La latitud y la longitud son obligatorias");
      return;
    }
    if (latitud < -90 || latitud > 90) {
      setError("La latitud debe estar entre -90 y 90");
      return;
    }
    if (longitud < -180 || longitud > 180) {
      setError("La longitud debe estar entre -180 y 180");
      return;
    }
    if (!poligono) {
      setError("Dibuja sobre el mapa el contorno de la zona (mínimo 3 vértices)");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      await apiFetch<{ mensaje: string }>("/ubicaciones", {
        method: "POST",
        body: {
          nmbr: form.nmbr.trim(),
          dscrpcn: form.dscrpcn.trim() || null,
          lttd: latitud,
          lngtd: longitud,
          plgn_gjsn: poligono,
          ...(form.id_sd ? { id_sd: Number(form.id_sd) } : {}),
        },
      });

      // CA3: volver al listado (HU07), que recarga y ya muestra la nueva
      // ubicación. El mensaje de éxito viaja en el state para que el
      // listado lo muestre sin necesidad de una pantalla intermedia.
      navigate("/ubicaciones", {
        state: { mensaje: "Ubicación registrada correctamente" },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo registrar la ubicación");
    } finally {
      setGuardando(false);
    }
  }

  const inputClase =
    "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl focus:ring-[#ccff00] focus:border-[#ccff00] block w-full p-2.5 outline-none";
  const labelClase = "block text-sm font-medium text-gray-700 dark:text-gray-200 mb-1";

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="ubicaciones" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar
            nombreCompleto={nombreCompleto}
            rol={rol}
            />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Agregar ubicación</h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Registra una nueva zona de monitoreo y delimita su contorno sobre el mapa.
              </p>
            </header>

            <form
              onSubmit={handleSubmit}
              className="bg-white/70 dark:bg-white/[0.04] backdrop-blur-md rounded-2xl shadow-sm border border-black/10 dark:border-white/10"
            >
              {error && (
                <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30 rounded-t-2xl">
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
                      placeholder="Estación Río Rímac"
                      className={inputClase}
                    />
                  </div>

                  {sedes.length > 0 && (
                    <div>
                      <label className={labelClase} htmlFor="id_sd">
                        Sede
                      </label>
                      <select
                        id="id_sd"
                        value={form.id_sd}
                        onChange={(e) => actualizarCampo("id_sd", e.target.value)}
                        className={inputClase + " cursor-pointer"}
                      >
                        <option value="">Mi sede</option>
                        {sedes.map((s) => (
                          <option key={s.id_sd} value={s.id_sd}>
                            {s.nmbr}
                          </option>
                        ))}
                      </select>
                    </div>
                  )}
                </div>

                <div>
                  <label className={labelClase} htmlFor="dscrpcn">
                    Descripción <span className="text-gray-500 dark:text-gray-400 font-normal">(opcional)</span>
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

                <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
                  <div>
                    <label className={labelClase} htmlFor="lttd">
                      Latitud <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="lttd"
                      type="number"
                      step="any"
                      min={-90}
                      max={90}
                      value={form.lttd}
                      onChange={(e) => actualizarCampo("lttd", e.target.value)}
                      placeholder="-12.046400"
                      className={inputClase}
                    />
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">Entre -90 y 90.</p>
                  </div>
                  <div>
                    <label className={labelClase} htmlFor="lngtd">
                      Longitud <span className="text-red-500">*</span>
                    </label>
                    <input
                      id="lngtd"
                      type="number"
                      step="any"
                      min={-180}
                      max={180}
                      value={form.lngtd}
                      onChange={(e) => actualizarCampo("lngtd", e.target.value)}
                      placeholder="-77.042800"
                      className={inputClase}
                    />
                    <p className="mt-1 text-xs text-gray-600 dark:text-gray-300">
                      Entre -180 y 180.
                    </p>
                  </div>
                </div>

                <div>
                  <span className={labelClase}>
                    Contorno de la zona <span className="text-red-500">*</span>
                  </span>
                  <MapaDibujoPoligono
                    valor={poligono}
                    onChange={setPoligono}
                    centroLat={latitud}
                    centroLng={longitud}
                  />
                </div>
              </div>

              <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
                {/* CA4: no toca el backend, solo descarta y vuelve. */}
                <button
                  type="button"
                  onClick={handleCancelar}
                  className="px-4 py-2 text-sm font-medium rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 hover:bg-black/10 dark:hover:bg-white/10 transition-colors"
                >
                  Cancelar
                </button>
                <button
                  type="submit"
                  disabled={guardando}
                  className="px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50 transition-colors"
                >
                  {guardando ? "Guardando..." : "Guardar ubicación"}
                </button>
              </div>
            </form>
          </main>
        </div>
      </div>
    </div>
  );
}
