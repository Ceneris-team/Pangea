/** Orden visual que se envía completo al servidor después de un arrastre. */
export function reordenarWidgets<T extends { id_wdgt: number }>(
  widgets: T[], origen: number, destino: number,
): T[] {
  const desde = widgets.findIndex((widget) => widget.id_wdgt === origen);
  const hasta = widgets.findIndex((widget) => widget.id_wdgt === destino);
  if (desde < 0 || hasta < 0 || desde === hasta) return widgets;
  const orden = [...widgets];
  const [movido] = orden.splice(desde, 1);
  orden.splice(hasta, 0, movido);
  return orden;
}
