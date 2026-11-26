-- QA PP-71 (PP-437): definiciones calculadas para el E2E real en pangea_qa36.
-- Idempotente. Creado por Elliot_QA | Aseguramiento de Calidad.
BEGIN;
INSERT INTO clnt (rzn_scl, rc, crr_cntct)
SELECT 'Empresa QA PP71', '20999999071', 'qa.pp71@example.test'
WHERE NOT EXISTS (SELECT 1 FROM clnt WHERE rzn_scl = 'Empresa QA PP71');
INSERT INTO sd (id_clnt, nmbr)
SELECT id_clnt, 'Sede QA PP71' FROM clnt WHERE rzn_scl = 'Empresa QA PP71'
AND NOT EXISTS (SELECT 1 FROM sd WHERE nmbr = 'Sede QA PP71');
INSERT INTO sscrpcn (id_clnt, id_pln, fch_inc, fch_vncmnt, estd)
SELECT c.id_clnt, 1, current_date, current_date + 30, 'Activa' FROM clnt c
WHERE c.rzn_scl = 'Empresa QA PP71'
AND NOT EXISTS (SELECT 1 FROM sscrpcn s WHERE s.id_clnt = c.id_clnt AND s.estd = 'Activa');

INSERT INTO prmtr_clcld (id_sd, nmbr, frml, undd, dscrpcn, estd, validada)
SELECT 1, v.n, '1 + 1', v.u, v.d, v.e, true FROM (VALUES
  ('Caudal neto', 'm3/s', 'Caudal de entrada menos caudal de salida', 'Activo'),
  ('Caudal específico', 'L/s', 'Caudal por unidad de área de la cuenca', 'Inactivo'),
  ('Presión diferencial', 'kPa', 'Diferencia de presión entre sensores', 'Activo'),
  ('Índice de calidad', '%', 'Índice compuesto de calidad del agua', 'Activo'),
  ('Balance hídrico', 'mm', 'Entradas menos salidas del sistema', 'Inactivo'),
  ('Temperatura media', '°C', 'Promedio de temperaturas del punto', 'Activo'),
  ('Humedad 90%', '%', 'Percentil 90 de humedad relativa', 'Activo'),
  ('Factor_k', '1', 'Factor adimensional de corrección', 'Inactivo'),
  ('Nivel corregido', 'm', 'Nivel compensado por presión atmosférica', 'Activo'),
  ('Conductividad 25', 'uS/cm', 'Conductividad normalizada a 25 °C', 'Activo'),
  ('Caudal acumulado', 'm3', 'Volumen acumulado en el periodo', 'Activo'),
  ('Caudal máximo', 'm3/s', 'Máximo de caudal en la ventana', 'Inactivo'),
  ('Turbidez ajustada', 'NTU', 'Turbidez con corrección de deriva', 'Activo'),
  ('Oxígeno saturado', '%', 'Porcentaje de saturación de oxígeno', 'Inactivo')
) AS v(n, u, d, e)
ON CONFLICT (id_sd, nmbr) DO NOTHING;

INSERT INTO prmtr_clcld (id_sd, nmbr, frml, undd, dscrpcn, estd, validada)
SELECT s.id_sd, 'Caudal de otra empresa', '1 + 1', 'm3/s', 'No debe verse desde Cliente Demo', 'Activo', true
FROM sd s WHERE s.nmbr = 'Sede QA PP71'
ON CONFLICT (id_sd, nmbr) DO NOTHING;
COMMIT;
SELECT c.rzn_scl, p.estd, count(*) FROM prmtr_clcld p JOIN sd s USING (id_sd) JOIN clnt c USING (id_clnt) GROUP BY 1, 2 ORDER BY 1, 2;
