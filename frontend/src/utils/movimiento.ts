/** Solo desplazamientos solicitados por la interfaz; la rueda y el touch son nativos. */
export function desplazarHastaElemento(
  elemento: Element | null,
  opciones: Omit<ScrollIntoViewOptions, "behavior"> = {},
): void {
  elemento?.scrollIntoView?.({
    ...opciones,
    behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
  });
}
