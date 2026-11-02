import os

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

TIPOS = {
    "csv": "text/csv; charset=utf-8",
    "xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}


def bucket_configurado() -> str:
    bucket = os.getenv("EXPORT_S3_BUCKET", "").strip()
    if not bucket:
        raise RuntimeError("El almacenamiento de exportaciones no está configurado")
    return bucket


class AlmacenExportaciones:
    def __init__(self, bucket=None):
        self.bucket = bucket or bucket_configurado()
        self.client = boto3.client(
            "s3",
            region_name=os.getenv("EXPORT_S3_REGION", "us-east-1"),
            endpoint_url=os.getenv("EXPORT_S3_ENDPOINT_URL") or None,
            config=Config(
                signature_version="s3v4",
                connect_timeout=10,
                read_timeout=60,
                retries={"max_attempts": 3},
            ),
        )

    def verificar_privado(self):
        acl = self.client.get_bucket_acl(Bucket=self.bucket)
        if any(
            g["Grantee"].get("URI", "").endswith(("/AllUsers", "/AuthenticatedUsers"))
            for g in acl.get("Grants", [])
        ):
            raise RuntimeError("El bucket de exportaciones debe ser privado")
        try:
            policy = self.client.get_bucket_policy_status(Bucket=self.bucket)
        except ClientError as exc:
            if exc.response["Error"]["Code"] != "NoSuchBucketPolicy":
                raise
        else:
            if policy.get("PolicyStatus", {}).get("IsPublic"):
                raise RuntimeError("El bucket de exportaciones tiene una política pública")

    def subir(self, archivo, clave, formato):
        self.verificar_privado()
        with open(archivo, "rb") as contenido:
            resultado = self.client.put_object(
                Bucket=self.bucket,
                Key=clave,
                Body=contenido,
                ContentType=TIPOS[formato],
                ContentDisposition=f'attachment; filename="telemetria.{formato}"',
            )
        return resultado.get("VersionId")

    def eliminar(self, clave, version=None):
        # Cada clave es exclusiva de una solicitud. Elimina también las versiones
        # de reintentos cuya respuesta de subida pudo perderse en la red.
        estado = self.client.get_bucket_versioning(Bucket=self.bucket).get("Status")
        if estado in ("Enabled", "Suspended"):
            paginas = self.client.get_paginator("list_object_versions").paginate(
                Bucket=self.bucket, Prefix=clave
            )
            for pagina in paginas:
                objetos = [
                    {"Key": item["Key"], "VersionId": item["VersionId"]}
                    for grupo in ("Versions", "DeleteMarkers")
                    for item in pagina.get(grupo, [])
                    if item["Key"] == clave
                ]
                for inicio in range(0, len(objetos), 1000):
                    respuesta = self.client.delete_objects(
                        Bucket=self.bucket,
                        Delete={"Objects": objetos[inicio : inicio + 1000], "Quiet": True},
                    )
                    if respuesta.get("Errors"):
                        raise RuntimeError(
                            "No se pudieron eliminar todas las versiones de la exportación"
                        )
            return
        parametros = {"Bucket": self.bucket, "Key": clave}
        if version:
            parametros["VersionId"] = version
        self.client.delete_object(**parametros)

    def firmar(self, clave, segundos, version=None):
        parametros = {"Bucket": self.bucket, "Key": clave}
        if version:
            parametros["VersionId"] = version
        return self.client.generate_presigned_url(
            "get_object", Params=parametros, ExpiresIn=segundos
        )
