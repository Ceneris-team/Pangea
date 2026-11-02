import assert from "node:assert/strict";
import test from "node:test";
import {
  RANGOS_VENCIMIENTO,
  diasRestantesTexto,
  esRango,
  inicioRenovacion,
} from "../src/components/comercial/vencimientos.ts";

test("el filtro ofrece todos, vencidos, vencen hoy, próximos 7 y próximos 30 días", () => {
  assert.deepEqual(RANGOS_VENCIMIENTO.map((r) => r.texto), ["Todos", "Vencidos", "Vencen hoy", "Próximos 7 días", "Próximos 30 días"]);
  assert.deepEqual(RANGOS_VENCIMIENTO.map((r) => r.valor), ["todos", "vencidos", "hoy", "7", "30"]);
});

test("solo los valores de la lista son rangos válidos", () => {
  assert.equal(esRango("7"), true);
  assert.equal(esRango("15"), false);
  assert.equal(esRango(null), false);
});

test("los días restantes se leen en palabras", () => {
  assert.equal(diasRestantesTexto(0), "Vence hoy");
  assert.equal(diasRestantesTexto(1), "1 día");
  assert.equal(diasRestantesTexto(12), "12 días");
  assert.equal(diasRestantesTexto(-1), "Venció hace 1 día");
  assert.equal(diasRestantesTexto(-5), "Venció hace 5 días");
});

test("renovar antes del vencimiento empieza al día siguiente; vencido, empieza hoy", () => {
  const hoy = "2026-11-02";
  assert.equal(inicioRenovacion("2026-11-20", hoy), "2026-11-21");
  assert.equal(inicioRenovacion("2026-11-30", hoy), "2026-12-01");
  assert.equal(inicioRenovacion("2026-11-02", hoy), "2026-11-03"); // vence hoy
  assert.equal(inicioRenovacion("2026-11-01", hoy), "2026-11-02"); // venció ayer
  assert.equal(inicioRenovacion("2026-10-01", hoy), hoy);
});
