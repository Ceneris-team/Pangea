"""
HU 03 - Listar usuarios / HU 04 - Agregar / HU 20 - Editar / HU 21 - Permisos

CA: tabla con Nombre, Correo, Rol, Estado y Acciones. Búsqueda por nombre o
correo (insensible a mayúsculas). Filtro por rol y por estado. Paginado de
10 por defecto. El acceso al módulo "Usuarios" lo decide prms_usr_sd
(HT-09/HT-03), no un rol hardcodeado: en la práctica hoy solo Administrador
tiene una fila con permiso en ese módulo, pero el control ya no depende del
nombre del rol sino del permiso otorgado.
"""

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import PermisoUbicacion, Rol, Ubicacion, Usuario
from app.schemas import (
    PermisosUbicacionActualizados,
    PermisosUbicacionActualizar,
    PermisosUbicacionPanel,
    UbicacionPermisoItem,
    UsuarioActualizado,
    UsuarioActualizar,
    UsuarioCreado,
    UsuarioCrear,
    UsuarioDetalle,
    UsuarioListItem,
)
from app.security.auditoria import auditar_cambios
from app.security.hashing import generar_password_temporal, hash_password
from app.security.permisos import EDICION, LECTURA, require_permiso
from app.security.ubicaciones_permitidas import ROLES_CON_ACCESO_TOTAL
from app.tasks.notificaciones import enviar_correo_bienvenida

router = APIRouter(prefix="/usuarios", tags=["Usuarios"])


