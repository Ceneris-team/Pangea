import type { RangoFechas } from "../utils/fechas";

export interface CambioRangoGrafico {
  motivo: "seleccion" | "refresco";
}

/** Una consulta en curso y, como máximo, el último refresco pendiente.
 * Los ticks no descartan respuestas lentas ni acumulan peticiones. Cambiar
 * los filtros o salir de la vista cancela la conexión y sus resultados. */
export function crearActualizadorSerial<S, R>(opciones: {
  ejecutar: (solicitud: S, signal: AbortSignal) => Promise<R>;
  alIniciar?: (solicitud: S) => void;
  alCompletar: (resultado: R, solicitud: S) => void;
  alFallar?: (error: unknown, solicitud: S) => void;
  alTerminar?: () => void;
}) {
  let activo = true;
  let ejecutando = false;
  let pendiente: { solicitud: S } | null = null;
  const controlador = new AbortController();

  async function procesar() {
    ejecutando = true;
    while (activo && pendiente !== null) {
      const { solicitud } = pendiente;
      pendiente = null;
      opciones.alIniciar?.(solicitud);
      try {
        const resultado = await opciones.ejecutar(solicitud, controlador.signal);
        if (activo) opciones.alCompletar(resultado, solicitud);
      } catch (error) {
        if (activo) opciones.alFallar?.(error, solicitud);
      }
    }
    ejecutando = false;
    if (activo) opciones.alTerminar?.();
  }

  return {
    pedir(solicitud: S) {
      if (!activo) return;
      pendiente = { solicitud };
      if (!ejecutando) void procesar();
    },
    cancelar() {
      activo = false;
      pendiente = null;
      controlador.abort();
    },
  };
}

export function acotarZoom(zoom: { min: number; max: number } | null, rango: RangoFechas) {
  if (!zoom) return null;
  const min = Math.max(zoom.min, Date.parse(rango.inicio));
  const max = Math.min(zoom.max, Date.parse(rango.fin));
  return min < max ? { min, max } : null;
}
