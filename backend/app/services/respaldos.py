"""Respaldo extendido de la base de datos hacia Object Storage (HT-06, PP-129).

HT-06 pide una política de respaldo MÁS LARGA que la nativa de Lightsail (7
días), porque los clientes mineros pueden requerir consultas históricas de
varios meses. Este módulo implementa el respaldo semanal con retención de 12
meses (CA: "el job de respaldo extendido se ejecuta semanalmente sin
intervención manual y deja el dump CIFRADO disponible en Object Storage con la
retención configurada").

Pipeline (streaming, sin cargar el dump entero en memoria -un dump de telemetría
puede pesar-):

    pg_dump  ->  gzip  ->  openssl enc (AES-256-CBC, PBKDF2)  ->  archivo .sql.gz.enc

Luego el archivo se sube al bucket (services/object_storage.py) y se aplica la
retención: se borran los respaldos más viejos que BACKUP_RETENTION_DAYS.

Para RESTAURAR un respaldo (operación manual, documentada acá para que no se
pierda el cómo): descargar el objeto del bucket y correr

    openssl enc -d -aes-256-cbc -pbkdf2 -pass env:BACKUP_ENCRYPTION_KEY \\
        -in pangea-YYYY-MM-DD.sql.gz.enc | gunzip | psql <DATABASE_URL libpq>

Variables de entorno:
    BACKUP_ENCRYPTION_KEY   passphrase para cifrar/descifrar el dump (obligatoria)
    BACKUP_PREFIX           prefijo/carpeta en el bucket (default "respaldos/")
    BACKUP_RETENTION_DAYS   días de retención (default 365 = 12 meses)
"""

import datetime as dt
import logging
import os
import subprocess
import tempfile

from app.database import DATABASE_URL
from app.services import object_storage

logger = logging.getLogger(__name__)

PREFIJO_DEFECTO = "respaldos/"
RETENCION_DEFECTO_DIAS = 365  # 12 meses (HT-06)


class RespaldoError(Exception):
    """Falló alguna etapa del respaldo (dump, cifrado o subida)."""


def _url_libpq(database_url: str) -> str:
    """pg_dump/psql hablan libpq y NO entienden el sufijo de driver de
    SQLAlchemy (`+psycopg2`). DATABASE_URL viene como
    'postgresql+psycopg2://...'; acá se lo saca para dejar una URL libpq
    válida ('postgresql://...'). El resto (usuario, clave, host, puerto,
    base) se pasa tal cual."""
    return database_url.replace("+psycopg2", "", 1)


def prefijo() -> str:
    return os.environ.get("BACKUP_PREFIX", PREFIJO_DEFECTO)


def retencion_dias() -> int:
    try:
        return int(os.environ.get("BACKUP_RETENTION_DAYS", RETENCION_DEFECTO_DIAS))
    except ValueError:
        return RETENCION_DEFECTO_DIAS


def clave_respaldo(fecha: dt.date) -> str:
    """Nombre del objeto en el bucket para el respaldo de una fecha dada.
    Incluye el prefijo configurado y la fecha ISO, así los respaldos quedan
    ordenables por nombre y es trivial ver a qué día corresponde cada uno."""
    return f"{prefijo()}pangea-{fecha.isoformat()}.sql.gz.enc"


