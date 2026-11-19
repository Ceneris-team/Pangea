import { useEffect, useRef, useState, type FormEvent } from "react";
import { ApiError, apiFetch } from "../services/api";
import {
  OPERADORES_ALARMA,
  condicionParaEnviar,
  errorUmbral,
  formatearUmbral,
  fraseCondicion,
  type OperadorAlarma,
} from "../pages/condicionAlarma";

/**
 * HU29 (PP-74, PP-228): ver y ACTUALIZAR la condición de una alarma ya
 * creada. "Una condición por alarma en v1.0": actualizar REEMPLAZA la
 * condición (PUT /alarmas/{id}/condicion), no agrega otra. Si la alarma se
 * creó antes con varias condiciones, se avisa que quedará solo esta.
 */

interface Detalle {
  id_alrm: number;
  alarma: string;
  parametro: string;
  unidad: string;
  oprdr: OperadorAlarma | null;
  vlr_umbrl: number | null;
  condicion: string | null;
  condiciones_guardadas: number;
}

interface Props {
  alarma: { id_alrm: number; nmbr: string };
  onClose: () => void;
  /** Se llama tras actualizar, con el mensaje del backend. */
  onUpdate: (mensaje: string) => void;
}

const campo =
  "rounded-lg border border-black/20 dark:border-white/20 bg-white dark:bg-gray-900 px-3 py-2 text-sm w-full";
const boton =
  "rounded-lg border border-black/20 dark:border-white/20 px-3 py-2 text-sm disabled:opacity-40";
const botonPrimario =
  "rounded-lg px-4 py-2 text-sm font-bold bg-[#ccff00] text-[#1a202c] hover:bg-[#b8e600] disabled:opacity-50";

