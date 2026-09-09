import { useState, type FormEvent } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import { ROLES } from "../config/roles";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

/**
 * HU24 - Crear panel.
 *
 *   CA1  formulario con el campo Nombre del panel
 *   CA2  "GUARDAR" -> POST /paneles -> "Panel creado correctamente"
 *   CA3  tras guardar, redirige al panel recién creado (vacío, con
 *        "Añadir ubicaciones" visible pero sin funcionalidad real)
 *   CA4  "CANCELAR" descarta el formulario sin llamar al backend
 */

interface PanelCreado {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

const NOMBRE_MAX_LARGO = 100;

export default function CrearPanel() {
  const navigate = useNavigate();
  const { nombreCompleto, rol, logout } = useAuth();

  const [nombre, setNombre] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");

  // HU24 (regla de rol confirmada): "YO COMO Cliente Final..." -crear un
  // panel es exclusivo de ese rol. Paneles.tsx ya oculta el botón que
  // trae hasta acá, pero alguien puede llegar por URL directa/favorito;
  // el backend igual devuelve 403 al hacer POST, esto solo evita mostrar
  // el formulario completo a quien nunca podría guardarlo. No hay un
  // ProtectedRoute con rolesPermitidos para esto porque ese mecanismo
  // redirige a /login -acá el destino correcto es /paneles, no login-.
  //
  // Guard en tiempo de RENDER, no useEffect: un efecto corre DESPUÉS del
  // primer render, así que el JSX del formulario llegaba a montarse en
  // el DOM -aunque fuera un instante- antes de que el efecto disparara el
  // redirect. Devolver <Navigate> acá corta el render ANTES de llegar al
  // return del formulario, mismo patrón que ya usa ProtectedRoute.tsx.
  if (rol !== null && rol !== ROLES.CLIENTE_FINAL) {
    return <Navigate to="/paneles" replace />;
  }

  /** CA4: descarta el formulario y vuelve al listado. No llama al backend. */
  function handleCancelar() {
    navigate("/paneles");
  }

  /** CA2 + CA3. */
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();

    // CA2: el nombre es obligatorio. Comodidad de UI -el schema Pydantic
    // repite la misma regla, que es la garantía real- para no gastar un
    // viaje al backend con un campo vacío.
    if (!nombre.trim()) {
      setError("El nombre del panel es obligatorio");
      return;
    }

    setGuardando(true);
    setError("");
    try {
      const respuesta = await apiFetch<{ mensaje: string; panel: PanelCreado }>("/paneles", {
        method: "POST",
        body: { nmbr: nombre.trim() },
      });

      // CA3: redirige al panel recién creado, no al listado -a
      // diferencia de Ubicaciones-, con el mensaje de éxito en el state.
      navigate(`/paneles/${respuesta.panel.id_pnl}`, {
        state: { mensaje: respuesta.mensaje },
      });
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo crear el panel");
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
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <header className="mb-6">
              <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Crear panel</h1>
              <p className="text-sm text-gray-600 dark:text-gray-300">
                Dale un nombre a tu nuevo tablero personalizado.
              </p>
            </header>

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
                  placeholder="Resumen de estaciones"
                  autoFocus
                  className={inputClase}
                />
                <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
                  {nombre.length}/{NOMBRE_MAX_LARGO}
                </p>
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
                  {guardando ? "Guardando..." : "Guardar"}
                </button>
              </div>
            </form>
          </main>
        </div>
      </div>
    </div>
  );
}
