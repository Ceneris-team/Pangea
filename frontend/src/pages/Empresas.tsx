import { useEffect, useState, type FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import DashboardLayout from "../components/layout/DashboardLayout";
import { useAuth } from "../hooks/useAuth";
import { ROLES } from "../config/roles";
import { ApiError, apiFetch, abrirEntorno } from "../services/api";
import DetalleSuscripcion from "../components/comercial/DetalleSuscripcion";
import SolicitudesSuscripcion from "../components/comercial/SolicitudesSuscripcion";

type Empresa = {
  id_clnt: number;
  nombre: string;
  rol_empresa: string;
  plan_nombre: string | null;
  estado_suscripcion: string;
  proyectos_total: number;
  consumo: { usuarios: number; ubicaciones: number; dispositivos: number };
  limites: { usuarios: number; ubicaciones: number; dispositivos: number } | null;
};
type Proyecto = {
  id_ubccn: number; nombre: string; descripcion: string | null;
  estado: string; dispositivos_total: number;
};
type Miembro = {
  id_mmb: number | null; id_usr: number; nombre: string; correo: string;
  rol: string; estado: string; proyecto_ids: number[]; legado: boolean;
};
const campo = "w-full rounded-lg border border-gray-300 bg-white px-3 py-2 text-sm text-gray-900 dark:border-white/20 dark:bg-[#262d39] dark:text-white";
const boton = "rounded-lg bg-[#ccff00] px-4 py-2 text-sm font-semibold text-gray-950 disabled:opacity-50";
const tarjeta = "rounded-2xl border border-black/10 bg-white/70 p-5 dark:border-white/10 dark:bg-[#1a202c]/90";

function mensajeError(error: unknown): string {
  return error instanceof ApiError ? error.message : "No se pudo completar la operación";
}

export default function Empresas() {
  const { rol, clienteId, puedeOperar } = useAuth();
  const adminCeneris = rol === ROLES.ADMINISTRADOR;
  const ceneris = adminCeneris || rol === ROLES.TECNICO_CENERIS;
  const [params, setParams] = useSearchParams();
  const empresaId = Number(params.get("cliente")) || (ceneris ? null : clienteId);
  const [empresas, setEmpresas] = useState<Empresa[]>([]);
  const [proyectos, setProyectos] = useState<Proyecto[]>([]);
  const [miembros, setMiembros] = useState<Miembro[]>([]);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [aviso, setAviso] = useState("");
  const [contrasenaNueva, setContrasenaNueva] = useState("");
  const [nuevaEmpresa, setNuevaEmpresa] = useState("");
  const [rucEmpresa, setRucEmpresa] = useState("");
  const [correoEmpresa, setCorreoEmpresa] = useState("");
  const [nombreUsuario, setNombreUsuario] = useState("");
  const [correoUsuario, setCorreoUsuario] = useState("");
  const [rolUsuario, setRolUsuario] = useState("Tecnico");
  const [proyectosUsuario, setProyectosUsuario] = useState<number[]>([]);
  const [editando, setEditando] = useState<number | null>(null);
  const [edicionRol, setEdicionRol] = useState("Tecnico");
  const [edicionProyectos, setEdicionProyectos] = useState<number[]>([]);
  const [revisionSuscripcion, setRevisionSuscripcion] = useState(0);

  const empresa = empresas.find((item) => item.id_clnt === empresaId);
  const puedeGestionarUsuarios = adminCeneris || empresa?.rol_empresa === "Administrador";

  const puedeVerUsuarios = ceneris || puedeGestionarUsuarios;

  async function cargarEmpresas() {
    const lista = await apiFetch<Empresa[]>("/empresas");
    setEmpresas(lista);
    if (!ceneris && lista.length && !lista.some((item) => item.id_clnt === empresaId)) {
      setParams({ cliente: String(lista[0].id_clnt) });
    }
  }

  async function cargarEmpresa(id: number, gestionar: boolean) {
    const [listaProyectos, listaMiembros] = await Promise.all([
      apiFetch<Proyecto[]>(`/empresas/${id}/proyectos`),
      gestionar ? apiFetch<Miembro[]>(`/empresas/${id}/usuarios`) : Promise.resolve([]),
    ]);
    setProyectos(listaProyectos);
    setMiembros(listaMiembros);
  }

  useEffect(() => {
    let cancelado = false;
    apiFetch<Empresa[]>("/empresas").then((lista) => {
      if (cancelado) return;
      setEmpresas(lista);
      if (!ceneris && lista.length && !lista.some((item) => item.id_clnt === empresaId)) {
        setParams({ cliente: String(lista[0].id_clnt) });
      }
    }).catch((err) => { if (!cancelado) setError(mensajeError(err)); })
      .finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
    // La lista se refresca explícitamente tras cada cambio; no en cada selección.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ceneris]);

  useEffect(() => {
    if (!empresaId || !empresa) {
      queueMicrotask(() => { setProyectos([]); setMiembros([]); });
      return;
    }
    let cancelado = false;
    Promise.all([
      apiFetch<Proyecto[]>(`/empresas/${empresaId}/proyectos`),
      (ceneris || empresa.rol_empresa === "Administrador")
        ? apiFetch<Miembro[]>(`/empresas/${empresaId}/usuarios`) : Promise.resolve([]),
    ]).then(([listaProyectos, listaMiembros]) => {
      if (cancelado) return;
      setProyectos(listaProyectos);
      setMiembros(listaMiembros);
    }).catch((err) => { if (!cancelado) setError(mensajeError(err)); });
    return () => { cancelado = true; };
  }, [empresaId, empresa, ceneris, puedeOperar]);

  function elegirEmpresa(id: number | null) {
    setError(""); setAviso(""); setContrasenaNueva(""); setEditando(null);
    setParams(id ? { cliente: String(id) } : {});
  }

  async function crearEmpresa(evento: FormEvent) {
    evento.preventDefault();
    setGuardando(true); setError(""); setAviso("");
    try {
      const res = await apiFetch<{ id_clnt: number }>("/empresas", {
        method: "POST", body: { nombre: nuevaEmpresa, ruc: rucEmpresa, correo_contacto: correoEmpresa },
      });
      setNuevaEmpresa(""); setRucEmpresa(""); setCorreoEmpresa("");
      await cargarEmpresas();
      setParams({ cliente: String(res.id_clnt) });
      setAviso("Empresa registrada. Asigna su plan, agrega su administrador y registra sus proyectos.");
    } catch (err) { setError(mensajeError(err)); }
    finally { setGuardando(false); }
  }

  function alternarProyecto(lista: number[], id: number, setter: (ids: number[]) => void) {
    setter(lista.includes(id) ? lista.filter((valor) => valor !== id) : [...lista, id]);
  }

  async function crearMiembro(evento: FormEvent) {
    evento.preventDefault();
    if (!empresaId) return;
    setGuardando(true); setError(""); setAviso(""); setContrasenaNueva("");
    try {
      const res = await apiFetch<{ contrasena_temporal: string | null }>(`/empresas/${empresaId}/usuarios`, {
        method: "POST",
        body: { nombre: nombreUsuario, correo: correoUsuario, rol: rolUsuario, proyecto_ids: proyectosUsuario },
      });
      setNombreUsuario(""); setCorreoUsuario(""); setProyectosUsuario([]);
      setContrasenaNueva(res.contrasena_temporal ?? "");
      setAviso(res.contrasena_temporal
        ? "Usuario creado. Entrega la contraseña temporal por un canal seguro; se muestra una sola vez."
        : "Usuario agregado a la empresa con su cuenta existente.");
      await Promise.all([cargarEmpresas(), cargarEmpresa(empresaId, puedeVerUsuarios)]);
    } catch (err) { setError(mensajeError(err)); }
    finally { setGuardando(false); }
  }

  async function guardarMiembro(miembro: Miembro, estado: string) {
    if (!empresaId || miembro.id_mmb === null) return;
    setGuardando(true); setError(""); setAviso("");
    try {
      await apiFetch(`/empresas/${empresaId}/usuarios/${miembro.id_mmb}`, {
        method: "PATCH",
        body: {
          rol: editando === miembro.id_mmb ? edicionRol : miembro.rol,
          estado,
          proyecto_ids: editando === miembro.id_mmb ? edicionProyectos : miembro.proyecto_ids,
        },
      });
      setEditando(null); setAviso("Acceso actualizado correctamente");
      await Promise.all([cargarEmpresas(), cargarEmpresa(empresaId, puedeVerUsuarios)]);
    } catch (err) { setError(mensajeError(err)); }
    finally { setGuardando(false); }
  }

  return (
    <DashboardLayout activo="empresas">
      <div className="mx-auto max-w-7xl space-y-6">
        <header className="flex flex-wrap items-end justify-between gap-4">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-white">{ceneris ? "Empresas y proyectos" : "Mi empresa"}</h1>
            <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">
              {ceneris ? "Vista global de clientes. Selecciona una empresa para administrar sus proyectos y usuarios." : "Consulta tus proyectos y gestiona el equipo de tu empresa según tu rol."}
            </p>
          </div>
          {ceneris && <select aria-label="Empresa a gestionar" className={campo + " min-w-64"} value={empresaId ?? ""}
            onChange={(e) => elegirEmpresa(e.target.value ? Number(e.target.value) : null)}>
            <option value="">Todos los clientes</option>
            {empresas.map((item) => <option key={item.id_clnt} value={item.id_clnt}>{item.nombre}</option>)}
          </select>}
        </header>

        {error && <div role="alert" className="rounded-xl border border-red-300 bg-red-50 p-3 text-sm text-red-800 dark:border-red-700 dark:bg-red-950/30 dark:text-red-200">{error}</div>}
        {aviso && <div role="status" className="rounded-xl border border-lime-400 bg-lime-50 p-3 text-sm text-gray-800 dark:bg-lime-950/30 dark:text-lime-200">{aviso}{contrasenaNueva && <div className="mt-2 font-mono font-bold">Contraseña temporal: {contrasenaNueva}</div>}</div>}
        {cargando && <p className="text-sm text-gray-600 dark:text-gray-300">Cargando empresas...</p>}

        {!empresaId && ceneris && (
          <div className="space-y-6">
          {adminCeneris && <form onSubmit={crearEmpresa} className={tarjeta + " grid gap-3 md:grid-cols-4"}>
            <div className="md:col-span-4"><h2 className="font-semibold text-gray-900 dark:text-white">Registrar empresa</h2><p className="text-sm text-gray-600 dark:text-gray-300">Después podrás asignarle un plan, registrar sus proyectos y agregar su administrador.</p></div>
            <input className={campo} aria-label="Razón social" placeholder="Razón social" value={nuevaEmpresa} onChange={(e) => setNuevaEmpresa(e.target.value)} required />
            <input className={campo} aria-label="RUC" placeholder="RUC de 11 dígitos" pattern="[0-9]{11}" value={rucEmpresa} onChange={(e) => setRucEmpresa(e.target.value)} required />
            <input className={campo} aria-label="Correo de contacto" type="email" placeholder="Correo de contacto" value={correoEmpresa} onChange={(e) => setCorreoEmpresa(e.target.value)} required />
            <button className={boton} disabled={guardando}>Registrar empresa</button>
          </form>}
          <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
            {empresas.map((item) => <button key={item.id_clnt} type="button" onClick={() => elegirEmpresa(item.id_clnt)} className={tarjeta + " text-left hover:border-lime-400"}>
              <div className="flex items-start justify-between gap-2"><h2 className="font-semibold text-gray-900 dark:text-white">{item.nombre}</h2><span className="text-xs text-lime-700 dark:text-lime-300">Abrir →</span></div>
              <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">{item.plan_nombre ?? "Sin plan"} · {item.estado_suscripcion}</p>
              <p className="mt-3 text-sm text-gray-600 dark:text-gray-300">{item.consumo.ubicaciones} proyectos · {item.consumo.usuarios} usuarios activos</p>
            </button>)}
            {!cargando && empresas.length === 0 && <p className="text-sm text-gray-600 dark:text-gray-300">Aún no hay empresas registradas.</p>}
          </div>
          </div>
        )}

        {empresa && <>
          <section className={tarjeta}>
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div><p className="text-xs uppercase tracking-wide text-gray-500 dark:text-gray-400">Empresa seleccionada</p><h2 className="text-xl font-bold text-gray-900 dark:text-white">{empresa.nombre}</h2><p className="text-sm text-gray-600 dark:text-gray-300">Acceso: {ceneris ? "CENERIS" : empresa.rol_empresa}</p></div>
              <div className="text-sm text-gray-700 dark:text-gray-200">Plan: <strong>{empresa.plan_nombre ?? "Sin asignar"}</strong> · {empresa.estado_suscripcion}<br />Usuarios: <strong>{empresa.consumo.usuarios} / {empresa.limites?.usuarios === 0 ? "∞" : empresa.limites?.usuarios ?? "—"}</strong></div>
            </div>
            {adminCeneris && !["Vigente", "En gracia"].includes(empresa.estado_suscripcion) && <Link to="/planes-suscripciones?vista=suscripciones" className="mt-3 inline-block text-sm font-semibold text-lime-700 underline dark:text-lime-300">Asignar una suscripción antes de crear usuarios</Link>}
          </section>

          {!ceneris && puedeGestionarUsuarios && <section className={tarjeta}><SolicitudesSuscripcion key={empresa.id_clnt} onCambio={async () => { await cargarEmpresas(); setRevisionSuscripcion(v => v + 1); }} /></section>}
          {!ceneris && puedeGestionarUsuarios && <DetalleSuscripcion clienteId={empresa.id_clnt} key={`${empresa.id_clnt}-${revisionSuscripcion}`} />}
          <section className={tarjeta}>
            <div className="flex flex-wrap items-center justify-between gap-3">
              <div><h2 className="text-lg font-semibold text-gray-900 dark:text-white">Proyectos de {empresa.nombre}</h2><p className="text-sm text-gray-600 dark:text-gray-300">Cada proyecto contiene sus dispositivos, datos y gráficos.</p></div>
              {puedeOperar && <button type="button" className={boton} onClick={() => abrirEntorno(empresa.id_clnt, null, "/ubicaciones?crear=1")}>Agregar proyecto</button>}
            </div>
            <div className="mt-4 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{proyectos.map((p) => <button key={p.id_ubccn} type="button" onClick={() => abrirEntorno(empresa.id_clnt, p.id_ubccn)} className="rounded-xl border border-gray-200 p-4 text-left hover:border-lime-400 dark:border-white/10"><strong className="text-gray-900 dark:text-white">{p.nombre}</strong><p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{p.dispositivos_total} dispositivos · {p.estado === "Activa" ? "Activo" : "Inactivo"}</p><span className="mt-2 inline-block text-sm font-semibold text-lime-700 dark:text-lime-300">Entrar al proyecto →</span></button>)}</div>
            {proyectos.length === 0 && <p className="mt-4 text-sm text-gray-600 dark:text-gray-300">Esta empresa todavía no tiene proyectos disponibles.</p>}
          </section>

          {puedeVerUsuarios && <section className={tarjeta}><h2 className="text-lg font-semibold text-gray-900 dark:text-white">Usuarios de {empresa.nombre}</h2><p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Administradores y técnicos acceden a todos los proyectos de la empresa. Los lectores consultan los proyectos asignados. Todos los miembros activos consumen cupo.</p>
            {puedeGestionarUsuarios && <form onSubmit={crearMiembro} className="mt-4 grid gap-3 md:grid-cols-2 xl:grid-cols-4"><input className={campo} placeholder="Nombre completo" aria-label="Nombre completo" value={nombreUsuario} onChange={(e) => setNombreUsuario(e.target.value)} required /><input className={campo} type="email" placeholder="Correo" aria-label="Correo" value={correoUsuario} onChange={(e) => setCorreoUsuario(e.target.value)} required /><select className={campo} aria-label="Rol en la empresa" value={rolUsuario} onChange={(e) => setRolUsuario(e.target.value)}><option value="Administrador">Administrador</option><option value="Tecnico">Técnico</option><option value="Lector">Lector</option></select><button className={boton} disabled={guardando || !["Vigente", "En gracia"].includes(empresa.estado_suscripcion)}>Agregar usuario</button>
              {rolUsuario === "Lector" && <div className="md:col-span-2 xl:col-span-4 flex flex-wrap gap-3 text-sm text-gray-700 dark:text-gray-200">{proyectos.map((p) => <label key={p.id_ubccn} className="flex items-center gap-1"><input type="checkbox" checked={proyectosUsuario.includes(p.id_ubccn)} onChange={() => alternarProyecto(proyectosUsuario, p.id_ubccn, setProyectosUsuario)} />{p.nombre}</label>)}</div>}
            </form>}
            <div className="mt-5 space-y-3">{miembros.map((m) => <div key={`${m.legado ? "legacy" : "member"}-${m.id_usr}`} className="rounded-xl border border-gray-200 p-3 dark:border-white/10"><div className="flex flex-wrap items-center justify-between gap-2"><div><strong className="text-gray-900 dark:text-white">{m.nombre}</strong><p className="text-sm text-gray-600 dark:text-gray-300">{m.correo} · {m.rol} · {m.estado}{m.legado ? " · Cuenta anterior" : ""}</p></div><div className="flex gap-2">{puedeGestionarUsuarios && (m.legado ? (adminCeneris && <Link to="/usuarios" className="rounded-lg border border-gray-300 px-3 py-1 text-sm text-gray-800 dark:border-white/20 dark:text-white">Ver en usuarios</Link>) : <><button type="button" className="rounded-lg border border-gray-300 px-3 py-1 text-sm text-gray-800 dark:border-white/20 dark:text-white" onClick={() => { setEditando(m.id_mmb); setEdicionRol(m.rol); setEdicionProyectos(m.proyecto_ids); }}>Editar</button><button type="button" className="rounded-lg border border-gray-300 px-3 py-1 text-sm text-gray-800 dark:border-white/20 dark:text-white" disabled={guardando} onClick={() => guardarMiembro(m, m.estado === "Activo" ? "Inactivo" : "Activo")}>{m.estado === "Activo" ? "Desactivar" : "Activar"}</button></>)} </div></div>
              {!m.legado && editando === m.id_mmb && <div className="mt-3 space-y-3"><select className={campo + " max-w-xs"} aria-label={`Rol de ${m.nombre}`} value={edicionRol} onChange={(e) => setEdicionRol(e.target.value)}><option value="Administrador">Administrador</option><option value="Tecnico">Técnico</option><option value="Lector">Lector</option></select>{edicionRol === "Lector" && <div className="flex flex-wrap gap-3 text-sm text-gray-700 dark:text-gray-200">{proyectos.map((p) => <label key={p.id_ubccn} className="flex items-center gap-1"><input type="checkbox" checked={edicionProyectos.includes(p.id_ubccn)} onChange={() => alternarProyecto(edicionProyectos, p.id_ubccn, setEdicionProyectos)} />{p.nombre}</label>)}</div>}<button type="button" className={boton} disabled={guardando} onClick={() => guardarMiembro(m, m.estado)}>Guardar cambios</button></div>}
            </div>)}{miembros.length === 0 && <p className="text-sm text-gray-600 dark:text-gray-300">Aún no hay usuarios empresariales.</p>}</div>
          </section>}
        </>}
      </div>
    </DashboardLayout>
  );
}
