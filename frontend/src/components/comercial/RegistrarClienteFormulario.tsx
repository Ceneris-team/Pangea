import { useState, type FormEvent } from "react";
import { apiFetch } from "../../services/api";
import type { Cliente } from "../../types/comercial";
import { CLIENTE_VACIO, cuerpoCliente, validarCliente, type DatosCliente, type ErroresCliente } from "./registroCliente";

const campo = "w-full rounded-xl border border-gray-300 bg-white px-3 py-2 text-gray-900 outline-none focus:border-lime-500 dark:border-white/20 dark:bg-[#242b39] dark:text-white";
const campoConError = "border-red-500 dark:border-red-400";
const etiqueta = "mb-1 block text-sm font-medium text-gray-700 dark:text-gray-200";
const boton = "rounded-xl bg-[#ccff00] px-4 py-2 font-semibold text-gray-950 hover:bg-[#b9eb00] disabled:cursor-not-allowed disabled:opacity-50";

const CAMPOS: { clave: keyof DatosCliente; titulo: string; obligatorio: boolean; tipo: string; maximo: number; ayuda: string }[] = [
  { clave: "razon_social", titulo: "Razón social", obligatorio: true, tipo: "text", maximo: 200, ayuda: "Ej. Minera Andina S.A.C." },
  { clave: "ruc", titulo: "RUC", obligatorio: true, tipo: "text", maximo: 11, ayuda: "11 dígitos" },
  { clave: "correo_contacto", titulo: "Correo de contacto", obligatorio: true, tipo: "email", maximo: 150, ayuda: "usuario@dominio.com" },
  { clave: "telefono_contacto", titulo: "Teléfono de contacto", obligatorio: false, tipo: "tel", maximo: 20, ayuda: "Opcional. Ej. +51 999 888 777" },
];

/**
 * HU 65 - Registrar cliente (PP-304).
 * CA1: Razón social, RUC, Correo de contacto y Teléfono de contacto.
 * CA2: GUARDAR registra y avisa a la página, que muestra "Cliente registrado correctamente".
 * CA4: CANCELAR descarta el formulario sin llamar a la API.
 */
export default function RegistrarClienteFormulario({ onCancelar, onRegistrado }: {
  onCancelar: () => void;
  onRegistrado: (cliente: Cliente, mensaje: string) => Promise<void>;
}) {
  const [datos, setDatos] = useState<DatosCliente>(CLIENTE_VACIO);
  const [errores, setErrores] = useState<ErroresCliente>({});
  const [error, setError] = useState("");
  const [ocupado, setOcupado] = useState(false);

  function cambiar(clave: keyof DatosCliente, valor: string) {
    setDatos({ ...datos, [clave]: valor });
    if (errores[clave]) setErrores({ ...errores, [clave]: undefined });
  }

  async function guardar(evento: FormEvent) {
    evento.preventDefault();
    setError("");
    const encontrados = validarCliente(datos);
    setErrores(encontrados);
    if (Object.keys(encontrados).length > 0) return;
    setOcupado(true);
    try {
      const respuesta = await apiFetch<{ mensaje: string; cliente: Cliente }>("/comercial/clientes", {
        method: "POST", body: cuerpoCliente(datos),
      });
      await onRegistrado(respuesta.cliente, respuesta.mensaje);
    } catch (e) {
      setError(e instanceof Error ? e.message : "No se pudo registrar el cliente");
    } finally {
      setOcupado(false);
    }
  }

  return <form onSubmit={guardar} noValidate aria-label="Registrar cliente" className="space-y-5 rounded-2xl border border-lime-500/50 bg-white/80 p-5 dark:bg-[#171d2a]">
    <div>
      <h3 className="text-lg font-semibold">Registrar cliente</h3>
      <p className="text-sm text-gray-600 dark:text-gray-300">Los campos con * son obligatorios. Después podrás asignarle su plan.</p>
    </div>
    {error && <div role="alert" className="rounded-xl border border-red-400/50 bg-red-500/10 p-3 text-red-700 dark:text-red-200">{error}</div>}
    <div className="grid gap-4 md:grid-cols-2">
      {CAMPOS.map(({ clave, titulo, obligatorio, tipo, maximo, ayuda }) => (
        <label key={clave}>
          <span className={etiqueta}>{titulo}{obligatorio ? " *" : ""}</span>
          <input
            className={`${campo} ${errores[clave] ? campoConError : ""}`}
            type={tipo}
            inputMode={clave === "ruc" ? "numeric" : undefined}
            maxLength={maximo}
            placeholder={ayuda}
            value={datos[clave]}
            onChange={(e) => cambiar(clave, e.target.value)}
            aria-invalid={Boolean(errores[clave])}
            aria-describedby={errores[clave] ? `error-${clave}` : undefined}
          />
          {errores[clave] && <span id={`error-${clave}`} className="mt-1 block text-sm text-red-600 dark:text-red-300">{errores[clave]}</span>}
        </label>
      ))}
    </div>
    <div className="flex gap-3">
      <button className={boton} disabled={ocupado}>{ocupado ? "Guardando..." : "GUARDAR"}</button>
      <button type="button" className="rounded-xl border border-gray-300 px-4 py-2 font-semibold dark:border-white/20" onClick={onCancelar} disabled={ocupado}>CANCELAR</button>
    </div>
  </form>;
}
