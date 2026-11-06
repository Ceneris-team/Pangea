-- Se ejecuta con el propietario de migraciones, nunca con la cuenta de ejecución.
DO $$ BEGIN
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pangea_app') THEN
        CREATE ROLE pangea_app NOLOGIN;
    END IF;
    IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'pangea_auditoria') THEN
        CREATE ROLE pangea_auditoria NOLOGIN;
    END IF;
    IF EXISTS (SELECT FROM pg_roles WHERE rolname IN ('pangea_app','pangea_auditoria')
               AND (rolsuper OR rolcreaterole OR rolcreatedb OR rolbypassrls OR rolcanlogin)) THEN
        RAISE EXCEPTION 'Los roles internos de HT-11 deben ser NOLOGIN y sin privilegios administrativos';
    END IF;
    EXECUTE format('GRANT pangea_app, pangea_auditoria TO %I', current_user);
END $$;
GRANT USAGE ON SCHEMA public TO pangea_app, pangea_auditoria;
REVOKE CREATE ON SCHEMA public FROM PUBLIC, pangea_app;
GRANT CREATE ON SCHEMA public TO pangea_auditoria;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pangea_app;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pangea_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pangea_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE, SELECT ON SEQUENCES TO pangea_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO pangea_auditoria;

-- Lista permitida recursiva para datos libres. Se descartan errores crudos y secretos.
CREATE FUNCTION public.auditoria_sanear(valor jsonb) RETURNS jsonb
LANGUAGE plpgsql IMMUTABLE SET search_path = pg_catalog, public AS $$
DECLARE salida jsonb; k text; v jsonb;
BEGIN
    IF jsonb_typeof(valor) = 'object' THEN
        salida := '{}';
        FOR k,v IN SELECT * FROM jsonb_each(valor) LOOP
            IF k !~* '(password|passwd|pswrd|psswd|pwd|contras|cntrsn|token|secret|clave|credential|credencial|hash|hsh|authorization|cookie|ftp|error|trace|exception|api_key|private_key|access_key|connection_string)' THEN
                salida := salida || jsonb_build_object(k, public.auditoria_sanear(v));
            END IF;
        END LOOP;
        RETURN salida;
    ELSIF jsonb_typeof(valor) = 'array' THEN
        SELECT coalesce(jsonb_agg(public.auditoria_sanear(value)), '[]') INTO salida FROM jsonb_array_elements(valor);
        RETURN salida;
    ELSIF jsonb_typeof(valor) = 'string' AND valor #>> '{}' ~* '(bearer[[:space:]]|://[^ /]+:[^ /]+@|-----BEGIN .*PRIVATE KEY|eyJ[A-Za-z0-9_-]+\.eyJ|(password|token|secret|clave)[[:space:]]*[:=])' THEN
        RETURN '"[REDACTADO]"'::jsonb;
    END IF;
    RETURN valor;
END $$;

ALTER TABLE public.lg_adtr RENAME TO lg_adtr_anterior;
ALTER INDEX public.idx_lgadtr_sd_fch RENAME TO idx_lgadtr_anterior_sd_fch;
ALTER INDEX public.idx_lgadtr_usr_fch RENAME TO idx_lgadtr_anterior_usr_fch;
ALTER SEQUENCE public.lg_adtr_id_evnt_seq OWNED BY NONE;
CREATE TABLE public.lg_adtr (
    id_evnt bigint NOT NULL DEFAULT nextval('public.lg_adtr_id_evnt_seq'),
    id_usr integer, id_afectado integer, id_sd integer, id_clnt integer, id_ubccn integer,
    accn varchar(50) NOT NULL, entdd varchar(100) NOT NULL,
    vlrs_antrrs jsonb, vlrs_nvs jsonb,
    fch_evnt timestamptz NOT NULL DEFAULT clock_timestamp(),
    resultado varchar(20) NOT NULL DEFAULT 'Exitoso' CHECK (resultado IN ('Exitoso','Denegado')),
    origen varchar(20) NOT NULL DEFAULT 'Proceso',
    ejecutor varchar(200) NOT NULL DEFAULT session_user,
    motivo varchar(100), operacion varchar(300), solicitud_id varchar(36),
    PRIMARY KEY (id_evnt, fch_evnt)
) PARTITION BY RANGE (fch_evnt);
ALTER TABLE public.lg_adtr OWNER TO pangea_auditoria;
ALTER SEQUENCE public.lg_adtr_id_evnt_seq OWNER TO pangea_auditoria;
ALTER SEQUENCE public.lg_adtr_id_evnt_seq OWNED BY public.lg_adtr.id_evnt;
CREATE INDEX idx_lgadtr_sd_fch ON public.lg_adtr (id_sd, fch_evnt);
CREATE INDEX idx_lgadtr_usr_fch ON public.lg_adtr (id_usr, fch_evnt);
CREATE INDEX idx_lgadtr_empresa_fch ON public.lg_adtr (id_clnt, fch_evnt, id_evnt);
CREATE INDEX idx_lgadtr_afectado_fch ON public.lg_adtr (id_afectado, fch_evnt);

