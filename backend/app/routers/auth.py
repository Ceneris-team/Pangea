"""
HU 01 - Iniciar sesión

CA: login con correo/contraseña correctos redirige al panel según rol.
JWT de 8 horas. "Mi perfil" muestra los datos de cuenta y el rol.
Contraseñas cifradas con bcrypt (via passlib, HT-04).
"""
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import Usuario
from app.security.hashing import verify_password
from app.security.jwt_auth import create_access_token
from app.security.dependencies import get_current_user

router = APIRouter(prefix="/auth", tags=["Autenticación"])
limiter = Limiter(key_func=get_remote_address, storage_uri="redis://localhost:6379/1")
MAX_INTENTOS = 5


class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str
    debe_cambiar_contrasena: bool


# Mensaje genérico a propósito: no hay que decirle al atacante si el correo
# existe o no, o si el problema fue el correo o la contraseña (HT-04).
MSG_CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos"


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/5minutes")
def login(request: Request, body: LoginRequest, db: Session = Depends(get_db)):
    usuario = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.crr == body.correo.lower())
        .first()
    )

    if usuario is None:
        raise HTTPException(status_code=401, detail=MSG_CREDENCIALES_INVALIDAS)

    # Bloqueo por intentos fallidos: se revisa ANTES de aceptar la contraseña,
    # si no, un usuario bloqueado podría seguir entrando con la clave correcta.
    if usuario.intnts_fllds >= MAX_INTENTOS:
        raise HTTPException(
            status_code=403,
            detail="Cuenta bloqueada por demasiados intentos fallidos. Contacte al administrador.",
        )

    if not verify_password(body.contrasena, usuario.cntrsn_hsh):
        usuario.intnts_fllds += 1
        db.commit()
        raise HTTPException(status_code=401, detail=MSG_CREDENCIALES_INVALIDAS)

    if usuario.estd != "Activo":
        raise HTTPException(status_code=401, detail=MSG_CREDENCIALES_INVALIDAS)

    # Login exitoso: resetear contador
    usuario.intnts_fllds = 0
    db.commit()

    token = create_access_token(
        user_id=usuario.id_usr,
        sede_id=None,
        scope=usuario.scp,
        rol=usuario.rol.nmbr,
    )

    return LoginResponse(
        access_token=token,
        rol=usuario.rol.nmbr,
        nombre_completo=usuario.nmbr_cmplt,
        debe_cambiar_contrasena=usuario.dbe_cmbr_pswrd,
    )


@router.get("/perfil")
def mi_perfil(
    usuario_token: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HU 01 CA: 'Mi perfil' muestra los datos de cuenta y el rol asignado."""
    usuario = (
        db.query(Usuario)
        .options(joinedload(Usuario.rol))
        .filter(Usuario.id_usr == int(usuario_token["sub"]))
        .first()
    )
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return {
        "nombre_completo": usuario.nmbr_cmplt,
        "correo": usuario.crr,
        "rol": usuario.rol.nmbr,
        "scope": usuario.scp,
        "estado": usuario.estd,
        "debe_cambiar_contrasena": usuario.dbe_cmbr_pswrd,
    }