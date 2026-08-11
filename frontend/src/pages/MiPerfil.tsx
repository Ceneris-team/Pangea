import { useEffect, useState, type FormEvent } from "react";
import { useNavigate } from "react-router-dom";
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
    <div style={{ padding: 32, fontFamily: "system-ui, sans-serif", maxWidth: 560 }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Mi perfil</h1>
        {/* Con el cambio de contraseña pendiente no hay a dónde volver:
            ProtectedRoute redirige de vuelta aquí (HU04). */}
        {!debeCambiarContrasena && <button onClick={() => navigate(-1)}>Volver</button>}
      </header>

      {debeCambiarContrasena && (
        <p
          style={{
            marginTop: 12,
            padding: 12,
            borderRadius: 8,
            background: "#fff4e5",
            border: "1px solid #f0c48a",
            color: "#8a5300",
          }}
        >
          Estás usando una contraseña temporal. Debes cambiarla antes de continuar.
        </p>
      )}

      {errorPerfil && <p style={{ color: "#b3261e" }}>{errorPerfil}</p>}

      {perfil && (
        <section style={{ marginTop: 16 }}>
          <p>
            <strong>Nombre:</strong> {perfil.nombre_completo}
          </p>
          <p>
            <strong>Correo:</strong> {perfil.correo}
          </p>
          <p>
            <strong>Rol:</strong> {perfil.rol}
          </p>
          <p>
            <strong>Estado:</strong> {perfil.estado}
          </p>
        </section>
      )}

      <section style={{ marginTop: 24 }}>
        {!mostrarForm ? (
          <button onClick={() => setMostrarForm(true)}>Cambiar contraseña</button>
        ) : (
          <form onSubmit={handleGuardar} noValidate style={{ display: "grid", gap: 12, maxWidth: 360 }}>
            <label>
              Contraseña actual
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={contrasenaActual}
                onChange={(e) => setContrasenaActual(e.target.value)}
                required
                style={{ display: "block", width: "100%" }}
              />
            </label>

            <label>
              Nueva contraseña
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                value={nuevaContrasena}
                onChange={(e) => setNuevaContrasena(e.target.value)}
                required
                style={{ display: "block", width: "100%" }}
              />
              {nuevaContrasena.length > 0 && !passwordOk && (
                <small style={{ color: "#b3261e" }}>
                  Debe tener mínimo 8 caracteres, al menos 1 mayúscula y 1 número.
                </small>
              )}
            </label>

            <label>
              Confirmar nueva contraseña
              <input
                type={showPassword ? "text" : "password"}
                autoComplete="new-password"
                value={confirmarContrasena}
                onChange={(e) => setConfirmarContrasena(e.target.value)}
                required
                style={{ display: "block", width: "100%" }}
              />
              {confirmarContrasena.length > 0 && !coinciden && (
                <small style={{ color: "#b3261e" }}>Las contraseñas no coinciden.</small>
              )}
            </label>

            <label style={{ fontSize: 13 }}>
              <input
                type="checkbox"
                checked={showPassword}
                onChange={(e) => setShowPassword(e.target.checked)}
              />{" "}
              Mostrar contraseñas
            </label>

            <div style={{ display: "flex", gap: 8 }}>
              <button type="submit" disabled={loading || !puedeGuardar}>
                {loading ? "Guardando…" : "Guardar"}
              </button>
              {/* Cancelar no se ofrece si el cambio es obligatorio (HU04). */}
              {!debeCambiarContrasena && (
                <button type="button" onClick={() => setMostrarForm(false)} disabled={loading}>
                  Cancelar
                </button>
              )}
            </div>

            <p style={{ color: formOk ? "#1e7a34" : "#b3261e", minHeight: 18 }}>{formMsg}</p>
          </form>
        )}
      </section>
    </div>
  );
}
