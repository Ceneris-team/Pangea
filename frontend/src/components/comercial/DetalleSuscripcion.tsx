import { useEffect, useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import { nombresRecursos, type Condiciones, type Limites } from "../../types/comercial";

type Contrato = { id: number; fecha_inicio: string; fecha_vencimiento: string; estado: string; condiciones: Condiciones };
type Historial = { suscripciones: Contrato[]; eventos: { id: number; actor_id: number; actor_nombre: string;
  fecha: string; accion: string; despues: { motivo?: string } }[] };

export default function DetalleSuscripcion({ clienteId, gestionar = false, onCambio }: {
  clienteId: number; gestionar?: boolean; onCambio?: () => Promise<void>;
}) {
  const [historial, setHistorial] = useState<Historial | null>(null);
  const [error, setError] = useState("");
  const [seleccion, setSeleccion] = useState<{ id: number; accion: string } | null>(null);
  const [motivo, setMotivo] = useState("");
  const [ocupado, setOcupado] = useState(false);
  async function cargar() { setHistorial(await apiFetch<Historial>(`/comercial/clientes/${clienteId}/historial`)); }
  useEffect(() => {
    let vigente = true;
    queueMicrotask(() => {
      if (vigente) { setHistorial(null); setError(""); setSeleccion(null); }
    });
    apiFetch<Historial>(`/comercial/clientes/${clienteId}/historial`).then(data => { if (vigente) setHistorial(data); })
      .catch(e => { if (vigente) setError(e instanceof Error ? e.message : "No se pudo cargar el historial"); });
    return () => { vigente = false; };
  }, [clienteId]);
  async function confirmar(event: FormEvent) {
    event.preventDefault(); if (!seleccion) return;
    setOcupado(true); setError("");
    try {
      await apiFetch(`/comercial/clientes/${clienteId}/suscripciones/${seleccion.id}/estado`, {
        method: "POST", body: { accion: seleccion.accion, motivo },
      });
      setSeleccion(null); setMotivo(""); await cargar(); await onCambio?.();
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo actualizar"); }
    finally { setOcupado(false); }
  }
  return <section className="space-y-4 rounded-2xl border border-gray-200 bg-white/80 p-5 dark:border-white/10 dark:bg-[#171d2a]">
    <h3 className="text-xl font-semibold">Condiciones e historial de suscripciones</h3>
    {error && <p role="alert" className="text-red-600 dark:text-red-300">{error}</p>}
    {!historial && !error && <p>Cargando historial...</p>}
    {historial?.suscripciones.map(c => <article key={c.id} className="space-y-2 rounded-xl border border-gray-300 p-4 dark:border-white/20">
      <h4 className="font-semibold">{c.condiciones.plan_nombre} · revisión {c.condiciones.revision_plan} · {c.estado}</h4>
      <p>{c.fecha_inicio} al {c.fecha_vencimiento} · {c.condiciones.moneda} {c.condiciones.precio_acordado} / {c.condiciones.periodicidad.toLowerCase()}{c.condiciones.es_prueba ? " · Prueba" : ""}</p>
      <p className="text-sm">{Object.entries(c.condiciones.limites ?? {}).map(([r, n]) => `${nombresRecursos[r as keyof Limites]}: ${n || "sin límite"}`).join(" · ")}</p>
      <p className="text-sm">Referencia: {c.condiciones.referencia || "Sin referencia"} · Gracia: {c.condiciones.dias_gracia} días</p>
      <p className="text-sm">Motivo: {c.condiciones.motivo}</p>
      {c.condiciones.complementos.map(extra => <p key={extra.id} className="text-sm">{extra.nombre} × {extra.cantidad} · {extra.tipo}</p>)}
      {Number(c.condiciones.importe_servicios) > 0 && <p className="text-sm">Servicios puntuales: {c.condiciones.moneda} {c.condiciones.importe_servicios}</p>}
      {gestionar && <div className="flex flex-wrap gap-3">{[
        ...(["Vigente", "En gracia"].includes(c.estado) ? ["Suspender", "Cancelar"] : []),
        ...(c.estado === "Suspendida" ? ["Reactivar", "Cancelar"] : []),
        ...(c.estado === "Programada" ? ["Cancelar"] : []),
      ].map(accion => <button key={accion} type="button" className="rounded-lg border border-gray-300 px-3 py-1 dark:border-white/20" onClick={() => { setSeleccion({ id: c.id, accion }); setMotivo(""); }}>{accion}{c.estado === "Programada" ? " programación" : ""}</button>)}</div>}
    </article>)}
    {historial?.suscripciones.length === 0 && <p>No hay suscripciones registradas.</p>}
    {seleccion && <form onSubmit={confirmar} className="space-y-3 rounded-xl border border-amber-500 p-4">
      <h4 className="font-semibold">Confirmar: {seleccion.accion.toLowerCase()} suscripción</h4>
      <p className="text-sm">La acción se aplica al confirmar. Los datos históricos y la recepción de telemetría se conservan.</p>
      {seleccion.accion === "Cancelar" && <p className="text-sm">Cancelar la suscripción vigente también anula sus cambios futuros programados. Cancelar solo una programación conserva la suscripción vigente.</p>}
      <input aria-label="Motivo de la acción" className="w-full rounded-xl border border-gray-300 bg-white p-2 dark:border-white/20 dark:bg-[#242b39]" placeholder="Motivo obligatorio" required minLength={3} maxLength={300} value={motivo} onChange={e => setMotivo(e.target.value)} />
      <div className="flex gap-3"><button className="rounded-lg bg-[#ccff00] px-4 py-2 font-semibold text-gray-950" disabled={ocupado}>Confirmar acción</button><button type="button" disabled={ocupado} onClick={() => setSeleccion(null)}>Volver</button></div>
    </form>}
    <h4 className="font-semibold">Registro de cambios</h4>
    {historial?.eventos.map(e => <p key={e.id} className="text-sm text-gray-600 dark:text-gray-300">{new Date(e.fecha).toLocaleString("es-PE", { timeZone: "America/Lima" })} · {e.actor_nombre || `Usuario ${e.actor_id}`} · {e.accion}{e.despues?.motivo ? ` · ${e.despues.motivo}` : ""}</p>)}
    {historial?.eventos.length === 0 && <p className="text-sm">No hay cambios posteriores a la migración.</p>}
  </section>;
}
