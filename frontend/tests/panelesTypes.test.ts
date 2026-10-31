import assert from "node:assert/strict";
import test from "node:test";
import { estadoLectura, resumenLecturas, type UbicacionPanel } from "../src/pages/panelesTypes.ts";

const ahora = Date.parse("2026-10-22T12:00:00Z");

test("separa lecturas antiguas de estaciones que nunca enviaron datos", () => {
  assert.equal(estadoLectura("2026-10-22T11:00:00Z", 24, ahora), "reciente");
  assert.equal(estadoLectura("2026-10-20T11:00:00Z", 24, ahora), "atrasada");
  assert.equal(estadoLectura(null, 24, ahora), "sin_datos");
});

test("resumen operativo respeta el umbral elegido", () => {
  const ubicaciones = ["2026-10-22T11:00:00Z", "2026-10-22T03:00:00Z", null]
    .map((ultima_lectura) => ({ ultima_lectura })) as UbicacionPanel[];
  assert.deepEqual(resumenLecturas(ubicaciones, 6, ahora), { total: 3, reciente: 1, atrasada: 1, sin_datos: 1 });
  assert.deepEqual(resumenLecturas(ubicaciones, 24, ahora), { total: 3, reciente: 2, atrasada: 0, sin_datos: 1 });
});
