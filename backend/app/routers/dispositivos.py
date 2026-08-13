"""
HU 10 - Listar dispositivos

CA: tabla con Nombre, Marca, Ubicación y Estado. Búsqueda por nombre o marca
(insensible a mayúsculas). Filtro por ubicación y por estado. Paginado de 10
por defecto. Mismo patrón de acceso que HU07 (routers/ubicaciones.py):
Administrador y Técnico CENERIS ven el listado completo (dentro de su sede);
Cliente Final solo ve dispositivos cuya ubicación esté en PermisoUbicacion.

Dispositivo no tiene id_sd propio (ver mapeo_dispositivo.py): el
aislamiento por sede (HT-09 CA3) se resuelve vía join con Ubicacion, mismo
criterio que mapeos.py e ingesta.py usan con su propio id_sd.

HU 11 - Añadir dispositivo

CA1: formulario con Nombre, Marca, Modelo (opcional), Ubicación y Conexión
FTP. Un campo del modelo NO está en el formulario y el POST lo resuelve
solo (documentado en crear_dispositivo):

  lttd/lngtd (NOT NULL, punto GPS del dispositivo): se copian de la
  Ubicación elegida como valor por defecto. Son columnas independientes de
  las de Ubicacion (no hay FK), así que un dispositivo con punto propio
  distinto al de su ubicación es una decisión de una HU futura, no de esta.

<<<<<<< HEAD
El mapeo de formato (HU06) YA NO es un requisito para crear el
dispositivo: antes el mapeo vivía por marca+sede y tenía que existir de
antemano; ahora cuelga del dispositivo mismo (mp_frmt.id_dspstv), así que
el orden real es dispositivo primero, mapeo después, desde su propia
ficha en Mapeos de Formato.
=======
DEC-09: el dispositivo ya NO resuelve un mapeo de formato al crearse. El
mapeo pasó a colgar del dispositivo (mp_frmt.id_dspstv), así que primero
existe el dispositivo y después se le configura su mapeo en HU06; crear un
dispositivo sin mapeo es un estado válido (todavía no ingesta nada).
>>>>>>> 9cc2710c1fbe0adfb3cde23c8f9f64de00d99853

Además valida (no es un CA literal, pero lo exige la arquitectura de
ingesta ya existente): resolver_dispositivo() en
services/ingesta/persistencia.py asume EXACTAMENTE un dispositivo Activo
por conexión FTP para poder resolver a qué dispositivo pertenece un
archivo entrante. Un segundo dispositivo Activo en la misma conexión
rompería esa resolución en silencio, así que se rechaza con 409.
"""
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database import get_db
from app.models import ConexionFTP, Dispositivo, Ubicacion, PermisoUbicacion
from app.security.permisos import require_permiso, verificar_sede, LECTURA, EDICION
from app.schemas import DispositivoCreado, DispositivoCrear, DispositivoListItem

router = APIRouter(prefix="/dispositivos", tags=["Dispositivos"])

ROLES_CON_ACCESO_TOTAL = {"Administrador", "Tecnico CENERIS", "Técnico CENERIS"}


