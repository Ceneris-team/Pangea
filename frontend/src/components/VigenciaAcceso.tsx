import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { apiFetch, ApiError } from "../services/api";

type Acceso = {
  version: string;
  empresas: { id_clnt: number; rol: string; proyecto_ids: number[] }[];
  proyecto_ids: number[];
};

/** Los cambios externos también invalidan tablas, gráficos y selecciones ya cargados. */
export default function VigenciaAcceso({ children }: { children: ReactNode }) {
  const { sesionIniciada, verificandoSesion, rol, logout } = useAuth();
  const [denegado, setDenegado] = useState(false);
  const [aviso] = useState(() => sessionStorage.getItem("pangea_aviso_acceso"));

  useEffect(() => {
    sessionStorage.removeItem("pangea_aviso_acceso");
    if (!sesionIniciada || verificandoSesion || !["Cliente Final", "Usuario Empresa"].includes(rol ?? "")) return;
    let version: string | null = null;
    let cancelado = false;
    let consultando = false;
    const controller = new AbortController();
    async function comprobar() {
      if (consultando || cancelado) return;
      consultando = true;
      try {
        const acceso = await apiFetch<Acceso>("/auth/acceso", { sinEntorno: true, signal: controller.signal });
        if (cancelado) return;
        if (version !== null && acceso.version !== version) {
          // Una carga completa elimina el estado de todos los módulos y las peticiones pendientes.
          const clienteId = Number(sessionStorage.getItem("pangea_cliente"));
          const empresa = acceso.empresas.find((e) => e.id_clnt === clienteId) ?? acceso.empresas[0];
          if (empresa) sessionStorage.setItem("pangea_cliente", String(empresa.id_clnt));
          else sessionStorage.removeItem("pangea_cliente");
          sessionStorage.removeItem("pangea_proyecto_v2");
          sessionStorage.setItem("pangea_aviso_acceso", "Tus permisos cambiaron. Se actualizaron los proyectos disponibles y se limpiaron los filtros anteriores.");
          setDenegado(true);
          window.location.replace("/consulta-datos");
          return;
        }
        version = acceso.version;
        setDenegado(false);
      } catch (error) {
        if (!cancelado && error instanceof ApiError && error.status === 403) setDenegado(true);
      } finally { consultando = false; }
    }
    void comprobar();
    const intervalo = window.setInterval(() => void comprobar(), 20_000);
    const alVolver = () => { if (document.visibilityState === "visible") void comprobar(); };
    window.addEventListener("focus", alVolver);
    document.addEventListener("visibilitychange", alVolver);
    window.addEventListener("pangea:acceso-rechazado", alVolver);
    return () => {
      cancelado = true;
      controller.abort();
      window.clearInterval(intervalo);
      window.removeEventListener("focus", alVolver);
      document.removeEventListener("visibilitychange", alVolver);
      window.removeEventListener("pangea:acceso-rechazado", alVolver);
    };
  }, [sesionIniciada, verificandoSesion, rol]);

  if (denegado && sesionIniciada) return <main className="mx-auto max-w-xl p-8 text-gray-900 dark:text-white" role="alert"><h1 className="text-xl font-bold">Tu acceso cambió</h1><p className="my-4">Se retiró el acceso a esta empresa o se están actualizando los proyectos disponibles. Contacta al administrador si necesitas recuperar el acceso.</p><button type="button" className="rounded-lg bg-[#ccff00] px-4 py-2 text-gray-950" onClick={logout}>Cerrar sesión</button></main>;
  return <>{aviso && <div role="status" className="bg-lime-100 p-3 text-sm text-gray-900">{aviso}</div>}{children}</>;
}
