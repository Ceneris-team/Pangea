"""Recuperacion exclusivamente en una base LOCAL NUEVA, sin ejecutar workers."""

import hashlib
import re
import subprocess
import tempfile
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

from app.services import almacen_respaldos as almacen
from app.services.cifrado_respaldos import descifrar_archivo
from app.services.respaldos import conexion_pg, entero_configurado, inventario


def validar_destino(url):
    destino = make_url(url)
    if destino.host not in {"localhost", "127.0.0.1", "::1", "db"}:
        raise ValueError("La restauracion solo permite PostgreSQL local")
    if not re.fullmatch(r"pangea_restore_[a-z0-9_]{1,40}", destino.database or ""):
        raise ValueError("La base nueva debe llamarse pangea_restore_<identificador>")
    # db es el alias de la red Docker LOCAL; no se aceptan hostaddr/service remotos.
    if destino.query:
        raise ValueError("No se permiten opciones de conexion en una restauracion local")
    return destino


def reparar_permisos(conn):
    """pg_dump no incluye roles globales; recupera las protecciones HT-11."""
    for rol in ("pangea_app", "pangea_auditoria"):
        atributos = conn.execute(
            text(
                "SELECT rolsuper OR rolcreatedb OR rolcreaterole OR rolbypassrls OR rolcanlogin FROM pg_roles WHERE rolname=:rol"
            ),
            {"rol": rol},
        ).scalar_one_or_none()
        if atributos is True:
            raise ValueError("Los roles internos existentes tienen privilegios inesperados")
        if atributos is None:
            conn.exec_driver_sql(
                f"CREATE ROLE {rol} NOLOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOBYPASSRLS"
            )
    conn.execute(
        text(
            "DO $$ BEGIN EXECUTE format('GRANT pangea_app,pangea_auditoria TO %I',current_user); END $$"
        )
    )
    for sql in [
        "GRANT USAGE ON SCHEMA public TO pangea_app,pangea_auditoria",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC,pangea_app",
        "GRANT CREATE ON SCHEMA public TO pangea_auditoria",
        "GRANT SELECT,INSERT,UPDATE,DELETE ON ALL TABLES IN SCHEMA public TO pangea_app",
        "GRANT USAGE,SELECT ON ALL SEQUENCES IN SCHEMA public TO pangea_app",
        "GRANT SELECT ON ALL TABLES IN SCHEMA public TO pangea_auditoria",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT,INSERT,UPDATE,DELETE ON TABLES TO pangea_app",
        "ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT USAGE,SELECT ON SEQUENCES TO pangea_app",
    ]:
        conn.exec_driver_sql(sql)
    moderna = conn.scalar(
        text("SELECT to_regprocedure('public.auditoria_particiones(date,integer)') IS NOT NULL")
    )
    tablas = (
        conn.execute(
            text(
                "SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace WHERE n.nspname='public' AND (c.oid='public.lg_adtr'::regclass OR c.oid IN (SELECT inhrelid FROM pg_inherits WHERE inhparent='public.lg_adtr'::regclass))"
            )
        )
        .scalars()
        .all()
    )
    for nombre in tablas:
        quoted = conn.dialect.identifier_preparer.quote(nombre)
        conn.exec_driver_sql(f"ALTER TABLE public.{quoted} OWNER TO pangea_auditoria")
        conn.exec_driver_sql(f"REVOKE ALL ON public.{quoted} FROM PUBLIC,pangea_app")
    conn.exec_driver_sql("ALTER SEQUENCE public.lg_adtr_id_evnt_seq OWNER TO pangea_auditoria")
    conn.exec_driver_sql("GRANT SELECT,INSERT ON public.lg_adtr TO pangea_app")
    conn.exec_driver_sql("GRANT USAGE,SELECT ON public.lg_adtr_id_evnt_seq TO pangea_app")
    if not moderna:
        # Preserva una copia anterior a HT-11 sin aplicar migraciones de negocio.
        # La cuenta de aplicacion sigue sin poder actualizar/borrar el historial.
        return False
    firmas = (
        conn.execute(
            text(
                "SELECT p.oid::regprocedure::text FROM pg_proc p JOIN pg_namespace n ON n.oid=p.pronamespace WHERE n.nspname='public' AND p.proname LIKE 'auditoria_%' "
            )
        )
        .scalars()
        .all()
    )
    for firma in firmas:
        # regprocedure proviene del catalogo de la base restaurada, no de argumentos CLI.
        conn.exec_driver_sql(f"ALTER FUNCTION {firma} OWNER TO pangea_auditoria")
        conn.exec_driver_sql(f"REVOKE ALL ON FUNCTION {firma} FROM PUBLIC")
    conn.exec_driver_sql(
        "GRANT EXECUTE ON FUNCTION public.auditoria_particiones(date,integer) TO pangea_app"
    )
    conn.exec_driver_sql(
        "REVOKE ALL ON FUNCTION public.telemetria_particiones(date,integer) FROM PUBLIC"
    )
    conn.exec_driver_sql(
        "GRANT EXECUTE ON FUNCTION public.telemetria_particiones(date,integer) TO pangea_app"
    )
    return True


