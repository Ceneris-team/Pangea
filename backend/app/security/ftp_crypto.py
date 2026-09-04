"""
T42 - Cifrar credenciales FTP

HT-04: "Las credenciales FTP de cada datalogger se almacenan cifradas en
la base de datos y nunca se exponen en texto plano en logs ni en
respuestas de API." El propio documento remarca que esto es crítico
porque una fuga aquí compromete la infraestructura del CLIENTE minero,
no solo la de Pangea.

OJO: esto es CIFRADO reversible (no hash) a propósito. A diferencia de
una contraseña de usuario (que nunca necesitas volver a leer, solo
comparar), aquí sí necesitas descifrar la credencial real para poder
conectarte al servidor FTP/TCP del datalogger (HU 05, T18 "Probar
conexión datalogger"). Por eso NO se usa bcrypt aquí.
"""

import os

from cryptography.fernet import Fernet, InvalidToken

# La llave maestra se genera UNA sola vez para todo el proyecto con:
#   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
# y se guarda como variable de entorno (o en un secret manager), nunca en el
# código ni en el repositorio. Si esta llave se pierde o cambia, todas las
# credenciales FTP ya cifradas en la base de datos quedan irrecuperables.
_FERNET_KEY = os.environ.get("FTP_CREDENTIAL_KEY")

if _FERNET_KEY is None:
    # Solo para que el módulo sea importable en desarrollo/pruebas sin la
    # variable de entorno configurada. En producción esto debe fallar fuerte.
    _FERNET_KEY = Fernet.generate_key().decode("utf-8")

_fernet = Fernet(_FERNET_KEY.encode("utf-8"))


def encrypt_credential(plain_text: str) -> str:
    """Cifra una credencial FTP en texto plano. El resultado es lo único
    que se debe guardar en cnxn_ftp.crdncl_cfrd."""
    return _fernet.encrypt(plain_text.encode("utf-8")).decode("utf-8")


def decrypt_credential(token: str) -> str:
    """Descifra una credencial guardada. Se usa solo en el momento de
    conectarse al FTP/TCP (HU 05, HU 09 al reintentar) - nunca para
    mostrarla en una respuesta de API ni para loguearla."""
    try:
        return _fernet.decrypt(token.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        raise ValueError(
            "No se pudo descifrar la credencial: token corrupto o la llave "
            "FTP_CREDENTIAL_KEY no coincide con la que se usó para cifrarla."
        )
