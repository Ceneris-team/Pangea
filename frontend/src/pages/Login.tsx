import { useState, type FormEvent } from "react";
import { useNavigate, Link } from "react-router-dom";
import "./Login.css";
import { useAuth } from "../context/AuthContext";
import { rutaPorRol } from "../config/roles";
import { ApiError } from "../services/api";

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
      <div className="bg-fallback" aria-hidden="true">
        <svg viewBox="0 0 1366 768" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
          <defs>
            <radialGradient id="nodeGlow" cx="50%" cy="50%" r="50%">
              <stop offset="0%" stopColor="#d4ff5f" stopOpacity="1" />
              <stop offset="45%" stopColor="#9be32e" stopOpacity="0.55" />
              <stop offset="100%" stopColor="#9be32e" stopOpacity="0" />
            </radialGradient>
            <linearGradient id="bgWash" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#7c828c" />
              <stop offset="100%" stopColor="#8d939c" />
            </linearGradient>
          </defs>

          <rect x="0" y="0" width="1366" height="768" fill="url(#bgWash)" />

          <g fill="#4b5158" opacity="0.55">
            {Array.from({ length: 46 }).map((_, i) => {
              const h = 20 + ((i * 37) % 130);
              return <rect key={i} x={i * 30} y={330 - h} width={10} height={h} rx={1} />;
            })}
          </g>

          <g fill="#2f3439" opacity="0.5">
            {Array.from({ length: 900 }).map((_, i) => {
              const col = i % 45;
              const row = Math.floor(i / 45);
              const x = 40 + col * 30 + ((row % 2) * 12);
              const y = 420 + row * 16;
              const seed = (col * 13 + row * 7) % 100;
              if (seed > 62) return null;
              return <circle key={i} cx={x} cy={y} r={2.1} />;
            })}
          </g>

          <g stroke="#c8f24a" strokeOpacity="0.55" strokeWidth="1" fill="none">
            <path d="M120 505 L300 500 L440 555 L560 620 L700 585 L860 500 L1030 555 L1160 470" />
            <path d="M300 500 L150 690 L480 700 L560 620" />
            <path d="M700 585 L610 660 L860 500" />
            <path d="M1030 555 L1180 605 L1160 470" />
          </g>

          {[
            { x: 120, y: 505, v: "10.75", up: true },
            { x: 300, y: 500, v: "26.01", up: false },
            { x: 440, y: 555, v: "07.28", up: true },
            { x: 560, y: 620, v: "24.78", up: true },
            { x: 700, y: 585, v: "22.10", up: false },
            { x: 860, y: 500, v: "25.21", up: true },
            { x: 1030, y: 555, v: "30.12", up: true },
            { x: 1160, y: 470, v: "18.07", up: false },
          ].map((n, i) => (
            <g key={i}>
              <circle cx={n.x} cy={n.y} r={22} fill="url(#nodeGlow)" />
              <circle cx={n.x} cy={n.y} r={4} fill="#eaffb0" />
              <text x={n.x + 14} y={n.y - 8} fontSize="13" fill="#d9ff8a" fontFamily="monospace">
                {n.up ? "▲" : "▼"} {n.v}
              </text>
            </g>
          ))}
        </svg>
        <div className="bg-fallback-tint" />
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