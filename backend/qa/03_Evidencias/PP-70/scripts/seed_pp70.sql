-- QA PP-70 (PP-442): datos para el E2E real en pangea_qa36.
-- «QA27 Nivel B» (dispositivo 29, punto 1) 30 s antes de cada lectura de «QA27 Nivel A»
-- entre 08:00 y 15:00 del 20/11/2026; de 16:00 a 19:00 falta B (más de 24 h → Incompleto).
-- Idempotente. Creado por Elliot_QA | Aseguramiento de Calidad.
BEGIN;
INSERT INTO tlmtr (fch_hr, id_dspstv, id_prmtr, id_sd, vlr)
SELECT a.fch_hr - interval '30 seconds', 29, 11, 1, 0.5
FROM tlmtr a
WHERE a.id_dspstv = 28 AND a.id_prmtr = 10 AND a.fch_hr <= '2026-11-20 15:00:00+00'
  AND NOT EXISTS (SELECT 1 FROM tlmtr b WHERE b.id_dspstv = 29 AND b.id_prmtr = 11
                  AND b.fch_hr = a.fch_hr - interval '30 seconds');
COMMIT;
SELECT id_dspstv, count(*) FROM tlmtr WHERE id_sd = 1 GROUP BY 1 ORDER BY 1;
