"""
HU 01 - Iniciar sesión
HU 02 - Gestionar contraseña

CA: login con correo/contraseña correctos redirige al panel según rol.
JWT de 8 horas. "Mi perfil" muestra los datos de cuenta y el rol.
Contraseñas cifradas con bcrypt (via passlib, HT-04).

HU 02 agrega tres flujos: solicitar enlace de recuperación (olvidé mi
contraseña), restablecerla con ese enlace, y cambiarla estando autenticado
desde "Mi perfil".
"""

import datetime as dt
import os
import secrets
from zoneinfo import available_timezones

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session, joinedload

from app.database import get_db
from app.models import TokenRecuperacion, Usuario
from app.security.dependencies import COOKIE_NOMBRE, get_current_user, get_token_crudo
from app.security.hashing import hash_password, verify_password
from app.security.jwt_auth import EXPIRATION_MINUTES, create_access_token
from app.security.mailer import enviar_correo_recuperacion
from app.security.password_policy import MSG_POLITICA_INVALIDA, es_password_valido
from app.security.ws_tickets import emitir_ticket

router = APIRouter(prefix="/auth", tags=["Autenticación"])
RATELIMIT_STORAGE_URL = os.environ.get("RATELIMIT_STORAGE_URL", "redis://localhost:6379/1")
limiter = Limiter(key_func=get_remote_address, storage_uri=RATELIMIT_STORAGE_URL)
MAX_INTENTOS = 5
VIGENCIA_TOKEN_RECUPERACION_MINUTOS = 30

# HT-04 migración a cookie httpOnly: el frontend (pangea-app y el ensayo
# en CloudFront) vive en un dominio DISTINTO al de pangea-api, así que la
# cookie tiene que poder viajar cross-site. SameSite=None es el único
# valor que permite eso -Strict y Lax la bloquean entre dominios
# distintos, dejando la cookie inútil-, y el navegador exige Secure como
# condición para aceptar SameSite=None (ambos despliegues sirven por
# HTTPS, así que no hay downgrade real).
COOKIE_MAX_AGE_SEGUNDOS = EXPIRATION_MINUTES * 60


def _setear_cookie_sesion(response: Response, token: str) -> None:
    response.set_cookie(
        key=COOKIE_NOMBRE,
        value=token,
        max_age=COOKIE_MAX_AGE_SEGUNDOS,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )


class LoginRequest(BaseModel):
    correo: EmailStr
    contrasena: str


class LoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    rol: str
    nombre_completo: str
    debe_cambiar_contrasena: bool
    zona_horaria: str


# Mensaje genérico a propósito: no hay que decirle al atacante si el correo
# existe o no, o si el problema fue el correo o la contraseña (HT-04).
MSG_CREDENCIALES_INVALIDAS = "Correo o contraseña incorrectos"


@router.post("/login", response_model=LoginResponse)
@limiter.limit("5/5minutes")
def login(request: Request, response: Response, body: LoginRequest, db: Session = Depends(get_db)):
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

    # Cookie httpOnly: mecanismo principal de sesión para el navegador.
    # El JWT sigue viajando también en el body (access_token) por
    # retrocompatibilidad con clientes que todavía usan el header
    # Authorization -ver get_current_user en security/dependencies.py-.
    _setear_cookie_sesion(response, token)

    return LoginResponse(
        access_token=token,
        rol=usuario.rol.nmbr,
        nombre_completo=usuario.nmbr_cmplt,
        debe_cambiar_contrasena=usuario.dbe_cmbr_pswrd,
        zona_horaria=usuario.zn_hrr,
    )


@router.post("/logout")
def logout(response: Response):
    """Borra la cookie de sesión explícitamente (Max-Age=0). Los flags
    (Secure/SameSite/Path) tienen que coincidir exactamente con los que
    usó set_cookie en el login: un delete_cookie con distinto Path o
    SameSite crea una cookie NUEVA en vez de pisar la existente, y el
    navegador terminaría con dos cookies del mismo nombre."""
    response.delete_cookie(
        key=COOKIE_NOMBRE,
        httponly=True,
        secure=True,
        samesite="none",
        path="/",
    )
    return {"mensaje": "Sesión cerrada correctamente"}


@router.post("/ws-ticket")
def crear_ticket_websocket(
    usuario_token: dict = Depends(get_current_user),
    token_crudo: str = Depends(get_token_crudo),
):
    """Mitigación de R-05 (RAID del proyecto): el WebSocket de HU17 no
    puede leer la cookie httpOnly ni mandar headers propios -limitación
    de la API WebSocket del navegador-, así que un cliente ya autenticado
    por cookie cambia esa identidad por un ticket opaco, de un solo uso y
    vida corta, para pegarlo en la query string del WS en su lugar. Ver
    security/ws_tickets.py y _autenticar_websocket en
    routers/mapa_cliente.py.
    """
    return {"ticket": emitir_ticket(token_crudo)}


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
        "zona_horaria": usuario.zn_hrr,
    }


@router.get("/zonas-horarias")
def listar_zonas_horarias():
    """HU14 CA1: listado de zonas horarias disponibles (estándar IANA)."""
    return {"zonas_horarias": sorted(available_timezones())}


class ZonaHorariaRequest(BaseModel):
    zona_horaria: str


