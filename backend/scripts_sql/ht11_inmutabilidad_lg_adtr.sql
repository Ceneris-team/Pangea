-- HT-11: verificacion posterior a alembic upgrade head.
-- Las protecciones y particiones se instalan mediante a11d20261104.
-- La cuenta LOGIN se aprovisiona con scripts/aprovisionar_auditoria.py.
-- Este archivo no crea roles ni cambia permisos.
SELECT relkind = 'p' AS auditoria_particionada FROM pg_class WHERE oid='public.lg_adtr'::regclass;
SELECT has_table_privilege('pangea_app','public.lg_adtr','SELECT') AS puede_consultar,
       has_table_privilege('pangea_app','public.lg_adtr','INSERT') AS puede_insertar,
       has_table_privilege('pangea_app','public.lg_adtr','UPDATE') AS puede_editar,
       has_table_privilege('pangea_app','public.lg_adtr','DELETE') AS puede_eliminar,
       has_table_privilege('pangea_app','public.lg_adtr','TRUNCATE') AS puede_truncar;
SELECT inhrelid::regclass AS particion FROM pg_inherits WHERE inhparent='public.lg_adtr'::regclass ORDER BY 1;
