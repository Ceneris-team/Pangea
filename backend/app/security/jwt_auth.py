"""
T40 - Implementar emisión de JWT
T43 - Configurar rate limiting login (depende de T40)

HT-04: "Se opta por JWT sobre sesiones de servidor para soportar
escalamiento horizontal del backend... Cada acción autenticada debe
registrar userId y sedeId para trazabilidad y auditoría."

IMPORTANTE: el payload incluye sede_id y scope desde el día 1, aunque el
log de auditoría formal (lg_adtr, HT-11) recién se construye en Sprint 3 -
así el middleware de HT-09 y el propio log no necesitan tocar este módulo
más adelante.
"""
import os
import datetime as dt

import jwt

# La llave real SIEMPRE debe venir de una variable de entorno, nunca hardcodeada.
# Generarla una sola vez con: python -c "import secrets; print(secrets.token_hex(32))"
SECRET_KEY = os.environ.get("JWT_SECRET_KEY", "clave-de-desarrollo-cambiar-en-produccion")
ALGORITHM = "HS256"
EXPIRATION_MINUTES = 60 * 8


class TokenInvalido(Exception):
    pass


class TokenExpirado(Exception):
    pass


def create_access_token(user_id: int, sede_id: int | None, scope: str, rol: str) -> str:
    """Emite un JWT para un usuario ya autenticado (HU 01, después de
    verify_password). scope viene de usr.scp ('global' o 'por_sede'):
    si es 'global', sede_id puede ir en None y el middleware de HT-09
    debe saltarse el filtro de sede para ese request.
    """
    now = dt.datetime.now(dt.timezone.utc)
    payload = {
        "sub": str(user_id),
        "sede_id": sede_id,
        "scope": scope,
        "rol": rol,
        "iat": now,
        "exp": now + dt.timedelta(minutes=EXPIRATION_MINUTES),
    }
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def decode_access_token(token: str) -> dict:
    """Valida y decodifica un JWT. Lanza TokenExpirado o TokenInvalido si
    corresponde, para que la capa HTTP (FastAPI) los traduzca a 401 (HT-04 CA)."""
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise TokenExpirado("El token ha expirado")
    except jwt.InvalidTokenError:
        raise TokenInvalido("El token es inválido")
