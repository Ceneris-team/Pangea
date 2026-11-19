import assert from "node:assert/strict";
import test from "node:test";
import {
  MSG_UMBRAL_DECIMALES,
  MSG_UMBRAL_NUMERO,
  MSG_UMBRAL_OBLIGATORIO,
  MSG_UMBRAL_RANGO,
  OPERADORES_ALARMA,
  condicionParaEnviar,
  errorUmbral,
  esOperadorValido,
  formatearUmbral,
  fraseCondicion,
  textoOperador,
} from "../src/pages/condicionAlarma.ts";

test("los cinco operadores del CHECK de cndcn_alrm, con texto legible", () => {
  assert.deepEqual(
    OPERADORES_ALARMA.map((o) => o.valor),
    [">", ">=", "<", "<=", "="],
  );
  assert.equal(textoOperador(">="), "mayor o igual que");
  assert.equal(esOperadorValido("!="), false);
});

test("umbrales válidos, incluidos los límites y la coma decimal", () => {
  for (const valor of ["0", "-12.5", "30", " 7,25 ", "1.2345", ".5", "9999999999.9999", "-9999999999.9999"]) {
    assert.equal(errorUmbral(valor), null, valor);
  }
});

test("umbral obligatorio", () => {
  assert.equal(errorUmbral(""), MSG_UMBRAL_OBLIGATORIO);
  assert.equal(errorUmbral("   "), MSG_UMBRAL_OBLIGATORIO);
});

test("umbral que no es número", () => {
  for (const valor of ["abc", "1e5", "12.3.4", "NaN", "Infinity", "--1", "1,5,0"]) {
    assert.equal(errorUmbral(valor), MSG_UMBRAL_NUMERO, valor);
  }
});

test("umbral con más de 4 decimales o fuera de rango", () => {
  assert.equal(errorUmbral("1.23456"), MSG_UMBRAL_DECIMALES);
  assert.equal(errorUmbral("10000000000"), MSG_UMBRAL_RANGO);
  assert.equal(errorUmbral("-10000000000"), MSG_UMBRAL_RANGO);
});

test("frase de vista previa con parámetro, operador, valor y unidad", () => {
  assert.equal(
    fraseCondicion("Temperatura", ">", "30.50", "°C"),
    "Se activará cuando Temperatura sea mayor que 30.5 °C",
  );
  assert.equal(
    fraseCondicion("pH", "<=", "6,5", ""),
    "Se activará cuando pH sea menor o igual que 6.5",
  );
  assert.equal(fraseCondicion("pH", ">", "", "u"), null);
  assert.equal(fraseCondicion("pH", "!=", "1", "u"), null);
  assert.equal(fraseCondicion("", ">", "1", "u"), null);
});

test("formatear y preparar el cuerpo para el backend", () => {
  assert.equal(formatearUmbral(30.5), "30.5");
  assert.equal(formatearUmbral("3,2500"), "3.25");
  assert.deepEqual(condicionParaEnviar(">=", " 7,25 "), { oprdr: ">=", vlr_umbrl: 7.25 });
});
