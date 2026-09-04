import { useState, type FormEvent } from "react";
import { Link } from "react-router-dom";
import "./Login.css";
import { apiFetch, ApiError } from "../services/api";

function isValidEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value);
}

export default function OlvideContrasena() {
  const [correo, setCorreo] = useState("");
  const [emailError, setEmailError] = useState(false);
  const [formMsg, setFormMsg] = useState("");
  const [formOk, setFormOk] = useState(false);
  const [loading, setLoading] = useState(false);

  // HU 02 CA 1: "DADO QUE me encuentro en la pantalla de inicio de sesión y
  // no recuerdo mi contraseña, CUANDO selecciono '¿Olvidaste tu contraseña?'
  // e ingreso mi correo electrónico registrado y selecciono 'ENVIAR'..."
  async function handleSubmit(e: FormEvent) {
    e.preventDefault();
    setFormMsg("");
    setFormOk(false);

    const emailOk = isValidEmail(correo.trim());
    setEmailError(!emailOk);
    if (!emailOk) return;

    setLoading(true);
    try {
      const data = await apiFetch<{ mensaje: string }>("/auth/olvide-contrasena", {
        method: "POST",
        body: { correo: correo.trim() },
      });
      setFormMsg(data.mensaje);
      setFormOk(true);
    } catch (err) {
      setFormMsg(err instanceof ApiError ? err.message : "Ocurrió un error inesperado");
      setFormOk(false);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="login-page">
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
            <ellipse cx={340} cy={120} rx={75} ry={24} transform="rotate(50 340 120)" />
            <ellipse cx={610} cy={110} rx={78} ry={25} transform="rotate(20 610 110)" />
          </g>
        </svg>
      </div>

      <div className="stage">
        <div className="panel" style={{ margin: "0 auto" }}>
          <div className="card">
            <p className="eyebrow">Pangea · Recuperar acceso</p>
            <h1>¿Olvidaste tu contraseña?</h1>
            <p className="sub">
              Ingresa el correo con el que te registraste y te enviaremos las instrucciones para
              recuperarla.
            </p>

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

              <button type="submit" className="submit" disabled={loading}>
                {loading ? "Enviando…" : "Enviar"}
              </button>
              <p className={`form-msg${formOk ? " ok" : ""}`}>{formMsg}</p>
            </form>

            <p className="foot-note">
              <Link to="/login" className="link">
                Volver a iniciar sesión
              </Link>
            </p>
          </div>
        </div>
      </div>
    </div>
  );
}
