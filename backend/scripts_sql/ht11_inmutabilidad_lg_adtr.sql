-- HT-11 CA3 - Inmutabilidad de lg_adtr a nivel de base de datos.
--
-- NO EJECUTAR contra la base de datos actual sin antes separar el usuario
-- de aplicación. Hoy `pangea` (ver DATABASE_URL en app/database.py y
-- docker-compose.yml) es el ÚNICO usuario que usa toda la app: el mismo
-- rol hace INSERT/UPDATE/DELETE sobre TODAS las tablas (usr, tlmtr,
-- ubccn, ...), no solo sobre lg_adtr. Si este script se corre tal cual
-- contra ese usuario, el REVOKE de UPDATE/DELETE que pide CA3 para
-- lg_adtr no rompe nada ahí -la app nunca actualiza ni borra auditoría-,
-- pero el resto del script (que además le revoca escritura genérica)
-- dejaría a la aplicación entera sin poder escribir NADA: `pangea`
-- necesita UPDATE/DELETE en el resto de las tablas (editar usuarios,
-- reintentar ingesta, borrar mapeos, etc.), así que revocárselos a nivel
-- de rol -en vez de por tabla- la tumbaría por completo.
--
-- Por eso este script asume un escenario de DOS roles que hoy NO existe:
--   - `pangea_app`: el rol que la app usaría para todo lo que no es
--     auditoría (el `pangea` actual, sin tocar).
--   - `pangea_auditoria`: un rol NUEVO, exclusivo para escribir en
--     lg_adtr, con permiso de solo INSERT y sin UPDATE/DELETE/TRUNCATE
--     sobre esa tabla. La app tendría que conectarse con este rol
--     específicamente para las escrituras de security/permisos.py y
--     security/auditoria.py (o usar `SET ROLE` dentro de esas rutas).
--
-- Separar esos dos roles y cablear la app para usar el segundo en el
-- camino de auditoría es TRABAJO DE INFRAESTRUCTURA, fuera de alcance de
-- este commit (HT-11 solo pide "entregar el script documentado"). Hasta
-- que exista `pangea_auditoria`, la inmutabilidad de lg_adtr depende
-- ÚNICAMENTE de la capa de aplicación (punto 2 de este mismo commit: no
-- existe ningún endpoint PUT/PATCH/DELETE sobre /auditoria, y el ORM no
-- se usa nunca para actualizar/borrar LogAuditoria en ningún router).
--
-- Ejecutar como superusuario (o el owner de la base) una vez que
-- pangea_auditoria exista:

-- 1. Crear el rol de solo-escritura para auditoría (ajustar la contraseña
--    antes de usarlo; este placeholder es intencionalmente inválido).
CREATE ROLE pangea_auditoria WITH LOGIN PASSWORD 'CAMBIAR_ANTES_DE_USAR';

-- 2. Puede conectarse a la base y usar el esquema, pero sin privilegios
--    por defecto sobre nada -se otorgan explícitamente abajo, tabla por
--    tabla, nunca con GRANT ALL-.
GRANT CONNECT ON DATABASE pangea_dev TO pangea_auditoria;
GRANT USAGE ON SCHEMA public TO pangea_auditoria;

-- 3. Únicamente INSERT sobre lg_adtr. Sin UPDATE, sin DELETE, sin
--    TRUNCATE: un intento de cualquiera de esas operaciones con este rol
--    falla a nivel de Postgres (42501: insufficient_privilege), pase lo
--    que pase en la capa de aplicación por encima.
GRANT INSERT ON lg_adtr TO pangea_auditoria;

-- 4. La secuencia del id_evnt (BigInteger autoincrement) necesita su
--    propio GRANT: sin esto, el INSERT fallaría al no poder generar el
--    siguiente id aunque el INSERT sobre la tabla esté permitido.
GRANT USAGE ON SEQUENCE lg_adtr_id_evnt_seq TO pangea_auditoria;

-- 5. Explícito y redundante con "no otorgado = no permitido", pero se
--    deja como documentación ejecutable de la garantía que pide CA3: ni
--    siquiera el propio dueño del esquema debería operar accidentalmente
--    sobre esta tabla con este rol.
REVOKE UPDATE, DELETE, TRUNCATE ON lg_adtr FROM pangea_auditoria;

-- 6. Verificación rápida de que quedó como se espera (columna `privilege_type`
--    debe listar solo INSERT para pangea_auditoria sobre lg_adtr):
--
--    SELECT grantee, privilege_type
--    FROM information_schema.role_table_grants
--    WHERE table_name = 'lg_adtr' AND grantee = 'pangea_auditoria';