@router.put("/zona-horaria")
def actualizar_zona_horaria(
    body: ZonaHorariaRequest,
    usuario_token: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HU14 CA2: configurar la zona horaria de visualización del usuario."""
    if body.zona_horaria not in available_timezones():
        raise HTTPException(status_code=400, detail="La zona horaria indicada no es válida.")

    usuario = db.query(Usuario).filter(Usuario.id_usr == int(usuario_token["sub"])).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    usuario.zn_hrr = body.zona_horaria
    db.commit()

    return {"mensaje": "Zona horaria actualizada correctamente", "zona_horaria": usuario.zn_hrr}


class OlvideContrasenaRequest(BaseModel):
    correo: EmailStr


MSG_CORREO_ENVIADO = "Te hemos enviado un correo con las instrucciones para recuperar tu contraseña"


@router.post("/olvide-contrasena")
@limiter.limit("5/15minutes")
def olvide_contrasena(
    request: Request, body: OlvideContrasenaRequest, db: Session = Depends(get_db)
):
    """HU 02 CA 1: solicitar el enlace de recuperación desde el login."""
    usuario = db.query(Usuario).filter(Usuario.crr == body.correo.lower()).first()

    # Igual que en /login (HT-04): la respuesta es idéntica exista o no el
    # correo, para no revelar qué cuentas están registradas.
    if usuario is not None and usuario.estd == "Activo":
        token = secrets.token_urlsafe(32)
        vencimiento = dt.datetime.now(dt.timezone.utc) + dt.timedelta(
            minutes=VIGENCIA_TOKEN_RECUPERACION_MINUTOS
        )
        db.add(TokenRecuperacion(id_usr=usuario.id_usr, tkn=token, fch_exp=vencimiento))
        db.commit()
        enviar_correo_recuperacion(usuario.crr, token)

    return {"mensaje": MSG_CORREO_ENVIADO}


class RestablecerContrasenaRequest(BaseModel):
    token: str
    nueva_contrasena: str
    confirmar_contrasena: str


@router.post("/restablecer-contrasena")
@limiter.limit("10/15minutes")
def restablecer_contrasena(
    request: Request, body: RestablecerContrasenaRequest, db: Session = Depends(get_db)
):
    """HU 02 CA 2: canjear el enlace de recuperación por una contraseña nueva."""
    token = (
        db.query(TokenRecuperacion)
        .filter(TokenRecuperacion.tkn == body.token, TokenRecuperacion.usad.is_(False))
        .first()
    )

    ahora = dt.datetime.now(dt.timezone.utc)
    vencimiento = token.fch_exp if token else None
    if vencimiento is not None and vencimiento.tzinfo is None:
        vencimiento = vencimiento.replace(tzinfo=dt.timezone.utc)

    if token is None or vencimiento < ahora:
        raise HTTPException(
            status_code=400, detail="El enlace de recuperación no es válido o ha expirado."
        )

    if body.nueva_contrasena != body.confirmar_contrasena:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden.")

    if not es_password_valido(body.nueva_contrasena):
        raise HTTPException(status_code=400, detail=MSG_POLITICA_INVALIDA)

    usuario = db.query(Usuario).filter(Usuario.id_usr == token.id_usr).first()

    usuario.cntrsn_hsh = hash_password(body.nueva_contrasena)
    usuario.fch_cntrsn_actlzd = ahora
    # HU04: la contraseña temporal ya se reemplazó, así que deja de exigirse
    # el cambio en el próximo login. Sin esto el flag queda pegado en True y
    # el usuario entra en un bucle: cambia la contraseña, vuelve a entrar, y
    # el sistema le sigue pidiendo cambiarla.
    usuario.dbe_cmbr_pswrd = False
    token.usad = True
    db.commit()

    return {"mensaje": "Tu contraseña ha sido actualizada correctamente"}


class CambiarContrasenaRequest(BaseModel):
    contrasena_actual: str
    nueva_contrasena: str
    confirmar_contrasena: str


@router.put("/cambiar-contrasena")
def cambiar_contrasena(
    body: CambiarContrasenaRequest,
    usuario_token: dict = Depends(get_current_user),
    db: Session = Depends(get_db),
):
    """HU 02 CA 3: cambiar la contraseña desde 'Mi perfil' con sesión activa."""
    usuario = db.query(Usuario).filter(Usuario.id_usr == int(usuario_token["sub"])).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if not verify_password(body.contrasena_actual, usuario.cntrsn_hsh):
        raise HTTPException(status_code=400, detail="La contraseña actual es incorrecta.")

    if body.nueva_contrasena != body.confirmar_contrasena:
        raise HTTPException(status_code=400, detail="Las contraseñas no coinciden.")

    if not es_password_valido(body.nueva_contrasena):
        raise HTTPException(status_code=400, detail=MSG_POLITICA_INVALIDA)

    usuario.cntrsn_hsh = hash_password(body.nueva_contrasena)
    usuario.fch_cntrsn_actlzd = dt.datetime.now(dt.timezone.utc)
    # Ver restablecer_contrasena: este es el flujo por el que pasa el
    # usuario nuevo al que se le forzó el cambio en su primer login (HU04),
    # así que es el que tiene que bajar el flag.
    usuario.dbe_cmbr_pswrd = False
    db.commit()

    return {"mensaje": "Contraseña actualizada exitosamente"}
