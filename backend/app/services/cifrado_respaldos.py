"""Contenedor versionado AES-256-GCM; autentica cabecera y contenido por bloques."""

import base64
import json
import os
import struct
from pathlib import Path

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

MAGIC = b"PANGEA-BACKUP\x01"
BLOQUE = 1024 * 1024


class CifradoRespaldoError(ValueError):
    pass


def _clave(valor):
    try:
        clave = base64.b64decode(valor, altchars=b"-_", validate=True)
    except (ValueError, TypeError) as exc:
        raise CifradoRespaldoError("La clave debe contener 32 bytes codificados en base64") from exc
    if len(clave) != 32:
        raise CifradoRespaldoError("La clave de respaldo debe tener 256 bits")
    return clave


def claves_configuradas():
    identificador = os.environ.get("BACKUP_KEY_ID", "v1")
    if not identificador or len(identificador) > 100:
        raise CifradoRespaldoError("BACKUP_KEY_ID inválido")
    valor = os.environ.get("BACKUP_ENCRYPTION_KEY", "")
    if not valor:
        raise CifradoRespaldoError("Falta BACKUP_ENCRYPTION_KEY")
    actuales = {identificador: _clave(valor)}
    anteriores = json.loads(os.environ.get("BACKUP_PREVIOUS_KEYS", "{}"))
    if not isinstance(anteriores, dict) or identificador in anteriores:
        raise CifradoRespaldoError(
            "BACKUP_PREVIOUS_KEYS debe contener solo identificadores anteriores"
        )
    actuales.update({nombre: _clave(valor) for nombre, valor in anteriores.items()})
    return identificador, actuales


def cifrar_stream(entrada, salida, metadata=None):
    identificador, claves = claves_configuradas()
    nonce = os.urandom(12)
    cabecera = json.dumps(
        {
            **(metadata or {}),
            "version": 1,
            "cifrado": "AES-256-GCM",
            "formato": "pg-custom",
            "key_id": identificador,
            "nonce": base64.b64encode(nonce).decode(),
        },
        sort_keys=True,
        separators=(",", ":"),
    ).encode()
    if len(cabecera) > 16384:
        raise CifradoRespaldoError("Cabecera de respaldo demasiado grande")
    aad = MAGIC + struct.pack(">I", len(cabecera)) + cabecera
    cifrador = Cipher(algorithms.AES(claves[identificador]), modes.GCM(nonce)).encryptor()
    cifrador.authenticate_additional_data(aad)
    salida.write(aad)
    while datos := entrada.read(BLOQUE):
        salida.write(cifrador.update(datos))
    salida.write(cifrador.finalize())
    salida.write(cifrador.tag)
    return json.loads(cabecera)


def descifrar_archivo(origen, destino):
    """No entrega el archivo al restaurador hasta verificar la etiqueta GCM."""
    destino = Path(destino)
    creado = False
    try:
        with open(origen, "rb") as entrada:
            magic = entrada.read(len(MAGIC))
            longitud = entrada.read(4)
            if magic != MAGIC or len(longitud) != 4:
                raise CifradoRespaldoError(
                    "Formato desconocido; los respaldos OpenSSL requieren modo legacy"
                )
            longitud = struct.unpack(">I", longitud)[0]
            if not 0 < longitud <= 16384:
                raise CifradoRespaldoError("Cabecera de respaldo inválida")
            cabecera = entrada.read(longitud)
            info = json.loads(cabecera)
            if (
                info.get("version") != 1
                or info.get("cifrado") != "AES-256-GCM"
                or info.get("formato") != "pg-custom"
            ):
                raise CifradoRespaldoError("Versión o algoritmo de respaldo no soportado")
            _, claves = claves_configuradas()
            clave = claves.get(info.get("key_id"))
            if clave is None:
                raise CifradoRespaldoError("No está disponible la versión de clave necesaria")
            nonce = base64.b64decode(info["nonce"], validate=True)
            if len(nonce) != 12:
                raise CifradoRespaldoError("Nonce inválido")
            inicio = entrada.tell()
            entrada.seek(0, 2)
            restante = entrada.tell() - inicio - 16
            if restante <= 0:
                raise CifradoRespaldoError("Respaldo truncado")
            entrada.seek(-16, 2)
            tag = entrada.read(16)
            entrada.seek(inicio)
            descifrador = Cipher(algorithms.AES(clave), modes.GCM(nonce, tag)).decryptor()
            descifrador.authenticate_additional_data(MAGIC + struct.pack(">I", longitud) + cabecera)
            descriptor = os.open(destino, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            creado = True
            with os.fdopen(descriptor, "wb") as salida:
                while restante:
                    datos = entrada.read(min(BLOQUE, restante))
                    if not datos:
                        raise CifradoRespaldoError("Respaldo truncado")
                    salida.write(descifrador.update(datos))
                    restante -= len(datos)
                salida.write(descifrador.finalize())
            return info
    except (InvalidTag, KeyError, ValueError, TypeError) as exc:
        if creado:
            destino.unlink(missing_ok=True)
        if isinstance(exc, CifradoRespaldoError):
            raise
        raise CifradoRespaldoError("Clave incorrecta o respaldo alterado") from exc
    except OSError:
        if creado:
            destino.unlink(missing_ok=True)
        raise
