import { useEffect, useRef, useState } from "react";
import { aValorDatetimeLocal, type RangoFechas } from "../utils/fechas";

/**
 * HU15: selector de rango de fechas tipo línea de tiempo con dos manijas
 * arrastrables, botones de rango rápido (7 días/30 días/1 año/Todo) y
 * actualización periódica mientras el rango siga apuntando a "ahora".
 * Es un componente aparte de SelectorRangoFechas.tsx (usado por HU12/
 * ConsultaDatos.tsx) para no alterar ese flujo de selección/aplicar.
 */

type RangoRapido = "7d" | "30d" | "1a" | "todo";

const SPANS_MS: Record<RangoRapido, number> = {
  "7d": 7 * 24 * 60 * 60 * 1000,
  "30d": 30 * 24 * 60 * 60 * 1000,
  "1a": 365 * 24 * 60 * 60 * 1000,
  // "Todo": no hay histórico ilimitado en la consulta, se usa una ventana
  // grande fija (2 años) para no disparar consultas sin límite de fecha.
  todo: 2 * 365 * 24 * 60 * 60 * 1000,
};

const ETIQUETAS_RANGO_RAPIDO: Record<RangoRapido, string> = {
  "7d": "7 días",
  "30d": "30 días",
  "1a": "1 año",
  todo: "Todo",
};

const INTERVALO_AUTOACTUALIZACION_MS = 60_000;

function formatearEtiquetaHandle(fecha: Date, zonaHoraria: string): string {
  return fecha.toLocaleString("en-US", {
    timeZone: zonaHoraria,
    month: "short",
    day: "2-digit",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    hour12: true,
  });
}

function calcularRango(rangoRapido: RangoRapido): RangoFechas {
  const fin = new Date();
  const inicio = new Date(fin.getTime() - SPANS_MS[rangoRapido]);
  return { inicio: aValorDatetimeLocal(inicio), fin: aValorDatetimeLocal(fin) };
}

interface Props {
  zonaHoraria: string;
  onCambiarRango: (rango: RangoFechas) => void;
}

