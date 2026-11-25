import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import DrawerPanel from "./layout/DrawerPanel";
import ResultadosCalculados from "./ResultadosCalculados";

export default function ConsultaCalculo({ id, onCerrar }: { id: number; onCerrar: () => void }) {
  const [data, setData] = useState<{ nombre: string; unidad: string; descripcion: string | null; frml: string; referencias: { variable: string; nombre: string | null; unidad: string | null }[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<NonNullable<typeof data>>(`/mediciones/calculados/${id}`, { signal: controller.signal })
      .then(res => { if (!controller.signal.aborted) { setData(res); setError(null); } })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof ApiError ? err.message : "No se pudo cargar la definición."); });
    return () => controller.abort();
  }, [id, revision]);
  return <DrawerPanel abierto titulo="Definición y resultados del cálculo" onCerrar={onCerrar} ancho="lg">
    <div className="space-y-4 text-sm text-gray-800 dark:text-gray-200">
      {error ? <div role="alert"><p>{error}</p><button type="button" className="underline" onClick={() => setRevision(v => v + 1)}>Reintentar definición</button></div> : !data ? <p>Cargando definición…</p> : <>
        <h3 className="text-lg font-bold">{data.nombre} ({data.unidad})</h3>
        {data.descripcion && <p>{data.descripcion}</p>}
        <p className="whitespace-pre-wrap break-words rounded-xl bg-black/5 p-3 font-mono dark:bg-white/5">{data.frml}</p>
        <p>Parámetros de origen: {data.referencias.map(r => `${r.nombre || "Referencia no disponible"} (${r.unidad || "Sin unidad"})`).join(", ")}</p>
        <ResultadosCalculados id={id} />
      </>}
    </div>
  </DrawerPanel>;
}
