import { useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import { fechaLima, sumarDias, nombresRecursos, type Catalogo, type Cliente, type Condiciones, type Limites, type Plan } from "../../types/comercial";

const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const boton = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 disabled:opacity-50";
type Preview = { condiciones: Condiciones; suscripcion_actual_id: number | null; revision_plan: number;
  fecha_inicio: string; fecha_vencimiento: string; advertencia: string | null; recursos_excedidos: string[] };

export default function ContratoFormulario({ cliente, planes, catalogo, onCancelar, onGuardado, solicitud }: {
  cliente: Cliente; planes: Plan[]; catalogo: Catalogo; onCancelar: () => void; onGuardado: () => Promise<void>;
  solicitud?: { id: number; revision: number; plan_id: number | null };
}) {
  const [operacion, setOperacion] = useState(cliente.suscripcion_id ? "Cambiar" : "Crear");
  const [planId, setPlanId] = useState(String(solicitud?.plan_id ?? cliente.plan_id ?? ""));
  const [inicio, setInicio] = useState(fechaLima());
  const [fin, setFin] = useState(sumarDias(fechaLima(), 365));
  const [periodicidad, setPeriodicidad] = useState(cliente.condiciones?.periodicidad ?? "Mensual");
  const [precio, setPrecio] = useState("");
  const [referencia, setReferencia] = useState("");
  const [motivo, setMotivo] = useState("");
  const [gracia, setGracia] = useState(0);
  const [prueba, setPrueba] = useState(false);
  const [personalizar, setPersonalizar] = useState(false);
  const [limites, setLimites] = useState<Limites>(cliente.limites ?? { ubicaciones: 0, dispositivos: 0, usuarios: 0 });
  const [preview, setPreview] = useState<Preview | null>(null);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const [clave] = useState(() => crypto.randomUUID());
  const [mensajePropuesta, setMensajePropuesta] = useState("");
  const [validez, setValidez] = useState(sumarDias(fechaLima(), 7));
  const [inicioAlActivar, setInicioAlActivar] = useState(true);
  const plan = planes.find(p => String(p.id_pln) === planId);
  const cuerpo = {
    plan_id: Number(planId), operacion, fecha_inicio: inicio, fecha_vencimiento: fin,
    moneda: plan?.moneda, periodicidad, precio_acordado: precio === "" ? null : precio,
    referencia: referencia || null, motivo, dias_gracia: gracia, es_prueba: prueba,
    limites_acordados: personalizar ? limites : null,
  };
  async function revisar(event: FormEvent) {
    event.preventDefault(); setOcupado(true); setError(""); setPreview(null);
    try { setPreview(await apiFetch<Preview>(`/comercial/clientes/${cliente.id_clnt}/suscripcion/preview`, { method: "POST", body: cuerpo })); }
    catch (e) { setError(e instanceof Error ? e.message : "No se pudo revisar la suscripción"); }
    finally { setOcupado(false); }
  }
  async function confirmar() {
    if (!preview || ocupado) return;
    setOcupado(true); setError("");
    try {
      const contrato = {
        ...cuerpo, revision_plan: preview.revision_plan, suscripcion_actual_id: preview.suscripcion_actual_id,
        clave_idempotencia: clave,
      };
      if (solicitud) {
        await apiFetch(`/solicitudes-suscripcion/${solicitud.id}/propuesta`, { method: "POST", body: {
          revision: solicitud.revision, contrato, mensaje: mensajePropuesta, valida_hasta: validez, inicio_al_activar: inicioAlActivar,
        } });
      } else {
        await apiFetch(`/comercial/clientes/${cliente.id_clnt}/suscripcion`, { method: "PUT", body: contrato });
      }
      await onGuardado();
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudo guardar la suscripción"); }
    finally { setOcupado(false); }
  }
  return <form onSubmit={revisar} onChange={() => setPreview(null)} className="space-y-5 rounded-2xl border border-lime-500/50 bg-white/80 p-5 dark:bg-[#171d2a]">
    <h3 className="text-xl font-semibold">Suscripción de {cliente.nombre}</h3>
    {solicitud && <fieldset className="space-y-3 rounded-xl border border-gray-300 p-4 dark:border-white/20">
      <legend className="font-semibold">Propuesta para la solicitud #{solicitud.id}</legend>
      <label className="block">Respuesta a la empresa<textarea aria-label="Respuesta comercial" required minLength={10} maxLength={2000} className={campo} value={mensajePropuesta} onChange={e => setMensajePropuesta(e.target.value)} /></label>
      <label className="block">Propuesta válida hasta<input type="date" required min={fechaLima()} max={sumarDias(fechaLima(), 30)} className={campo} value={validez} onChange={e => setValidez(e.target.value)} /></label>
      <label className="flex items-center gap-2"><input type="checkbox" checked={inicioAlActivar} onChange={e => setInicioAlActivar(e.target.checked)} />Comenzar al activar y conservar la duración indicada abajo</label>
      <p className="text-sm">En renovaciones, la vigencia comienza después del contrato actual. Desmarca esta opción para acordar fechas fijas. La empresa debe aceptar antes de que CENERIS pueda activar.</p>
    </fieldset>}
    <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-3">
      <label>Acción<select aria-label="Acción de suscripción" className={campo} value={operacion} onChange={e => {
        setOperacion(e.target.value);
        const nuevoInicio = e.target.value === "Renovar" && cliente.fecha_vencimiento ? [fechaLima(), sumarDias(cliente.fecha_vencimiento, 1)].sort().at(-1)! : fechaLima();
        setInicio(nuevoInicio);
        setFin(sumarDias(nuevoInicio, prueba ? 14 : 365));
      }}><option>Crear</option><option>Cambiar</option><option>Renovar</option></select></label>
      <label>Plan<select aria-label="Plan a contratar" className={campo} required value={planId} onChange={e => setPlanId(e.target.value)}>
        <option value="">Seleccionar plan</option>{planes.filter(p => p.limites && p.estado === "Activo").map(p => <option key={p.id_pln} value={p.id_pln}>{p.nombre} · revisión {p.revision}</option>)}
      </select></label>
      <label>Periodicidad del importe<select className={campo} value={periodicidad} onChange={e => setPeriodicidad(e.target.value)}><option>Mensual</option><option>Trimestral</option><option>Anual</option></select></label>
      <label>Inicio de vigencia<input aria-label="Inicio de vigencia" className={campo} type="date" min={fechaLima()} required value={inicio} onChange={e => setInicio(e.target.value)} /></label>
      <label>Fin de vigencia<input aria-label="Fin de vigencia" className={campo} type="date" min={inicio} required value={fin} onChange={e => setFin(e.target.value)} /></label>
      <label>Importe acordado por período ({plan?.moneda ?? "PEN"})<input className={campo} type="number" min="0" step="0.01" placeholder="Usar precio del plan" value={precio} disabled={prueba} onChange={e => setPrecio(e.target.value)} /></label>
      <label>Referencia de cotización o contrato<input className={campo} maxLength={200} value={referencia} onChange={e => setReferencia(e.target.value)} /></label>
      <label>Motivo del alta o cambio<input aria-label="Motivo del cambio" className={campo} required minLength={3} maxLength={300} value={motivo} onChange={e => setMotivo(e.target.value)} /></label>
      <label>Días de gracia después del vencimiento<input className={campo} type="number" min="0" max="30" value={gracia} onChange={e => setGracia(Number(e.target.value))} /></label>
    </div>
    <label className="flex items-center gap-2"><input type="checkbox" checked={prueba} onChange={e => { setPrueba(e.target.checked); if (e.target.checked) { setGracia(0); setFin(sumarDias(inicio, 14)); } }} />Prueba gratuita de hasta 30 días</label>
    <label className="flex items-center gap-2"><input type="checkbox" checked={personalizar} onChange={e => setPersonalizar(e.target.checked)} />Acordar cupos particulares para esta empresa</label>
    {personalizar && <div className="grid gap-3 sm:grid-cols-3">{(Object.keys(limites) as (keyof Limites)[]).map(r => <label key={r}>{nombresRecursos[r]} (0 = sin límite)<input className={campo} type="number" min="0" required value={limites[r]} onChange={e => setLimites({ ...limites, [r]: Number(e.target.value) })} /></label>)}</div>}
    <p className="text-sm text-gray-600 dark:text-gray-300">Al vencer el contrato y su gracia, se bloquearán altas y configuración operativa. Se conservarán la consulta histórica y la recepción de telemetría. Los importes se registran como condiciones comerciales; no generan cobros automáticos.</p>
    {error && <p role="alert" className="text-red-600 dark:text-red-300">{error}</p>}
    <div className="flex gap-3"><button className={boton} disabled={ocupado}>Revisar condiciones</button><button type="button" onClick={onCancelar} disabled={ocupado}>Cancelar</button></div>
    {preview && <section aria-label="Revisión de condiciones" className="space-y-3 rounded-xl border border-lime-500 p-4">
      <h4 className="font-bold">Confirmar condiciones de {cliente.nombre}</h4>
      <p>{preview.condiciones.plan_nombre} · revisión {preview.revision_plan} · {preview.fecha_inicio} al {preview.fecha_vencimiento}</p>
      {solicitud && <p>Válida hasta {validez}. {inicioAlActivar ? "Las fechas se desplazan al activar, conservando la duración; las renovaciones empiezan al terminar el contrato anterior." : "Se mantendrán exactamente las fechas indicadas."}</p>}
      <p className="font-semibold">{preview.condiciones.moneda} {preview.condiciones.precio_acordado} / {preview.condiciones.periodicidad.toLowerCase()}{preview.condiciones.es_prueba ? " · Prueba gratuita" : ""}</p>
      {Number(preview.condiciones.importe_servicios) > 0 && <p>Servicios puntuales: {preview.condiciones.moneda} {preview.condiciones.importe_servicios}</p>}
      <p>{Object.entries(preview.condiciones.limites).map(([r, n]) => `${nombresRecursos[r as keyof Limites]}: ${n || "sin límite"}`).join(" · ")}</p>
      {preview.condiciones.funcionalidades.some(c => c !== "tableros") && <p>Funcionalidades: {preview.condiciones.funcionalidades.filter(c => c !== "tableros").map(c => catalogo.funcionalidades.find(f => f.codigo === c)?.nombre ?? c).join(", ")}</p>}
      {preview.condiciones.complementos.map(c => <p key={c.id}>{c.nombre} × {c.cantidad}</p>)}
      <p>{solicitud ? "Enviar esta propuesta no modifica la suscripción. Requiere aceptación de la empresa y activación de CENERIS." : inicio > fechaLima() ? `Se aplicará el ${inicio}. La suscripción actual continúa hasta entonces.` : "El cambio se aplicará al confirmar."}</p>
      {preview.advertencia && <p role="alert" className="font-semibold text-amber-700 dark:text-amber-300">{preview.advertencia}. Recursos: {preview.recursos_excedidos.map(r => nombresRecursos[r as keyof Limites]).join(", ")}.</p>}
      <button type="button" className={boton} disabled={ocupado} onClick={confirmar}>{solicitud ? "Enviar propuesta para aceptación" : "Confirmar suscripción"}</button>
    </section>}
  </form>;
}
