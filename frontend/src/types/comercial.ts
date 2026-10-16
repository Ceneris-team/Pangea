export type Limites = { ubicaciones: number; dispositivos: number; usuarios: number };
export type Condiciones = {
  plan_nombre: string; revision_plan: number; moneda: string; periodicidad: string;
  precio_acordado: string; referencia: string | null; motivo: string; dias_gracia: number;
  es_prueba: boolean; limites: Limites; funcionalidades: string[]; importe_servicios: string;
  complementos: { id: number; nombre: string; cantidad: number; tipo: string }[];
};
export type Plan = {
  id_pln: number; nombre: string; descripcion: string | null; precio_mensual: string;
  moneda: string; revision: number; estado: string; limites: Limites | null; funcionalidades: string[];
};
export type Cliente = {
  id_clnt: number; nombre: string; ruc: string; plan_id: number | null; plan_nombre: string | null;
  suscripcion_id: number | null; estado_suscripcion: string; fecha_inicio: string | null;
  fecha_vencimiento: string | null; consumo: Limites; limites: Limites | null;
  condiciones: Condiciones | null; aviso_vencimiento: boolean;
  programada: { id: number; fecha_inicio: string; fecha_vencimiento: string; condiciones: Condiciones } | null;
};
export type Catalogo = {
  funcionalidades: { codigo: string; nombre: string; disponible: boolean }[];
  complementos: { id: number; nombre: string; tipo: string; precio: string; moneda: string;
    cupos: Limites; funcionalidades: string[]; activo: boolean }[];
};
export function fechaLima() {
  return new Intl.DateTimeFormat("en-CA", { timeZone: "America/Lima", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date());
}
export function sumarDias(fecha: string, dias: number) {
  const date = new Date(fecha + "T12:00:00Z");
  date.setUTCDate(date.getUTCDate() + dias);
  return date.toISOString().slice(0, 10);
}
export const nombresRecursos = { ubicaciones: "Proyectos", dispositivos: "Dispositivos", usuarios: "Usuarios" };