CREATE FUNCTION public.auditoria_inmutable() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog AS $$ BEGIN
    RAISE EXCEPTION 'El historial de auditoría es inmutable' USING ERRCODE = '42501';
END $$;
CREATE TRIGGER auditoria_no_modificar BEFORE UPDATE OR DELETE ON public.lg_adtr
FOR EACH ROW EXECUTE FUNCTION public.auditoria_inmutable();
CREATE TRIGGER auditoria_no_truncar BEFORE TRUNCATE ON public.lg_adtr
FOR EACH STATEMENT EXECUTE FUNCTION public.auditoria_inmutable();

CREATE FUNCTION public.auditoria_particiones(desde date DEFAULT CURRENT_DATE, meses integer DEFAULT 4)
RETURNS integer LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog, public AS $$
DECLARE fecha date; hasta date; nombre text; creadas integer := 0;
BEGIN
    IF meses < 1 OR meses > 1200 THEN RAISE EXCEPTION 'Rango de particiones inválido'; END IF;
    PERFORM pg_advisory_xact_lock(11002311);
    FOR i IN 0..meses-1 LOOP
        fecha := (date_trunc('month', desde) + make_interval(months => i))::date;
        hasta := (fecha + interval '1 month')::date;
        nombre := 'lg_adtr_' || to_char(fecha, 'YYYY_MM');
        IF to_regclass('public.' || nombre) IS NULL THEN
            EXECUTE format('CREATE TABLE public.%I PARTITION OF public.lg_adtr FOR VALUES FROM (%L) TO (%L)',
                nombre, fecha::text || ' 00:00:00+00', hasta::text || ' 00:00:00+00');
            -- Los triggers de fila se clonan; TRUNCATE necesita protección propia.
            EXECUTE format('CREATE TRIGGER auditoria_no_truncar BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION public.auditoria_inmutable()', nombre);
            EXECUTE format('REVOKE ALL ON public.%I FROM PUBLIC, pangea_app', nombre);
            creadas := creadas + 1;
        END IF;
    END LOOP;
    RETURN creadas;
