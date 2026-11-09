import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../services/api";

interface Destinatario { id: number; correo: string }
interface Intento { numero: number; fecha: string; resultado: string; error: string | null }
interface Envio {
  id: number; destinatario: string; tipo: string; estado: string; creada: string;
  enviada: string | null; proximo_intento: string | null; ultimo_error: string | null;
  mensaje_id: string | null; intentos: Intento[];
}
interface Historial { total: number; items: Envio[] }
interface Props {
  alarma: { id_alrm: number; nmbr: string; estd: string };
  onClose: () => void;
  onUpdate: () => void;
}

const campo = "rounded-lg border border-black/20 dark:border-white/20 bg-white dark:bg-gray-900 px-3 py-2 text-sm min-w-0";
const boton = "rounded-lg border border-black/20 dark:border-white/20 px-3 py-2 text-sm disabled:opacity-40";
const fecha = (valor: string) => new Date(valor).toLocaleString("es-PE");

export default function NotificacionesAlarma({ alarma, onClose, onUpdate }: Props) {
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

  useEffect(() => {
    dialogo.current?.showModal();
  }, []);

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
      if (!cancelado) { setDestinatarios(lista.items); setHistorial(envios); }
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
          <div><h2 id="notificaciones-titulo" className="text-xl font-bold">Notificaciones de {alarma.nmbr}</h2>
            <p className="text-sm mt-1">Estado de la alarma: {alarma.estd}</p></div>
          <button type="button" onClick={onClose} className={boton} disabled={ocupado}>Cerrar</button>
        </header>
        {error && <p role="alert" className="text-red-600 dark:text-red-400">{error}</p>}
        <section aria-labelledby="destinatarios-titulo" className="space-y-3">
          <h3 id="destinatarios-titulo" className="font-semibold">1. Correos que recibirán la alarma</h3>
          <p className="text-sm">Se enviará un aviso a cada correo cuando la condición se active. Para recibir otro, primero debe volver a la normalidad.</p>
          <form onSubmit={agregar} className="flex flex-col sm:flex-row gap-2">
            <label className="sr-only" htmlFor="destinatario-correo">Correo del destinatario</label>
            <input id="destinatario-correo" type="email" required maxLength={150} placeholder="operaciones@empresa.com"
              value={correo} onChange={e => setCorreo(e.target.value)} className={`${campo} flex-1`} disabled={ocupado} />
            <button className={boton} disabled={ocupado || destinatarios.length >= 100}>Añadir correo</button>
          </form>
          {!cargando && destinatarios.length === 0 && <p className="text-sm">Aún no hay destinatarios. Añade al menos uno para recibir avisos.</p>}
          <ul className="space-y-2">{destinatarios.map(d => (
            <li key={d.id} className="flex items-center justify-between gap-3 border-b border-black/10 dark:border-white/10 pb-2">
              <span className="break-all">{d.correo}</span>
              <button className={boton} disabled={ocupado} aria-label={`Quitar ${d.correo}`}
                onClick={() => void operar(() => apiFetch(`/alarmas/${alarma.id_alrm}/destinatarios/${d.id}`, { method: "DELETE" }))}>Quitar</button>
            </li>
          ))}</ul>
          <button className={boton} disabled={ocupado} onClick={() => void operar(async () => {
            await apiFetch(`/alarmas/${alarma.id_alrm}`, { method: "PATCH", body: { estado: alarma.estd === "Activa" ? "Inactiva" : "Activa" } });
            onUpdate();
          })}>{alarma.estd === "Activa" ? "Pausar alarma" : "Activar alarma"}</button>
        </section>
        <section aria-labelledby="historial-titulo" className="space-y-3">
          <h3 id="historial-titulo" className="font-semibold">2. Historial de notificaciones</h3>
          <p className="text-sm">«Enviado» significa que el proveedor aceptó el correo; la llegada a la bandeja de entrada se verifica con el destinatario.</p>
          <div className="flex flex-wrap gap-2">
            <label htmlFor="estado-envio" className="self-center text-sm">Resultado</label>
            <select id="estado-envio" value={estado} onChange={e => { setEstado(e.target.value); setPagina(1); }} className={campo}>
              <option value="">Todos</option>{["Pendiente", "Encolado", "Reintentando", "Enviado", "Fallido"].map(s => <option key={s}>{s}</option>)}
            </select>
            <button className={boton} onClick={() => setVersion(v => v + 1)}>Actualizar</button>
          </div>
          {cargando && <p role="status">Cargando notificaciones…</p>}
          {!cargando && historial.total === 0 && <p className="text-sm">No hay notificaciones con este resultado.</p>}
          <div className="space-y-3">{historial.items.map(n => (
            <article key={n.id} className="rounded-xl border border-black/15 dark:border-white/15 p-3 space-y-1 text-sm">
              <p className="font-semibold break-all">{n.destinatario} · {n.estado}</p>
              <p>{n.tipo === "alarma_activada" ? "Alarma activada" : n.tipo} · {fecha(n.creada)}</p>
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
