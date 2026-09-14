import { useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiFetch, ApiError } from "../services/api";

/**
 * Ventana emergente obligatoria de cambio de contraseña (HU04): se muestra
 * mientras el usuario siga con la contraseña temporal generada al crearse
 * su cuenta, en vez de mandarlo a una página aparte. Sigue el mismo patrón
 * visual que ConfirmarEliminacionModal (overlay + tarjeta con Tailwind).
 */

function esPasswordValido(password: string): boolean {
  return password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password);
}

const inputClass =
  "w-full rounded-xl border border-gray-300 dark:border-gray-600 bg-white dark:bg-[#1f2733] px-3 py-2.5 text-sm text-gray-900 dark:text-white focus:outline-none focus:ring-2 focus:ring-[#ccff00]/50";

export default function CambiarContrasenaModal() {
  const { logout, marcarContrasenaCambiada } = useAuth();
  const navigate = useNavigate();

  const [contrasenaActual, setContrasenaActual] = useState("");
  const [nuevaContrasena, setNuevaContrasena] = useState("");
  const [confirmarContrasena, setConfirmarContrasena] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [formMsg, setFormMsg] = useState("");
  const [formOk, setFormOk] = useState(false);
  const [loading, setLoading] = useState(false);

  const passwordOk = esPasswordValido(nuevaContrasena);
  const coinciden = confirmarContrasena.length > 0 && nuevaContrasena === confirmarContrasena;
  const puedeGuardar = contrasenaActual.length > 0 && passwordOk && coinciden;

  async function handleGuardar(e: FormEvent) {
    e.preventDefault();
    if (!puedeGuardar) return;

    setFormMsg("");
    setFormOk(false);
    setLoading(true);
    try {
      const data = await apiFetch<{ mensaje: string }>("/auth/cambiar-contrasena", {
        method: "PUT",
        body: {
          contrasena_actual: contrasenaActual,
          nueva_contrasena: nuevaContrasena,
          confirmar_contrasena: confirmarContrasena,
        },
      });
      setFormMsg(data.mensaje);
      setFormOk(true);
      marcarContrasenaCambiada();
      // El cambio de contraseña invalida la sesión actual: se cierra sesión
      // localmente y se vuelve al login para que ingrese con la nueva.
      setTimeout(() => {
        logout();
        navigate("/login", { replace: true, state: { contrasenaActualizada: true } });
      }, 1500);
    } catch (err) {
      setFormMsg(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
      setFormOk(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 p-4">
      <div className="bg-white dark:bg-[#2d3748] rounded-2xl shadow-xl border border-gray-200 dark:border-gray-700 max-w-md w-full p-6">
        <div className="flex items-start gap-3 mb-4">
          <div className="flex-shrink-0 w-10 h-10 rounded-full flex items-center justify-center bg-[#ccff00]/20 dark:bg-[#ccff00]/10">
            <svg
              className="w-5 h-5 text-[#5a7000] dark:text-[#ccff00]"
              fill="none"
              viewBox="0 0 24 24"
              strokeWidth="2"
              stroke="currentColor"
            >
              <path
                strokeLinecap="round"
                strokeLinejoin="round"
                d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"
              />
            </svg>
          </div>
          <div>
            <h2 className="text-base font-bold text-gray-900 dark:text-white">Cambia tu contraseña</h2>
            <p className="text-sm text-gray-500 dark:text-gray-400 mt-1">
              Estás usando una contraseña temporal. Debes cambiarla antes de continuar.
            </p>
          </div>
        </div>

        <form onSubmit={handleGuardar} noValidate className="space-y-4">
          <div>
            <label
              htmlFor="modal-contrasena-actual"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Contraseña actual
            </label>
            <input
              id="modal-contrasena-actual"
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              value={contrasenaActual}
              onChange={(e) => setContrasenaActual(e.target.value)}
              required
              className={inputClass}
            />
          </div>

          <div>
            <label
              htmlFor="modal-nueva-contrasena"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Nueva contraseña
            </label>
            <input
              id="modal-nueva-contrasena"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={nuevaContrasena}
              onChange={(e) => setNuevaContrasena(e.target.value)}
              required
              className={inputClass}
            />
            {nuevaContrasena.length > 0 && !passwordOk && (
              <p className="text-xs text-red-500 mt-1">
                Debe tener mínimo 8 caracteres, al menos 1 mayúscula y 1 número.
              </p>
            )}
          </div>

          <div>
            <label
              htmlFor="modal-confirmar-contrasena"
              className="block text-sm font-medium text-gray-700 dark:text-gray-300 mb-1"
            >
              Confirmar nueva contraseña
            </label>
            <input
              id="modal-confirmar-contrasena"
              type={showPassword ? "text" : "password"}
              autoComplete="new-password"
              value={confirmarContrasena}
              onChange={(e) => setConfirmarContrasena(e.target.value)}
              required
              className={inputClass}
            />
            {confirmarContrasena.length > 0 && !coinciden && (
              <p className="text-xs text-red-500 mt-1">Las contraseñas no coinciden.</p>
            )}
          </div>

          <label className="flex items-center gap-2 text-sm text-gray-600 dark:text-gray-300">
            <input
              type="checkbox"
              checked={showPassword}
              onChange={(e) => setShowPassword(e.target.checked)}
              className="rounded border-gray-300 dark:border-gray-600"
            />
            Mostrar contraseñas
          </label>

          {formMsg && (
            <p className={`text-sm ${formOk ? "text-green-600 dark:text-[#ccff00]" : "text-red-500"}`}>
              {formMsg}
            </p>
          )}

          <div className="flex justify-end gap-3 mt-5">
            <button
              type="submit"
              disabled={loading || !puedeGuardar}
              className="px-4 py-2.5 text-sm font-semibold rounded-xl text-[#5a7000] dark:text-[#ccff00] bg-[#ccff00]/10 hover:bg-[#ccff00]/20 border border-[#ccff00]/30 disabled:opacity-50 disabled:cursor-not-allowed transition-all"
            >
              {loading ? "Guardando…" : "Guardar"}
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
