import test from "node:test";
import assert from "node:assert/strict";
import { agruparSeriesComparables, type SerieTelemetria } from "../src/pages/seriesTelemetria.ts";

function fuente(id: number, parametro = 1, significado: SerieTelemetria["configuracion"]["significado"] = "continuo"): SerieTelemetria {
  return { id_serie: id, id_dspstv: id, dispositivo_nombre: `DL ${id}`,
    id_prmtr: parametro, parametro_nombre: `Parámetro ${parametro}`, undd: "V",
    id_ubccn: 1, ubicacion_nombre: "Proyecto", tp_trm: "H", indc_clmn: 1,
    configuracion: { significado, vista: "kpi", reinicio: "desconocido", modulo: null, confirmada: true } };
}

test("seis dataloggers con dos parámetros generan dos grupos con seis fuentes", () => {
  const series = Array.from({ length: 6 }, (_, i) => [fuente(i * 2 + 1), fuente(i * 2 + 2, 2)]).flat();
  const grupos = agruparSeriesComparables(series);
  assert.deepEqual(grupos.map(g => g.series.length), [6, 6]);
  assert.equal(new Set(grupos.flatMap(g => g.series.map(s => s.id_serie))).size, 12);
});

test("no compara unidades diferentes ni confunde mV con MV", () => {
  const a = fuente(1), b = { ...fuente(2), undd: "mV" }, c = { ...fuente(3), undd: "MV" };
  assert.equal(agruparSeriesComparables([a, b, c]).length, 3);
});

test("no mezcla contador de eventos, secuencia y estado aunque compartan parámetro", () => {
  const series = [fuente(1, 1, "contador"), fuente(2, 1, "secuencia"), fuente(3, 1, "estado")];
  assert.equal(agruparSeriesComparables(series).length, 3);
});

test("mantiene separados encabezados con significado desconocido", () => {
  assert.equal(agruparSeriesComparables([fuente(1, 1, "desconocido"), fuente(2, 1, "desconocido")]).length, 2);
});

test("conserva formatos y reglas de reinicio propios de cada fuente al comparar", () => {
  const a = fuente(1, 1, "contador");
  const b = { ...fuente(2, 1, "contador"), tp_trm: "P", configuracion: { ...a.configuracion, reinicio: "cero" as const } };
  const grupo = agruparSeriesComparables([a, b])[0];
  assert.equal(grupo.series.length, 2);
  assert.equal(grupo.series[0].configuracion.reinicio, "desconocido");
  assert.equal(grupo.series[1].configuracion.reinicio, "cero");
  assert.equal(grupo.series[1].tp_trm, "P");
});

test("no mezcla proyectos distintos", () => {
  assert.equal(agruparSeriesComparables([fuente(1), { ...fuente(2), id_ubccn: 2 }]).length, 2);
});
