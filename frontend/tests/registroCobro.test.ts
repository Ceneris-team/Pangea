import assert from "node:assert/strict";
import test from "node:test";
import {
  METODOS_PAGO,
  MSG_FECHA,
  MSG_FECHA_FUTURA,
  MSG_METODO,
  MSG_MONTO,
  MSG_MONTO_MAXIMO,
  cuerpoCobro,
  montoVisible,
  validarCobro,
} from "../src/components/comercial/registroCobro.ts";

const hoy = "2026-11-02";
const valido = { monto: "350.00", fecha_cobro: hoy, metodo_pago: "Transferencia bancaria" };

test("los métodos de pago de v1.0 son transferencia bancaria, efectivo y cheque", () => {
  assert.deepEqual([...METODOS_PAGO], ["Transferencia bancaria", "Efectivo", "Cheque"]);
});

test("datos válidos no tienen errores", () => {
  assert.deepEqual(validarCobro(valido, hoy), {});
  assert.deepEqual(validarCobro({ ...valido, monto: "350,5", fecha_cobro: "2026-10-01", metodo_pago: "Cheque" }, hoy), {});
});

test("el formulario vacío marca los tres obligatorios", () => {
  assert.deepEqual(validarCobro({ monto: "", fecha_cobro: "", metodo_pago: "" }, hoy), {
    monto: MSG_MONTO, fecha_cobro: MSG_FECHA, metodo_pago: MSG_METODO,
  });
});

test("el monto es un decimal mayor que 0 con hasta 2 decimales", () => {
  for (const monto of ["abc", "0", "0.00", "-5", "10.555", "1e3", "12.3.4"]) {
    assert.equal(validarCobro({ ...valido, monto }, hoy).monto, MSG_MONTO, monto);
  }
  assert.equal(validarCobro({ ...valido, monto: "10000000000" }, hoy).monto, MSG_MONTO_MAXIMO);
  assert.equal(validarCobro({ ...valido, monto: "0.01" }, hoy).monto, undefined);
});

test("la fecha de cobro no puede ser futura", () => {
  assert.equal(validarCobro({ ...valido, fecha_cobro: "2026-11-03" }, hoy).fecha_cobro, MSG_FECHA_FUTURA);
  assert.equal(validarCobro({ ...valido, fecha_cobro: hoy }, hoy).fecha_cobro, undefined);
});

test("solo se aceptan los métodos de la lista", () => {
  assert.equal(validarCobro({ ...valido, metodo_pago: "Tarjeta" }, hoy).metodo_pago, MSG_METODO);
});

test("el cuerpo para la API usa punto decimal", () => {
  assert.deepEqual(cuerpoCobro({ ...valido, monto: " 1250,50 " }), { ...valido, monto: "1250.50" });
});

test("el monto se muestra con separador de miles y 2 decimales", () => {
  assert.equal(montoVisible("1250.5"), "1,250.50");
  assert.equal(montoVisible("350.00"), "350.00");
});
