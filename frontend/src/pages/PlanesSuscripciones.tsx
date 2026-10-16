import { useCallback, useEffect, useState, type FormEvent } from "react";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import { useAuth } from "../context/AuthContext";
import { apiFetch } from "../services/api";
import { useSearchParams } from "react-router-dom";
import { ROLES } from "../config/roles";

import ContratoFormulario from "../components/comercial/ContratoFormulario";
import DetalleSuscripcion from "../components/comercial/DetalleSuscripcion";
import SolicitudesSuscripcion from "../components/comercial/SolicitudesSuscripcion";
import { type Limites, type Plan, type Cliente, type Catalogo } from "../types/comercial";

const tarjeta = "rounded-2xl border border-gray-200 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-[#171d2a]/90";
const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 outline-none focus:border-lime-500 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const etiqueta = "mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200";
const primario = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 hover:bg-[#b9eb00] disabled:cursor-not-allowed disabled:opacity-50";

function Cupo({ titulo, uso, limite }: { titulo: string; uso: number; limite: number | undefined }) {
  const porcentaje = limite && limite > 0 ? Math.min(100, (uso / limite) * 100) : 0;
  const agotado = Boolean(limite && uso >= limite);
  return (
    <div>
      <div className="mb-1 flex justify-between gap-2 text-sm">
        <span>{titulo}</span>
        <span className={agotado ? "font-semibold text-amber-600 dark:text-amber-300" : "font-semibold"}>
          {uso} / {limite === undefined ? "—" : limite === 0 ? "Sin límite" : limite}
        </span>
      </div>
      {limite !== undefined && limite > 0 && (
        <div className="h-2 overflow-hidden rounded-full bg-gray-200 dark:bg-white/10">
          <div className={`h-full rounded-full ${agotado ? "bg-amber-500" : "bg-lime-500"}`} style={{ width: `${porcentaje}%` }} />
        </div>
      )}
    </div>
  );
}

export default function PlanesSuscripciones() {
  const { nombreCompleto, rol, logout } = useAuth();
  const puedeGestionar = rol === ROLES.ADMINISTRADOR_COMERCIAL || rol === ROLES.ADMINISTRADOR;
  const [parametros, setParametros] = useSearchParams();
  const vista = ["suscripciones", "solicitudes"].includes(parametros.get("vista") ?? "") ? parametros.get("vista")! : "planes";
  const [planes, setPlanes] = useState<Plan[]>([]);
  const [catalogo, setCatalogo] = useState<Catalogo>({ funcionalidades: [], complementos: [] });
  const [historialCliente, setHistorialCliente] = useState<number | null>(null);
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [filtroCliente, setFiltroCliente] = useState("");
  const [nombre, setNombre] = useState("");
  const [descripcion, setDescripcion] = useState("");
  const [precio, setPrecio] = useState("");
  const [moneda, setMoneda] = useState("PEN");
  const [editandoLimites, setEditandoLimites] = useState<number | null>(null);
  const [limites, setLimites] = useState<Limites>({ ubicaciones: 0, dispositivos: 0, usuarios: 0 });
  const [asignando, setAsignando] = useState<number | null>(null);
  const [cargando, setCargando] = useState(true);
  const [guardando, setGuardando] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");

  const recargar = useCallback(async () => {
    const [listaPlanes, listaClientes, listaCatalogo] = await Promise.all([
      apiFetch<Plan[]>("/comercial/planes"),
      apiFetch<Cliente[]>("/comercial/clientes"),
      apiFetch<Catalogo>("/comercial/catalogo"),
    ]);
    setPlanes(listaPlanes);
    setClientes(listaClientes);
    setCatalogo(listaCatalogo);
  }, []);

  useEffect(() => {
    recargar().catch((e: Error) => setError(e.message)).finally(() => setCargando(false));
  }, [recargar]);

  async function ejecutar(accion: () => Promise<{ mensaje: string }>) {
    setError("");
    setMensaje("");
    setGuardando(true);
    try {
      const respuesta = await accion();
      await recargar();
      setMensaje(respuesta.mensaje);
      return true;
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo guardar");
      return false;
    } finally {
      setGuardando(false);
    }
  }

  async function crearPlan(evento: FormEvent) {
    evento.preventDefault();
    if (await ejecutar(() => apiFetch("/comercial/planes", {
      method: "POST",
      body: { nombre, descripcion: descripcion || null, precio_mensual: precio, moneda },
    }))) {
      setNombre("");
      setDescripcion("");
      setPrecio("");
    }
  }

  async function guardarLimites(evento: FormEvent) {
    evento.preventDefault();
    if (editandoLimites === null) return;
    if (await ejecutar(() => apiFetch(`/comercial/planes/${editandoLimites}/limites`, {
      method: "PUT", body: limites,
    }))) setEditandoLimites(null);
  }

  function abrirSuscripcion(idCliente?: number) {
    setAsignando(idCliente ?? clientes.find((cliente) => cliente.plan_id === null)?.id_clnt ?? clientes[0]?.id_clnt ?? null);
    setError("");
  }

  const clientesFiltrados = clientes.filter((cliente) =>
    `${cliente.nombre} ${cliente.ruc} ${cliente.plan_nombre ?? ""} ${cliente.estado_suscripcion}`.toLocaleLowerCase("es-PE")
      .includes(filtroCliente.trim().toLocaleLowerCase("es-PE"))
  );

  return (
    <div className="flex h-screen overflow-hidden text-gray-900 dark:text-white">
      <Sidebar onLogout={logout} activo={vista === "suscripciones" ? "suscripciones" : "planes"} rol={rol} />
      <div className="flex min-w-0 flex-1 flex-col">
        <div className="franja-superior flex justify-end p-4 pb-0 md:p-6"><Topbar nombreCompleto={nombreCompleto} rol={rol} /></div>
        <main className="flex-1 overflow-y-auto p-5 md:p-8">
          <div className="mx-auto max-w-6xl space-y-8">
            <header>
              <h1 className="text-3xl font-bold">Planes y suscripciones</h1>
              <p className="mt-2 text-gray-600 dark:text-gray-300">Los contratos pertenecen a la empresa minera. Sus proyectos y usuarios comparten los cupos contratados.</p>
            </header>
            <nav aria-label="Gestión comercial" className="flex flex-wrap gap-2 border-b border-gray-300 pb-3 dark:border-white/20">
              <button type="button" onClick={() => setParametros({ vista: "solicitudes" })} className={`rounded-xl px-4 py-2 font-semibold ${vista === "solicitudes" ? "bg-[#ccff00] text-gray-950" : "bg-gray-200/70 dark:bg-white/10"}`}>Solicitudes</button>
              <button type="button" onClick={() => setParametros({ vista: "planes" })} className={`rounded-xl px-4 py-2 font-semibold ${vista === "planes" ? "bg-[#ccff00] text-gray-950" : "bg-gray-200/70 dark:bg-white/10"}`}>Planes</button>
              <button type="button" onClick={() => setParametros({ vista: "suscripciones" })} className={`rounded-xl px-4 py-2 font-semibold ${vista === "suscripciones" ? "bg-[#ccff00] text-gray-950" : "bg-gray-200/70 dark:bg-white/10"}`}>Suscripciones</button>
            </nav>
            {error && <div role="alert" className="rounded-xl border border-red-400/50 bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</div>}
            {mensaje && <div role="status" className="rounded-xl border border-lime-500/50 bg-lime-500/10 p-3 text-lime-800 dark:text-lime-200">{mensaje}</div>}
            {cargando ? <p>Cargando planes y clientes...</p> : (
              <>
                {vista === "solicitudes" && <SolicitudesSuscripcion comercial clientes={clientes} planes={planes} catalogo={catalogo} onCambio={recargar} />}
                {vista === "planes" && <section className="space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div><h2 className="text-xl font-semibold">Planes</h2><p className="text-sm text-gray-600 dark:text-gray-300">Un plan necesita sus tres límites antes de poder asignarse.</p></div>
                  </div>
                  {planes.length === 0 && <p className="rounded-xl border border-dashed border-gray-400 p-5">Todavía no hay planes. Crea el primero abajo.</p>}
                  <div className="grid gap-4 lg:grid-cols-3">
                    {planes.map((plan) => (
                      <article key={plan.id_pln} className={tarjeta}>
                        <div className="flex items-start justify-between gap-3"><h3 className="text-lg font-bold">{plan.nombre}</h3><span className="rounded-full bg-lime-500/20 px-2 py-1 text-xs font-semibold">{plan.estado}</span></div>
                        <p className="mt-1 min-h-10 text-sm text-gray-600 dark:text-gray-300">{plan.descripcion || "Sin descripción"}</p>
                        <p className="text-xs text-gray-500">Revisión {plan.revision} · se conserva la versión contratada por cada empresa</p>
                        <p className="mt-3 text-2xl font-bold">{plan.moneda} {Number(plan.precio_mensual).toLocaleString("es-PE", { minimumFractionDigits: 2 })}<span className="text-sm font-normal"> / mes</span></p>
                        <div className="mt-4 space-y-2 border-t border-gray-200 pt-4 text-sm dark:border-white/10">
                          {plan.limites ? <>
                            <p>Proyectos: <strong>{plan.limites.ubicaciones || "Sin límite"}</strong></p>
                            <p>Dispositivos: <strong>{plan.limites.dispositivos || "Sin límite"}</strong></p>
                            <p>Usuarios activos: <strong>{plan.limites.usuarios || "Sin límite"}</strong></p>
                          </> : <p className="text-amber-700 dark:text-amber-300">Límites pendientes</p>}
                        </div>
                        {puedeGestionar && <button type="button" className="mt-4 rounded-xl border border-gray-300 px-3 py-2 text-sm font-semibold hover:border-lime-500 dark:border-white/20" onClick={() => { setEditandoLimites(plan.id_pln); setLimites(plan.limites || { ubicaciones: 0, dispositivos: 0, usuarios: 0 }); }}>
                          {plan.limites ? "Editar límites" : "Definir límites"}
                        </button>}
                      </article>
                    ))}
                  </div>
                  {puedeGestionar && editandoLimites !== null && <form onSubmit={guardarLimites} className={tarjeta}>
                    <h3 className="mb-4 font-semibold">Límites de {planes.find((p) => p.id_pln === editandoLimites)?.nombre}</h3>
                    <p className="mb-4 text-sm text-gray-600 dark:text-gray-300">0 significa sin límite. Guardar crea una nueva revisión para futuras contrataciones. Las suscripciones existentes conservan sus condiciones.</p>
                    <div className="grid gap-4 sm:grid-cols-3">{(["ubicaciones", "dispositivos", "usuarios"] as const).map((clave) => <label key={clave}><span className={etiqueta}>{clave === "ubicaciones" ? "Proyectos" : clave === "dispositivos" ? "Dispositivos" : "Usuarios"}</span><input className={campo} type="number" min="0" step="1" required value={limites[clave]} onChange={(e) => setLimites({ ...limites, [clave]: Number(e.target.value) })} /></label>)}</div>
                    <div className="mt-4 flex gap-2"><button className={primario} disabled={guardando}>Guardar límites</button><button type="button" onClick={() => setEditandoLimites(null)}>Cancelar</button></div>
                  </form>}
                  {puedeGestionar && <form onSubmit={crearPlan} className={tarjeta}>
                    <h3 className="mb-4 font-semibold">Crear plan</h3>
                    <div className="grid gap-4 md:grid-cols-3">
                      <label><span className={etiqueta}>Nombre *</span><input className={campo} value={nombre} onChange={(e) => setNombre(e.target.value)} maxLength={100} required /></label>
                      <label><span className={etiqueta}>Descripción</span><input className={campo} value={descripcion} onChange={(e) => setDescripcion(e.target.value)} maxLength={300} /></label>
                      <label><span className={etiqueta}>Precio mensual *</span><input className={campo} type="number" min="0" step="0.01" value={precio} onChange={(e) => setPrecio(e.target.value)} required /></label>
                      <label><span className={etiqueta}>Moneda</span><select className={campo} value={moneda} onChange={e => setMoneda(e.target.value)}><option>PEN</option><option>USD</option></select></label>
                    </div>
                    <div className="mt-4 flex gap-3">
                      <button className={primario} disabled={guardando}>Crear plan</button>
                      <button type="button" onClick={() => { setNombre(""); setDescripcion(""); setPrecio(""); setError(""); }}>Cancelar</button>
                    </div>
                  </form>}
                </section>}
                {vista === "suscripciones" && <section className="space-y-4">
                  <div className="flex flex-wrap items-end justify-between gap-4">
                    <div><h2 className="text-xl font-semibold">Clientes y suscripciones</h2><p className="text-sm text-gray-600 dark:text-gray-300">El plan corresponde a la empresa minera; sus usuarios comparten estos cupos.</p></div>
                    {puedeGestionar && <button type="button" className={primario} onClick={() => abrirSuscripcion()} disabled={clientes.length === 0}>+ Crear suscripción</button>}
                  </div>
                  {asignando !== null && <div className="space-y-3">
                    <label className="block max-w-md">Empresa<select aria-label="Empresa del contrato" className={campo} value={asignando} onChange={e => setAsignando(Number(e.target.value))}>{clientes.map(c => <option key={c.id_clnt} value={c.id_clnt}>{c.nombre}</option>)}</select></label>
                    {clientes.find(c => c.id_clnt === asignando) && <ContratoFormulario key={asignando} cliente={clientes.find(c => c.id_clnt === asignando)!} planes={planes} catalogo={catalogo} onCancelar={() => setAsignando(null)} onGuardado={async () => { await recargar(); setAsignando(null); setHistorialCliente(null); setMensaje("Suscripción guardada correctamente"); }} />}
                  </div>}
                  <label className="block max-w-md"><span className={etiqueta}>Buscar cliente o plan</span><input className={campo} value={filtroCliente} onChange={(e) => setFiltroCliente(e.target.value)} placeholder="Nombre, RUC o plan" /></label>
                  {clientesFiltrados.length === 0 && <p className={tarjeta}>No hay clientes con ese criterio.</p>}
                  <div className="grid gap-4 lg:grid-cols-2">{clientesFiltrados.map((cliente) => <article key={cliente.id_clnt} className={tarjeta}>
                    <div className="flex flex-wrap items-start justify-between gap-2"><div><h3 className="font-bold">{cliente.nombre}</h3><p className="text-xs text-gray-500 dark:text-gray-400">RUC {cliente.ruc}</p></div><div className="flex flex-wrap gap-2"><span className="rounded-full bg-gray-200 px-3 py-1 text-sm dark:bg-white/10">{cliente.plan_nombre || "Sin plan"}</span><span className={`rounded-full px-3 py-1 text-sm ${cliente.estado_suscripcion === "Vigente" ? "bg-lime-500/20 text-lime-800 dark:text-lime-300" : "bg-amber-500/20 text-amber-800 dark:text-amber-300"}`}>{cliente.estado_suscripcion}</span></div></div>
                    {cliente.fecha_vencimiento && <p className="mt-2 text-xs text-gray-500 dark:text-gray-400">Vencimiento: {cliente.fecha_vencimiento}</p>}
                    {cliente.condiciones && <p className="mt-2 text-sm">{cliente.condiciones.moneda} {cliente.condiciones.precio_acordado} / {cliente.condiciones.periodicidad.toLowerCase()} · revisión contratada {cliente.condiciones.revision_plan}</p>}
                    {cliente.aviso_vencimiento && <p className="mt-2 text-sm font-semibold text-amber-700 dark:text-amber-300">Revisar renovación. Al vencer y finalizar la gracia, la empresa quedará en modo consulta.</p>}
                    {cliente.programada && <p className="mt-2 text-sm font-semibold text-lime-700 dark:text-lime-300">Programada: {cliente.programada.condiciones.plan_nombre} desde {cliente.programada.fecha_inicio}</p>}
                    <div className="mt-5 space-y-4">
                      <Cupo titulo="Proyectos" uso={cliente.consumo.ubicaciones} limite={cliente.limites?.ubicaciones} />
                      <Cupo titulo="Dispositivos" uso={cliente.consumo.dispositivos} limite={cliente.limites?.dispositivos} />
                      <Cupo titulo="Usuarios activos" uso={cliente.consumo.usuarios} limite={cliente.limites?.usuarios} />
                    </div>
                    {puedeGestionar && <button type="button" className="mt-5 rounded-xl border border-gray-300 px-3 py-2 text-sm font-semibold hover:border-lime-500 dark:border-white/20" onClick={() => { abrirSuscripcion(cliente.id_clnt); }}>Gestionar suscripción</button>}
                    <button type="button" className="ml-3 mt-3 text-sm font-semibold underline" onClick={() => setHistorialCliente(historialCliente === cliente.id_clnt ? null : cliente.id_clnt)}>Condiciones e historial</button>
                  </article>)}</div>
                  {historialCliente !== null && <DetalleSuscripcion key={historialCliente} clienteId={historialCliente} gestionar onCambio={recargar} />}
                </section>}
              </>
            )}
          </div>
        </main>
      </div>
    </div>
  );
}