def restaurar_local(clave, destino_url):
    destino = validar_destino(destino_url)
    info = almacen.leer_json(clave + ".json")
    if not info or info.get("estado") != "Exitoso" or info.get("clave") != clave:
        raise ValueError("No existe un manifiesto exitoso para este respaldo")
    with tempfile.TemporaryDirectory(prefix="pangea-restore-") as temporal:
        cifrado, dump = Path(temporal) / "respaldo.enc", Path(temporal) / "respaldo.dump"
        almacen.descargar(clave, cifrado)
        with cifrado.open("rb") as entrada:
            checksum = hashlib.file_digest(entrada, "sha256").hexdigest()
        if checksum != info["sha256"] or cifrado.stat().st_size != info["bytes"]:
            raise ValueError("El respaldo descargado no coincide con su manifiesto")
        descifrar_archivo(cifrado, dump)  # Autenticar ANTES de crear la base o ejecutar SQL.
        admin = create_engine(
            destino.set(database="postgres"), isolation_level="AUTOCOMMIT", hide_parameters=True
        )
        try:
            with admin.connect() as conn:
                if conn.scalar(
                    text("SELECT 1 FROM pg_database WHERE datname=:nombre"),
                    {"nombre": destino.database},
                ):
                    raise ValueError("La base destino ya existe; se rechaza sobrescribirla")
                nombre = conn.dialect.identifier_preparer.quote(destino.database)
                conn.exec_driver_sql(f"CREATE DATABASE {nombre} TEMPLATE template0")
        finally:
            admin.dispose()
        url, entorno = conexion_pg(destino_url)
        with tempfile.TemporaryFile() as errores:
            resultado = subprocess.run(
                [
                    "pg_restore",
                    "--exit-on-error",
                    "--no-owner",
                    "--no-privileges",
                    "--dbname",
                    url,
                    str(dump),
                ],
                env=entorno,
                stdout=subprocess.DEVNULL,
                stderr=errores,
                timeout=entero_configurado("BACKUP_RESTORE_TIMEOUT_SECONDS", 3600),
            )
            if resultado.returncode:
                raise RuntimeError("pg_restore fallo; la base aislada se conserva para diagnostico")
        engine = create_engine(destino, hide_parameters=True)
        try:
            with engine.begin() as conn:
                auditoria_moderna = reparar_permisos(conn)
                revision = (
                    conn.execute(
                        text("SELECT version_num FROM alembic_version ORDER BY version_num")
                    )
                    .scalars()
                    .all()
                )
                conteos = inventario(conn)
                if revision != info["alembic"] or conteos != info["tablas"]:
                    raise RuntimeError(
                        "La base restaurada no coincide con el inventario del respaldo"
                    )
                permisos = conn.scalar(
                    text(
                        "SELECT has_table_privilege('pangea_app','public.lg_adtr','UPDATE,DELETE,TRUNCATE')"
                    )
                )
                if permisos:
                    raise RuntimeError("El rol de la aplicacion puede modificar auditoria")
            return {
                "estado": "Restaurado",
                "base": destino.database,
                "tablas_verificadas": len(conteos),
                "filas_verificadas": sum(conteos.values()),
                "alembic": revision,
                "sha256": checksum,
                "auditoria_inmutable": auditoria_moderna,
                "auditoria_protegida_por_permisos": True,
            }
        finally:
            engine.dispose()
