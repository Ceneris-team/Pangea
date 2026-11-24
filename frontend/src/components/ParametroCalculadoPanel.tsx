import { useEffect, useState, type FormEvent } from "react";
import DrawerPanel from "./layout/DrawerPanel";
import { apiFetch, ApiError } from "../services/api";

export interface DefinicionCalculada {
  id_prm_clc: number;
  nmbr: string;
  frml: string;
  undd: string;
  dscrpcn: string | null;
  estd: string;
  empresa_nombre: string;
  sede_nombre: string;
  ambito: string;
}
interface Detalle extends DefinicionCalculada {
  referencias: { variable: string; nombre: string | null; unidad: string | null; estado: string | null; disponible: boolean }[];
}
const campo = "mt-1 w-full rounded-xl border border-black/15 bg-white/50 px-3 py-2.5 text-sm text-gray-900 outline-none focus:ring-2 focus:ring-[#8fb300] dark:border-white/20 dark:bg-gray-900 dark:text-white";
const boton = "rounded-xl border border-gray-400 px-4 py-2 text-sm disabled:opacity-40";
const mensaje = (err: unknown, defecto: string) => err instanceof ApiError ? err.message : defecto;

export function DetalleParametroCalculado({ id, onCerrar }: { id: number; onCerrar: () => void }) {
  const [detalle, setDetalle] = useState<Detalle | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<Detalle>(`/parametros-calculados/${id}`, { signal: controller.signal })
      .then(res => { if (!controller.signal.aborted) { setDetalle(res); setError(null); } })
      .catch(err => { if (!controller.signal.aborted) setError(mensaje(err, "No se pudo cargar el detalle.")); });
    return () => controller.abort();
  }, [id, revision]);
  return <DrawerPanel abierto onCerrar={onCerrar} titulo="Detalle del parámetro calculado" ancho="lg">
    <div className="space-y-5 text-sm text-gray-800 dark:text-gray-200">
      {error ? <div role="alert"><p>{error}</p><button className={`${boton} mt-3`} onClick={() => setRevision(v => v + 1)}>Reintentar detalle</button></div>
        : !detalle ? <p role="status">Cargando detalle…</p> : <>
          <h3 className="break-words text-xl font-bold">{detalle.nmbr}</h3>
          <dl className="space-y-4">
            <div><dt className="font-semibold">Descripción</dt><dd className="mt-1 break-words">{detalle.dscrpcn || "Sin descripción"}</dd></div>
            <div><dt className="font-semibold">Fórmula completa</dt><dd className="mt-1 whitespace-pre-wrap break-words rounded-xl bg-black/5 p-4 font-mono dark:bg-white/5">{detalle.frml}</dd></div>
            <div className="flex gap-10"><div><dt className="font-semibold">Unidad de medida</dt><dd>{detalle.undd || "—"}</dd></div><div><dt className="font-semibold">Estado</dt><dd>{detalle.estd}</dd></div></div>
            <div><dt className="font-semibold">Ámbito de aplicación</dt><dd className="mt-1">{detalle.empresa_nombre}<br />{detalle.ambito}</dd></div>
          </dl>
          <section aria-label="Parámetros de origen">
            <h4 className="mb-2 font-semibold">Parámetros de origen</h4>
            {detalle.referencias.length ? <ul className="space-y-3">{detalle.referencias.map(r => <li key={r.variable} className="break-words rounded-xl border border-black/10 p-3 dark:border-white/10">
              {r.disponible ? <><p className="font-semibold">{r.nombre} ({r.unidad || "Sin unidad"})</p><p className="mt-1 text-xs text-gray-500 dark:text-gray-400">Estado del parámetro de origen: {r.estado}</p></>
                : <><p className="font-mono">{r.variable}</p><p className="mt-1 text-xs text-amber-700 dark:text-amber-300">Referencia sin vínculo verificable con los parámetros disponibles en este ámbito.</p></>}
            </li>)}</ul> : <p>No se identificaron referencias a parámetros de origen en esta expresión.</p>}
          </section>
          <p className="text-xs text-gray-500 dark:text-gray-400">Esta consulta muestra la definición guardada y no ejecuta la fórmula. Activo o Inactivo describe la definición, no la conectividad de los dispositivos.</p>
        </>}
    </div>
  </DrawerPanel>;
}

interface Sede { id_sd: number; nombre: string; origenes: { id_prmtr: number; nombre: string; unidad: string }[] }
interface Formulario { nmbr: string; frml: string; undd: string; dscrpcn: string; estd: string }

