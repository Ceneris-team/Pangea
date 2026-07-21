"""
Conecta jwt_auth.py con FastAPI. Este es el "candado" que se pone en cada
endpoint protegido: HT-04 exige que devuelva 401 si el token falta,
es inválido o expiró.

Uso en un endpoint:

    from fastapi import Depends
    from security.dependencies import get_current_user

    @app.get("/dispositivos")
    def listar_dispositivos(usuario: dict = Depends(get_current_user)):
        sede_id = usuario["sede_id"]  # None si scope == "global"
        ...
"""
from fastapi import Header, HTTPException

from .jwt_auth import decode_access_token, TokenExpirado, TokenInvalido


def get_current_user(authorization: str = Header(default=None)) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = decode_access_token(token)
    except TokenExpirado:
        raise HTTPException(status_code=401, detail="El token ha expirado")
    except TokenInvalido:
        raise HTTPException(status_code=401, detail="El token es inválido")

    return payload
