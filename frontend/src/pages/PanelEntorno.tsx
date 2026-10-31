import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../components/layout/DashboardLayout";
import { useAuth } from "../hooks/useAuth";
import { apiFetch } from "../services/api";

type Estacion = {
  id_ubccn: number; nmbr: string; ultima_lectura: string | null;
  parametros: { parametro: string; unidad: string; valor: number | string }[];
};
type Resumen = {
  empresa: string; proyecto: string | null; ubicaciones: number; dispositivos: number; activos: number;
  estaciones: Estacion[];
};

export default function PanelEntorno() {
  const { clienteId, proyectoId, zonaHoraria } = useAuth();
  const [resumen, setResumen] = useState<Resumen | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!clienteId) return;
    let vigente = true;
    Promise.all([
      apiFetch<{ id_clnt: number; nombre: string }[]>("/empresas"),
      apiFetch<{ id_ubccn: number; nombre: string }[]>(`/empresas/${clienteId}/proyectos`),
      apiFetch<{ id_ubccn: number }[]>("/ubicaciones/mapa"),
      apiFetch<{ estd: string }[]>("/dispositivos/mapa"),
      apiFetch<{ items: Estacion[] }>("/mapa-cliente"),
    ]).then(([empresas, proyectos, ubicaciones, dispositivos, estaciones]) => {
      if (vigente) setResumen({
        empresa: empresas.find((e) => e.id_clnt === clienteId)?.nombre ?? "Mi empresa",
        proyecto: proyectos.find((p) => p.id_ubccn === proyectoId)?.nombre ?? null,
        ubicaciones: ubicaciones.length, dispositivos: dispositivos.length,
        activos: dispositivos.filter((d) => d.estd === "Activo").length,
        estaciones: estaciones.items,
      });
    }).catch(() => { if (vigente) setError("No se pudo cargar el resumen del entorno. Vuelve a intentar."); });
    return () => { vigente = false; };
  }, [clienteId, proyectoId]);
  const indicadores = [
    ["Proyectos", resumen?.ubicaciones], ["Dispositivos", resumen?.dispositivos],
    ["Dispositivos activos", resumen?.activos], ["Proyectos con lecturas", resumen?.estaciones.filter((e) => e.ultima_lectura).length],
  ] as const;
  return <DashboardLayout activo="panel">
    <div className="mx-auto max-w-7xl space-y-6">
      <header><p className="text-xs font-semibold uppercase tracking-widest text-lime-700 dark:text-lime-300">Entorno del cliente</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">{resumen?.empresa ?? "Cargando empresa..."}</h1>
        <p className="mt-2 text-gray-600 dark:text-gray-300">{resumen?.proyecto ?? "Todos los proyectos"} · Datos y equipos del entorno seleccionado.</p>
      </header>
      {error && <p role="alert" className="rounded-xl bg-red-500/10 p-4 text-red-700 dark:text-red-300">{error}</p>}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{indicadores.map(([label, valor]) => <div key={label} className="rounded-2xl border border-black/10 bg-white/70 p-5 dark:border-white/10 dark:bg-[#1a202c]/90"><p className="text-xs text-gray-500 dark:text-gray-400">{label}</p><p className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">{valor ?? "—"}</p></div>)}</div>
      <section className="overflow-hidden rounded-2xl border border-black/10 bg-white/70 dark:border-white/10 dark:bg-[#1a202c]/90">
        <div className="border-b border-black/10 p-5 dark:border-white/10"><h2 className="text-lg font-semibold text-gray-950 dark:text-white">Últimas lecturas por proyecto</h2><p className="mt-1 text-sm text-gray-500 dark:text-gray-400">Abre la serie de un proyecto para consultar su historial o ver sus gráficos.</p></div>
        {!resumen ? <p className="p-5 text-gray-500 dark:text-gray-400">Cargando lecturas...</p> : resumen.estaciones.length === 0 ? <p className="p-5 text-gray-500 dark:text-gray-400">No hay proyectos disponibles en este entorno.</p> : <div className="overflow-x-auto"><table className="w-full text-left text-sm">
          <thead className="bg-black/5 text-xs uppercase text-gray-500 dark:bg-white/5 dark:text-gray-400"><tr><th className="p-4">Proyecto</th><th className="p-4">Últimos valores</th><th className="p-4">Última lectura</th><th className="p-4">Consultar</th></tr></thead>
          <tbody>{resumen.estaciones.map((e) => <tr key={e.id_ubccn} className="border-t border-black/10 text-gray-700 dark:border-white/10 dark:text-gray-200">
            <td className="p-4 font-semibold">{e.nmbr}</td>
            <td className="p-4">{e.parametros.length ? <div className="flex flex-wrap gap-2">{e.parametros.slice(0, 3).map((p) => <span key={p.parametro} className="rounded-lg bg-black/5 px-2 py-1 dark:bg-white/5">{p.parametro}: <strong>{p.valor} {p.unidad}</strong></span>)}{e.parametros.length > 3 && <span>+{e.parametros.length - 3} parámetros</span>}</div> : <span className="text-gray-500 dark:text-gray-400">Sin mediciones registradas</span>}</td>
            <td className="whitespace-nowrap p-4">{e.ultima_lectura ? new Date(e.ultima_lectura).toLocaleString("es-PE", { timeZone: zonaHoraria }) : "—"}</td>
            <td className="p-4"><div className="flex gap-3"><Link className="font-semibold text-lime-800 underline dark:text-lime-300" to={`/graficos?ubicacion_id=${e.id_ubccn}`}>Gráficos</Link><Link className="font-semibold text-lime-800 underline dark:text-lime-300" to={`/consulta-datos?ubicacion_id=${e.id_ubccn}`}>Datos</Link></div></td>
          </tr>)}</tbody>
        </table></div>}
      </section>
    </div>
  </DashboardLayout>;
}
