import assert from "node:assert/strict";
import test from "node:test";
import { ayudaCanalCorreo, estadoCanal } from "../src/components/configNotificaciones.ts";

test("canal activo sin destinatarios avisa que se agregará el correo de la cuenta", () => {
  assert.equal(
    ayudaCanalCorreo(true, 0, "luis@empresa.com"),
    "Activo: al guardar se agregará el correo de tu cuenta (luis@empresa.com) como destinatario.",
  );
});

test("canal activo con destinatarios dice cuántos recibirán el aviso", () => {
  assert.match(ayudaCanalCorreo(true, 1, "x@y.com"), /1 destinatario recibirá/);
  assert.match(ayudaCanalCorreo(true, 3, "x@y.com"), /3 destinatarios recibirán/);
});

test("canal desactivado aclara que los destinatarios se conservan", () => {
  assert.match(ayudaCanalCorreo(false, 2, "x@y.com"), /se conservan, pero no recibirán avisos/);
  assert.match(ayudaCanalCorreo(false, 0, "x@y.com"), /no enviará avisos por correo/);
});

test("estado de cada canal", () => {
  assert.equal(estadoCanal({ canal: "email", nombre: "Correo", disponible: true, activo: true }), "Activo");
  assert.equal(estadoCanal({ canal: "email", nombre: "Correo", disponible: true, activo: false }), "Desactivado");
  assert.equal(
    estadoCanal({ canal: "telegram", nombre: "Telegram", disponible: false, activo: false }),
    "No disponible en esta versión",
  );
});
