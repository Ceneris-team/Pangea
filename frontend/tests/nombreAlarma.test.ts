import assert from "node:assert/strict";
import test from "node:test";
import {
  MSG_NOMBRE_FORMATO,
  MSG_NOMBRE_LARGO,
  MSG_NOMBRE_OBLIGATORIO,
  errorNombreAlarma,
} from "../src/pages/nombreAlarma.ts";

test("un nombre de texto con espacios, tildes y puntuación habitual es válido", () => {
  for (const nombre of ["Crecida del río Rímac", "pH alto - Planta 2", "Nivel (m) / caudal", "Alarma_1", "Ñandú 3.5"]) {
    assert.equal(errorNombreAlarma(nombre), null, nombre);
  }
});

test("el nombre es obligatorio", () => {
  assert.equal(errorNombreAlarma(""), MSG_NOMBRE_OBLIGATORIO);
  assert.equal(errorNombreAlarma("   "), MSG_NOMBRE_OBLIGATORIO);
});

test("un nombre solo de símbolos o con símbolos no admitidos se rechaza", () => {
  for (const nombre of ["###", "-inicio con guion", "pH > 7", "alarma@planta", "100%"]) {
    assert.equal(errorNombreAlarma(nombre), MSG_NOMBRE_FORMATO, nombre);
  }
});

test("el nombre admite como máximo 100 caracteres", () => {
  assert.equal(errorNombreAlarma("a".repeat(100)), null);
  assert.equal(errorNombreAlarma("a".repeat(101)), MSG_NOMBRE_LARGO);
});
