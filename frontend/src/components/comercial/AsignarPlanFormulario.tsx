import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import { fechaLima, type Cliente, type Plan } from "../../types/comercial";
import { fechaVisible, planesActivos, planSinLimites, validarAsignacion, vencimientoPlan } from "./asignacionPlan";

const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 outline-none focus:border-lime-500 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const campoConError = "border-red-500 dark:border-red-400";
const etiqueta = "mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200";
const boton = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 hover:bg-[#b9eb00] disabled:cursor-not-allowed disabled:opacity-50";

/**
 * HU 45 - Asignar plan a cliente (PP-308).
 * CA1: selector de plan (solo Activos, HU42) y Fecha de inicio de suscripción.
 * CA2/CA4: CONFIRMAR ASIGNACIÓN; la página muestra "Plan asignado correctamente"
 * o "Plan actualizado correctamente" según lo que responda la API.
 */
export default function AsignarPlanFormulario({ cliente, planes, onCancelar, onAsignado, inicioSugerido }: {
  cliente: Cliente;
  planes: Plan[];
  onCancelar: () => void;
  onAsignado: (mensaje: string) => Promise<void>;
  /** PP-68 "Renovar": fecha de inicio propuesta (el día siguiente al vencimiento). */
  inicioSugerido?: string;
}) {
  const hoy = fechaLima();
  const disponibles = planesActivos(planes);
  const [planId, setPlanId] = useState("");
  const [inicio, setInicio] = useState(inicioSugerido ?? hoy);
  const [errores, setErrores] = useState<{ plan?: string; fecha?: string }>({});
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const vencimiento = vencimientoPlan(inicio);
  const formulario = useRef<HTMLFormElement>(null);

  // El botón "Asignar plan" está en la tarjeta del cliente, más abajo: se
  // lleva la vista al formulario para que no quede fuera de pantalla.
  useEffect(() => { formulario.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }); }, []);

  async function confirmar(evento: FormEvent) {
    evento.preventDefault();
    setError("");
    const encontrados = validarAsignacion(planId, inicio, hoy);
    setErrores(encontrados);
    if (Object.keys(encontrados).length > 0) return;
    setOcupado(true);
    try {
      const respuesta = await apiFetch<{ mensaje: string }>(`/comercial/clientes/${cliente.id_clnt}/plan`, {
        method: "POST", body: { plan_id: Number(planId), fecha_inicio: inicio },
      });
      await onAsignado(respuesta.mensaje);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo asignar el plan");
    } finally {
      setOcupado(false);
    }
  }

  return <form ref={formulario} onSubmit={confirmar} noValidate aria-label="Asignar plan" className="scroll-mt-28 space-y-5 rounded-2xl border border-lime-500/50 bg-white/80 p-5 dark:bg-[#171d2a]">
    <div>
      <h3 className="text-lg font-semibold">Asignar plan a {cliente.nombre}</h3>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        {cliente.plan_nombre ? `Plan actual: ${cliente.plan_nombre}. El plan nuevo lo reemplazará.` : "El cliente todavía no tiene plan."}
      </p>
      {inicioSugerido && inicioSugerido > hoy && <p className="text-sm text-gray-600 dark:text-gray-300">
        Renovación: empieza el {fechaVisible(inicioSugerido)}, al día siguiente del vencimiento actual, y queda programada hasta esa fecha.
      </p>}
    </div>
    {error && <div role="alert" className="rounded-xl border border-red-400/50 bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</div>}
    <div className="grid gap-4 md:grid-cols-3">
      <label>
        <span className={etiqueta}>Plan *</span>
        <select className={`${campo} ${errores.plan ? campoConError : ""}`} value={planId} aria-invalid={Boolean(errores.plan)}
          onChange={(e) => { setPlanId(e.target.value); setErrores({ ...errores, plan: undefined }); }}>
          <option value="">Seleccionar plan</option>
          {disponibles.map((plan) => (
            <option key={plan.id_pln} value={plan.id_pln} disabled={planSinLimites(plan)}>
              {plan.nombre} · {plan.moneda} {plan.precio_mensual} / mes{planSinLimites(plan) ? " (sin límites configurados)" : ""}
            </option>
          ))}
        </select>
        {errores.plan && <span className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores.plan}</span>}
        {disponibles.length === 0 && <span className="mt-1 block text-sm text-amber-700 dark:text-amber-300">No hay planes activos. Créalo en la pestaña Planes.</span>}
      </label>
      <label>
        <span className={etiqueta}>Fecha de inicio de suscripción *</span>
        <input className={`${campo} ${errores.fecha ? campoConError : ""}`} type="date" min={hoy} value={inicio} aria-invalid={Boolean(errores.fecha)}
          onChange={(e) => { setInicio(e.target.value); setErrores({ ...errores, fecha: undefined }); }} />
        {errores.fecha && <span className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores.fecha}</span>}
      </label>
      <div>
        <span className={etiqueta}>Fecha de vencimiento</span>
        <p className="rounded-xl border border-dashed border-gray-300 px-3 py-2 dark:border-white/20" aria-label="Fecha de vencimiento calculada">{fechaVisible(vencimiento)}</p>
        <span className="mt-1 block text-xs text-gray-500 dark:text-gray-400">Se calcula sola: inicio + 30 días.</span>
      </div>
    </div>
    <div className="flex gap-3">
      <button className={boton} disabled={ocupado}>{ocupado ? "Asignando..." : "CONFIRMAR ASIGNACIÓN"}</button>
      <button type="button" className="rounded-xl border border-gray-300 px-4 py-2 font-semibold dark:border-white/20" onClick={onCancelar} disabled={ocupado}>CANCELAR</button>
    </div>
  </form>;
}
