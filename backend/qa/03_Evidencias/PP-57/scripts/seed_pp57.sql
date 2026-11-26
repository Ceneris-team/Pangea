-- QA PP-57 (PP-438): proyectos para el E2E real de filtros en pangea_qa36.
-- Idempotente. Copia geometría de un proyecto demo. Creado por Elliot_QA | Aseguramiento de Calidad.
BEGIN;
INSERT INTO ubccn (id_sd, nmbr, dscrpcn, lttd, lngtd, plgn_gjsn, estd, monitoreo_activo)
SELECT v.sd, v.n, 'Proyecto QA PP-57', b.lttd, b.lngtd, b.plgn_gjsn, v.e, v.m
FROM (VALUES
  (1, 'QA57 Laguna Norte', 'Inactiva', true),
  (1, 'QA57 Laguna Sur',   'Inactiva', false),
  (1, 'QA57 Pozo Norte',   'Activa',   true),
  (1, 'QA57 Canal 90%',    'Activa',   true),
  (2, 'QA57 Laguna Ajena', 'Inactiva', true)
) AS v(sd, n, e, m)
CROSS JOIN (SELECT lttd, lngtd, plgn_gjsn FROM ubccn WHERE nmbr = '[DEMO] Planta de Tratamiento') b
WHERE NOT EXISTS (SELECT 1 FROM ubccn u WHERE u.nmbr = v.n AND u.id_sd = v.sd);
COMMIT;
