import { useEffect, useRef, useState } from "react";
import type { FormEvent } from "react";
import { Link, useSearchParams } from "react-router-dom";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import { useAuth } from "../hooks/useAuth";
import { apiFetch } from "../services/api";

interface Evento {
  id_evento: number;
  id_archv: number;
  archivo: string;
  datalogger: string;
  proyecto: string | null;
  fecha: string;
  recepcion: string;
  inicio: string | null;
  fin: string | null;
  resultado: string;
  mensaje: string | null;
  registros_procesados: number | null;
  registros_rechazados: number | null;
  origen: string;
}
interface Listado { items: Evento[]; total: number; pagina: number; por_pagina: number }
interface Datalogger { id_cnxn: number; id_dspstv: number | null; nombre: string }
interface Filtros { nombre: string; resultado: string; datalogger: string; inicio: string; fin: string }
const VACIOS: Filtros = { nombre: "", resultado: "", datalogger: "", inicio: "", fin: "" };
const CAMPO = "w-full rounded-lg border border-black/20 bg-white p-2 text-gray-900 dark:border-white/20 dark:bg-gray-900 dark:text-white";
const BOTON = "rounded-lg border border-black/20 px-3 py-2 text-sm font-semibold disabled:opacity-40 dark:border-white/20";

export default function LogIngesta() {
  const { clienteId, proyectoId, zonaHoraria } = useAuth();
  // Un cambio de entorno elimina de inmediato los datos del contexto anterior.
  return <ContenidoLog key={`${clienteId}:${proyectoId}:${zonaHoraria}`} />;
}