def generar_respaldo_cifrado(ruta_destino: str) -> None:
    """Corre pg_dump -> gzip -> openssl y deja el resultado cifrado en
    `ruta_destino`. Encadena procesos por pipes (streaming): el dump nunca
    se materializa sin cifrar en disco ni se carga entero en memoria.

    La passphrase viaja a openssl por `-pass env:` -NUNCA como argumento de
    línea de comandos-, para que no quede visible en la lista de procesos
    (`ps`) de la máquina."""
    clave = os.environ.get("BACKUP_ENCRYPTION_KEY")
    if not clave:
        raise RespaldoError(
            "Falta BACKUP_ENCRYPTION_KEY: sin ella el dump no se puede cifrar "
            "(CA de HT-06 exige que el respaldo quede cifrado)."
        )

    entorno = {**os.environ, "BACKUP_ENCRYPTION_KEY": clave}
    url = _url_libpq(DATABASE_URL)

    # --no-owner/--no-privileges: el restore se hace sobre una base nueva cuyo
    # rol dueño puede diferir del de origen (otra instancia Lightsail/RDS); sin
    # esto, psql tiraría errores de "role does not exist" al restaurar.
    dump = subprocess.Popen(
        ["pg_dump", "--format=plain", "--no-owner", "--no-privileges", url],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        env=entorno,
    )
    comprimir = subprocess.Popen(
        ["gzip", "-c"], stdin=dump.stdout, stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    with open(ruta_destino, "wb") as salida:
        cifrar = subprocess.Popen(
            ["openssl", "enc", "-aes-256-cbc", "-pbkdf2", "-salt", "-pass", "env:BACKUP_ENCRYPTION_KEY"],
            stdin=comprimir.stdout,
            stdout=salida,
            stderr=subprocess.PIPE,
            env=entorno,
        )
        # Cerrar los extremos de lectura en el proceso padre para que cada
        # etapa reciba EOF cuando la anterior termina (patrón estándar de
        # encadenar Popen por pipes).
        dump.stdout.close()
        comprimir.stdout.close()
        _, err_cifrar = cifrar.communicate()

    _, err_comprimir = comprimir.communicate()
    _, err_dump = dump.communicate()

    for nombre, proc, err in (
        ("pg_dump", dump, err_dump),
        ("gzip", comprimir, err_comprimir),
        ("openssl", cifrar, err_cifrar),
    ):
        if proc.returncode:
            detalle = (err or b"").decode("utf-8", "replace").strip()
            raise RespaldoError(f"Falló {nombre} (código {proc.returncode}): {detalle}")


def _expirados(objetos: list[dict], limite: dt.datetime) -> list[str]:
    """Claves cuyos objetos son más viejos que `limite` (según LastModified).
    Función pura para poder testear la política de retención sin tocar el
    bucket real."""
    claves = []
    for obj in objetos:
        modificado = obj.get("LastModified")
        if modificado is not None and modificado < limite:
            claves.append(obj["Key"])
    return claves


def aplicar_retencion(hoy: dt.date | None = None) -> list[str]:
    """Borra del bucket los respaldos más viejos que la retención configurada.
    Devuelve las claves borradas. Idempotente: si no hay nada que expirar,
    devuelve []."""
    hoy = hoy or dt.date.today()
    limite = dt.datetime.combine(
        hoy - dt.timedelta(days=retencion_dias()), dt.time.min, tzinfo=dt.timezone.utc
    )
    objetos = object_storage.listar(prefijo())
    expirados = _expirados(objetos, limite)
    object_storage.eliminar(expirados)
    return expirados


def ejecutar_respaldo(hoy: dt.date | None = None) -> dict:
    """Orquesta el respaldo completo: genera el dump cifrado en un archivo
    temporal, lo sube al bucket y aplica la retención. El temporal se borra
    siempre (incluso si la subida falla): nunca se deja un dump -aunque esté
    cifrado- olvidado en el disco del contenedor."""
    hoy = hoy or dt.date.today()
    clave = clave_respaldo(hoy)

    descriptor, ruta_tmp = tempfile.mkstemp(suffix=".sql.gz.enc")
    os.close(descriptor)
    try:
        generar_respaldo_cifrado(ruta_tmp)
        tamano = os.path.getsize(ruta_tmp)
        object_storage.subir_archivo(ruta_tmp, clave)
        logger.info("HT-06: respaldo subido a Object Storage: %s (%s bytes)", clave, tamano)
    finally:
        try:
            os.remove(ruta_tmp)
        except OSError:
            logger.warning("No se pudo borrar el respaldo temporal %s", ruta_tmp)

    borrados = aplicar_retencion(hoy)
    if borrados:
        logger.info("HT-06: retención aplicada, %s respaldo(s) viejo(s) borrado(s)", len(borrados))

    return {"clave": clave, "bytes": tamano, "borrados_por_retencion": len(borrados)}
