-- Cuentas locales de QA para HU-23 (solo la BD pangea_e2e). Copian rol, alcance y permisos del Cliente Final del seed (cliente@pangea-dev.com),
-- con su misma clave de prueba; no se escribe ninguna contraseña aquí.
-- Uso: docker exec -i pangea-db-1 psql -U postgres -d pangea_e2e < crear_cuentas_qa.sql
insert into usr (id_rl,scp,nmbr_cmplt,crr,cntrsn_hsh,zn_hrr,estd,dbe_cmbr_pswrd)
 select id_rl,scp,'QA Sin Paneles','qa.sinpaneles@pangea-dev.com',cntrsn_hsh,zn_hrr,estd,false from usr where crr='cliente@pangea-dev.com';
insert into usr (id_rl,scp,nmbr_cmplt,crr,cntrsn_hsh,zn_hrr,estd,dbe_cmbr_pswrd)
 select id_rl,scp,'QA Otro Usuario','qa.otro@pangea-dev.com',cntrsn_hsh,zn_hrr,estd,false from usr where crr='cliente@pangea-dev.com';
insert into prms_usr_sd (id_usr,id_sd,mdl,nvl,id_rl)
 select u.id_usr,p.id_sd,p.mdl,p.nvl,p.id_rl from prms_usr_sd p join usr base on base.id_usr=p.id_usr and base.crr='cliente@pangea-dev.com', usr u
 where u.crr in ('qa.sinpaneles@pangea-dev.com','qa.otro@pangea-dev.com');
insert into pnl (id_usr,id_sd,nmbr) select u.id_usr,p.id_sd,'QA Panel ajeno' from usr u join prms_usr_sd p on p.id_usr=u.id_usr and p.mdl='Tableros' where u.crr='qa.otro@pangea-dev.com';
