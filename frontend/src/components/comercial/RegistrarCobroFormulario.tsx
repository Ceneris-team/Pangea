import { useEffect, useRef, useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import { fechaLima, type Cliente } from "../../types/comercial";
import { fechaVisible } from "./asignacionPlan";
import { METODOS_PAGO, cuerpoCobro, validarCobro, type DatosCobro, type ErroresCobro } from "./registroCobro";

const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 outline-none focus:border-lime-500 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const campoConError = "border-red-500 dark:border-red-400";
const etiqueta = "mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200";
const boton = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 hover:bg-[#b9eb00] disabled:cursor-not-allowed disabled:opacity-50";

/**
 * PP-67 - Registrar cobro (PP-311).
 * CA1: Monto cobrado, Fecha de cobro y Método de pago.
 * CA2: GUARDAR registra; la página muestra "Cobro registrado correctamente".
 * CA4: CANCELAR descarta el formulario sin llamar a la API.
 */
export default function RegistrarCobroFormulario({ cliente, onCancelar, onRegistrado }: {
  cliente: Cliente;
  onCancelar: () => void;
  onRegistrado: (mensaje: string) => Promise<void>;
}) {
  const hoy = fechaLima();
  const [datos, setDatos] = useState<DatosCobro>({ monto: "", fecha_cobro: hoy, metodo_pago: "" });
  const [errores, setErrores] = useState<ErroresCobro>({});
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);
  const formulario = useRef<HTMLFormElement>(null);

  // El botón está en la tarjeta del cliente, más abajo: se lleva la vista al formulario.
  useEffect(() => { formulario.current?.scrollIntoView?.({ behavior: "smooth", block: "start" }); }, []);

  function cambiar(clave: keyof DatosCobro, valor: string) {
    setDatos({ ...datos, [clave]: valor });
    if (errores[clave]) setErrores({ ...errores, [clave]: undefined });
  }

  async function guardar(evento: FormEvent) {
    evento.preventDefault();
    setError("");
    const encontrados = validarCobro(datos, hoy);
    setErrores(encontrados);
    if (Object.keys(encontrados).length > 0) return;
    setOcupado(true);
    try {
      const respuesta = await apiFetch<{ mensaje: string }>(`/comercial/clientes/${cliente.id_clnt}/cobros`, {
        method: "POST", body: cuerpoCobro(datos),
      });
      await onRegistrado(respuesta.mensaje);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar el cobro");
    } finally {
      setOcupado(false);
    }
  }

  const moneda = cliente.condiciones?.moneda ?? "PEN";

  return <form ref={formulario} onSubmit={guardar} noValidate aria-label="Registrar cobro" className="scroll-mt-28 space-y-5 rounded-2xl border border-lime-500/50 bg-white/80 p-5 dark:bg-[#171d2a]">
    <div>
      <h3 className="text-lg font-semibold">Registrar cobro de {cliente.nombre}</h3>
      <p className="text-sm text-gray-600 dark:text-gray-300">
        Se asocia al período actual: {cliente.plan_nombre} del {fechaVisible(cliente.fecha_inicio)} al {fechaVisible(cliente.fecha_vencimiento)}.
      </p>
    </div>
    {error && <div role="alert" className="rounded-xl border border-red-400/50 bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</div>}
    <div className="grid gap-4 md:grid-cols-3">
      <label>
        <span className={etiqueta}>Monto cobrado ({moneda}) *</span>
        <input className={`${campo} ${errores.monto ? campoConError : ""}`} inputMode="decimal" placeholder="Ej. 350.00" maxLength={16}
          value={datos.monto} aria-invalid={Boolean(errores.monto)} onChange={(e) => cambiar("monto", e.target.value)} />
        {errores.monto && <span className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores.monto}</span>}
      </label>
      <label>
        <span className={etiqueta}>Fecha de cobro *</span>
        <input className={`${campo} ${errores.fecha_cobro ? campoConError : ""}`} type="date" max={hoy}
          value={datos.fecha_cobro} aria-invalid={Boolean(errores.fecha_cobro)} onChange={(e) => cambiar("fecha_cobro", e.target.value)} />
        {errores.fecha_cobro && <span className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores.fecha_cobro}</span>}
      </label>
      <label>
        <span className={etiqueta}>Método de pago *</span>
        <select className={`${campo} ${errores.metodo_pago ? campoConError : ""}`} value={datos.metodo_pago}
          aria-invalid={Boolean(errores.metodo_pago)} onChange={(e) => cambiar("metodo_pago", e.target.value)}>
          <option value="">Seleccionar método</option>
          {METODOS_PAGO.map((metodo) => <option key={metodo} value={metodo}>{metodo}</option>)}
        </select>
        {errores.metodo_pago && <span className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores.metodo_pago}</span>}
      </label>
    </div>
    <div className="flex gap-3">
      <button className={boton} disabled={ocupado}>{ocupado ? "Guardando..." : "GUARDAR"}</button>
      <button type="button" className="rounded-xl border border-gray-300 px-4 py-2 font-semibold dark:border-white/20" onClick={onCancelar} disabled={ocupado}>CANCELAR</button>
    </div>
  </form>;
}
