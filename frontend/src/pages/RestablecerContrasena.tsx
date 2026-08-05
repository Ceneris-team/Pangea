import { useState, type FormEvent } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import "./login.css";
import { apiFetch, ApiError } from "../services/api";

// HU 02, detalle de conversación: "La nueva contraseña debe tener mínimo 8
// caracteres, al menos 1 letra mayúscula y 1 número."
function esPasswordValido(password: string): boolean {
  return password.length >= 8 && /[A-Z]/.test(password) && /[0-9]/.test(password);
}

export default function RestablecerContrasena() {
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") ?? "";
  const navigate = useNavigate();

  const [nuevaContrasena, setNuevaContrasena] = useState("");
  const [confirmarContrasena, setConfirmarContrasena] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [formMsg, setFormMsg] = useState("");
  const [formOk, setFormOk] = useState(false);
  const [loading, setLoading] = useState(false);

  const passwordOk = esPasswordValido(nuevaContrasena);
  // HU 02, detalle de conversación: "El campo confirmar contraseña debe
  // coincidir exactamente con el campo nueva contraseña para habilitar el
  // botón de confirmación."
  const coinciden = confirmarContrasena.length > 0 && nuevaContrasena === confirmarContrasena;
  const puedeEnviar = !!token && passwordOk && coinciden;

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    if (!puedeEnviar) return;

    setFormMsg("");
    setFormOk(false);
    setLoading(true);
    try {
      const data = await apiFetch<{ mensaje: string }>("/auth/restablecer-contrasena", {
        method: "POST",
        body: {
          token,
          nueva_contrasena: nuevaContrasena,
          confirmar_contrasena: confirmarContrasena,
        },
      });
      setFormMsg(data.mensaje);
      setFormOk(true);
      // HU 02 CA 2: "...el sistema actualiza la contraseña, muestra el MSG
      // ...y me redirige a la pantalla de inicio de sesión."
      setTimeout(() => navigate("/login", { replace: true }), 1800);
    } catch (err) {
      setFormMsg(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
      setFormOk(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div className="stage">
        <div className="panel" style={{ margin: "0 auto" }}>
          <div className="card">
            <p className="eyebrow">Pangea · Recuperar acceso</p>
            <h1>Cambiar contraseña</h1>
            <p className="sub">Ingresa y confirma tu nueva contraseña.</p>

            {!token && (
              <p className="form-msg">
                Este enlace no es válido. Solicita uno nuevo desde{" "}
                <Link to="/olvide-contrasena" className="link">
                  ¿Olvidaste tu contraseña?
                </Link>
              </p>
            )}

            <form onSubmit={handleSubmit} noValidate>
              <div className="field">
                <label htmlFor="nueva">Nueva contraseña</label>
                <div className="input-wrap">
                  <input
                    type={showPassword ? "text" : "password"}
                    id="nueva"
                    autoComplete="new-password"
                    placeholder="Mínimo 8 caracteres, 1 mayúscula y 1 número"
                    value={nuevaContrasena}
                    onChange={(e) => setNuevaContrasena(e.target.value)}
                    required
                  />
                  <button
                    type="button"
                    className="toggle-visibility"
                    aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
                    onClick={() => setShowPassword((v) => !v)}
                  >
                    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={1.6}>
                      <path d="M1.5 12S5 5 12 5s10.5 7 10.5 7-3.5 7-10.5 7S1.5 12 1.5 12Z" />
                      <circle cx={12} cy={12} r={3} />
                    </svg>
                  </button>
                </div>
                {nuevaContrasena.length > 0 && !passwordOk && (
                  <p className="field-error">
                    Debe tener mínimo 8 caracteres, al menos 1 mayúscula y 1 número.
                  </p>
                )}
              </div>

              <div className="field">
                <label htmlFor="confirmar">Confirmar contraseña</label>
                <div className="input-wrap">
                  <input
                    type={showPassword ? "text" : "password"}
                    id="confirmar"
                    autoComplete="new-password"
                    placeholder="Repite la nueva contraseña"
                    value={confirmarContrasena}
                    onChange={(e) => setConfirmarContrasena(e.target.value)}
                    required
                  />
                </div>
                {confirmarContrasena.length > 0 && !coinciden && (
                  <p className="field-error">Las contraseñas no coinciden.</p>
                )}
              </div>

              <button type="submit" className="submit" disabled={loading || !puedeEnviar}>
                {loading ? "Guardando…" : "Cambiar contraseña"}
              </button>
              <p className={`form-msg${formOk ? " ok" : ""}`}>{formMsg}</p>
            </form>
          </div>
        </div>
      </div>
    </div>
  );
}
