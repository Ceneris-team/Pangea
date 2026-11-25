export interface FuenteParametro {
  dispositivo_id: number;
  ubicacion_id: number;
  admite_rango: boolean;
}

export interface ParametroFiltro {
  id_prmtr: number;
  nmbr: string;
  undd: string;
  tipo_dato?: string;
  fuentes?: FuenteParametro[];
}

export interface CondicionBorrador {
  parametro_id: number;
  minimo: string;
  maximo: string;
  modo: "dentro" | "fuera";
}

export interface CondicionParametro {
  parametro_id: number;
  minimo: string | null;
  maximo: string | null;
  modo: "dentro" | "fuera";
}

export function parametrosConRango(parametros: ParametroFiltro[], proyectos: number[], equipos: number[], seleccion: number[]) {
  return parametros.filter(p => {
    const fuentes = p.fuentes?.filter(f => (!proyectos.length || proyectos.includes(f.ubicacion_id)) && (!equipos.length || equipos.includes(f.dispositivo_id))) ?? [];
    return (!seleccion.length || seleccion.includes(p.id_prmtr)) && fuentes.length > 0 && fuentes.every(f => f.admite_rango);
  });
}

export function serializarCondiciones(condiciones: CondicionBorrador[]): CondicionParametro[] {
  return condiciones.map(c => ({ ...c, minimo: c.minimo.trim().replace(",", ".") || null, maximo: c.maximo.trim().replace(",", ".") || null }));
}

export function validarCondiciones(condiciones: CondicionBorrador[], disponibles: ParametroFiltro[]): string | null {
  if (condiciones.length > 100) return "Se admiten hasta 100 condiciones por consulta.";
  if (new Set(condiciones.map(c => c.parametro_id)).size !== condiciones.length) return "Solo se admite una condición por parámetro.";
  for (const condicion of serializarCondiciones(condiciones)) {
    const parametro = disponibles.find(p => p.id_prmtr === condicion.parametro_id);
    if (!parametro) return "Hay una condición que no corresponde a los parámetros numéricos de los proyectos y equipos seleccionados. Quítala o revisa la selección.";
    if (condicion.minimo === null && condicion.maximo === null) return `${parametro.nmbr}: introduce un mínimo, un máximo o ambos.`;
    for (const valor of [condicion.minimo, condicion.maximo]) {
      if (valor !== null && (!/^[+-]?(?:\d+(?:\.\d*)?|\.\d+)$/.test(valor) || !Number.isFinite(Number(valor)))) return `${parametro.nmbr}: introduce límites decimales válidos.`;
    }
    if (condicion.minimo !== null && condicion.maximo !== null && Number(condicion.minimo) > Number(condicion.maximo)) return `${parametro.nmbr}: el mínimo no puede ser mayor que el máximo.`;
  }
  return null;
}

export function describirCondicion(condicion: CondicionBorrador, parametros: ParametroFiltro[]) {
  const p = parametros.find(p => p.id_prmtr === condicion.parametro_id);
  const unidad = p?.undd ? ` ${p.undd}` : "";
  const limites = [condicion.minimo !== "" ? `${condicion.modo === "dentro" ? "≥" : "<"} ${condicion.minimo}${unidad}` : "", condicion.maximo !== "" ? `${condicion.modo === "dentro" ? "≤" : ">"} ${condicion.maximo}${unidad}` : ""].filter(Boolean);
  return `${p?.nmbr ?? "Parámetro"}: ${limites.join(condicion.modo === "dentro" ? " y " : " o ")}`;
}
