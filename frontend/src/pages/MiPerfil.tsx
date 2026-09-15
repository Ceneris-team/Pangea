import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import { useAuth } from "../context/AuthContext";
import { apiFetch, ApiError } from "../services/api";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface PerfilResponse {
  nombre_completo: string;
  correo: string;
  rol: string;
  scope: string;
  estado: string;
  zona_horaria: string;
}

interface ZonasHorariasResponse {
  zonas_horarias: string[];
}

function esPasswordValido(password: string): boolean {
  return password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password);
}

const CLASE_INPUT =
  "bg-black/5 dark:bg-white/5 border border-black/10 dark:border-white/20 text-gray-900 dark:text-white text-sm rounded-xl block w-full p-2.5 outline-none focus:ring-1 focus:ring-[#ccff00] focus:border-[#ccff00] transition-all";
const CLASE_LABEL = "block text-sm text-gray-700 dark:text-gray-200 mb-1";

export default function MiPerfil() {
  const { nombreCompleto, rol, logout, debeCambiarContrasena, marcarContrasenaCambiada, actualizarZonaHoraria } =
    useAuth();
  const navigate = useNavigate();

  const [perfil, setPerfil] = useState<PerfilResponse | null>(null);
  const [errorPerfil, setErrorPerfil] = useState<string | null>(null);

  // HU14: selector de zona horaria en "Mi perfil".
  const [zonasHorarias, setZonasHorarias] = useState<string[]>([]);
  const [zonaSeleccionada, setZonaSeleccionada] = useState("");
  const [zonaMsg, setZonaMsg] = useState("");
  const [zonaOk, setZonaOk] = useState(false);
  const [guardandoZona, setGuardandoZona] = useState(false);

  // HU04: si viene de un primer login con contraseña temporal, el formulario
  // de cambio arranca abierto y no se puede cancelar (ProtectedRoute lo
  // devuelve aquí mientras el flag siga activo).
  const [mostrarForm, setMostrarForm] = useState(debeCambiarContrasena);
  const [contrasenaActual, setContrasenaActual] = useState("");
  const [nuevaContrasena, setNuevaContrasena] = useState("");
  const [confirmarContrasena, setConfirmarContrasena] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [formMsg, setFormMsg] = useState("");
  const [formOk, setFormOk] = useState(false);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    apiFetch<PerfilResponse>("/auth/perfil")
      .then((data) => {
        setPerfil(data);
        setZonaSeleccionada(data.zona_horaria);
      })
      .catch((err) => setErrorPerfil(err instanceof ApiError ? err.message : "No se pudo cargar el perfil"));

    apiFetch<ZonasHorariasResponse>("/auth/zonas-horarias")
      .then((data) => setZonasHorarias(data.zonas_horarias))
      .catch(() => setZonasHorarias([]));
  }, []);

  // HU14 CA2: guarda la zona horaria elegida y actualiza el contexto para
  // que el resto de la app (p. ej. el módulo de consulta) la use de inmediato.
  async function handleGuardarZonaHoraria(e: FormEvent) {
    e.preventDefault();
    if (!zonaSeleccionada || zonaSeleccionada === perfil?.zona_horaria) return;

    setZonaMsg("");
    setZonaOk(false);
    setGuardandoZona(true);
    try {
      const data = await apiFetch<{ mensaje: string; zona_horaria: string }>("/auth/zona-horaria", {
        method: "PUT",
        body: { zona_horaria: zonaSeleccionada },
      });
      setZonaMsg(data.mensaje);
      setZonaOk(true);
      setPerfil((prev) => (prev ? { ...prev, zona_horaria: data.zona_horaria } : prev));
      actualizarZonaHoraria(data.zona_horaria);
    } catch (err) {
      setZonaMsg(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
      setZonaOk(false);
    } finally {
      setGuardandoZona(false);
    }
  }

  const passwordOk = esPasswordValido(nuevaContrasena);
  const coinciden = confirmarContrasena.length > 0 && nuevaContrasena === confirmarContrasena;
  const puedeGuardar = contrasenaActual.length > 0 && passwordOk && coinciden;

  // HU 02 CA 3: "...ingreso mi contraseña actual, la nueva contraseña, la
  // confirmo y selecciono 'GUARDAR', ENTONCES el sistema actualiza la
  // contraseña y muestra el MSG 'Contraseña actualizada exitosamente'."
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
      // Levanta el bloqueo de HU04 (contraseña temporal ya cambiada) para
      // que ProtectedRoute no siga redirigiendo aquí en el intervalo previo
      // al logout.
      marcarContrasenaCambiada();
      // El cambio de contraseña invalida la sesión actual: se cierra sesión
      // localmente y se vuelve al login.
      setTimeout(() => {
        logout();
        navigate("/login", { replace: true });
      }, 1500);
    } catch (err) {
      setFormMsg(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
      setFormOk(false);
    } finally {
      setLoading(false);
    }
  }

  const contenido = (
    <div className="max-w-xl">
      <header className="flex items-center justify-between mb-6">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-white">Mi perfil</h1>
        {/* Con el cambio de contraseña pendiente no hay a dónde volver:
            ProtectedRoute redirige de vuelta aquí (HU04). */}
        {!debeCambiarContrasena && (
          <button
            type="button"
            onClick={() => navigate(-1)}
            className="px-4 py-2 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/5 dark:hover:bg-white/10 transition-all"
          >
            Volver
          </button>
        )}
      </header>

      {debeCambiarContrasena && (
        <div
          role="alert"
          className="flex items-start gap-2.5 mb-5 p-4 rounded-xl bg-amber-50 dark:bg-amber-900/20 border border-amber-300/50 dark:border-amber-800/40 text-amber-700 dark:text-amber-400 text-sm"
        >
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true" className="shrink-0 mt-0.5">
            <path
              d="M12 9v4m0 4h.01M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"
              stroke="currentColor"
              strokeWidth="1.6"
              strokeLinecap="round"
              strokeLinejoin="round"
            />
          </svg>
          <span>Estás usando una contraseña temporal. Debes cambiarla antes de continuar.</span>
        </div>
      )}

      {errorPerfil && (
        <div className="mb-4 p-3 rounded-xl bg-red-50 dark:bg-red-900/20 border border-red-200 dark:border-red-800/30 text-red-600 dark:text-red-400 text-sm">
          {errorPerfil}
        </div>
      )}

      {perfil && (
        <section className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 mb-5">
          <dl className="grid grid-cols-[auto_1fr] gap-y-3 gap-x-4 text-sm">
            <dt className="text-gray-500 dark:text-gray-400 font-medium">Nombre</dt>
            <dd className="m-0 text-gray-900 dark:text-white">{perfil.nombre_completo}</dd>
            <dt className="text-gray-500 dark:text-gray-400 font-medium">Correo</dt>
            <dd className="m-0 text-gray-900 dark:text-white">{perfil.correo}</dd>
            <dt className="text-gray-500 dark:text-gray-400 font-medium">Rol</dt>
            <dd className="m-0 text-gray-900 dark:text-white">{perfil.rol}</dd>
            <dt className="text-gray-500 dark:text-gray-400 font-medium">Estado</dt>
            <dd className="m-0">
              <span className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-semibold bg-[#ccff00]/20 text-[#5a7000] dark:text-[#ccff00] border border-[#8fb300]/40 dark:border-[#ccff00]/30">
                <span className="w-1.5 h-1.5 rounded-full bg-current" />
                {perfil.estado}
              </span>
            </dd>
          </dl>
        </section>
      )}

      <section className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6 mb-5">
        <h2 className="text-sm font-bold text-gray-900 dark:text-white mb-4">Zona horaria</h2>
        <form onSubmit={handleGuardarZonaHoraria} className="grid gap-4">
          <div>
            <label htmlFor="zona-horaria" className={CLASE_LABEL}>
              Zona horaria
            </label>
            <select
              id="zona-horaria"
              value={zonaSeleccionada}
              onChange={(e) => setZonaSeleccionada(e.target.value)}
              className={`${CLASE_INPUT} cursor-pointer`}
            >
              {zonaSeleccionada && !zonasHorarias.includes(zonaSeleccionada) && (
                <option value={zonaSeleccionada}>{zonaSeleccionada}</option>
              )}
              {zonasHorarias.map((zona) => (
                <option key={zona} value={zona}>
                  {zona}
                </option>
              ))}
            </select>
          </div>

          <div className="flex gap-3 items-center">
            <button
              type="submit"
              disabled={guardandoZona || !zonaSeleccionada || zonaSeleccionada === perfil?.zona_horaria}
              className="px-5 py-2.5 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:opacity-90 disabled:opacity-45 disabled:cursor-not-allowed transition-opacity"
            >
              {guardandoZona ? "Guardando…" : "Guardar"}
            </button>
          </div>

          {zonaMsg && (
            <p className={`text-sm m-0 ${zonaOk ? "text-[#5a7000] dark:text-[#ccff00]" : "text-red-600 dark:text-red-400"}`}>
              {zonaMsg}
            </p>
          )}
        </form>
      </section>

      <section className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 p-6">
        {!mostrarForm ? (
          <>
            <h2 className="text-sm font-bold text-gray-900 dark:text-white mb-4">Seguridad</h2>
            <button
              type="button"
              onClick={() => setMostrarForm(true)}
              className="px-5 py-2.5 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:opacity-90 transition-opacity"
            >
              Cambiar contraseña
            </button>
          </>
        ) : (
          <>
            <h2 className="text-sm font-bold text-gray-900 dark:text-white mb-4">Cambiar contraseña</h2>
            <form onSubmit={handleGuardar} noValidate className="grid gap-4">
              <div>
                <label htmlFor="contrasena-actual" className={CLASE_LABEL}>
                  Contraseña actual
                </label>
                <input
                  id="contrasena-actual"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  value={contrasenaActual}
                  onChange={(e) => setContrasenaActual(e.target.value)}
                  required
                  className={CLASE_INPUT}
                />
              </div>

              <div>
                <label htmlFor="nueva-contrasena" className={CLASE_LABEL}>
                  Nueva contraseña
                </label>
                <input
                  id="nueva-contrasena"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={nuevaContrasena}
                  onChange={(e) => setNuevaContrasena(e.target.value)}
                  required
                  className={CLASE_INPUT}
                />
                {nuevaContrasena.length > 0 && !passwordOk && (
                  <small className="block mt-1 text-xs text-red-600 dark:text-red-400">
                    Debe tener mínimo 8 caracteres, al menos 1 mayúscula y 1 número.
                  </small>
                )}
              </div>

              <div>
                <label htmlFor="confirmar-contrasena" className={CLASE_LABEL}>
                  Confirmar nueva contraseña
                </label>
                <input
                  id="confirmar-contrasena"
                  type={showPassword ? "text" : "password"}
                  autoComplete="new-password"
                  value={confirmarContrasena}
                  onChange={(e) => setConfirmarContrasena(e.target.value)}
                  required
                  className={CLASE_INPUT}
                />
                {confirmarContrasena.length > 0 && !coinciden && (
                  <small className="block mt-1 text-xs text-red-600 dark:text-red-400">
                    Las contraseñas no coinciden.
                  </small>
                )}
              </div>

              <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-200 cursor-pointer">
                <input
                  type="checkbox"
                  checked={showPassword}
                  onChange={(e) => setShowPassword(e.target.checked)}
                  className="accent-[#ccff00]"
                />
                Mostrar contraseñas
              </label>

              <div className="flex gap-3 items-center">
                <button
                  type="submit"
                  disabled={loading || !puedeGuardar}
                  className="px-5 py-2.5 rounded-xl bg-[#ccff00] text-gray-900 text-sm font-bold hover:opacity-90 disabled:opacity-45 disabled:cursor-not-allowed transition-opacity"
                >
                  {loading ? "Guardando…" : "Guardar"}
                </button>
                {/* Cancelar no se ofrece si el cambio es obligatorio (HU04). */}
                {!debeCambiarContrasena && (
                  <button
                    type="button"
                    onClick={() => setMostrarForm(false)}
                    disabled={loading}
                    className="px-5 py-2.5 rounded-xl border border-black/20 dark:border-white/20 text-gray-700 dark:text-gray-200 text-sm font-bold hover:bg-black/5 dark:hover:bg-white/10 disabled:opacity-45 disabled:cursor-not-allowed transition-all"
                  >
                    Cancelar
                  </button>
                )}
              </div>

              {formMsg && (
                <p className={`text-sm m-0 ${formOk ? "text-[#5a7000] dark:text-[#ccff00]" : "text-red-600 dark:text-red-400"}`}>
                  {formMsg}
                </p>
              )}
            </form>
          </>
        )}
      </section>
    </div>
  );

  // Con el cambio de contraseña pendiente (HU04) no hay Sidebar/Topbar
  // útiles todavía -el resto de la app sigue bloqueada-, así que la página
  // se centra sola, igual que Login; fuera de ese caso usa el layout
  // estándar del dashboard para heredar el mismo tema claro/oscuro.
  if (debeCambiarContrasena) {
    return (
      <div className="min-h-screen flex items-center justify-center p-6 bg-gray-50 dark:bg-[#1a202c]">
        {contenido}
      </div>
    );
  }

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="mi-perfil" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">{contenido}</main>
        </div>
      </div>
    </div>
  );
}
