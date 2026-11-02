import { useEffect, useState } from "react";
import { apiFetch } from "../services/api";
import { useAuth } from "../hooks/useAuth";

interface FiltrosExportacion {
  fecha_inicio: string;
  fecha_fin: string;
  ubicacion_ids: number[];
  parametro_ids: number[];
  dispositivo_ids?: number[];
  valor_min: string | null;
  valor_max: string | null;
  frecuencia_muestreo: number | null;
}

interface Exportacion {
  id_exprtcn: number;
  frmt: string;
  estd: string;
  fch_slctd: string;
  fch_exprcn: string | null;
  filas: number | null;
  error: string | null;
  notificacion_estado: string;
}

export default function ExportacionesPanel({ filtros, idInicial }: { filtros: FiltrosExportacion; idInicial?: number }) {
  const { clienteId, proyectoId, zonaHoraria } = useAuth();
  const [abierto, setAbierto] = useState(Boolean(idInicial));
  const [formato, setFormato] = useState("csv");
  const [items, setItems] = useState<Exportacion[]>([]);
  const [limites, setLimites] = useState<{ max_dias: number; max_filas: number; vigencia_horas: number } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [mensaje, setMensaje] = useState<string | null>(null);
  const [enviando, setEnviando] = useState(false);
  const [descargando, setDescargando] = useState<number | null>(null);
  const [recarga, setRecarga] = useState(0);
  const [dispositivos, setDispositivos] = useState<{ id_dspstv: number; nmbr: string; proyecto_nombre: string }[]>([]);
  const [dispositivoElegido, setDispositivoElegido] = useState("");
  const [paginaDispositivos, setPaginaDispositivos] = useState(1);
  const [hayMasDispositivos, setHayMasDispositivos] = useState(false);
  const proyectos = filtros.ubicacion_ids.join(",");

  useEffect(() => {
    if (!abierto) return;
    const controller = new AbortController();
    const params = new URLSearchParams({ pagina: String(paginaDispositivos) });
    proyectos.split(",").filter(Boolean).forEach(id => params.append("ubicacion_ids", id));
    apiFetch<{ items: typeof dispositivos; hay_mas: boolean }>(`/exportaciones/dispositivos?${params}`, { signal: controller.signal })
      .then(res => { if (!controller.signal.aborted) { setDispositivos(res.items); setHayMasDispositivos(res.hay_mas); } })
      .catch(err => { if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "No se pudieron cargar los dispositivos."); });
    return () => controller.abort();
  }, [abierto, clienteId, proyectoId, proyectos, paginaDispositivos]);

  useEffect(() => {
    if (!abierto) return;
    const controller = new AbortController();
    let timer: ReturnType<typeof setTimeout> | undefined;
    async function consultar() {
      try {
        const [listado, config] = await Promise.all([
          apiFetch<{ items: Exportacion[] }>("/exportaciones", { signal: controller.signal }),
          apiFetch<NonNullable<typeof limites>>("/exportaciones/limites", { signal: controller.signal }),
        ]);
        if (controller.signal.aborted) return;
        setItems(listado.items);
        setLimites(config);
        if (idInicial && !listado.items.some(item => item.id_exprtcn === idInicial)) {
          const solicitada = await apiFetch<Exportacion>(`/exportaciones/${idInicial}`, { signal: controller.signal });
          if (!controller.signal.aborted) setItems([solicitada, ...listado.items]);
        }
      } catch (err) {
        if (!controller.signal.aborted) setError(err instanceof Error ? err.message : "No se pudieron consultar las exportaciones.");
      } finally {
        if (!controller.signal.aborted) timer = setTimeout(() => { void consultar(); }, 5000);
      }
    }
    void consultar();
    return () => { controller.abort(); if (timer) clearTimeout(timer); };
  }, [abierto, clienteId, proyectoId, idInicial, recarga]);

  async function solicitar() {
    setError(null);
    setMensaje(null);
    const dias = (Date.parse(filtros.fecha_fin) - Date.parse(filtros.fecha_inicio)) / 86400000;
    if (limites && dias > limites.max_dias) {
      setError(`El máximo por exportación es de ${limites.max_dias} días. Aplica un rango menor.`);
      return;
    }
    setEnviando(true);
    try {
      const respuesta = await apiFetch<{ mensaje: string }>("/exportaciones", { method: "POST", body: { ...filtros, formato, dispositivo_ids: dispositivoElegido ? [Number(dispositivoElegido)] : (filtros.dispositivo_ids ?? []) } });
      setMensaje(respuesta.mensaje);
      setRecarga(actual => actual + 1);
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo solicitar la exportación.");
    } finally {
      setEnviando(false);
    }
  }

  async function descargar(id: number) {
    setError(null);
    setDescargando(id);
    try {
      const { url } = await apiFetch<{ url: string }>(`/exportaciones/${id}/descarga`, { method: "POST" });
      const enlace = document.createElement("a");
      enlace.href = url;
      enlace.rel = "noreferrer";
      enlace.click();
    } catch (err) {
      setError(err instanceof Error ? err.message : "No se pudo descargar el archivo.");
    } finally {
      setDescargando(null);
    }
  }

  return <section className="mb-5 rounded-2xl border border-black/10 bg-white/30 p-4 dark:border-white/10 dark:bg-white/[0.02]">
    <button type="button" onClick={() => setAbierto(valor => !valor)} aria-expanded={abierto} className="text-sm font-semibold text-[#5a7000] dark:text-[#ccff00]">
      {abierto ? "Cerrar exportaciones" : "Exportar datos CSV / Excel"}
    </button>
    {abierto && <div className="mt-3 space-y-3">
      <p className="text-sm text-gray-600 dark:text-gray-300">Se exportarán los datos del rango y los filtros aplicados. Puedes seguir trabajando mientras se prepara el archivo.</p>
      {limites && <p className="text-xs text-gray-500 dark:text-gray-400">Máximo {limites.max_dias} días y {limites.max_filas.toLocaleString()} registros. Disponible durante {limites.vigencia_horas} horas desde que esté listo.</p>}
      <div className="flex flex-wrap items-center gap-3">
        <label className="text-sm text-gray-700 dark:text-gray-200">Dispositivo <select aria-label="Dispositivo a exportar" value={dispositivoElegido} onChange={event => setDispositivoElegido(event.target.value)} className="ml-2 max-w-64 rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-white/20 dark:bg-gray-900 dark:text-white"><option value="">Todos los del filtro</option>{dispositivos.map(dispositivo => <option key={dispositivo.id_dspstv} value={dispositivo.id_dspstv}>{dispositivo.nmbr} · {dispositivo.proyecto_nombre}</option>)}</select></label>
        {(paginaDispositivos > 1 || hayMasDispositivos) && <span className="flex items-center gap-2 text-xs text-gray-600 dark:text-gray-300"><button type="button" disabled={paginaDispositivos === 1} onClick={() => { setDispositivoElegido(""); setPaginaDispositivos(pagina => pagina - 1); }} className="disabled:opacity-40">Anterior</button><span>Pág. {paginaDispositivos}</span><button type="button" disabled={!hayMasDispositivos} onClick={() => { setDispositivoElegido(""); setPaginaDispositivos(pagina => pagina + 1); }} className="disabled:opacity-40">Siguiente</button></span>}
        <label className="text-sm text-gray-700 dark:text-gray-200">Formato <select aria-label="Formato de exportación" value={formato} onChange={event => setFormato(event.target.value)} className="ml-2 rounded-lg border border-gray-300 bg-white px-3 py-2 text-gray-900 dark:border-white/20 dark:bg-gray-900 dark:text-white"><option value="csv">CSV</option><option value="xlsx">Excel (.xlsx)</option></select></label>
        <button type="button" disabled={enviando || !limites} onClick={() => { void solicitar(); }} className="rounded-xl bg-[#ccff00] px-4 py-2 text-sm font-bold text-gray-900 disabled:opacity-50">{enviando ? "Solicitando…" : "Solicitar exportación"}</button>
      </div>
      {mensaje && <p role="status" className="text-sm text-green-700 dark:text-green-400">{mensaje}</p>}
      {error && <p role="alert" className="text-sm text-red-600 dark:text-red-400">{error}</p>}
      {items.length === 0 && <p className="text-sm text-gray-500">Todavía no has solicitado exportaciones en este entorno.</p>}
      <ul className="space-y-2">{items.map(item => <li key={item.id_exprtcn} className="flex flex-wrap items-center justify-between gap-2 rounded-xl border border-black/10 p-3 text-sm dark:border-white/10">
        <div className="text-gray-700 dark:text-gray-200">
          <span className="font-semibold">#{item.id_exprtcn} · {item.frmt.toUpperCase()} · {item.estd}</span>
          {item.filas !== null && <span> · {item.filas.toLocaleString()} registros</span>}
          {item.error && <p className="text-red-600 dark:text-red-400">{item.error}</p>}
          {item.estd === "Lista" && item.fch_exprcn && <p className="text-xs text-gray-500">Disponible hasta {new Date(item.fch_exprcn).toLocaleString("es-PE", { timeZone: zonaHoraria })}.</p>}
          {item.estd === "Lista" && item.notificacion_estado === "Fallida" && <p className="text-xs text-amber-700 dark:text-amber-300">No se pudo enviar el correo. Puedes descargar el archivo aquí.</p>}
        </div>
        {item.estd === "Lista" && <button type="button" disabled={descargando !== null} onClick={() => { void descargar(item.id_exprtcn); }} className="rounded-lg bg-[#ccff00] px-3 py-2 font-semibold text-gray-900 disabled:opacity-50">{descargando === item.id_exprtcn ? "Preparando…" : "Descargar"}</button>}
      </li>)}</ul>
    </div>}
  </section>;
}
