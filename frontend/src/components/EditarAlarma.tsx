import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch } from "../services/api";

interface Condicion { oprdr: string; vlr_umbrl: number }
interface Detalle { nmbr: string; parametro_nombre: string; unidad: string; condiciones: Condicion[] }

export default function EditarAlarma({ id, onCerrar, onGuardar }: {
  id: number; onCerrar: () => void; onGuardar: () => void;
}) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [detalle, setDetalle] = useState<Detalle | null>(null);
  const [condiciones, setCondiciones] = useState<{ oprdr: string; umbral: string }[]>([]);
  const [error, setError] = useState("");
  const [guardando, setGuardando] = useState(false);
  const [intento, setIntento] = useState(0);
  useEffect(() => { dialogo.current?.showModal(); }, []);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<Detalle>(`/alarmas/${id}`, { signal: controller.signal }).then(d => {
      if (controller.signal.aborted) return;
      setDetalle(d); setError("");
      setCondiciones(d.condiciones.length ? d.condiciones.map(c => ({ oprdr: c.oprdr, umbral: String(c.vlr_umbrl) })) : [{ oprdr: ">", umbral: "" }]);
    }).catch(e => { if (!controller.signal.aborted) setError(e instanceof Error ? e.message : "No se pudo cargar la alarma"); });
    return () => controller.abort();
  }, [id, intento]);

  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (condiciones.some(c => c.umbral.trim() === "" || !Number.isFinite(Number(c.umbral)))) {
      setError("Introduce un umbral numérico para cada condición."); return;
    }
    setGuardando(true); setError("");
    try {
      await apiFetch(`/alarmas/${id}`, { method: "PATCH", body: { condiciones: condiciones.map(c => ({ oprdr: c.oprdr, vlr_umbrl: Number(c.umbral) })) } });
      onGuardar();
    } catch (e) { setError(e instanceof Error ? e.message : "No se pudieron guardar las condiciones"); }
    finally { setGuardando(false); }
  }
  const boton = "rounded-xl border border-black/20 px-3 py-2 text-sm dark:border-white/20 disabled:opacity-50";
  return <dialog ref={dialogo} onCancel={e => { if (guardando) e.preventDefault(); else onCerrar(); }} aria-labelledby="editar-alarma-titulo"
    className="w-[calc(100%-2rem)] max-w-xl max-h-[90vh] rounded-2xl bg-white p-6 text-gray-900 dark:bg-gray-950 dark:text-white backdrop:bg-black/50">
    <header className="mb-4 flex items-center justify-between gap-3"><h2 id="editar-alarma-titulo" className="text-xl font-bold">Editar condiciones{detalle ? ` de ${detalle.nmbr}` : ""}</h2><button type="button" className={boton} onClick={onCerrar} disabled={guardando}>Cerrar</button></header>
    {error && <p role="alert" className="my-3 text-sm text-red-700 dark:text-red-300">{error}{!detalle && <button type="button" className="ml-2 underline" onClick={() => setIntento(n => n + 1)}>Reintentar</button>}</p>}
    {!detalle && !error && <p role="status">Cargando condiciones…</p>}
    {detalle && <form onSubmit={guardar} className="space-y-4">
      <p className="text-sm">{detalle.parametro_nombre} ({detalle.unidad}). La alarma se activa cuando se cumple cualquiera de las condiciones.</p>
      <fieldset disabled={guardando} className="space-y-3">
        <legend className="sr-only">Condiciones de la alarma</legend>
        {condiciones.map((c, i) => <div key={i} className="flex flex-wrap items-end gap-2">
          <label className="text-sm">Operador {i + 1}<select aria-label={`Operador ${i + 1}`} value={c.oprdr} className="mt-1 block rounded-lg border border-gray-400 bg-transparent p-2" onChange={e => setCondiciones(actual => actual.map((v, indice) => indice === i ? { ...v, oprdr: e.target.value } : v))}>{[">", ">=", "<", "<=", "="].map(op => <option key={op}>{op}</option>)}</select></label>
          <label className="min-w-0 flex-1 text-sm">Umbral {i + 1}<input aria-label={`Umbral ${i + 1}`} type="number" step="0.0001" min="-9999999999.9999" max="9999999999.9999" required value={c.umbral} className="mt-1 block w-full rounded-lg border border-gray-400 bg-transparent p-2" onChange={e => setCondiciones(actual => actual.map((v, indice) => indice === i ? { ...v, umbral: e.target.value } : v))} /></label>
          {condiciones.length > 1 && <button type="button" className={boton} aria-label={`Quitar condición ${i + 1}`} onClick={() => setCondiciones(actual => actual.filter((_, indice) => indice !== i))}>Quitar</button>}
        </div>)}
        <button type="button" className={boton} disabled={condiciones.length >= 20} onClick={() => setCondiciones(actual => [...actual, { oprdr: ">", umbral: "" }])}>Añadir condición</button>
      </fieldset>
      <p className="text-xs text-gray-600 dark:text-gray-300">Los equipos volverán a evaluar la regla con la siguiente lectura nueva.</p>
      <button type="submit" disabled={guardando} className="rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 disabled:opacity-50">{guardando ? "Guardando…" : "Guardar condiciones"}</button>
    </form>}
  </dialog>;
}
