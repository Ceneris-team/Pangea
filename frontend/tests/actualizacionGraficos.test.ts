import test from "node:test";
import assert from "node:assert/strict";
import { acotarZoom, crearActualizadorSerial } from "../src/pages/actualizacionGraficos.ts";

function diferido<T>() {
  let resolver!: (valor: T) => void;
  let rechazar!: (error: Error) => void;
  const promesa = new Promise<T>((resolve, reject) => { resolver = resolve; rechazar = reject; });
  return { promesa, resolver, rechazar };
}
const microtareas = () => new Promise<void>(resolve => setImmediate(resolve));

test("una respuesta lenta se publica y los ticks pendientes se reducen al más reciente", async () => {
  const pendientes = [diferido<number>(), diferido<number>()];
  const iniciadas: number[] = [], recibidas: number[] = [];
  const actualizador = crearActualizadorSerial<number, number>({
    ejecutar: solicitud => { iniciadas.push(solicitud); return pendientes[iniciadas.length - 1].promesa; },
    alCompletar: resultado => recibidas.push(resultado),
  });
  actualizador.pedir(1);
  actualizador.pedir(2);
  actualizador.pedir(3);
  assert.deepEqual(iniciadas, [1]);
  pendientes[0].resolver(10);
  await microtareas();
  assert.deepEqual(recibidas, [10]);
  assert.deepEqual(iniciadas, [1, 3]);
  pendientes[1].resolver(30);
  await microtareas();
  assert.deepEqual(recibidas, [10, 30]);
});

test("cambiar de filtros cancela la conexión, la cola y los resultados antiguos", async () => {
  const pendiente = diferido<number>();
  let signal!: AbortSignal;
  const recibidas: number[] = [], iniciadas: number[] = [];
  const actualizador = crearActualizadorSerial<number, number>({
    ejecutar: (solicitud, s) => { signal = s; iniciadas.push(solicitud); return pendiente.promesa; },
    alCompletar: resultado => recibidas.push(resultado),
  });
  actualizador.pedir(1);
  actualizador.pedir(2);
  actualizador.cancelar();
  assert.equal(signal.aborted, true);
  pendiente.resolver(100);
  await microtareas();
  actualizador.pedir(3);
  assert.deepEqual(recibidas, []);
  assert.deepEqual(iniciadas, [1]);
});

test("un error permite procesar el refresco siguiente y terminar el indicador de carga", async () => {
  const pendiente = diferido<number>();
  const recibidas: number[] = [], errores: unknown[] = [];
  let finalizadas = 0;
  const actualizador = crearActualizadorSerial<number, number>({
    ejecutar: solicitud => solicitud === 1 ? pendiente.promesa : Promise.resolve(solicitud),
    alCompletar: resultado => recibidas.push(resultado),
    alFallar: error => errores.push(error),
    alTerminar: () => finalizadas++,
  });
  actualizador.pedir(1);
  actualizador.pedir(2);
  pendiente.rechazar(new Error("Sin conexión"));
  await microtareas();
  assert.equal(errores.length, 1);
  assert.deepEqual(recibidas, [2]);
  assert.equal(finalizadas, 1);
});

test("actualizar manualmente el mismo rango vuelve a consultar", async () => {
  let consultas = 0;
  const actualizador = crearActualizadorSerial<string, number>({
    ejecutar: async () => ++consultas,
    alCompletar: () => {},
  });
  actualizador.pedir("mismo rango");
  await microtareas();
  actualizador.pedir("mismo rango");
  await microtareas();
  assert.equal(consultas, 2);
});

const rango = { inicio: "2026-10-21T00:00:00.000Z", fin: "2026-10-21T01:00:00.000Z" };
test("el zoom se conserva dentro de la ventana móvil", () => {
  const zoom = { min: Date.parse("2026-10-21T00:10:00Z"), max: Date.parse("2026-10-21T00:20:00Z") };
  assert.deepEqual(acotarZoom(zoom, rango), zoom);
});

test("un zoom que sale de la ventana se acota o se restaura al rango completo", () => {
  assert.equal(acotarZoom({ min: 0, max: 1 }, rango), null);
  assert.deepEqual(acotarZoom({ min: 0, max: Date.parse("2026-10-21T00:20:00Z") }, rango), {
    min: Date.parse(rango.inicio), max: Date.parse("2026-10-21T00:20:00Z"),
  });
});
