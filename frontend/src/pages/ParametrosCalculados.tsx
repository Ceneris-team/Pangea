import { useEffect, useState } from "react";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import { useAuth } from "../hooks/useAuth";
import { apiFetch, ApiError } from "../services/api";
import { CrearParametroCalculado, DetalleParametroCalculado, type DefinicionCalculada } from "../components/ParametroCalculadoPanel";

interface Listado {
  total: number;
  pagina: number;
  por_pagina: number;
  contexto: { empresa: string | null; proyecto: string | null };
  permisos: { crear: boolean };
  items: DefinicionCalculada[];
}

interface Filtros { busqueda: string; estado: string; pagina: number }
const VACIOS: Filtros = { busqueda: "", estado: "", pagina: 1 };
const campo = "w-full rounded-xl border border-black/15 bg-white/50 px-3 py-2.5 text-sm text-gray-900 outline-none focus:ring-2 focus:ring-[#8fb300] dark:border-white/20 dark:bg-gray-900 dark:text-white";

export default function ParametrosCalculados() {
  const { nombreCompleto, rol, logout } = useAuth();
  const [busqueda, setBusqueda] = useState("");
  const [filtros, setFiltros] = useState<Filtros>(VACIOS);
  const [revision, setRevision] = useState(0);
  const [data, setData] = useState<Listado | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [seleccionado, setSeleccionado] = useState<number | null>(null);
  const [creando, setCreando] = useState(false);
  const [aviso, setAviso] = useState<string | null>(null);

  useEffect(() => {
    const timer = setTimeout(() => {
      const valor = busqueda.trim();
      setFiltros(actual => actual.busqueda === valor ? actual : { ...actual, busqueda: valor, pagina: 1 });
    }, 300);
    return () => clearTimeout(timer);
  }, [busqueda]);

  useEffect(() => {
    const controller = new AbortController();
    queueMicrotask(() => {
      if (controller.signal.aborted) return;
      setLoading(true);
      setError(null);
      setData(null);
    });
    apiFetch<Listado>("/parametros-calculados", { signal: controller.signal, params: {
      q: filtros.busqueda || undefined, estado: filtros.estado || undefined,
      pagina: filtros.pagina, por_pagina: 10,
    } }).then(res => { if (!controller.signal.aborted) setData(res); })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof ApiError ? err.message : "No se pudo cargar el listado de parámetros calculados."); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [filtros, revision]);

  function limpiar() {
    setBusqueda("");
    setFiltros(VACIOS);
  }
  const hayFiltros = busqueda !== "" || filtros.busqueda !== "" || filtros.estado !== "";
  const pendiente = loading || busqueda.trim() !== filtros.busqueda;
  const totalPaginas = data ? Math.max(1, Math.ceil(data.total / data.por_pagina)) : 1;
  const inicio = data?.total ? (data.pagina - 1) * data.por_pagina + 1 : 0;
  const fin = data ? Math.min(data.pagina * data.por_pagina, data.total) : 0;

  return <div className="flex h-screen overflow-hidden bg-transparent font-sans">
    <Sidebar onLogout={logout} activo="parametros-calculados" rol={rol} />
    <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
      <div className="flex justify-end p-4 pb-0 md:p-6 md:pb-0"><Topbar nombreCompleto={nombreCompleto} rol={rol} /></div>
      <main className="flex-1 overflow-y-auto p-6 md:p-8">
        <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
          <div><h1 className="text-2xl font-bold text-gray-900 dark:text-white">Parámetros calculados</h1>
          <p className="mt-1 text-sm text-gray-600 dark:text-gray-300">Consulta las variables derivadas, sus fórmulas y parámetros de origen.</p></div>
          {data?.permisos.crear && <button type="button" onClick={() => { setAviso(null); setCreando(true); }} className="rounded-xl bg-[#ccff00] px-4 py-2.5 text-sm font-semibold text-gray-950">Añadir parámetro calculado</button>}
        </header>
        {aviso && <p role="status" className="mb-4 rounded-xl bg-lime-100 p-3 text-sm text-gray-900">{aviso}</p>}
        {data && <p className="mb-4 text-sm text-gray-700 dark:text-gray-200" aria-label="Contexto del listado">Empresa: {data.contexto.empresa ?? "Todas las empresas autorizadas"}{data.contexto.proyecto ? ` · Proyecto: ${data.contexto.proyecto}` : ""}</p>}
        <section aria-label="Listado de parámetros calculados" className="overflow-hidden rounded-2xl border border-black/10 bg-white/25 dark:border-white/10 dark:bg-white/[0.02]">
          <div className="flex flex-col gap-3 border-b border-black/10 p-5 dark:border-white/10 sm:flex-row sm:items-end">
            <label className="min-w-0 flex-1 text-sm text-gray-700 dark:text-gray-200">Buscar por nombre
              <input type="search" maxLength={100} value={busqueda} onChange={e => setBusqueda(e.target.value)} className={`${campo} mt-1`} placeholder="Nombre o fragmento del parámetro…" />
            </label>
            <label className="text-sm text-gray-700 dark:text-gray-200 sm:w-52">Estado
              <select value={filtros.estado} onChange={e => setFiltros(actual => ({ ...actual, estado: e.target.value, pagina: 1 }))} className={`${campo} mt-1`}>
                <option value="">Todos los estados</option><option value="Activo">Activo</option><option value="Inactivo">Inactivo</option>
              </select>
            </label>
            <button type="button" onClick={limpiar} disabled={!hayFiltros} className="rounded-xl border border-gray-400 px-4 py-2.5 text-sm text-gray-700 disabled:opacity-40 dark:text-gray-200">Limpiar filtros</button>
          </div>
          {loading && <p role="status" className="p-6 text-sm text-gray-600 dark:text-gray-300">Cargando parámetros calculados…</p>}
          {error && <div role="alert" className="p-5 text-sm text-red-700 dark:text-red-300"><p>{error}</p><button type="button" onClick={() => setRevision(v => v + 1)} className="mt-2 underline">Reintentar listado</button></div>}
          {!loading && data && <>
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm text-gray-700 dark:text-gray-200">
                <thead className="bg-black/5 text-xs uppercase dark:bg-white/5"><tr>
                  {["Nombre", "Fórmula", "Unidad", "Estado", "Ámbito", "Acciones"].map(t => <th key={t} className="px-5 py-4 font-semibold">{t}</th>)}
                </tr></thead>
                <tbody>{data.items.map(p => <tr key={p.id_prm_clc} className="border-t border-black/10 dark:border-white/10">
                  <td className="min-w-44 px-5 py-4 font-semibold text-gray-900 dark:text-white">{p.nmbr}</td>
                  <td className="min-w-44 px-5 py-4"><span className="block max-w-64 truncate font-mono" title={p.frml}>{p.frml}</span></td>
                  <td className="px-5 py-4">{p.undd || "—"}</td>
                  <td className="px-5 py-4"><span className={`inline-block rounded-full px-2.5 py-1 text-xs font-semibold ${p.estd === "Activo" ? "bg-[#ccff00]/20 text-[#526600] dark:text-[#ccff00]" : "bg-black/5 text-gray-600 dark:bg-white/10 dark:text-gray-300"}`}>{p.estd}</span></td>
                  <td className="min-w-44 px-5 py-4"><p>{p.empresa_nombre}</p><p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{p.ambito}</p></td>
                  <td className="px-5 py-4"><button type="button" onClick={() => setSeleccionado(p.id_prm_clc)} aria-label={`Ver detalle de ${p.nmbr}`} className="whitespace-nowrap rounded-lg border border-gray-400 px-3 py-1.5">Ver detalle</button></td>
                </tr>)}</tbody>
              </table>
            </div>
            {data.total === 0 && <p role="status" className="p-6 text-center text-sm text-gray-600 dark:text-gray-300">{filtros.busqueda || filtros.estado ? "No se encontraron parámetros calculados con esos filtros." : "Aún no hay parámetros calculados configurados en este contexto."}</p>}
            <div className="flex flex-wrap items-center justify-between gap-3 border-t border-black/10 p-5 text-sm text-gray-600 dark:border-white/10 dark:text-gray-300">
              <p>Mostrando {inicio} a {fin} de {data.total} registros</p>
              <nav aria-label="Páginas del listado" className="flex flex-wrap items-center gap-2">
                <button type="button" disabled={pendiente || filtros.pagina <= 1} onClick={() => setFiltros(actual => ({ ...actual, pagina: actual.pagina - 1 }))} className="rounded-lg border border-gray-400 px-3 py-1.5 disabled:opacity-40">Anterior</button>
                <span>Página {data.pagina} de {totalPaginas}</span>
                <button type="button" disabled={pendiente || filtros.pagina >= totalPaginas} onClick={() => setFiltros(actual => ({ ...actual, pagina: actual.pagina + 1 }))} className="rounded-lg border border-gray-400 px-3 py-1.5 disabled:opacity-40">Siguiente</button>
              </nav>
            </div>
          </>}
        </section>
      </main>
    </div>
    {seleccionado !== null && <DetalleParametroCalculado key={seleccionado} id={seleccionado} onCerrar={() => setSeleccionado(null)} />}
    {creando && <CrearParametroCalculado onCerrar={() => setCreando(false)} onCreado={() => { setCreando(false); setAviso("Definición registrada. Se conservan los filtros actuales del listado."); setFiltros(actual => ({ ...actual, pagina: 1 })); setRevision(v => v + 1); }} />}
  </div>;
}
