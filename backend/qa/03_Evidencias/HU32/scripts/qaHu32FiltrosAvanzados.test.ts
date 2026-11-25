// QA HU32 (PP-435) · Creado por Elliot_QA | Aseguramiento de Calidad
import { test } from "node:test";
import assert from "node:assert/strict";
import { validarCondiciones, serializarCondiciones, describirCondicion, parametrosConRango, type ParametroFiltro } from "../src/services/filtrosAvanzados.ts";

const temp: ParametroFiltro = { id_prmtr: 1, nmbr: "Temperatura", undd: "°C", fuentes: [{ dispositivo_id: 10, ubicacion_id: 100, admite_rango: true }] };
const nivel: ParametroFiltro = { id_prmtr: 2, nmbr: "Nivel", undd: "m", fuentes: [{ dispositivo_id: 10, ubicacion_id: 100, admite_rango: true }] };
const mixto: ParametroFiltro = { id_prmtr: 3, nmbr: "Bomba", undd: "", fuentes: [{ dispositivo_id: 10, ubicacion_id: 100, admite_rango: true }, { dispositivo_id: 11, ubicacion_id: 100, admite_rango: false }] };
const c = (minimo: string, maximo: string, modo: "dentro" | "fuera" = "dentro", parametro_id = 1) => ({ parametro_id, minimo, maximo, modo });

test("CP-496 acepta decimales, negativos, cero y coma decimal", () => {
  for (const [mi, ma] of [["-5.25", "0"], ["0", "0"], ["1,5", "2"], ["", "-3"], [".5", ""], ["+1", "2"]]) {
    assert.equal(validarCondiciones([c(mi, ma)], [temp]), null, `${mi}..${ma}`);
  }
  assert.deepEqual(serializarCondiciones([c("1,5", " ")])[0], { parametro_id: 1, minimo: "1.5", maximo: null, modo: "dentro" });
});

test("CP-497 rechaza no numéricos, vacíos, min>max y duplicados indicando el parámetro", () => {
  assert.match(validarCondiciones([c("abc", "")], [temp])!, /Temperatura: introduce límites decimales válidos/);
  assert.match(validarCondiciones([c("1e3", "")], [temp])!, /decimales válidos/);
  assert.match(validarCondiciones([c("", "")], [temp])!, /Temperatura: introduce un mínimo, un máximo o ambos/);
  assert.match(validarCondiciones([c("10", "5")], [temp])!, /mínimo no puede ser mayor/);
  assert.match(validarCondiciones([c("1", ""), c("2", "")], [temp])!, /una condición por parámetro/);
});

test("CP-497 coma de miles: '1,000,5' se rechaza", () => {
  assert.notEqual(validarCondiciones([c("1,000,5", "")], [temp]), null);
});

test("CP-497 precisión: el cliente deja pasar lo que el backend rechaza (OBS)", () => {
  // Number(0.30000000000000001) === 0.3 → el cliente no detecta min>max; el backend sí (422).
  assert.equal(validarCondiciones([c("0.30000000000000001", "0.3")], [temp]), null);
});

test("CP-495 solo ofrece parámetros con todas sus fuentes numéricas en la selección", () => {
  assert.deepEqual(parametrosConRango([temp, nivel, mixto], [], [], []).map(p => p.id_prmtr), [1, 2]);
  assert.deepEqual(parametrosConRango([temp, nivel, mixto], [], [10], []).map(p => p.id_prmtr), [1, 2, 3]);
  assert.deepEqual(parametrosConRango([temp, nivel], [], [], [2]).map(p => p.id_prmtr), [2]);
  assert.deepEqual(parametrosConRango([temp], [999], [], []), []);
});

test("CP-501 el resumen muestra límites y unidad del parámetro propio", () => {
  assert.equal(describirCondicion(c("-5", "10"), [temp, nivel]), "Temperatura: ≥ -5 °C y ≤ 10 °C");
  assert.equal(describirCondicion(c("0", "2", "fuera", 2), [temp, nivel]), "Nivel: < 0 m o > 2 m");
  assert.equal(describirCondicion(c("", "0", "fuera"), [temp]), "Temperatura: > 0 °C");
});
