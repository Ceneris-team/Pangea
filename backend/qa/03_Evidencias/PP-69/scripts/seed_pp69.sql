-- QA PP-69 (PP-441): datos para el E2E real en pangea_qa36 (además de seed_pp71.sql).
-- Una definición con fórmula extensa y referencias reales, una sin descripción
-- y una empresa sin definiciones. Idempotente. Creado por Elliot_QA | Aseguramiento de Calidad.
BEGIN;
INSERT INTO prmtr_clcld (id_sd, nmbr, frml, undd, dscrpcn, estd, validada)
SELECT 1, 'Índice térmico ponderado',
  'p_1 * 0.35 + p_3 * 0.0125 + p_4 * 0.002 + p_2 * 1.5 + p_1 * p_1 * 0.0004 + p_3 * p_2 * 0.00075'
  || ' + p_4 * p_1 * 0.000125 + p_2 * p_2 * 0.03 + p_1 * 0.015 + p_3 * 0.0006 + p_4 * 0.0008 - p_2 * 0.25',
  'u', 'Combinación ponderada de temperatura, pH, conductividad y ORP', 'Activo', true
ON CONFLICT (id_sd, nmbr) DO NOTHING;
INSERT INTO prmtr_clcld (id_sd, nmbr, frml, undd, dscrpcn, estd, validada)
SELECT 1, 'Amplitud sin descripción', 'p_1 - p_2', 'u', NULL, 'Inactivo', true
ON CONFLICT (id_sd, nmbr) DO NOTHING;

INSERT INTO clnt (rzn_scl, rc, crr_cntct)
SELECT 'Empresa QA PP69', '20999999069', 'qa.pp69@example.test'
WHERE NOT EXISTS (SELECT 1 FROM clnt WHERE rzn_scl = 'Empresa QA PP69');
INSERT INTO sd (id_clnt, nmbr)
SELECT id_clnt, 'Sede QA PP69' FROM clnt WHERE rzn_scl = 'Empresa QA PP69'
AND NOT EXISTS (SELECT 1 FROM sd WHERE nmbr = 'Sede QA PP69');
INSERT INTO sscrpcn (id_clnt, id_pln, fch_inc, fch_vncmnt, estd)
SELECT c.id_clnt, 1, current_date, current_date + 30, 'Activa' FROM clnt c
WHERE c.rzn_scl = 'Empresa QA PP69'
AND NOT EXISTS (SELECT 1 FROM sscrpcn s WHERE s.id_clnt = c.id_clnt AND s.estd = 'Activa');
COMMIT;
SELECT c.rzn_scl, count(p.id_prm_clc) FROM clnt c JOIN sd s USING (id_clnt)
LEFT JOIN prmtr_clcld p USING (id_sd) GROUP BY 1 ORDER BY 1;
