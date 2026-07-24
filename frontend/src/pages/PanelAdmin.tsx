import { Link } from "react-router-dom";
import { useAuth } from "../context/AuthContext";

export default function PanelAdmin() {
  const { nombreCompleto, logout } = useAuth();

  return (
    <div style={{ padding: 32, fontFamily: "system-ui, sans-serif" }}>
      <header style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <h1>Panel de Administrador</h1>
        <div>
          <span style={{ marginRight: 16 }}>Hola, {nombreCompleto}</span>
          <button onClick={logout}>Cerrar sesión</button>
        </div>
      </header>

      <nav style={{ marginTop: 24 }}>
        <Link to="/usuarios">Gestión de Usuarios</Link>
        {/* TODO (equipo): agregar aquí los links a Ubicaciones (HU07/HU08),
            Dispositivos (HU10/HU11), etc. a medida que se implementen. */}
      </nav>
    </div>
  );
}
