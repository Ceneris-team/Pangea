import { useEffect, useRef, useState } from "react";
import { apiFetch } from "../../services/api";
import { fechaVisible } from "./asignacionPlan";
import { montoVisible } from "./registroCobro";

export type CobroItem = {
  id: number; monto: string; moneda: string; fecha_cobro: string; metodo_pago: string; fecha_registro: string;
  suscripcion_id: number; plan_nombre: string | null; periodo_inicio: string; periodo_fin: string;
};

/** PP-67 CA3: historial de cobros del cliente con monto, fecha y método de pago. */
export default function HistorialCobros({ clienteId, nombre, recarga, onCerrar }: {
  clienteId: number; nombre: string; recarga: number; onCerrar: () => void;
}) {
  const [cobros, setCobros] = useState<CobroItem[] | null>(null);
  const [error, setError] = useState("");
  const panel = useRef<HTMLElement>(null);

  useEffect(() => {
    let activo = true;
    apiFetch<CobroItem[]>(`/comercial/clientes/${clienteId}/cobros`)
      .then((lista) => { if (activo) { setCobros(lista); setError(""); } })
      .catch((e: Error) => { if (activo) setError(e.message); });
    return () => { activo = false; };
  }, [clienteId, recarga]);

  useEffect(() => { panel.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }); }, [clienteId]);

  return <section ref={panel} aria-label="Historial de cobros" className="scroll-mt-28 space-y-4 rounded-2xl border border-gray-200 bg-white/80 p-5 shadow-sm dark:border-white/10 dark:bg-[#171d2a]/90">
    <div className="flex flex-wrap items-center justify-between gap-3">
      <h3 className="text-lg font-semibold">Historial de cobros de {nombre}</h3>
      <button type="button" className="text-sm font-semibold underline" onClick={onCerrar}>Cerrar</button>
    </div>
    {error && <p role="alert" className="text-red-600 dark:text-red-300">{error}</p>}
    {cobros === null && !error && <p>Cargando cobros...</p>}
    {cobros?.length === 0 && <p className="text-gray-600 dark:text-gray-300">Todavía no hay cobros registrados.</p>}
    {cobros && cobros.length > 0 && <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead className="border-b border-gray-300 dark:border-white/20">
          <tr><th className="py-2 pr-4">Fecha de cobro</th><th className="py-2 pr-4">Monto</th><th className="py-2 pr-4">Método de pago</th><th className="py-2">Período</th></tr>
        </thead>
        <tbody>
          {cobros.map((cobro) => <tr key={cobro.id} className="border-b border-gray-200 dark:border-white/10">
            <td className="py-2 pr-4">{fechaVisible(cobro.fecha_cobro)}</td>
            <td className="py-2 pr-4 font-semibold">{cobro.moneda} {montoVisible(cobro.monto)}</td>
            <td className="py-2 pr-4">{cobro.metodo_pago}</td>
            <td className="py-2">{cobro.plan_nombre} · {fechaVisible(cobro.periodo_inicio)} al {fechaVisible(cobro.periodo_fin)}</td>
          </tr>)}
        </tbody>
      </table>
    </div>}
  </section>;
}
