import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
import "./MiPerfil.css";
import { useAuth } from "../context/AuthContext";
import { apiFetch, ApiError } from "../services/api";

interface PerfilResponse {
  nombre_completo: string;
  correo: string;
  rol: string;
  scope: string;
  estado: string;
}

function esPasswordValido(password: string): boolean {
  return password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password);
}

export default function MiPerfil() {
  const { logout, debeCambiarContrasena, marcarContrasenaCambiada } = useAuth();
  const navigate = useNavigate();

  const [perfil, setPerfil] = useState<PerfilResponse | null>(null);
  const [errorPerfil, setErrorPerfil] = useState<string | null>(null);

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
      .then(setPerfil)
      .catch((err) => setErrorPerfil(err instanceof ApiError ? err.message : "No se pudo cargar el perfil"));
  }, []);

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

  return (
    <div className="miperfil-page">
      <div className="miperfil-card">
        <header className="miperfil-header">
          <h1>Mi perfil</h1>
          {/* Con el cambio de contraseña pendiente no hay a dónde volver:
              ProtectedRoute redirige de vuelta aquí (HU04). */}
          {!debeCambiarContrasena && (
            <button className="miperfil-btn-ghost" onClick={() => navigate(-1)}>
              Volver
            </button>
          )}
        </header>

        {debeCambiarContrasena && (
          <div className="miperfil-alert" role="alert">
            <svg width="18" height="18" viewBox="0 0 24 24" fill="none" aria-hidden="true">
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

        {errorPerfil && <div className="miperfil-error">{errorPerfil}</div>}

        {perfil && (
          <section className="miperfil-panel">
            <dl className="miperfil-info">
              <dt>Nombre</dt>
              <dd>{perfil.nombre_completo}</dd>
              <dt>Correo</dt>
              <dd>{perfil.correo}</dd>
              <dt>Rol</dt>
              <dd>{perfil.rol}</dd>
              <dt>Estado</dt>
              <dd>
                <span className="miperfil-badge">{perfil.estado}</span>
              </dd>
            </dl>
          </section>
        )}

        <section className="miperfil-panel">
          {!mostrarForm ? (
            <>
              <h2 className="miperfil-panel-title">Seguridad</h2>
              <button className="miperfil-btn-primary" onClick={() => setMostrarForm(true)}>
                Cambiar contraseña
              </button>
            </>
          ) : (
            <>
              <h2 className="miperfil-panel-title">Cambiar contraseña</h2>
              <form onSubmit={handleGuardar} noValidate className="miperfil-form">
                <div className="miperfil-field">
                  <label htmlFor="contrasena-actual">Contraseña actual</label>
                  <input
                    id="contrasena-actual"
                    type={showPassword ? "text" : "password"}
                    autoComplete="current-password"
                    value={contrasenaActual}
                    onChange={(e) => setContrasenaActual(e.target.value)}
                    required
                  />
                </div>

                <div className="miperfil-field">
                  <label htmlFor="nueva-contrasena">Nueva contraseña</label>
                  <input
                    id="nueva-contrasena"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={nuevaContrasena}
                    onChange={(e) => setNuevaContrasena(e.target.value)}
                    required
                  />
                  {nuevaContrasena.length > 0 && !passwordOk && (
                    <small>Debe tener mínimo 8 caracteres, al menos 1 mayúscula y 1 número.</small>
                  )}
                </div>

                <div className="miperfil-field">
                  <label htmlFor="confirmar-contrasena">Confirmar nueva contraseña</label>
                  <input
                    id="confirmar-contrasena"
                    type={showPassword ? "text" : "password"}
                    autoComplete="new-password"
                    value={confirmarContrasena}
                    onChange={(e) => setConfirmarContrasena(e.target.value)}
                    required
                  />
                  {confirmarContrasena.length > 0 && !coinciden && (
                    <small>Las contraseñas no coinciden.</small>
                  )}
                </div>

                <label className="miperfil-checkbox">
                  <input
                    type="checkbox"
                    checked={showPassword}
                    onChange={(e) => setShowPassword(e.target.checked)}
                  />
                  Mostrar contraseñas
                </label>

                <div className="miperfil-actions">
                  <button className="miperfil-btn-primary" type="submit" disabled={loading || !puedeGuardar}>
                    {loading ? "Guardando…" : "Guardar"}
                  </button>
                  {/* Cancelar no se ofrece si el cambio es obligatorio (HU04). */}
                  {!debeCambiarContrasena && (
                    <button
                      className="miperfil-btn-secondary"
                      type="button"
                      onClick={() => setMostrarForm(false)}
                      disabled={loading}
                    >
                      Cancelar
                    </button>
                  )}
                </div>

                {formMsg && <p className={`miperfil-form-msg ${formOk ? "ok" : "err"}`}>{formMsg}</p>}
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