export default function EditarCondicionAlarma({ alarma, onClose, onUpdate }: Props) {
  const dialogo = useRef<HTMLDialogElement>(null);
  const [detalle, setDetalle] = useState<Detalle | null>(null);
  const [operador, setOperador] = useState<OperadorAlarma>(">");
  const [umbral, setUmbral] = useState("");
  const [tocado, setTocado] = useState(false);
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  useEffect(() => {
    dialogo.current?.showModal();
  }, []);

  useEffect(() => {
    let cancelado = false;
    apiFetch<Detalle>(`/alarmas/${alarma.id_alrm}/condicion`)
      .then((d) => {
        if (cancelado) return;
        setDetalle(d);
        if (d.oprdr) setOperador(d.oprdr);
        if (d.vlr_umbrl !== null) setUmbral(formatearUmbral(d.vlr_umbrl));
      })
      .catch((err) => {
        if (!cancelado)
          setError(err instanceof ApiError ? err.message : "No se pudo cargar la condición");
      });
    return () => {
      cancelado = true;
    };
  }, [alarma.id_alrm]);

  const mensajeUmbral = tocado ? errorUmbral(umbral) : null;
  const frase = detalle ? fraseCondicion(detalle.parametro, operador, umbral, detalle.unidad) : null;
  const sinCambios =
    !!detalle &&
    detalle.condiciones_guardadas === 1 &&
    detalle.oprdr === operador &&
    detalle.vlr_umbrl !== null &&
    !errorUmbral(umbral) &&
    Number(condicionParaEnviar(operador, umbral).vlr_umbrl) === detalle.vlr_umbrl;

  async function actualizar(e: FormEvent) {
    e.preventDefault();
    setTocado(true);
    const errorDelUmbral = errorUmbral(umbral);
    if (errorDelUmbral) {
      setError(errorDelUmbral);
      return;
    }
    setOcupado(true);
    setError("");
    try {
      const res = await apiFetch<{ mensaje: string; condicion: Detalle }>(
        `/alarmas/${alarma.id_alrm}/condicion`,
        { method: "PUT", body: condicionParaEnviar(operador, umbral) },
      );
      onUpdate(res.mensaje);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar la condición");
    } finally {
      setOcupado(false);
    }
  }

  return (
    <dialog
      ref={dialogo}
      onCancel={onClose}
      aria-labelledby="condicion-titulo"
      className="w-[calc(100%-2rem)] max-w-xl rounded-2xl p-0 bg-white dark:bg-gray-950 text-gray-900 dark:text-white backdrop:bg-black/50"
    >
      <form onSubmit={actualizar} className="p-5 sm:p-7 space-y-5">
        <header className="flex justify-between gap-4 items-start">
          <div>
            <h2 id="condicion-titulo" className="text-xl font-bold">
              Condición de {alarma.nmbr}
            </h2>
            {detalle && (
              <p className="text-sm mt-1 text-gray-600 dark:text-gray-300">
                Parámetro: {detalle.parametro}
                {detalle.unidad ? ` (${detalle.unidad})` : ""}
              </p>
            )}
          </div>
          <button type="button" onClick={onClose} className={boton} disabled={ocupado}>
            Cerrar
          </button>
        </header>

        {error && (
          <p role="alert" className="text-sm text-red-600 dark:text-red-400">
            {error}
          </p>
        )}

        {!detalle && !error && <p role="status">Cargando condición…</p>}

        {detalle && (
          <>
            <p className="text-sm">
              <span className="font-semibold">Condición actual: </span>
              {detalle.condicion ?? "Sin condición configurada"}
            </p>

            {detalle.condiciones_guardadas > 1 && (
              <p
                role="note"
                className="rounded-lg border border-amber-400/50 bg-amber-50 dark:bg-amber-900/20 px-3 py-2 text-sm text-amber-800 dark:text-amber-200"
              >
                Esta alarma se creó con {detalle.condiciones_guardadas} condiciones. En esta versión
                cada alarma tiene una sola: al actualizar quedará únicamente la que definas aquí.
              </p>
            )}

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <label className="text-sm font-medium space-y-1" htmlFor="condicion-oprdr">
                <span className="block">Operador</span>
                <select
                  id="condicion-oprdr"
                  value={operador}
                  onChange={(e) => setOperador(e.target.value as OperadorAlarma)}
                  className={campo + " cursor-pointer"}
                >
                  {OPERADORES_ALARMA.map((op) => (
                    <option key={op.valor} value={op.valor}>
                      {op.valor} {op.texto}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm font-medium space-y-1" htmlFor="condicion-umbral">
                <span className="block">
                  Valor umbral{detalle.unidad ? ` (${detalle.unidad})` : ""}
                </span>
                <input
                  id="condicion-umbral"
                  type="text"
                  inputMode="decimal"
                  autoComplete="off"
                  value={umbral}
                  onChange={(e) => setUmbral(e.target.value)}
                  onBlur={() => setTocado(true)}
                  aria-invalid={mensajeUmbral ? true : undefined}
                  aria-describedby={mensajeUmbral ? "condicion-umbral-error" : undefined}
                  className={campo}
                />
                {mensajeUmbral && (
                  <span id="condicion-umbral-error" className="block text-xs text-red-600 dark:text-red-400">
                    {mensajeUmbral}
                  </span>
                )}
              </label>
            </div>

            <p
              aria-live="polite"
              data-testid="frase-condicion"
              className="rounded-xl border border-[#ccff00]/40 bg-[#ccff00]/10 px-4 py-3 text-sm"
            >
              {frase ?? "Elige el operador y escribe el valor umbral para ver cuándo se activará."}
            </p>

            <div className="flex justify-end gap-3">
              <button type="button" onClick={onClose} className={boton} disabled={ocupado}>
                Cancelar
              </button>
              <button type="submit" className={botonPrimario} disabled={ocupado || sinCambios}>
                {ocupado ? "Actualizando…" : "Actualizar"}
              </button>
            </div>
          </>
        )}
      </form>
    </dialog>
  );
}