export default function SelectorRangoFechasTimeline({ zonaHoraria, onCambiarRango }: Props) {
  const [rangoRapido, setRangoRapido] = useState<RangoRapido>("7d");
  // true mientras el rango activo siga siendo "hasta ahora" (botón rápido
  // sin arrastrar manijas): se recalcula cada 60s para incluir la hora
  // actual (CA5). Arrastrar una manija o editar a mano lo desactiva.
  const [siguiendoAhora, setSiguiendoAhora] = useState(true);
  const [rango, setRango] = useState<RangoFechas>(() => calcularRango("7d"));
  const [arrastrando, setArrastrando] = useState<"inicio" | "fin" | null>(null);

  const trackRef = useRef<HTMLDivElement>(null);
  const rangoRef = useRef(rango);
  useEffect(() => {
    rangoRef.current = rango;
  }, [rango]);

  // Notifica al padre solo en cambios confirmados (rango rápido, edición
  // manual, fin de arrastre, tick de auto-actualización) — nunca en cada
  // pixel movido durante el arrastre, para no disparar un fetch por frame.
  useEffect(() => {
    onCambiarRango(rango);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (!siguiendoAhora) return;
    const id = setInterval(() => {
      const nuevo = calcularRango(rangoRapido);
      setRango(nuevo);
      onCambiarRango(nuevo);
    }, INTERVALO_AUTOACTUALIZACION_MS);
    return () => clearInterval(id);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [siguiendoAhora, rangoRapido]);

  const aplicarRangoRapido = (r: RangoRapido) => {
    setRangoRapido(r);
    setSiguiendoAhora(true);
    const nuevo = calcularRango(r);
    setRango(nuevo);
    onCambiarRango(nuevo);
  };

  const actualizarDatos = () => {
    const nuevo = siguiendoAhora ? calcularRango(rangoRapido) : { ...rangoRef.current };
    setRango(nuevo);
    onCambiarRango(nuevo);
  };

  const dominioFin = new Date().getTime();
  const dominioInicio = dominioFin - SPANS_MS[rangoRapido];
  const dominioSpan = dominioFin - dominioInicio || 1;

  const inicioMs = new Date(rango.inicio).getTime();
  const finMs = new Date(rango.fin).getTime();

  const porcentajeDe = (t: number) => {
    const acotado = Math.min(Math.max(t, dominioInicio), dominioFin);
    return ((acotado - dominioInicio) / dominioSpan) * 100;
  };

  const tiempoDesdeClientX = (clientX: number): number => {
    const el = trackRef.current;
    if (!el) return dominioInicio;
    const rect = el.getBoundingClientRect();
    const frac = Math.min(Math.max((clientX - rect.left) / rect.width, 0), 1);
    return dominioInicio + frac * dominioSpan;
  };

  useEffect(() => {
    if (!arrastrando) return;

    const onMove = (e: PointerEvent) => {
      const t = tiempoDesdeClientX(e.clientX);
      setSiguiendoAhora(false);
      setRango((actual) => {
        const actualInicioMs = new Date(actual.inicio).getTime();
        const actualFinMs = new Date(actual.fin).getTime();
        if (arrastrando === "inicio") {
          return { inicio: aValorDatetimeLocal(new Date(Math.min(t, actualFinMs))), fin: actual.fin };
        }
        return { inicio: actual.inicio, fin: aValorDatetimeLocal(new Date(Math.max(t, actualInicioMs))) };
      });
    };
    const onUp = () => {
      setArrastrando(null);
      onCambiarRango(rangoRef.current);
    };

    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [arrastrando, dominioInicio, dominioSpan]);

  const inicioPct = porcentajeDe(inicioMs);
  const finPct = porcentajeDe(finMs);

  return (
    <div className="w-full">
      <div
        ref={trackRef}
        className="relative w-full h-9 rounded-md bg-black/10 dark:bg-white/10 select-none touch-none"
      >
        <div className="absolute inset-0 flex justify-between pointer-events-none">
          {Array.from({ length: 9 }).map((_, i) => (
            <div key={i} className="w-px h-full bg-black/10 dark:bg-white/15" />
          ))}
        </div>

        <div
          className="absolute top-0 h-full bg-[#ccff00]/70 pointer-events-none"
          style={{ left: `${inicioPct}%`, width: `${Math.max(finPct - inicioPct, 0)}%` }}
        />

        {(["inicio", "fin"] as const).map((cual) => {
          const p = cual === "inicio" ? inicioPct : finPct;
          const t = cual === "inicio" ? inicioMs : finMs;
          return (
            <div
              key={cual}
              className="absolute top-0 h-full -translate-x-1/2 flex flex-col items-center z-10"
              style={{ left: `${p}%` }}
            >
              <span className="mb-1 -mt-7 whitespace-nowrap rounded bg-[#ccff00] text-gray-900 text-[10px] font-bold px-1.5 py-0.5 shadow">
                {formatearEtiquetaHandle(new Date(t), zonaHoraria)}
              </span>
              <div
                onPointerDown={(e) => {
                  e.preventDefault();
                  setArrastrando(cual);
                }}
                className="w-2 h-full bg-gray-700 dark:bg-white rounded cursor-ew-resize"
              />
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between mt-3 flex-wrap gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
          🌐 {zonaHoraria}
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {(Object.keys(ETIQUETAS_RANGO_RAPIDO) as RangoRapido[]).map((r) => (
            <button
              key={r}
              type="button"
              onClick={() => aplicarRangoRapido(r)}
              className={`px-3 py-1.5 rounded-lg text-xs font-bold transition-all ${
                rangoRapido === r
                  ? "bg-blue-600 text-white"
                  : "bg-black/5 dark:bg-white/5 text-gray-600 dark:text-gray-300 hover:bg-black/10 dark:hover:bg-white/10"
              }`}
            >
              {ETIQUETAS_RANGO_RAPIDO[r]}
            </button>
          ))}
        </div>

        <button
          type="button"
          onClick={actualizarDatos}
          className="text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline"
        >
          Actualizar datos
        </button>
      </div>
    </div>
  );
}
