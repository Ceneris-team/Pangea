"""Respaldo consistente, cifrado autenticado y retencion por entorno."""

import datetime as dt
import hashlib
import os
import subprocess
import tempfile
import threading
import uuid
from contextlib import contextmanager
from pathlib import Path
from urllib.parse import quote, unquote, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

from sqlalchemy import create_engine, text

from app.database import DATABASE_URL
from app.services import almacen_respaldos as almacen
from app.services.cifrado_respaldos import cifrar_stream, claves_configuradas

ZONA = ZoneInfo("America/Lima")


class RespaldoError(Exception):
    pass


class RespaldoEnCurso(RespaldoError):
    pass


def _url_libpq(url):
    return url.replace("+psycopg2", "", 1).replace("+psycopg", "", 1)


def _separar_credenciales(url):
    partes = urlsplit(url)
    host = partes.hostname or ""
    if ":" in host:
        host = f"[{host}]"
    if partes.port:
        host += f":{partes.port}"
    if partes.username:
        host = quote(unquote(partes.username), safe="") + "@" + host
    limpia = urlunsplit((partes.scheme, host, partes.path, partes.query, partes.fragment))
    return limpia, unquote(partes.password) if partes.password is not None else None


def entero_configurado(nombre, defecto):
    valor = int(os.environ.get(nombre, defecto))
    if valor < 1:
        raise ValueError(f"{nombre} debe ser positivo")
    return valor


def retencion_dias():
    return entero_configurado("BACKUP_RETENTION_DAYS", 56)


def prefijo():
    return almacen.prefijo()


def database_url():
    return os.environ.get("BACKUP_DATABASE_URL") or DATABASE_URL


def conexion_pg(url):
    limpia, password = _separar_credenciales(_url_libpq(url))
    entorno = {**os.environ, "PGCONNECT_TIMEOUT": "10"}
    entorno.pop("PGPASSWORD", None)
    if password is not None:
        entorno["PGPASSWORD"] = password
    return limpia, entorno


@contextmanager
def bloqueo_respaldo():
    engine = create_engine(
        database_url(), hide_parameters=True, connect_args={"connect_timeout": 10}
    )
    try:
        with engine.connect() as conn:
            if not conn.scalar(text("SELECT pg_try_advisory_lock(80002606)")):
                raise RespaldoEnCurso("Ya existe un respaldo ejecutandose")
            conn.commit()
            try:
                yield conn
            finally:
                conn.rollback()
                conn.execute(text("SELECT pg_advisory_unlock(80002606)"))
    finally:
        engine.dispose()


def clave_respaldo(fecha, identificador=None):
    return f"{prefijo()}{fecha:%Y/%m/%d}/pangea-{identificador or uuid.uuid4().hex}.dump.enc"


def generar_respaldo_cifrado(ruta_destino, snapshot=None):
    claves_configuradas()
    url, entorno = conexion_pg(database_url())
    comando = [
        "pg_dump",
        "--format=custom",
        "--no-owner",
        "--no-privileges",
        "--lock-wait-timeout=30000",
    ]
    if snapshot:
        comando.append(f"--snapshot={snapshot}")
    comando.append(url)
    agotado = threading.Event()
    with tempfile.TemporaryFile() as errores:
        proc = subprocess.Popen(comando, stdout=subprocess.PIPE, stderr=errores, env=entorno)

        def terminar():
            agotado.set()
            proc.kill()

        reloj = threading.Timer(entero_configurado("BACKUP_TIMEOUT_SECONDS", 3600), terminar)
        reloj.start()
        try:
            with open(ruta_destino, "wb") as salida:
                cifrar_stream(proc.stdout, salida)
            codigo = proc.wait(timeout=10)
            if agotado.is_set() or codigo:
                raise RespaldoError("pg_dump fallo o excedio el tiempo permitido")
        finally:
            reloj.cancel()
            proc.stdout.close()
            if proc.poll() is None:
                proc.kill()
                proc.wait()


def inventario(conn):
    """Cuenta tablas raiz con el mismo snapshot que usa pg_dump."""
    tablas = conn.execute(text("""
        SELECT c.relname FROM pg_class c JOIN pg_namespace n ON n.oid=c.relnamespace
        WHERE n.nspname='public' AND c.relkind IN ('r','p')
        AND NOT EXISTS (SELECT 1 FROM pg_inherits i WHERE i.inhrelid=c.oid)
        ORDER BY c.relname
    """)).scalars()
    return {
        nombre: conn.scalar(
            text("SELECT count(*) FROM public." + '"' + nombre.replace('"', '""') + '"')
        )
        for nombre in tablas
    }


