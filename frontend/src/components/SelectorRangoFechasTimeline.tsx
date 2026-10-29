import { useCallback, useEffect, useImperativeHandle, useRef, useState, type Ref } from "react";
import type { RangoFechas } from "../utils/fechas";
import type { CambioRangoGrafico } from "../pages/actualizacionGraficos";

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
  return { inicio: inicio.toISOString(), fin: fin.toISOString() };
}

interface Props {
  controlRef?: Ref<ControlTimeline>;
  zonaHoraria: string;
  onCambiarRango: (rango: RangoFechas, cambio: CambioRangoGrafico) => void;
}

export interface ControlTimeline {
  actualizar: () => void;
}

export default function SelectorRangoFechasTimeline({ zonaHoraria, onCambiarRango, controlRef }: Props) {
  const [rangoRapido, setRangoRapido] = useState<RangoRapido>("7d");
  const [siguiendoAhora, setSiguiendoAhora] = useState(true);
  const [rango, setRango] = useState<RangoFechas>(() => calcularRango("7d"));
  const [arrastrando, setArrastrando] = useState<"inicio" | "fin" | null>(null);
  const [dominioFin, setDominioFin] = useState(() => Date.now());
  const trackRef = useRef<HTMLDivElement>(null);
  const rangoRef = useRef(rango);
  const inicioFijo = useRef(false);
  const inicioDelArrastre = useRef({ rango, siguiendoAhora: true });
  const huboMovimiento = useRef(false);

  const publicar = useCallback((nuevo: RangoFechas, motivo: CambioRangoGrafico["motivo"]) => {
    rangoRef.current = nuevo;
    setRango(nuevo);
    onCambiarRango(nuevo, { motivo });
  }, [onCambiarRango]);

  useEffect(() => {
    onCambiarRango(rangoRef.current, { motivo: "seleccion" });
  }, [onCambiarRango]);

  const refrescar = useCallback(() => {
    const nuevo = siguiendoAhora
      ? { inicio: inicioFijo.current ? rangoRef.current.inicio : calcularRango(rangoRapido).inicio, fin: new Date().toISOString() }
      : { ...rangoRef.current };
    if (siguiendoAhora) setDominioFin(Date.parse(nuevo.fin));
    publicar(nuevo, "refresco");
  }, [siguiendoAhora, rangoRapido, publicar]);

  useImperativeHandle(controlRef, () => ({ actualizar: refrescar }), [refrescar]);

  useEffect(() => {
    if (!siguiendoAhora || arrastrando) return;
    const alVolver = () => { if (document.visibilityState === "visible") refrescar(); };
    const id = setInterval(() => { if (document.visibilityState === "visible") refrescar(); }, INTERVALO_AUTOACTUALIZACION_MS);
    document.addEventListener("visibilitychange", alVolver);
    window.addEventListener("online", alVolver);
    return () => {
      clearInterval(id);
      document.removeEventListener("visibilitychange", alVolver);
      window.removeEventListener("online", alVolver);
    };
  }, [siguiendoAhora, arrastrando, refrescar]);

  const aplicarRangoRapido = (r: RangoRapido) => {
    setRangoRapido(r);
    setSiguiendoAhora(true);
    inicioFijo.current = false;
    const nuevo = calcularRango(r);
    setDominioFin(Date.parse(nuevo.fin));
    publicar(nuevo, "seleccion");
  };

  const dominioInicio = dominioFin - SPANS_MS[rangoRapido];
  const dominioSpan = dominioFin - dominioInicio || 1;
  const inicioMs = new Date(rango.inicio).getTime();
  const finMs = new Date(rango.fin).getTime();
  const porcentajeDe = (t: number) => ((Math.min(Math.max(t, dominioInicio), dominioFin) - dominioInicio) / dominioSpan) * 100;

  useEffect(() => {
    if (!arrastrando) return;
    const onMove = (e: PointerEvent) => {
      const rect = trackRef.current?.getBoundingClientRect();
      if (!rect?.width) return;
      const fraccion = Math.min(Math.max((e.clientX - rect.left) / rect.width, 0), 1);
      const t = dominioInicio + fraccion * dominioSpan;
      const actual = rangoRef.current;
      const nuevo = arrastrando === "inicio"
        ? { inicio: new Date(Math.min(t, Date.parse(actual.fin))).toISOString(), fin: actual.fin }
        : { inicio: actual.inicio, fin: new Date(Math.max(t, Date.parse(actual.inicio))).toISOString() };
      huboMovimiento.current ||= nuevo.inicio !== actual.inicio || nuevo.fin !== actual.fin;
      // La referencia se escribe antes de pointerup, incluso si React aún no pintó el último movimiento.
      rangoRef.current = nuevo;
      setRango(nuevo);
    };
    const onUp = () => {
      setArrastrando(null);
      if (!huboMovimiento.current) return;
      inicioFijo.current = true;
      const seguir = arrastrando === "inicio" ? inicioDelArrastre.current.siguiendoAhora : Date.parse(rangoRef.current.fin) >= dominioFin - 1;
      setSiguiendoAhora(seguir);
      const nuevo = seguir ? { ...rangoRef.current, fin: new Date().toISOString() } : rangoRef.current;
      if (seguir) setDominioFin(Date.parse(nuevo.fin));
      publicar(nuevo, "seleccion");
    };
    const onCancel = () => {
      rangoRef.current = inicioDelArrastre.current.rango;
      setRango(rangoRef.current);
      setArrastrando(null);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    return () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
    };
  }, [arrastrando, dominioInicio, dominioSpan, dominioFin, publicar]);

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
          // La manija en sí queda siempre centrada exacto en `left: p%`
          // (vía el -translate-x-1/2 del contenedor, como antes: su
          // posición tiene que ser precisa). Solo la ETIQUETA de texto se
          // desplaza aparte: centrada por defecto, pero cerca de cada
          // extremo del track (0% o 100%) eso la saca del contenedor -la
          // mitad queda cortada por la izquierda o casi se sale por la
          // derecha-, así que ahí se corre hacia el lado de ADENTRO en vez
          // de quedar centrada, igual que el tooltip del gráfico.
          const ancladoIzquierda = p < 8;
          const ancladoDerecha = p > 92;
          return (
            <div key={cual} className="absolute top-0 h-full z-10" style={{ left: `${p}%` }}>
              {/* La etiqueta NO cuelga del mismo contenedor centrado de la
                  manija -ese contenedor es angosto (se ajusta al ancho del
                  handle) y aunque se "ancle" dentro de él, sigue quedando
                  fuera del TRACK cuando p está cerca de 0% o 100%-. Por
                  eso se posiciona aparte, anclada al track completo (este
                  div, con `left: p%` pero sin -translate-x-1/2), y solo se
                  centra sobre la manija en la zona media; cerca de cada
                  borde se pega hacia adentro para no salirse del track. */}
              <span
                className="absolute -top-7 whitespace-nowrap rounded bg-[#ccff00] text-gray-900 text-[10px] font-bold px-1.5 py-0.5 shadow"
                style={{
                  left: ancladoIzquierda ? 0 : ancladoDerecha ? undefined : "50%",
                  right: ancladoDerecha ? 0 : undefined,
                  transform: ancladoIzquierda || ancladoDerecha ? undefined : "translateX(-50%)",
                }}
              >
                {formatearEtiquetaHandle(new Date(t), zonaHoraria)}
              </span>
              <div
                role="slider" tabIndex={0} aria-label={cual === "inicio" ? "Fecha de inicio" : "Fecha de fin"}
                aria-valuemin={dominioInicio} aria-valuemax={dominioFin} aria-valuenow={t}
                aria-valuetext={formatearEtiquetaHandle(new Date(t), zonaHoraria)}
                onKeyDown={e => {
                  if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
                  e.preventDefault();
                  const paso = Math.max(60_000, dominioSpan / 100);
                  const destino = e.key === "Home" ? dominioInicio : e.key === "End" ? dominioFin : t + (e.key === "ArrowRight" ? paso : -paso);
                  const valor = Math.min(dominioFin, Math.max(dominioInicio, destino));
                  const seguir = cual === "fin" && valor >= dominioFin - 1;
                  const nuevo = cual === "inicio" ? { inicio: new Date(Math.min(valor, finMs)).toISOString(), fin: rango.fin }
                    : { inicio: rango.inicio, fin: seguir ? new Date().toISOString() : new Date(Math.max(valor, inicioMs)).toISOString() };
                  inicioFijo.current = true;
                  if (cual === "fin") setSiguiendoAhora(seguir);
                  if (seguir) setDominioFin(Date.parse(nuevo.fin));
                  publicar(nuevo, "seleccion");
                }}
                onPointerDown={(e) => {
                  e.preventDefault();
                  inicioDelArrastre.current = { rango: rangoRef.current, siguiendoAhora };
                  huboMovimiento.current = false;
                  setArrastrando(cual);
                }}
                className="w-2 h-full -translate-x-1/2 bg-gray-700 dark:bg-white rounded cursor-ew-resize"
              />
            </div>
          );
        })}
      </div>

      <div className="flex items-center justify-between mt-3 flex-wrap gap-3">
        <div className="flex items-center gap-1.5 text-xs text-gray-500 dark:text-gray-400">
          🌐 {zonaHoraria}
          <span className="ml-2">{siguiendoAhora ? "Actualización cada 60 s" : "Rango fijo"}</span>
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
          onClick={refrescar}
          disabled={arrastrando !== null}
          className="text-xs font-bold text-blue-600 dark:text-blue-400 hover:underline"
        >
          Actualizar datos
        </button>
      </div>
    </div>
  );
}
