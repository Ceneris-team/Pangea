import { useEffect, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../context/AuthContext";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";

interface PanelDetalle {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
}

export default function DetallePanel() {
  const { id } = useParams<{ id: string }>();
  const { nombreCompleto, rol, logout } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();

  // HU24 CA2: tras crear el panel, la redirección trae el mensaje de
  // éxito en el state (mismo patrón que Ubicaciones.tsx).
  const [mensajeExito, setMensajeExito] = useState<string | null>(
    (location.state as { mensaje?: string } | null)?.mensaje ?? null
  );

  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) {
      navigate(location.pathname, { replace: true, state: null });
    }
  }, [location.pathname, location.state, navigate]);

  const [panel, setPanel] = useState<PanelDetalle | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelado = false;
    setLoading(true);
    setError(null);

    apiFetch<PanelDetalle>(`/paneles/${id}`)
      .then((res) => {
        if (!cancelado) setPanel(res);
      })
      .catch((err) => {
        if (cancelado) return;
        setError(err instanceof ApiError ? err.message : "No se pudo cargar el panel");
      })
      .finally(() => {
        if (!cancelado) setLoading(false);
      });

    return () => {
      cancelado = true;
    };
  }, [id]);

  return (
    <div className="font-sans">
      <div className="flex h-screen bg-transparent transition-colors duration-300 overflow-hidden">
        <Sidebar onLogout={logout} activo="paneles" rol={rol} />

        <div className="flex-1 flex flex-col overflow-hidden">
          <div className="flex justify-end p-4 md:p-6 pb-0">
            <Topbar nombreCompleto={nombreCompleto} rol={rol} />
          </div>

          <main className="flex-1 overflow-y-auto p-6 md:p-8">
            <div className="mb-6">
              <Link
                to="/paneles"
                className="text-sm text-gray-600 dark:text-gray-300 hover:text-[#5a7000] dark:hover:text-[#ccff00] transition-colors"
              >
                ← Volver a Tableros Personalizables
              </Link>
            </div>

            {mensajeExito && (
              <div className="mb-4 p-4 rounded-xl bg-[#ccff00]/20 border border-[#ccff00]/40 text-[#5a7000] dark:text-[#ccff00] text-sm flex items-center justify-between">
                <span>{mensajeExito}</span>
                <button onClick={() => setMensajeExito(null)} className="text-xs font-medium underline">
                  Cerrar
                </button>
              </div>
            )}

            {loading && (
              <div className="flex justify-center items-center gap-2 py-16 text-gray-600 dark:text-gray-300">
                <div className="w-4 h-4 rounded-full bg-[#ccff00] animate-bounce"></div>
                <span>Cargando panel...</span>
              </div>
            )}

            {!loading && error && (
              <div className="p-4 rounded-xl bg-red-50 dark:bg-red-900/20 text-red-600 dark:text-red-400 text-sm">
                {error}
              </div>
            )}

            {!loading && panel && (
              <>
                <header className="mb-6">
                  <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{panel.nmbr}</h1>
                </header>

                {/* HU24 CA3: panel vacío con el botón "Añadir ubicaciones"
                    disponible. El contenido real (ubicaciones y widgets)
                    se conecta en HU26/HU34; acá es un placeholder sin
                    funcionalidad detrás, a propósito. */}
                <div className="bg-white/25 dark:bg-white/[0.02] backdrop-blur-sm rounded-2xl shadow-sm border border-black/10 dark:border-white/10 flex flex-col items-center justify-center gap-4 py-20 px-6 text-center">
                  <p className="text-gray-600 dark:text-gray-300">
                    Este panel todavía no tiene ubicaciones configuradas.
                  </p>
                  <button
                    disabled
                    title="Disponible próximamente"
                    className="inline-flex items-center px-4 py-2 text-sm font-bold rounded-xl bg-[#ccff00] text-[#1a202c] opacity-60 cursor-not-allowed"
                  >
                    + Añadir ubicaciones
                  </button>
                </div>
              </>
            )}
          </main>
        </div>
      </div>
    </div>
  );
}
