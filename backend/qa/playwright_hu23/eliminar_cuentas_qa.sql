-- Elimina las cuentas locales de QA de HU-23 y sus datos (solo la BD pangea_e2e).
-- Uso: docker exec -i pangea-db-1 psql -U postgres -d pangea_e2e < eliminar_cuentas_qa.sql
delete from wdgt where id_pnl in (select id_pnl from pnl where id_usr in (select id_usr from usr where crr like 'qa.%@pangea-dev.com'));
delete from pnl_ubccn where id_pnl in (select id_pnl from pnl where id_usr in (select id_usr from usr where crr like 'qa.%@pangea-dev.com'));
delete from pnl where id_usr in (select id_usr from usr where crr like 'qa.%@pangea-dev.com');
delete from lg_adtr where id_usr in (select id_usr from usr where crr like 'qa.%@pangea-dev.com');
delete from prms_usr_sd where id_usr in (select id_usr from usr where crr like 'qa.%@pangea-dev.com');
delete from usr where crr like 'qa.%@pangea-dev.com';
