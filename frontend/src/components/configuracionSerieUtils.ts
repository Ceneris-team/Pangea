export type Significado = "continuo" | "contador" | "secuencia" | "estado" | "desconocido";
export type VistaSerie = "linea" | "area" | "kpi" | "barras" | "escalon";
export interface ConfigSerie {
  significado: Significado;
  vista: VistaSerie;
  reinicio: "desconocido" | "cero" | "modulo";
  modulo: number | null;
  confirmada: boolean;
}
export const VISTAS_SERIE: Record<Significado, VistaSerie[]> = {
  continuo: ["linea", "area", "kpi"], contador: ["kpi", "barras", "escalon"],
  secuencia: ["kpi", "barras", "escalon"], estado: ["escalon", "kpi", "barras"],
  desconocido: ["linea", "kpi"],
};
export const NOMBRES_VISTA: Record<VistaSerie, string> = {
  linea: "Línea", area: "Área", kpi: "KPI", barras: "Barras", escalon: "Escalonado",
};
export const CONFIG_VACIA: ConfigSerie = {
  significado: "desconocido", vista: "linea", reinicio: "desconocido", modulo: null, confirmada: false,
};
