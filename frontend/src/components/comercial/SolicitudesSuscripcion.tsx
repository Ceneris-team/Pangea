import { useCallback, useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import { nombresRecursos, type Catalogo, type Cliente, type Condiciones, type Limites, type Plan } from "../../types/comercial";
import ContratoFormulario from "./ContratoFormulario";

type Solicitud = {
  id: number; cliente_id: number; empresa: string; solicitante: string; estado: string; revision: number;
  creada_en: string; aceptante: string | null; aceptada_en: string | null; propuesta_vencida: boolean;
  solicitud: { tipo: string; plan_id: number | null; incrementos: Limites; funcionalidades: string[]; descripcion: string };
  propuesta: null | { condiciones: Condiciones; mensaje: string; valida_hasta: string; inicio_al_activar: boolean;
    duracion_dias: number; contrato: { fecha_inicio: string; fecha_vencimiento: string; operacion: string };
    advertencia: string | null; recursos_excedidos: string[] };
  resultado: null | { id: number; estado: string; fecha_inicio: string; fecha_vencimiento: string };
};
type Evento = { id: number; accion: string; fecha: string; actor: string; datos: { motivo: string; revision: number } };
const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const boton = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 disabled:opacity-50";
const secundario = "rounded-xl border border-gray-300 px-3 py-2 text-sm dark:border-white/20 disabled:opacity-50";
const abiertas = ["Pendiente", "En evaluación", "Esperando aceptación", "Aceptada"];
const fecha = (f: string) => new Date(f).toLocaleString("es-PE");

export default function SolicitudesSuscripcion({ comercial = false, clientes = [], planes = [], catalogo, onCambio }: {
  comercial?: boolean; clientes?: Cliente[]; planes?: Plan[]; catalogo?: Catalogo; onCambio?: () => Promise<void>;
}) {
  const [lista, setLista] = useState<Solicitud[]>([]);
  const [opciones, setOpciones] = useState<{ planes: Plan[]; funcionalidades: { codigo: string; nombre: string }[] }>({ planes: [], funcionalidades: [] });
  const [miPlan, setMiPlan] = useState<Cliente | null>(null);
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  const [error, setError] = useState("");
  const [mensaje, setMensaje] = useState("");
  const [crear, setCrear] = useState(false);
  const [tipo, setTipo] = useState("Cambiar plan");
  const [planId, setPlanId] = useState("");
  const [incrementos, setIncrementos] = useState<Limites>({ ubicaciones: 0, dispositivos: 0, usuarios: 0 });
  const [descripcion, setDescripcion] = useState("");
  const [clave, setClave] = useState(() => crypto.randomUUID());
  const [filtro, setFiltro] = useState("Abiertas");
  const [busqueda, setBusqueda] = useState("");
  const [proponer, setProponer] = useState<number | null>(null);
  const [accion, setAccion] = useState<{ fila: Solicitud; nombre: string } | null>(null);
  const [motivo, setMotivo] = useState("");
  const [historial, setHistorial] = useState<{ id: number; eventos: Evento[] } | null>(null);
  const cargar = useCallback(async () => {
    const solicitudes = await apiFetch<Solicitud[]>("/solicitudes-suscripcion");
    setLista(solicitudes);
    if (!comercial) {
      const [op, contrato] = await Promise.all([apiFetch<typeof opciones>("/solicitudes-suscripcion/opciones"), apiFetch<Cliente>("/comercial/mi-plan")]);
      setOpciones(op); setMiPlan(contrato);
    }
  }, [comercial]);
  useEffect(() => {
    let activo = true;
    queueMicrotask(() => {
      if (activo) cargar().catch(e => setError(e.message)).finally(() => setCargando(false));
    });
    return () => { activo = false; };
  }, [cargar]);
  async function ejecutar(tarea: () => Promise<unknown>, exito: string) {
    if (ocupado) return false;
    setOcupado(true); setError(""); setMensaje("");
    try {
      await tarea(); await cargar(); await onCambio?.();
      setMensaje(exito); setHistorial(null); window.dispatchEvent(new Event("solicitudes-actualizadas")); return true;
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo completar la acción"); return false; }
    finally { setOcupado(false); }
  }
  async function enviar(event: FormEvent) {
    event.preventDefault();
    if (await ejecutar(() => apiFetch("/solicitudes-suscripcion", { method: "POST", body: {
      tipo, plan_id: tipo === "Cambiar plan" ? Number(planId) : null,
      incrementos: tipo === "Ampliar cupos" ? incrementos : { ubicaciones: 0, dispositivos: 0, usuarios: 0 },
      funcionalidades: [], descripcion, clave_idempotencia: clave,
    } }), "Solicitud enviada a CENERIS. La suscripción actual continúa vigente según sus condiciones.")) {
      setCrear(false); setDescripcion(""); setClave(crypto.randomUUID());
    }
  }
  function prepararAccion(fila: Solicitud, nombre: string) { setAccion({ fila, nombre }); setMotivo(""); setError(""); }
  async function confirmar(event: FormEvent) {
    event.preventDefault(); if (!accion) return;
    if (await ejecutar(() => apiFetch(`/solicitudes-suscripcion/${accion.fila.id}/accion`, { method: "POST", body: {
      accion: accion.nombre, revision: accion.fila.revision, motivo,
    } }), accion.nombre === "Aplicar" ? "Cambio registrado. Revisa su fecha de inicio en la solicitud." : "Solicitud actualizada correctamente.")) {
      if (accion.nombre === "Aplicar") setFiltro("Aplicada");
      else if (["Rechazar", "Cancelar"].includes(accion.nombre)) setFiltro("Todas");
      setAccion(null);
    }
  }
  async function verHistorial(id: number) {
    try { const detalle = await apiFetch<{ eventos: Evento[] }>(`/solicitudes-suscripcion/${id}`); setHistorial({ id, eventos: detalle.eventos }); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo cargar el historial"); }
  }
  const nombresFunciones = comercial ? catalogo?.funcionalidades ?? [] : opciones.funcionalidades;
  const filtradas = lista.filter(s => (filtro === "Todas" || filtro === "Abiertas" && abiertas.includes(s.estado) || filtro === s.estado) && s.empresa.toLocaleLowerCase().includes(busqueda.toLocaleLowerCase()));
  return <section id="solicitudes" className="space-y-5 scroll-mt-6">
    <header className="flex flex-wrap items-start justify-between gap-3">
      <div><h2 className="text-xl font-bold">{comercial ? "Solicitudes de ampliación" : "Mi suscripción y ampliaciones"}</h2>
        <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{comercial ? "Evalúa la necesidad, envía condiciones y activa únicamente después de la aceptación de la empresa." : "Pide un cambio de plan, más cupos o una renovación. CENERIS responderá aquí; podrás revisar el precio y las condiciones antes de aceptar."}</p></div>
      <div className="flex flex-wrap gap-2"><button type="button" disabled={ocupado} className={secundario} onClick={() => ejecutar(cargar, "Vista actualizada")}>Actualizar solicitudes</button>
        {!comercial && <button type="button" className={boton} disabled={cargando || lista.some(s => abiertas.includes(s.estado))} onClick={() => setCrear(true)}>Solicitar ampliación</button>}</div>
    </header>
    {!comercial && miPlan && <div className="rounded-xl border border-gray-300 p-4 dark:border-white/15">
      <h3 className="font-semibold">{miPlan.plan_nombre ?? "Sin plan asignado"} · {miPlan.estado_suscripcion}</h3>
      <p className="text-sm">Vencimiento: {miPlan.fecha_vencimiento ?? "Sin contrato"}</p>
      <div className="mt-3 grid gap-2 sm:grid-cols-3">{(Object.keys(nombresRecursos) as (keyof Limites)[]).map(r => <p key={r}>{nombresRecursos[r]}: <strong>{miPlan.consumo[r]} / {miPlan.limites ? miPlan.limites[r] || "Sin límite" : "Sin configurar"}</strong></p>)}</div>
      {lista.some(s => abiertas.includes(s.estado)) && <p className="mt-2 text-sm">Tu empresa tiene una solicitud en curso. Puedes seguirla más abajo.</p>}
    </div>}
    {error && <p role="alert" className="rounded-xl bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</p>}
    {mensaje && <p role="status" className="rounded-xl bg-lime-500/10 p-3">{mensaje}</p>}
    {crear && !comercial && <form onSubmit={enviar} className="space-y-4 rounded-2xl border border-lime-500/50 p-5">
      <h3 className="font-bold">Nueva solicitud</h3>
      <label className="block">¿Qué necesita tu empresa?<select aria-label="Tipo de solicitud" className={campo} value={tipo} onChange={e => setTipo(e.target.value)}>{["Cambiar plan", "Ampliar cupos", "Renovar"].map(t => <option key={t}>{t}</option>)}</select></label>
      {tipo === "Cambiar plan" && <label className="block">Plan de interés<select aria-label="Plan de interés" className={campo} required value={planId} onChange={e => setPlanId(e.target.value)}><option value="">Seleccionar plan</option>{opciones.planes.map(p => <option key={p.id_pln} value={p.id_pln}>{p.nombre} · desde {p.moneda} {p.precio_mensual}/mes</option>)}</select></label>}
      {tipo === "Ampliar cupos" && <div><p className="mb-2 text-sm">Indica las cantidades adicionales; 0 significa que no solicitas aumento en ese recurso.</p><div className="grid gap-3 sm:grid-cols-3">{(Object.keys(incrementos) as (keyof Limites)[]).map(r => <label key={r}>{nombresRecursos[r]} adicionales<input className={campo} aria-label={`${nombresRecursos[r]} adicionales`} type="number" min="0" step="1" required value={incrementos[r]} onChange={e => setIncrementos({ ...incrementos, [r]: Number(e.target.value) })} /></label>)}</div></div>}
      <label className="block">Describe tu necesidad<textarea aria-label="Necesidad de ampliación" className={campo} required minLength={10} maxLength={2000} value={descripcion} onChange={e => setDescripcion(e.target.value)} /></label>
      <p className="text-sm">Los precios de los planes son referenciales. Enviar esta solicitud no cambia tu plan ni genera un cobro.</p>
      <div className="flex gap-3"><button className={boton} disabled={ocupado}>Enviar solicitud</button><button type="button" onClick={() => setCrear(false)} disabled={ocupado}>Cancelar</button></div>
    </form>}
    <div className="flex flex-wrap gap-3"><label>Mostrar<select aria-label="Estado de solicitudes" className={campo} value={filtro} onChange={e => setFiltro(e.target.value)}>{["Abiertas", "Todas", ...abiertas, "Aplicada", "Rechazada", "Cancelada"].map(e => <option key={e}>{e}</option>)}</select></label>{comercial && <label className="flex-1">Buscar empresa<input aria-label="Buscar empresa en solicitudes" className={campo} value={busqueda} onChange={e => setBusqueda(e.target.value)} /></label>}</div>
    {cargando && <p>Cargando solicitudes...</p>}
    {!cargando && !filtradas.length && <p className="text-sm">{lista.length ? "No hay solicitudes con estos filtros." : "Todavía no hay solicitudes."}</p>}
    {filtradas.map(s => <article key={s.id} className="space-y-4 rounded-2xl border border-gray-300 bg-white/80 p-5 dark:border-white/15 dark:bg-[#171d2a]/95">
      <header className="flex flex-wrap justify-between gap-2"><div><h3 className="font-bold">#{s.id} · {s.empresa} · {s.solicitud.tipo}</h3><p className="text-sm text-gray-600 dark:text-gray-300">{s.solicitante} · {fecha(s.creada_en)}</p></div><span className="h-fit rounded-full bg-lime-500/15 px-3 py-1 text-sm font-semibold">{s.estado}{s.propuesta_vencida && ["Esperando aceptación", "Aceptada"].includes(s.estado) ? " · Propuesta vencida" : ""}</span></header>
      <p className="whitespace-pre-wrap break-words">{s.solicitud.descripcion}</p>
      {s.solicitud.plan_id && <p>Plan solicitado: {(comercial ? planes : opciones.planes).find(p => p.id_pln === s.solicitud.plan_id)?.nombre ?? `#${s.solicitud.plan_id}`}</p>}
      {Object.entries(s.solicitud.incrementos).some(([, n]) => n > 0) && <p>Cupos adicionales solicitados: {Object.entries(s.solicitud.incrementos).filter(([, n]) => n > 0).map(([r, n]) => `${nombresRecursos[r as keyof Limites]} +${n}`).join(" · ")}</p>}
      {!!s.solicitud.funcionalidades.length && <p>Módulos solicitados: {s.solicitud.funcionalidades.map(c => nombresFunciones.find(f => f.codigo === c)?.nombre ?? c).join(", ")}</p>}
      {s.propuesta && <section aria-label={`Propuesta de solicitud ${s.id}`} className="space-y-2 rounded-xl border border-gray-300 p-4 dark:border-white/15">
        <h4 className="font-bold">Condiciones propuestas · {s.propuesta.condiciones.plan_nombre}</h4>
        <p className="whitespace-pre-wrap break-words">{s.propuesta.mensaje}</p>
        <p className="text-lg font-semibold">{s.propuesta.condiciones.moneda} {s.propuesta.condiciones.precio_acordado} / {s.propuesta.condiciones.periodicidad.toLowerCase()}</p>
        {Number(s.propuesta.condiciones.importe_servicios) > 0 && <p>Servicios puntuales: {s.propuesta.condiciones.moneda} {s.propuesta.condiciones.importe_servicios}</p>}
        <p>Cupos totales: {Object.entries(s.propuesta.condiciones.limites).map(([r, n]) => `${nombresRecursos[r as keyof Limites]}: ${n || "Sin límite"}`).join(" · ")}</p>
        {s.propuesta.condiciones.funcionalidades.some(c => c !== "tableros") && <p>Módulos: {s.propuesta.condiciones.funcionalidades.filter(c => c !== "tableros").map(c => nombresFunciones.find(f => f.codigo === c)?.nombre ?? c).join(", ")}</p>}
        {s.propuesta.condiciones.complementos.map(c => <p key={c.id}>{c.nombre} × {c.cantidad} · {c.tipo}</p>)}
        <p>{s.propuesta.inicio_al_activar ? `${s.propuesta.duracion_dias} días de vigencia desde la activación${s.propuesta.contrato.operacion === "Renovar" ? " o desde el término del contrato anterior, si es posterior" : ""}.` : `Vigencia fija: ${s.propuesta.contrato.fecha_inicio} al ${s.propuesta.contrato.fecha_vencimiento}.`}</p>
        <p>Gracia: {s.propuesta.condiciones.dias_gracia} días · Válida hasta {s.propuesta.valida_hasta} (Lima){s.propuesta.condiciones.es_prueba ? " · Prueba gratuita" : ""}</p>
        {s.propuesta.condiciones.referencia && <p>Referencia: {s.propuesta.condiciones.referencia}</p>}
        {s.propuesta.advertencia && <p className="text-amber-700 dark:text-amber-300">{s.propuesta.advertencia}: {s.propuesta.recursos_excedidos.map(r => nombresRecursos[r as keyof Limites]).join(", ")}</p>}
        {s.aceptante && <p className="font-semibold">Aceptada por {s.aceptante} · {s.aceptada_en && fecha(s.aceptada_en)}</p>}
        {s.estado === "En evaluación" && <p className="text-amber-700 dark:text-amber-300">Esta propuesta está en revisión y no puede activarse.</p>}
      </section>}
      {s.resultado && <p role="status" className="font-semibold">Contrato #{s.resultado.id} · {s.resultado.estado} · {s.resultado.fecha_inicio} al {s.resultado.fecha_vencimiento}{s.resultado.estado === "Programada" ? ". Los nuevos cupos se habilitarán en la fecha de inicio." : ""}</p>}
      {s.estado === "Aceptada" && <p className="font-semibold">Esperando activación de CENERIS. Los cupos actuales se conservan hasta el inicio del nuevo contrato.</p>}
      <div className="flex flex-wrap gap-2">
        {comercial && s.estado === "Pendiente" && <button className={secundario} disabled={ocupado} onClick={() => prepararAccion(s, "Evaluar")}>Iniciar evaluación</button>}
        {comercial && ["Pendiente", "En evaluación", "Esperando aceptación"].includes(s.estado) && <button className={boton} disabled={ocupado} onClick={() => { setProponer(s.id); setAccion(null); }}>Preparar propuesta</button>}
        {comercial && ["Esperando aceptación", "Aceptada"].includes(s.estado) && <button className={secundario} disabled={ocupado} onClick={() => prepararAccion(s, "Reabrir")}>Reabrir revisión</button>}
        {comercial && s.estado === "Aceptada" && !s.propuesta_vencida && <button className={boton} disabled={ocupado} onClick={() => prepararAccion(s, "Aplicar")}>Activar cambio aceptado</button>}
        {!comercial && s.estado === "Esperando aceptación" && !s.propuesta_vencida && <button className={boton} disabled={ocupado} onClick={() => prepararAccion(s, "Aceptar")}>Revisar y aceptar propuesta</button>}
        {!comercial && ["Esperando aceptación", "Aceptada"].includes(s.estado) && <button className={secundario} disabled={ocupado} onClick={() => prepararAccion(s, "Pedir revisión")}>Pedir revisión</button>}
        {((comercial && abiertas.includes(s.estado)) || (!comercial && s.estado === "Esperando aceptación")) && <button className={secundario} disabled={ocupado} onClick={() => prepararAccion(s, "Rechazar")}>Rechazar</button>}
        {abiertas.includes(s.estado) && <button className={secundario} disabled={ocupado} onClick={() => prepararAccion(s, "Cancelar")}>Cancelar solicitud</button>}
        <button className={secundario} disabled={ocupado} onClick={() => verHistorial(s.id)}>Ver seguimiento</button>
      </div>
      {accion?.fila.id === s.id && <form onSubmit={confirmar} className="space-y-3 rounded-xl border border-lime-500 p-4">
        <h4 className="font-bold">Confirmar: {accion.nombre}</h4>
        {accion.nombre === "Aceptar" && <p>Aceptas los importes, cupos y vigencia indicados arriba. CENERIS deberá activar el cambio; esta aceptación no realiza un cobro automático.</p>}
        {accion.nombre === "Aplicar" && <p>Se registrará el contrato con las condiciones aceptadas. La fecha de inicio determinará cuándo entran en vigor los nuevos cupos.</p>}
        {["Reabrir", "Pedir revisión"].includes(accion.nombre) && <p>La aceptación anterior quedará invalidada. Será necesaria una nueva propuesta y aceptación.</p>}
        <label className="block">{accion.nombre === "Aceptar" ? "Confirmación u observación" : "Motivo"}<input aria-label="Motivo de acción" required minLength={3} maxLength={300} className={campo} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
        <div className="flex gap-3"><button className={boton} disabled={ocupado}>Confirmar {accion.nombre.toLowerCase()}</button><button type="button" disabled={ocupado} onClick={() => setAccion(null)}>Volver</button></div>
      </form>}
      {proponer === s.id && comercial && catalogo && clientes.find(c => c.id_clnt === s.cliente_id) && <ContratoFormulario key={`${s.id}-${s.revision}`} solicitud={{ id: s.id, revision: s.revision, plan_id: s.solicitud.plan_id }} cliente={clientes.find(c => c.id_clnt === s.cliente_id)!} planes={planes} catalogo={catalogo} onCancelar={() => setProponer(null)} onGuardado={async () => { setProponer(null); await cargar(); await onCambio?.(); setMensaje("Propuesta enviada. Esperando aceptación del administrador de la empresa."); window.dispatchEvent(new Event("solicitudes-actualizadas")); }} />}
      {historial?.id === s.id && <section className="space-y-2 border-t border-gray-300 pt-3 dark:border-white/15"><h4 className="font-bold">Seguimiento</h4>{historial.eventos.map(e => <p key={e.id} className="text-sm break-words">{fecha(e.fecha)} · {e.actor} · {e.accion} · revisión {e.datos.revision}: {e.datos.motivo}</p>)}</section>}
    </article>)}
    {lista.length >= 200 && <p className="text-sm">Se muestran las últimas 200 solicitudes.</p>}
  </section>;
}
