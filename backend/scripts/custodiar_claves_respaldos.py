"""Exporta/importa un paquete de recuperacion cifrado fuera del repositorio."""

import argparse
import base64
import getpass
import json
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from cryptography.hazmat.primitives.kdf.scrypt import Scrypt
from dotenv import load_dotenv

CAMPOS = (
    "BACKUP_ENCRYPTION_KEY",
    "BACKUP_KEY_ID",
    "BACKUP_PREVIOUS_KEYS",
    "FTP_CREDENTIAL_KEY",
    "NOTIFICATION_CREDENTIAL_KEY",
)
MAGIC = b"PANGEA-KEYS\x01"


def derivar(password, sal):
    return Scrypt(salt=sal, length=32, n=2**17, r=8, p=1).derive(password.encode())


def exportar(datos, password):
    if len(password) < 16:
        raise ValueError("Usa una frase secreta de al menos 16 caracteres")
    sal, nonce = os.urandom(16), os.urandom(12)
    cabecera = MAGIC + sal + nonce
    return cabecera + AESGCM(derivar(password, sal)).encrypt(
        nonce, json.dumps(datos).encode(), cabecera
    )


def importar(datos, password):
    if not datos.startswith(MAGIC) or len(datos) < len(MAGIC) + 44:
        raise ValueError("Formato de paquete desconocido")
    inicio = len(MAGIC)
    cabecera = datos[: inicio + 28]
    return json.loads(
        AESGCM(derivar(password, datos[inicio : inicio + 16])).decrypt(
            datos[inicio + 16 : inicio + 28], datos[inicio + 28 :], cabecera
        )
    )


def main():
    load_dotenv(Path(__file__).resolve().parents[2] / ".env")
    parser = argparse.ArgumentParser(description="Conservar claves fuera del equipo y del bucket")
    parser.add_argument("operacion", choices=["exportar", "importar"])
    parser.add_argument("archivo", type=Path)
    parser.add_argument("--salida", type=Path, help="Archivo .env privado NUEVO para importar")
    args = parser.parse_args()
    password = getpass.getpass("Frase secreta del paquete (no se mostrara): ")
    if args.operacion == "exportar":
        if password != getpass.getpass("Repite la frase secreta: "):
            raise ValueError("Las frases no coinciden")
        datos = {nombre: os.environ[nombre] for nombre in CAMPOS if os.environ.get(nombre)}
        if (
            "BACKUP_ENCRYPTION_KEY" not in datos
            or len(base64.urlsafe_b64decode(datos["BACKUP_ENCRYPTION_KEY"])) != 32
        ):
            raise ValueError("Falta una clave valida de respaldo")
        ruta = args.archivo.resolve()
        if ruta.is_relative_to(Path(__file__).resolve().parents[2]):
            raise ValueError("Guarda el paquete fuera del repositorio")
        contenido = exportar(datos, password)
        if importar(contenido, password) != datos:
            raise ValueError("No se pudo verificar el paquete de recuperacion")
    else:
        if not args.salida:
            parser.error("Importar requiere --salida con un archivo privado nuevo")
        ruta = args.salida.resolve()
        if ruta.is_relative_to(Path(__file__).resolve().parents[2]):
            raise ValueError("El archivo de claves debe estar fuera del repositorio")
        datos = importar(args.archivo.read_bytes(), password)
        contenido = (
            "\n".join(nombre + "=" + datos[nombre] for nombre in CAMPOS if nombre in datos) + "\n"
        ).encode()
    descriptor = os.open(ruta, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(descriptor, "wb") as salida:
        salida.write(contenido)
    print(
        "Archivo privado creado. Conserva el paquete y su frase secreta por separado; no los subas a Git ni al bucket."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("Operacion rechazada. Codigo: " + type(exc).__name__)
        raise SystemExit(1) from None
