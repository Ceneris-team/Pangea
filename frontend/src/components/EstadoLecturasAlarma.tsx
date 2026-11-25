import { useAuth } from "../hooks/useAuth";
import { formatearFechaHoraEnZona } from "../utils/fechas";

export interface EstadoDispositivoAlarma {
  id_dspstv: number;
  nombre: string;
  en_alarma: boolean;
  desde: string | null;
  ultima_evaluacion: string | null;
  pendiente_evaluacion: boolean;
}

export default function EstadoLecturasAlarma({ regla, dispositivos = [] }: {
  regla: string;
  dispositivos?: EstadoDispositivoAlarma[];
}) {
  const { zonaHoraria } = useAuth();
  if (regla !== "Activa") return <span className="text-gray-500 dark:text-gray-400">Evaluación pausada</span>;
  const activas = dispositivos.filter(d => d.en_alarma && !d.pendiente_evaluacion);
  const pendientes = dispositivos.filter(d => d.pendiente_evaluacion);
  const etiqueta = activas.length ? `${activas.length} ${activas.length === 1 ? "equipo en alarma" : "equipos en alarma"}`
    : !dispositivos.length || pendientes.length === dispositivos.length ? "Pendiente de lectura"
    : "Normal en última lectura";
  return <div className="min-w-40 text-sm">
    <p className={activas.length ? "font-semibold text-red-700 dark:text-red-300" : "text-gray-700 dark:text-gray-200"}>{etiqueta}</p>
    {dispositivos.length > 0 && <details className="mt-1">
      <summary className="cursor-pointer text-xs underline">Ver equipos y fechas</summary>
      <ul className="mt-2 space-y-2">{dispositivos.map(d => <li key={d.id_dspstv}>
        <p className="font-medium">{d.nombre}: {d.pendiente_evaluacion ? "pendiente de evaluar la regla" : d.en_alarma ? "en alarma" : "normal"}</p>
        {!d.pendiente_evaluacion && d.en_alarma && <p className="text-xs">{d.desde ? `Desde ${formatearFechaHoraEnZona(d.desde, zonaHoraria)}` : "Fecha de inicio no disponible"}</p>}
        <p className="text-xs text-gray-500 dark:text-gray-400">{d.ultima_evaluacion ? `Última evaluación: ${formatearFechaHoraEnZona(d.ultima_evaluacion, zonaHoraria)}` : "Aún no se han evaluado lecturas de este equipo"}</p>
      </li>)}</ul>
    </details>}
    {pendientes.length > 0 && pendientes.length < dispositivos.length && <p className="text-xs text-amber-700 dark:text-amber-300">{pendientes.length} pendientes de reevaluar</p>}
  </div>;
}
