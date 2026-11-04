import { useEffect, useState, type ReactNode } from "react";
import { useAuth } from "../hooks/useAuth";
import { apiFetch, ApiError } from "../services/api";
import { guardarVersionAcceso, leerVersionAcceso } from "../services/vigenciaAcceso";

type Acceso = {
  version: string;
  empresas: { id_clnt: number; rol: string; proyecto_ids: number[] }[];
  proyecto_ids: number[];
};

function CargandoAcceso() {
  return <main className="p-8 text-gray-900 dark:text-white" aria-busy="true" role="status">Comprobando tus permisos…</main>;
}

/** Cada cuenta valida su acceso antes de montar los módulos y cargar sus datos. */
export default function VigenciaAcceso({ children }: { children: ReactNode }) {
  const { sesionIniciada, verificandoSesion, rol, correo, logout } = useAuth();
  if (verificandoSesion) return <CargandoAcceso />;
  if (!sesionIniciada || !["Cliente Final", "Usuario Empresa"].includes(rol ?? "")) return children;
  if (!correo) return <CargandoAcceso />;
  return <VigenciaSesion key={`${correo}:${rol}`} usuario={correo} logout={logout}>{children}</VigenciaSesion>;
}

function VigenciaSesion({ children, usuario, logout }: { children: ReactNode; usuario: string; logout: () => void }) {
  const [estado, setEstado] = useState<{ denegado: boolean; aviso: string | null } | null>(null);

  useEffect(() => {
    let version = leerVersionAcceso(sessionStorage, usuario);
    let cancelado = false;
    let consultando = false;
    const controller = new AbortController();
    async function comprobar() {
      if (consultando || cancelado) return;
      consultando = true;
      try {
        const acceso = await apiFetch<Acceso>("/auth/acceso", { sinEntorno: true, signal: controller.signal });
        if (cancelado) return;
        const clienteId = Number(sessionStorage.getItem("pangea_cliente"));
        const empresaActual = acceso.empresas.find((e) => e.id_clnt === clienteId);
        const proyecto = sessionStorage.getItem("pangea_proyecto_v2");
        const proyectos = empresaActual?.proyecto_ids
          ?? [...acceso.proyecto_ids, ...acceso.empresas.flatMap(e => e.proyecto_ids)];
        const filtroInicial = window.location.pathname === "/consulta-datos"
          ? new URLSearchParams(window.location.search).get("ubicacion_id") : null;
        const seleccionRevocada = (proyecto !== null && !proyectos.includes(Number(proyecto)))
          || (filtroInicial !== null && !proyectos.includes(Number(filtroInicial)))
          || (clienteId > 0 && acceso.empresas.length > 0 && !empresaActual);
        if ((version !== null && acceso.version !== version) || seleccionRevocada) {
          // Actualizar antes de recargar evita comparar otra vez con la versión revocada.
          guardarVersionAcceso(sessionStorage, usuario, acceso.version);
          // Una carga completa elimina el estado de todos los módulos y las peticiones pendientes.
          const empresa = empresaActual ?? acceso.empresas[0];
          if (empresa) sessionStorage.setItem("pangea_cliente", String(empresa.id_clnt));
          else sessionStorage.removeItem("pangea_cliente");
          sessionStorage.removeItem("pangea_proyecto_v2");
          sessionStorage.removeItem("pangea_proyecto");
          sessionStorage.setItem("pangea_aviso_acceso", "Tus permisos cambiaron. Se actualizaron los proyectos disponibles y se limpiaron los filtros anteriores.");
          setEstado({ denegado: true, aviso: null });
          window.location.replace("/consulta-datos");
          return;
        }
        version = acceso.version;
        guardarVersionAcceso(sessionStorage, usuario, acceso.version);
        const aviso = sessionStorage.getItem("pangea_aviso_acceso");
        sessionStorage.removeItem("pangea_aviso_acceso");
        setEstado(anterior => ({ denegado: false, aviso: aviso ?? anterior?.aviso ?? null }));
      } catch (error) {
        if (!cancelado && error instanceof ApiError && error.status === 403) setEstado({ denegado: true, aviso: null });
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
  }, [usuario]);

  if (!estado) return <CargandoAcceso />;
  if (estado.denegado) return <main className="mx-auto max-w-xl p-8 text-gray-900 dark:text-white" role="alert"><h1 className="text-xl font-bold">Tu acceso cambió</h1><p className="my-4">Se retiró el acceso a esta empresa o se están actualizando los proyectos disponibles. Contacta al administrador si necesitas recuperar el acceso.</p><button type="button" className="rounded-lg bg-[#ccff00] px-4 py-2 text-gray-950" onClick={logout}>Cerrar sesión</button></main>;
  return <>{estado.aviso && <div role="status" className="bg-lime-100 p-3 text-sm text-gray-900">{estado.aviso}</div>}{children}</>;
}
