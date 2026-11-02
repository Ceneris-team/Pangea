import assert from "node:assert/strict";
import test from "node:test";
import {
  CLIENTE_VACIO,
  MSG_CORREO,
  MSG_RAZON_SOCIAL,
  MSG_RUC,
  MSG_TELEFONO,
  cuerpoCliente,
  validarCliente,
} from "../src/components/comercial/registroCliente.ts";

const valido = {
  razon_social: "Minera Andina S.A.C.",
  ruc: "20123456789",
  correo_contacto: "contacto@mineraandina.pe",
  telefono_contacto: "+51 999 888 777",
};

test("datos válidos no tienen errores, con o sin teléfono", () => {
  assert.deepEqual(validarCliente(valido), {});
  assert.deepEqual(validarCliente({ ...valido, telefono_contacto: "" }), {});
});

test("el formulario vacío marca los tres obligatorios y no el teléfono", () => {
  assert.deepEqual(validarCliente(CLIENTE_VACIO), {
    razon_social: MSG_RAZON_SOCIAL,
    ruc: MSG_RUC,
    correo_contacto: MSG_CORREO,
  });
});

test("el RUC debe tener exactamente 11 dígitos numéricos", () => {
  for (const ruc of ["2012345678", "201234567890", "20A23456789", "20 12345678"]) {
    assert.equal(validarCliente({ ...valido, ruc }).ruc, MSG_RUC, ruc);
  }
  assert.equal(validarCliente({ ...valido, ruc: " 20123456789 " }).ruc, undefined);
});

test("el correo debe tener formato usuario@dominio.com", () => {
  for (const correo of ["contacto", "contacto@", "@minera.pe", "contacto@minera", "a b@minera.pe", "contacto@minera..pe"]) {
    assert.equal(validarCliente({ ...valido, correo_contacto: correo }).correo_contacto, MSG_CORREO, correo);
  }
});

test("el teléfono solo admite números, espacios, + y -", () => {
  for (const telefono of ["abc", "999-ABC", "+- ", "1".repeat(21)]) {
    assert.equal(validarCliente({ ...valido, telefono_contacto: telefono }).telefono_contacto, MSG_TELEFONO, telefono);
  }
  assert.equal(validarCliente({ ...valido, telefono_contacto: "01-555-1234" }).telefono_contacto, undefined);
});

test("el cuerpo para la API recorta espacios y manda el teléfono vacío como null", () => {
  assert.deepEqual(cuerpoCliente({ ...valido, razon_social: "  Minera  ", telefono_contacto: "  " }), {
    razon_social: "Minera",
    ruc: "20123456789",
    correo_contacto: "contacto@mineraandina.pe",
    telefono_contacto: null,
  });
});