END $$;
ALTER FUNCTION public.auditoria_particiones(date,integer) OWNER TO pangea_auditoria;
REVOKE ALL ON FUNCTION public.auditoria_particiones(date,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.auditoria_particiones(date,integer) TO pangea_app;
-- Conserva el rango historico completo, incluso fechas futuras preexistentes.
DO $$ DECLARE inicio date; fin date; hoy date := (CURRENT_TIMESTAMP AT TIME ZONE 'UTC')::date; BEGIN
    SELECT least(coalesce((min(fch_evnt) AT TIME ZONE 'UTC')::date,hoy),hoy),
           greatest(coalesce((max(fch_evnt) AT TIME ZONE 'UTC')::date,hoy),
                    (date_trunc('month',hoy)+interval '4 months')::date)
      INTO inicio,fin FROM public.lg_adtr_anterior;
    PERFORM public.auditoria_particiones(inicio,
        (extract(year FROM fin)::int-extract(year FROM inicio)::int)*12
        + extract(month FROM fin)::int-extract(month FROM inicio)::int+1);
END $$;
INSERT INTO public.lg_adtr (id_evnt,id_usr,id_sd,accn,entdd,vlrs_antrrs,vlrs_nvs,fch_evnt,resultado,origen,ejecutor)
SELECT id_evnt,id_usr,id_sd,accn,entdd,public.auditoria_sanear(vlrs_antrrs),public.auditoria_sanear(vlrs_nvs),fch_evnt,
       CASE WHEN accn LIKE 'acceso_denegado:%%' THEN 'Denegado' ELSE 'Exitoso' END,
       'Legado', 'usuario:' || id_usr FROM public.lg_adtr_anterior;
SELECT setval('public.lg_adtr_id_evnt_seq', greatest(coalesce((SELECT max(id_evnt) FROM public.lg_adtr),1),1), true);
DROP TABLE public.lg_adtr_anterior;

CREATE FUNCTION public.auditoria_preparar_evento() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog,public AS $$ BEGIN
    NEW.origen := coalesce(nullif(current_setting('pangea.origen',true),''),NEW.origen);
    NEW.id_usr := coalesce(nullif(current_setting('pangea.actor',true),'')::integer,NEW.id_usr);
    NEW.ejecutor := CASE WHEN NEW.id_usr IS NULL THEN 'proceso:' || session_user
        WHEN NEW.origen='Proceso' THEN 'proceso:' || NEW.id_usr ELSE 'usuario:' || NEW.id_usr END;
    NEW.vlrs_antrrs := public.auditoria_sanear(NEW.vlrs_antrrs);
    NEW.vlrs_nvs := public.auditoria_sanear(NEW.vlrs_nvs);
    NEW.operacion := coalesce(nullif(current_setting('pangea.operacion',true),''),NEW.operacion);
    NEW.solicitud_id := coalesce(nullif(current_setting('pangea.solicitud',true),''),NEW.solicitud_id);
    IF NEW.motivo NOT IN ('permisos_insuficientes','permisos_o_ambito_insuficientes','empresa_no_autorizada',
        'proyecto_de_otra_empresa','proyecto_no_autorizado','rol_insuficiente','membresia_revocada',
        'recurso_fuera_de_ambito') THEN NEW.motivo := NULL; END IF;
    IF NEW.operacion !~ '^(GET|POST|PUT|PATCH|DELETE|OPTIONS|HEAD) /[A-Za-z0-9_/{}/-]*$' THEN NEW.operacion := NULL; END IF;
    RETURN NEW;
END $$;
CREATE TRIGGER auditoria_sanear BEFORE INSERT ON public.lg_adtr
FOR EACH ROW EXECUTE FUNCTION public.auditoria_preparar_evento();

CREATE FUNCTION public.auditoria_identidad(fila jsonb) RETURNS jsonb
LANGUAGE sql IMMUTABLE SET search_path = pg_catalog AS $$
    SELECT coalesce(jsonb_object_agg(key,value),'{}') FROM jsonb_each(fila)
    WHERE key IN ('id_usr','id_rl','scp','nmbr_cmplt','crr','tlfn','estd');
$$;

CREATE FUNCTION public.auditoria_capturar() RETURNS trigger
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,public AS $$
DECLARE
    anterior jsonb := CASE WHEN TG_OP <> 'INSERT' THEN to_jsonb(OLD) ELSE '{}' END;
    nuevo jsonb := CASE WHEN TG_OP <> 'DELETE' THEN to_jsonb(NEW) ELSE '{}' END;
    fila jsonb := CASE WHEN TG_OP = 'DELETE' THEN anterior ELSE nuevo END;
    antes jsonb; despues jsonb; actor integer; afectado integer; empresa integer;
    sede integer; proyecto integer; miembro integer; entidad text; accion text;
    ids integer[]; ids_antes integer[]; ids_despues integer[]; base jsonb;
    origen_evento text; etiqueta text;
BEGIN
    actor := nullif(current_setting('pangea.actor',true),'')::integer;
    origen_evento := coalesce(nullif(current_setting('pangea.origen',true),''),'SQL');
    etiqueta := CASE WHEN actor IS NULL THEN 'proceso:' || session_user
                    WHEN origen_evento='Proceso' THEN 'proceso:' || actor ELSE 'usuario:' || actor END;
    afectado := (fila->>'id_usr')::integer;
    antes := anterior; despues := nuevo;
    accion := CASE TG_OP WHEN 'INSERT' THEN 'conceder' WHEN 'DELETE' THEN 'revocar' ELSE 'editar' END;
    IF TG_TABLE_NAME = 'usr' THEN
        antes := public.auditoria_identidad(anterior);
        despues := public.auditoria_identidad(nuevo);
        IF TG_OP <> 'INSERT' THEN
            antes := antes || jsonb_build_object('rol',(SELECT nmbr FROM public.rl WHERE id_rl=(anterior->>'id_rl')::integer));
        END IF;
        IF TG_OP <> 'DELETE' THEN
            despues := despues || jsonb_build_object('rol',(SELECT nmbr FROM public.rl WHERE id_rl=(nuevo->>'id_rl')::integer));
        END IF;
        IF antes = despues THEN RETURN NULL; END IF;
        entidad := 'usuario:' || afectado;
        accion := CASE TG_OP WHEN 'INSERT' THEN 'crear_usuario' WHEN 'DELETE' THEN 'eliminar_usuario'
            ELSE CASE WHEN anterior->>'estd' IS DISTINCT FROM nuevo->>'estd'
                THEN CASE WHEN nuevo->>'estd' = 'Activo' THEN 'activar_usuario' ELSE 'desactivar_usuario' END
                ELSE 'editar_usuario' END END;
        -- Identidad global: no se atribuye a la empresa del ejecutor ni se copia a otras empresas.
        IF TG_OP = 'UPDATE' THEN
            SELECT coalesce(jsonb_object_agg(a.key,a.value),'{}'),coalesce(jsonb_object_agg(n.key,n.value),'{}')
              INTO antes,despues FROM jsonb_each(antes) a JOIN jsonb_each(despues) n ON n.key=a.key WHERE a.value IS DISTINCT FROM n.value;
        END IF;
    ELSIF TG_TABLE_NAME = 'usr_clnt' THEN
        miembro := (fila->>'id_mmb')::integer; empresa := (fila->>'id_clnt')::integer;
        SELECT coalesce(array_agg(id_ubccn ORDER BY id_ubccn),'{}') INTO ids FROM public.usr_pryct_ubccn WHERE id_mmb=miembro;
        antes := CASE WHEN TG_OP='INSERT' THEN '{}'::jsonb ELSE jsonb_build_object('usuario_id',afectado,'miembro_id',miembro,'cliente_id',empresa,'rol',anterior->>'rol_emp','estado',anterior->>'estd','proyecto_ids',ids) END;
        despues := CASE WHEN TG_OP='DELETE' THEN '{}'::jsonb ELSE jsonb_build_object('usuario_id',afectado,'miembro_id',miembro,'cliente_id',empresa,'rol',nuevo->>'rol_emp','estado',nuevo->>'estd','proyecto_ids',ids) END;
        entidad := 'miembro_empresa:' || miembro;
    ELSIF TG_TABLE_NAME IN ('usr_pryct_ubccn','prms_ubccn') THEN
        proyecto := (fila->>'id_ubccn')::integer;
        SELECT s.id_clnt,u.id_sd INTO empresa,sede FROM public.ubccn u JOIN public.sd s USING (id_sd) WHERE u.id_ubccn=proyecto;
        IF TG_TABLE_NAME = 'usr_pryct_ubccn' THEN
            miembro := (fila->>'id_mmb')::integer;
            SELECT id_usr,jsonb_build_object('usuario_id',id_usr,'miembro_id',miembro,'cliente_id',empresa,'rol',rol_emp,'estado',estd)
              INTO afectado,base FROM public.usr_clnt WHERE id_mmb=miembro;
            -- Una baja en cascada ya está representada por la baja de membresía.
            IF afectado IS NULL THEN
                IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
            END IF;
            SELECT coalesce(array_agg(p.id_ubccn ORDER BY p.id_ubccn),'{}') INTO ids
              FROM public.usr_pryct_ubccn p JOIN public.ubccn u USING(id_ubccn) JOIN public.sd s USING(id_sd)
              WHERE p.id_mmb=miembro AND s.id_clnt=empresa;
            entidad := 'proyectos_miembro:' || miembro;
        ELSE
            SELECT jsonb_build_object('usuario_id',u.id_usr,'cliente_id',empresa,'rol',r.nmbr,'estado',u.estd)
              INTO base FROM public.usr u JOIN public.rl r USING(id_rl) WHERE u.id_usr=afectado;
            SELECT coalesce(array_agg(p.id_ubccn ORDER BY p.id_ubccn),'{}') INTO ids
              FROM public.prms_ubccn p JOIN public.ubccn u USING(id_ubccn) JOIN public.sd s USING(id_sd)
              WHERE p.id_usr=afectado AND s.id_clnt=empresa;
            entidad := 'permisos_ubicacion:' || afectado;
        END IF;
        -- BEFORE ROW conserva el conjunto exacto aun en DELETE/INSERT masivos.
        ids_antes := ids;
        ids_despues := CASE WHEN TG_OP='DELETE' THEN array_remove(ids,proyecto)
                           ELSE ARRAY(SELECT DISTINCT unnest(ids || proyecto) ORDER BY 1) END;
        antes := base || jsonb_build_object('proyecto_ids',ids_antes,'ubicacion_ids',ids_antes,'ubicaciones_quitadas',CASE WHEN TG_OP='DELETE' THEN ARRAY[proyecto] ELSE '{}'::integer[] END);
        despues := base || jsonb_build_object('proyecto_ids',ids_despues,'ubicacion_ids',ids_despues,'ubicaciones_agregadas',CASE WHEN TG_OP='INSERT' THEN ARRAY[proyecto] ELSE '{}'::integer[] END);
    ELSE -- permisos granulares por sede
        sede := (fila->>'id_sd')::integer;
        SELECT id_clnt INTO empresa FROM public.sd WHERE id_sd=sede;
        entidad := 'permisos_sede:' || afectado;
    END IF;
    IF antes = despues THEN
        IF TG_WHEN='BEFORE' THEN RETURN NEW; ELSE RETURN NULL; END IF;
    END IF;
    INSERT INTO public.lg_adtr (id_usr,id_afectado,id_sd,id_clnt,id_ubccn,accn,entdd,vlrs_antrrs,vlrs_nvs,origen,ejecutor)
    VALUES (actor,afectado,sede,empresa,proyecto,accion,entidad,antes,despues,origen_evento,etiqueta);
    IF TG_WHEN='BEFORE' THEN
        IF TG_OP='DELETE' THEN RETURN OLD; ELSE RETURN NEW; END IF;
    END IF;
    RETURN NULL;
END $$;
ALTER FUNCTION public.auditoria_capturar() OWNER TO pangea_auditoria;
REVOKE ALL ON FUNCTION public.auditoria_capturar() FROM PUBLIC;
CREATE FUNCTION public.auditoria_validar_acceso() RETURNS trigger
LANGUAGE plpgsql SET search_path = pg_catalog,public AS $$ BEGIN
    -- Cambiar la identidad o el ambito de una concesion exige revocar y
    -- conceder; asi ambos lados quedan registrados sin mezclar empresas.
    IF TG_OP='UPDATE' AND (
        (to_jsonb(OLD)->'id_usr') IS DISTINCT FROM (to_jsonb(NEW)->'id_usr') OR
        (to_jsonb(OLD)->'id_clnt') IS DISTINCT FROM (to_jsonb(NEW)->'id_clnt') OR
        (to_jsonb(OLD)->'id_mmb') IS DISTINCT FROM (to_jsonb(NEW)->'id_mmb') OR
        (to_jsonb(OLD)->'id_sd') IS DISTINCT FROM (to_jsonb(NEW)->'id_sd') OR
        (to_jsonb(OLD)->'id_ubccn') IS DISTINCT FROM (to_jsonb(NEW)->'id_ubccn')) THEN
        RAISE EXCEPTION 'Revoca la concesion y crea otra para cambiar su ambito' USING ERRCODE='23514';
    END IF;
    IF TG_TABLE_NAME='usr_pryct_ubccn' AND NOT EXISTS (
        SELECT 1 FROM public.usr_clnt m JOIN public.sd s ON s.id_clnt=m.id_clnt
        JOIN public.ubccn u ON u.id_sd=s.id_sd
        WHERE m.id_mmb=(to_jsonb(NEW)->>'id_mmb')::integer
          AND u.id_ubccn=(to_jsonb(NEW)->>'id_ubccn')::integer) THEN
        RAISE EXCEPTION 'El proyecto no pertenece a la empresa de la membresia' USING ERRCODE='23514';
    END IF;
    RETURN NEW;
END $$;
DO $$ DECLARE tabla text; BEGIN
    FOREACH tabla IN ARRAY ARRAY['usr','usr_clnt','usr_pryct_ubccn','prms_ubccn','prms_usr_sd'] LOOP
        IF tabla='usr_clnt' THEN
            EXECUTE format('CREATE TRIGGER auditoria_cambios AFTER INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.auditoria_capturar()',tabla);
            EXECUTE format('CREATE TRIGGER auditoria_baja BEFORE DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.auditoria_capturar()',tabla);
        ELSIF tabla IN ('usr_pryct_ubccn','prms_ubccn') THEN
            EXECUTE format('CREATE TRIGGER auditoria_cambios BEFORE INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.auditoria_capturar()',tabla);
        ELSE
            EXECUTE format('CREATE TRIGGER auditoria_cambios AFTER INSERT OR UPDATE OR DELETE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.auditoria_capturar()',tabla);
        END IF;
        EXECUTE format('CREATE TRIGGER auditoria_no_truncar BEFORE TRUNCATE ON public.%I FOR EACH STATEMENT EXECUTE FUNCTION public.auditoria_inmutable()',tabla);
        IF tabla <> 'usr' THEN
            EXECUTE format('CREATE TRIGGER auditoria_ambito BEFORE INSERT OR UPDATE ON public.%I FOR EACH ROW EXECUTE FUNCTION public.auditoria_validar_acceso()',tabla);
        END IF;
    END LOOP;
END $$;
-- El rol de ejecución no es propietario ni puede mutar/borrar el historial.
REVOKE ALL ON public.lg_adtr FROM PUBLIC, pangea_app;
GRANT SELECT, INSERT ON public.lg_adtr TO pangea_app;
GRANT USAGE, SELECT ON SEQUENCE public.lg_adtr_id_evnt_seq TO pangea_app;
REVOKE ALL ON FUNCTION public.auditoria_inmutable(), public.auditoria_preparar_evento(), public.auditoria_identidad(jsonb) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.auditoria_sanear(jsonb), public.auditoria_identidad(jsonb) TO pangea_auditoria;
GRANT EXECUTE ON FUNCTION public.auditoria_inmutable(), public.auditoria_preparar_evento() TO pangea_auditoria;
-- Funciones de trigger se invocan exclusivamente por los triggers instalados.

-- HT-08 sigue funcionando con la cuenta restringida: solo esta funcion
-- puede crear particiones de telemetria; no se otorga DDL al worker.
CREATE FUNCTION public.telemetria_particiones(desde date, meses integer) RETURNS text[]
LANGUAGE plpgsql SECURITY DEFINER SET search_path = pg_catalog,public AS $$
DECLARE fecha date; hasta date; nombre text; creadas text[] := '{}';
BEGIN
    IF meses < 1 OR meses > 36 THEN RAISE EXCEPTION 'Rango de particiones invalido'; END IF;
    PERFORM pg_advisory_xact_lock(80002311);
    FOR i IN 0..meses-1 LOOP
        fecha := (date_trunc('month',desde) + make_interval(months=>i))::date;
        hasta := (fecha + interval '1 month')::date;
        nombre := 'tlmtr_' || to_char(fecha,'YYYY_MM');
        IF to_regclass('public.' || nombre) IS NULL THEN
            EXECUTE format('CREATE TABLE public.%I PARTITION OF public.tlmtr FOR VALUES FROM (%L) TO (%L)',
                           nombre,fecha::text,hasta::text);
            creadas := array_append(creadas,nombre);
        END IF;
    END LOOP;
    RETURN creadas;
END $$;
REVOKE ALL ON FUNCTION public.telemetria_particiones(date,integer) FROM PUBLIC;
GRANT EXECUTE ON FUNCTION public.telemetria_particiones(date,integer) TO pangea_app;
