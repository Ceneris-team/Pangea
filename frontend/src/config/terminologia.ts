/** Vocabulario visible; los nombres de campos de la API conservan compatibilidad. */
export function textoDeProyectos(texto: string): string {
  return texto
    .replace(/Todas las ubicaciones/g, "Todos los proyectos")
    .replace(/todas las ubicaciones/g, "todos los proyectos")
    .replace(/Las ubicaciones/g, "Los proyectos")
    .replace(/las ubicaciones/g, "los proyectos")
    .replace(/una ubicación/g, "un proyecto")
    .replace(/Una ubicación/g, "Un proyecto")
    .replace(/de la ubicación/g, "del proyecto")
    .replace(/a la ubicación/g, "al proyecto")
    .replace(/la ubicación/g, "el proyecto")
    .replace(/La ubicación/g, "El proyecto")
    .replace(/Ubicaciones/g, "Proyectos")
    .replace(/ubicaciones/g, "proyectos")
    .replace(/Ubicación/g, "Proyecto")
    .replace(/ubicación/g, "proyecto")
    .replace(/proyectos asignadas/g, "proyectos asignados")
    .replace(/proyectos activas/g, "proyectos activos")
    .replace(/Proyecto actualizada/g, "Proyecto actualizado")
    .replace(/Proyecto registrada/g, "Proyecto registrado");
}

export function estadoProyecto(estado: string): string {
  return estado === "Activa" ? "Activo" : estado === "Inactiva" ? "Inactivo" : estado;
}
