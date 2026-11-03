import assert from "node:assert/strict";
import test from "node:test";
import { MENSAJE_GENERICO, mensajeDeDetalle } from "../src/services/mensajeError.ts";

test("un detail de texto se muestra tal cual", () => {
  assert.equal(mensajeDeDetalle("Ya existe un cliente con ese RUC"), "Ya existe un cliente con ese RUC");
});

test("un 422 de Pydantic muestra el msg sin el prefijo «Value error, » (DEF-02)", () => {
  const detalle = [{
    type: "value_error",
    loc: ["body", "nmbr"],
    msg: "Value error, El nombre de la alarma debe ser texto alfanumérico (se admiten espacios y los signos . , ; : _ ( ) - /)",
    input: "<script>alert(1)</script>",
  }];
  assert.equal(
    mensajeDeDetalle(detalle),
    "El nombre de la alarma debe ser texto alfanumérico (se admiten espacios y los signos . , ; : _ ( ) - /)",
  );
});

test("varios errores se unen sin repetir", () => {
  const detalle = [
    { msg: "Field required", loc: ["body", "id_prmtr"] },
    { msg: "Field required", loc: ["body", "id_ubccn"] },
    { msg: "Value error, El operador debe ser uno de: >, <, >=, <=, =" },
  ];
  assert.equal(mensajeDeDetalle(detalle), "Field required. El operador debe ser uno de: >, <, >=, <=, =");
});

test("sin detail o con una forma desconocida se usa el mensaje genérico", () => {
  for (const detalle of [undefined, null, "", [], [{}], 42, { otro: 1 }]) {
    assert.equal(mensajeDeDetalle(detalle), MENSAJE_GENERICO, JSON.stringify(detalle));
  }
});

test("nunca devuelve «[object Object]»", () => {
  assert.notEqual(mensajeDeDetalle([{ loc: ["body"] }]), "[object Object]");
  assert.notEqual(mensajeDeDetalle({ msg: "Value error, Dato inválido" }), "[object Object]");
  assert.equal(mensajeDeDetalle({ msg: "Value error, Dato inválido" }), "Dato inválido");
});
