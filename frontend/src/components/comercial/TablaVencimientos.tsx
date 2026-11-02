import { useEffect, useState } from "react";
import { apiFetch } from "../../services/api";
import { fechaVisible } from "./asignacionPlan";
import { RANGOS_VENCIMIENTO, diasRestantesTexto, type RangoVencimiento } from "./vencimientos";

export type FilaVencimiento = {
  id_clnt: number; razon_social: string; ruc: string; suscripcion_id: number; plan_nombre: string | null;
  fecha_inicio: string; fecha_vencimiento: string; dias_restantes: number; estado: string; vencida: boolean;
};

const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 outline-none focus:border-lime-500 dark:border-white/20 dark:bg-[#242b39] dark:text-white";

/**
 * PP-68 - Consultar vencimientos.
 * CA1 (PP-314): razón social, plan, fecha de vencimiento y días restantes, del más próximo al más lejano.
 * CA2 (PP-315): filtro por rango de días restantes.
 * PP-316: las suscripciones vencidas se resaltan.
 * CA3: "Renovar" lleva a Asignar plan (HU45) con el cliente preseleccionado.
 */
export default function TablaVencimientos({ rango, onRango, onRenovar }: {
  rango: RangoVencimiento;
  onRango: (rango: RangoVencimiento) => void;
  onRenovar: (fila: FilaVencimiento) => void;
}) {
  const [filas, setFilas] = useState<FilaVencimiento[] | null>(null);
  const [error, setError] = useState("");

  useEffect(() => {
    let activo = true;
    apiFetch<FilaVencimiento[]>(`/comercial/vencimientos?rango=${rango}`)
      .then((lista) => { if (activo) { setFilas(lista); setError(""); } })
      .catch((e: Error) => { if (activo) setError(e.message); });
    return () => { activo = false; };
  }, [rango]);

  const vencidas = filas?.filter((fila) => fila.vencida).length ?? 0;

  return <section className="space-y-4" aria-label="Vencimientos">
    <div className="flex flex-wrap items-end justify-between gap-4">
      <div>
        <h2 className="text-xl font-semibold">Vencimientos</h2>
        <p className="text-sm text-gray-600 dark:text-gray-300">Clientes con suscripción activa, del vencimiento más próximo al más lejano.</p>
      </div>
      <label className="block w-full max-w-xs">
        <span className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200">Días restantes</span>
        <select className={campo} value={rango} onChange={(e) => onRango(e.target.value as RangoVencimiento)}>
          {RANGOS_VENCIMIENTO.map((opcion) => <option key={opcion.valor} value={opcion.valor}>{opcion.texto}</option>)}
        </select>
      </label>
    </div>
    {error && <div role="alert" className="rounded-xl border border-red-400/50 bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</div>}
    {filas === null && !error && <p>Cargando vencimientos...</p>}
    {filas?.length === 0 && <p className="rounded-2xl border border-dashed border-gray-400 p-5">No hay clientes con vencimiento en este rango.</p>}
    {filas && filas.length > 0 && <>
      <p className="text-sm text-gray-600 dark:text-gray-300">{filas.length} {filas.length === 1 ? "cliente" : "clientes"}{vencidas > 0 ? ` · ${vencidas} con suscripción vencida` : ""}</p>
      <div className="overflow-x-auto rounded-2xl border border-gray-200 bg-white/80 shadow-sm dark:border-white/10 dark:bg-[#171d2a]/90">
        <table className="w-full text-left text-sm">
          <thead className="border-b border-gray-300 dark:border-white/20">
            <tr>
              <th className="px-4 py-3">Razón social</th><th className="px-4 py-3">Plan asignado</th>
              <th className="px-4 py-3">Fecha de vencimiento</th><th className="px-4 py-3">Días restantes</th><th className="px-4 py-3">Acción</th>
            </tr>
          </thead>
          <tbody>
            {filas.map((fila) => <tr key={fila.id_clnt} data-vencida={fila.vencida}
              className={`border-b border-gray-200 dark:border-white/10 ${fila.vencida ? "bg-red-500/10 text-red-800 dark:text-red-200" : ""}`}>
              <td className="px-4 py-3">
                <span className="font-semibold">{fila.razon_social}</span>
                <span className="block text-xs text-gray-500 dark:text-gray-400">RUC {fila.ruc}</span>
              </td>
              <td className="px-4 py-3">{fila.plan_nombre ?? "—"}</td>
              <td className="px-4 py-3">{fechaVisible(fila.fecha_vencimiento)}</td>
              <td className="px-4 py-3">
                <span className="font-semibold">{diasRestantesTexto(fila.dias_restantes)}</span>
                {fila.estado !== "Vigente" && <span className={`ml-2 rounded-full px-2 py-0.5 text-xs font-semibold ${fila.vencida && fila.estado === "Vencida" ? "bg-red-600 text-white" : "bg-amber-500/20 text-amber-800 dark:text-amber-300"}`}>{fila.estado}</span>}
              </td>
              <td className="px-4 py-3">
                <button type="button" className="rounded-xl bg-[#ccff00] px-3 py-1.5 text-sm font-semibold text-gray-950 hover:bg-[#b9eb00]" onClick={() => onRenovar(fila)}>Renovar</button>
              </td>
            </tr>)}
          </tbody>
        </table>
      </div>
    </>}
  </section>;
}
