import assert from "node:assert/strict";
import test from "node:test";
import { parametrosConRango, serializarCondiciones, validarCondiciones, describirCondicion } from "../src/services/filtrosAvanzados.ts";

const parametros = [
  { id_prmtr: 1, nmbr: "Temperatura", undd: "°C", fuentes: [{ dispositivo_id: 1, ubicacion_id: 1, admite_rango: true }] },
  { id_prmtr: 2, nmbr: "Nivel", undd: "m", fuentes: [{ dispositivo_id: 2, ubicacion_id: 2, admite_rango: true }] },
  { id_prmtr: 3, nmbr: "Estado", undd: "", fuentes: [{ dispositivo_id: 1, ubicacion_id: 1, admite_rango: false }] },
];

test("el contexto ofrece solo parámetros compatibles de los equipos y proyectos elegidos", () => {
  assert.deepEqual(parametrosConRango(parametros, [1], [], []).map(p => p.id_prmtr), [1]);
  assert.deepEqual(parametrosConRango(parametros, [], [2], []).map(p => p.id_prmtr), [2]);
  assert.deepEqual(parametrosConRango(parametros, [], [], [3]), []);
});

test("valida decimales negativos y cero, normaliza coma y conserva extremos vacíos", () => {
  const condiciones = [{ parametro_id: 1, minimo: " -5,25 ", maximo: "0", modo: "dentro" as const }];
  assert.equal(validarCondiciones(condiciones, parametros), null);
  assert.deepEqual(serializarCondiciones(condiciones), [{ parametro_id: 1, minimo: "-5.25", maximo: "0", modo: "dentro" }]);
  assert.equal(serializarCondiciones([{ ...condiciones[0], minimo: "" }])[0].minimo, null);
});

test("rechaza límites invertidos, no numéricos, vacíos y condiciones fuera de contexto", () => {
  for (const cambios of [{ minimo: "2", maximo: "1" }, { minimo: "NaN" }, { maximo: "1.2.3" }, { minimo: "", maximo: "" }, { parametro_id: 9 }]) {
    assert.ok(validarCondiciones([{ parametro_id: 1, minimo: "0", maximo: "10", modo: "dentro", ...cambios }], parametros));
  }
});

test("el resumen conserva unidad y expresa correctamente dentro y fuera del rango", () => {
  assert.equal(describirCondicion({ parametro_id: 1, minimo: "0", maximo: "10", modo: "fuera" }, parametros), "Temperatura: < 0 °C o > 10 °C");
  assert.equal(describirCondicion({ parametro_id: 2, minimo: "0", maximo: "", modo: "dentro" }, parametros), "Nivel: ≥ 0 m");
});

test("compara límites decimales sin perder precisión al convertirlos a Number", () => {
  for (const [minimo, maximo] of [["0.30000000000000001", "0.3"], ["-0.3", "-0.30000000000000001"], ["9007199254740993", "9007199254740992"]]) {
    assert.match(validarCondiciones([{ parametro_id: 1, minimo, maximo, modo: "dentro" }], parametros) ?? "", /mínimo no puede ser mayor/);
  }
  for (const [minimo, maximo] of [["0.3", "0.30000000000000001"], ["-.5000", "-0.5"], ["+.1", "0.100"], ["-0.000", "0"]]) {
    assert.equal(validarCondiciones([{ parametro_id: 1, minimo, maximo, modo: "dentro" }], parametros), null);
  }
});

test("rechaza dígitos no ASCII, notación no admitida y más de 60 caracteres", () => {
  for (const valor of ["٢١", "１２", "1_000", "1e400", "9".repeat(61), "9".repeat(5000)]) {
    for (const campo of ["minimo", "maximo"]) {
      assert.ok(validarCondiciones([{ parametro_id: 1, minimo: "", maximo: "", modo: "dentro", [campo]: valor }], parametros));
    }
  }
});
