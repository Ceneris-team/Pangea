import { useEffect, useState } from "react";
import DashboardLayout from "../components/layout/DashboardLayout";
import { apiFetch, abrirEntorno } from "../services/api";

type Cliente = {
  id_clnt: number; nombre: string; plan_nombre: string | null;
  proyectos_total: number; consumo: { ubicaciones: number; dispositivos: number; usuarios: number };
};

export default function Clientes() {
  const [clientes, setClientes] = useState<Cliente[]>([]);
  const [busqueda, setBusqueda] = useState("");
  const [cargando, setCargando] = useState(true);
  const [error, setError] = useState("");
  useEffect(() => {
    let vigente = true;
    apiFetch<Cliente[]>("/empresas").then((data) => { if (vigente) setClientes(data); })
      .catch(() => { if (vigente) setError("No se pudieron cargar los clientes"); })
      .finally(() => { if (vigente) setCargando(false); });
    return () => { vigente = false; };
  }, []);
  const visibles = clientes.filter((c) => c.nombre.toLocaleLowerCase("es").includes(busqueda.trim().toLocaleLowerCase("es")));
  return <DashboardLayout activo="clientes">
    <div className="mx-auto max-w-6xl space-y-6">
      <header><p className="text-xs font-semibold uppercase tracking-widest text-lime-700 dark:text-lime-300">CENERIS · Acceso operativo</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">Entorno de clientes</h1>
        <p className="mt-2 max-w-3xl text-gray-600 dark:text-gray-300">Selecciona una empresa para entrar a sus proyectos. El menú mostrará sus módulos de datos, gráficos, equipos e ingesta.</p>
      </header>
      <input type="search" aria-label="Buscar cliente" placeholder="Buscar empresa..." value={busqueda} onChange={(e) => setBusqueda(e.target.value)} className="w-full max-w-lg rounded-xl border border-black/15 bg-white px-4 py-3 text-gray-950 dark:border-white/20 dark:bg-[#262d39] dark:text-white" />
      {error && <p role="alert" className="text-red-600 dark:text-red-400">{error}</p>}
      {cargando ? <p className="text-gray-500 dark:text-gray-400">Cargando clientes...</p> : <div className="grid gap-5 md:grid-cols-2 xl:grid-cols-3">
        {visibles.map((c) => <article key={c.id_clnt} className="flex flex-col rounded-2xl border border-black/10 bg-white/70 p-6 dark:border-white/10 dark:bg-[#1a202c]/90">
          <h2 className="text-xl font-semibold text-gray-950 dark:text-white">{c.nombre}</h2>
          <p className="mt-2 text-sm text-gray-500 dark:text-gray-400">{c.plan_nombre ?? "Sin plan asignado"}</p>
          <dl className="my-5 grid grid-cols-3 gap-2 text-center">
            {[["Proyectos", c.consumo.ubicaciones], ["Dispositivos", c.consumo.dispositivos], ["Usuarios", c.consumo.usuarios]].map(([label, n]) => <div key={label}><dt className="text-[11px] text-gray-500 dark:text-gray-400">{label}</dt><dd className="mt-1 text-2xl font-bold text-gray-950 dark:text-white">{n}</dd></div>)}
          </dl>
          {!c.consumo.dispositivos && <p className="mb-4 text-xs text-gray-500 dark:text-gray-400">Este cliente aún no tiene dispositivos activos.</p>}
          <button type="button" onClick={() => abrirEntorno(c.id_clnt)} className="mt-auto rounded-xl bg-[#ccff00] px-4 py-2.5 text-sm font-semibold text-gray-950">Entrar al entorno de {c.nombre}</button>
        </article>)}
        {visibles.length === 0 && <p className="text-gray-500 dark:text-gray-400">No se encontraron clientes.</p>}
      </div>}
    </div>
  </DashboardLayout>;
}