def aplicar_retencion(hoy=None):
    hoy = hoy or dt.datetime.now(ZONA).date()
    limite = dt.datetime.combine(
        hoy - dt.timedelta(days=retencion_dias()), dt.time.min, tzinfo=dt.timezone.utc
    )
    copias = []
    objetos = almacen.listar()
    for obj in objetos:
        if obj["Key"].endswith(".dump.enc.json"):
            info = almacen.leer_json(obj["Key"])
            if (
                info
                and info.get("estado") == "Exitoso"
                and info.get("clave", "") + ".json" == obj["Key"]
            ):
                almacen.validar_clave(info["clave"])
                copias.append(info)
    borrados = []
    for tipo, maximo in [
        ("semanal", entero_configurado("BACKUP_MAX_COPIES", 8)),
        ("manual", entero_configurado("BACKUP_MANUAL_MAX_COPIES", 2)),
    ]:
        semanas, conservadas = set(), 0
        for info in sorted(
            (c for c in copias if c["tipo"] == tipo), key=lambda c: c["finalizado"], reverse=True
        ):
            fecha = dt.datetime.fromisoformat(info["finalizado"])
            if fecha.tzinfo is None:
                raise ValueError("Fecha de manifiesto sin zona horaria")
            duplicada = tipo == "semanal" and info["semana"] in semanas
            if fecha < limite or conservadas >= maximo or duplicada:
                borrados.append(info["clave"])
            else:
                conservadas += 1
                if tipo == "semanal":
                    semanas.add(info["semana"])
    # Un intento interrumpido antes de guardar el manifiesto no puede acumularse.
    claves = {obj["Key"] for obj in objetos}
    borrados.extend(
        obj["Key"]
        for obj in objetos
        if obj["Key"].endswith(".dump.enc")
        and obj["Key"] + ".json" not in claves
        and obj["LastModified"] < limite
    )
    almacen.eliminar([clave for dato in borrados for clave in (dato, dato + ".json")])
    return borrados


def ejecutar_respaldo(hoy=None, tipo="semanal"):
    if tipo not in {"semanal", "manual"}:
        raise ValueError("Tipo de respaldo desconocido")
    claves_configuradas()
    ahora = dt.datetime.now(dt.timezone.utc)
    fecha = hoy or ahora.astimezone(ZONA).date()
    identificador = uuid.uuid4().hex
    info = {
        "id": identificador,
        "clave": clave_respaldo(fecha, identificador),
        "tipo": tipo,
        "semana": fecha.strftime("%G-W%V"),
        "estado": "EnProceso",
        "iniciado": ahora.isoformat(),
        "entorno": os.environ.get("BACKUP_ENVIRONMENT", "local"),
        "key_id": claves_configuradas()[0],
    }
    with bloqueo_respaldo() as conn:
        almacen.guardar_json(prefijo() + "control/ultima-ejecucion.json", info)
        try:
            conn.execution_options(isolation_level="REPEATABLE READ")
            conn.execute(
                text("SELECT set_config('statement_timeout', :limite, true)"),
                {"limite": str(entero_configurado("BACKUP_TIMEOUT_SECONDS", 3600) * 1000)},
            )
            info["postgres_version"] = conn.scalar(text("SHOW server_version"))
            info["alembic"] = (
                conn.execute(text("SELECT version_num FROM alembic_version ORDER BY version_num"))
                .scalars()
                .all()
            )
            snapshot = conn.scalar(text("SELECT pg_export_snapshot()"))
            info["tablas"] = inventario(conn)
            with tempfile.TemporaryDirectory(prefix="pangea-backup-") as temporal:
                ruta = Path(temporal) / "respaldo.enc"
                generar_respaldo_cifrado(ruta, snapshot)
                conn.rollback()
                with ruta.open("rb") as entrada:
                    info["sha256"] = hashlib.file_digest(entrada, "sha256").hexdigest()
                info["bytes"] = ruta.stat().st_size
                almacen.subir(ruta, info["clave"], info["sha256"])
            info.update(estado="Exitoso", finalizado=dt.datetime.now(dt.timezone.utc).isoformat())
            almacen.guardar_json(info["clave"] + ".json", info)
            info["borrados_por_retencion"] = len(aplicar_retencion(hoy))
            almacen.guardar_json(prefijo() + f"control/ultimo-exito-{tipo}.json", info)
            almacen.guardar_json(prefijo() + "control/ultima-ejecucion.json", info)
        except Exception as exc:
            info.update(estado="Fallido", codigo_error=type(exc).__name__)
            try:
                almacen.guardar_json(prefijo() + "control/ultima-ejecucion.json", info)
            except Exception:
                pass  # El watchdog independiente tambien detecta indisponibilidad de S3.
            raise
        return info
