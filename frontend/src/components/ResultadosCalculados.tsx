import { useEffect, useState } from "react";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import { formatearFechaHoraEnZona } from "../utils/fechas";

interface Origen { nombre?: string; tipo: string; fecha: string; valor: number | null; unidad: string; estado?: string }
interface Traza { formula: string; unidad: string; configuracion: { tolerancia_segundos: number; espera_horas: number }; origenes: Record<string, Origen> }
interface Resultado { id: number; fecha: string; ubicacion: string; valor: number | null; unidad: string; estado: string; causa: string | null; revision: number; trazabilidad: Traza }
interface Revision { revision: number; fecha: string; estado: string; valor: number | null; causa: string | null }

export default function ResultadosCalculados({ id }: { id: number }) {
  const { zonaHoraria } = useAuth();
  const [pagina, setPagina] = useState(1);
  const [estado, setEstado] = useState("");
  const [data, setData] = useState<{ total: number; items: Resultado[] } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [historiales, setHistoriales] = useState<Record<number, { total: number; items: Revision[] }>>({});
  const [errorHistorial, setErrorHistorial] = useState<string | null>(null);
  useEffect(() => {
    const controller = new AbortController();
    const cargar = () => apiFetch<{ total: number; items: Resultado[] }>(`/mediciones/calculados/${id}/resultados`, {
      signal: controller.signal, params: { pagina, estado: estado || undefined },
    }).then(res => { if (!controller.signal.aborted) { setData(res); setError(null); } })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof ApiError ? err.message : "No se pudieron cargar los resultados."); });
    cargar(); const timer = setInterval(cargar, 5000);
    return () => { controller.abort(); clearInterval(timer); };
  }, [id, pagina, estado, revision]);
  return <section aria-label="Resultados calculados" className="space-y-3 text-sm">
    <h4 className="font-semibold">Resultados y trazabilidad</h4>
    <label className="block">Estado del cálculo<select value={estado} onChange={e => { setEstado(e.target.value); setPagina(1); setData(null); }} className="mt-1 w-full rounded-lg border border-gray-400 bg-white p-2 dark:bg-gray-900">
      <option value="">Todos</option>{["Calculado", "Pendiente de datos", "Incompleto", "Fallido"].map(e => <option key={e}>{e}</option>)}
    </select></label>
    {error ? <div role="alert"><p>{error}</p><button type="button" className="underline" onClick={() => setRevision(v => v + 1)}>Reintentar resultados</button></div> : !data ? <p role="status">Cargando resultados…</p> : <>
      {data.items.length === 0 && <p>No hay resultados para esta selección. Si el histórico está pendiente, espera a que avance el procesamiento.</p>}
      {data.items.map(r => <article key={r.id} className="space-y-2 rounded-xl border border-black/15 p-3 dark:border-white/20">
        <p className="font-semibold">{r.ubicacion} · {formatearFechaHoraEnZona(r.fecha, zonaHoraria)}</p>
        <p>{r.estado}: {r.valor === null ? "Sin valor" : `${r.valor} ${r.unidad}`}</p>
        {r.causa && <p>{r.causa}</p>}
        <details><summary className="cursor-pointer">Ver fuentes y reglas utilizadas</summary><div className="mt-2 space-y-2">
          <p>Tolerancia: {r.trazabilidad.configuracion.tolerancia_segundos} s · Espera: {r.trazabilidad.configuracion.espera_horas} h</p>
          {Object.entries(r.trazabilidad.origenes).map(([v, o]) => <p key={v}>{o.nombre || (o.tipo === "calculado" ? "Parámetro calculado" : "Parámetro de origen")}: {o.valor ?? "Sin valor"} {o.unidad} · {formatearFechaHoraEnZona(o.fecha, zonaHoraria)}{o.estado ? ` · ${o.estado}` : ""}</p>)}
        </div></details>
        {r.revision > 1 && <><button type="button" className="underline" onClick={async () => {
          setErrorHistorial(null);
          try { const res = await apiFetch<{ total: number; items: Revision[] }>(`/mediciones/calculados/resultados/${r.id}/revisiones`); setHistoriales(actual => ({ ...actual, [r.id]: res })); }
          catch { setErrorHistorial("No se pudo cargar el historial de revisiones."); }
        }}>Ver revisiones anteriores ({r.revision - 1})</button>
          {historiales[r.id]?.items.map(h => <p key={h.revision}>Revisión {h.revision}: {h.estado} · {h.valor ?? "Sin valor"} {h.causa || ""}</p>)}
          {historiales[r.id]?.total > 20 && <p>Se muestran las 20 revisiones anteriores más recientes.</p>}
        </>}
      </article>)}
      <nav aria-label="Páginas de resultados" className="flex items-center justify-between gap-2">
        <button type="button" disabled={pagina <= 1} className="disabled:opacity-40" onClick={() => { setData(null); setPagina(v => v - 1); }}>Anterior</button>
        <span>Página {pagina} · {data.total} resultados</span>
        <button type="button" disabled={pagina * 20 >= data.total} className="disabled:opacity-40" onClick={() => { setData(null); setPagina(v => v + 1); }}>Siguiente</button>
      </nav>
    </>}
    {errorHistorial && <p role="alert">{errorHistorial}</p>}
  </section>;
}
