import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import MapaEstacionesCliente, { type EstacionParaMapa } from "./MapaEstacionesCliente";
import { estadoLectura, resumenLecturas, type DispositivoPanel, type EstadoLectura, type UbicacionPanel } from "../pages/panelesTypes";

interface Props {
  ubicaciones: UbicacionPanel[];
  dispositivos: DispositivoPanel[];
  seleccionada: number | null;
  parametroId: number | null;
  umbralHoras: number;
  estadoFiltro: EstadoLectura | null;
  zonaHoraria: string;
  puedeGestionar: boolean;
  destelloEn?: number | null;
  destelloSecuencia?: number;
  onSeleccionar: (id: number | null) => void;
  onFiltrarEstado: (estado: EstadoLectura | null) => void;
  onQuitar: (ubicacion: UbicacionPanel) => void;
}

const ETIQUETA_ESTADO: Record<EstadoLectura, string> = {
  reciente: "Lectura reciente",
  atrasada: "Sin lectura reciente",
  sin_datos: "Sin lecturas",
};
const COLOR_ESTADO: Record<EstadoLectura, string> = {
  reciente: "bg-emerald-500/15 text-emerald-700 dark:text-emerald-300",
  atrasada: "bg-amber-500/15 text-amber-700 dark:text-amber-300",
  sin_datos: "bg-slate-500/15 text-slate-700 dark:text-slate-300",
};

