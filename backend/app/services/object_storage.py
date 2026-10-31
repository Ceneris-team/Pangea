"""Cliente de Object Storage compatible con S3 (HT-06, PP-127).

Lightsail Object Storage expone la API estándar de S3, así que se usa boto3
apuntando al endpoint regional. Este módulo centraliza la creación del cliente
y las operaciones básicas (subir, listar, borrar) para que todo lo que necesite
el bucket -el respaldo extendido de HT-06 (PP-129, tasks/respaldos.py), y más
adelante los .dat crudos y las exportaciones de HU33- use la misma
configuración por variables de entorno, sin credenciales en el código (CA de
HT-06: "las credenciales de Object Storage se gestionan mediante variables de
entorno, sin aparecer en el código fuente").

Variables de entorno (ver .env.example):
    OBJECT_STORAGE_BUCKET      nombre del bucket (p. ej. pangea-data-prod)
    OBJECT_STORAGE_REGION      región AWS (p. ej. us-east-1)
    OBJECT_STORAGE_ENDPOINT    endpoint S3 (p. ej. https://s3.us-east-1.amazonaws.com);
                               opcional, boto3 lo deriva de la región si falta
    OBJECT_STORAGE_ACCESS_KEY  access key del bucket
    OBJECT_STORAGE_SECRET_KEY  secret del bucket
"""

import os

import boto3


class ObjectStorageNoConfigurado(Exception):
    """Falta alguna variable de entorno obligatoria para hablar con el bucket.

    Es un error de configuración del entorno, no de datos: el llamador (p. ej.
    la tarea de respaldo) lo trata como un fallo claro y accionable en vez de
    reventar con un error críptico de boto3 más adentro."""


def _requerido(nombre: str) -> str:
    valor = os.environ.get(nombre)
    if not valor:
        raise ObjectStorageNoConfigurado(
            f"Falta la variable de entorno {nombre}: configúrala antes de usar "
            f"Object Storage (ver .env.example / containers.example.json)."
        )
    return valor


def bucket() -> str:
    return _requerido("OBJECT_STORAGE_BUCKET")


def cliente_s3():
    """Cliente boto3 S3 apuntando a Lightsail Object Storage (o cualquier
    almacenamiento compatible con S3, incluido MinIO en pruebas locales).

    El endpoint es explícito y no se deja al default de boto3 porque Lightsail
    -y un MinIO de desarrollo- no viven en el dominio de AWS S3; con la región
    sola, boto3 armaría la URL de S3 "real" y no la del bucket de Lightsail.
    """
    region = _requerido("OBJECT_STORAGE_REGION")
    endpoint = os.environ.get("OBJECT_STORAGE_ENDPOINT") or f"https://s3.{region}.amazonaws.com"
    return boto3.client(
        "s3",
        region_name=region,
        endpoint_url=endpoint,
        aws_access_key_id=_requerido("OBJECT_STORAGE_ACCESS_KEY"),
        aws_secret_access_key=_requerido("OBJECT_STORAGE_SECRET_KEY"),
    )


def subir_archivo(ruta_local: str, clave: str) -> None:
    """Sube un archivo del disco al bucket bajo `clave` (la ruta/nombre del
    objeto). Usa upload_file, que hace multipart por debajo para archivos
    grandes -un dump de la base puede pesar-, sin cargarlo entero en memoria."""
    cliente_s3().upload_file(ruta_local, bucket(), clave)


def listar(prefijo: str) -> list[dict]:
    """Lista los objetos cuyo nombre empieza con `prefijo`. Devuelve dicts con
    al menos 'Key' y 'LastModified' (lo que necesita la política de retención
    de PP-129). Pagina para no quedarse en los primeros 1000 objetos."""
    s3 = cliente_s3()
    paginador = s3.get_paginator("list_objects_v2")
    objetos: list[dict] = []
    for pagina in paginador.paginate(Bucket=bucket(), Prefix=prefijo):
        objetos.extend(pagina.get("Contents", []))
    return objetos


def eliminar(claves: list[str]) -> None:
    """Borra los objetos indicados. S3 acepta hasta 1000 por llamada a
    delete_objects, así que se trocea en lotes de ese tamaño."""
    if not claves:
        return
    s3 = cliente_s3()
    nombre = bucket()
    for inicio in range(0, len(claves), 1000):
        lote = claves[inicio : inicio + 1000]
        s3.delete_objects(Bucket=nombre, Delete={"Objects": [{"Key": k} for k in lote]})
