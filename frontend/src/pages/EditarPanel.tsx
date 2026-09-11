import { useEffect, useState, type FormEvent } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU25 - Editar panel.
 *
 *   CA1  formulario de edición con el nombre actual precargado
 *   CA2  "GUARDAR" -> PUT /paneles/{id} -> "Panel actualizado correctamente"
 *
 * Mismo formulario de un solo campo que CrearPanel.tsx, con precarga desde
 * GET /paneles/{id} (ya existe desde HU23) -mismo patrón que
 * EditarUbicacion.tsx respecto de AgregarUbicacion.tsx-.
 */

interface PanelDetalle {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

const NOMBRE_MAX_LARGO = 100;

export default function EditarPanel() {
  const { id } = useParams<{ id: string }>();
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  // Mismo criterio que CrearPanel.tsx: editar un panel es exclusivo del
  // rol Cliente Final. Pendiente conocido (fuera de esta tarea): pasar
  // esto a un guard en tiempo de render en vez de useEffect, para evitar
  // el flash del formulario -ver la nota en CrearPanel.tsx-.
  useEffect(() => {
    if (rol !== null && rol !== ROLES.CLIENTE_FINAL) {
      navigate("/paneles", { replace: true });
    }
  }, [rol, navigate]);

  const [nombre, setNombre] = useState("");
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [panelEncontrado, setPanelEncontrado] = useState(false);

  // CA1: precarga el nombre actual del panel.
  useEffect(() => {
    if (!id) return;
    let cancelado = false;
    setCargando(true);

    apiFetch<PanelDetalle>(`/paneles/${id}`)
      .then((panel) => {
        if (cancelado) return;
        setNombre(panel.nmbr);
        setPanelEncontrado(true);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el panel");
      })
      .finally(() => {
        if (!cancelado) setCargando(false);
      });

    return () => {
      cancelado = true;
    };
  }, [id]);

  function handleCancelar() {
    navigate("/paneles");
  }

  /** CA2. */
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!id) return;

    if (!nombre.trim()) {
      setError("El nombre del panel es obligatorio");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      const respuesta = await apiFetch<{ mensaje: string }>(`/paneles/${id}`, {
        method: "PUT",
        body: { nmbr: nombre.trim() },
      });

      // Mismo patrón que Ubicaciones.tsx: el mensaje viaja en el state y
      // lo muestra el listado al aterrizar.
      navigate("/paneles", { state: { mensaje: respuesta.mensaje } });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar el panel");
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
        <Sidebar onLogout={logout} activo="paneles" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="franja-superior flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Editar panel</h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Modifica el nombre de tu tablero personalizado.
              </p>
            </header>

            {cargando ? (
              <div className="flex justify-center items-center gap-2 py-16 text-gray-600 dark:text-gray-300">
                <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                <span>Cargando panel...</span>
              </div>
            ) : !panelEncontrado ? (
              <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error || "No se pudo cargar el panel"}
              </div>
            ) : (
              <form
                onSubmit={handleSubmit}
                className="max-w-xl bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10"
              >
                {error && (
                  <div className="p-4 bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm border-b border-red-200 dark:border-red-800/30 rounded-t-2xl">
                    {error}
                  </div>
                )}

                <div className="p-6">
                  <label className={labelClase} htmlFor="nmbr">
                    Nombre del panel <span className="text-red-500">*</span>
                  </label>
                  <input
                    id="nmbr"
                    type="text"
                    maxLength={NOMBRE_MAX_LARGO}
                    value={nombre}
                    onChange={(e) => setNombre(e.target.value)}
                    autoFocus
                    className={inputClase}
                  />
                  <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                    {nombre.length}/{NOMBRE_MAX_LARGO}
                  </p>
                </div>

                <div className="p-6 border-t border-black/10 dark:border-white/10 flex justify-end gap-3">
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
                    {guardando ? "Guardando..." : "Guardar"}
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
