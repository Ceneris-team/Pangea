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

  const [bgImage, setBgImage] = useState<string | null>(null);

  function handleBgUpload(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    if (!file) return;
    const reader = new FileReader();
    reader.onload = (ev) => setBgImage(ev.target?.result as string);
    reader.readAsDataURL(file);
  }

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
        style={bgImage ? { backgroundImage: `url(${bgImage})` } : undefined}
      />
      {!bgImage && (
        <div className="bg-fallback">
          <svg viewBox="0 0 800 1000" preserveAspectRatio="xMidYMid slice" xmlns="http://www.w3.org/2000/svg">
            <defs>
              <linearGradient id="leafFill" x1="0" y1="0" x2="1" y2="1">
                <stop offset="0%" stopColor="#2b4a37" />
                <stop offset="100%" stopColor="#152720" />
              </linearGradient>
            </defs>
            <g fill="url(#leafFill)" opacity={0.9}>
              <ellipse cx={90} cy={80} rx={70} ry={24} transform="rotate(35 90 80)" />
              <ellipse cx={220} cy={40} rx={80} ry={26} transform="rotate(-20 220 40)" />
              <ellipse cx={340} cy={120} rx={75} ry={24} transform="rotate(50 340 120)" />
              <ellipse cx={470} cy={60} rx={85} ry={27} transform="rotate(-40 470 60)" />
              <ellipse cx={610} cy={110} rx={78} ry={25} transform="rotate(20 610 110)" />
              <ellipse cx={740} cy={60} rx={70} ry={23} transform="rotate(-55 740 60)" />
            </g>
          </svg>
        </div>
      )}

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

            <input type="file" accept="image/*" onChange={handleBgUpload} style={{ marginTop: 24 }} />
          </div>
        </div>
      </div>
    </div>
  );
}