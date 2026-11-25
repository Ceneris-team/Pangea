"""Renderizado Jinja2 y transporte SES v2. Sin fallback a envíos simulados."""

import base64
import hashlib
import hmac
import os
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.config import Config
from botocore.exceptions import (
    ClientError,
    ConnectionClosedError,
    ConnectTimeoutError,
    EndpointConnectionError,
    ReadTimeoutError,
)
from cryptography.fernet import Fernet
from jinja2 import Environment, FileSystemLoader, StrictUndefined

from app.services.notificaciones import PLANTILLAS


class DestinatarioPruebaNoPermitido(ValueError):
    """El entorno de pruebas solo permite el buzón indicado por configuración."""


def _cifrador_bienvenida():
    # Clave derivada con separación de propósito. Compatible con la clave
    # de cifrado ya obligatoria del proyecto; admite una clave independiente.
    secreto = os.environ.get("NOTIFICATION_CREDENTIAL_KEY") or os.environ["FTP_CREDENTIAL_KEY"]
    material = base64.urlsafe_b64decode(secreto.encode())
    if len(material) != 32:
        raise ValueError("La clave para credenciales de bienvenida debe ser una clave Fernet")
    derivada = hmac.new(material, b"pangea:correo:bienvenida:v1", hashlib.sha256).digest()
    return Fernet(base64.urlsafe_b64encode(derivada))


def cifrar_password_temporal(password):
    return _cifrador_bienvenida().encrypt(password.encode()).decode()


def renderizar(plantilla, contexto):
    if plantilla not in PLANTILLAS:
        raise ValueError("Plantilla de notificación desconocida")
    entorno = Environment(
        loader=FileSystemLoader(Path(__file__).resolve().parents[1] / "templates" / "correo"),
        autoescape=lambda nombre: bool(nombre and nombre.endswith(".html.j2")),
        undefined=StrictUndefined,
        auto_reload=True,
    )
    datos = {**contexto, "app_url": os.environ.get("FRONTEND_URL", "http://localhost:5173")}
    if plantilla == "bienvenida":
        datos["password_temporal"] = (
            _cifrador_bienvenida().decrypt(datos.pop("password_cifrada").encode()).decode()
        )
    if urlparse(datos["app_url"]).scheme not in {"http", "https"}:
        raise ValueError("FRONTEND_URL debe ser una URL HTTP o HTTPS")
    # El texto plano y el asunto no se escapan como HTML.
    asunto = entorno.get_template(f"{plantilla}.asunto.j2").render(datos)
    texto = entorno.get_template(f"{plantilla}.txt.j2").render(datos)
    html = entorno.get_template(f"{plantilla}.html.j2").render(datos)
    if not asunto.strip() or "\n" in asunto.strip() or "\r" in asunto:
        raise ValueError("Asunto de correo inválido")
    return asunto.strip(), texto, html


def enviar_ses(plantilla, contexto, destinatario, correlacion):
    destino_prueba = os.environ.get("SES_TEST_RECIPIENT", "").strip().lower()
    if destino_prueba and destinatario.strip().lower() != destino_prueba:
        raise DestinatarioPruebaNoPermitido("El destinatario no es el buzón de pruebas configurado")
    remitente = os.environ.get("SES_FROM_EMAIL", "").strip()
    region = os.environ.get("SES_REGION", os.environ.get("AWS_DEFAULT_REGION", "us-east-1"))
    if not remitente:
        raise ValueError("SES_FROM_EMAIL no configurado")
    asunto, texto, html = renderizar(plantilla, contexto)
    ses = boto3.client(
        "sesv2",
        region_name=region,
        config=Config(
            connect_timeout=5,
            read_timeout=20,
            retries={"max_attempts": 0},
        ),
    )
    parametros = {
        "FromEmailAddress": remitente,
        "Destination": {"ToAddresses": [destinatario]},
        "Content": {
            "Simple": {
                "Subject": {"Data": asunto, "Charset": "UTF-8"},
                "Body": {
                    "Text": {"Data": texto, "Charset": "UTF-8"},
                    "Html": {"Data": html, "Charset": "UTF-8"},
                },
            }
        },
        "EmailTags": [{"Name": "pangea_notificacion", "Value": str(correlacion)}],
    }
    configuracion = os.environ.get("SES_CONFIGURATION_SET", "").strip()
    if configuracion:
        parametros["ConfigurationSetName"] = configuracion
    return ses.send_email(**parametros)["MessageId"]


def error_transitorio(exc):
    if isinstance(
        exc,
        (
            ConnectionClosedError,
            ConnectTimeoutError,
            EndpointConnectionError,
            ReadTimeoutError,
            TimeoutError,
            ConnectionError,
        ),
    ):
        return True
    if isinstance(exc, ClientError):
        codigo = exc.response.get("Error", {}).get("Code", "")
        http = exc.response.get("ResponseMetadata", {}).get("HTTPStatusCode", 0)
        return (
            http >= 500
            or http == 429
            or codigo
            in {
                "Throttling",
                "ThrottlingException",
                "TooManyRequestsException",
                "ServiceUnavailable",
                "ServiceUnavailableException",
                "InternalFailure",
                "InternalServerError",
                "RequestTimeout",
                "RequestTimeoutException",
            }
        )
    return False


def codigo_error(exc):
    # Los mensajes de AWS pueden contener direcciones; persistir solo el código.
    if isinstance(exc, ClientError):
        return exc.response.get("Error", {}).get("Code", type(exc).__name__)
    return type(exc).__name__
