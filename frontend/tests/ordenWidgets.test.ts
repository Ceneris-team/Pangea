import assert from "node:assert/strict";
import test from "node:test";
import { reordenarWidgets } from "../src/pages/ordenWidgets.ts";

test("mover un widget conserva los demás y envía el orden completo", () => {
  const widgets = [1, 2, 3, 4].map((id_wdgt) => ({ id_wdgt }));
  const orden = reordenarWidgets(widgets, 4, 2);

  assert.deepEqual(orden.map((w) => w.id_wdgt), [1, 4, 2, 3]);
  assert.deepEqual(widgets.map((w) => w.id_wdgt), [1, 2, 3, 4]);
});

test("soltar fuera del panel no modifica el orden", () => {
  const widgets = [{ id_wdgt: 1 }, { id_wdgt: 2 }];
  assert.equal(reordenarWidgets(widgets, 1, 99), widgets);
});
