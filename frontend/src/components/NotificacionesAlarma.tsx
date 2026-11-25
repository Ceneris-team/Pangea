import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../services/api";
import { MENSAJE_GUARDADO, ayudaCanalCorreo, estadoCanal, type CanalNotificacion } from "./configNotificaciones";

/**
 * HU30 (PP-75 / PP-231) "Configurar notificaciones" de una alarma:
 *   CA1  canales disponibles y destinatarios actuales
 *   CA2  activar el canal de correo y GUARDAR -> "Notificaciones configuradas correctamente"
 *   CA4  desactivar el canal y GUARDAR -> deja de notificar
 * Más los destinatarios (HT-14) y el historial de envíos (PP-424).
 */
import { useAuth } from "../hooks/useAuth";
import { formatearFechaHoraEnZona } from "../utils/fechas";

interface Destinatario { id: number; correo: string }
interface ConfigNotificaciones {
  canal_email_activo: boolean;
  canales: CanalNotificacion[];
  destinatarios: Destinatario[];
  correo_cuenta: string;
}
interface Intento { numero: number; fecha: string; resultado: string; error: string | null }
interface Envio {
  id: number; destinatario: string; tipo: string; estado: string; creada: string;
  enviada: string | null; proximo_intento: string | null; ultimo_error: string | null;
  mensaje_id: string | null; intentos: Intento[];
}
interface Historial { total: number; items: Envio[] }
interface Props {
  alarma: { id_alrm: number; nmbr: string; estd: string; correos_habilitados?: boolean };
  onClose: () => void;
  onUpdate: () => void;
  puedeEditar: boolean;
}

const campo = "rounded-lg border border-black/20 dark:border-white/20 bg-white dark:bg-gray-900 px-3 py-2 text-sm min-w-0";
const boton = "rounded-lg border border-black/20 dark:border-white/20 px-3 py-2 text-sm disabled:opacity-40";

