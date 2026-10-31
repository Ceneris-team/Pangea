import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Link, useLocation, useNavigate, useParams } from "react-router-dom";
import { apiFetch, ApiError } from "../services/api";
import { useAuth } from "../hooks/useAuth";
import { useMapaEnVivo } from "../hooks/useMapaEnVivo";
import { ROLES } from "../config/roles";
import type { SerieTelemetria } from "./seriesTelemetria";
import Sidebar from "../components/layout/Sidebar";
import Topbar from "../components/layout/Topbar";
import DrawerPanel from "../components/layout/DrawerPanel";
import ConfirmarEliminacionModal from "../components/ConfirmarEliminacionModal";
import WidgetTelemetria, { type WidgetConfigurado } from "../components/WidgetTelemetria";
import PanelResumenOperativo from "../components/PanelResumenOperativo";
import { reordenarWidgets } from "./ordenWidgets";
import { estadoLectura, type ContenidoPanel as ContenidoPanelBase, type EstadoLectura, type PanelDetalle, type UbicacionDisponible, type UbicacionPanel } from "./panelesTypes";

type ContenidoPanel = ContenidoPanelBase<WidgetConfigurado>;
interface FormWidget { tp: WidgetConfigurado["tp"]; id_ubccn: string; id_prmtr: string; ancho: 1 | 2 }

const INPUT = "w-full rounded-xl border border-black/10 bg-black/5 p-2.5 text-sm text-gray-900 outline-none focus:border-[#ccff00] dark:border-white/20 dark:bg-white/5 dark:text-white";
const ACCION = "rounded-lg border border-black/20 px-3 py-1.5 text-sm text-gray-700 hover:bg-black/5 dark:border-white/20 dark:text-gray-200 dark:hover:bg-white/10 disabled:opacity-40";
const PRINCIPAL = "rounded-lg bg-[#ccff00] px-3 py-1.5 text-sm font-bold text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50";

