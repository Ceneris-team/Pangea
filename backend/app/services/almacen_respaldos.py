"""Operaciones S3 limitadas al espacio de respaldos del entorno."""

import json
import os
import re
from pathlib import Path

from botocore.exceptions import ClientError

from app.services import object_storage


def bucket():
    return os.environ.get("BACKUP_BUCKET") or object_storage.bucket()


def prefijo():
    base = os.environ.get("BACKUP_PREFIX", "respaldos/").strip()
    entorno = os.environ.get("BACKUP_ENVIRONMENT", "local")
    if not base.startswith("respaldos/") or ".." in base or "//" in base:
        raise ValueError("BACKUP_PREFIX debe estar dentro de respaldos/")
    if not re.fullmatch(r"[a-z0-9_-]{1,40}", entorno):
        raise ValueError("BACKUP_ENVIRONMENT invalido")
    return base.rstrip("/") + "/" + entorno + "/"


def validar_clave(clave):
    if not clave.startswith(prefijo()) or ".." in clave:
        raise ValueError("Objeto fuera del espacio de respaldos configurado")


def guardar_json(clave, datos):
    validar_clave(clave)
    object_storage.cliente_s3().put_object(
        Bucket=bucket(),
        Key=clave,
        Body=json.dumps(datos).encode(),
        ContentType="application/json",
        ServerSideEncryption="AES256",
    )


def leer_json(clave):
    validar_clave(clave)
    try:
        respuesta = object_storage.cliente_s3().get_object(Bucket=bucket(), Key=clave)
    except ClientError as exc:
        if exc.response["Error"]["Code"] in {"NoSuchKey", "404"}:
            return None
        raise
    with respuesta["Body"] as entrada:
        datos = entrada.read(1024 * 1024 + 1)
    if len(datos) > 1024 * 1024:
        raise ValueError("Manifiesto demasiado grande")
    return json.loads(datos)


def listar():
    paginas = object_storage.cliente_s3().get_paginator("list_objects_v2")
    return [
        obj
        for pagina in paginas.paginate(Bucket=bucket(), Prefix=prefijo())
        for obj in pagina.get("Contents", [])
    ]


def subir(ruta, clave, checksum):
    validar_clave(clave)
    cliente = object_storage.cliente_s3()
    cliente.upload_file(
        str(ruta),
        bucket(),
        clave,
        ExtraArgs={
            "ServerSideEncryption": "AES256",
            "Metadata": {"sha256": checksum},
        },
    )
    objeto = cliente.head_object(Bucket=bucket(), Key=clave)
    if (
        objeto["ContentLength"] != Path(ruta).stat().st_size
        or objeto["Metadata"].get("sha256") != checksum
    ):
        raise RuntimeError("No coincide el objeto subido con el respaldo local")


def descargar(clave, ruta):
    validar_clave(clave)
    object_storage.cliente_s3().download_file(bucket(), clave, str(ruta))


def eliminar(claves):
    if not claves:
        return
    for clave in claves:
        validar_clave(clave)
    cliente = object_storage.cliente_s3()
    versionado = cliente.get_bucket_versioning(Bucket=bucket()).get("Status")
    objetos = []
    for clave in claves:
        if versionado in {"Enabled", "Suspended"}:
            for pagina in cliente.get_paginator("list_object_versions").paginate(
                Bucket=bucket(), Prefix=clave
            ):
                objetos.extend(
                    {"Key": clave, "VersionId": obj["VersionId"]}
                    for obj in pagina.get("Versions", []) + pagina.get("DeleteMarkers", [])
                    if obj["Key"] == clave
                )
        else:
            objetos.append({"Key": clave})
    for inicio in range(0, len(objetos), 1000):
        resultado = cliente.delete_objects(
            Bucket=bucket(), Delete={"Objects": objetos[inicio : inicio + 1000]}
        )
        if resultado.get("Errors"):
            raise RuntimeError("S3 no pudo eliminar todas las versiones expiradas")
