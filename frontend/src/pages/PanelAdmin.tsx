import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import DashboardLayout from "../components/layout/DashboardLayout";
import { apiFetch } from "../services/api";

type Empresa = { id_clnt: number; proyectos_total: number; consumo: { usuarios: number; dispositivos: number; ubicaciones: number } };
const secciones = [
  { ruta: "/usuarios", numero: "01", titulo: "Gestión de usuarios", descripcion: "Consulta las cuentas del sistema y administra el equipo CENERIS." },
  { ruta: "/empresas", numero: "02", titulo: "Empresas y proyectos", descripcion: "Registra clientes, organiza sus proyectos y gestiona sus administradores y usuarios." },
  { ruta: "/planes-suscripciones", numero: "03", titulo: "Planes y suscripciones", descripcion: "Define límites y precios, asigna planes y consulta las suscripciones de cada empresa." },
  { ruta: "/clientes", numero: "04", titulo: "Entorno de clientes", descripcion: "Entra a una empresa para trabajar con sus datos, gráficos, dispositivos y conexiones." },
];

export default function PanelAdmin() {
  const [empresas, setEmpresas] = useState<Empresa[] | null>(null);
  const [error, setError] = useState("");
  useEffect(() => {
    let vigente = true;
    apiFetch<Empresa[]>("/empresas").then((data) => { if (vigente) setEmpresas(data); })
      .catch(() => { if (vigente) setError("No se pudo cargar el resumen de empresas"); });
    return () => { vigente = false; };
  }, []);
  const resumen = [
    ["Empresas activas", empresas?.length],
    ["Proyectos activos", empresas?.reduce((n, e) => n + e.consumo.ubicaciones, 0)],
    ["Dispositivos activos", empresas?.reduce((n, e) => n + e.consumo.dispositivos, 0)],
    ["Usuarios de clientes activos", empresas?.reduce((n, e) => n + e.consumo.usuarios, 0)],
  ] as const;
  return <DashboardLayout activo="panel">
    <div className="mx-auto max-w-6xl space-y-7">
      <header><p className="text-xs font-semibold uppercase tracking-widest text-lime-700 dark:text-lime-300">CENERIS · Vista global</p>
        <h1 className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">Administración de Pangea</h1>
        <p className="mt-2 max-w-3xl text-gray-600 dark:text-gray-300">Gestiona la plataforma y entra al entorno de cada cliente cuando necesites trabajar con sus proyectos.</p>
      </header>
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">{resumen.map(([label, valor]) => <div key={label} className="rounded-2xl border border-black/10 bg-white/70 p-5 dark:border-white/10 dark:bg-[#1a202c]/90"><p className="text-xs text-gray-500 dark:text-gray-400">{label}</p><p className="mt-2 text-3xl font-bold text-gray-950 dark:text-white">{valor ?? "—"}</p></div>)}</div>
      <div className="grid gap-5 md:grid-cols-2">{secciones.map((s) => <Link key={s.ruta} to={s.ruta} className="group rounded-2xl border border-black/10 bg-white/70 p-6 transition hover:border-lime-500 dark:border-white/10 dark:bg-[#1a202c]/90 dark:hover:border-lime-400">
        <div className="flex items-start justify-between"><span className="rounded-lg bg-lime-500/15 px-3 py-1.5 text-sm font-semibold text-lime-800 dark:text-lime-300">{s.numero}</span><span aria-hidden="true" className="text-xl text-gray-500 group-hover:text-lime-600 dark:text-gray-400">↗</span></div>
        <h2 className="mt-5 text-xl font-semibold text-gray-950 dark:text-white">{s.titulo}</h2><p className="mt-2 text-sm leading-6 text-gray-600 dark:text-gray-300">{s.descripcion}</p>
      </Link>)}</div>
    </div>
  </DashboardLayout>;
}