function ContenidoLog() {
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();
  const [params, setParams] = useSearchParams();
  const leer = (): Filtros => ({
    nombre: params.get("nombre") ?? "", resultado: params.get("resultado") ?? "",
    datalogger: params.get("datalogger") ?? "", inicio: params.get("fecha_inicio") ?? "",
    fin: params.get("fecha_fin") ?? "",
  });
  const [borrador, setBorrador] = useState<Filtros>(leer);
  const [errorFiltro, setErrorFiltro] = useState<string | null>(null);
  const [datos, setDatos] = useState<Listado | null>(null);
  const [equipos, setEquipos] = useState<Datalogger[]>([]);
  const [errorEquipos, setErrorEquipos] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cargando, setCargando] = useState(true);
  const [revision, setRevision] = useState(0);
  const [detalle, setDetalle] = useState<(Evento & { historial: Evento[] }) | null>(null);
  const [errorDetalle, setErrorDetalle] = useState<string | null>(null);
  const [cargandoDetalle, setCargandoDetalle] = useState(false);
  const [seleccion, setSeleccion] = useState<number | null>(null);
  const [revisionDetalle, setRevisionDetalle] = useState(0);
  const cerrarRef = useRef<HTMLButtonElement>(null);
  const dialogoRef = useRef<HTMLElement>(null);
  const filtros = leer();
  const pagina = Math.max(1, Number(params.get("pagina")) || 1);
  const consulta = params.toString();
  const fecha = (valor: string | null) => valor ? new Date(valor).toLocaleString("es-PE", { timeZone: zonaHoraria }) : "No disponible";
  const mensaje = (evento: Evento) => evento.mensaje ?? (evento.resultado === "Fallido"
    ? "No se conservó un mensaje de error para este intento."
    : "Procesamiento completado sin errores registrados.");

  useEffect(() => {
    const controller = new AbortController();
    apiFetch<{ items: Datalogger[] }>("/ingesta/log/dataloggers", { signal: controller.signal })
      .then(r => { setEquipos(r.items); setErrorEquipos(null); })
      .catch(e => { if (!controller.signal.aborted) setErrorEquipos(e.message); });
    return () => controller.abort();
  }, [revision]);

  useEffect(() => {
    const controller = new AbortController();
    const activos = new URLSearchParams(consulta);
    const [cnxn, equipo] = (activos.get("datalogger") ?? "").split(":");
    queueMicrotask(() => { if (!controller.signal.aborted) {
      setCargando(true); setError(null); setDatos(null);
      setBorrador({ nombre: activos.get("nombre") ?? "", resultado: activos.get("resultado") ?? "",
        datalogger: activos.get("datalogger") ?? "", inicio: activos.get("fecha_inicio") ?? "", fin: activos.get("fecha_fin") ?? "" });
    } });
    apiFetch<Listado>("/ingesta/log", { signal: controller.signal, params: {
      nombre: activos.get("nombre") || undefined, resultado: activos.get("resultado") || undefined,
      fecha_inicio: activos.get("fecha_inicio") || undefined, fecha_fin: activos.get("fecha_fin") || undefined,
      id_cnxn: cnxn || activos.get("id_cnxn") || undefined,
      id_dspstv: equipo || activos.get("dispositivo_id") || undefined,
      sin_identificar: activos.get("datalogger") && !equipo ? "true" : undefined,
      pagina, zona_horaria: zonaHoraria,
    } }).then(r => {
      if (!controller.signal.aborted) setDatos(r);
    }).catch(e => { if (!controller.signal.aborted) setError(e.message || "No se pudo cargar el log de ingesta."); })
      .finally(() => { if (!controller.signal.aborted) setCargando(false); });
    return () => controller.abort();
  }, [consulta, pagina, zonaHoraria, revision]);

  useEffect(() => {
    if (seleccion === null) return;
    const controller = new AbortController();
    queueMicrotask(() => {
      if (!controller.signal.aborted) { setCargandoDetalle(true); setErrorDetalle(null); setDetalle(null); cerrarRef.current?.focus(); }
    });
    apiFetch<Evento & { historial: Evento[] }>(`/ingesta/log/${seleccion}`, { signal: controller.signal })
      .then(r => { if (!controller.signal.aborted) setDetalle(r); })
      .catch(e => { if (!controller.signal.aborted) setErrorDetalle(e.message); })
      .finally(() => { if (!controller.signal.aborted) setCargandoDetalle(false); });
    const anterior = document.activeElement as HTMLElement | null;
    const escape = (e: KeyboardEvent) => {
      if (e.key === "Escape") setSeleccion(null);
      if (e.key === "Tab") {
        const controles = dialogoRef.current?.querySelectorAll<HTMLElement>("button:not([disabled]), summary, [tabindex='0']");
        if (!controles?.length) return;
        const primero = controles[0], ultimo = controles[controles.length - 1];
        if (e.shiftKey && document.activeElement === primero) { e.preventDefault(); ultimo.focus(); }
        else if (!e.shiftKey && document.activeElement === ultimo) { e.preventDefault(); primero.focus(); }
      }
    };
    document.addEventListener("keydown", escape);
    return () => { controller.abort(); document.removeEventListener("keydown", escape); anterior?.focus(); };
  }, [seleccion, revisionDetalle]);

  function aplicar(e: FormEvent) {
    e.preventDefault();
    if (borrador.inicio && borrador.fin && borrador.inicio > borrador.fin) {
      setErrorFiltro("La fecha inicial no puede ser posterior a la final."); return;
    }
    const siguientes = new URLSearchParams();
    for (const [clave, valor] of Object.entries({ nombre: borrador.nombre.trim(), resultado: borrador.resultado,
      datalogger: borrador.datalogger, fecha_inicio: borrador.inicio, fecha_fin: borrador.fin })) {
      if (valor) siguientes.set(clave, valor);
    }
    if (!borrador.datalogger) {
      for (const clave of ["id_cnxn", "dispositivo_id"]) { const valor = params.get(clave); if (valor) siguientes.set(clave, valor); }
    }
    setErrorFiltro(null); setParams(siguientes);
  }
  function irPagina(valor: number) { const siguientes = new URLSearchParams(params); siguientes.set("pagina", String(valor)); setParams(siguientes); }
  function campo(clave: keyof Filtros, valor: string) { setBorrador(actual => ({ ...actual, [clave]: valor })); }
  const paginas = Math.max(1, Math.ceil((datos?.total ?? 0) / (datos?.por_pagina ?? 20)));
  const estado = (valor: string) => <span className={`rounded-full px-2 py-1 text-xs font-bold ${valor === "Fallido" ? "bg-red-100 text-red-800 dark:bg-red-900/40 dark:text-red-200" : "bg-lime-100 text-lime-900 dark:bg-lime-900/40 dark:text-lime-200"}`}>{valor}</span>;
  const eventoDetalle = (evento: Evento) => <dl className="grid gap-3 text-sm sm:grid-cols-2">
    {Object.entries({ Archivo: evento.archivo, Datalogger: evento.datalogger, Proyecto: evento.proyecto ?? "Sin identificar",
      Origen: evento.origen, Resultado: evento.resultado, "Fecha del intento": fecha(evento.fecha),
      Recepción: fecha(evento.recepcion), Inicio: fecha(evento.inicio), Fin: fecha(evento.fin),
      "Registros procesados": evento.registros_procesados ?? "No disponible",
      "Lecturas rechazadas": evento.registros_rechazados ?? "No disponible",
    }).map(([titulo, valor]) => <div key={titulo}><dt className="text-gray-500 dark:text-gray-400">{titulo}</dt><dd className="break-words font-medium">{valor}</dd></div>)}
    <div className="sm:col-span-2"><dt className="text-gray-500 dark:text-gray-400">Mensaje de detalle</dt><dd className="mt-1 whitespace-pre-wrap break-words">{mensaje(evento)}</dd></div>
  </dl>;

  return <div className="flex h-screen overflow-hidden text-gray-900 dark:text-gray-100">
    <Sidebar onLogout={logout} activo="cola-ingesta" rol={rol} />
    <div className="flex min-w-0 flex-1 flex-col">
      <div className="flex justify-end p-4"><Topbar nombreCompleto={nombreCompleto} rol={rol} /></div>
      <main className="flex-1 overflow-y-auto p-4 md:p-8">
        <Link to="/cola-ingesta" className="text-sm font-semibold underline">Volver a Cola de ingesta</Link>
        <h1 className="mt-4 text-2xl font-extrabold">Log de ingesta</h1>
        <p className="mt-2 text-sm text-gray-600 dark:text-gray-300">Historial de cada intento terminado durante los últimos 90 días. Un reproceso conserva los resultados anteriores.</p>
        <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Fechas del intento y horas en {zonaHoraria}. Los archivos en espera o procesando se consultan en la cola.</p>
        <form onSubmit={aplicar} className="my-5 grid gap-3 rounded-2xl border border-black/10 bg-white/30 p-4 dark:border-white/10 sm:grid-cols-2 lg:grid-cols-5">
          <label className="text-sm">Nombre de archivo<input className={CAMPO} value={borrador.nombre} maxLength={300} onChange={e => campo("nombre", e.target.value)} /></label>
          <label className="text-sm">Resultado<select aria-label="Resultado" className={CAMPO} value={borrador.resultado} onChange={e => campo("resultado", e.target.value)}><option value="">Todos</option><option>Procesado</option><option>Fallido</option></select></label>
          <label className="text-sm">Datalogger<select aria-label="Datalogger" className={CAMPO} value={borrador.datalogger} onChange={e => campo("datalogger", e.target.value)}><option value="">Todos</option>{equipos.map((d, i) => <option key={i} value={`${d.id_cnxn}:${d.id_dspstv ?? ""}`}>{d.nombre}</option>)}</select></label>
          <label className="text-sm">Desde<input type="date" className={CAMPO} value={borrador.inicio} onChange={e => campo("inicio", e.target.value)} /></label>
          <label className="text-sm">Hasta<input type="date" className={CAMPO} value={borrador.fin} onChange={e => campo("fin", e.target.value)} /></label>
          <div className="flex flex-wrap gap-2 sm:col-span-2 lg:col-span-5">
            <button className={`${BOTON} bg-[#ccff00] text-gray-900`} type="submit">APLICAR</button>
            <button className={BOTON} type="button" onClick={() => { setBorrador(VACIOS); setErrorFiltro(null); setParams({}); }}>Limpiar filtros</button>
            <button className={BOTON} type="button" onClick={() => setRevision(n => n + 1)}>Actualizar</button>
          </div>
          {(errorFiltro || errorEquipos) && <p role="alert" className="text-sm text-red-600 dark:text-red-300 sm:col-span-2 lg:col-span-5">{errorFiltro || errorEquipos} {errorEquipos && <button type="button" className="underline" onClick={() => setRevision(n => n + 1)}>Reintentar filtros</button>}</p>}
        </form>
        {(params.has("dispositivo_id") || params.has("id_cnxn")) && <p className="mb-3 text-sm">Consulta limitada al equipo de origen. Usa «Limpiar filtros» para consultar todos.</p>}
        <p className="mb-3 text-sm">Filtros aplicados: {filtros.nombre ? `archivo «${filtros.nombre}»; ` : ""}{filtros.resultado || "todos los resultados"}; {equipos.find(d => `${d.id_cnxn}:${d.id_dspstv ?? ""}` === filtros.datalogger)?.nombre ?? "todos los dataloggers"}; {filtros.inicio || "inicio del historial"} a {filtros.fin || "hoy"}.</p>
        {cargando && <p role="status">Cargando log de ingesta…</p>}
        {error && <div role="alert" className="rounded-xl bg-red-100 p-4 text-red-900">{error} <button className={BOTON} onClick={() => setRevision(n => n + 1)}>Reintentar carga</button></div>}
        {!cargando && datos && <>
          {datos.total === 0 ? <p role="status" className="rounded-xl border border-black/10 p-6 dark:border-white/10">No hay eventos para los filtros seleccionados en los últimos 90 días.</p> : <div className="overflow-x-auto rounded-xl border border-black/10 dark:border-white/10">
            <table className="w-full text-left text-sm"><thead className="bg-black/5 dark:bg-white/5"><tr>{["Fecha del intento", "Archivo", "Datalogger de origen", "Resultado", "Mensaje de detalle", "Acciones"].map(t => <th key={t} className="whitespace-nowrap p-3">{t}</th>)}</tr></thead>
              <tbody>{datos.items.map(e => <tr key={e.id_evento} className="border-t border-black/10 dark:border-white/10"><td className="whitespace-nowrap p-3">{fecha(e.fecha)}</td><td className="p-3">{e.archivo}</td><td className="p-3">{e.datalogger}</td><td className="p-3">{estado(e.resultado)}</td><td className="max-w-xs p-3"><p className="line-clamp-2 break-words">{mensaje(e)}</p></td><td className="p-3"><button className={`${BOTON} whitespace-nowrap`} onClick={() => { setDetalle(null); setErrorDetalle(null); setCargandoDetalle(true); setSeleccion(e.id_evento); }}>Ver detalle</button></td></tr>)}</tbody>
            </table>
          </div>}
          <div className="mt-4 flex flex-wrap items-center justify-between gap-3 text-sm"><span>{datos.total} evento(s) · 20 por página</span><div className="flex items-center gap-2"><button className={BOTON} disabled={pagina <= 1} onClick={() => irPagina(pagina - 1)}>Anterior</button><span>Página {pagina} de {paginas}</span><button className={BOTON} disabled={pagina >= paginas} onClick={() => irPagina(pagina + 1)}>Siguiente</button></div></div>
        </>}
      </main>
    </div>
    {seleccion !== null && <div className="ui-modal-fondo fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4" onClick={() => setSeleccion(null)}>
      <section ref={dialogoRef} role="dialog" aria-modal="true" aria-labelledby="titulo-evento" tabIndex={-1} onClick={e => e.stopPropagation()} className="ui-modal-superficie max-h-[90vh] w-full max-w-3xl overflow-y-auto rounded-2xl bg-white p-5 dark:bg-gray-900">
        <div className="mb-5 flex items-center justify-between gap-2"><h2 id="titulo-evento" className="text-lg font-bold">Detalle del evento de ingesta</h2><button ref={cerrarRef} className={BOTON} onClick={() => setSeleccion(null)}>Cerrar</button></div>
        <p className="mb-4 text-xs">Zona horaria: {zonaHoraria}</p>
        {cargandoDetalle && <p role="status">Cargando detalle…</p>}
        {errorDetalle && <p role="alert">{errorDetalle} <button className={BOTON} onClick={() => setRevisionDetalle(n => n + 1)}>Reintentar detalle</button></p>}
        {detalle && <>{eventoDetalle(detalle)}<h3 className="mb-3 mt-6 font-bold">Historial de intentos del archivo · últimos 90 días</h3><div className="space-y-3">{detalle.historial.map(e => <details key={e.id_evento} className="rounded-xl border border-black/10 p-3 dark:border-white/10" open={e.id_evento === seleccion}><summary className="cursor-pointer text-sm">{fecha(e.fecha)} · {e.origen} · {e.resultado}{e.id_evento === seleccion ? " · Evento seleccionado" : ""}</summary><div className="mt-3">{eventoDetalle(e)}</div></details>)}</div><p className="mt-4 text-xs text-gray-500">Los eventos históricos migrados muestran solo los datos que se conservaron; no se reconstruyen fechas ni cantidades desconocidas.</p></>}
      </section>
    </div>}
  </div>;
}
