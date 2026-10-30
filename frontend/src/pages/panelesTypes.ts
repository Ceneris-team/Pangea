export interface PanelDetalle {
  id_pnl: number;
  nmbr: string;
  fch_crcn: string;
  vsbldd: "Privado" | "Empresa";
  es_propietario: boolean;
}

export interface UbicacionDisponible { id_ubccn: number; nmbr: string }

export interface UltimoValor {
  id_dspstv: number;
  id_prmtr: number;
  parametro: string;
  unidad: string;
  dispositivo_nombre: string;
  valor: number | string;
  fch_hr: string | null;
}

export interface UbicacionPanel extends UbicacionDisponible {
  dscrpcn: string | null;
  lttd: number;
  lngtd: number;
  estd: string;
  semaforo: string;
  ultima_lectura: string | null;
  ultimos_valores: UltimoValor[];
}

export interface DispositivoPanel { id_dspstv: number; id_ubccn: number; nmbr: string; estd: string; ultima_ingesta: { estado: string; fecha: string } | null }

export interface ContenidoPanel<TWidget> {
  proyecto_activo: UbicacionDisponible | null;
  ubicaciones: UbicacionPanel[];
  dispositivos: DispositivoPanel[];
  widgets: TWidget[];
}

export type EstadoLectura = "reciente" | "atrasada" | "sin_datos";

/** El umbral es una preferencia visual; no declara que el dispositivo esté averiado. */
export function estadoLectura(fecha: string | null, umbralHoras: number, ahora = Date.now()): EstadoLectura {
  if (!fecha) return "sin_datos";
  const tiempo = Date.parse(fecha);
  if (!Number.isFinite(tiempo)) return "sin_datos";
  return ahora - tiempo > umbralHoras * 60 * 60 * 1000 ? "atrasada" : "reciente";
}

export function resumenLecturas(ubicaciones: UbicacionPanel[], umbralHoras: number, ahora = Date.now()) {
  const conteos = { total: ubicaciones.length, reciente: 0, atrasada: 0, sin_datos: 0 };
  for (const ubicacion of ubicaciones) conteos[estadoLectura(ubicacion.ultima_lectura, umbralHoras, ahora)]++;
  return conteos;
}
