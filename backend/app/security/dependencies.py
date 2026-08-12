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

import datetime as dt

from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario

from .jwt_auth import TokenExpirado, TokenInvalido, decode_access_token


def get_current_user(
    authorization: str = Header(default=None),
    db: Session = Depends(get_db),
) -> dict:
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token no proporcionado")

    token = authorization.removeprefix("Bearer ").strip()

    try:
        payload = decode_access_token(token)
    except TokenExpirado:
        raise HTTPException(status_code=401, detail="El token ha expirado")
    except TokenInvalido:
        raise HTTPException(status_code=401, detail="El token es inválido")

    # HU 02 CA: "el cambio de contraseña invalida todas las sesiones activas
    # previas del usuario." Como el JWT es stateless, se compara su fecha de
    # emisión (iat) contra la última vez que se cambió la contraseña.
    usuario = db.query(Usuario).filter(Usuario.id_usr == int(payload["sub"])).first()
    if usuario is None:
        raise HTTPException(status_code=401, detail="El token es inválido")

    if usuario.fch_cntrsn_actlzd is not None:
        emitido_en = dt.datetime.fromtimestamp(payload["iat"], tz=dt.timezone.utc)
        actualizado_en = usuario.fch_cntrsn_actlzd
        if actualizado_en.tzinfo is None:
            actualizado_en = actualizado_en.replace(tzinfo=dt.timezone.utc)
        if emitido_en < actualizado_en:
            raise HTTPException(
                status_code=401,
                detail="Tu sesión ya no es válida porque la contraseña fue actualizada. Vuelve a iniciar sesión.",
            )

    return payload