export default function DetallePanel() {
  const { id } = useParams<{ id: string }>();
  const { nombreCompleto, rol, logout, zonaHoraria } = useAuth();
  const location = useLocation();
  const navigate = useNavigate();
  const [mensaje, setMensaje] = useState<string | null>((location.state as { mensaje?: string } | null)?.mensaje ?? null);
  const [errorAccion, setErrorAccion] = useState<string | null>(null);
  const [panel, setPanel] = useState<PanelDetalle | null>(null);
  const puedeGestionar = panel?.es_propietario === true && (rol === ROLES.CLIENTE_FINAL || rol === ROLES.USUARIO_EMPRESA);
  const [contenido, setContenido] = useState<ContenidoPanel | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [dias, setDias] = useState<0 | 1 | 7 | 30>(7);
  const [fechaDesde, setFechaDesde] = useState("");
  const [fechaHasta, setFechaHasta] = useState("");
  const [rangoPersonalizado, setRangoPersonalizado] = useState<{ inicio: string; fin: string } | null>(null);
  const [filtroUbicacion, setFiltroUbicacion] = useState<number | null>(null);
  const [filtroDispositivo, setFiltroDispositivo] = useState<number | null>(null);
  const [filtroParametro, setFiltroParametro] = useState<number | null>(null);
  const [filtroEstado, setFiltroEstado] = useState<EstadoLectura | null>(null);
  const [umbralHoras, setUmbralHoras] = useState(24);
  const [autoActualizar, setAutoActualizar] = useState(true);
  const [modoPresentacion, setModoPresentacion] = useState(false);
  const [ahora, setAhora] = useState(() => Date.now());
  const [revision, setRevision] = useState(0);
  const [destelloEn, setDestelloEn] = useState<number | null>(null);
  const [destelloSecuencia, setDestelloSecuencia] = useState(0);
  const [drawerUbicaciones, setDrawerUbicaciones] = useState(false);
  const [disponibles, setDisponibles] = useState<UbicacionDisponible[] | null>(null);
  const [idsUbicaciones, setIdsUbicaciones] = useState<number[]>([]);
  const [drawerWidget, setDrawerWidget] = useState(false);
  const [widgetEnEdicion, setWidgetEnEdicion] = useState<WidgetConfigurado | null>(null);
  const [form, setForm] = useState<FormWidget>({ tp: "linea", id_ubccn: "", id_prmtr: "", ancho: 1 });
  const [catalogo, setCatalogo] = useState<{ ubicacion: number; items: SerieTelemetria[] } | null>(null);
  const [confirmarWidget, setConfirmarWidget] = useState<WidgetConfigurado | null>(null);
  const [confirmarUbicacion, setConfirmarUbicacion] = useState<UbicacionPanel | null>(null);
  const [guardando, setGuardando] = useState(false);
  const arrastrando = useRef<number | null>(null);
  const refrescoEnVivo = useRef<number | null>(null);
  const solicitudContenido = useRef(0);

  const cargarContenido = useCallback(async (dispositivoId: number | null = filtroDispositivo) => {
    if (!id) return;
    const solicitud = ++solicitudContenido.current;
    const datos = await apiFetch<ContenidoPanel>(`/paneles/${id}/contenido`, { params: { dispositivo_id: dispositivoId ?? undefined } });
    if (solicitud === solicitudContenido.current) setContenido(datos);
  }, [id, filtroDispositivo]);

  const { estado: estadoEnVivo } = useMapaEnVivo((evento) => {
    if (!contenido?.ubicaciones.some((ubicacion) => ubicacion.id_ubccn === evento.id_ubccn)) return;
    setDestelloEn(evento.id_ubccn);
    setDestelloSecuencia((valor) => valor + 1);
    if (refrescoEnVivo.current !== null) window.clearTimeout(refrescoEnVivo.current);
    refrescoEnVivo.current = window.setTimeout(() => {
      refrescoEnVivo.current = null;
      void cargarContenido().then(() => setRevision((valor) => valor + 1)).catch(() => {});
    }, 1_000);
  });

  useEffect(() => () => {
    if (refrescoEnVivo.current !== null) window.clearTimeout(refrescoEnVivo.current);
  }, []);

  useEffect(() => {
    if (!autoActualizar) return;
    const temporizador = window.setInterval(() => {
      void cargarContenido().then(() => setRevision((valor) => valor + 1)).catch(() => {});
    }, 60_000);
    return () => window.clearInterval(temporizador);
  }, [autoActualizar, cargarContenido]);

  useEffect(() => {
    const temporizador = window.setInterval(() => setAhora(Date.now()), 60_000);
    return () => window.clearInterval(temporizador);
  }, []);

  useEffect(() => {
    const alSalirDePantallaCompleta = () => {
      if (!document.fullscreenElement) setModoPresentacion(false);
    };
    document.addEventListener("fullscreenchange", alSalirDePantallaCompleta);
    return () => document.removeEventListener("fullscreenchange", alSalirDePantallaCompleta);
  }, []);

  useEffect(() => {
    if ((location.state as { mensaje?: string } | null)?.mensaje) navigate(location.pathname, { replace: true, state: null });
  }, [location.pathname, location.state, navigate]);

  useEffect(() => {
    let cancelado = false;
    Promise.all([apiFetch<PanelDetalle>(`/paneles/${id}`), apiFetch<ContenidoPanel>(`/paneles/${id}/contenido`)])
      .then(([detalle, datos]) => { if (!cancelado) { setPanel(detalle); setContenido(datos); } })
      .catch((err) => { if (!cancelado) setError(err instanceof ApiError ? err.message : "No se pudo cargar el panel"); })
      .finally(() => { if (!cancelado) setLoading(false); });
    return () => { cancelado = true; };
  }, [id]);

  useEffect(() => {
    if (!drawerWidget || !form.id_ubccn) return;
    const ubicacion = Number(form.id_ubccn);
    let cancelado = false;
    apiFetch<{ items: SerieTelemetria[] }>(`/mediciones/series?ubicacion_id=${ubicacion}`)
      .then((res) => { if (!cancelado) setCatalogo({ ubicacion, items: res.items }); })
      .catch((err) => { if (!cancelado) { setCatalogo({ ubicacion, items: [] }); setErrorAccion(err instanceof ApiError ? err.message : "No se pudieron cargar los parámetros"); } });
    return () => { cancelado = true; };
  }, [drawerWidget, form.id_ubccn]);

  const parametros = useMemo(() => {
    if (catalogo?.ubicacion !== Number(form.id_ubccn)) return [];
    const unicos = new Map<number, SerieTelemetria>();
    for (const serie of catalogo.items) unicos.set(serie.id_prmtr, serie);
    return [...unicos.values()].sort((a, b) => a.parametro_nombre.localeCompare(b.parametro_nombre));
  }, [catalogo, form.id_ubccn]);

  function fallo(err: unknown, alternativo: string) { setErrorAccion(err instanceof ApiError ? err.message : alternativo); }

  function abrirUbicaciones() {
    setErrorAccion(null); setIdsUbicaciones([]); setDisponibles(null); setDrawerUbicaciones(true);
    apiFetch<{ items: UbicacionDisponible[] }>(`/paneles/${id}/ubicaciones/disponibles`)
      .then((res) => setDisponibles(res.items)).catch((err) => fallo(err, "No se pudieron cargar las ubicaciones"));
  }

  async function agregarUbicacion() {
    if (idsUbicaciones.length === 0 || guardando) return;
    setGuardando(true); setErrorAccion(null);
    try {
      const res = await apiFetch<{ mensaje: string }>(`/paneles/${id}/ubicaciones/lote`, { method: "POST", body: { ids: idsUbicaciones } });
      await cargarContenido(); setMensaje(res.mensaje); setDrawerUbicaciones(false);
    } catch (err) { fallo(err, "No se pudo añadir la ubicación"); }
    finally { setGuardando(false); }
  }

  function abrirWidget(widget: WidgetConfigurado | null = null) {
    setErrorAccion(null); setWidgetEnEdicion(widget);
    setForm(widget
      ? { tp: widget.tp, id_ubccn: String(widget.id_ubccn), id_prmtr: String(widget.id_prmtr), ancho: widget.ancho }
      : { tp: "linea", id_ubccn: String(contenido?.ubicaciones[0]?.id_ubccn ?? ""), id_prmtr: "", ancho: 1 });
    setDrawerWidget(true);
  }

  async function guardarWidget() {
    if (!form.id_ubccn || !form.id_prmtr || guardando) return;
    setGuardando(true); setErrorAccion(null);
    try {
      const res = await apiFetch<{ mensaje: string }>(widgetEnEdicion ? `/paneles/${id}/widgets/${widgetEnEdicion.id_wdgt}` : `/paneles/${id}/widgets`, {
        method: widgetEnEdicion ? "PUT" : "POST",
        body: { tp: form.tp, id_ubccn: Number(form.id_ubccn), id_prmtr: Number(form.id_prmtr), ancho: form.ancho },
      });
      await cargarContenido(); setMensaje(res.mensaje); setDrawerWidget(false);
    } catch (err) { fallo(err, "No se pudo guardar el widget"); }
    finally { setGuardando(false); }
  }

  async function eliminarWidget() {
    if (!confirmarWidget || guardando) return;
    setGuardando(true); setErrorAccion(null);
    try {
      const res = await apiFetch<{ mensaje: string }>(`/paneles/${id}/widgets/${confirmarWidget.id_wdgt}`, { method: "DELETE" });
      await cargarContenido(); setMensaje(res.mensaje); setConfirmarWidget(null);
    } catch (err) { fallo(err, "No se pudo eliminar el widget"); }
    finally { setGuardando(false); }
  }

  async function cambiarAncho(widget: WidgetConfigurado) {
    if (guardando) return;
    setGuardando(true); setErrorAccion(null);
    try {
      await apiFetch(`/paneles/${id}/widgets/${widget.id_wdgt}`, {
        method: "PUT",
        body: { tp: widget.tp, id_ubccn: widget.id_ubccn, id_prmtr: widget.id_prmtr, ancho: widget.ancho === 1 ? 2 : 1 },
      });
      await cargarContenido();
    } catch (err) { fallo(err, "No se pudo cambiar el tamaño del widget"); }
    finally { setGuardando(false); }
  }

  async function quitarUbicacion() {
    if (!confirmarUbicacion || guardando) return;
    setGuardando(true); setErrorAccion(null);
    try {
      const res = await apiFetch<{ mensaje: string }>(`/paneles/${id}/ubicaciones/${confirmarUbicacion.id_ubccn}`, { method: "DELETE" });
      await cargarContenido(); setMensaje(res.mensaje); setFiltroUbicacion((actual) => actual === confirmarUbicacion.id_ubccn ? null : actual); setConfirmarUbicacion(null);
    } catch (err) { fallo(err, "No se pudo quitar la ubicación"); }
    finally { setGuardando(false); }
  }

  async function moverWidget(destino: number) {
    const origen = arrastrando.current;
    arrastrando.current = null;
    if (!contenido || origen === null || origen === destino || guardando) return;
    const anterior = contenido.widgets;
    const orden = reordenarWidgets(anterior, origen, destino);
    if (orden === anterior) return;
    setContenido({ ...contenido, widgets: orden }); setGuardando(true);
    try { await apiFetch(`/paneles/${id}/widgets/orden`, { method: "PUT", body: { ids: orden.map((w) => w.id_wdgt) } }); }
    catch (err) { setContenido({ ...contenido, widgets: anterior }); fallo(err, "No se pudo guardar el orden"); }
    finally { setGuardando(false); }
  }

  function moverConBoton(idWidget: number, desplazamiento: number) {
    if (!contenido) return;
    const indice = contenido.widgets.findIndex((w) => w.id_wdgt === idWidget);
    const destino = contenido.widgets[indice + desplazamiento];
    if (destino) { arrastrando.current = idWidget; void moverWidget(destino.id_wdgt); }
  }

  const nombres = new Map(contenido?.ubicaciones.map((u) => [u.id_ubccn, u.nmbr]) ?? []);
  const paraAgregar = disponibles?.filter((u) => !contenido?.ubicaciones.some((a) => a.id_ubccn === u.id_ubccn));
  const parametrosPanel = useMemo(() => {
    const opciones = new Map<number, string>();
    for (const ubicacion of contenido?.ubicaciones ?? []) for (const valor of ubicacion.ultimos_valores) opciones.set(valor.id_prmtr, valor.parametro);
    for (const widget of contenido?.widgets ?? []) opciones.set(widget.id_prmtr, widget.parametro_nombre);
    return [...opciones].sort((a, b) => a[1].localeCompare(b[1]));
  }, [contenido]);
  const ubicacionDelDispositivo = contenido?.dispositivos.find((d) => d.id_dspstv === filtroDispositivo)?.id_ubccn;
  const ubicacionesOperativas = contenido?.ubicaciones.filter((u) => filtroDispositivo === null || u.id_ubccn === ubicacionDelDispositivo) ?? [];
  const widgetsVisibles = contenido?.widgets.filter((widget) => (filtroUbicacion === null || widget.id_ubccn === filtroUbicacion)
    && (filtroDispositivo === null || widget.id_ubccn === ubicacionDelDispositivo)
    && (filtroParametro === null || widget.id_prmtr === filtroParametro)
    && (filtroEstado === null || estadoLectura(contenido.ubicaciones.find((u) => u.id_ubccn === widget.id_ubccn)?.ultima_lectura ?? null, umbralHoras, ahora) === filtroEstado)) ?? [];

  function aplicarRango() {
    const inicio = new Date(fechaDesde);
    const fin = new Date(fechaHasta);
    if (!Number.isFinite(inicio.getTime()) || !Number.isFinite(fin.getTime()) || inicio >= fin) {
      setErrorAccion("Selecciona un inicio anterior al fin para el período personalizado.");
      return;
    }
    setErrorAccion(null);
    setRangoPersonalizado({ inicio: inicio.toISOString(), fin: fin.toISOString() });
  }

  async function seleccionarDispositivo(dispositivoId: number | null) {
    const anterior = filtroDispositivo;
    const ubicacionAnterior = filtroUbicacion;
    setFiltroDispositivo(dispositivoId);
    const dispositivo = contenido?.dispositivos.find((d) => d.id_dspstv === dispositivoId);
    setFiltroUbicacion(dispositivo?.id_ubccn ?? null);
    try { await cargarContenido(dispositivoId); }
    catch (err) { setFiltroDispositivo(anterior); setFiltroUbicacion(ubicacionAnterior); fallo(err, "No se pudo filtrar por dispositivo"); }
  }

  async function alternarPresentacion() {
    if (!modoPresentacion) await document.documentElement.requestFullscreen?.().catch(() => {});
    else if (document.fullscreenElement) await document.exitFullscreen().catch(() => {});
    setModoPresentacion((actual) => !actual);
  }

  function exportarLecturas() {
    if (!panel || !contenido) return;
    const filas = [["Estación", "Parámetro", "Valor", "Unidad", "Fecha y hora", "Dispositivo"]];
    for (const ubicacion of ubicacionesOperativas) {
      if (filtroUbicacion !== null && ubicacion.id_ubccn !== filtroUbicacion) continue;
      if (filtroEstado !== null && estadoLectura(ubicacion.ultima_lectura, umbralHoras, ahora) !== filtroEstado) continue;
      for (const valor of ubicacion.ultimos_valores) {
        if (filtroParametro !== null && valor.id_prmtr !== filtroParametro) continue;
        filas.push([ubicacion.nmbr, valor.parametro, String(valor.valor), valor.unidad, valor.fch_hr ?? "", valor.dispositivo_nombre]);
      }
    }
    const csv = "\uFEFF" + filas.map((fila) => fila.map((celda) => `"${celda.replaceAll('"', '""')}"`).join(",")).join("\r\n");
    const enlace = document.createElement("a");
    enlace.href = URL.createObjectURL(new Blob([csv], { type: "text/csv;charset=utf-8" }));
    enlace.download = `${panel.nmbr.replace(/[^\p{L}\p{N}-]+/gu, "_")}_lecturas.csv`;
    enlace.click();
    URL.revokeObjectURL(enlace.href);
  }

  return <div className="font-sans">
    <div className="flex h-screen overflow-hidden bg-transparent transition-colors duration-300 print:h-auto print:overflow-visible">
      {!modoPresentacion && <div className="print:hidden"><Sidebar onLogout={logout} activo="paneles" rol={rol} /></div>}
      <div className="flex flex-1 flex-col overflow-hidden print:overflow-visible">
        {!modoPresentacion && <div className="franja-superior flex justify-end p-4 pb-0 md:p-6 print:hidden"><Topbar nombreCompleto={nombreCompleto} rol={rol} /></div>}
        <main className="flex-1 overflow-y-auto p-6 md:p-8 print:overflow-visible print:p-0">
          {!modoPresentacion && <Link to="/paneles" className="mb-6 inline-block text-sm text-gray-600 hover:underline dark:text-gray-300 print:hidden">← Volver a Tableros Personalizables</Link>}
          {mensaje && <div role="status" className="mb-4 flex justify-between rounded-xl border border-[#ccff00]/40 bg-[#ccff00]/20 p-4 text-sm text-[#5a7000] dark:text-[#ccff00]"><span>{mensaje}</span><button type="button" onClick={() => setMensaje(null)} className="underline">Cerrar</button></div>}
          {errorAccion && !drawerWidget && !drawerUbicaciones && !confirmarWidget && !confirmarUbicacion && <p role="alert" className="mb-4 rounded-xl bg-red-50 p-4 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">{errorAccion}</p>}
          {loading && <p className="py-16 text-center text-gray-600 dark:text-gray-300">Cargando panel...</p>}
          {!loading && error && <p role="alert" className="rounded-xl bg-red-50 p-4 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">{error}</p>}
          {!loading && panel && contenido && <>
            <header className="mb-6 flex flex-wrap items-start justify-between gap-4">
              <div><h1 className="text-2xl font-bold text-gray-900 dark:text-white">{panel.nmbr}</h1><p className="mt-1 text-sm text-gray-600 dark:text-gray-300">{panel.es_propietario ? "Tu panel de telemetría" : "Panel compartido de la empresa"} · {estadoEnVivo === "conectado" ? "Datos en vivo" : "Actualización periódica"}</p><p className="mt-1 text-xs font-semibold text-[#648000] dark:text-[#ccff00]">{contenido.proyecto_activo ? `Proyecto activo: ${contenido.proyecto_activo.nmbr} · datos y gráficos de este proyecto` : "Vista general · datos de los proyectos añadidos al panel"}</p></div>
              <div className="flex flex-wrap gap-2">
                <button type="button" onClick={() => void alternarPresentacion()} className={`${ACCION} print:hidden`}>{modoPresentacion ? "Salir de presentación" : "Presentar"}</button>
                {!modoPresentacion && <button type="button" onClick={() => window.print()} className={`${ACCION} print:hidden`}>Imprimir / PDF</button>}
                {!modoPresentacion && <button type="button" onClick={exportarLecturas} className={`${ACCION} print:hidden`}>Exportar últimas lecturas CSV</button>}
                {puedeGestionar && !modoPresentacion && contenido.ubicaciones.length > 0 && <button type="button" onClick={abrirUbicaciones} className={ACCION}>+ Añadir ubicaciones</button>}
                {puedeGestionar && !modoPresentacion && contenido.ubicaciones.length > 0 && <button type="button" onClick={() => abrirWidget()} className={PRINCIPAL}>+ Añadir widget</button>}
              </div>
            </header>
            {contenido.ubicaciones.length > 0 && <>
              <div className="mb-4 flex flex-wrap items-end gap-3 rounded-2xl border border-black/10 bg-white/40 p-4 dark:border-white/10 dark:bg-white/[0.04] print:hidden">
                <label className="min-w-40 flex-1 text-xs font-medium text-gray-600 dark:text-gray-300">Proyecto / estación<select value={filtroUbicacion ?? ""} onChange={(e) => setFiltroUbicacion(e.target.value ? Number(e.target.value) : null)} className={`mt-1 ${INPUT}`}><option value="">Todas</option>{contenido.ubicaciones.map((u) => <option key={u.id_ubccn} value={u.id_ubccn}>{u.nmbr}</option>)}</select></label>
                <label className="min-w-40 flex-1 text-xs font-medium text-gray-600 dark:text-gray-300">Dispositivo<select value={filtroDispositivo ?? ""} onChange={(e) => void seleccionarDispositivo(e.target.value ? Number(e.target.value) : null)} className={`mt-1 ${INPUT}`}><option value="">Todos</option>{contenido.dispositivos.map((d) => <option key={d.id_dspstv} value={d.id_dspstv}>{d.nmbr}</option>)}</select></label>
                <label className="min-w-40 flex-1 text-xs font-medium text-gray-600 dark:text-gray-300">Parámetro<select value={filtroParametro ?? ""} onChange={(e) => setFiltroParametro(e.target.value ? Number(e.target.value) : null)} className={`mt-1 ${INPUT}`}><option value="">Todos</option>{parametrosPanel.map(([idParametro, nombre]) => <option key={idParametro} value={idParametro}>{nombre}</option>)}</select></label>
                <label className="min-w-32 text-xs font-medium text-gray-600 dark:text-gray-300">Lectura reciente en<select value={umbralHoras} onChange={(e) => setUmbralHoras(Number(e.target.value))} className={`mt-1 ${INPUT}`}><option value={6}>6 horas</option><option value={24}>24 horas</option><option value={72}>72 horas</option></select></label>
                {(filtroUbicacion !== null || filtroDispositivo !== null || filtroParametro !== null || filtroEstado !== null) && <button type="button" onClick={() => { setFiltroUbicacion(null); setFiltroParametro(null); setFiltroEstado(null); void seleccionarDispositivo(null); }} className={ACCION}>Limpiar filtros</button>}
              </div>
              <PanelResumenOperativo ubicaciones={ubicacionesOperativas} dispositivos={contenido.dispositivos} seleccionada={filtroUbicacion} parametroId={filtroParametro} umbralHoras={umbralHoras} estadoFiltro={filtroEstado} zonaHoraria={zonaHoraria} puedeGestionar={puedeGestionar && !modoPresentacion} destelloEn={destelloEn} destelloSecuencia={destelloSecuencia} onSeleccionar={setFiltroUbicacion} onFiltrarEstado={setFiltroEstado} onQuitar={(ubicacion) => { setErrorAccion(null); setConfirmarUbicacion(ubicacion); }} />
            </>}
            {contenido.ubicaciones.length === 0 ? <div className="flex flex-col items-center gap-4 rounded-2xl border border-black/10 bg-white/25 px-6 py-20 text-center dark:border-white/10 dark:bg-white/[0.02]"><p className="text-gray-600 dark:text-gray-300">Este panel todavía no tiene ubicaciones configuradas.</p>{puedeGestionar && <button type="button" onClick={abrirUbicaciones} className={PRINCIPAL}>+ Añadir ubicaciones</button>}</div> : <>
              <div className="mb-4 flex flex-wrap items-end justify-between gap-3"><h2 className="text-lg font-semibold text-gray-900 dark:text-white">Widgets <span className="text-sm font-normal text-gray-500">({widgetsVisibles.length})</span></h2><div className="flex flex-wrap items-end gap-2 text-sm text-gray-600 dark:text-gray-300"><label htmlFor="rango-panel">Período<select id="rango-panel" value={dias} onChange={(e) => setDias(Number(e.target.value) as 0 | 1 | 7 | 30)} className={`mt-1 ${INPUT}`}><option value={1}>Últimas 24 horas</option><option value={7}>Últimos 7 días</option><option value={30}>Últimos 30 días</option><option value={0}>Personalizado</option></select></label><button type="button" onClick={() => { setRevision((v) => v + 1); void cargarContenido().catch((err) => fallo(err, "No se pudieron actualizar las ubicaciones")); }} className={ACCION}>Actualizar</button><label className="flex items-center gap-2 pb-2 text-xs"><input type="checkbox" checked={autoActualizar} onChange={(e) => setAutoActualizar(e.target.checked)} />Cada 60 s</label></div></div>
              {dias === 0 && <div className="mb-4 flex flex-wrap items-end gap-2"><label className="text-xs text-gray-600 dark:text-gray-300">Desde<input type="datetime-local" value={fechaDesde} onChange={(e) => setFechaDesde(e.target.value)} className={`mt-1 ${INPUT}`} /></label><label className="text-xs text-gray-600 dark:text-gray-300">Hasta<input type="datetime-local" value={fechaHasta} onChange={(e) => setFechaHasta(e.target.value)} className={`mt-1 ${INPUT}`} /></label><button type="button" onClick={aplicarRango} className={PRINCIPAL}>Aplicar período</button></div>}
              {dias === 0 && !rangoPersonalizado ? <p className="rounded-xl border border-dashed border-black/20 p-5 text-sm text-gray-600 dark:border-white/20 dark:text-gray-300">Selecciona las fechas y aplica el período.</p> : contenido.widgets.length === 0 ? <div className="rounded-2xl border border-dashed border-black/20 px-6 py-12 text-center text-sm text-gray-600 dark:border-white/20 dark:text-gray-300">Aún no hay widgets. Añade uno para visualizar la telemetría de estas ubicaciones.</div> : widgetsVisibles.length === 0 ? <p className="rounded-xl border border-dashed border-black/20 p-6 text-center text-sm text-gray-500 dark:border-white/20">No hay widgets para estos filtros.</p> : <div className="grid gap-4 lg:grid-cols-2">
                {widgetsVisibles.map((widget) => { const indice = contenido.widgets.findIndex((w) => w.id_wdgt === widget.id_wdgt); return <article key={widget.id_wdgt} draggable={puedeGestionar && !modoPresentacion && !guardando} onDragStart={(e) => { arrastrando.current = widget.id_wdgt; e.dataTransfer.effectAllowed = "move"; }} onDragOver={(e) => { if (puedeGestionar && !modoPresentacion) e.preventDefault(); }} onDrop={(e) => { e.preventDefault(); void moverWidget(widget.id_wdgt); }} className={`rounded-2xl border border-black/10 bg-white/40 p-5 shadow-sm dark:border-white/10 dark:bg-white/[0.03] ${widget.ancho === 2 ? "lg:col-span-2" : ""}`}>
                  {puedeGestionar && !modoPresentacion && <div className="mb-3 flex flex-wrap items-center justify-end gap-2 print:hidden"><span className="mr-auto text-xs text-gray-500 dark:text-gray-400" title="Arrastra para cambiar el orden">⠿ Arrastrar</span><button type="button" disabled={indice === 0 || guardando} onClick={() => moverConBoton(widget.id_wdgt, -1)} aria-label="Mover widget hacia arriba" className={ACCION}>↑</button><button type="button" disabled={indice === contenido.widgets.length - 1 || guardando} onClick={() => moverConBoton(widget.id_wdgt, 1)} aria-label="Mover widget hacia abajo" className={ACCION}>↓</button><button type="button" disabled={guardando} onClick={() => void cambiarAncho(widget)} className={ACCION}>{widget.ancho === 1 ? "Ampliar" : "Reducir"}</button><button type="button" onClick={() => abrirWidget(widget)} className={ACCION}>Editar</button><button type="button" onClick={() => { setErrorAccion(null); setConfirmarWidget(widget); }} className="rounded-lg border border-red-300 px-3 py-1.5 text-sm text-red-600 dark:border-red-800 dark:text-red-400">Eliminar</button></div>}
                  <WidgetTelemetria key={`${widget.id_wdgt}-${widget.tp}-${widget.id_prmtr}-${widget.id_ubccn}-${dias}-${revision}`} widget={widget} ubicacionNombre={nombres.get(widget.id_ubccn) ?? "Ubicación"} ultimoValor={contenido.ubicaciones.find((u) => u.id_ubccn === widget.id_ubccn)?.ultimos_valores.find((valor) => valor.id_prmtr === widget.id_prmtr)} dias={dias || 7} fechaInicio={dias === 0 ? rangoPersonalizado?.inicio : undefined} fechaFin={dias === 0 ? rangoPersonalizado?.fin : undefined} idDispositivo={filtroDispositivo} revision={revision} zonaHoraria={zonaHoraria} />
                </article>; })}
              </div>}
            </>}
          </>}
        </main>
      </div>
    </div>

    <DrawerPanel abierto={drawerUbicaciones} onCerrar={() => { if (!guardando) setDrawerUbicaciones(false); }} titulo="Añadir ubicaciones">
      <div className="flex h-full flex-col gap-4">
        <p className="text-sm text-gray-600 dark:text-gray-300">Selecciona una o más ubicaciones asignadas a tu cuenta.</p>
        {errorAccion && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">{errorAccion}</p>}
        {!disponibles && !errorAccion && <p className="text-sm text-gray-500">Cargando ubicaciones...</p>}
        {paraAgregar?.length === 0 && <p className="text-sm text-gray-500">No hay más ubicaciones disponibles.</p>}
        {paraAgregar && paraAgregar.length > 0 && <div className="flex-1 space-y-2 overflow-y-auto">
          {paraAgregar.map((u) => <label key={u.id_ubccn} className="flex cursor-pointer items-center gap-3 rounded-xl border border-black/10 p-3 text-sm text-gray-800 hover:bg-black/5 dark:border-white/20 dark:text-gray-200 dark:hover:bg-white/5">
            <input type="checkbox" checked={idsUbicaciones.includes(u.id_ubccn)} onChange={(e) => setIdsUbicaciones((actual) => e.target.checked ? [...actual, u.id_ubccn] : actual.filter((idActual) => idActual !== u.id_ubccn))} className="h-4 w-4 accent-[#8fb300]" />
            {u.nmbr}
          </label>)}
        </div>}
        <div className="mt-auto flex gap-3 pt-6">
          <button type="button" disabled={guardando} onClick={() => setDrawerUbicaciones(false)} className={ACCION}>Cancelar</button>
          <button type="button" disabled={idsUbicaciones.length === 0 || guardando} onClick={() => void agregarUbicacion()} className={PRINCIPAL}>{guardando ? "Guardando..." : `Agregar al panel (${idsUbicaciones.length})`}</button>
        </div>
      </div>
    </DrawerPanel>

    <DrawerPanel abierto={drawerWidget} onCerrar={() => { if (!guardando) setDrawerWidget(false); }} titulo={widgetEnEdicion ? "Editar widget" : "Añadir widget"}><div className="flex h-full flex-col gap-5">{errorAccion && <p role="alert" className="rounded-lg bg-red-50 p-3 text-sm text-red-600 dark:bg-red-900/20 dark:text-red-400">{errorAccion}</p>}<label className="text-sm font-medium text-gray-700 dark:text-gray-200">Tipo de widget<select value={form.tp} onChange={(e) => setForm((v) => ({ ...v, tp: e.target.value as FormWidget["tp"] }))} className={`mt-1 ${INPUT}`}><option value="linea">Gráfico de línea</option><option value="area">Gráfico de área</option><option value="tarjeta">Tarjeta de valor actual</option><option value="tabla">Tabla de lecturas</option></select></label><label className="text-sm font-medium text-gray-700 dark:text-gray-200">Ubicación<select value={form.id_ubccn} onChange={(e) => setForm((v) => ({ ...v, id_ubccn: e.target.value, id_prmtr: "" }))} className={`mt-1 ${INPUT}`}>{contenido?.ubicaciones.map((u) => <option key={u.id_ubccn} value={u.id_ubccn}>{u.nmbr}</option>)}</select></label><label className="text-sm font-medium text-gray-700 dark:text-gray-200">Parámetro<select value={form.id_prmtr} onChange={(e) => setForm((v) => ({ ...v, id_prmtr: e.target.value }))} className={`mt-1 ${INPUT}`}><option value="">Selecciona un parámetro</option>{parametros.map((serie) => <option key={serie.id_prmtr} value={serie.id_prmtr}>{serie.parametro_nombre} ({serie.undd})</option>)}</select></label>{form.id_ubccn && catalogo?.ubicacion !== Number(form.id_ubccn) && <p className="text-sm text-gray-500">Cargando parámetros...</p>}{catalogo?.ubicacion === Number(form.id_ubccn) && parametros.length === 0 && <p className="text-sm text-gray-500">Esta ubicación aún no tiene parámetros numéricos mapeados.</p>}<div className="mt-auto flex gap-3 pt-6"><button type="button" disabled={guardando} onClick={() => setDrawerWidget(false)} className={ACCION}>Cancelar</button><button type="button" disabled={!form.id_prmtr || guardando} onClick={() => void guardarWidget()} className={PRINCIPAL}>{guardando ? "Guardando..." : "Guardar widget"}</button></div></div></DrawerPanel>

    {confirmarWidget && <ConfirmarEliminacionModal titulo="Eliminar widget" mensaje="Se retirará este widget del panel. Los datos de telemetría y la ubicación permanecerán disponibles." error={errorAccion} confirmando={guardando} onConfirmar={() => void eliminarWidget()} onCancelar={() => { setConfirmarWidget(null); setErrorAccion(null); }} textoAccion="Confirmar" />}
    {confirmarUbicacion && <ConfirmarEliminacionModal titulo={`Quitar ${confirmarUbicacion.nmbr}`} mensaje="Se retirará esta ubicación del panel y se eliminarán sus widgets. Los datos de telemetría permanecerán disponibles." error={errorAccion} confirmando={guardando} onConfirmar={() => void quitarUbicacion()} onCancelar={() => { setConfirmarUbicacion(null); setErrorAccion(null); }} textoAccion="Confirmar" />}
  </div>;
}
