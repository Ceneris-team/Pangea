import assert from "node:assert/strict";
import test from "node:test";
import {
  MSG_ELEGIR_PLAN,
  MSG_FECHA_INICIO,
  MSG_FECHA_PASADA,
  fechaVisible,
  planSinLimites,
  planesActivos,
  validarAsignacion,
  vencimientoPlan,
} from "../src/components/comercial/asignacionPlan.ts";

const limites = { ubicaciones: 3, dispositivos: 10, usuarios: 5 };

test("el selector solo ofrece planes con estado Activo", () => {
  const planes = [
    { id_pln: 1, estado: "Activo", limites },
    { id_pln: 2, estado: "Inactivo", limites },
    { id_pln: 3, estado: "Activo", limites: null },
  ];
  assert.deepEqual(planesActivos(planes).map((p) => p.id_pln), [1, 3]);
  assert.equal(planSinLimites(planes[2]), true);
  assert.equal(planSinLimites(planes[0]), false);
});

test("el vencimiento es la fecha de inicio más 30 días calendario", () => {
  assert.equal(vencimientoPlan("2026-11-02"), "2026-12-02");
  assert.equal(vencimientoPlan("2026-01-31"), "2026-03-02");
  assert.equal(vencimientoPlan("2026-12-15"), "2027-01-14");
  assert.equal(vencimientoPlan("2028-02-01"), "2028-03-02"); // año bisiesto
  assert.equal(vencimientoPlan(""), "");
});

test("las fechas se muestran como DD/MM/AAAA", () => {
  assert.equal(fechaVisible("2026-12-02"), "02/12/2026");
  assert.equal(fechaVisible(null), "—");
});

test("hay que elegir plan y una fecha de inicio desde hoy", () => {
  const hoy = "2026-11-02";
  assert.deepEqual(validarAsignacion("", "", hoy), { plan: MSG_ELEGIR_PLAN, fecha: MSG_FECHA_INICIO });
  assert.deepEqual(validarAsignacion("4", "2026-11-01", hoy), { fecha: MSG_FECHA_PASADA });
  assert.deepEqual(validarAsignacion("4", hoy, hoy), {});
  assert.deepEqual(validarAsignacion("4", "2026-11-20", hoy), {});
});
