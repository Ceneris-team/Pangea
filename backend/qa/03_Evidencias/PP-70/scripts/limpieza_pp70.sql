-- QA PP-70: borra las definiciones QA70% y sus resultados para repetir el E2E. Creado por Elliot_QA | Aseguramiento de Calidad.
BEGIN;
CREATE TEMP TABLE q70 AS SELECT id_prm_clc FROM prmtr_clcld WHERE nmbr ILIKE 'QA70%';
DELETE FROM clcl_revision WHERE id_resultado IN (SELECT id_resultado FROM clcl_resultado WHERE id_prm_clc IN (SELECT * FROM q70));
DELETE FROM clcl_resultado WHERE id_prm_clc IN (SELECT * FROM q70);
DELETE FROM clcl_serie WHERE id_prm_clc IN (SELECT * FROM q70);
DELETE FROM clcl_trabajo WHERE id_prm_clc IN (SELECT * FROM q70);
DELETE FROM clcl_dependencia WHERE id_prm_clc IN (SELECT * FROM q70);
DELETE FROM prmtr_clcld WHERE id_prm_clc IN (SELECT * FROM q70);
COMMIT;