@router.get("")
def listar_usuarios(
    busqueda: str | None = Query(default=None, description="Nombre completo o correo, parcial"),
    rol: str | None = Query(default=None, description="Filtrar por nombre de rol"),
    estado: str | None = Query(default=None, description="Activo / Inactivo"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Usuarios", LECTURA)),
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
        query.order_by(Usuario.nmbr_cmplt).offset((pagina - 1) * por_pagina).limit(por_pagina).all()
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
    _usuario: dict = Depends(require_permiso("Usuarios", EDICION)),
):
    """HU04: crear usuarios requiere permiso de Edición en el módulo
    Usuarios (HT-09). Genera una contraseña temporal, la hashea, y encola
    el correo de bienvenida (HU04 CA2).
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


# ---------------------------------------------------------------------------
# HU 20 - Editar usuario
# ---------------------------------------------------------------------------


@router.get("/{id_usr}", response_model=UsuarioDetalle)
def obtener_usuario(
    id_usr: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Usuarios", LECTURA)),
):
    """HU20 CA1: los datos actuales con los que el formulario de edición se
    precarga -Nombre completo, Correo electrónico, Rol y Teléfono-.

    Va con permiso de LECTURA y no de Edición: es la misma consulta que ya
    alimenta el listado (HU03), solo que de un usuario puntual y con el
    teléfono incluido. Quien pueda ver el listado puede ver la ficha; lo
    que exige Edición es guardar (PUT).
    """
    usuario = db.query(Usuario).filter(Usuario.id_usr == id_usr).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    return UsuarioDetalle(
        id_usr=usuario.id_usr,
        nmbr_cmplt=usuario.nmbr_cmplt,
        crr=usuario.crr,
        rol_nombre=usuario.rol.nmbr,
        tlfn=usuario.tlfn,
        estd=usuario.estd,
    )


@router.put("/{id_usr}", response_model=UsuarioActualizado)
def actualizar_usuario(
    id_usr: int,
    body: UsuarioActualizar,
    # HT-11 CA1: en vez de get_db, auditar_cambios -que internamente
    # también entrega la sesión- marca en db.info quién ejecuta este PUT,
    # para que el listener de before_flush (security/auditoria.py) arme la
    # fila de lg_adtr automáticamente en el mismo commit de más abajo.
    db: Session = Depends(auditar_cambios),
    usuario_actual: dict = Depends(require_permiso("Usuarios", EDICION)),
):
    """HU20 CA2: actualiza los datos y responde con el mensaje exacto
    "Usuario actualizado correctamente".

    Mismos permisos y errores que el alta de HU04 -Edición sobre el módulo
    "Usuarios" (que hoy solo tiene el Administrador, cumpliendo "solo el
    rol Administrador puede editar usuarios" sin hardcodear el nombre del
    rol, igual que HU03/HU04), 400 si el rol no existe, 409 si el correo ya
    está tomado- y PUT como el resto de los recursos del proyecto
    (ubicaciones, dispositivos, conexiones_ftp, mapeos; ver DEC-29).

    El body es parcial: solo se toca lo que venga.

    Regla de la conversación de HU20: el Administrador NO puede cambiar su
    PROPIO rol desde este módulo -se rechaza explícitamente con 409-, pero
    sí puede editar el resto de sus campos. Evita que el único
    Administrador se quite a sí mismo el acceso al módulo por descuido y se
    deje al sistema sin quien administre usuarios.

    El historial de cambios no se registra ni se expone: queda fuera de
    v1.0 por decisión del .docx, y la auditoría formal es alcance de HT-11.
    """
    usuario = db.query(Usuario).filter(Usuario.id_usr == id_usr).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    datos = body.model_dump(exclude_unset=True)

    # tlfn es la única columna nullable del conjunto: un string vacío se
    # normaliza a NULL. El resto son NOT NULL, así que un null explícito se
    # descarta -significa "no lo toques"- en vez de reventar en el commit.
    if "tlfn" in datos:
        datos["tlfn"] = (datos["tlfn"].strip() or None) if datos["tlfn"] else None
    for campo in ("nmbr_cmplt", "crr", "rol_nombre"):
        if campo in datos and datos[campo] is None:
            del datos[campo]

    # Rol: se traduce el nombre al id, con el mismo 400 de HU04 si no existe.
    rol_nuevo = None
    if "rol_nombre" in datos:
        rol_nuevo = db.query(Rol).filter(Rol.nmbr == datos["rol_nombre"]).first()
        if rol_nuevo is None:
            raise HTTPException(status_code=400, detail=f"Rol '{datos['rol_nombre']}' no existe")

        # Regla de negocio HU20: nadie edita su propio rol desde este módulo.
        # Se compara contra el id del JWT (HT-04), no contra el rol que dice
        # traer el token. Mandar el rol que YA tiene no es un cambio, así que
        # no se rechaza: guardar el formulario sin tocar el selector debe
        # funcionar.
        if int(usuario_actual["sub"]) == id_usr and rol_nuevo.id_rl != usuario.id_rl:
            raise HTTPException(
                status_code=409, detail="No puedes modificar tu propio rol desde este módulo"
            )

        datos["id_rl"] = rol_nuevo.id_rl
        del datos["rol_nombre"]

    # Correo: editable siempre que el nuevo valor no lo tenga OTRO usuario.
    # Se normaliza a minúsculas igual que en el alta (HU04).
    if "crr" in datos:
        datos["crr"] = datos["crr"].lower()
        duplicado = (
            db.query(Usuario)
            .filter(
                func.lower(Usuario.crr) == datos["crr"],
                Usuario.id_usr != id_usr,
            )
            .first()
        )
        if duplicado is not None:
            raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")

    for campo, valor in datos.items():
        setattr(usuario, campo, valor)

    try:
        db.commit()
    except IntegrityError:
        # Red de seguridad ante dos ediciones simultáneas: el UNIQUE real de
        # usr.crr es la garantía, el chequeo de arriba solo da el mensaje.
        db.rollback()
        raise HTTPException(status_code=409, detail="Ya existe un usuario con ese correo")
    db.refresh(usuario)

    return UsuarioActualizado(
        id_usr=usuario.id_usr,
        nmbr_cmplt=usuario.nmbr_cmplt,
        crr=usuario.crr,
        rol_nombre=usuario.rol.nmbr,
        tlfn=usuario.tlfn,
        estd=usuario.estd,
    )


# ---------------------------------------------------------------------------
# HU 21 - Conceder permisos (acceso por ubicación)
# ---------------------------------------------------------------------------


def _usuario_gestionable_o_error(db: Session, id_usr: int) -> Usuario:
    """Regla de negocio de HU21: la gestión de permisos aplica ÚNICAMENTE a
    usuarios con rol Cliente Final.

    Administrador y Técnico CENERIS ya tienen acceso completo por defecto
    -es exactamente lo que decide ROLES_CON_ACCESO_TOTAL en
    security/ubicaciones_permitidas.py, la misma constante que usan los
    módulos de consulta- y por eso no requieren asignación: escribirles
    filas en prms_ubccn no cambiaría nada de lo que ven y solo dejaría
    datos engañosos en la tabla. Se responde 409 (conflicto con el estado
    del recurso) en vez de 403, que es lo que devuelve require_permiso
    cuando el problema es QUIÉN pide, no SOBRE QUIÉN se pide.

    La interfaz además no ofrece la acción para esos roles (CA1), así que
    llegar acá con uno de ellos es un intento de saltarse la interfaz.
    """
    usuario = db.query(Usuario).filter(Usuario.id_usr == id_usr).first()
    if usuario is None:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")

    if usuario.rol.nmbr in ROLES_CON_ACCESO_TOTAL:
        raise HTTPException(
            status_code=409,
            detail=(
                f"El rol '{usuario.rol.nmbr}' ya tiene acceso completo a todas las "
                "ubicaciones y no requiere asignación de permisos"
            ),
        )
    return usuario


@router.get("/{id_usr}/permisos-ubicaciones", response_model=PermisosUbicacionPanel)
def listar_permisos_ubicaciones(
    id_usr: int,
    db: Session = Depends(get_db),
    _usuario: dict = Depends(require_permiso("Usuarios", LECTURA)),
):
    """HU21 CA1: el panel de permisos, con el listado de TODAS las
    ubicaciones registradas y el estado de acceso actual del usuario.

    Se listan todas -no solo las concedidas- porque el panel es de
    marcar/desmarcar: sin las no concedidas no habría nada que marcar.
    """
    usuario = _usuario_gestionable_o_error(db, id_usr)

    concedidas = {
        fila.id_ubccn
        for fila in db.query(PermisoUbicacion).filter(PermisoUbicacion.id_usr == id_usr).all()
    }

    ubicaciones = db.query(Ubicacion).order_by(Ubicacion.nmbr).all()

    return PermisosUbicacionPanel(
        id_usr=usuario.id_usr,
        nmbr_cmplt=usuario.nmbr_cmplt,
        rol_nombre=usuario.rol.nmbr,
        items=[
            UbicacionPermisoItem(
                id_ubccn=u.id_ubccn,
                nmbr=u.nmbr,
                tiene_acceso=u.id_ubccn in concedidas,
            )
            for u in ubicaciones
        ],
    )


@router.put("/{id_usr}/permisos-ubicaciones", response_model=PermisosUbicacionActualizados)
def actualizar_permisos_ubicaciones(
    id_usr: int,
    body: PermisosUbicacionActualizar,
    # HT-11 CA1: ver el comentario equivalente en actualizar_usuario.
    db: Session = Depends(auditar_cambios),
    _usuario: dict = Depends(require_permiso("Usuarios", EDICION)),
):
    """HU21 CA2: reemplaza el conjunto de ubicaciones habilitadas y responde
    con el mensaje exacto "Permisos actualizados correctamente".

    Reemplaza en vez de sumar: el panel manda el conjunto completo, así que
    borrar lo que sobra y agregar lo que falta deja la tabla exactamente
    como se ve en pantalla. Solo se tocan las filas que cambian -no un
    DELETE de todo seguido de un INSERT de todo- para no invalidar el
    UNIQUE ni reescribir filas que ya estaban bien.

    CA3: los cambios tienen efecto INMEDIATO, sin cerrar sesión. Eso sale
    solo de escribir en prms_ubccn: los módulos de consulta resuelven las
    ubicaciones visibles en cada request vía
    security/ubicaciones_permitidas.py, contra la base de datos. Por eso
    el conjunto permitido NO viaja en el JWT -si viajara, un permiso
    recién quitado seguiría vigente hasta que expirara el token-.
    """
    _usuario_gestionable_o_error(db, id_usr)

    solicitadas = set(body.ubicacion_ids)

    # Ubicaciones inexistentes -> 400, mismo criterio que el rol inexistente
    # de HU04/HU20: es un id que la interfaz no pudo haber ofrecido.
    if solicitadas:
        existentes = {
            fila[0]
            for fila in db.query(Ubicacion.id_ubccn)
            .filter(Ubicacion.id_ubccn.in_(solicitadas))
            .all()
        }
        faltantes = solicitadas - existentes
        if faltantes:
            ids = ", ".join(str(i) for i in sorted(faltantes))
            raise HTTPException(status_code=400, detail=f"No existe la ubicación: {ids}")

    actuales = {
        fila.id_ubccn: fila
        for fila in db.query(PermisoUbicacion).filter(PermisoUbicacion.id_usr == id_usr).all()
    }

    for id_ubccn, fila in actuales.items():
        if id_ubccn not in solicitadas:
            db.delete(fila)

    for id_ubccn in solicitadas - set(actuales):
        db.add(PermisoUbicacion(id_usr=id_usr, id_ubccn=id_ubccn))

    try:
        db.commit()
    except IntegrityError:
        # Red de seguridad ante dos ediciones simultáneas del mismo panel:
        # uq_prmsubccn_usr_ubccn es la garantía real de no duplicar accesos.
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Los permisos cambiaron mientras guardabas, vuelve a intentarlo"
        )

    return PermisosUbicacionActualizados(
        id_usr=id_usr,
        ubicacion_ids=sorted(solicitadas),
    )