export function CrearParametroCalculado({ onCerrar, onCreado }: { onCerrar: () => void; onCreado: () => void }) {
  const [sedes, setSedes] = useState<Sede[] | null>(null);
  const [sedeId, setSedeId] = useState("");
  const [errorOpciones, setErrorOpciones] = useState<string | null>(null);
  const [revision, setRevision] = useState(0);
  const [form, setForm] = useState<Formulario>({ nmbr: "", frml: "", undd: "", dscrpcn: "", estd: "Activo" });
  const [error, setError] = useState<string | null>(null);
  const [guardando, setGuardando] = useState(false);
  useEffect(() => {
    const controller = new AbortController();
    apiFetch<{ sedes: Sede[] }>("/parametros-calculados/opciones-creacion", { signal: controller.signal })
      .then(res => {
        if (controller.signal.aborted) return;
        setSedes(res.sedes); setErrorOpciones(null);
        setSedeId(actual => res.sedes.some(s => String(s.id_sd) === actual) ? actual : res.sedes.length === 1 ? String(res.sedes[0].id_sd) : "");
      }).catch(err => { if (!controller.signal.aborted) setErrorOpciones(mensaje(err, "No se pudieron cargar los ámbitos y parámetros de origen.")); });
    return () => controller.abort();
  }, [revision]);
  const sede = sedes?.find(s => String(s.id_sd) === sedeId);
  function cambiar(campo: keyof Formulario, valor: string) { setForm(actual => ({ ...actual, [campo]: valor })); }
  async function guardar(e: FormEvent) {
    e.preventDefault();
    if (guardando || !sede || !sede.origenes.length) return;
    setGuardando(true); setError(null);
    try {
      await apiFetch("/parametros-calculados", { method: "POST", body: { ...form, id_sd: sede.id_sd } });
      onCreado();
    } catch (err) { setError(mensaje(err, "No se pudo registrar la definición. Revisa el listado antes de reintentar.")); }
    finally { setGuardando(false); }
  }
  return <DrawerPanel abierto onCerrar={() => { if (!guardando) onCerrar(); }} titulo="Añadir parámetro calculado" ancho="lg">
    <form onSubmit={guardar} className="space-y-5 text-sm text-gray-800 dark:text-gray-200" aria-label="Registrar definición calculada">
      <p>Define una variable derivada a partir de parámetros numéricos configurados. Guardar esta definición no genera ni modifica mediciones.</p>
      {errorOpciones ? <div role="alert"><p>{errorOpciones}</p><button type="button" className={`${boton} mt-3`} onClick={() => setRevision(v => v + 1)}>Reintentar opciones</button></div>
        : !sedes ? <p role="status">Cargando ámbitos y parámetros de origen…</p> : <>
          <label className="block">Ámbito compartido
            <select className={campo} required value={sedeId} disabled={guardando} onChange={e => { setSedeId(e.target.value); cambiar("frml", ""); }}>
              <option value="">Selecciona un ámbito</option>{sedes.map(s => <option key={s.id_sd} value={s.id_sd}>{s.nombre}</option>)}
            </select>
          </label>
          {sede && <p className="text-xs text-gray-500 dark:text-gray-400">La definición estará disponible para los proyectos que comparten {sede.nombre}.</p>}
          <label className="block">Nombre<input className={campo} required maxLength={100} value={form.nmbr} disabled={guardando} onChange={e => cambiar("nmbr", e.target.value)} /></label>
          <section aria-label="Insertar parámetro de origen">
            <h3 className="mb-2 font-semibold">Parámetros de origen disponibles</h3>
            {!sede ? <p>Selecciona el ámbito para ver sus parámetros.</p> : !sede.origenes.length ? <p role="status">No hay parámetros numéricos activos configurados en este ámbito. Configura primero el formato de datos de sus dispositivos.</p>
              : <div className="flex flex-wrap gap-2">{sede.origenes.map(p => <button type="button" key={p.id_prmtr} disabled={guardando} className={`${boton} text-left`} onClick={() => cambiar("frml", `${form.frml}${form.frml && !form.frml.endsWith(" ") ? " " : ""}[${p.nombre}]`)}>Insertar {p.nombre} ({p.unidad || "Sin unidad"})</button>)}</div>}
          </section>
          <label className="block">Fórmula<textarea className={`${campo} min-h-28 font-mono`} required maxLength={2000} value={form.frml} disabled={guardando} onChange={e => cambiar("frml", e.target.value)} aria-describedby="ayuda-formula" /></label>
          <p id="ayuda-formula" className="text-xs text-gray-500 dark:text-gray-400">Inserta los parámetros y escribe operaciones con +, -, *, /, **, % y paréntesis. Usa punto para los decimales. Ejemplo de estructura: ([parámetro de origen] * 1.5).</p>
          <label className="block">Unidad de medida<input className={campo} required maxLength={30} value={form.undd} disabled={guardando} onChange={e => cambiar("undd", e.target.value)} /></label>
          <label className="block">Descripción (opcional)<textarea className={campo} maxLength={300} value={form.dscrpcn} disabled={guardando} onChange={e => cambiar("dscrpcn", e.target.value)} /></label>
          <label className="block">Estado de la definición<select className={campo} value={form.estd} disabled={guardando} onChange={e => cambiar("estd", e.target.value)}><option>Activo</option><option>Inactivo</option></select></label>
        </>}
      {error && <p role="alert" className="text-red-700 dark:text-red-300">{error}</p>}
      <div className="flex flex-wrap justify-end gap-3"><button type="button" disabled={guardando} className={boton} onClick={onCerrar}>Cancelar</button><button type="submit" disabled={guardando || !!errorOpciones || !sede?.origenes.length} className="rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 disabled:opacity-40">{guardando ? "Guardando…" : "Guardar definición"}</button></div>
    </form>
  </DrawerPanel>;
}