export default function PanelResumenOperativo({ ubicaciones, dispositivos, seleccionada, parametroId, umbralHoras, estadoFiltro, zonaHoraria, puedeGestionar, destelloEn, destelloSecuencia, onSeleccionar, onFiltrarEstado, onQuitar }: Props) {
  const [ahora, setAhora] = useState(() => Date.now());
  useEffect(() => {
    const temporizador = window.setInterval(() => setAhora(Date.now()), 60_000);
    return () => window.clearInterval(temporizador);
  }, []);
  const resumen = resumenLecturas(ubicaciones, umbralHoras, ahora);
  const visibles = ubicaciones.filter((u) => (seleccionada === null || u.id_ubccn === seleccionada)
    && (estadoFiltro === null || estadoLectura(u.ultima_lectura, umbralHoras, ahora) === estadoFiltro));
  const estaciones: EstacionParaMapa[] = ubicaciones.map((u) => {
    const estado = estadoLectura(u.ultima_lectura, umbralHoras, ahora);
    return {
      id_ubccn: u.id_ubccn,
      nmbr: u.nmbr,
      dscrpcn: u.dscrpcn,
      lttd: u.lttd,
      lngtd: u.lngtd,
      estd: u.estd,
      semaforo: estado === "reciente" ? u.semaforo : estado === "atrasada" ? "desactualizada" : "sin_datos",
      ultima_lectura: u.ultima_lectura,
      parametros: u.ultimos_valores.map((valor) => ({ parametro: valor.parametro, unidad: valor.unidad, valor: valor.valor, fch_hr: valor.fch_hr })),
    };
  });

  const indicadores: { clave: EstadoLectura | null; titulo: string; valor: number }[] = [
    { clave: null, titulo: "Estaciones", valor: resumen.total },
    { clave: "reciente", titulo: "Con lectura reciente", valor: resumen.reciente },
    { clave: "atrasada", titulo: `Sin lectura en ${umbralHoras} h`, valor: resumen.atrasada },
    { clave: "sin_datos", titulo: "Nunca recibieron datos", valor: resumen.sin_datos },
  ];

  return <section className="mb-7 space-y-4" aria-label="Estado operativo del panel">
    <div className="grid gap-3 sm:grid-cols-2 xl:grid-cols-4">
      {indicadores.map(({ clave, titulo, valor }) => <button key={titulo} type="button" onClick={() => onFiltrarEstado(clave)} aria-pressed={estadoFiltro === clave}
        className={`rounded-2xl border bg-white/50 p-4 text-left transition hover:border-[#a3ca00] dark:bg-white/[0.04] ${estadoFiltro === clave ? "border-[#a3ca00] ring-1 ring-[#a3ca00]" : "border-black/10 dark:border-white/10"}`}>
        <span className="block text-xs text-gray-600 dark:text-gray-300">{titulo}</span>
        <strong className="mt-1 block text-2xl text-gray-900 dark:text-white">{valor}</strong>
      </button>)}
    </div>
    <div className="grid gap-4 xl:grid-cols-[minmax(0,1.2fr)_minmax(0,1fr)]">
      <div className="overflow-hidden rounded-2xl border border-black/10 bg-white/40 dark:border-white/10 dark:bg-white/[0.04]">
        <div className="flex items-center justify-between px-4 py-3"><h2 className="font-semibold text-gray-900 dark:text-white">Mapa de estaciones</h2><span className="text-xs text-gray-500 dark:text-gray-400">Selecciona un marcador para filtrar</span></div>
        <div className="h-[340px] border-t border-black/10 dark:border-white/10"><MapaEstacionesCliente estaciones={estaciones} onSeleccionarEstacion={onSeleccionar} destelloEn={destelloEn} destelloSecuencia={destelloSecuencia} /></div>
        <p className="px-4 py-2 text-xs text-gray-500 dark:text-gray-400">El color de las lecturas recientes usa umbrales de referencia; la antigüedad se evalúa por separado.</p>
      </div>
      <div className="min-w-0 rounded-2xl border border-black/10 bg-white/40 p-4 dark:border-white/10 dark:bg-white/[0.04]">
        <div className="mb-3 flex items-center justify-between gap-2"><h2 className="font-semibold text-gray-900 dark:text-white">Estaciones del panel</h2><span className="text-xs text-gray-500 dark:text-gray-400">{visibles.length} de {ubicaciones.length}</span></div>
        <div className="max-h-[390px] space-y-3 overflow-y-auto pr-1">
          {visibles.length === 0 && <p className="py-8 text-center text-sm text-gray-500">No hay estaciones para estos filtros.</p>}
          {visibles.map((u) => {
            const estado = estadoLectura(u.ultima_lectura, umbralHoras, ahora);
            const valores = u.ultimos_valores.filter((valor) => parametroId === null || valor.id_prmtr === parametroId);
            const fuentes = dispositivos.filter((d) => d.id_ubccn === u.id_ubccn);
            return <article key={u.id_ubccn} className={`rounded-xl border p-3 ${seleccionada === u.id_ubccn ? "border-[#a3ca00] bg-[#ccff00]/10" : "border-black/10 bg-white/40 dark:border-white/10 dark:bg-white/[0.03]"}`}>
              <div className="flex items-start justify-between gap-2"><button type="button" onClick={() => onSeleccionar(seleccionada === u.id_ubccn ? null : u.id_ubccn)} className="text-left font-semibold text-gray-900 hover:underline dark:text-white">{u.nmbr}</button><span className={`rounded-full px-2 py-1 text-[11px] font-semibold ${COLOR_ESTADO[estado]}`}>{ETIQUETA_ESTADO[estado]}</span></div>
              <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{u.ultima_lectura ? `Última lectura: ${new Date(u.ultima_lectura).toLocaleString("es-PE", { timeZone: zonaHoraria })}` : "Sin datos registrados"}</p>
              {valores.length > 0 && <dl className="mt-2 grid grid-cols-2 gap-2">{valores.slice(0, 6).map((valor) => <div key={valor.id_prmtr} className="rounded-lg bg-black/[0.04] px-2 py-1.5 dark:bg-white/[0.05]"><dt className="truncate text-[11px] text-gray-500 dark:text-gray-400">{valor.parametro}</dt><dd className="truncate text-sm font-semibold text-gray-900 dark:text-white">{typeof valor.valor === "number" ? valor.valor.toLocaleString("es-PE", { maximumFractionDigits: 3 }) : valor.valor} {valor.unidad}</dd></div>)}</dl>}
              {estado !== "reciente" && fuentes.length > 0 && <div className="mt-3 rounded-lg bg-amber-500/10 p-2 text-xs text-gray-700 dark:text-gray-300"><p className="font-semibold">Revisar origen de datos</p>{fuentes.map((fuente) => <p key={fuente.id_dspstv} className="mt-1"><Link to={`/dispositivos/${fuente.id_dspstv}`} className="underline">{fuente.nmbr}</Link>: {fuente.ultima_ingesta ? `último archivo ${fuente.ultima_ingesta.estado.toLowerCase()} (${new Date(fuente.ultima_ingesta.fecha).toLocaleString("es-PE", { timeZone: zonaHoraria })})` : "sin archivos recibidos"}</p>)}</div>}
              <div className="mt-3 flex items-center gap-3 text-xs"><Link to={`/ubicaciones/${u.id_ubccn}`} className="font-semibold text-[#648000] hover:underline dark:text-[#ccff00]">Ver detalle →</Link>{puedeGestionar && <button type="button" onClick={() => onQuitar(u)} className="text-red-600 hover:underline dark:text-red-400">Quitar del panel</button>}</div>
            </article>;
          })}
        </div>
      </div>
    </div>
  </section>;
}
