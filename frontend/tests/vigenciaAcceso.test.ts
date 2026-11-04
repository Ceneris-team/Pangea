import test from "node:test";
import assert from "node:assert/strict";
import { guardarVersionAcceso, leerVersionAcceso } from "../src/services/vigenciaAcceso.ts";

function storage() {
  const datos = new Map<string, string>();
  return {
    getItem: (key: string) => datos.get(key) ?? null,
    setItem: (key: string, valor: string) => { datos.set(key, valor); },
    removeItem: (key: string) => { datos.delete(key); },
  };
}

test("la primera lectura tras recargar conserva la versión anterior de la misma cuenta", () => {
  const sesion = storage();
  guardarVersionAcceso(sesion, "lector@test.example", "antes");
  assert.equal(leerVersionAcceso(sesion, "lector@test.example"), "antes");
  guardarVersionAcceso(sesion, "lector@test.example", "revocada");
  assert.equal(leerVersionAcceso(sesion, "lector@test.example"), "revocada");
});

test("cambiar de cuenta descarta la versión de la persona anterior", () => {
  const sesion = storage();
  guardarVersionAcceso(sesion, "anterior@test.example", "antes");
  sesion.setItem("pangea_aviso_acceso", "Aviso de la otra cuenta");
  assert.equal(leerVersionAcceso(sesion, "otra@test.example"), null);
  assert.equal(sesion.getItem("pangea_acceso"), null);
  assert.equal(sesion.getItem("pangea_aviso_acceso"), null);
});

for (const dato of [null, "{inválido", "null", '"texto"', '{"usuario":"lector@test.example","version":7}']) {
  test(`una sesión sin versión válida requiere validar el acceso: ${dato}`, () => {
    const sesion = storage();
    if (dato !== null) sesion.setItem("pangea_acceso", dato);
    assert.equal(leerVersionAcceso(sesion, "lector@test.example"), null);
    assert.equal(sesion.getItem("pangea_acceso"), null);
  });
}