export default function NotificacionesAlarma({ alarma, onClose, onUpdate, puedeEditar }: Props) {
  const { zonaHoraria } = useAuth();
  const fecha = (valor: string) => formatearFechaHoraEnZona(valor, zonaHoraria);
  const dialogo = useRef<HTMLDialogElement>(null);
  const [destinatarios, setDestinatarios] = useState<Destinatario[]>([]);
  const [historial, setHistorial] = useState<Historial>({ total: 0, items: [] });
  const [correo, setCorreo] = useState("");
  const [estado, setEstado] = useState("");
  const [pagina, setPagina] = useState(1);
  const [version, setVersion] = useState(0);
  const [error, setError] = useState("");
  const [cargando, setCargando] = useState(true);
  const [ocupado, setOcupado] = useState(false);
  // CA1/CA2/CA4: configuración del canal. `canalElegido` es lo que el
  // usuario marcó y todavía no guardó (null = sin cambios).
  const [config, setConfig] = useState<ConfigNotificaciones | null>(null);
  const [canalElegido, setCanalElegido] = useState<boolean | null>(null);
  const [mensaje, setMensaje] = useState("");

  useEffect(() => {
    dialogo.current?.showModal();
  }, []);

  // La configuración no entra en el refresco de 10 s del historial: así no
  // se pisa lo que el usuario está marcando.
  useEffect(() => {
    let cancelado = false;
    apiFetch<ConfigNotificaciones>(`/alarmas/${alarma.id_alrm}/notificaciones`)
      .then((c) => { if (!cancelado) setConfig(c); })
      .catch((err) => {
        if (!cancelado) setError(err instanceof ApiError ? err.message : "No se pudo cargar la configuración");
      });
    return () => { cancelado = true; };
  }, [alarma.id_alrm]);

  const canalCorreo = canalElegido ?? config?.canal_email_activo ?? true;
  // Mientras la lista de destinatarios carga, se usa la que trae la
  // configuración: si no, la ayuda diría "sin destinatarios" un instante.
  const cantidadDestinatarios = cargando ? (config?.destinatarios.length ?? 0) : destinatarios.length;
  const hayCambios = config !== null && canalElegido !== null && canalElegido !== config.canal_email_activo;

  async function guardarCanales() {
    if (!puedeEditar || ocupado) return;
    setOcupado(true); setError(""); setMensaje("");
    try {
      const res = await apiFetch<{ mensaje: string; notificaciones: ConfigNotificaciones }>(
        `/alarmas/${alarma.id_alrm}/notificaciones`,
        { method: "PUT", body: { canal_email_activo: canalCorreo } },
      );
      setConfig(res.notificaciones);
      setCanalElegido(null);
      setMensaje(res.mensaje || MENSAJE_GUARDADO);
      setVersion(v => v + 1); // activar puede haber agregado el correo de la cuenta
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar la configuración");
    } finally {
      setOcupado(false);
    }
  }

  useEffect(() => {
    const intervalo = setInterval(() => setVersion(v => v + 1), 10000);
    return () => clearInterval(intervalo);
  }, []);

  useEffect(() => {
    let cancelado = false;
    Promise.all([
      apiFetch<{ items: Destinatario[] }>(`/alarmas/${alarma.id_alrm}/destinatarios`),
      apiFetch<Historial>("/alarmas/notificaciones", {
        params: { alarma_id: alarma.id_alrm, estado: estado || undefined, pagina, por_pagina: 10 },
      }),
    ]).then(([lista, envios]) => {
      if (!cancelado) { setDestinatarios(lista.items); setHistorial(envios); setError(""); }
    }).catch(err => {
      if (!cancelado) setError(err instanceof ApiError ? err.message : "No se pudo cargar la información");
    }).finally(() => { if (!cancelado) setCargando(false); });
    return () => { cancelado = true; };
  }, [alarma.id_alrm, estado, pagina, version]);

  async function operar(accion: () => Promise<unknown>) {
    setOcupado(true); setError("");
    try { await accion(); setVersion(v => v + 1); }
    catch (err) { setError(err instanceof ApiError ? err.message : "No se pudo guardar el cambio"); }
    finally { setOcupado(false); }
  }

  function agregar(e: FormEvent) {
    e.preventDefault();
    void operar(async () => {
      await apiFetch(`/alarmas/${alarma.id_alrm}/destinatarios`, { method: "POST", body: { correo } });
      setCorreo("");
    });
  }

  return (
    <dialog ref={dialogo} onCancel={onClose} aria-labelledby="notificaciones-titulo"
      className="w-[calc(100%-2rem)] max-w-4xl max-h-[90vh] rounded-2xl p-0 bg-white dark:bg-gray-950 text-gray-900 dark:text-white backdrop:bg-black/50">
      <div className="p-5 sm:p-7 space-y-6">
        <header className="flex justify-between gap-4 items-start">
          <div><h2 id="notificaciones-titulo" className="text-xl font-bold">Configurar notificaciones de {alarma.nmbr}</h2>
            <p className="text-sm mt-1">Regla: {alarma.estd === "Activa" ? "habilitada" : "pausada"}</p></div>
          <button type="button" onClick={onClose} className={boton} disabled={ocupado}>Cerrar</button>
        </header>
        {error && <p role="alert" className="text-red-600 dark:text-red-400">{error}</p>}
        {mensaje && (
          <p role="status" className="rounded-lg border border-[#ccff00]/40 bg-[#ccff00]/15 px-3 py-2 text-sm text-[#5a7000] dark:text-[#ccff00]">
            {mensaje}
          </p>
        )}

        {/* HU30 CA1/CA2/CA4: canales disponibles y su estado. */}
        <section aria-labelledby="canales-titulo" className="space-y-3">
          <h3 id="canales-titulo" className="font-semibold">1. Canales de notificación</h3>
          {!config && !error && <p role="status" className="text-sm">Cargando canales…</p>}
          {config && (
            <ul className="space-y-2">
              {config.canales.map(c => (
                <li key={c.canal} className="flex flex-wrap items-center justify-between gap-3 rounded-xl border border-black/15 dark:border-white/15 p-3">
                  <div className="min-w-0">
                    <p className="font-medium">{c.nombre}</p>
                    <p className="text-xs text-gray-600 dark:text-gray-300">
                      {c.canal === "email"
                        ? ayudaCanalCorreo(canalCorreo, cantidadDestinatarios, config.correo_cuenta)
                        : estadoCanal(c)}
                    </p>
                  </div>
                  {c.canal === "email" ? (
                    <label className="flex items-center gap-2 text-sm cursor-pointer">
                      <input type="checkbox" role="switch" aria-label="Correo electrónico" checked={canalCorreo} disabled={!puedeEditar || ocupado}
                        aria-describedby="canal-email-estado"
                        onChange={e => { setMensaje(""); setCanalElegido(e.target.checked); }} />
                      <span id="canal-email-estado">{canalCorreo ? "Activo" : "Desactivado"}</span>
                    </label>
                  ) : (
                    <span className="text-xs rounded-full border border-black/15 dark:border-white/15 px-2 py-1">{estadoCanal(c)}</span>
                  )}
                </li>
              ))}
            </ul>
          )}
          {puedeEditar && <button type="button" onClick={() => void guardarCanales()} disabled={ocupado || !hayCambios}
            className="rounded-lg px-4 py-2 text-sm font-bold bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50">
            {ocupado ? "Guardando…" : "Guardar"}
          </button>}
        </section>

        <section aria-labelledby="destinatarios-titulo" className="space-y-3">
          <h3 id="destinatarios-titulo" className="font-semibold">2. Correos que recibirán la alarma</h3>
          {config && !config.canal_email_activo && (
            <p className="text-sm rounded-lg border border-amber-400/50 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-amber-800 dark:text-amber-200">
              El canal de correo está desactivado: estos destinatarios no recibirán avisos hasta que lo actives.
            </p>
          )}
          <p className="text-sm">Se enviará un aviso a cada correo cuando la condición se active. Para recibir otro, primero debe volver a la normalidad.</p>
          {puedeEditar && <form onSubmit={agregar} className="flex flex-col sm:flex-row gap-2">
            <label className="sr-only" htmlFor="destinatario-correo">Correo del destinatario</label>
            <input id="destinatario-correo" type="email" required maxLength={150} placeholder="operaciones@empresa.com"
              value={correo} onChange={e => setCorreo(e.target.value)} className={`${campo} flex-1`} disabled={ocupado} />
            <button className={boton} disabled={ocupado || destinatarios.length >= 100}>Añadir correo</button>
          </form>}
          {!cargando && destinatarios.length === 0 && <p className="text-sm">Aún no hay destinatarios. {puedeEditar ? "Añade al menos uno para recibir avisos." : "Solicita su configuración a una persona con permiso de edición."}</p>}
          <p className="text-xs text-gray-600 dark:text-gray-400">Los destinatarios de las alarmas activas también reciben avisos por ausencia de datos de los equipos del proyecto.</p>
          <ul className="space-y-2">{destinatarios.map(d => (
            <li key={d.id} className="flex items-center justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-2">
              <span className="break-all">{d.correo}</span>
              {puedeEditar && <button className={boton} disabled={ocupado} aria-label={`Quitar ${d.correo}`}
                onClick={() => void operar(() => apiFetch(`/alarmas/${alarma.id_alrm}/destinatarios/${d.id}`, { method: "DELETE" }))}>Quitar</button>}
            </li>
          ))}</ul>
          {puedeEditar && <button className={boton} disabled={ocupado} onClick={() => void operar(async () => {
            await apiFetch(`/alarmas/${alarma.id_alrm}`, { method: "PATCH", body: { estado: alarma.estd === "Activa" ? "Inactiva" : "Activa" } });
            onUpdate();
          })}>{alarma.estd === "Activa" ? "Pausar alarma" : "Activar alarma"}</button>}
        </section>
        <section aria-labelledby="historial-titulo" className="space-y-3">
          <h3 id="historial-titulo" className="font-semibold">3. Historial de notificaciones</h3>
          {alarma.correos_habilitados === false && <p role="status" className="rounded-lg bg-amber-500/10 p-3 text-sm">Los correos están pausados por la vigencia de la suscripción o porque se detuvo el monitoreo. Al regularizar se enviará un resumen de los últimos estados de alarma conocidos.</p>}
          <p className="text-xs text-gray-600 dark:text-gray-400">Horarios en {zonaHoraria}</p>
          <p className="text-sm">«Enviado» significa que el proveedor aceptó el correo; la llegada a la bandeja de entrada se verifica con el destinatario.</p>
          <div className="flex flex-wrap gap-2">
            <label htmlFor="estado-envio" className="self-center text-sm">Resultado</label>
            <select id="estado-envio" value={estado} onChange={e => { setEstado(e.target.value); setPagina(1); }} className={campo}>
              <option value="">Todos</option>{["Pendiente", "Encolado", "Reintentando", "Enviado", "Fallido", "Omitido"].map(s => <option key={s}>{s}</option>)}
            </select>
            <button className={boton} onClick={() => setVersion(v => v + 1)}>Actualizar</button>
          </div>
          {cargando && <p role="status">Cargando notificaciones…</p>}
          {!cargando && historial.total === 0 && <p className="text-sm">No hay notificaciones con este resultado.</p>}
          <div className="space-y-3">{historial.items.map(n => (
            <article key={n.id} className="rounded-xl border border-black/15 dark:border-white/15 p-3 space-y-1 text-sm">
              <p className="font-semibold break-all">{n.destinatario} · {n.estado}</p>
              <p>{n.tipo === "alarma_activada" ? "Alarma activada" : n.tipo === "resumen_alarma_reanudada" ? "Resumen tras reanudar avisos" : n.tipo === "dispositivo_sin_datos" ? "Equipo sin datos" : n.tipo} · {fecha(n.creada)}</p>
              {n.enviada && <p>Aceptado por el proveedor: {fecha(n.enviada)}</p>}
              {n.estado === "Reintentando" && n.proximo_intento && <p>Próximo intento: {fecha(n.proximo_intento)}</p>}
              {(n.ultimo_error || n.intentos.length > 0) && <details><summary className="cursor-pointer">Ver diagnóstico e intentos</summary>
                {n.ultimo_error && <p>Último error: {n.ultimo_error}</p>}
                <ol>{n.intentos.map(i => <li key={i.numero}>Intento {i.numero}: {i.resultado} · {fecha(i.fecha)}{i.error ? ` · ${i.error}` : ""}</li>)}</ol>
                {n.mensaje_id && <p className="break-all">Referencia del proveedor: {n.mensaje_id}</p>}
              </details>}
            </article>
          ))}</div>
          <div className="flex flex-wrap items-center gap-3 text-sm">
            <button className={boton} disabled={pagina <= 1} onClick={() => setPagina(p => p - 1)}>Anterior</button>
            <span>Página {pagina} · {historial.total} notificaciones</span>
            <button className={boton} disabled={pagina * 10 >= historial.total} onClick={() => setPagina(p => p + 1)}>Siguiente</button>
          </div>
        </section>
      </div>
    </dialog>
  );
}
