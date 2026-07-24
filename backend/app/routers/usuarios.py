"""
HU 03 - Listar usuarios

CA: tabla con Nombre, Correo, Rol, Estado y Acciones. Búsqueda por nombre o
correo (insensible a mayúsculas). Filtro por rol y por estado. Paginado de
10 por defecto. Solo el rol Administrador accede a este módulo.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import Usuario, Rol
from app.security.dependencies import get_current_user
from app.security.hashing import generar_password_temporal, hash_password
from app.schemas import UsuarioListItem, UsuarioCrear, UsuarioCreado
from app.tasks.notificaciones import enviar_correo_bienvenida

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


def _requerir_administrador(usuario: dict = Depends(get_current_user)) -> dict:
    """HU 03 CA: 'Solo el rol Administrador puede acceder a este módulo.'"""
    if usuario.get("rol") != "Administrador":
        raise HTTPException(status_code=403, detail="Solo un Administrador puede ver este listado")
    return usuario


@router.get("")
def listar_usuarios(
    busqueda: str | None = Query(default=None, description="Nombre completo o correo, parcial"),
    rol: str | None = Query(default=None, description="Filtrar por nombre de rol"),
    estado: str | None = Query(default=None, description="Activo / Inactivo"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    _admin: dict = Depends(_requerir_administrador),
):
    query = db.query(Usuario).join(Rol, Usuario.id_rl == Rol.id_rl)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(
            or_(
                func.lower(Usuario.nmbr_cmplt).like(patron),
                func.lower(Usuario.crr).like(patron),
            )
        )
    if rol:
        query = query.filter(Rol.nmbr == rol)
    if estado:
        query = query.filter(Usuario.estd == estado)

    total = query.count()
    usuarios = (
        query.order_by(Usuario.nmbr_cmplt)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [
        UsuarioListItem(
            id_usr=u.id_usr,
            nmbr_cmplt=u.nmbr_cmplt,
            crr=u.crr,
            rol_nombre=u.rol.nmbr,
            estd=u.estd,
        )
        for u in usuarios
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.post("", response_model=UsuarioCreado, status_code=201)
def crear_usuario(
    body: UsuarioCrear,
    db: Session = Depends(get_db),
    _admin: dict = Depends(_requerir_administrador),
):
    """HU04: solo el Administrador crea usuarios. Genera una contraseña
    temporal, la hashea, y encola el correo de bienvenida (HU04 CA2).
    """
    rol = db.query(Rol).filter(Rol.nmbr == body.rol_nombre).first()
    if rol is None:
        raise HTTPException(status_code=400, detail=f"Rol '{body.rol_nombre}' no existe")

    password_temporal = generar_password_temporal()

    usuario = Usuario(
        id_rl=rol.id_rl,
        nmbr_cmplt=body.nmbr_cmplt,
        crr=body.crr.lower(),
        tlfn=body.tlfn,
        cntrsn_hsh=hash_password(password_temporal),
        dbe_cmbr_pswrd=True,
    )
    db.add(usuario)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")
    db.refresh(usuario)

    enviar_correo_bienvenida.delay(
        correo=usuario.crr,
        nombre_completo=usuario.nmbr_cmplt,
        password_temporal=password_temporal,
    )

    return UsuarioCreado(
        id_usr=usuario.id_usr,
        nmbr_cmplt=usuario.nmbr_cmplt,
        crr=usuario.crr,
        rol_nombre=rol.nmbr,
        estd=usuario.estd,
    )
