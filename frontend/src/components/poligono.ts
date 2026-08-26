import type { PoligonoGeoJSON } from "./MapaDibujoPoligono";

/**
 * Centro de un polígono, para llenar solo el lttd/lngtd de una Ubicación.
 *
 * Por qué existe: el punto de referencia es NOT NULL en ubccn y lo usan
 * HU22 (ancla del panel del mapa) y HU11 (punto por defecto de un
 * dispositivo nuevo), pero pedírselo tecleado al usuario que YA dibujó el
 * contorno es redundante y se presta a error -en la BD hay ubicaciones
 * cuyo centro declarado cae fuera de su propio polígono-. Calculándolo se
 * garantiza que el punto pertenezca a la zona.
 *
 * Usa el centroide del ÁREA (fórmula del polígono), no el promedio de los
 * vértices: el promedio se corre hacia el lado que tenga más vértices
 * juntos, y en un contorno irregular -que es el caso real de una zona
 * minera- puede quedar bastante fuera de lugar.
 */
export function centroideDePoligono(
  poligono: PoligonoGeoJSON | null
): { lat: number; lng: number } | null {
  const anillo = poligono?.coordinates?.[0];
  // Anillo cerrado: 3 vértices reales + el que repite el primero.
  if (!anillo || anillo.length < 4) return null;

  // Se recorre sin el vértice de cierre para no contarlo dos veces.
  const vertices = anillo.slice(0, -1);

  let areaDoble = 0;
  let lng = 0;
  let lat = 0;

  for (let i = 0; i < vertices.length; i++) {
    const [x1, y1] = vertices[i];
    const [x2, y2] = vertices[(i + 1) % vertices.length];
    const cruz = x1 * y2 - x2 * y1;
    areaDoble += cruz;
    lng += (x1 + x2) * cruz;
    lat += (y1 + y2) * cruz;
  }

  // Área cero: los vértices son colineales (o repetidos) y no encierran
  // superficie. El centroide de área no está definido, así que se cae al
  // promedio simple, que para ese caso degenerado es razonable.
  if (areaDoble === 0) {
    const suma = vertices.reduce(
      (acc, [vx, vy]) => ({ lng: acc.lng + vx, lat: acc.lat + vy }),
      { lng: 0, lat: 0 }
    );
    return {
      lat: redondear(suma.lat / vertices.length),
      lng: redondear(suma.lng / vertices.length),
    };
  }

  const factor = 1 / (3 * areaDoble);
  return { lat: redondear(lat * factor), lng: redondear(lng * factor) };
}

/** 6 decimales: la misma precisión que Numeric(9,6) de ubccn.lttd/lngtd. */
function redondear(valor: number): number {
  return Number(valor.toFixed(6));
}