@router.get("")
def listar_dispositivos(
    busqueda: str | None = Query(default=None, description="Nombre o marca del dispositivo, parcial"),
    id_ubccn: int | None = Query(default=None, description="Filtrar por ubicación"),
    estado: str | None = Query(default=None, description="Activo / Inactivo"),
    pagina: int = Query(default=1, ge=1),
    por_pagina: int = Query(default=10, ge=1, le=100),  # CA: 10 por defecto
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", LECTURA)),
):
    query = db.query(Dispositivo, Ubicacion.nmbr).join(
        Ubicacion, Ubicacion.id_ubccn == Dispositivo.id_ubccn
    )

    # Aislamiento por sede (HT-09 CA3): un usuario 'por_sede' solo ve los
    # dispositivos de ubicaciones de su sede, aunque pida otra explícitamente.
    if usuario.get("scope") == "por_sede":
        query = query.filter(Ubicacion.id_sd == usuario["sede_id"])

    # CA: Administrador/Tecnico CENERIS ven todo; Cliente solo lo asignado.
    if usuario.get("rol") not in ROLES_CON_ACCESO_TOTAL:
        id_usr = int(usuario["sub"])
        query = query.join(
            PermisoUbicacion, PermisoUbicacion.id_ubccn == Dispositivo.id_ubccn
        ).filter(PermisoUbicacion.id_usr == id_usr)

    if busqueda:
        patron = f"%{busqueda.lower()}%"
        query = query.filter(
            func.lower(Dispositivo.nmbr).like(patron) | func.lower(Dispositivo.mrc).like(patron)
        )
    if id_ubccn is not None:
        query = query.filter(Dispositivo.id_ubccn == id_ubccn)
    if estado:
        query = query.filter(Dispositivo.estd == estado)

    total = query.count()
    filas = (
        query.order_by(Dispositivo.nmbr)
        .offset((pagina - 1) * por_pagina)
        .limit(por_pagina)
        .all()
    )

    items = [
        DispositivoListItem(
            id_dspstv=dispositivo.id_dspstv,
            nmbr=dispositivo.nmbr,
            mrc=dispositivo.mrc,
            ubicacion_nombre=ubicacion_nombre,
            estd=dispositivo.estd,
        )
        for dispositivo, ubicacion_nombre in filas
    ]

    return {"total": total, "pagina": pagina, "por_pagina": por_pagina, "items": items}


@router.post("", status_code=201)
def crear_dispositivo(
    body: DispositivoCrear,
    db: Session = Depends(get_db),
    usuario: dict = Depends(require_permiso("Dispositivos", EDICION)),
):
    """CA2: 'GUARDAR' registra el dispositivo con estado 'Activo' y
    devuelve 201 con 'Dispositivo añadido correctamente', mismo formato de
    respuesta que crear_ubicacion (HU08)."""
    ubicacion = db.query(Ubicacion).filter(Ubicacion.id_ubccn == body.id_ubccn).first()
    if ubicacion is None:
        raise HTTPException(status_code=422, detail=f"La ubicación {body.id_ubccn} no existe")
    if ubicacion.estd != "Activa":
        raise HTTPException(
            status_code=422, detail="La ubicación elegida no está Activa"
        )

    conexion = db.query(ConexionFTP).filter(ConexionFTP.id_cnxn == body.id_cnxn).first()
    if conexion is None:
        raise HTTPException(status_code=422, detail=f"La conexión FTP {body.id_cnxn} no existe")

    # Un usuario 'por_sede' no puede crear un dispositivo en una ubicación
    # de otra sede aunque conozca su id_ubccn (HT-09 CA3).
    verificar_sede(usuario, ubicacion.id_sd, modulo="Dispositivos", accion=EDICION)

    # resolver_dispositivo() en services/ingesta/persistencia.py asume
    # exactamente 1 dispositivo Activo por conexión FTP; un segundo
    # rompería en silencio la resolución de archivos entrantes.
    ya_tiene_activo = (
        db.query(Dispositivo)
        .filter(Dispositivo.id_cnxn == body.id_cnxn, Dispositivo.estd == "Activo")
        .first()
    )
    if ya_tiene_activo is not None:
        raise HTTPException(
            status_code=409,
            detail="Esta conexión FTP ya tiene un dispositivo activo asociado",
        )

    dispositivo = Dispositivo(
        id_ubccn=ubicacion.id_ubccn,
        id_cnxn=conexion.id_cnxn,
        nmbr=body.nmbr,
        mrc=body.mrc,
        mdl=body.mdl,
        lttd=ubicacion.lttd,
        lngtd=ubicacion.lngtd,
        # estd lo pone el server_default 'Activo' del modelo.
    )
    db.add(dispositivo)
    db.commit()
    db.refresh(dispositivo)

    return {
        "mensaje": "Dispositivo añadido correctamente",
        "dispositivo": DispositivoCreado.model_validate(dispositivo),
    }
