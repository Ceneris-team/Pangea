import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import "./Login.css";
import { useAuth } from "../context/AuthContext";
import { rutaPorRol } from "../config/roles";
import { ApiError } from "../services/api";
import loginBg from "../assets/login-bg.jpg";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function Login() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const [correo, setCorreo] = useState("");
  const [contrasena, setContrasena] = useState("");
  const [remember, setRemember] = useState(false);
  const [showPassword, setShowPassword] = useState(false);

  const [emailError, setEmailError] = useState(false);
  const [passwordError, setPasswordError] = useState(false);
  const [formMsg, setFormMsg] = useState("");
  const [formOk, setFormOk] = useState(false);
  const [loading, setLoading] = useState(false);

  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormMsg("");
    setFormOk(false);

    const emailOk = isValidEmail(correo.trim());
    const passwordOk = contrasena.length > 0;
    setEmailError(!emailOk);
    setPasswordError(!passwordOk);
    if (!emailOk || !passwordOk) return;

    setLoading(true);
    try {
      const data = await login(correo.trim(), contrasena, remember);

      setFormMsg(`Bienvenido, ${data.nombre_completo}`);
      setFormOk(true);

      // HU04: la contraseña temporal generada al crear el usuario "deberá
      // cambiarla en su primer inicio de sesión". Se le manda al formulario
      // de cambio de contraseña (HU02 CA3) en vez de al panel de su rol;
      // ProtectedRoute mantiene el bloqueo si intenta navegar a otra ruta.
      if (data.debe_cambiar_contrasena) {
        navigate("/mi-perfil", { replace: true });
        return;
      }

      // HU01 CA: "el sistema me autentica y me redirige al panel principal
      // correspondiente a mi rol."
      navigate(rutaPorRol(data.rol), { replace: true });
    } catch (err) {
      setFormMsg(err instanceof ApiError ? err.message : "Correo o contraseña incorrectos");
      setFormOk(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
      <div
        className="bg-photo"
        style={{ backgroundImage: `url(${loginBg})` }}
        aria-hidden="true"
      >
        <div className="bg-photo-tint" />
      </div>

      <div className="stage">
        <div className="canopy">
          <div className="canopy-tag">
            <b>Pangea 4.0</b>
            Monitoreo ambiental en tiempo real
          </div>
        </div>

        <div className="panel">
          <div className="card">
            <p className="eyebrow">Pangea · Plataforma de monitoreo</p>
            <h1>Bienvenido de nuevo</h1>
            <p className="sub">Ingresa tus credenciales para continuar.</p>

            <form onSubmit={handleSubmit} noValidate>
              <div className={`field${emailError ? " has-error" : ""}`}>
                <label htmlFor="email">Correo electrónico</label>
                <div className="input-wrap">
                  <input
                    type="email"
                    id="email"
                    autoComplete="username"
                    placeholder="Ingresa tu correo"
                    value={correo}
                    onChange={(e) => setCorreo(e.target.value)}
                    required
                  />
                </div>
                {emailError && <p className="field-error">Ingresa un correo electrónico válido.</p>}
              </div>

              <div className={`field${passwordError ? " has-error" : ""}`}>
                <label htmlFor="password">Contraseña</label>
                <div className="input-wrap">
                  <input
                    type={showPassword ? "text" : "password"}
                    id="password"
                    autoComplete="current-password"
                    placeholder="Ingresa tu contraseña"
                    value={contrasena}
                    onChange={(e) => setContrasena(e.target.value)}
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
                {passwordError && <p className="field-error">Ingresa tu contraseña.</p>}
              </div>

              <div className="row-between">
                <label className="remember">
                  <input
                    type="checkbox"
                    checked={remember}
                    onChange={(e) => setRemember(e.target.checked)}
                  />
                  Recordarme
                </label>
                <Link to="/olvide-contrasena" className="link">
                  ¿Olvidaste tu contraseña?
                </Link>
              </div>

              <button type="submit" className="submit" disabled={loading}>
                {loading ? "Ingresando…" : "Iniciar sesión"}
              </button>
              <p className={`form-msg${formOk ? " ok" : ""}`}>{formMsg}</p>
            </form>

            <p className="foot-note">
              Los accesos son creados por un Administrador.
              <br />
              Si no tienes cuenta, solicítala a tu área de TI.
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}